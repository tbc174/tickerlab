"""As DFP e os ITR como eram na API externa (B-32a, PR 3): `demonstracoes_como_era` campo a campo, pelo portão.

`LeitorDeDemonstracoes(porta, permitido, linhas_maximas).demonstracoes(cnpj, como_era_em, fim)` devolve, em
tipos simples e com as chaves em português (a rota traduz na saída), um valor por fato (conta de um período)
como era público em `como_era_em`: a versão 1 até a reapresentação, a reapresentação até o balanço seguinte
refazer o ano, e assim por diante (`base/ponto_no_tempo.py`). A porta faz o corte (`publico_em ≤ D` e `ate`
vazio ou depois de D) e esconde o fim que só veio depois.

Cada linha diz de onde veio: o documento (DFP ou ITR), a data a que ele se refere, a versão e a origem (dados
abertos ou XML do ENET). A fonte de cada linha é a do documento (`cvm-hist-dfp` ou `cvm-hist-itr`), e a data
de publicação é o dia da entrega à CVM. A base não guarda quando o TickerLab viu cada valor: `visto_em` sai
vazio. As linhas saem do período mais novo para o mais velho, cortadas no limite do plano.

O documento (DFP, ITR) que o portão não libera não some em silêncio (linha 882,
`src/api_externa/nao_disponivel.py`): sem as linhas do ITR, a resposta leria como "a companhia não entregou
ITR". Ele vai em `entregas_nao_disponiveis` (o mesmo nome de fora do perfil, `unavailable_filings`) e os
limites avisam que a lista de linhas não diz nada sobre ele; sem nenhum documento liberado, nada sai.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from itertools import islice

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from src.api_externa import nao_disponivel
from src.api_externa.conjuntos import Permitido
from src.api_externa.envelope import campo

CONJUNTO = "financials"
TABELA = "demonstracoes_como_era"
FONTES_DOS_DOCUMENTOS = {"DFP": "cvm-hist-dfp", "ITR": "cvm-hist-itr"}
CAMPOS = (
    "demonstracao", "grupo", "conta", "descricao", "valor", "inicio", "fim",
    "documento", "referencia", "versao", "origem", "ate",
)  # fmt: skip
DATAS = ("inicio", "fim", "referencia", "ate")
PUBLICADO_EM = "divulgado_em"
# o período mais novo primeiro; dentro dele, a ordem do plano de contas
ORDEM = ("fim", "demonstracao", "grupo", "conta", "inicio")
CRESCENTE = (False, True, True, True, True)
# o nome de dentro da lista dos documentos que o portão não libera (o mesmo do perfil, `conjuntos/ficha.py`)
NAO_DISPONIVEIS = "entregas_nao_disponiveis"
LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL = nao_disponivel.aviso(
    NAO_DISPONIVEIS, "documentos", "a lista de linhas"
)


def limites(nao_disponiveis: Sequence[str]) -> list[str]:
    """Os limites das demonstrações: só o aviso, quando algum documento ficou de fora."""
    return [LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL] if nao_disponiveis else []


@dataclass(frozen=True)
class DemonstracoesServidas:
    """O que sai de uma empresa: o corpo, as fontes usadas (para a atribuição) e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def _simples(nome: str, valor: object) -> object:
    """O valor da base num tipo que vira JSON: data em ISO, número do NumPy em número, vazio em None."""
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    if nome in DATAS:
        return pd.Timestamp(valor).date().isoformat()  # type: ignore[arg-type]
    if nome == "versao":
        return int(valor)  # type: ignore[call-overload]
    if nome == "valor":
        return float(valor)  # type: ignore[arg-type]
    return str(valor)


class LeitorDeDemonstracoes:
    """Lê as demonstrações de uma empresa de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido, linhas_maximas: int) -> None:
        self.porta = porta
        self.permitido = permitido
        self.linhas_maximas = linhas_maximas

    def _documentos_pedidos(self) -> dict[str, list[str]]:
        """Os campos que o portão libera de cada documento (DFP, ITR)."""
        return {
            documento: [nome for nome in CAMPOS if self.permitido(fonte, nome, False)]
            for documento, fonte in FONTES_DOS_DOCUMENTOS.items()
        }

    def _linha(self, linha: pd.Series) -> tuple[dict, str] | None:
        fonte = FONTES_DOS_DOCUMENTOS.get(str(linha["documento"]))
        if fonte is None:
            return None  # documento que não é DFP nem ITR não tem fonte nem direito
        publico_em = pd.Timestamp(linha[PUBLICADO_EM]).date()
        servida = {
            nome: campo(_simples(nome, linha[nome]), fonte=fonte, publico_em=publico_em, visto_em=None)
            for nome in CAMPOS
            if self.permitido(fonte, nome, False)
        }  # fmt: skip
        return (servida, fonte) if servida else None

    def demonstracoes(
        self, cnpj: str, como_era_em: date, fim: date | None = None
    ) -> DemonstracoesServidas | None:
        """As contas da empresa como eram em `como_era_em` (só o período que termina em `fim`, se dado),
        só com o que o portão libera; None se nada sai."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        nao_disponiveis = nao_disponivel.nao_disponiveis(self._documentos_pedidos())
        if len(nao_disponiveis) == len(FONTES_DOS_DOCUMENTOS):
            return None  # nenhum documento liberado: nada a consultar
        filtros: dict[str, object] = {"cnpj": cnpj_.formatar(normal)}
        if fim is not None:
            filtros["fim"] = pd.Timestamp(fim)
        tabela = self.porta.ler(
            TABELA,
            como_era_em=como_era_em,
            filtros=filtros,
            colunas=[*CAMPOS, PUBLICADO_EM],
        ).sort_values(list(ORDEM), ascending=list(CRESCENTE), na_position="first")
        servidas = (s for _i, linha in tabela.iterrows() if (s := self._linha(linha)))
        # uma a mais que o limite basta para dizer se cortou: o resto da empresa nem vira campo
        cortadas = list(islice(servidas, self.linhas_maximas + 1))
        cortada = len(cortadas) > self.linhas_maximas
        cortadas = cortadas[: self.linhas_maximas]
        if not cortadas:
            return None
        corpo = {
            "cnpj": normal,
            "como_era_em": como_era_em.isoformat(),
            "linhas": [servida for servida, _fonte in cortadas],
            "cortada": cortada,
            NAO_DISPONIVEIS: nao_disponiveis,
            "limites": limites(nao_disponiveis),
        }
        return DemonstracoesServidas(
            corpo, {fonte for _servida, fonte in cortadas}, len(cortadas)
        )
