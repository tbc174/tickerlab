"""Dados da ficha P0-3: as cinco séries em reais, no calendário da B3, com cache fora do Git.

Aproximações declaradas (o relatório as repete em "Limites e cuidados"):
- **NTN-B sintética de 5 anos:** índice que rende o juro real da curva de 5 anos do Tesouro
  (prazo constante: a cada dia o título é "trocado" por um de 5 anos), mais a variação de preço
  quando a taxa muda, mais o IPCA do mês espalhado pelos pregões do mês. Não é o preço de um
  título de verdade nem o do B5P211. Dia em que a curva não tem o ponto de 5 anos (de abr a
  ago/2019 o Tesouro Direto só vendia IPCA+ de 10 anos ou mais) usa o último ponto conhecido
  deslocado pelo que o ponto de 10 anos andou; dia sem curva nenhuma mantém a taxa e segue
  rendendo o carry e o IPCA (o índice nunca fica "parado").
- **Ouro e S&P 500 em reais:** preço em dólar × dólar do dia, sem hedge; em feriado lá fora vale o
  último preço em dólar (o dólar do dia ainda move o valor em reais).
- **Calendário:** o dos preços do BOVA11 (pregões da B3); as outras séries são levadas a ele com
  o último valor disponível.
- **Volumes para o impacto:** estimativas conservadoras por ETF, fixadas aqui antes dos números.
- **Barras sem negócio:** o export do MT5 traz barras de feriado com volume zero e o preço
  repetido (91 no BOVA11 entre 2010 e 2023); elas ficam fora do calendário.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from src import bcb
from src import cdi as modulo_cdi
from trader.estrategias.carteira_rp import ATIVOS_DE_RISCO
from trader.registro import RAIZ

PASTA_DA_PESQUISA = RAIZ / "pesquisa_quant"
PASTA_DO_MT5 = RAIZ / "dados_mt5"
PASTA_DA_CURVA = Path("C:/Users/tiago/TickerLab-Acervo/acervo/base/curva_juros")
PRAZO_DA_NTNB_EM_ANOS = 5.0
PRAZO_DE_RESERVA_EM_ANOS = 10.0  # quem guia o ponto de 5 anos nos dias em que ele falta
PREGOES_POR_ANO = 252
SERIE_DO_IPCA = bcb.SERIES["ipca"]
ARQUIVOS_DO_MT5 = {
    "BOVA11": "BOVA11.SA_D1.parquet",
    "OURO": "GLD_D1.parquet",
    "SP500": "IDX_GSPC_D1.parquet",
    "BRL": "BRL_X_D1.parquet",
}
# Volume financeiro médio diário (reais) de cada ETF, estimativa conservadora para o impacto.
VOLUME_MEDIO_EM_REAIS = {
    "NTNB": 5_000_000.0,  # B5P211
    "BOVA11": 1_000_000_000.0,
    "OURO": 10_000_000.0,  # GOLD11
    "SP500": 50_000_000.0,  # IVVB11
}

Baixar = Callable[[pd.Timestamp, pd.Timestamp], pd.Series]


def indice_sintetico_da_ntnb(
    taxa_real: pd.Series,
    ipca_mensal: pd.Series,
    prazo_anos: float = PRAZO_DA_NTNB_EM_ANOS,
) -> pd.Series:
    """Índice (começa em 100) de uma NTN-B de prazo constante: carry + preço + IPCA do mês.

    `taxa_real` é a taxa real ao ano (0,06 = 6%) em cada pregão; `ipca_mensal` é a variação do mês
    (0,01 = 1%) indexada pelo mês. Falta de IPCA em algum mês é erro.
    """
    taxa = taxa_real.sort_index().astype(float)
    ipca = ipca_mensal.copy()
    ipca.index = pd.DatetimeIndex(ipca.index).to_period("M")
    meses = pd.Series(taxa.index.to_period("M"), index=taxa.index)
    faltando = sorted(set(meses) - set(ipca.index))
    if faltando:
        raise ValueError(
            f"falta o IPCA de {faltando[0]} (e de mais {len(faltando) - 1} meses)"
        )
    pregoes_no_mes = meses.map(meses.value_counts())
    ipca_do_dia = (1 + ipca.reindex(meses).to_numpy(float)) ** (
        1 / pregoes_no_mes.to_numpy(float)
    ) - 1
    carry = (1 + taxa.shift(1)) ** (1 / PREGOES_POR_ANO) - 1
    preco = ((1 + taxa.shift(1)) / (1 + taxa)) ** prazo_anos - 1
    retorno = (1 + carry.fillna(0.0)) * (1 + preco.fillna(0.0)) * (1 + ipca_do_dia) - 1
    retorno.iloc[0] = 0.0
    return 100 * (1 + retorno).cumprod()


def em_reais(serie_usd: pd.Series, brl: pd.Series) -> pd.Series:
    """Preço em dólar × dólar, no calendário do dólar; feriado lá fora usa o último preço."""
    usd = serie_usd.sort_index().reindex(brl.sort_index().index, method="ffill")
    return (usd * brl.sort_index()).dropna()


def ao_calendario(serie: pd.Series, indice: pd.DatetimeIndex) -> pd.Series:
    """A série no calendário dado, com o último valor disponível (nunca o seguinte)."""
    return serie.sort_index().reindex(indice, method="ffill")


def ntnb_no_calendario(
    taxa_real: pd.Series, ipca_mensal: pd.Series, indice: pd.DatetimeIndex
) -> pd.Series:
    """A NTN-B sintética no calendário dado: dia sem curva mantém a taxa e rende o carry e o IPCA."""
    return indice_sintetico_da_ntnb(
        ao_calendario(taxa_real, indice).dropna(), ipca_mensal
    )


def montar_precos(
    *,
    bova11: pd.Series,
    ntnb: pd.Series,
    ouro_usd: pd.Series,
    sp500_usd: pd.Series,
    brl: pd.Series,
) -> pd.DataFrame:
    """As quatro séries de risco em reais, no calendário do BOVA11, do primeiro dia comum em diante."""
    indice = pd.DatetimeIndex(bova11.sort_index().index)
    tabela = pd.DataFrame(
        {
            "NTNB": ao_calendario(ntnb, indice),
            "BOVA11": bova11.sort_index(),
            "OURO": ao_calendario(em_reais(ouro_usd, brl), indice),
            "SP500": ao_calendario(em_reais(sp500_usd, brl), indice),
        }
    )[list(ATIVOS_DE_RISCO)]
    return tabela.dropna()


# --- cache das séries do Banco Central (fora do Git) -----------------------------------------------


def carregar_com_cache(
    nome: str, inicio: pd.Timestamp, fim: pd.Timestamp, pasta: Path, baixar: Baixar
) -> pd.Series:
    """Lê `pasta/nome_inicio_fim.parquet`; se não existe, baixa, grava e devolve."""
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{nome}_{inicio:%Y%m%d}_{fim:%Y%m%d}.parquet"
    if arquivo.exists():
        return pd.read_parquet(arquivo).iloc[:, 0]
    serie = baixar(inicio, fim)
    serie.to_frame(name=nome).to_parquet(arquivo)
    return serie


def carregar_cdi(
    inicio: pd.Timestamp, fim: pd.Timestamp, pasta: Path = PASTA_DA_PESQUISA
) -> pd.Series:
    """CDI diário (fração) do SGS 12, com cache."""
    return carregar_com_cache("cdi", inicio, fim, pasta, modulo_cdi.baixar_cdi)


def carregar_ipca(
    inicio: pd.Timestamp, fim: pd.Timestamp, pasta: Path = PASTA_DA_PESQUISA
) -> pd.Series:
    """IPCA mensal (fração) do SGS 433, com cache."""

    def baixar(comeco: pd.Timestamp, final: pd.Timestamp) -> pd.Series:
        return bcb.baixar_sgs(SERIE_DO_IPCA, comeco.date(), final.date()) / 100

    return carregar_com_cache("ipca", inicio, fim, pasta, baixar)


# --- leitura das fontes locais ------------------------------------------------------------------------


def _ponto_da_curva(real: pd.DataFrame, prazo_anos: float) -> pd.Series:
    ponto = real[real["prazo_anos"] == prazo_anos]
    serie = ponto.set_index("data_base")["taxa"].astype(float).sort_index()
    serie.index = pd.DatetimeIndex(serie.index)
    return serie[~serie.index.duplicated(keep="last")]


def taxa_real_a_prazo(
    curva: pd.DataFrame,
    prazo_anos: float = PRAZO_DA_NTNB_EM_ANOS,
    prazo_de_reserva: float = PRAZO_DE_RESERVA_EM_ANOS,
) -> pd.Series:
    """A taxa real (fração a.a.) no prazo dado, por `data_base`, da tabela da curva do Tesouro.

    Dia em que o ponto não existe (o Tesouro Direto não oferecia título perto dele) recebe o
    último valor conhecido mais o que o ponto de reserva andou desde então (deslocamento
    paralelo). Dia sem os dois pontos fica de fora.
    """
    real = curva[curva["curva"] == "real"]
    alvo = _ponto_da_curva(real, prazo_anos)
    reserva = _ponto_da_curva(real, prazo_de_reserva)
    datas = alvo.index.union(reserva.index)
    alvo, reserva = alvo.reindex(datas), reserva.reindex(datas)
    reserva_quando_o_alvo_existia = reserva.where(alvo.notna()).ffill()
    deslocada = alvo.ffill() + (reserva - reserva_quando_o_alvo_existia)
    return alvo.fillna(deslocada).dropna()


def carregar_curva_real(
    pasta: Path = PASTA_DA_CURVA, prazo_anos: float = PRAZO_DA_NTNB_EM_ANOS
) -> pd.Series:
    arquivos = sorted(pasta.glob("*.parquet"))
    if not arquivos:
        raise FileNotFoundError(f"nenhuma curva de juros em {pasta}")
    return taxa_real_a_prazo(
        pd.concat(pd.read_parquet(a) for a in arquivos), prazo_anos
    )


def _coluna_de_volume(tabela: pd.DataFrame) -> str | None:
    return next((c for c in tabela.columns if "volume" in c.lower()), None)


def fechamento_do_mt5(arquivo: Path, *, so_com_negocio: bool = False) -> pd.Series:
    """A coluna de fechamento de um parquet D1 exportado do MT5, indexada pela data.

    `so_com_negocio` tira as barras com volume zero (feriado com o preço repetido).
    """
    tabela = pd.read_parquet(arquivo)
    volume = _coluna_de_volume(tabela)
    if so_com_negocio and volume is not None:
        tabela = tabela[tabela[volume] > 0]
    coluna = next(c for c in tabela.columns if c.lower() in ("close", "fechamento"))
    data = next(
        (c for c in tabela.columns if c.lower() in ("time", "data", "date")), None
    )
    serie = tabela.set_index(data)[coluna] if data else tabela[coluna]
    serie.index = pd.DatetimeIndex(serie.index).normalize()
    return serie.astype(float).sort_index()


def volume_medio_do_mt5(arquivo: Path, pregoes: int = 60) -> float | None:
    """Volume financeiro médio (preço × volume) dos últimos `pregoes`, se o arquivo tem volume."""
    tabela = pd.read_parquet(arquivo)
    volume = _coluna_de_volume(tabela)
    if volume is None:
        return None
    fechamento = fechamento_do_mt5(arquivo)
    financeiro = fechamento.to_numpy() * tabela[volume].to_numpy(float)
    return float(np.mean(financeiro[-pregoes:]))
