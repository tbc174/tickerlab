"""Um fundo da CVM na tela (linha 664, d): o raio-x de fundo da API externa, em tipos simples.

A conta é a da API (`LeitorDeFundos`: cadastro, custo da taxa e carteira "como era no dia", sem olhar o
futuro); muda o portão. Na tela a regra é a do app (ADR 0102, canal `tela`), não o contrato de uma chave.
O raio-x lê a base pela porta (`TICKERLAB_ACERVO`); onde a base não está, `FundoIndisponivelError` e a
tela diz que não está aqui, sem dar a entender que o fundo não existe.
"""

from dataclasses import dataclass
from datetime import date

import duckdb

from base import cnpj as cnpj_
from base import porta as porta_da_base
from src.api_externa.conjuntos import Permitido, fundos
from src.api_externa.envelope import ATRIBUICOES_DA_API
from src.banco.conexao import obter_engine
from src.portao_externo import Canal, Finalidade, Pedido, decidir

LINHAS_MAXIMAS_DA_CARTEIRA = 200
ATRIBUICAO = ATRIBUICOES_DA_API["cvm"]


class FundoIndisponivelError(Exception):
    """A base dos fundos não está neste servidor, ou a leitura falhou."""


@dataclass(frozen=True)
class FundoNaTela:
    """O que a tela mostra de um fundo; cada lista é uma tabela pronta."""

    cnpj: str
    como_era_em: date
    cadastro: dict[str, object]
    cadastro_publico_em: date | None
    custo_da_taxa: list[dict[str, float]]
    retorno_suposto: float | None
    carteira: list[dict[str, object]]
    carteira_cortada: bool


def _permitido(hoje: date) -> Permitido:
    """O portão do app para um campo dos fundos: a regra da ADR 0102, canal `tela`."""

    def permitido(fonte: str, campo: str, derivado: bool) -> bool:
        pedido = Pedido(
            fonte, fundos.CONJUNTO, campo, Canal.TELA, Finalidade.ANALISE, derivado
        )
        return decidir(pedido, hoje).libera

    return permitido


def _valores(campos: dict[str, dict]) -> dict[str, object]:
    return {nome: c["valor"] for nome, c in campos.items()}


def _dia(texto: str | None) -> date | None:
    return None if texto is None else date.fromisoformat(texto)


def _custo(custo: dict | None) -> list[dict[str, float]]:
    if custo is None:
        return []
    return [
        {"anos": prazo["anos"]}
        | _valores({k: v for k, v in prazo.items() if k != "anos"})
        for prazo in custo["prazos"]
    ]


def _montar(corpo: dict, como_era_em: date, retorno: float | None) -> FundoNaTela:
    cadastro = corpo.get("cadastro", {})
    datas = {c["publico_em"] for c in cadastro.values()}
    carteira = corpo["carteira"]
    return FundoNaTela(
        cnpj=corpo["cnpj"],
        como_era_em=como_era_em,
        cadastro=_valores(cadastro),
        cadastro_publico_em=_dia(max(datas)) if datas else None,
        custo_da_taxa=_custo(corpo.get("custo_da_taxa")),
        retorno_suposto=retorno,
        carteira=[_valores(posicao) for posicao in carteira["posicoes"]],
        carteira_cortada=carteira["cortada"],
    )


def fundo_na_tela(
    cnpj: str, hoje: date, retorno_suposto: float | None = None
) -> FundoNaTela | None:
    """O fundo como é em `hoje`; None se não está na base ou nada dele pode ser mostrado.

    `ValueError` com CNPJ inválido; `FundoIndisponivelError` sem a base neste servidor.
    `retorno_suposto` é o retorno bruto ao ano que a pessoa supõe: sem ele não há custo da taxa.
    """
    if not cnpj_.normalizar_cnpj(cnpj):
        raise ValueError(f"CNPJ inválido: {cnpj!r}")
    try:
        with (
            obter_engine().connect() as conexao,
            porta_da_base.abrir(banco=conexao) as porta,
        ):
            leitor = fundos.LeitorDeFundos(
                porta, _permitido(hoje), LINHAS_MAXIMAS_DA_CARTEIRA
            )
            servido = leitor.fundo(cnpj, hoje, retorno_suposto)
    except (ImportError, OSError, ValueError, duckdb.Error) as erro:
        raise FundoIndisponivelError from erro  # ValueError: acervo desligado
    return None if servido is None else _montar(servido.corpo, hoje, retorno_suposto)
