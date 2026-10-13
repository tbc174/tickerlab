"""Testes de src/juros_e_inflacao.py: o painel de juros e inflação a partir do acervo do BC."""

from datetime import date

import pandas as pd
import pytest
import sqlalchemy as sa

from src import juros_e_inflacao as ji
from src.banco import series as acervo
from src.banco.modelo import metadata

HOJE = date(2026, 10, 13)


def _mensal(valores, fim="2026-09-01"):
    indice = pd.date_range(end=fim, periods=len(valores), freq="MS")
    return pd.Series(valores, index=indice, dtype=float)


def _lida(valores, divulgado_em=date(2026, 10, 10)):
    return ji.SerieLida(valores, divulgado_em)


def _lidas(**mudancas):
    base = {
        ji.SELIC_META: _lida(
            pd.Series([10.5, 15.0], index=pd.to_datetime(["2025-01-02", "2026-10-10"]))
        ),
        ji.IPCA: _lida(_mensal([0.5] * 12)),
        ji.FOCUS_IPCA: _lida(
            pd.Series([4.8, 4.2], index=pd.to_datetime(["2026-12-31", "2027-12-31"])),
            date(2026, 10, 9),
        ),
        ji.FOCUS_SELIC: _lida(
            pd.Series([15.0, 12.5], index=pd.to_datetime(["2026-12-31", "2027-12-31"])),
            date(2026, 10, 9),
        ),
        ji.DOLAR: _lida(pd.Series([5.40], index=pd.to_datetime(["2026-10-10"]))),
    }
    base.update(mudancas)
    return base


def _numero(painel, nome):
    return next(n for n in painel.numeros if n.nome == nome)


def test_ipca_em_12_meses_compoe_os_meses():
    painel = ji.montar_painel(_lidas(), None, HOJE)
    # 1,005 elevado a 12 = 1,061678: 6,17% em 12 meses (e não 6,0%, a soma simples)
    assert _numero(painel, ji.NOME_IPCA_12M).valor == pytest.approx(6.1678, abs=1e-4)


def test_ipca_com_menos_de_12_meses_nao_inventa_o_acumulado():
    painel = ji.montar_painel(
        _lidas(**{ji.IPCA: _lida(_mensal([0.5] * 8))}), None, HOJE
    )
    assert _numero(painel, ji.NOME_IPCA_12M).valor is None


def test_juro_real_desconta_a_inflacao():
    # CDI de 0,05% ao dia por 252 dias úteis = 13,42% em 12 meses; IPCA 12m = 6,1678%
    dias = pd.bdate_range(end="2026-10-09", periods=300)
    cdi = pd.Series(0.0005, index=dias)
    painel = ji.montar_painel(_lidas(), cdi, HOJE)
    cdi_12m = _numero(painel, ji.NOME_CDI_12M).valor
    assert cdi_12m == pytest.approx((1.0005**252 - 1) * 100, abs=1e-6)
    real = _numero(painel, ji.NOME_JURO_REAL).valor
    assert real == pytest.approx(((1 + cdi_12m / 100) / 1.061678 - 1) * 100, abs=1e-3)


def test_sem_cdi_o_juro_real_fica_vazio_e_avisa():
    painel = ji.montar_painel(_lidas(), None, HOJE)
    assert _numero(painel, ji.NOME_JURO_REAL).valor is None
    assert any("CDI" in aviso for aviso in painel.avisos)


def test_cada_numero_traz_a_referencia_a_divulgacao_e_a_fonte():
    painel = ji.montar_painel(_lidas(), None, HOJE)
    selic = _numero(painel, ji.NOME_SELIC)
    assert selic.valor == 15.0 and selic.unidade == "% ao ano"
    assert selic.referencia == date(2026, 10, 10)
    assert selic.divulgado_em == date(2026, 10, 10)
    assert "Banco Central" in selic.fonte and "432" in selic.fonte
    ipca = _numero(painel, ji.NOME_IPCA_MES)
    assert ipca.referencia == date(2026, 9, 1)


def test_expectativas_do_focus_para_este_ano_e_o_proximo():
    painel = ji.montar_painel(_lidas(), None, HOJE)
    pares = {(e.indicador, e.ano): e.mediana for e in painel.expectativas}
    assert pares == {
        ("IPCA", 2026): 4.8,
        ("IPCA", 2027): 4.2,
        ("Selic", 2026): 15.0,
        ("Selic", 2027): 12.5,
    }
    assert all(e.pesquisa == date(2026, 10, 9) for e in painel.expectativas)


def test_serie_faltando_vira_aviso_e_nao_quebra():
    lidas = _lidas()
    del lidas[ji.DOLAR]
    painel = ji.montar_painel(lidas, None, HOJE)
    assert _numero(painel, ji.NOME_DOLAR).valor is None
    assert any("dólar" in aviso.lower() for aviso in painel.avisos)


def test_historico_mensal_traz_selic_e_ipca_em_12_meses():
    lidas = _lidas(**{ji.IPCA: _lida(_mensal([0.5] * 24))})
    painel = ji.montar_painel(lidas, None, HOJE)
    ultimo = painel.historico[-1]
    assert ultimo.mes == date(2026, 9, 1)
    assert ultimo.ipca_12_meses == pytest.approx(6.1678, abs=1e-4)
    assert (
        painel.historico[0].ipca_12_meses is None
    )  # os 11 primeiros meses não têm 12 para trás


# --- leitura do acervo --------------------------------------------------------------------


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


def test_valor_revisto_mostra_a_safra_mais_nova_e_a_data(conexao):
    serie = acervo.SerieDoAcervo(ji.IPCA, "IPCA", "% no mês", "mensal")
    acervo.garantir_serie(conexao, serie)
    setembro = pd.Series([0.44], index=pd.to_datetime(["2026-09-01"]))
    acervo.gravar(conexao, ji.IPCA, setembro, date(2026, 10, 9))
    acervo.gravar(conexao, ji.IPCA, setembro * 0 + 0.48, date(2026, 10, 11))  # revisto
    lida = ji.ler_series(conexao, HOJE)[ji.IPCA]
    assert lida.valores.iloc[-1] == 0.48
    assert lida.divulgado_em == date(2026, 10, 11)
    antes = ji.ler_series(conexao, date(2026, 10, 10))[
        ji.IPCA
    ]  # como estava antes da revisão
    assert antes.valores.iloc[-1] == 0.44 and antes.divulgado_em == date(2026, 10, 9)


def test_serie_sem_dados_nao_aparece_na_leitura(conexao):
    assert ji.ler_series(conexao, HOJE) == {}


# --- textos para a tela (e para a API) ----------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "unidade", "esperado"),
    [
        (15.0, "% ao ano", "15,00% ao ano"),
        (0.44, "% no mês", "0,44%"),
        (6.1678, "% em 12 meses", "6,17%"),
        (5.4, "R$ por US$", "R$ 5,40"),
        (None, "% ao ano", "—"),
    ],
)
def test_valor_formatado_em_portugues(valor, unidade, esperado):
    numero = ji.Numero("X", valor, unidade, None, None, "fonte")
    assert ji.formatar_valor(numero) == esperado


def test_legenda_diz_a_referencia_a_divulgacao_e_a_fonte():
    painel = ji.montar_painel(_lidas(), None, HOJE)
    assert ji.legenda(_numero(painel, ji.NOME_SELIC)) == (
        "Referência: 10/10/2026 · divulgado em 10/10/2026 · Banco Central, SGS 432"
    )
    assert ji.legenda(_numero(painel, ji.NOME_IPCA_MES)).startswith(
        "Referência: set/2026"
    )


def test_legenda_sem_divulgacao_nao_inventa_data():
    numero = ji.Numero(
        "CDI", 13.4, "% em 12 meses", date(2026, 10, 9), None, "Banco Central, SGS 12"
    )
    assert ji.legenda(numero) == "Referência: 09/10/2026 · Banco Central, SGS 12"
