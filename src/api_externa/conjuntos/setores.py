"""O setor do molde D na API externa (linha 781): o tamanho e a concentração do mercado e quem são as
companhias abertas dele, campo a campo pelo portão.

`LeitorDeSetores(permitido, linhas_maximas, pasta).setor(chave, como_era_em)` devolve, em tipos simples e
com as chaves em português (a rota traduz na saída), a seção `setor` da ficha da noite
(`src.dossie.secao_do_setor`, molde D de `docs/padrao-de-analise.md`), já conferida pelas regras da base
(série de agência só com fonte vendável). É a exceção ao "só pela porta da base" dos outros conjuntos: o
setor é uma conta da noite sobre várias tabelas (a série da agência, a ligação às companhias, o cadastro da
CVM), e a ficha é o lugar onde essa conta já está feita e conferida, a mesma que o app e o PDF mostram.

Cada coluna passa pelo portão com a fonte de onde saiu: a concentração (`concentracao_<série>`) e a
participação das companhias (`participacao_dos_membros`) pela fonte da agência da série, a lista das
companhias pela CVM. Coluna sem linha de direito não aparece.

A parte que o portão não libera não some em silêncio (linha 882, `src/api_externa/nao_disponivel.py`): sem a
série, o mercado leria como "a agência não mede"; sem a lista das companhias, como "o setor não tem companhia
aberta". A série sem nenhuma coluna liberada vai em `series_nao_disponiveis` (o nome dela) e a lista das
companhias barrada vai em `blocos_nao_disponiveis`; os limites avisam que a resposta não diz nada sobre elas.

Datas: a base não guarda quando a agência publicou cada mês da série nem quando a ligação ficou pública
(`ITENS_SEM_DATA_DE_PUBLICACAO` da base), então `publico_em` é o dia da noite (o dado já era público nele,
no máximo) e `visto_em` sai vazio. Só existe a noite mais nova: um `known_at` antes dela não tem resposta.

Nada de pessoa física: as linhas são de mercado (agregado) e de companhia aberta. Linha de companhia sem
CNPJ de 14 dígitos não sai, mesmo que a noite a traga. O lado a lado por entidade e o mercado de energia
(CCEE, ONS) ficam fora desta versão.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src import dossie
from src.api_externa import nao_disponivel
from src.api_externa.conjuntos import Permitido
from src.api_externa.envelope import campo
from src.api_externa.nomes import NOMES_DE_FORA
from src.relatorio_setor import POR_CHAVE

CONJUNTO = "sectors"
FONTE_DOS_MEMBROS = "cvm-cadastros"
TABELA_DA_PARTICIPACAO = "participacao_dos_membros"
TABELA_DOS_MEMBROS = "membros"
COLUNAS_DA_CONCENTRACAO = (
    "ano", "participantes", "total", "cr4", "hhi", "faixa", "delta_hhi", "meses", "ultimo_mes",
    "por_entidade",
)  # fmt: skip
COLUNAS_DA_PARTICIPACAO = (
    "cnpj", "empresa", "ano", "valor", "participacao", "meses", "ultimo_mes",
)  # fmt: skip
COLUNAS_DOS_MEMBROS = ("cnpj", "empresa", "motivo")
TAMANHO_DO_CNPJ = 14
TAMANHO_DO_DIA = 10  # "2025-12-31" (a noite pode gravar "2025-12-31T00:00:00")
# os nomes de dentro das listas do que o portão não libera: as séries de agência e os blocos (os membros)
SERIES_NAO_DISPONIVEIS = "series_nao_disponiveis"
BLOCOS_NAO_DISPONIVEIS = "blocos_nao_disponiveis"
LIMITE_DA_SERIE_NAO_DISPONIVEL = nao_disponivel.aviso(
    SERIES_NAO_DISPONIVEIS, "séries", "o mercado do setor"
)
LIMITE_DO_BLOCO_NAO_DISPONIVEL = nao_disponivel.aviso(
    BLOCOS_NAO_DISPONIVEIS, "blocos", "a resposta"
)


def limites(series_de_fora: Sequence[str], blocos_de_fora: Sequence[str]) -> list[str]:
    """Os limites de um setor: só os avisos das listas que não estão vazias."""
    return [
        aviso
        for aviso, de_fora in (
            (LIMITE_DA_SERIE_NAO_DISPONIVEL, series_de_fora),
            (LIMITE_DO_BLOCO_NAO_DISPONIVEL, blocos_de_fora),
        )
        if de_fora
    ]


@dataclass(frozen=True)
class SetorServido:
    """O que sai de um setor: o corpo, as fontes usadas (para a atribuição) e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def _simples(nome: str, valor: object) -> object:
    """O valor da ficha num tipo que vira JSON: o mês em ISO e o número que não é número em None."""
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    if nome == "ultimo_mes" and isinstance(valor, str):
        return valor[:TAMANHO_DO_DIA]
    return valor


def _e_empresa(linha: dict) -> bool:
    """A linha é de companhia (CNPJ de 14 dígitos), nunca de pessoa."""
    cnpj = str(linha.get("cnpj") or "")
    return len(cnpj) == TAMANHO_DO_CNPJ and cnpj.isdigit()


def disponiveis(pasta: Path | None = None) -> list[dict]:
    """Os setores do relatório que a noite gravou, com o dia dela; nenhum dado do setor."""
    return [
        {"setor": chave, "nome": setor.nome, "como_era_em": noite.dia.isoformat()}
        for chave, setor in POR_CHAVE.items()
        if (noite := dossie.secao_do_setor(chave, pasta)) is not None
    ]


class LeitorDeSetores:
    """Lê um setor da ficha da noite para um pedido."""

    def __init__(
        self, permitido: Permitido, linhas_maximas: int, pasta: Path | None = None
    ) -> None:
        self.permitido = permitido
        self.linhas_maximas = linhas_maximas
        self.pasta = pasta
        self._restantes = linhas_maximas
        self._cortada = False
        self._fontes: set[str] = set()
        self._series_de_fora: list[str] = []

    def _liberada(self, fonte: str, colunas: tuple[str, ...], derivado: bool) -> bool:
        """O portão libera alguma das colunas dessa fonte."""
        return any(self.permitido(fonte, nome, derivado) for nome in colunas)

    def _linha(
        self,
        linha: dict,
        colunas: tuple[str, ...],
        fonte: str,
        dia: date,
        derivado: bool,
    ) -> dict | None:
        servida = {
            nome: campo(_simples(nome, linha.get(nome)), fonte=fonte, publico_em=dia, visto_em=None)
            for nome in colunas
            if self.permitido(fonte, nome, derivado)
        }  # fmt: skip
        return servida or None

    def _linhas(
        self,
        linhas: list[dict],
        colunas: tuple[str, ...],
        fonte: str,
        dia: date,
        derivado: bool,
    ) -> list[dict]:
        """As linhas liberadas, até o limite do plano (o resto marca a resposta como cortada)."""
        servidas = []
        for linha in linhas:
            servida = self._linha(linha, colunas, fonte, dia, derivado)
            if servida is None:
                continue
            if self._restantes == 0:
                self._cortada = True
                break
            servidas.append(servida)
            self._restantes -= 1
            self._fontes.add(fonte)
        return servidas

    def _series(self, secao: dossie.SecaoDaFicha, dia: date) -> list[dict]:
        """Uma entrada por série de agência: a concentração e a participação de cada companhia."""
        participacao = [
            linha
            for linha in secao.tabelas.get(TABELA_DA_PARTICIPACAO, [])
            if _e_empresa(linha)
        ]
        series = []
        for nome_da_tabela, linhas in secao.tabelas.items():
            if not nome_da_tabela.startswith(dossie.PREFIXO_DA_CONCENTRACAO):
                continue
            serie = dossie.serie_da_tabela_do_setor(nome_da_tabela)
            if serie is None:
                continue
            fonte = serie.fonte_b13
            colunas = (*COLUNAS_DA_CONCENTRACAO, *COLUNAS_DA_PARTICIPACAO)
            if not self._liberada(fonte, colunas, True):
                self._series_de_fora.append(serie.nome)
                continue
            concentracao = self._linhas(
                linhas, COLUNAS_DA_CONCENTRACAO, fonte, dia, True
            )
            da_serie = [
                linha for linha in participacao if linha.get("serie") == serie.nome
            ]
            partes = self._linhas(da_serie, COLUNAS_DA_PARTICIPACAO, fonte, dia, True)
            if concentracao or partes:
                series.append(
                    {
                        "serie": serie.nome,
                        "concentracao": concentracao,
                        TABELA_DA_PARTICIPACAO: partes,
                    }
                )
        return series

    def setor(self, chave: str, como_era_em: date) -> SetorServido | None:
        """O setor como a noite o deixou, se `como_era_em` é dela em diante; None se nada sai."""
        setor = POR_CHAVE.get(chave)
        noite = dossie.secao_do_setor(chave, self.pasta) if setor else None
        if setor is None or noite is None or como_era_em < noite.dia:
            return None
        series = self._series(noite.secao, noite.dia)
        membros = [
            linha
            for linha in noite.secao.tabelas.get(TABELA_DOS_MEMBROS, [])
            if _e_empresa(linha)
        ]
        membros_servidos = self._linhas(
            membros, COLUNAS_DOS_MEMBROS, FONTE_DOS_MEMBROS, noite.dia, False
        )
        linhas = self.linhas_maximas - self._restantes
        if linhas == 0:
            return None
        blocos_de_fora = (
            []
            if self._liberada(FONTE_DOS_MEMBROS, COLUNAS_DOS_MEMBROS, False)
            else [TABELA_DOS_MEMBROS]
        )
        corpo = {
            "setor": chave,
            "nome": setor.nome,
            "como_era_em": noite.dia.isoformat(),
            "por_serie": series,
            TABELA_DOS_MEMBROS: membros_servidos,
            "avisos": list(noite.secao.paragrafos),
            "cortada": self._cortada,
            SERIES_NAO_DISPONIVEIS: list(self._series_de_fora),
            BLOCOS_NAO_DISPONIVEIS: [NOMES_DE_FORA[b] for b in blocos_de_fora],
            "limites": limites(self._series_de_fora, blocos_de_fora),
        }
        return SetorServido(corpo, set(self._fontes), linhas)
