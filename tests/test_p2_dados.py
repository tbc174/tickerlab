"""Pesquisa 2, fase P3: universo candidato, leitura do FRED, qualidade e download (sem internet)."""

import pandas as pd
import pytest

from trader.p2 import baixar, fontes, mercados
from trader.p2.mercados import GRUPOS, MERCADOS, Mercado, entra_no_universo


# --- universo -------------------------------------------------------------------------------
def test_codigos_e_cfds_sao_unicos():
    assert len({m.codigo for m in MERCADOS}) == len(MERCADOS)
    assert len({m.cfd for m in MERCADOS}) == len(MERCADOS)


def test_todo_mercado_tem_grupo_fonte_e_cfd_validos():
    for m in MERCADOS:
        assert m.grupo in GRUPOS, m
        assert m.fonte in mercados.FONTES, m
        assert m.cfd.endswith("-T"), m  # sufixo dos CFDs da conta de referência


def test_os_cinco_grupos_estao_representados():
    assert {m.grupo for m in MERCADOS} == set(GRUPOS)


def test_as_duas_moedas_de_cada_par_tem_juros_curtos():
    """Sem os juros das duas pontas não há como calcular o carry do par."""
    for m in MERCADOS:
        if m.grupo == "moedas":
            base, cotacao = m.codigo[:3], m.codigo[3:]
            assert base in mercados.JUROS_CURTOS, m
            assert cotacao in mercados.JUROS_CURTOS, m


def test_regra_de_entrada_exige_15_anos_antes_do_holdout():
    m = mercados.por_codigo("EURUSD")
    assert mercados.INICIO_MAXIMO == pd.Timestamp("2008-10-10")
    assert entra_no_universo(m, pd.Timestamp("1999-01-04"))
    assert entra_no_universo(m, pd.Timestamp("2008-10-10"))
    assert not entra_no_universo(m, pd.Timestamp("2008-10-13"))
    assert not entra_no_universo(m, None)


def test_mercado_sem_cfd_nao_entra():
    sem_cfd = Mercado("X", "indices", "", "yahoo", "^X", "USD")
    assert not entra_no_universo(sem_cfd, pd.Timestamp("1990-01-01"))


def test_por_codigo_recusa_mercado_desconhecido():
    with pytest.raises(KeyError):
        mercados.por_codigo("NAO_EXISTE")


# --- leitura do FRED ------------------------------------------------------------------------
def test_csv_do_fred_vira_serie_sem_valores_faltando():
    texto = (
        "observation_date,DEXUSEU\n1999-01-04,1.1812\n1999-01-05,.\n1999-01-06,1.1760\n"
    )
    serie = fontes.ler_csv_do_fred(texto)
    assert list(serie.index) == [pd.Timestamp("1999-01-04"), pd.Timestamp("1999-01-06")]
    assert serie.iloc[0] == pytest.approx(1.1812)


# --- qualidade ------------------------------------------------------------------------------
def _serie(valores, inicio="2020-01-01"):
    return pd.Series(
        valores, index=pd.bdate_range(inicio, periods=len(valores)), dtype=float
    )


def test_serie_limpa_e_aprovada():
    q = fontes.medir_qualidade(_serie([100, 101, 100.5, 102, 101.5]))
    assert q.aprovada and q.pontos == 5 and q.saltos_suspeitos == 0


def test_preco_nao_positivo_reprova_mas_taxa_negativa_nao():
    precos = _serie([100, -5, 100])
    assert not fontes.medir_qualidade(precos).aprovada
    taxas = _serie([0.5, -0.2, -0.1])
    assert fontes.medir_qualidade(taxas, e_preco=False).aprovada


def test_salto_improvavel_e_contado():
    calmo = [100 * (1.001**i) for i in range(300)]
    q = fontes.medir_qualidade(_serie([*calmo, calmo[-1] * 3]))
    assert q.saltos_suspeitos == 1


def test_lacuna_longa_e_medida():
    serie = pd.Series(
        [1.0, 1.1, 1.2],
        index=pd.to_datetime(["2020-01-01", "2020-01-02", "2020-02-01"]),
    )
    assert fontes.medir_qualidade(serie).maior_lacuna_em_dias == 30


def test_nome_de_serie_perigoso_e_recusado(tmp_path):
    with pytest.raises(ValueError):
        fontes.caminho_da_serie("fred", "../segredo", tmp_path)


def test_salvar_e_carregar_serie(tmp_path):
    serie = _serie([1.0, 2.0, 3.0])
    fontes.salvar_serie(serie, "yahoo", "^GSPC", tmp_path)
    lida = fontes.carregar_serie("yahoo", "^GSPC", tmp_path)
    pd.testing.assert_series_equal(lida, serie.rename("valor"), check_freq=False)


# --- download (com baixadores falsos) -------------------------------------------------------
def test_baixar_tudo_grava_series_e_relatorio(tmp_path):
    def fred_falso(serie_id):
        if serie_id == "DEXBZUS":
            raise ConnectionError("fora do ar")
        return _serie([1.0, 1.01, 1.02], inicio="1990-01-01")

    def mt5_falso(simbolo):
        return _serie([1800.0, 1810.0, 1805.0], inicio="1995-01-03")

    def yahoo_falso(simbolo):
        return _serie([100.0, 101.0, 102.0], inicio="2015-01-01")

    relatorio = baixar.baixar_tudo(
        {"fred": fred_falso, "yahoo": yahoo_falso, "mt5": mt5_falso}, tmp_path
    )

    assert (tmp_path / "relatorio_de_qualidade.csv").exists()
    assert len(relatorio) == len(MERCADOS) + len(mercados.JUROS_CURTOS)
    brl = relatorio[relatorio["codigo"] == "USDBRL"].iloc[0]
    assert "fora do ar" in brl["erro"] and not brl["entra_no_universo"]
    eur = relatorio[relatorio["codigo"] == "EURUSD"].iloc[0]
    assert eur["entra_no_universo"]  # série falsa começa em 1990
    spx = relatorio[relatorio["codigo"] == "USA500"].iloc[0]
    assert not spx["entra_no_universo"]  # série falsa começa em 2015


def test_nome_de_cfd_com_colchetes_e_aceito(tmp_path):
    assert fontes.caminho_da_serie("mt5", "[USA500]-T", tmp_path).name.startswith(
        "mt5_"
    )


def test_baixar_mt5_usa_a_conexao_demo_e_normaliza_as_datas(monkeypatch):
    class ConexaoFalsa:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def candles(self, simbolo, timeframe, inicio):
            assert (simbolo, timeframe) == ("GOLD-T", "D1")
            indice = pd.to_datetime(
                ["1995-01-03 00:00", "1995-01-04 00:00", "1995-01-04 00:00"]
            )
            return pd.DataFrame({"Close": [380.0, 381.0, 382.0]}, index=indice)

    import trader.mt5

    monkeypatch.setattr(trader.mt5, "ConexaoMT5", ConexaoFalsa)
    serie = fontes.baixar_mt5("GOLD-T")
    assert list(serie) == [380.0, 382.0]  # data repetida: fica a última
