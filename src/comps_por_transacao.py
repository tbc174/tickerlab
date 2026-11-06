"""Comps por transação: os múltiplos pagos nas operações de M&A do setor, como eram num dia (protótipo A,
M&A, do dossiê da plataforma; B-25).

Para uma empresa e uma data, os precedentes são as operações cuja alvo é do mesmo grupo de setor
(`src/setores.py`, pelo setor que a alvo informa à CVM) e cujo múltiplo já era público na data. De
cada múltiplo (EV/EBITDA, EV/receita, EV/EBIT) saem a mediana e os quartis, com o rastro de cada
precedente e o do resumo.

**Sem olhar o futuro**, em dois passos:
- `precedentes_como_eram_em` lê só os documentos do IPE públicos até o dia (`publico_em ≤ dia`, a regra
  "como era em D" da porta) antes de juntar as operações e ler o valor: um documento que saiu depois
  não muda nem a alvo, nem o valor, nem o anúncio;
- `comps_por_transacao` só usa a linha a partir de `disponivel_em` = o dia mais tarde entre o anúncio e
  o documento que trouxe o valor (`valor_publico_em`). Os números da alvo já são só de DFP e ITR
  entregues antes do anúncio (`base/ma_multiplos.py`).

É a régua do que outros pagaram, não um preço: nada aqui diz quanto a empresa vale nem se é caro ou
barato. Tipos simples, sem Streamlit (a API e o app novo leem o mesmo `como_dict`).
"""

import math
import statistics
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd

from base import ma_multiplos as mm
from base import ma_operacoes as mo
from src.rastro import DocumentoUsado, Rastro, datas_em_texto
from src.setores import NOMES, SEM_GRUPO, grupo_do_setor

VERSAO_DO_CALCULO = "comps por transação 1"  # sobe quando uma fórmula abaixo mudar
FONTE_DO_VALOR = "cvm-ipe"  # o valor da operação, lido no documento do IPE
FONTE_DOS_NUMEROS = "cvm"  # receita, EBITDA e EBIT da alvo, dos DFP e ITR
MINIMO_DE_PRECEDENTES = 3  # com menos, mediana e quartis não dizem nada

# múltiplo → (nome para a tela, fórmula do número de cada precedente)
MULTIPLOS: dict[str, tuple[str, str]] = {
    "ev_ebitda": (
        "EV/EBITDA",
        (
            "valor da empresa pago ÷ (EBIT + depreciação e amortização) dos 12 meses da alvo "
            "entregues à CVM antes do anúncio"
        ),
    ),
    "ev_receita": (
        "EV/receita",
        "valor da empresa pago ÷ receita dos 12 meses da alvo entregue à CVM antes do anúncio",
    ),
    "ev_ebit": (
        "EV/EBIT",
        "valor da empresa pago ÷ EBIT dos 12 meses da alvo entregues à CVM antes do anúncio",
    ),
}
FORMULA_DO_RESUMO = (
    "mediana e quartis (interpolação linear, `statistics.quantiles` inclusivo) dos múltiplos dos "
    "precedentes do grupo de setor públicos até a data"
)
SEM_SETOR = "a empresa não tem setor reconhecido na CVM"
POUCOS = "menos de {minimo} precedentes do setor com este múltiplo até a data ({n})"
LIMITES = (
    (
        "Só entram operações com alvo de capital aberto que entregou DFP ou ITR antes do anúncio e com "
        "o valor da empresa ou o preço por ação lido em reais; a maior parte das operações do Brasil "
        "fica de fora, e os precedentes não são uma amostra do mercado."
    ),
    (
        "O valor de uma participação não entra (a fração comprada não é lida com segurança), nem "
        "prêmio de controle, sinergias, ajustes de preço ou dívida assumida fora do balanço."
    ),
    (
        "Os múltiplos são de datas e ciclos diferentes: a mediana mistura juros, câmbio e setores "
        "de momentos distintos. É uma régua do que foi pago, não um preço nem uma recomendação."
    ),
)


@dataclass(frozen=True)
class Precedente:
    """Uma operação do setor e o múltiplo pago, com o rastro do número."""

    operacao: str
    alvo: str
    alvo_cnpj: str
    anuncio: date
    disponivel_em: (
        date  # o dia em que o múltiplo ficou público (anúncio ou documento do valor)
    )
    multiplo: float
    rastro: Rastro


@dataclass(frozen=True)
class ResumoDoMultiplo:
    """Mediana e quartis de um múltiplo entre os precedentes (None com poucos precedentes)."""

    chave: str
    nome: str
    precedentes: tuple[Precedente, ...]
    mediana: float | None
    primeiro_quartil: float | None
    terceiro_quartil: float | None
    rastro: Rastro
    motivo: str = ""  # por que não há mediana e quartis

    @property
    def quantos(self) -> int:
        return len(self.precedentes)


@dataclass(frozen=True)
class CompsPorTransacao:
    """Os comps de uma empresa numa data (`como_dict` para a API)."""

    cnpj: str
    grupo: str  # o grupo de setor (`src/setores.py`), ou `SEM_GRUPO`
    nome_do_grupo: str
    como_era_em: date
    multiplos: tuple[ResumoDoMultiplo, ...]
    motivo: str = ""  # por que não há comps (sem setor)
    limites: tuple[str, ...] = LIMITES

    def do_multiplo(self, chave: str) -> ResumoDoMultiplo:
        return next(m for m in self.multiplos if m.chave == chave)

    def como_dict(self) -> dict:
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def precedentes_como_eram_em(
    documentos: list[mo.DocumentoLido],
    emissoras: Mapping[str, mm.Emissora],
    contas: pd.DataFrame,
    documentos_da_cvm: pd.DataFrame,
    dia: date,
) -> pd.DataFrame:
    """A tabela de `base.ma_multiplos.multiplos` só com os documentos do IPE públicos até `dia`."""
    ate_o_dia = [d for d in documentos if d.publico_em <= dia]
    return mm.multiplos(ate_o_dia, dict(emissoras), contas, documentos_da_cvm)


def _dia(valor: object) -> date | None:
    """A data de uma célula da tabela (vazia → None; `Timestamp` do pandas → `date`)."""
    if valor is None or (not isinstance(valor, date) and pd.isna(valor)):
        return None
    return valor if type(valor) is date else pd.Timestamp(valor).date()


def disponivel_em(linha: Mapping) -> date:
    """O dia em que o múltiplo da operação ficou público: o mais tarde entre o anúncio e o documento
    que trouxe o valor."""
    anuncio = _dia(linha["anuncio"])
    assert anuncio is not None
    valor_em = _dia(linha.get("valor_publico_em"))
    return max(anuncio, valor_em) if valor_em else anuncio


def _rastro_do_precedente(linha: Mapping, chave: str) -> Rastro:
    documentos = [
        DocumentoUsado(
            f"documento do IPE da CVM, protocolo {linha['valor_protocolo']} (o valor pago)",
            _dia(linha.get("valor_publico_em")),
        ),
        DocumentoUsado(
            f"DFP e ITR da alvo ({linha['base_12m']}), entregues à CVM antes do anúncio",
            _dia(linha.get("entregue_ate")),
        ),
    ]
    return Rastro.dos_documentos(
        MULTIPLOS[chave][1],
        VERSAO_DO_CALCULO,
        FONTE_DO_VALOR,
        documentos,
        (FONTE_DOS_NUMEROS,),
    )


def _precedentes(
    tabela: pd.DataFrame, grupo: str, setor_de: Mapping[str, str], chave: str, dia: date
) -> tuple[Precedente, ...]:
    precedentes = []
    for linha in tabela.to_dict("records"):
        multiplo = linha.get(chave)
        cnpj = linha.get("alvo_cnpj")
        if multiplo is None or pd.isna(multiplo) or not math.isfinite(multiplo):
            continue
        if not cnpj or grupo_do_setor(setor_de.get(cnpj, "")) != grupo:
            continue
        quando = disponivel_em(linha)
        if quando > dia:
            continue
        precedentes.append(
            Precedente(
                operacao=str(linha["operacao"]),
                alvo=str(linha["alvo"]),
                alvo_cnpj=str(cnpj),
                anuncio=_dia(linha["anuncio"]) or quando,
                disponivel_em=quando,
                multiplo=float(multiplo),
                rastro=_rastro_do_precedente(linha, chave),
            )
        )
    return tuple(sorted(precedentes, key=lambda p: (p.disponivel_em, p.operacao)))


def resumir(
    chave: str, precedentes: tuple[Precedente, ...], dia: date
) -> ResumoDoMultiplo:
    """Mediana e quartis dos múltiplos, com o rastro de todos os documentos dos precedentes."""
    documentos = [d for p in precedentes for d in p.rastro.documentos]
    rastro = Rastro(
        FORMULA_DO_RESUMO,
        VERSAO_DO_CALCULO,
        FONTE_DO_VALOR,
        max((p.disponivel_em for p in precedentes), default=dia),
        tuple(documentos),
        (FONTE_DOS_NUMEROS,),
    )
    nome = MULTIPLOS[chave][0]
    if len(precedentes) < MINIMO_DE_PRECEDENTES:
        motivo = POUCOS.format(minimo=MINIMO_DE_PRECEDENTES, n=len(precedentes))
        return ResumoDoMultiplo(
            chave, nome, precedentes, None, None, None, rastro, motivo
        )
    valores = sorted(p.multiplo for p in precedentes)
    q1, mediana, q3 = statistics.quantiles(valores, n=4, method="inclusive")
    return ResumoDoMultiplo(chave, nome, precedentes, mediana, q1, q3, rastro)


def comps_por_transacao(
    tabela: pd.DataFrame, setor_de: Mapping[str, str], cnpj: str, dia: date
) -> CompsPorTransacao:
    """Os comps da empresa `cnpj` em `dia`.

    `tabela`: a de `precedentes_como_eram_em` (ou de `base.ma_multiplos.multiplos`); `setor_de`: CNPJ →
    setor informado à CVM, da empresa e das alvos."""
    grupo = grupo_do_setor(setor_de.get(cnpj, ""))
    nome = NOMES.get(grupo, grupo)
    if grupo == SEM_GRUPO:
        return CompsPorTransacao(cnpj, grupo, nome, dia, (), SEM_SETOR)
    resumos = tuple(
        resumir(chave, _precedentes(tabela, grupo, setor_de, chave, dia), dia)
        for chave in MULTIPLOS
    )
    return CompsPorTransacao(cnpj, grupo, nome, dia, resumos)
