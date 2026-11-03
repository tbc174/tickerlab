"""As rotas da API externa do TickerLab Data, em `/data/v1` (B-32a; ADR 0108).

Só entram no app com `TICKERLAB_API_EXTERNA=1` (`src/api.py`). Cada rota recebe a organização pela
chave (`acesso`), faz a conta em `src/` e traduz as chaves para o inglês na saída, num lugar só
(`nomes.traduzir_chaves`). O catálogo e o consumo não servem dado: não gastam a quota do mês nem entram
no consumo, mas contam no limite do minuto.

As rotas de dado contam na quota do mês (o lote conta um por CNPJ válido) e passam cada campo pelo
contrato da organização e pelo portão (`acesso.autorizar`). Toda recusa sai como `not_available`, o
mesmo de um CNPJ que não existe, para não dizer qual foi o motivo.
"""

import math
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from functools import cache
from typing import Annotated

import duckdb
import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from base import porta as porta_da_base
from base.porta import Porta
from src.api_externa import acesso, lote
from src.api_externa.catalogo import catalogo_da_organizacao, consumo_da_organizacao
from src.api_externa.conjuntos import fundos
from src.api_externa.envelope import fontes_da_resposta
from src.api_externa.nomes import traduzir_chaves
from src.banco.chaves_da_api import registrar_consumo
from src.banco.conexao import obter_engine
from src.chaves_da_api import ContextoDaChave
from src.portao_externo import Finalidade, Regras

router = APIRouter(prefix="/data/v1")

ChaveSemQuota = Annotated[
    ContextoDaChave, Depends(acesso.exigir_chave_sem_quota_do_mes)
]
Chave = Annotated[ContextoDaChave, Depends(acesso.exigir_chave)]

FINALIDADE = Finalidade.ANALISE.value  # o beta só tem contratos de análise
NAO_DISPONIVEL = "not_available"
# 100% ao ano: acima disso a conta de exemplo deixa de ser plausível
RETORNO_SUPOSTO_MAXIMO = 1.0


def regras_da_api() -> Regras | None:
    """As regras do portão: None vale as vigentes (os testes trocam esta função)."""
    return None


def abrir_porta(banco: sa.Connection) -> Porta:
    """A porta da base, com o registro de coletas para a linhagem (os testes trocam esta função)."""
    return porta_da_base.abrir(banco=banco)


def _fora_do_ar() -> HTTPException:
    return HTTPException(status_code=503, detail="service_unavailable")


@contextmanager
def _porta(banco: sa.Connection) -> Iterator[Porta]:
    """A porta aberta; 503 sem dizer onde nem por quê se a base não está neste servidor ou falha na
    leitura (a transação volta e o pedido não conta no consumo)."""
    try:
        porta = abrir_porta(banco)
    except (ImportError, OSError, ValueError) as erro:
        raise _fora_do_ar() from erro
    with porta:
        try:
            yield porta
        except (duckdb.Error, OSError) as erro:
            raise _fora_do_ar() from erro


def _recusa(codigo: str) -> HTTPException:
    return HTTPException(status_code=400, detail=codigo)


def _dia_pedido(known_at: date | None) -> date:
    """O `known_at` do pedido (sem ele, hoje); 400 se está no futuro."""
    hoje = acesso.agora().date()
    if known_at is None:
        return hoje
    if known_at > hoje:
        raise _recusa("invalid_known_at")
    return known_at


def _retorno_pedido(assumed_return: float | None) -> float | None:
    """O retorno suposto do cliente; 400 se não é um número ou está fora do plausível."""
    if assumed_return is None:
        return None
    if not math.isfinite(assumed_return) or not (
        -1 < assumed_return <= RETORNO_SUPOSTO_MAXIMO
    ):
        raise _recusa("invalid_assumed_return")
    return assumed_return


def _portao(
    conexao: sa.Connection, contexto: ContextoDaChave, conjunto: str
) -> fundos.Permitido:
    """O contrato da organização e o portão, uma pergunta por fonte e campo dentro do pedido."""
    hoje = acesso.agora().date()
    regras = regras_da_api()

    @cache
    def permitido(fonte: str, campo: str, derivado: bool) -> bool:
        return acesso.autorizar(
            conexao, contexto, fonte=fonte, conjunto=conjunto, campo=campo,
            finalidade=FINALIDADE, hoje=hoje, derivado=derivado, regras=regras,
        ).libera  # fmt: skip

    return permitido


def _leitor(
    conexao: sa.Connection, porta: Porta, contexto: ContextoDaChave
) -> fundos.LeitorDeFundos:
    return fundos.LeitorDeFundos(
        porta,
        _portao(conexao, contexto, fundos.CONJUNTO),
        acesso.linhas_por_resposta(contexto),
    )


@router.get("/catalog")
def catalogo(contexto: ChaveSemQuota) -> object:
    """O que esta chave pode pedir hoje: conjuntos, campos, licença e atribuição de cada fonte."""
    with obter_engine().connect() as conexao:
        corpo = catalogo_da_organizacao(
            conexao, contexto, acesso.agora().date(), regras_da_api()
        )
    return traduzir_chaves(corpo)


@router.get("/usage")
def consumo(contexto: ChaveSemQuota) -> object:
    """O consumo do mês da própria organização, os limites do plano e o que falta da quota."""
    with obter_engine().connect() as conexao:
        corpo = consumo_da_organizacao(conexao, contexto, acesso.agora().date())
    return traduzir_chaves(corpo)


class LoteDeFundos(BaseModel):
    """O corpo do lote: até 100 CNPJs, um `known_at` e um `assumed_return` para todos."""

    cnpjs: list[object]
    known_at: date | None = None
    assumed_return: float | None = None


# o lote vem antes de `/funds/{cnpj}` só por clareza: um é POST, o outro GET
@router.post("/funds/batch")
def lote_de_fundos(pedido: LoteDeFundos, contexto: Chave) -> object:
    """O mesmo de `/funds/{cnpj}` para cada CNPJ; conta um pedido por CNPJ válido e distinto."""
    try:
        lido = lote.ler_lote(pedido.cnpjs)
    except lote.LoteInvalidoError as erro:
        raise _recusa("invalid_batch") from erro
    dia = _dia_pedido(pedido.known_at)
    retorno = _retorno_pedido(pedido.assumed_return)
    itens: list[dict] = []
    fontes: set[str] = set()
    linhas = 0
    with obter_engine().begin() as conexao:
        # o lote inteiro cabe na quota ou volta 429 antes de ler qualquer fundo
        acesso.exigir_quota(conexao, contexto, lido.pedidos, acesso.agora())
        with _porta(conexao) as porta:
            leitor = _leitor(conexao, porta, contexto)
            for cnpj in lido.validos:
                servido = leitor.fundo(cnpj, dia, retorno)
                if servido is None:
                    itens.append({"cnpj": cnpj, "situacao_do_item": NAO_DISPONIVEL})
                    continue
                itens.append({"situacao_do_item": "ok"} | servido.corpo)
                fontes |= servido.fontes
                linhas += servido.linhas
        registrar_consumo(
            conexao, contexto, conjunto=fundos.CONJUNTO, finalidade=FINALIDADE,
            linhas=linhas, pedidos=lido.pedidos, agora=acesso.agora(),
        )  # fmt: skip
    itens += [
        {"cnpj": invalido, "situacao_do_item": "invalid_cnpj"}
        for invalido in lido.invalidos
    ]
    corpo = {
        "como_era_em": dia.isoformat(),
        "itens": itens,
        "fontes": fontes_da_resposta(fontes),
    }
    return traduzir_chaves(corpo)


@router.get("/funds/{cnpj}")
def fundo(
    cnpj: str,
    contexto: Chave,
    known_at: date | None = None,
    assumed_return: float | None = None,
) -> object:
    """Taxas, custo da taxa e carteira do fundo como eram em `known_at`; o custo só com `assumed_return`."""
    lido = lote.ler_lote([cnpj])
    if not lido.validos:
        raise _recusa("invalid_cnpj")
    dia, retorno = _dia_pedido(known_at), _retorno_pedido(assumed_return)
    with obter_engine().begin() as conexao:
        with _porta(conexao) as porta:
            servido = _leitor(conexao, porta, contexto).fundo(
                lido.validos[0], dia, retorno
            )
        # a recusa conta como negada; o 404 sai depois do `with` para o consumo não voltar atrás
        registrar_consumo(
            conexao, contexto, conjunto=fundos.CONJUNTO, finalidade=FINALIDADE,
            linhas=0 if servido is None else servido.linhas, negado=servido is None,
            agora=acesso.agora(),
        )  # fmt: skip
    if servido is None:
        raise HTTPException(status_code=404, detail=NAO_DISPONIVEL)
    corpo = servido.corpo | {"fontes": fontes_da_resposta(servido.fontes)}
    return traduzir_chaves(corpo)
