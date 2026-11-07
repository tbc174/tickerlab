"""A ficha de crédito por CNPJ (linha 754): fatos, regras do papel, sem pessoa, sem nota, sem futuro.

As três empresas do exemplo de tokenização (reports/tokenizacao-exemplo-mundial-2026-11-06.md): a
Mundial como cedente, a RD como sacado forte e o GPA como sacado em recuperação extrajudicial, com as
tabelas de mentira de `test_credito_sinais`.
"""

import random
from datetime import date, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.credito import elegibilidade as el
from src.credito import features_da_base as fb
from src.credito import ficha as fi
from src.credito.dicionario import DA_BASE, DA_FICHA, DAS_DEMONSTRACOES
from src.credito.dossie import NotaNoDossieError
from src.credito.features import conferir_ponto_no_tempo
from tests.test_credito_features import _demonstracoes_sinteticas
from tests.test_credito_sinais import DIA, GPA, MEI, MUNDIAL, NOVA, RD, _porta


@pytest.fixture
def porta(tmp_path):
    with _porta(tmp_path) as p:
        yield p


def _regra(ficha, chave):
    return next(regra for regra in ficha.regras if regra.chave == chave)


def test_a_ficha_tem_os_fatos_da_base_e_os_sinais_na_ordem(porta):
    ficha = fi.ficha_de_credito(porta, MUNDIAL, el.CEDENTE, DIA)
    assert [fato.chave for fato in ficha.fatos] == [*DA_BASE, *DA_FICHA]
    assert ficha.cnpj == MUNDIAL
    assert ficha.limites == fi.LIMITES_DA_FICHA


def test_com_as_demonstracoes_os_fatos_delas_vem_primeiro(porta):
    dados = _demonstracoes_sinteticas(random.Random(3))
    ficha = fi.ficha_de_credito(porta, RD, el.SACADO, DIA, dados=dados)
    assert [fato.chave for fato in ficha.fatos] == [
        *DAS_DEMONSTRACOES,
        *DA_BASE,
        *DA_FICHA,
    ]


def test_gpa_como_sacado_e_inelegivel_pela_re_e_a_rd_nao(porta):
    gpa = fi.ficha_de_credito(porta, GPA, el.SACADO, DIA)
    regra = _regra(gpa, "insolvencia_nos_ultimos_24_meses")
    assert (regra.resultado, regra.efeito, regra.valor) == (el.ACIONA, el.INELEGIVEL, 3)
    assert regra in gpa.acionadas()
    rd = fi.ficha_de_credito(porta, RD, el.SACADO, DIA)
    assert _regra(rd, "insolvencia_nos_ultimos_24_meses").resultado == el.NAO_ACIONA


def test_companhia_sem_ipe_nao_da_para_saber_da_insolvencia(porta):
    nova = fi.ficha_de_credito(porta, NOVA, el.SACADO, DIA)
    regra = _regra(nova, "insolvencia_nos_ultimos_24_meses")
    assert regra.resultado == el.NAO_DA_PARA_SABER
    assert regra.motivo == fb.SEM_IPE
    assert nova.lacunas()["insolvencia_24_meses"] == fb.SEM_IPE


def test_a_mundial_como_cedente_tem_os_fundos_e_a_regra_do_fundo(porta):
    ficha = fi.ficha_de_credito(porta, MUNDIAL, el.CEDENTE, DIA)
    assert ficha["fundos_em_que_cede"].valor == 2
    regra = _regra(ficha, "fundo_do_cedente_com_inadimplencia_alta")
    assert (
        regra.resultado == el.ACIONA
    )  # o informe de 08/2026 do Marfim: 4,4 mi de 6,3 mi
    como_sacado = fi.ficha_de_credito(porta, MUNDIAL, el.SACADO, DIA)
    assert "fundo_do_cedente_com_inadimplencia_alta" not in {
        r.chave for r in como_sacado.regras
    }


def test_tabela_que_falta_vira_lacuna_e_nao_da_para_saber(tmp_path):
    with _porta(tmp_path, sem=("cnpj_situacao_cadastral",)) as porta:
        ficha = fi.ficha_de_credito(porta, RD, el.SACADO, DIA)
    motivo = fb.SEM_A_TABELA.format(tabela="cnpj_situacao_cadastral")
    assert ficha.lacunas()["situacao_cadastral_na_receita"] == motivo
    assert (
        _regra(ficha, "cnpj_fora_da_situacao_ativa").resultado == el.NAO_DA_PARA_SABER
    )


def test_mei_nao_tem_fato_nenhum(porta):
    ficha = fi.ficha_de_credito(porta, MEI, el.SACADO, DIA)
    assert all(
        fato.valor is None and fato.motivo == fb.COMO_PESSOA for fato in ficha.fatos
    )
    assert all(not fato.rastro.documentos for fato in ficha.fatos)
    assert {regra.resultado for regra in ficha.regras} == {el.NAO_DA_PARA_SABER}


def test_papel_desconhecido_e_recusado(porta):
    with pytest.raises(el.PapelDesconhecidoError):
        fi.ficha_de_credito(porta, RD, "avalista", DIA)


def test_ficha_com_palavra_vedada_ou_chave_de_nota_falha(porta, monkeypatch):
    regra = el.REGRAS[0]
    monkeypatch.setattr(el, "REGRAS", (el.Regra("nota_do_sacado", *[getattr(regra, c) for c in (
        "texto", "sinal", "aciona_quando", "para_o_cedente", "para_o_sacado")]),))  # fmt: skip
    with pytest.raises(NotaNoDossieError):
        fi.ficha_de_credito(porta, RD, el.SACADO, DIA)


def test_como_dict_so_tem_tipos_simples(porta):
    dicionario = fi.ficha_de_credito(porta, GPA, el.SACADO, DIA).como_dict()
    assert dicionario["data_da_analise"] == DIA.isoformat()
    assert dicionario["papel"] == el.SACADO
    assert {"chave", "valor", "disponivel_em", "motivo"} <= set(dicionario["fatos"][0])
    assert isinstance(dicionario["regras"][0]["resultado"], str)


@settings(max_examples=10, deadline=None)
@given(
    dia=st.dates(date(2025, 6, 1), date(2027, 3, 31)),
    folga=st.integers(0, 400),
    cnpj=st.sampled_from([MUNDIAL, RD, GPA, NOVA]),
    papel=st.sampled_from(el.PAPEIS),
)
def test_cortar_o_que_ficou_publico_depois_nao_muda_a_ficha(
    tmp_path_factory, dia, folga, cnpj, papel
):
    pasta = tmp_path_factory.mktemp("ficha")
    with (
        _porta(pasta) as inteira,
        _porta(pasta, corte=dia + timedelta(days=folga)) as cortada,
    ):
        completa = fi.ficha_de_credito(inteira, cnpj, papel, dia)
        sem_o_futuro = fi.ficha_de_credito(cortada, cnpj, papel, dia)
    conferir_ponto_no_tempo(completa.fatos, dia)
    assert completa == sem_o_futuro
