"""Papel da v0.2: os dados do dia saem das fontes de sempre, com o que ainda não saiu marcado como
estimado e sem preço do fechamento inventado. Sem internet: as fontes são dublês."""

import io
import re
import zipfile
from dataclasses import dataclass, replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from trader.calendario import eh_pregao
from trader.estrategias import dados_p0_3
from trader.papel import dados as dd
from trader.papel import series as sr

PRIMEIRO = date(2026, 11, 5)  # o primeiro fechamento (véspera do início, 06/11)
COMECO = pd.Timestamp("2024-09-01")
PREGOES = pd.DatetimeIndex(
    [d for d in pd.date_range(COMECO, "2027-01-31") if eh_pregao(d.date())]
)


@dataclass
class Mundo:
    """O que cada fonte já publicou: o último dia (ou mês) de cada uma."""

    precos_ate: date
    cdi_ate: date
    curva_ate: date
    ipca_ate: str  # mês "AAAA-MM"
    mensal_ate: str  # último mês com o zip mensal da Binance
    diario_ate: date

    def yahoo(self, simbolo: str) -> pd.DataFrame:
        semente = sum(map(ord, simbolo))
        datas = PREGOES[pd.Timestamp(self.precos_ate) >= PREGOES]
        fechamento = 100 * np.cumprod(
            1 + np.random.default_rng(semente).normal(0.0003, 0.01, len(datas))
        )
        tabela = pd.DataFrame(
            {
                "Open": fechamento,
                "High": fechamento * 1.01,
                "Low": fechamento * 0.99,
                "Close": fechamento,
                "Volume": 1e6,
            },
            index=pd.DatetimeIndex(datas, name="Date"),
        )
        return tabela

    def cdi(self, inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.Series:
        datas = PREGOES[
            (inicio <= PREGOES) & (min(fim, pd.Timestamp(self.cdi_ate)) >= PREGOES)
        ]
        return pd.Series(0.0004, index=datas)

    def sgs(self, serie, inicio: date, fim: date) -> pd.Series:
        if serie == dados_p0_3.SERIE_DO_IPCA:
            meses = pd.period_range(
                pd.Period(inicio, "M"), pd.Period(self.ipca_ate, "M"), freq="M"
            )
            return pd.Series(0.4, index=meses.to_timestamp())  # em %, como o SGS
        datas = PREGOES[
            (pd.Timestamp(inicio) <= PREGOES) & (pd.Timestamp(fim) >= PREGOES)
        ]
        return pd.Series(5.0, index=datas)

    def url(self, endereco: str) -> bytes:
        mensal = re.search(r"/monthly/.*-1d-(\d{4}-\d{2})\.zip$", endereco)
        if mensal:
            if mensal.group(1) > self.mensal_ate:
                raise FileNotFoundError(endereco)
            mes = pd.Period(mensal.group(1), "M")
            return _zip(pd.date_range(mes.start_time, mes.end_time.normalize()))
        dia = date.fromisoformat(
            re.search(r"-1d-(\d{4}-\d{2}-\d{2})\.zip$", endereco).group(1)
        )
        if dia > self.diario_ate:
            raise FileNotFoundError(endereco)
        return _zip(pd.DatetimeIndex([pd.Timestamp(dia)]))


def _zip(dias: pd.DatetimeIndex) -> bytes:
    linhas = []
    for dia in dias:
        abertura = int(dia.tz_localize("UTC").timestamp() * 1000)
        fechamento = 100 + (dia - COMECO).days * 0.1
        linhas.append(
            [
                abertura,
                1,
                2,
                0.5,
                fechamento,
                10,
                abertura + 86_399_999,
                1e7,
                5,
                1,
                1,
                0,
            ]
        )
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            "klines.csv", "\n".join(",".join(str(v) for v in linha) for linha in linhas)
        )
    return saida.getvalue()


def _curva(pasta, ate: date) -> None:
    datas = PREGOES[pd.Timestamp(ate) >= PREGOES]
    partes = [
        pd.DataFrame(
            {"data_base": datas, "curva": curva, "prazo_anos": prazo, "taxa": taxa}
        )
        for curva, prazo, taxa in (
            ("real", 5.0, 0.06),
            ("real", 10.0, 0.062),
            ("nominal", 2.0, 0.11),
        )
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    pd.concat(partes, ignore_index=True).to_parquet(pasta / "curva.parquet")


def _fontes(mundo: Mundo, tmp_path) -> dd.Fontes:
    pasta_da_curva = tmp_path / "acervo" / f"curva_{mundo.curva_ate:%Y%m%d}"
    _curva(pasta_da_curva, mundo.curva_ate)
    return dd.Fontes(
        yahoo=mundo.yahoo,
        cdi=mundo.cdi,
        sgs=mundo.sgs,
        url=mundo.url,
        pasta_da_curva=pasta_da_curva,
    )


F = date(2026, 11, 10)  # uma terça
TUDO_PUBLICADO = Mundo(
    precos_ate=F,
    cdi_ate=F,
    curva_ate=F,
    ipca_ate="2026-11",
    mensal_ate="2026-10",
    diario_ate=F,
)
NO_FECHAMENTO = Mundo(  # o que de fato existe às 19h30 do fechamento
    precos_ate=F,
    cdi_ate=date(2026, 11, 9),
    curva_ate=date(2026, 11, 9),
    ipca_ate="2026-09",
    mensal_ate="2026-10",
    diario_ate=F,
)


# --- P0-3 ----------------------------------------------------------------------------------------


def test_p0_3_le_ate_o_fechamento_desde_a_folga(tmp_path):
    tabelas = dd.carregar_p0_3(
        F, PRIMEIRO, _fontes(TUDO_PUBLICADO, tmp_path), tmp_path / "papel"
    )
    assert tabelas.precos.index.max() == pd.Timestamp(F)
    assert tabelas.precos.index.min() >= dd.inicio_dos_dados(PRIMEIRO)
    assert list(tabelas.precos.columns) == ["NTNB", "BOVA11", "OURO", "SP500"]
    assert tabelas.cdi.index.equals(tabelas.precos.index)
    assert tabelas.estimados == ()
    assert (tmp_path / "papel" / "yahoo" / "BOVA11.SA_D1.parquet").exists()


def test_p0_3_marca_o_que_ainda_nao_saiu_no_fechamento(tmp_path):
    tabelas = dd.carregar_p0_3(
        F, PRIMEIRO, _fontes(NO_FECHAMENTO, tmp_path), tmp_path / "papel"
    )
    assert tabelas.estimados == ("IPCA", "cdi", "curva")
    assert (
        tabelas.cdi.loc[pd.Timestamp(F)] == tabelas.cdi.loc[pd.Timestamp("2026-11-09")]
    )
    assert tabelas.precos.index.max() == pd.Timestamp(F)


def test_sem_o_preco_do_fechamento_espera(tmp_path):
    atrasado = replace(TUDO_PUBLICADO, precos_ate=date(2026, 11, 9))
    with pytest.raises(dd.DadoAindaNaoSaiuError, match="BOVA11"):
        dd.carregar_p0_3(F, PRIMEIRO, _fontes(atrasado, tmp_path), tmp_path / "papel")


def test_a_ntnb_nao_antecipa_o_ipca_do_mes(tmp_path):
    """Ler no 3º pregão do mês ou no fim do mês dá o mesmo preço nos dias já passados."""
    cedo = date(2026, 11, 5)
    fim_do_mes = date(2026, 11, 30)
    mundo = replace(
        TUDO_PUBLICADO, precos_ate=fim_do_mes, cdi_ate=fim_do_mes, curva_ate=fim_do_mes
    )
    fontes = _fontes(mundo, tmp_path)
    no_comeco = dd.carregar_p0_3(cedo, PRIMEIRO, fontes, tmp_path / "a").precos["NTNB"]
    no_fim = dd.carregar_p0_3(fim_do_mes, PRIMEIRO, fontes, tmp_path / "b").precos[
        "NTNB"
    ]
    pd.testing.assert_series_equal(no_comeco, no_fim.loc[: pd.Timestamp(cedo)])


def test_p0_3_os_dados_do_papel_fazem_a_foto(tmp_path):
    tabelas = dd.carregar_p0_3(
        F, PRIMEIRO, _fontes(NO_FECHAMENTO, tmp_path), tmp_path / "papel"
    )
    foto = sr.fotografar_p0_3(tabelas, F, PRIMEIRO)
    assert foto["fechamento"] == F.isoformat()
    assert foto["dados"]["estimados"] == ["IPCA", "cdi", "curva"]


# --- DI1 -----------------------------------------------------------------------------------------


def test_di1_le_ate_o_fechamento_com_a_curva_da_vespera(tmp_path):
    entradas = dd.carregar_di1(
        F, PRIMEIRO, _fontes(NO_FECHAMENTO, tmp_path), tmp_path / "papel"
    )
    assert entradas.estimados == ("cdi", "curva")
    assert entradas.ativo.excesso.index.max() == pd.Timestamp(F)
    foto = sr.fotografar_di1(entradas, F, PRIMEIRO)
    assert set(foto["carteira"]["exposicao"]) == {"DI1"}
    assert foto["dados"]["estimados"] == ["cdi", "curva"]


def test_di1_sem_o_bova11_do_fechamento_espera(tmp_path):
    atrasado = replace(NO_FECHAMENTO, precos_ate=date(2026, 11, 9))
    with pytest.raises(dd.DadoAindaNaoSaiuError):
        dd.carregar_di1(F, PRIMEIRO, _fontes(atrasado, tmp_path), tmp_path / "papel")


# --- P0-1 ----------------------------------------------------------------------------------------


def test_cripto_usa_os_mensais_e_os_diarios_do_mes_corrente(tmp_path):
    pasta = tmp_path / "papel"
    tabelas = dd.carregar_p0_1(F, PRIMEIRO, _fontes(TUDO_PUBLICADO, tmp_path), pasta)
    assert tabelas.precos.index.max() == pd.Timestamp(F)
    assert (
        tabelas.precos.index.to_series().diff().dropna() == pd.Timedelta(days=1)
    ).all()
    binance = pasta / "binance"
    assert (binance / "BTCUSDT-1d-2026-10.zip").exists()
    assert (binance / "BTCUSDT-1d-2026-11-10.zip").exists()
    assert not (
        binance / "BTCUSDT-1d-2026-10-15.zip"
    ).exists()  # o mensal cobre outubro
    foto = sr.fotografar_p0_1(tabelas, F, PRIMEIRO)
    assert set(foto["carteira"]["exposicao"]) == {"BTC", "ETH"}


def test_cripto_vai_pelos_diarios_quando_o_mensal_ainda_nao_saiu(tmp_path):
    dia = date(2026, 11, 1)
    mundo = replace(
        TUDO_PUBLICADO,
        mensal_ate="2026-09",
        diario_ate=dia,
        precos_ate=dia,
        cdi_ate=dia,
    )
    pasta = tmp_path / "papel"
    tabelas = dd.carregar_p0_1(dia, PRIMEIRO, _fontes(mundo, tmp_path), pasta)
    assert (pasta / "binance" / "BTCUSDT-1d-2026-10-31.zip").exists()
    assert tabelas.precos.index.max() == pd.Timestamp(dia)
    assert tabelas.precos.loc["2026-10"].notna().all().all()


def test_cripto_sem_o_candle_do_fechamento_espera(tmp_path):
    atrasado = replace(TUDO_PUBLICADO, diario_ate=date(2026, 11, 9))
    with pytest.raises(dd.DadoAindaNaoSaiuError, match="BTC"):
        dd.carregar_p0_1(F, PRIMEIRO, _fontes(atrasado, tmp_path), tmp_path / "papel")


def test_cripto_le_de_novo_sem_baixar_o_que_ja_tem(tmp_path):
    pasta = tmp_path / "papel"
    baixados = []
    mundo = TUDO_PUBLICADO

    def contar(endereco: str) -> bytes:
        baixados.append(endereco)
        return mundo.url(endereco)

    fontes = replace(_fontes(mundo, tmp_path), url=contar)
    dd.carregar_p0_1(F, PRIMEIRO, fontes, pasta)
    primeira = len(baixados)
    dd.carregar_p0_1(F, PRIMEIRO, fontes, pasta)
    assert len(baixados) == primeira


def test_cripto_comeca_num_dia_cuja_vespera_tem_dolar(tmp_path):
    primeiro = date(2026, 11, 3)  # a folga cai num domingo, com a véspera no sábado
    assert dd.inicio_dos_dados(primeiro).day_name() == "Sunday"
    tabelas = dd.carregar_p0_1(
        F, primeiro, _fontes(TUDO_PUBLICADO, tmp_path), tmp_path / "papel"
    )
    assert tabelas.precos.notna().all().all()
    assert tabelas.precos.index.min() == pd.Timestamp(
        "2024-11-05"
    )  # a véspera, 04/11, é pregão


def test_p0_1b_le_os_pares_em_reais_sem_dolar(tmp_path):
    pasta = tmp_path / "papel"
    pedidos = []
    mundo = TUDO_PUBLICADO

    def sgs(serie, inicio, fim):
        pedidos.append(serie)
        return mundo.sgs(serie, inicio, fim)

    fontes = replace(_fontes(mundo, tmp_path), sgs=sgs)
    tabelas = dd.carregar_p0_1b(F, PRIMEIRO, fontes, pasta)
    assert pedidos == []  # sem PTAX: o par já é em reais
    assert (pasta / "binance_brl" / "BTCBRL-1d-2026-11-10.zip").exists()
    assert not (pasta / "binance").exists()
    assert tabelas.precos.index.min() == dd.inicio_dos_dados(PRIMEIRO)
    assert tabelas.precos.index.max() == pd.Timestamp(F)
    foto = sr.fotografar_p0_1b(tabelas, F, PRIMEIRO)
    assert foto["regra"]["registro"] == 18


def test_p0_1b_sem_o_candle_do_fechamento_espera(tmp_path):
    atrasado = replace(TUDO_PUBLICADO, diario_ate=date(2026, 11, 9))
    with pytest.raises(dd.DadoAindaNaoSaiuError, match="BTC"):
        dd.carregar_p0_1b(F, PRIMEIRO, _fontes(atrasado, tmp_path), tmp_path / "papel")


def test_toda_serie_tem_carregador():
    assert set(dd.CARREGADORES) == {s.nome for s in sr.SERIES}
