"""A fachada de análise do TickerLab Research (PRD v2, seções 4.1 e 9.4): um ponto único que
calcula as métricas de um ativo com os parâmetros resolvidos e diz **de onde cada número veio**.

Não há fórmula nova aqui: cada métrica chama a função que o site já usa (`indicadores`,
`metricas`, `correlacao`). O que muda é o pacote que volta:

- **proveniência:** ticker, fonte dos dados (Yahoo, histórico guardado ou exemplo), primeiro e
  último pregão, quantidade de pregões, moeda, política de ajuste e uma assinatura dos dados;
- **parâmetros:** os valores efetivos (com a origem de cada um, vinda de `src/presets.py`) e a
  assinatura do conjunto;
- **versão da fórmula** de cada métrica (`VERSOES_DAS_FORMULAS`): se um cálculo mudar de
  propósito, a versão sobe e os resultados antigos continuam identificáveis;
- **"indisponível com motivo"** em vez de um número inventado: período curto para a janela, CDI
  não informado, índice de referência ausente.

O `id_da_execucao` junta dados, parâmetros e versões: mesma entrada, mesmo id (PRD 18.1).
"""

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from src import correlacao, metricas
from src import indicadores as ind
from src.comparacao import alinhar_fechamentos
from src.moedas import moeda_do_ticker
from src.presets import Resolucao, resolver

FUSO = ZoneInfo("America/Sao_Paulo")
VERSAO_DA_FACHADA = "1"
# sobe a versão de uma métrica quando o cálculo dela mudar (os testes "golden" cobram isso)
VERSOES_DAS_FORMULAS: dict[str, str] = {
    "retorno_total": "1",
    "retorno_anualizado": "2",  # 2: vazio com menos de ~1 ano (padrão GIPS)
    "volatilidade_anual": "1",
    "volatilidade_recente": "1",
    "maior_queda": "1",
    "sharpe": "1",
    "sortino": "1",
    "var": "1",
    "cvar": "1",
    "dias_de_alta": "1",
    "beta": "1",
    "tracking_error": "1",
    "information_ratio": "1",
    "correlacao_recente": "1",
    "media_rapida": "1",
    "media_lenta": "1",
    "rsi": "1",
    "macd": "1",
    "macd_sinal": "1",
    "bollinger_percentual_b": "1",
    "atr": "1",
    "adx": "1",
    "volume_relativo": "1",
}
FONTES = {
    None: "Yahoo Finance",
    "exemplo": "dados de exemplo guardados no projeto",
    "cache_antigo": "histórico guardado (o Yahoo não respondeu)",
}
POLITICA_DE_AJUSTE = (
    "fechamento ajustado por dividendos e desdobramentos (Yahoo Finance)"
)


@dataclass(frozen=True)
class Metrica:
    chave: str
    nome: str
    valor: float | None  # None: indisponível (veja `motivo`)
    unidade: str  # "fração" (0,12 = 12%), "número", "preço", "pontos"
    versao_da_formula: str
    parametros: dict = field(default_factory=dict)  # só os que esta métrica usou
    motivo: str = ""

    @property
    def disponivel(self) -> bool:
        return self.valor is not None


@dataclass(frozen=True)
class Proveniencia:
    ticker: str
    fonte: str
    inicio: pd.Timestamp
    fim: pd.Timestamp
    pregoes: int
    moeda: str
    ajuste: str
    assinatura_dos_dados: str
    assinatura_dos_parametros: str
    calculado_em: datetime
    versao_da_fachada: str = VERSAO_DA_FACHADA


@dataclass(frozen=True)
class Analise:
    proveniencia: Proveniencia
    metricas: dict[str, Metrica]
    resolucao: Resolucao

    def __getitem__(self, chave: str) -> Metrica:
        return self.metricas[chave]

    @property
    def id_da_execucao(self) -> str:
        """Mesmos dados + mesmos parâmetros + mesmas fórmulas = mesmo id (não depende da hora)."""
        p = self.proveniencia
        partes = [
            p.ticker,
            p.assinatura_dos_dados,
            p.assinatura_dos_parametros,
            p.versao_da_fachada,
            *(f"{k}={v}" for k, v in sorted(VERSOES_DAS_FORMULAS.items())),
        ]
        return hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()[:16]


def assinatura_da_serie(serie: pd.Series) -> str:
    """Resumo (hash) das datas e valores: muda se qualquer preço ou dia mudar."""
    datas = (
        serie.index.asi8.tobytes() if isinstance(serie.index, pd.DatetimeIndex) else b""
    )
    valores = np.ascontiguousarray(serie.to_numpy(dtype="float64")).tobytes()
    return hashlib.sha256(datas + valores).hexdigest()[:16]


def _numero(valor: object) -> float | None:
    """Um float finito, ou None (NaN e infinito viram "indisponível", nunca zero)."""
    try:
        valor = float(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return valor if math.isfinite(valor) else None


def _ultimo(serie: pd.Series) -> float | None:
    serie = serie.dropna()
    return _numero(serie.iloc[-1]) if len(serie) else None


class _Montador:
    """Junta as métricas, transformando ausência de dado em "indisponível com motivo"."""

    def __init__(self, pregoes: int) -> None:
        self.pregoes = pregoes
        self.barras = pregoes  # na técnica semanal, quantas semanas há
        self.unidade_das_barras = "pregões"
        self.metricas: dict[str, Metrica] = {}

    def add(
        self,
        chave: str,
        nome: str,
        valor: object,
        unidade: str,
        parametros: dict | None = None,
        motivo: str = "",
    ) -> None:
        numero = None if motivo else _numero(valor)
        if numero is None and not motivo:
            motivo = "Não há dados suficientes para calcular."
        self.metricas[chave] = Metrica(
            chave,
            nome,
            numero,
            unidade,
            VERSOES_DAS_FORMULAS[chave],
            parametros or {},
            motivo,
        )

    def janela_curta(self, janela: int) -> str:
        if self.barras <= janela:
            return (
                f"O período tem {self.barras} {self.unidade_das_barras} e a janela pede {janela}: "
                "escolha um período maior ou uma janela menor."
            )
        return ""

    def usar_barras(self, barras: int, unidade: str) -> None:
        """A partir daqui, as janelas contam em `unidade` (semanas, na técnica semanal)."""
        self.barras, self.unidade_das_barras = barras, unidade


def _retorno_e_risco(
    m: _Montador,
    r: Resolucao,
    fechamento: pd.Series,
    retorno: pd.Series,
    taxa_cdi_anual: float | None,
) -> None:
    """Retorno, volatilidade, quedas, Sharpe, Sortino, VaR e dias de alta."""
    # taxa livre de risco: zero, ou o CDI informado (sem CDI, Sharpe e Sortino ficam indisponíveis)
    modo_da_taxa = r["quant.taxa_livre_de_risco"]
    taxa = 0.0 if modo_da_taxa == "zero" else taxa_cdi_anual
    sem_taxa = (
        "" if taxa is not None else "O CDI não foi informado para descontar do retorno."
    )
    p_taxa = {"quant.taxa_livre_de_risco": modo_da_taxa}

    # --- retorno e risco (as mesmas funções da Visão geral e do relatório) --------------------
    m.add(
        "retorno_total",
        "Retorno total",
        ind.calcular_retorno_acumulado(retorno).iloc[-1],
        "fração",
    )
    anualizado = ind.retorno_anualizado_para_mostrar(retorno)
    m.add(
        "retorno_anualizado",
        "Retorno anualizado",
        anualizado,
        "fração",
        motivo=ind.MOTIVO_SEM_ANUALIZAR if np.isnan(anualizado) else "",
    )
    m.add(
        "volatilidade_anual",
        "Volatilidade anual (período todo)",
        ind.calcular_volatilidade_anual(retorno),
        "fração",
    )
    janela_vol = int(r["quant.janela_volatilidade"])
    curta = m.janela_curta(janela_vol)
    m.add(
        "volatilidade_recente",
        "Volatilidade recente",
        None
        if curta
        else _ultimo(ind.calcular_volatilidade_movel(retorno, janela_vol)),
        "fração",
        {"quant.janela_volatilidade": janela_vol},
        curta,
    )
    m.add(
        "maior_queda", "Maior queda", ind.calcular_drawdown(fechamento).min(), "fração"
    )
    m.add(
        "sharpe", "Índice de Sharpe",
        None if sem_taxa else ind.calcular_indice_sharpe(retorno, taxa), "número", p_taxa, sem_taxa,
    )  # fmt: skip
    m.add(
        "sortino", "Índice de Sortino",
        None if sem_taxa else metricas.calcular_sortino(retorno, taxa), "número", p_taxa, sem_taxa,
    )  # fmt: skip
    confianca = int(r["quant.var_confianca"])
    m.add(
        "var",
        f"Perda de um dia ruim (VaR {confianca}%)",
        ind.calcular_var_historico(retorno, confianca / 100),
        "fração",
        {"quant.var_confianca": confianca},
    )
    m.add(
        "cvar",
        f"Perda média nos piores dias (CVaR {confianca}%)",
        ind.calcular_cvar_historico(retorno, confianca / 100),
        "fração",
        {"quant.var_confianca": confianca},
    )
    m.add(
        "dias_de_alta",
        "Dias de alta",
        ind.calcular_percentual_dias_positivos(retorno),
        "fração",
    )


def _dependencia_do_indice(
    m: _Montador, r: Resolucao, fechamento: pd.Series, benchmark: pd.Series | None
) -> None:
    """Beta e correlação recente contra o índice de referência escolhido."""
    # --- dependência do índice de referência ---------------------------------------------------
    indice = r["quant.benchmark"]
    janela_corr = int(r["quant.janela_correlacao"])
    p_indice = {"quant.benchmark": indice}
    if benchmark is None or benchmark.dropna().empty:
        motivo = f"O índice de referência ({indice}) não foi carregado."
        m.add("beta", "Beta", None, "número", p_indice, motivo)
        m.add("tracking_error", "Tracking error", None, "fração", p_indice, motivo)
        m.add(
            "information_ratio", "Information Ratio", None, "número", p_indice, motivo
        )
        m.add("correlacao_recente", "Correlação recente", None, "número",
              {**p_indice, "quant.janela_correlacao": janela_corr}, motivo)  # fmt: skip
    else:
        # como a página Correlação e beta: só os dias em que os dois negociaram, e só depois
        # os retornos (feriados diferentes não viram retornos de dois dias)
        alinhado, _ = alinhar_fechamentos({"ativo": fechamento, "indice": benchmark})
        retornos = correlacao.calcular_retornos(alinhado)
        try:
            beta = correlacao.calcular_beta(retornos["ativo"], retornos["indice"]).beta
            motivo_beta = ""
        except ValueError as erro:
            beta, motivo_beta = None, str(erro)
        m.add("beta", "Beta", beta, "número", p_indice, motivo_beta)
        m.add(
            "tracking_error", "Tracking error",
            ind.calcular_tracking_error(retornos["ativo"], retornos["indice"]), "fração", p_indice,
        )  # fmt: skip
        m.add(
            "information_ratio", "Information Ratio",
            ind.calcular_information_ratio(retornos["ativo"], retornos["indice"]), "número",
            p_indice,
        )  # fmt: skip
        comuns = len(retornos)
        curta = (
            f"Há {comuns} dias em comum com o índice e a janela pede {janela_corr}."
            if comuns < janela_corr
            else ""
        )
        m.add(
            "correlacao_recente",
            "Correlação recente",
            None
            if curta
            else _ultimo(
                correlacao.calcular_correlacao_movel(
                    retornos["ativo"], retornos["indice"], janela_corr
                )
            ),
            "número",
            {**p_indice, "quant.janela_correlacao": janela_corr},
            curta,
        )


def _medias_e_rsi(m: _Montador, r: Resolucao, fechamento: pd.Series) -> None:
    """Médias rápida e lenta (simples ou exponencial) e RSI."""
    # --- técnica (as mesmas funções das estratégias) -------------------------------------------
    tipo = r["tecnica.tipo_de_media"]
    media = (
        ind.calcular_media_movel
        if tipo == "simples"
        else ind.calcular_media_movel_exponencial
    )
    for chave, nome, parametro in (
        ("media_rapida", "Média rápida", "tecnica.media_rapida"),
        ("media_lenta", "Média lenta", "tecnica.media_lenta"),
    ):
        janela = int(r[parametro])
        curta = m.janela_curta(janela)
        m.add(
            chave, f"{nome} ({janela}, {tipo})",
            None if curta else _ultimo(media(fechamento, janela)), "preço",
            {parametro: janela, "tecnica.tipo_de_media": tipo}, curta,
        )  # fmt: skip
    periodo_rsi = int(r["tecnica.rsi_periodo"])
    curta = m.janela_curta(periodo_rsi)
    m.add(
        "rsi", f"RSI ({periodo_rsi})",
        None if curta else _ultimo(ind.calcular_rsi(fechamento, periodo_rsi)), "pontos",
        {"tecnica.rsi_periodo": periodo_rsi,
         "tecnica.rsi_inferior": r["tecnica.rsi_inferior"],
         "tecnica.rsi_superior": r["tecnica.rsi_superior"]},
        curta,
    )  # fmt: skip


def _macd_bollinger_e_atr(
    m: _Montador, r: Resolucao, dados: pd.DataFrame, fechamento: pd.Series
) -> None:
    """MACD e linha de sinal, %b de Bollinger e ATR."""
    rapida, lenta, sinal = (
        int(r["tecnica.macd_rapida"]), int(r["tecnica.macd_lenta"]), int(r["tecnica.macd_sinal"]),
    )  # fmt: skip
    p_macd = {
        "tecnica.macd_rapida": rapida,
        "tecnica.macd_lenta": lenta,
        "tecnica.macd_sinal": sinal,
    }
    curta = m.janela_curta(lenta + sinal)
    ultimo_macd = ultimo_sinal = None
    if not curta:
        macd = ind.calcular_macd(fechamento, rapida, lenta, sinal)
        ultimo_macd, ultimo_sinal = _ultimo(macd["macd"]), _ultimo(macd["sinal"])
    m.add("macd", "MACD", ultimo_macd, "preço", p_macd, curta)
    m.add("macd_sinal", "MACD: linha de sinal", ultimo_sinal, "preço", p_macd, curta)
    periodo_bb, desvios = (
        int(r["tecnica.bollinger_periodo"]),
        float(r["tecnica.bollinger_desvios"]),
    )
    curta = m.janela_curta(periodo_bb)
    m.add(
        "bollinger_percentual_b", "Bollinger: %b",
        None if curta else _ultimo(
            ind.calcular_bandas_de_bollinger(fechamento, periodo_bb, desvios)["percentual_b"]
        ),
        "fração",
        {"tecnica.bollinger_periodo": periodo_bb, "tecnica.bollinger_desvios": desvios},
        curta,
    )  # fmt: skip
    periodo_atr = int(r["tecnica.atr_periodo"])
    tem_ohlc = {"High", "Low"} <= set(dados.columns)
    motivo_atr = (
        "Os dados não têm máxima e mínima do dia."
        if not tem_ohlc
        else m.janela_curta(periodo_atr)
    )
    m.add(
        "atr", f"ATR ({periodo_atr})",
        None if motivo_atr else _ultimo(ind.calcular_atr(dados, periodo_atr)), "preço",
        {"tecnica.atr_periodo": periodo_atr}, motivo_atr,
    )  # fmt: skip


def _adx_e_volume(m: _Montador, r: Resolucao, dados: pd.DataFrame) -> None:
    """ADX (força da tendência) e volume relativo (volume de hoje contra o normal)."""
    periodo_adx, nivel = int(r["tecnica.adx_periodo"]), int(r["tecnica.adx_tendencia"])
    motivo_adx = (
        "Os dados não têm máxima e mínima do dia."
        if not {"High", "Low"} <= set(dados.columns)
        else m.janela_curta(2 * periodo_adx)
    )
    m.add(
        "adx", f"ADX ({periodo_adx})",
        None if motivo_adx else _ultimo(ind.calcular_adx(dados, periodo_adx)["adx"]), "pontos",
        {"tecnica.adx_periodo": periodo_adx, "tecnica.adx_tendencia": nivel}, motivo_adx,
    )  # fmt: skip
    janela_volume = int(r["tecnica.volume_janela"])
    sem_volume = (
        "Volume" not in dados.columns or not (dados["Volume"].fillna(0) > 0).any()
    )
    motivo_volume = (
        "Os dados não têm volume (índices e câmbio costumam não ter)."
        if sem_volume
        else m.janela_curta(janela_volume)
    )
    m.add(
        "volume_relativo", "Volume relativo",
        None if motivo_volume else _ultimo(ind.calcular_volume_relativo(dados, janela_volume)),
        "número", {"tecnica.volume_janela": janela_volume}, motivo_volume,
    )  # fmt: skip


def analisar_ativo(
    ticker: str,
    dados: pd.DataFrame,
    resolucao: Resolucao | None = None,
    taxa_cdi_anual: float | None = None,
    benchmark: pd.Series | None = None,
    agora: datetime | None = None,
) -> Analise:
    """As métricas do ativo com os parâmetros efetivos (padrão do sistema se `resolucao` faltar).

    `dados`: o DataFrame de `src.dados` (Open, High, Low, Close; `attrs` com a origem).
    `taxa_cdi_anual`: só é usada se o parâmetro `quant.taxa_livre_de_risco` for "cdi".
    `benchmark`: fechamentos do índice de referência (para beta e correlação).
    """
    r = resolucao or resolver([])
    fechamento = dados["Close"].dropna()
    if len(fechamento) < 2:
        raise ValueError(
            "São necessários pelo menos dois pregões para analisar o ativo."
        )
    retorno = ind.calcular_retorno_diario(fechamento)
    pregoes = len(fechamento)
    m = _Montador(pregoes)
    _retorno_e_risco(m, r, fechamento, retorno, taxa_cdi_anual)
    _dependencia_do_indice(m, r, fechamento, benchmark)
    # técnica: no diário ou no semanal (barras da semana; as janelas passam a contar semanas)
    tecnicos = (
        ind.para_semanal(dados) if r["tecnica.periodicidade"] == "semanal" else dados
    )
    fechamento_tecnico = tecnicos["Close"].dropna()
    if tecnicos is not dados:
        m.usar_barras(len(fechamento_tecnico), "semanas")
    _medias_e_rsi(m, r, fechamento_tecnico)
    _macd_bollinger_e_atr(m, r, tecnicos, fechamento_tecnico)
    _adx_e_volume(m, r, tecnicos)

    proveniencia = Proveniencia(
        ticker=ticker,
        fonte=FONTES.get(dados.attrs.get("origem"), str(dados.attrs.get("origem"))),
        inicio=fechamento.index[0],
        fim=fechamento.index[-1],
        pregoes=pregoes,
        moeda=dados.attrs.get("moeda") or moeda_do_ticker(ticker),
        ajuste=POLITICA_DE_AJUSTE,
        assinatura_dos_dados=assinatura_da_serie(fechamento),
        assinatura_dos_parametros=r.assinatura,
        calculado_em=agora or datetime.now(FUSO),
    )
    return Analise(proveniencia, m.metricas, r)
