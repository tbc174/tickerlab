"""Capacidade de endividamento por regra declarada (B-22 do dossiê da plataforma, protótipo B, parte 2).

As contas das regras com insumos de mentira; a sensibilidade monotônica por propriedade (Hypothesis);
os insumos das demonstrações reais de 4 empresas (`tests/arquivos/cvm/fundamentos/`), como eram no dia."""

import json
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src import demonstracoes as dm
from src import fundamentos as fu
from src.banco import demonstracoes as repo
from src.banco.conexao import criar_engine, migrar_para
from src.divida import capacidade as ca
from src.rastro import DocumentoUsado, Rastro

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
PETROBRAS, ITAU, WEG = "33.000.167/0001-01", "60.872.504/0001-23", "84.429.695/0001-11"
DIA = date(2026, 9, 30)
BI = 1e9
RASTRO = Rastro.dos_documentos(
    "x", "x", "cvm", [DocumentoUsado("DFP de mentira", date(2026, 3, 1))]
)


def _insumo(chave: str, valor: float | None) -> ca.Insumo:
    return ca.Insumo(chave, chave.capitalize(), valor, "12 meses", RASTRO)


def _insumos(
    ebitda: float | None = 10 * BI,
    ebit: float | None = 8 * BI,
    despesa: float | None = 2 * BI,
    caixa: float | None = 5 * BI,
    liquida: float | None = 15 * BI,
) -> ca.Insumos:
    return ca.Insumos(
        ebitda=_insumo("ebitda", ebitda),
        ebit=_insumo("ebit", ebit),
        despesa_financeira=_insumo("despesa_financeira", despesa),
        divida_bruta=_insumo(
            "divida_bruta",
            None if liquida is None or caixa is None else liquida + caixa,
        ),
        caixa=_insumo("caixa", caixa),
        divida_liquida=_insumo("divida_liquida", liquida),
    )


TODAS = ca.Regras(
    alavancagem_maxima=3.0,
    cobertura_minima=2.0,
    caixa_minimo=2 * BI,
    taxa_da_divida_nova=0.15,
)


# --- as regras ------------------------------------------------------------------------------------
def test_cada_regra_pela_formula_e_a_menor_amarra():
    r = ca.calcular_capacidade(_insumos(), TODAS, DIA, "11222333000181")
    folgas = {f.regra: f for f in r.folgas}
    assert folgas[ca.ALAVANCAGEM].capacidade == pytest.approx(3.0 * 10 * BI - 15 * BI)
    assert folgas[ca.COBERTURA].capacidade == pytest.approx(
        (10 * BI / 2.0 - 2 * BI) / 0.15
    )
    assert folgas[ca.CAIXA_MINIMO].capacidade == pytest.approx((5 * BI - 2 * BI) / 0.15)
    assert (
        r.capacidade == pytest.approx(15 * BI) and r.regra_que_amarra == ca.ALAVANCAGEM
    )
    assert all(f.cumprida_hoje for f in r.folgas) and r.motivo == ""
    for folga in r.folgas:
        assert folga.rastro.formula == ca.FORMULAS[folga.regra]
        assert folga.rastro.versao_do_calculo == ca.VERSAO_DO_CALCULO
        assert folga.rastro.o_que_falta() == []


def test_so_as_regras_declaradas_entram_e_a_cobertura_pode_ser_pelo_ebit():
    so_cobertura = ca.Regras(
        cobertura_minima=2.0, base_da_cobertura="ebit", taxa_da_divida_nova=0.10
    )
    r = ca.calcular_capacidade(_insumos(), so_cobertura, DIA)
    assert [f.regra for f in r.folgas] == [ca.COBERTURA]
    assert r.capacidade == pytest.approx((8 * BI / 2.0 - 2 * BI) / 0.10)


def test_regra_ja_quebrada_hoje_nao_deixa_caber_nada():
    r = ca.calcular_capacidade(_insumos(liquida=40 * BI), TODAS, DIA)
    alavancagem = r.folgas[0]
    assert alavancagem.capacidade == 0 and alavancagem.cumprida_hoje is False
    assert r.capacidade == 0 and r.regra_que_amarra == ca.ALAVANCAGEM


def test_ebitda_negativo_nao_deixa_caber_nada_pela_alavancagem():
    regras = ca.Regras(alavancagem_maxima=3.0)
    r = ca.calcular_capacidade(_insumos(ebitda=-1 * BI, liquida=-5 * BI), regras, DIA)
    assert r.capacidade == 0 and r.folgas[0].motivo == ca.EBITDA_NAO_POSITIVO


def test_insumo_que_falta_fica_nao_observado_e_sem_capacidade():
    r = ca.calcular_capacidade(_insumos(despesa=None), TODAS, DIA)
    folgas = {f.regra: f for f in r.folgas}
    assert folgas[ca.COBERTURA].capacidade is None
    assert "despesa_financeira" in folgas[ca.COBERTURA].motivo
    assert folgas[ca.ALAVANCAGEM].capacidade is not None  # as outras continuam
    assert r.capacidade is None and r.regra_que_amarra is None
    assert "cobertura" in r.motivo


@pytest.mark.parametrize(
    "campos",
    [
        {},
        {"alavancagem_maxima": 0},
        {"cobertura_minima": -1, "taxa_da_divida_nova": 0.1},
        {"caixa_minimo": -1, "taxa_da_divida_nova": 0.1},
        {"cobertura_minima": 2},  # sem a taxa
        {"caixa_minimo": 1, "taxa_da_divida_nova": 0},
        {"alavancagem_maxima": 3, "base_da_cobertura": "lucro"},
    ],
)
def test_regras_invalidas_levantam_erro(campos):
    with pytest.raises(ValueError):
        ca.Regras(**campos)


def test_regras_e_resultado_viram_json():
    assert ca.Regras.de_dict(TODAS.como_dict()) == TODAS
    with pytest.raises(TypeError):
        ca.Regras.de_dict({"alavancagem": 3})
    r = ca.calcular_capacidade(_insumos(), TODAS, DIA)
    texto = json.dumps(r.como_dict())
    assert '"como_era_em": "2026-09-30"' in texto
    assert json.loads(texto)["regra_que_amarra"] == ca.ALAVANCAGEM


# --- sensibilidade --------------------------------------------------------------------------------
def test_tabela_de_sensibilidade_tem_uma_celula_por_par_de_choques():
    tabela = ca.tabela_de_sensibilidade(_insumos(), TODAS)
    assert len(tabela.celulas) == len(ca.CHOQUES_NO_EBITDA)
    assert all(len(linha) == len(ca.CHOQUES_NA_TAXA_EM_PB) for linha in tabela.celulas)
    sem_choque = tabela.celulas[ca.CHOQUES_NO_EBITDA.index(0.0)][
        ca.CHOQUES_NA_TAXA_EM_PB.index(0)
    ]
    assert (
        sem_choque.capacidade
        == ca.calcular_capacidade(_insumos(), TODAS, DIA).capacidade
    )
    menos_10 = tabela.celulas[ca.CHOQUES_NO_EBITDA.index(-0.10)][
        ca.CHOQUES_NA_TAXA_EM_PB.index(0)
    ]
    assert menos_10.capacidade == pytest.approx(3.0 * 9 * BI - 15 * BI)
    json.dumps(tabela.como_dict())


def test_choque_que_zera_a_taxa_fica_sem_numero():
    regras = ca.Regras(caixa_minimo=0, taxa_da_divida_nova=0.01)
    tabela = ca.tabela_de_sensibilidade(_insumos(), regras, (0.0,), (-100, -200))
    assert [c.capacidade for c in tabela.celulas[0]] == [None, None]
    assert tabela.celulas[0][0].motivo == ca.TAXA_NAO_POSITIVA


def test_choque_negativo_diminui_tambem_o_ebitda_negativo():
    menor = ca.com_choque_no_ebitda(_insumos(ebitda=-2 * BI, ebit=-3 * BI), -0.5)
    assert menor.ebitda.valor == -3 * BI and menor.ebit.valor == -4 * BI


reais = st.floats(-50 * BI, 50 * BI, allow_nan=False)
positivos = st.floats(0, 50 * BI, allow_nan=False)
insumos_gerados = st.builds(
    _insumos,
    ebitda=reais,
    ebit=reais,
    despesa=positivos,
    caixa=positivos,
    liquida=reais,
)
regras_geradas = st.builds(
    ca.Regras,
    alavancagem_maxima=st.floats(0.5, 8),
    cobertura_minima=st.floats(0.5, 8),
    base_da_cobertura=st.sampled_from(ca.BASES_DA_COBERTURA),
    caixa_minimo=positivos,
    taxa_da_divida_nova=st.floats(0.02, 0.4),
)
choques = st.floats(-0.9, 0.5, allow_nan=False)


def _capacidade(insumos: ca.Insumos, regras: ca.Regras, choque=0.0, pb=0) -> float:
    tabela = ca.tabela_de_sensibilidade(insumos, regras, (choque,), (pb,))
    capacidade = tabela.celulas[0][0].capacidade
    assert capacidade is not None and capacidade >= 0
    return capacidade


def _folga(valor: float) -> float:  # tolerância da conta em ponto flutuante
    return valor + 1e-6 * max(1.0, abs(valor))


@settings(max_examples=200, deadline=None)
@given(insumos_gerados, regras_geradas, choques, choques)
def test_capacidade_nao_sobe_quando_o_ebitda_cai(insumos, regras, a, b):
    menor, maior = sorted((a, b))
    assert _capacidade(insumos, regras, menor) <= _folga(
        _capacidade(insumos, regras, maior)
    )


@settings(max_examples=200, deadline=None)
@given(insumos_gerados, regras_geradas, st.integers(0, 500), st.integers(0, 500))
def test_capacidade_nao_sobe_quando_a_taxa_sobe(insumos, regras, a, b):
    menor, maior = sorted((a, b))
    assert _capacidade(insumos, regras, pb=maior) <= _folga(
        _capacidade(insumos, regras, pb=menor)
    )


@settings(max_examples=200, deadline=None)
@given(insumos_gerados, regras_geradas, st.floats(1, 3), st.floats(0, 1))
def test_capacidade_nao_cai_quando_a_regra_afrouxa(insumos, regras, mais, menos):
    frouxa = ca.Regras(
        alavancagem_maxima=(regras.alavancagem_maxima or 1) * mais,
        cobertura_minima=(regras.cobertura_minima or 1) / mais,
        base_da_cobertura=regras.base_da_cobertura,
        caixa_minimo=(regras.caixa_minimo or 0) * menos,
        taxa_da_divida_nova=regras.taxa_da_divida_nova,
    )
    assert _capacidade(insumos, regras) <= _folga(_capacidade(insumos, frouxa))


# --- os insumos das demonstrações reais -----------------------------------------------------------
@pytest.fixture(scope="module")
def banco(tmp_path_factory):
    """Um SQLite com as amostras gravadas (DFP 2024 e 2025, ITR 2026 e o cadastro)."""
    url = f"sqlite:///{(tmp_path_factory.mktemp('c') / 'c.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    with motor.begin() as c:
        repo.gravar_setores(
            c, dm.ler_setores((PASTA / "cad_cia_aberta.csv").read_bytes())
        )
        for arquivo, documento in (
            ("dfp_cia_aberta_2024.zip", "DFP"),
            ("dfp_cia_aberta_2025.zip", "DFP"),
            ("itr_cia_aberta_2026.zip", "ITR"),
        ):
            repo.gravar_demonstracoes(
                c, *dm.ler_demonstracoes((PASTA / arquivo).read_bytes(), documento)
            )
    yield motor
    motor.dispose()


def _dados(banco, cnpj):
    with banco.connect() as c:
        return repo.dados_da_empresa(c, cnpj)


def test_insumos_sao_os_numeros_da_ficha(banco):
    dados = _dados(banco, WEG)
    insumos = ca.insumos_das_demonstracoes(dados, DIA)
    ficha = fu.calcular(dados, preco=None)
    ttm, base, _ = fu.doze_meses(dados.contas)
    assert insumos.ebitda.valor == pytest.approx(ttm["ebit"] + ttm["depreciacao"])
    assert insumos.despesa_financeira.valor == pytest.approx(
        -ttm["despesas_financeiras"]
    )
    assert insumos.divida_liquida.valor == ficha["divida_liquida"].valor
    assert insumos.caixa.valor == ficha["caixa"].valor
    assert insumos.ebitda.periodo == base == "12 meses até 30/06/2026"
    assert insumos.caixa.rastro.formula == fu.FORMULAS["caixa"]
    assert [d.nome for d in insumos.caixa.rastro.documentos] == [
        "ITR de 30/06/2026, versão 1"
    ]
    assert {d.nome for d in insumos.ebitda.rastro.documentos} == {
        "DFP de 31/12/2025, versão 1",
        "ITR de 30/06/2026, versão 1",
    }


def test_como_era_em_nao_olha_o_futuro(banco):
    """WEG em 01/05/2026: o ITR de junho ainda não existia; vale o de março."""
    insumos = ca.insumos_das_demonstracoes(_dados(banco, WEG), date(2026, 5, 1))
    assert insumos.ebitda.periodo == "12 meses até 31/03/2026"
    for insumo in insumos.todos():
        assert insumo.rastro.publicado_em is not None
        assert insumo.rastro.publicado_em <= date(2026, 5, 1)


def test_cortar_o_futuro_nao_muda_o_passado(banco):
    dados, dia = _dados(banco, WEG), date(2026, 5, 1)
    cortadas = ca.demonstracoes_como_eram(dados, date(2026, 6, 1)).dados
    assert ca.insumos_das_demonstracoes(cortadas, dia) == ca.insumos_das_demonstracoes(
        dados, dia
    )


def test_reapresentado_depois_do_dia_fica_nao_observado(banco):
    """Petrobras: o ITR de março tem a versão 2, recebida em 11/05/2026; a 1ª não está guardada."""
    insumos = ca.insumos_das_demonstracoes(_dados(banco, PETROBRAS), date(2026, 5, 1))
    assert all(i.valor is None for i in insumos.todos())
    assert "ITR de 31/03/2026" in insumos.ebitda.motivo
    depois = ca.insumos_das_demonstracoes(_dados(banco, PETROBRAS), date(2026, 5, 20))
    assert (
        depois.ebitda.valor is not None
        and depois.ebitda.periodo == "12 meses até 31/03/2026"
    )


def test_antes_de_qualquer_documento_nada_e_observado(banco):
    insumos = ca.insumos_das_demonstracoes(_dados(banco, WEG), date(2025, 1, 1))
    assert all(i.valor is None and i.motivo for i in insumos.todos())


def test_banco_nao_tem_capacidade_por_estas_regras(banco):
    insumos = ca.insumos_das_demonstracoes(_dados(banco, ITAU), DIA)
    assert all(i.motivo == fu.NAO_SE_APLICA_A_FINANCEIRAS for i in insumos.todos())


def test_capacidade_do_emissor_pelo_banco(banco):
    with banco.connect() as c:
        r = ca.capacidade_do_emissor(c, "84429695000111", TODAS, DIA)
    assert r.emissor_cnpj == "84429695000111" and r.capacidade is not None
    assert r.rastro.publicado_em is not None and r.rastro.publicado_em <= DIA
    with banco.connect() as c, pytest.raises(ValueError):
        ca.capacidade_do_emissor(c, "123", TODAS, DIA)
