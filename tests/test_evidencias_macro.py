"""Evidências macro (etapa 2 dos porquês): o nível com a frase da tela, a tendência em 12 meses pela
regra fixa, o Focus contra a Selic de hoje, a série que falta e, no acervo, sem olhar o futuro."""

import json
from datetime import date

import pandas as pd
import pytest
import sqlalchemy as sa

from src import evidencias as ev
from src import evidencias_macro as em
from src import juros_e_inflacao as ji
from src.banco import series as acervo
from src.banco.modelo import metadata

DIA = date(2026, 10, 13)
DIVULGADO = date(2026, 10, 10)


def _mensal(valores, fim="2026-09-01"):
    indice = pd.date_range(end=fim, periods=len(valores), freq="MS")
    return pd.Series(valores, index=indice, dtype=float)


def _diaria(pares):
    return pd.Series(
        [v for _, v in pares], index=pd.to_datetime([d for d, _ in pares]), dtype=float
    )


def _lida(valores, divulgado_em=DIVULGADO):
    return ji.SerieLida(valores, divulgado_em)


def _lidas(**mudancas):
    base = {
        # 10,50% até o Copom de março/2025 e 15,00% desde out/2026: +4,5 pontos em 12 meses
        ji.SELIC_META: _lida(_diaria([("2025-01-02", 10.5), ("2026-10-10", 15.0)])),
        # 0,3% ao mês no 1º ano e 0,5% no 2º: o IPCA de 12 meses sobe ~2,5 pontos
        ji.IPCA: _lida(_mensal([0.3] * 12 + [0.5] * 12)),
        ji.DOLAR: _lida(_diaria([("2025-10-01", 5.00), ("2026-10-10", 5.40)])),
        ji.FOCUS_SELIC: _lida(
            _diaria([("2026-12-31", 14.25), ("2027-12-31", 12.5)]), date(2026, 10, 9)
        ),
    }
    base.update(mudancas)
    return base


def _por_prefixo(evidencias, prefixo):
    (achada,) = [e for e in evidencias if e.id.startswith(prefixo)]
    return achada


def _tendencia(evidencias, chave):
    """A evidência de tendência de uma série, pela regra (o id muda com o rótulo)."""
    (achada,) = [
        e for e in evidencias if e.regra.startswith(f"macro/{chave}_tendencia")
    ]
    return achada


# --- fatos: o nível com a frase da tela ------------------------------------------------------------
def test_nivel_da_selic_tem_o_mesmo_numero_e_a_legenda_da_tela():
    lidas = _lidas()
    selic = _por_prefixo(em.evidencias_macro(lidas, DIA), "macro.selic.nivel")
    numero = next(
        n for n in ji.montar_painel(lidas, None, DIA).numeros if n.nome == ji.NOME_SELIC
    )
    assert selic.valor == numero.valor == 15.0
    assert (
        ji.formatar_valor(numero) in selic.frase and ji.legenda(numero) in selic.frase
    )
    assert (selic.forca, selic.tipo, selic.divulgado_em) == (
        ev.FATO,
        ev.MACRO,
        DIVULGADO,
    )


def test_nivel_do_ipca_em_12_meses_compoe_os_meses_como_a_tela():
    ipca = _por_prefixo(em.evidencias_macro(_lidas(), DIA), "macro.ipca_12m.nivel")
    assert ipca.valor == pytest.approx((1.005**12 - 1) * 100, abs=1e-4)


# --- padrões: a tendência em 12 meses --------------------------------------------------------------
def test_selic_que_subiu_mais_que_o_limiar_vira_subiu():
    selic = _tendencia(em.evidencias_macro(_lidas(), DIA), "selic")
    assert selic.id == "macro.selic.subiu"
    assert selic.valor == pytest.approx(4.5)
    assert "de 10,50% para 15,00%" in selic.frase
    assert selic.forca == ev.PADRAO


@pytest.mark.parametrize(
    ("antes", "agora", "esperado"),
    [(15.0, 15.25, "estavel"), (15.0, 14.5, "caiu"), (14.5, 15.0, "subiu")],
)
def test_limiar_dos_juros_decide_subiu_caiu_ou_estavel(antes, agora, esperado):
    selic = _lida(_diaria([("2025-01-02", antes), ("2026-10-10", agora)]))
    evidencias = em.evidencias_macro(_lidas(**{ji.SELIC_META: selic}), DIA)
    assert any(e.id == f"macro.selic.{esperado}" for e in evidencias)


def test_ipca_que_acelerou_vira_subiu():
    ipca = _tendencia(em.evidencias_macro(_lidas(), DIA), "ipca_12m")
    assert ipca.id == "macro.ipca_12m.subiu"
    esperado = ((1.005**12) - (1.003**12)) * 100
    assert ipca.valor == pytest.approx(esperado, abs=1e-4)


def test_dolar_que_subiu_8_por_cento_fica_estavel_pela_regra_dos_10():
    dolar = _tendencia(em.evidencias_macro(_lidas(), DIA), "dolar")
    assert dolar.id == "macro.dolar.estavel"
    assert dolar.valor == pytest.approx(0.08)
    assert "de R$ 5,00 para R$ 5,40" in dolar.frase


def test_regra_escrita_vai_nos_limites_de_toda_tendencia():
    for evidencia in em.evidencias_macro(_lidas(), DIA):
        if evidencia.forca == ev.PADRAO:
            assert em.LIMITE_DO_PADRAO in evidencia.limites
            assert evidencia.regra.endswith(f"@{em.VERSAO_DAS_REGRAS}")


# --- padrão: o Focus contra a Selic de hoje -------------------------------------------------------
def test_focus_abaixo_da_selic_de_hoje_e_corte_esperado():
    focus = _por_prefixo(em.evidencias_macro(_lidas(), DIA), "macro.focus_selic.")
    assert focus.id == "macro.focus_selic.espera-corte"
    assert focus.valor == pytest.approx(-0.75)
    assert focus.divulgado_em == date(2026, 10, 9)  # a data da pesquisa
    assert ji.NOTA_DO_FOCUS in focus.limites


# --- série que falta -------------------------------------------------------------------------------
def test_serie_que_falta_vira_indisponivel_com_motivo_e_o_resto_continua():
    lidas = _lidas()
    del lidas[ji.DOLAR]
    evidencias = em.evidencias_macro(lidas, DIA)
    dolar = _por_prefixo(evidencias, "macro.dolar.")
    assert dolar.id == "macro.dolar.indisponivel"
    assert dolar.valor is None and dolar.divulgado_em is None and "Dólar" in dolar.frase
    assert any(e.id == "macro.selic.subiu" for e in evidencias)


def test_menos_de_12_meses_de_historico_nao_inventa_tendencia():
    curta = _lida(_diaria([("2026-06-01", 14.0), ("2026-10-10", 15.0)]))
    evidencias = em.evidencias_macro(_lidas(**{ji.SELIC_META: curta}), DIA)
    assert any(e.id == "macro.selic.indisponivel" for e in evidencias)


def test_todas_viram_json():
    json.dumps([e.como_dict() for e in em.evidencias_macro(_lidas(), DIA)])


# --- sem olhar o futuro, no acervo do Banco Central -----------------------------------------------
@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    metadata.create_all(motor)
    with motor.begin() as c:
        yield c


def _gravar_selic(conexao, pares, divulgado_em):
    acervo.garantir_serie(
        conexao,
        acervo.SerieDoAcervo(ji.SELIC_META, "Meta da Selic", "% a.a.", "diaria"),
    )
    acervo.gravar(conexao, ji.SELIC_META, _diaria(pares), divulgado_em)


def test_decisao_do_copom_depois_do_dia_nao_muda_as_evidencias_do_dia(conexao):
    _gravar_selic(
        conexao, [("2025-01-02", 10.5), ("2026-10-10", 15.0)], date(2026, 10, 10)
    )
    antes_do_copom = em.evidencias_macro_em(conexao, DIA)
    # o Copom de 05/11/2026 corta para 14,50%: publicado depois do dia, não pode aparecer
    _gravar_selic(conexao, [("2026-11-05", 14.5)], date(2026, 11, 5))
    assert em.evidencias_macro_em(conexao, DIA) == antes_do_copom
    selic = _por_prefixo(em.evidencias_macro_em(conexao, DIA), "macro.selic.nivel")
    assert selic.valor == 15.0
    depois = _por_prefixo(
        em.evidencias_macro_em(conexao, date(2026, 11, 6)), "macro.selic.nivel"
    )
    assert depois.valor == 14.5 and depois.divulgado_em == date(2026, 11, 5)


def test_nenhuma_evidencia_e_divulgada_depois_do_dia(conexao):
    _gravar_selic(
        conexao, [("2025-01-02", 10.5), ("2026-10-10", 15.0)], date(2026, 10, 10)
    )
    _gravar_selic(conexao, [("2026-11-05", 14.5)], date(2026, 11, 5))
    for evidencia in em.evidencias_macro_em(conexao, DIA):
        assert evidencia.divulgado_em is None or evidencia.divulgado_em <= DIA
