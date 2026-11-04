"""Os dados do dia de cada série do papel, das mesmas fontes que as séries já usam.

Nenhuma fonte nova: Yahoo (os mesmos símbolos do `dados_mt5/`, baixados pelo mesmo leitor), CDI,
IPCA e PTAX do Banco Central, a curva de juros do acervo e os klines diários do Binance Vision.
O papel guarda a sua cópia em `PASTA_DOS_DADOS` (fora do Git e fora das pastas da pesquisa, que
ficam como o desenvolvimento as deixou) e não corta o holdout: os dados entram desde um aquecimento
antes do primeiro fechamento do papel, e o próprio `series` só deixa a carteira sair do caixa no
início do papel.

**O que ainda não saiu no fechamento.** O CDI de um dia sai na manhã seguinte, a curva de juros do
dia chega ao acervo no dia seguinte e o IPCA do mês sai no mês seguinte. Nesses casos o dado repete
o último valor conhecido e o nome dele vai para `estimados`, que a foto grava. O preço do próprio
fechamento nunca é estimado: sem ele, `DadoAindaNaoSaiuError` e o gravador tenta de novo mais tarde.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src import bcb
from src import cdi as modulo_cdi
from trader import dados as dados_do_trader
from trader.baixar_historico import baixar_yfinance
from trader.calendario import eh_pregao, proximo_pregao
from trader.estrategias import dados_p0_3, rodar_alavancagem
from trader.estrategias import dados_tendencia_b3 as dados_b3
from trader.estrategias import dados_cripto_brl as dados_brl
from trader.estrategias import dados_tendencia_cripto as dados_cripto
from trader.estrategias import tendencia_b3 as tb
from trader.papel.registro import PASTA_PADRAO
from trader.papel.series import EntradasDoDI1, Tabelas

PASTA_DOS_DADOS = PASTA_PADRAO / "dados"
URL_DIARIA_DA_BINANCE = (
    "https://data.binance.vision/data/spot/daily/klines/{par}/1d/{par}-1d-{dia}.zip"
)
SIMBOLOS_DO_YAHOO = {
    "BOVA11": "BOVA11.SA",
    "OURO": "GLD",
    "SP500": "^GSPC",
    "BRL": "BRL=X",
}
# Folga antes do primeiro fechamento: o maior aquecimento (360 pregões do DI1, uns 520 dias
# corridos; 365 dias mais o volume de 60 na cripto) com margem.
DIAS_ANTES_DO_PRIMEIRO_FECHAMENTO = 730


class DadoAindaNaoSaiuError(RuntimeError):
    """O preço do fechamento ainda não está na fonte: tentar de novo mais tarde."""


@dataclass(frozen=True)
class Fontes:
    """Quem baixa cada coisa (os testes trocam por dublês, sem internet)."""

    yahoo: Callable[[str], pd.DataFrame] = baixar_yfinance
    cdi: Callable[[pd.Timestamp, pd.Timestamp], pd.Series] = modulo_cdi.baixar_cdi
    sgs: Callable[[bcb.Serie, date, date], pd.Series] = bcb.baixar_sgs
    url: Callable[[str], bytes] = dados_cripto._baixar_da_internet
    pasta_da_curva: Path = dados_p0_3.PASTA_DA_CURVA


FONTES = Fontes()


def inicio_dos_dados(primeiro_fechamento: date) -> pd.Timestamp:
    return pd.Timestamp(
        primeiro_fechamento - timedelta(days=DIAS_ANTES_DO_PRIMEIRO_FECHAMENTO)
    )


# --- ajudantes -----------------------------------------------------------------------------------


def _exigir_o_fechamento(datas: pd.DatetimeIndex, fechamento: date, nome: str) -> None:
    if pd.Timestamp(fechamento) not in datas:
        raise DadoAindaNaoSaiuError(
            f"{nome} ainda não tem o fechamento de {fechamento}"
        )


def _cdi_ate(
    fontes: Fontes, inicio: pd.Timestamp, fechamento: date, estimados: set[str]
) -> pd.Series:
    """CDI diário dos dias úteis até o fechamento; pregão cujo CDI ainda não saiu repete o último."""
    fim = pd.Timestamp(fechamento)
    cdi = fontes.cdi(inicio, fim).sort_index().loc[:fim]
    ultimo = pd.Timestamp(cdi.index.max())
    faltando = [
        dia
        for dia in pd.date_range(ultimo + pd.Timedelta(days=1), fim)
        if eh_pregao(dia.date())
    ]
    if faltando:
        cdi = pd.concat(
            [cdi, pd.Series(float(cdi.iloc[-1]), index=pd.DatetimeIndex(faltando))]
        )
        estimados.add("cdi")
    return cdi


def _ultima_data(datas: pd.Series) -> date:
    return pd.Timestamp(max(pd.to_datetime(pd.Series(datas)))).date()


def _yahoo(nome: str, fontes: Fontes, pasta: Path) -> Path:
    """Baixa um símbolo como o `baixar_historico` faz (OHLC reparado) e grava a cópia do papel."""
    simbolo = SIMBOLOS_DO_YAHOO[nome]
    arquivo = dados_p0_3.ARQUIVOS_DO_MT5[nome]
    candles, _ = dados_do_trader.reparar_candles(fontes.yahoo(simbolo))
    return dados_do_trader.salvar(
        candles, arquivo.removesuffix("_D1.parquet"), "D1", pasta
    )


def _pregoes_ate_o_fim_do_mes(
    pregoes: pd.DatetimeIndex, fechamento: date
) -> pd.DatetimeIndex:
    """Os pregões dados mais os que faltam no mês do fechamento (o calendário já é conhecido)."""
    extras, dia = [], proximo_pregao(fechamento)
    while dia.month == fechamento.month and dia.year == fechamento.year:
        extras.append(pd.Timestamp(dia))
        dia = proximo_pregao(dia)
    return pregoes.union(pd.DatetimeIndex(extras))


def _ipca_ate(
    fontes: Fontes, inicio: pd.Timestamp, fechamento: date, estimados: set[str]
) -> pd.Series:
    """IPCA mensal até o mês do fechamento; mês ainda sem IPCA repete o último publicado."""
    bruto = fontes.sgs(dados_p0_3.SERIE_DO_IPCA, inicio.date(), fechamento) / 100
    ipca = bruto.copy()
    ipca.index = pd.DatetimeIndex(ipca.index).to_period("M")
    meses = pd.period_range(ipca.index.min(), pd.Period(fechamento, "M"), freq="M")
    if len(meses) > len(ipca):
        estimados.add("IPCA")
    ipca = ipca.reindex(meses).ffill()
    ipca.index = ipca.index.to_timestamp()
    return ipca


# --- P0-3 ----------------------------------------------------------------------------------------


def carregar_p0_3(
    fechamento: date,
    primeiro_fechamento: date,
    fontes: Fontes = FONTES,
    pasta: Path = PASTA_DOS_DADOS,
) -> Tabelas:
    """As quatro séries em reais, o CDI e os volumes, como o `rodar_p0_3`, até o fechamento."""
    inicio, fim, estimados = (
        inicio_dos_dados(primeiro_fechamento),
        pd.Timestamp(fechamento),
        set(),
    )
    yahoo = pasta / "yahoo"
    mt5 = {
        nome: dados_p0_3.fechamento_do_mt5(
            _yahoo(nome, fontes, yahoo), so_com_negocio=(nome == "BOVA11")
        ).loc[inicio:fim]
        for nome in dados_p0_3.ARQUIVOS_DO_MT5
    }
    _exigir_o_fechamento(pd.DatetimeIndex(mt5["BOVA11"].index), fechamento, "o BOVA11")
    curva = dados_p0_3.carregar_curva_real(fontes.pasta_da_curva).loc[:fim]
    if curva.index.max() < fim:
        estimados.add("curva")
    ipca = _ipca_ate(fontes, inicio - pd.DateOffset(months=1), fechamento, estimados)
    pregoes = pd.DatetimeIndex(mt5["BOVA11"].index)
    # A NTN-B reparte o IPCA do mês pelos pregões do mês: o calendário inteiro do mês entra, e o
    # que passa do fechamento é cortado (só a contagem de dias vem de lá, não preço).
    ntnb = dados_p0_3.ntnb_no_calendario(
        curva, ipca, _pregoes_ate_o_fim_do_mes(pregoes, fechamento)
    ).loc[:fim]
    precos = dados_p0_3.montar_precos(
        bova11=mt5["BOVA11"],
        ntnb=ntnb,
        ouro_usd=mt5["OURO"],
        sp500_usd=mt5["SP500"],
        brl=mt5["BRL"],
    )
    cdi = _cdi_ate(fontes, precos.index.min(), fechamento, estimados)
    cdi = cdi.reindex(precos.index).ffill()
    volumes = pd.Series(dados_p0_3.VOLUME_MEDIO_EM_REAIS)
    return Tabelas(precos, cdi, volumes, tuple(sorted(estimados)))


# --- DI1 -----------------------------------------------------------------------------------------


def carregar_di1(
    fechamento: date,
    primeiro_fechamento: date,
    fontes: Fontes = FONTES,
    pasta: Path = PASTA_DOS_DADOS,
) -> EntradasDoDI1:
    """O DI1 sintético sobre o calendário do BOVA11, como o `rodar_tendencia_b3`, até o fechamento."""
    inicio, fim, estimados = (
        inicio_dos_dados(primeiro_fechamento),
        pd.Timestamp(fechamento),
        set(),
    )
    barras = dados_b3.so_com_negocio_desde_o_inicio(
        dados_b3.barras_do_yahoo(_yahoo("BOVA11", fontes, pasta / "yahoo"))
    ).loc[inicio:fim]
    pregoes = pd.DatetimeIndex(barras.index)
    _exigir_o_fechamento(pregoes, fechamento, "o BOVA11")
    cdi = (
        _cdi_ate(fontes, pregoes.min(), fechamento, estimados).reindex(pregoes).ffill()
    )
    curva = rodar_alavancagem.carregar_curva(fontes.pasta_da_curva)
    curva = curva[pd.to_datetime(curva["data_base"]) <= fim]
    if _ultima_data(curva["data_base"]) < fechamento:
        estimados.add("curva")
    bova11 = tb.a_vista(
        "BOVA11",
        barras["abertura"],
        barras["fechamento"],
        barras["volume"] * barras["fechamento"],
        cdi,
    )
    return EntradasDoDI1(
        tb.di1_sintetico(curva, cdi, bova11), cdi, tuple(sorted(estimados))
    )


# --- P0-1 e P0-1b (cripto) -----------------------------------------------------------------------


def _baixar_dia(par: str, dia: date, fontes: Fontes, pasta: Path, hashes: dict) -> bool:
    nome = f"{par}-1d-{dia.isoformat()}.zip"
    destino = pasta / nome
    if destino.exists():
        return True
    try:
        conteudo = fontes.url(
            URL_DIARIA_DA_BINANCE.format(par=par, dia=dia.isoformat())
        )
    except OSError:
        return False
    # confere que é um zip de candles antes de gravar
    dados_cripto.ler_kline_zip(conteudo)
    destino.write_bytes(conteudo)
    hashes[nome] = hashlib.sha256(conteudo).hexdigest()
    return True


def atualizar_binance(
    inicio: pd.Timestamp,
    fechamento: date,
    fontes: Fontes,
    pasta: Path,
    pares: dict[str, str] = dados_cripto.PARES,
) -> None:
    """Zips mensais dos meses fechados e diários do mês corrente (e do mês cujo mensal não saiu)."""
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo_de_hashes = pasta / "sha256_diarios.json"
    hashes = (
        json.loads(arquivo_de_hashes.read_text("utf-8"))
        if arquivo_de_hashes.exists()
        else {}
    )
    mes_do_fechamento = pd.Period(fechamento, "M")
    for par in pares.values():
        for mes in pd.period_range(pd.Period(inicio, "M"), mes_do_fechamento, freq="M"):
            if mes < mes_do_fechamento and _baixar_mes(par, mes, fontes, pasta):
                continue
            ultimo = min(mes.end_time.date(), fechamento)
            for dia in pd.date_range(mes.start_time, ultimo, freq="D"):
                _baixar_dia(par, dia.date(), fontes, pasta, hashes)
    arquivo_de_hashes.write_text(json.dumps(hashes, indent=1, sort_keys=True), "utf-8")


def _baixar_mes(par: str, mes: pd.Period, fontes: Fontes, pasta: Path) -> bool:
    try:
        dados_cripto.baixar_par(par, pd.PeriodIndex([mes]), pasta, baixar=fontes.url)
    except OSError:
        # o mensal sai nos primeiros dias do mês seguinte: vai pelos diários
        return False
    return True


def _klines_ate(
    pares: dict[str, str],
    inicio: pd.Timestamp,
    fechamento: date,
    fontes: Fontes,
    pasta: Path,
) -> dict[str, pd.DataFrame]:
    """Os candles de cada ativo, do início dos dados ao fechamento (que tem de já ter saído)."""
    atualizar_binance(inicio, fechamento, fontes, pasta, pares)
    tabelas = {
        ativo: dados_cripto.carregar_par(par, pasta).loc[inicio : pd.Timestamp(fechamento)]
        for ativo, par in pares.items()
    }
    for ativo, tabela in tabelas.items():
        _exigir_o_fechamento(pd.DatetimeIndex(tabela.index), fechamento, f"o {ativo}")
    return tabelas


def _caixa_corrido(
    fontes: Fontes,
    inicio: pd.Timestamp,
    fechamento: date,
    estimados: set[str],
    dias: pd.DatetimeIndex,
) -> pd.Series:
    uteis = _cdi_ate(fontes, inicio, fechamento, estimados)
    return modulo_cdi.retorno_diario_do_caixa(uteis, dias)


def carregar_p0_1(
    fechamento: date,
    primeiro_fechamento: date,
    fontes: Fontes = FONTES,
    pasta: Path = PASTA_DOS_DADOS,
) -> Tabelas:
    """BTC e ETH em reais (USDT × PTAX da véspera), o caixa e o volume, até o fechamento."""
    inicio, estimados = inicio_dos_dados(primeiro_fechamento), set()
    klines = _klines_ate(
        dados_cripto.PARES, inicio, fechamento, fontes, pasta / "binance"
    )
    dolar = fontes.sgs(
        dados_cripto.SERIE_DO_DOLAR, (inicio - pd.Timedelta(days=10)).date(), fechamento
    )
    # `dolar_da_vespera` só acha a véspera do primeiro dia se ela tem cotação: começa num desses.
    comeco = next(
        dia
        for dia in pd.date_range(inicio, pd.Timestamp(fechamento))
        if dia - pd.Timedelta(days=1) in dolar.index
    )
    tabelas = {ativo: tabela.loc[comeco:] for ativo, tabela in klines.items()}
    precos, volumes = dados_cripto.montar_precos(tabelas, dolar)
    volumes = dados_cripto.volume_medio_conhecido(volumes)
    cdi = _caixa_corrido(
        fontes, inicio, fechamento, estimados, pd.DatetimeIndex(precos.index)
    )
    return Tabelas(precos, cdi, volumes, tuple(sorted(estimados)))


def carregar_p0_1b(
    fechamento: date,
    primeiro_fechamento: date,
    fontes: Fontes = FONTES,
    pasta: Path = PASTA_DOS_DADOS,
) -> Tabelas:
    """BTCBRL e ETHBRL, já em reais (sem câmbio), o caixa e o volume, até o fechamento."""
    inicio, estimados = inicio_dos_dados(primeiro_fechamento), set()
    tabelas = _klines_ate(
        dados_brl.PARES, inicio, fechamento, fontes, pasta / "binance_brl"
    )
    precos, volumes = dados_brl.montar_precos(tabelas)
    volumes = dados_cripto.volume_medio_conhecido(volumes)
    cdi = _caixa_corrido(
        fontes, inicio, fechamento, estimados, pd.DatetimeIndex(precos.index)
    )
    return Tabelas(precos, cdi, volumes, tuple(sorted(estimados)))


CARREGADORES = {
    "p0_3": carregar_p0_3,
    "p0_1": carregar_p0_1,
    "di1": carregar_di1,
    "p0_1b": carregar_p0_1b,
}
