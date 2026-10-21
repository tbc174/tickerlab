"""Cenários de curva e covenants preliminares do simulador (B-23 do dossiê da plataforma, protótipo B).

Os choques e os covenants com contas de cabeça (gabarito à mão); a sensibilidade monotônica dos
juros ao choque paralelo por propriedade (Hypothesis)."""

import json
from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.divida import capacidade as ca
from src.divida import cenarios as ce
from src.divida import covenants as co
from src.divida import curva_do_dia as cd
from src.divida import simulador as si
from src.rastro import DocumentoUsado, Rastro

DIA = date(2026, 9, 30)
BI = 1e9
NOMINAL = ((0.5, 0.11), (1.0, 0.115), (2.0, 0.12))
IMPLICITA = ((0.5, 0.045), (1.0, 0.047), (2.0, 0.05))
DFP = DocumentoUsado("DFP de mentira", date(2026, 3, 1))


def _curva(nominal=NOMINAL, implicita=IMPLICITA) -> cd.CurvaDoDia:
    return cd.CurvaDoDia(
        date(2026, 9, 29),
        DIA,
        nominal,
        implicita,
        cd.rastro_da_curva(date(2026, 9, 29), DIA),
    )


def _taxas(vertices: tuple[tuple[float, float], ...]) -> list[float]:
    return [taxa for _, taxa in vertices]


# --- os choques na curva -------------------------------------------------------------------------
def test_choque_paralelo_soma_o_mesmo_a_todos_os_vertices():
    chocada = ce.com_choque(_curva(), ce.CenarioDeCurva("x", paralelo_pb=100))
    assert _taxas(chocada.nominal) == pytest.approx([0.12, 0.125, 0.13])
    assert _taxas(chocada.implicita) == pytest.approx([0.055, 0.057, 0.06])
    assert chocada.data_base == _curva().data_base


def test_inclinacao_gira_a_curva_em_volta_do_vertice_mais_curto():
    chocada = ce.com_choque(_curva(), ce.CenarioDeCurva("x", inclinacao_pb=150))
    # 0,5 ano: nada; 1 ano: (1 − 0,5) ÷ (2 − 0,5) = 1/3 de 150 pb; 2 anos: 150 pb
    assert _taxas(chocada.nominal) == pytest.approx([0.11, 0.12, 0.135])
    assert [p for p, _ in chocada.nominal] == [0.5, 1.0, 2.0]


def test_choque_que_deixa_a_taxa_impossivel_e_recusado():
    with pytest.raises(ValueError, match="−100%"):
        ce.com_choque(_curva(), ce.CenarioDeCurva("x", paralelo_pb=-20_000))


def test_cenarios_do_cdi_mudam_os_juros_na_direcao_do_choque():
    instrumento = si.Instrumento(
        1_000_000, si.CDI, 0.015, 24, si.SAC, meses_por_periodo=3
    )
    tabela = ce.tabela_de_cenarios(instrumento, _curva(), DIA)
    juros = {r.cenario.nome: r.total_de_juros for r in tabela.resultados}
    assert juros["+100 pb"] > juros["curva do dia"] > juros["−100 pb"]
    assert juros["mais inclinada (+100 pb no longo)"] > juros["curva do dia"]
    assert tabela.aviso == ""
    base = tabela.resultados[0]
    assert base.simulacao == si.simular(instrumento, _curva(), DIA)
    assert base.maior_parcela == max(p.parcela for p in base.simulacao.periodos)
    assert base.rastro.fonte_id == "tesouro-br-direto"
    assert base.rastro.o_que_falta() == []


def test_cenarios_do_pre_dao_o_mesmo_fluxo_e_avisam():
    instrumento = si.Instrumento(1_000_000, si.PRE, 0.12, 12, si.PRICE)
    tabela = ce.tabela_de_cenarios(instrumento, _curva(), DIA)
    assert len({r.simulacao.periodos for r in tabela.resultados}) == 1
    assert tabela.aviso == ce.PRE_NAO_USA_A_CURVA
    sem_curva = ce.tabela_de_cenarios(instrumento, None, DIA)
    assert sem_curva.resultados[0].rastro.fonte_id == si.FONTE_DOS_TERMOS


def test_cenario_que_passa_da_curva_continua_sem_extrapolar():
    instrumento = si.Instrumento(
        1_000_000, si.IPCA, 0.06, 36, si.SAC, meses_por_periodo=12
    )
    with pytest.raises(cd.ForaDaCurva):
        ce.tabela_de_cenarios(instrumento, _curva(), DIA)


def test_tabela_de_cenarios_vira_json():
    instrumento = si.Instrumento(1_000, si.IPCA, 0.06, 12, si.SAC)
    dados = json.loads(
        json.dumps(ce.tabela_de_cenarios(instrumento, _curva(), DIA).como_dict())
    )
    assert [r["cenario"]["nome"] for r in dados["resultados"]] == [
        c.nome for c in ce.CENARIOS_PADRAO
    ]


@settings(max_examples=150, deadline=None)
@given(
    st.sampled_from(si.AMORTIZACOES),
    st.sampled_from((si.CDI, si.IPCA)),
    st.integers(-300, 300),
    st.integers(1, 300),
)
def test_juros_sobem_com_o_choque_paralelo(amortizacao, indexador, choque, passo):
    """Mais curva, mais juros (e correção): a sensibilidade é monotônica."""
    instrumento = si.Instrumento(
        1_000_000, indexador, 0.02, 24, amortizacao, meses_por_periodo=3
    )
    menor, maior = ce.tabela_de_cenarios(
        instrumento,
        _curva(),
        DIA,
        [
            ce.CenarioDeCurva("a", paralelo_pb=choque),
            ce.CenarioDeCurva("b", paralelo_pb=choque + passo),
        ],
    ).resultados
    assert (
        maior.total_de_juros + maior.total_de_correcao
        > menor.total_de_juros + menor.total_de_correcao
    )


# --- covenants preliminares ----------------------------------------------------------------------
RASTRO_DA_DFP = Rastro.dos_documentos("x", "x", "cvm", [DFP])


def _insumos(
    ebitda=10 * BI, liquida=15 * BI, despesa=2 * BI, ebit=8 * BI
) -> ca.Insumos:
    def insumo(chave: str, valor: float | None) -> ca.Insumo:
        return ca.Insumo(chave, chave.capitalize(), valor, "12 meses", RASTRO_DA_DFP)

    return ca.Insumos(
        ebitda=insumo("ebitda", ebitda),
        ebit=insumo("ebit", ebit),
        despesa_financeira=insumo("despesa_financeira", despesa),
        divida_bruta=insumo("divida_bruta", 20 * BI),
        caixa=insumo("caixa", 5 * BI),
        divida_liquida=insumo("divida_liquida", liquida),
    )


REGRAS = ca.Regras(
    alavancagem_maxima=1.8, cobertura_minima=3.0, taxa_da_divida_nova=0.10
)


def test_covenants_do_bullet_anual_batem_com_a_conta_de_cabeca():
    """Bullet pré de 5 bi a 10% em 2 anos: ano 1, (15 + 5) ÷ 10 = 2,0 e 10 ÷ (2 + 0,5) = 4,0;
    ano 2, a dívida nova já foi paga: 15 ÷ 10 = 1,5 e a cobertura ainda conta os juros do ano."""
    instrumento = si.Instrumento(
        5 * BI, si.PRE, 0.10, 24, si.BULLET, meses_por_periodo=12
    )
    simulacao = si.simular(instrumento, None, DIA)
    resultado = co.covenants_preliminares(simulacao, _insumos(), REGRAS)
    um, dois = resultado.anos
    assert (um.saldo_da_divida_nova, um.despesa_da_divida_nova) == pytest.approx(
        (5 * BI, 0.5 * BI)
    )
    assert (um.alavancagem.valor, um.alavancagem.cumpre) == (pytest.approx(2.0), False)
    assert (um.cobertura.valor, um.cobertura.cumpre) == (pytest.approx(4.0), True)
    assert (dois.alavancagem.valor, dois.alavancagem.cumpre) == (
        pytest.approx(1.5),
        True,
    )
    assert dois.cobertura.valor == pytest.approx(4.0)
    assert um.alavancagem.limite == 1.8
    assert um.cobertura.limite == 3.0


def test_covenants_do_ipca_contam_a_correcao_como_despesa():
    instrumento = si.Instrumento(
        1 * BI, si.IPCA, 0.06, 12, si.BULLET, meses_por_periodo=12
    )
    simulacao = si.simular(instrumento, _curva(), DIA)
    (ano,) = co.covenants_preliminares(simulacao, _insumos(), REGRAS).anos
    periodo = simulacao.periodos[0]
    assert ano.despesa_da_divida_nova == pytest.approx(
        periodo.juros + periodo.correcao_monetaria
    )
    assert ano.cobertura.valor == pytest.approx(
        10 * BI / (2 * BI + ano.despesa_da_divida_nova)
    )


def test_ultimo_ano_curto_vai_ate_o_ultimo_mes():
    instrumento = si.Instrumento(1 * BI, si.PRE, 0.1, 18, si.SAC, meses_por_periodo=6)
    anos = co.covenants_preliminares(
        si.simular(instrumento, None, DIA), _insumos(), REGRAS
    ).anos
    assert [(a.ano, a.ate_o_mes) for a in anos] == [(1, 12), (2, 18)]
    assert anos[-1].saldo_da_divida_nova == 0.0


def test_regra_nao_declarada_projeta_sem_dizer_se_cumpre():
    regras = ca.Regras(alavancagem_maxima=3.0)
    instrumento = si.Instrumento(1 * BI, si.PRE, 0.1, 12, si.SAC)
    (ano,) = co.covenants_preliminares(
        si.simular(instrumento, None, DIA), _insumos(), regras
    ).anos
    assert ano.cobertura.valor is not None
    assert (ano.cobertura.limite, ano.cobertura.cumpre) == (None, None)


@pytest.mark.parametrize(
    ("insumos", "motivo_da_alavancagem", "motivo_da_cobertura"),
    [
        (_insumos(ebitda=None), "Falta ebitda", "Falta ebitda"),
        (_insumos(ebitda=-1 * BI), "EBITDA negativo", ""),
        (_insumos(liquida=None), "Falta divida_liquida", ""),
        (_insumos(despesa=None), "", "Falta despesa_financeira"),
    ],
)
def test_insumo_que_falta_fica_nao_observado(
    insumos, motivo_da_alavancagem, motivo_da_cobertura
):
    instrumento = si.Instrumento(1 * BI, si.PRE, 0.1, 12, si.SAC)
    (ano,) = co.covenants_preliminares(
        si.simular(instrumento, None, DIA), insumos, REGRAS
    ).anos
    for indicador, motivo in (
        (ano.alavancagem, motivo_da_alavancagem),
        (ano.cobertura, motivo_da_cobertura),
    ):
        if motivo:
            assert indicador.valor is None
            assert indicador.cumpre is None
            assert indicador.motivo.startswith(motivo)
        else:
            assert indicador.valor is not None


def test_covenants_tem_rastro_da_cvm_e_da_curva_e_viram_json():
    instrumento = si.Instrumento(1 * BI, si.CDI, 0.015, 12, si.SAC, meses_por_periodo=3)
    resultado = co.covenants_preliminares(
        si.simular(instrumento, _curva(), DIA), _insumos(), REGRAS
    )
    rastro = resultado.anos[0].alavancagem.rastro
    assert rastro.fonte_id == "cvm"
    assert rastro.outras_fontes == ("tesouro-br-direto",)
    assert {d.nome for d in rastro.documentos} == {
        DFP.nome,
        _curva().rastro.documentos[0].nome,
    }
    assert rastro.publicado_em == DIA  # o insumo mais novo: a curva
    assert rastro.o_que_falta() == []
    dados = json.loads(json.dumps(resultado.como_dict()))
    assert dados["anos"][0]["alavancagem"]["limite"] == 1.8
