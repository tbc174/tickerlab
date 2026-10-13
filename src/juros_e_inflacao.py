"""Juros e inflação: Selic, CDI, IPCA, juro real e o que o mercado espera (Focus).

Os números vêm do acervo de séries do Banco Central (Radar, ADR 0024), lidos "como estavam" no
dia pedido: cada um sai com a data a que se refere, a data em que foi divulgado e a fonte. O CDI
não está no acervo: vem da consulta ao Banco Central que o backtest já usa (`src/cdi.py`).

Tudo aqui é cálculo e texto (sem Streamlit), em tipos simples: a tela só mostra, e uma rota da
API pode devolver o mesmo painel (ADR 0044 e 0048).
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd
import sqlalchemy as sa

from src.banco import series as acervo

SELIC_META = "bcb-sgs-432"
IPCA = "bcb-sgs-433"
DOLAR = "bcb-sgs-1"
FOCUS_IPCA = "bcb-focus-ipca"
FOCUS_SELIC = "bcb-focus-selic"
SERIES_DO_PAINEL = (SELIC_META, IPCA, DOLAR, FOCUS_IPCA, FOCUS_SELIC)

NOME_SELIC = "Meta da Selic"
NOME_CDI_12M = "CDI em 12 meses"
NOME_IPCA_MES = "IPCA no mês"
NOME_IPCA_12M = "IPCA em 12 meses"
NOME_JURO_REAL = "Juro real em 12 meses"
NOME_DOLAR = "Dólar comercial"
NOMES_DAS_SERIES = {
    SELIC_META: NOME_SELIC,
    IPCA: "IPCA",
    DOLAR: "dólar comercial",
    FOCUS_IPCA: "expectativa do IPCA (Focus)",
    FOCUS_SELIC: "expectativa da Selic (Focus)",
}
# o verbete do glossário que explica cada número (o "?" ao lado dele na tela)
TERMO_DO_GLOSSARIO = {
    NOME_SELIC: "Selic",
    NOME_CDI_12M: "CDI",
    NOME_IPCA_MES: "IPCA",
    NOME_IPCA_12M: "IPCA",
    NOME_JURO_REAL: "Juro real",
    NOME_DOLAR: "Câmbio e moeda",
}
FONTE_SGS = "Banco Central, SGS {}"
FONTE_FOCUS = "Banco Central, boletim Focus (mediana)"
NOTA_DO_FOCUS = "É a mediana das projeções, não uma previsão do TickerLab."

MESES_ABREVIADOS = (
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
)
MESES_NO_ANO = 12
DIAS_UTEIS_NO_ANO = 252
ANOS_DE_HISTORICO = 10
DIAS_DE_CDI = 400  # um pouco mais que um ano de dias corridos: cobre 252 dias úteis


@dataclass(frozen=True)
class SerieLida:
    valores: (
        pd.Series
    )  # índice = data de referência, como a série era conhecida no dia pedido
    divulgado_em: date | None  # quando o último valor foi divulgado (a safra)


@dataclass(frozen=True)
class Numero:
    nome: str
    valor: float | None  # None: faltou dado (o motivo está nos avisos do painel)
    unidade: str
    referencia: date | None  # o dia ou o mês a que o número se refere
    divulgado_em: date | None
    fonte: str
    referencia_mensal: bool = False  # True: o número vale para o mês inteiro (IPCA)


@dataclass(frozen=True)
class Expectativa:
    indicador: str  # "IPCA" ou "Selic"
    ano: int
    mediana: float  # % (como no boletim)
    pesquisa: date | None


@dataclass(frozen=True)
class PontoMensal:
    mes: date  # o primeiro dia do mês
    selic_meta: float | None  # % ao ano no fim do mês
    ipca_12_meses: float | None  # %


@dataclass(frozen=True)
class PainelDeJuros:
    numeros: tuple[Numero, ...]
    expectativas: tuple[Expectativa, ...]
    historico: tuple[PontoMensal, ...]
    avisos: tuple[str, ...]


# --- leitura do acervo ---------------------------------------------------------------------


def _divulgacao_do_ultimo(
    conexao: sa.Connection, codigo: str, referencia: date, dia: date
) -> date | None:
    versoes = [d for d, _ in acervo.safras(conexao, codigo, referencia) if d <= dia]
    return versoes[-1] if versoes else None


def ler_series(conexao: sa.Connection, dia: date) -> dict[str, SerieLida]:
    """As séries do painel como eram conhecidas no fim de `dia`; as que não têm dado ficam de fora."""
    lidas = {}
    for codigo in SERIES_DO_PAINEL:
        valores = acervo.como_estava_em(conexao, codigo, dia)
        if valores.empty:
            continue
        ultima = valores.index[-1].date()
        lidas[codigo] = SerieLida(
            valores, _divulgacao_do_ultimo(conexao, codigo, ultima, dia)
        )
    return lidas


# --- contas --------------------------------------------------------------------------------


def _acumulado_em_12_meses(ipca_mensal: pd.Series) -> pd.Series:
    """IPCA de 12 meses em cada mês (%), compondo os meses: (1,005 × 1,004 × ...) − 1.

    Só há valor onde os 12 meses anteriores existem e são seguidos (um mês faltando dá vazio).
    """
    mensal = ipca_mensal.asfreq("MS")
    fatores = 1 + mensal / 100
    return (fatores.rolling(MESES_NO_ANO).apply(pd.Series.prod, raw=False) - 1) * 100


def _cdi_em_12_meses(cdi_diario: pd.Series | None) -> tuple[float | None, date | None]:
    if cdi_diario is None or len(cdi_diario) < DIAS_UTEIS_NO_ANO:
        return None, None
    ultimos = cdi_diario.iloc[-DIAS_UTEIS_NO_ANO:]
    return float(((1 + ultimos).prod() - 1) * 100), ultimos.index[-1].date()


def _ultimo(lida: SerieLida | None) -> tuple[float | None, date | None]:
    if lida is None:
        return None, None
    return float(lida.valores.iloc[-1]), lida.valores.index[-1].date()


def _numero_da_serie(
    lidas: dict[str, SerieLida],
    codigo: str,
    nome: str,
    unidade: str,
    referencia_mensal: bool = False,
) -> Numero:
    lida = lidas.get(codigo)
    valor, referencia = _ultimo(lida)
    return Numero(
        nome,
        valor,
        unidade,
        referencia,
        lida.divulgado_em if lida else None,
        FONTE_SGS.format(codigo.removeprefix("bcb-sgs-")),
        referencia_mensal,
    )


def _numeros(
    lidas: dict[str, SerieLida], cdi_diario: pd.Series | None
) -> tuple[Numero, ...]:
    ipca = lidas.get(IPCA)
    ipca_12m, referencia_ipca = None, None
    if ipca is not None:
        acumulado = _acumulado_em_12_meses(ipca.valores).dropna()
        if not acumulado.empty and acumulado.index[-1] == ipca.valores.index[-1]:
            ipca_12m, referencia_ipca = (
                float(acumulado.iloc[-1]),
                acumulado.index[-1].date(),
            )
    cdi_12m, referencia_cdi = _cdi_em_12_meses(cdi_diario)
    juro_real = None
    if cdi_12m is not None and ipca_12m is not None:
        juro_real = ((1 + cdi_12m / 100) / (1 + ipca_12m / 100) - 1) * 100
    return (
        _numero_da_serie(lidas, SELIC_META, NOME_SELIC, "% ao ano"),
        Numero(NOME_CDI_12M, cdi_12m, "% em 12 meses", referencia_cdi, None,
               FONTE_SGS.format(12)),
        _numero_da_serie(lidas, IPCA, NOME_IPCA_MES, "% no mês", referencia_mensal=True),
        Numero(NOME_IPCA_12M, ipca_12m, "% em 12 meses", referencia_ipca,
               ipca.divulgado_em if ipca else None, FONTE_SGS.format(433), True),
        Numero(NOME_JURO_REAL, juro_real, "% em 12 meses (CDI descontado o IPCA)",
               referencia_cdi, None, "Conta do TickerLab com o CDI e o IPCA acima"),
        _numero_da_serie(lidas, DOLAR, NOME_DOLAR, "R$ por US$"),
    )  # fmt: skip


def _expectativas(lidas: dict[str, SerieLida], hoje: date) -> tuple[Expectativa, ...]:
    saida = []
    for codigo, indicador in ((FOCUS_IPCA, "IPCA"), (FOCUS_SELIC, "Selic")):
        lida = lidas.get(codigo)
        if lida is None:
            continue
        for ano in (hoje.year, hoje.year + 1):
            no_ano = lida.valores[lida.valores.index.year == ano]
            if not no_ano.empty:
                saida.append(
                    Expectativa(
                        indicador, ano, float(no_ano.iloc[-1]), lida.divulgado_em
                    )
                )
    return tuple(saida)


def _historico(lidas: dict[str, SerieLida], hoje: date) -> tuple[PontoMensal, ...]:
    ipca = lidas.get(IPCA)
    if ipca is None:
        return ()
    acumulado = _acumulado_em_12_meses(ipca.valores)
    inicio = pd.Timestamp(hoje.year - ANOS_DE_HISTORICO, hoje.month, 1)
    acumulado = acumulado[acumulado.index >= inicio]
    selic = lidas.get(SELIC_META)
    selic_no_mes = (
        selic.valores.resample("MS").last().reindex(acumulado.index).ffill()
        if selic is not None
        else pd.Series(index=acumulado.index, dtype=float)
    )
    return tuple(
        PontoMensal(
            mes.date(),
            None if pd.isna(selic_no_mes.get(mes)) else float(selic_no_mes[mes]),
            None if pd.isna(valor) else float(valor),
        )
        for mes, valor in acumulado.items()
    )


def _avisos(
    lidas: dict[str, SerieLida], cdi_diario: pd.Series | None
) -> tuple[str, ...]:
    avisos = [
        f"Sem dados de {nome} no acervo do TickerLab: este número fica em branco."
        for codigo, nome in NOMES_DAS_SERIES.items()
        if codigo not in lidas
    ]
    if _cdi_em_12_meses(cdi_diario)[0] is None:
        avisos.append(
            "O CDI não veio do Banco Central agora: o CDI em 12 meses e o juro real ficam em "
            "branco."
        )
    return tuple(avisos)


def montar_painel(
    lidas: dict[str, SerieLida], cdi_diario: pd.Series | None, hoje: date
) -> PainelDeJuros:
    """O painel de juros e inflação a partir das séries lidas e do CDI diário (fração ao dia)."""
    return PainelDeJuros(
        numeros=_numeros(lidas, cdi_diario),
        expectativas=_expectativas(lidas, hoje),
        historico=_historico(lidas, hoje),
        avisos=_avisos(lidas, cdi_diario),
    )


# --- textos --------------------------------------------------------------------------------


def _decimal(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def formatar_valor(numero: Numero) -> str:
    """O valor como a tela mostra: "15,00% ao ano", "0,44%", "R$ 5,40" ou "—" sem dado."""
    if numero.valor is None:
        return "—"
    if numero.unidade.startswith("R$"):
        return f"R$ {_decimal(numero.valor)}"
    if numero.unidade == "% ao ano":
        return f"{_decimal(numero.valor)}% ao ano"
    return f"{_decimal(numero.valor)}%"


def _data(dia: date, mensal: bool) -> str:
    if mensal:
        return f"{MESES_ABREVIADOS[dia.month - 1]}/{dia.year}"
    return f"{dia:%d/%m/%Y}"


def legenda(numero: Numero) -> str:
    """De onde veio o número: a referência, a divulgação (quando houver) e a fonte."""
    partes = []
    if numero.referencia is not None:
        partes.append(
            f"Referência: {_data(numero.referencia, numero.referencia_mensal)}"
        )
    if numero.divulgado_em is not None:
        partes.append(f"divulgado em {numero.divulgado_em:%d/%m/%Y}")
    partes.append(numero.fonte)
    return " · ".join(partes)
