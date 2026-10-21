"""Features de crédito da base, pela porta (B-30, parte 2): PGFN, situação especial, insolvência e IPE.

Tabelas de mentira (`extras` da porta) com datas escolhidas: o que conta é o dia em que cada linha ficou
pública (a PGFN e a Receita, pelo último dia do mês, como a porta lê). Por propriedade: tirar da
base as linhas publicadas depois de um corte não muda as features de nenhum dia antes dele."""

import random
from datetime import date, timedelta

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import cnpj as cnpj_
from base.porta import Porta
from src.credito import features as fc
from src.credito import features_da_base as fb
from src.credito.dicionario import DA_BASE, DAS_DEMONSTRACOES, DICIONARIO

EMPRESA, OUTRA, MEI, NOVA = (
    "84429695000111",
    "33000167000101",
    "44555666000199",
    "11222333000181",
)


def _formatado(cnpj: str) -> str:
    return cnpj_.formatar(cnpj)


def _pgfn(
    cnpj,
    retrato,
    visto,
    devedor="principal",
    ajuizado=False,
    inscricoes=1,
    valor=100.0,
    pessoa=False,
    tipo="nao_previdenciaria",
) -> dict:
    return {"cnpj": _formatado(cnpj), "cnpj_basico": cnpj[:8], "tipo_divida": tipo, "regiao": "1",
            "tipo_devedor": devedor, "tipo_situacao": "Em cobrança", "situacao_inscricao": "ATIVA",
            "ajuizado": ajuizado, "inscricoes": inscricoes, "valor_consolidado": valor,
            "data_do_retrato": pd.Timestamp(retrato), "trata_como_pessoa": pessoa,
            "disponivel_em": pd.Timestamp(visto)}  # fmt: skip


def _situacao(cnpj, mes, visto, rotulo, matriz=True) -> dict:
    return {"cnpj": _formatado(cnpj), "cnpj_basico": cnpj[:8], "matriz": matriz,
            "situacao_especial": rotulo.upper(), "rotulo": rotulo,
            "data_situacao_especial": pd.Timestamp("2026-01-01"), "mes_do_retrato": mes,
            "disponivel_em": pd.Timestamp(visto)}  # fmt: skip


def _insolvencia(cnpj, protocolo, versao, rotulo, conhecido_em) -> dict:
    return {"cnpj": _formatado(cnpj), "empresa": "X", "rotulo": rotulo, "evento": rotulo,
            "regra": "categoria_ipe", "evidencia": "categoria_ipe", "categoria": "c", "tipo": "",
            "assunto": "", "conhecido_em": pd.Timestamp(conhecido_em),
            "referencia": pd.Timestamp(conhecido_em), "protocolo": protocolo, "versao": versao,
            "link": f"https://cvm/{protocolo}"}  # fmt: skip


def _evento(cnpj, protocolo, rotulo, tema, publicado_em) -> dict:
    return {"protocolo": protocolo, "versao": 1, "cnpj": _formatado(cnpj), "empresa": "X",
            "categoria": rotulo, "tipo": "", "assunto": "", "rotulo": rotulo, "tema": tema,
            "materialidade": 50, "referencia": pd.Timestamp(publicado_em),
            "publicado_em": pd.Timestamp(publicado_em), "link": f"https://cvm/{protocolo}"}  # fmt: skip


PGFN = [
    _pgfn(
        EMPRESA, "2026-06-30", "2026-07-23", ajuizado=True, inscricoes=2, valor=1000.0
    ),
    _pgfn(EMPRESA, "2026-06-30", "2026-07-23", inscricoes=1, valor=500.0, tipo="fgts"),
    _pgfn(EMPRESA, "2026-06-30", "2026-07-23", devedor="corresponsavel", valor=9999.0),
    _pgfn(
        EMPRESA, "2026-09-30", "2026-10-14", ajuizado=True, inscricoes=3, valor=3000.0
    ),
    _pgfn(OUTRA, "2026-09-30", "2026-10-14", valor=50.0),
    _pgfn(MEI, "2026-09-30", "2026-10-14", valor=70.0, pessoa=True),
]
SITUACAO = [
    _situacao(EMPRESA, "2026-08", "2026-09-12", "recuperacao_judicial"),
    _situacao(EMPRESA, "2026-08", "2026-09-12", "recuperacao_judicial", matriz=False),
    _situacao(OUTRA, "2026-08", "2026-09-12", "falencia"),
]
INSOLVENCIA = [
    _insolvencia(EMPRESA, "P1", 1, "recuperacao_judicial", "2025-03-10"),
    _insolvencia(EMPRESA, "P1", 2, "recuperacao_judicial", "2025-04-01"),
    _insolvencia(EMPRESA, "P2", 1, "exposicao_a_terceiro", "2025-06-01"),
    _insolvencia(EMPRESA, "P3", 1, "falencia", "2026-09-01"),
]
EVENTOS = [
    _evento(EMPRESA, "P1", "Fato relevante", "eventos", "2025-03-10"),
    _evento(EMPRESA, "E2", "Fato relevante", "eventos", "2026-02-01"),
    _evento(EMPRESA, "E3", "Rating", "risco", "2026-05-05"),
    _evento(EMPRESA, "E4", "Comunicado ao mercado", "eventos", "2026-06-01"),
    _evento(OUTRA, "E5", "Comunicado ao mercado", "eventos", "2026-06-01"),
]
TABELAS = {
    "pgfn_divida": PGFN,
    "cnpj_situacao_especial": SITUACAO,
    "insolvencia": INSOLVENCIA,
    "eventos": EVENTOS,
}
# o dia em que cada tabela fica pública (a PGFN e a Receita valem pelo último dia do mês)
PUBLICO_EM = {
    "pgfn_divida": lambda linha: linha["disponivel_em"] + pd.offsets.MonthEnd(0),
    "cnpj_situacao_especial": lambda linha: (
        linha["disponivel_em"] + pd.offsets.MonthEnd(0)
    ),
    "insolvencia": lambda linha: linha["conhecido_em"],
    "eventos": lambda linha: linha["publicado_em"],
}


def _porta(pasta, corte: date | None = None, sem: tuple[str, ...] = ()) -> Porta:
    """A porta com as tabelas acima (com `corte`, só o que era público até ele)."""
    extras = {}
    for nome, linhas in TABELAS.items():
        if nome in sem:
            continue
        tabela = pd.DataFrame(linhas)
        if corte is not None:
            tabela = tabela[
                [PUBLICO_EM[nome](x).date() <= corte for _, x in tabela.iterrows()]
            ]
        extras[nome] = tabela
    return Porta(pasta, arquivos={}, conferidas={}, extras=extras)


@pytest.fixture
def porta(tmp_path):
    with _porta(tmp_path) as p:
        yield p


def _da_base(porta, cnpj, dia) -> dict[str, fc.Feature]:
    return {f.chave: f for f in fb.features_da_base(porta, cnpj, dia)}


# --- PGFN -----------------------------------------------------------------------------------------
def test_pgfn_soma_o_devedor_principal_do_retrato_mais_novo_publico(porta):
    f = _da_base(porta, EMPRESA, date(2026, 8, 15))
    assert f["divida_ativa_da_uniao"].valor == 1500.0  # sem os 9.999 de corresponsável
    assert f["divida_ativa_ajuizada"].valor == 1000.0
    assert f["inscricoes_em_divida_ativa"].valor == 3
    assert f["divida_ativa_da_uniao"].disponivel_em == date(2026, 7, 31)
    assert f["divida_ativa_da_uniao"].periodo == "retrato de 30/06/2026"
    assert f["divida_ativa_da_uniao"].rastro.fonte_id == "pgfn"


def test_pgfn_vale_pelo_fim_do_mes_em_que_foi_vista(porta):
    """O retrato de setembro foi visto em 14/10: só vale a partir de 31/10."""
    assert (
        _da_base(porta, EMPRESA, date(2026, 10, 20))["divida_ativa_da_uniao"].valor
        == 1500.0
    )
    assert (
        _da_base(porta, EMPRESA, date(2026, 11, 1))["divida_ativa_da_uniao"].valor
        == 3000.0
    )


def test_empresa_fora_do_retrato_tem_zero_e_antes_do_retrato_nao_observado(porta):
    f = _da_base(porta, NOVA, date(2026, 11, 1))
    assert f["divida_ativa_da_uniao"].valor == 0.0
    assert f["divida_ativa_da_uniao"].disponivel_em == date(2026, 10, 31)
    antes = _da_base(porta, EMPRESA, date(2026, 7, 15))["divida_ativa_da_uniao"]
    assert antes.valor is None and antes.disponivel_em is None
    assert antes.motivo == fb.SEM_RETRATO.format(fonte="PGFN")


def test_mei_nao_sai_da_base(porta):
    f = _da_base(porta, MEI, date(2026, 11, 1))
    for chave in (
        "divida_ativa_da_uniao",
        "divida_ativa_ajuizada",
        "inscricoes_em_divida_ativa",
    ):
        assert f[chave].valor is None and f[chave].motivo == fb.COMO_PESSOA


# --- situação especial na Receita -----------------------------------------------------------------
def test_situacao_especial_do_retrato_publico(porta):
    f = _da_base(porta, EMPRESA, date(2026, 10, 1))["situacao_especial_na_receita"]
    assert f.valor == "recuperacao_judicial" and f.disponivel_em == date(2026, 9, 30)
    assert f.periodo == "retrato de 2026-08"
    fora = _da_base(porta, NOVA, date(2026, 10, 1))["situacao_especial_na_receita"]
    assert fora.valor == fb.NENHUMA and fora.disponivel_em == date(2026, 9, 30)
    antes = _da_base(porta, EMPRESA, date(2026, 9, 29))["situacao_especial_na_receita"]
    assert antes.valor is None and antes.motivo == fb.SEM_RETRATO.format(
        fonte="Receita"
    )


# --- IPE: insolvência e eventos -------------------------------------------------------------------
def test_insolvencia_conta_so_a_da_propria_e_cada_entrega_uma_vez(porta):
    f = _da_base(porta, EMPRESA, date(2026, 8, 1))
    assert (
        f["eventos_de_insolvencia"].valor == 1
    )  # P1 em duas versões; P2 é de terceiro
    assert f["ultimo_evento_de_insolvencia"].valor == "recuperacao_judicial"
    assert f["eventos_de_insolvencia"].disponivel_em == date(2025, 4, 1)
    depois = _da_base(porta, EMPRESA, date(2026, 9, 2))
    assert depois["eventos_de_insolvencia"].valor == 2
    assert depois["ultimo_evento_de_insolvencia"].valor == "falencia"


def test_eventos_dos_ultimos_12_meses(porta):
    f = _da_base(porta, EMPRESA, date(2026, 8, 1))
    assert (
        f["fatos_relevantes_12_meses"].valor == 1
    )  # o de 10/03/2025 ficou fora da janela
    assert f["ratings_12_meses"].valor == 1
    assert f["fatos_relevantes_12_meses"].periodo == "12 meses até 01/08/2026"
    assert [d.url for d in f["ratings_12_meses"].rastro.documentos] == [
        "https://cvm/E3"
    ]


def test_sem_fato_na_janela_e_zero_com_a_data_do_ultimo_documento(porta):
    f = _da_base(porta, OUTRA, date(2026, 8, 1))
    assert f["fatos_relevantes_12_meses"].valor == 0
    assert f["eventos_de_insolvencia"].valor == 0
    assert f["ultimo_evento_de_insolvencia"].valor == fb.NENHUM
    assert f["fatos_relevantes_12_meses"].disponivel_em == date(2026, 6, 1)


def test_quem_nao_entrega_a_cvm_fica_nao_observado(porta):
    f = _da_base(porta, NOVA, date(2026, 8, 1))
    for chave in (
        "eventos_de_insolvencia",
        "ultimo_evento_de_insolvencia",
        "ratings_12_meses",
    ):
        assert f[chave].valor is None and f[chave].motivo == fb.SEM_IPE


def test_tabela_que_falta_na_base_fica_nao_observada(tmp_path):
    with _porta(tmp_path, sem=("pgfn_divida", "eventos")) as p:
        f = _da_base(p, EMPRESA, date(2026, 11, 1))
    assert f["divida_ativa_da_uniao"].motivo == fb.SEM_A_TABELA.format(
        tabela="pgfn_divida"
    )
    assert f["fatos_relevantes_12_meses"].motivo == fb.SEM_A_TABELA.format(
        tabela="eventos"
    )
    assert f["eventos_de_insolvencia"].valor == 2  # a insolvência ainda está lá


def test_toda_feature_da_base_tem_a_formula_do_dicionario(porta):
    features = fb.features_da_base(porta, EMPRESA, date(2026, 11, 1))
    assert [f.chave for f in features] == list(DA_BASE)
    for f in features:
        assert f.rastro.formula == DICIONARIO[f.chave].formula
        if f.valor is not None:
            assert f.rastro.o_que_falta() == [], f.chave


def test_cnpj_invalido(porta):
    with pytest.raises(ValueError):
        fb.features_da_base(porta, "123", date(2026, 11, 1))


def test_features_de_credito_juntam_demonstracoes_e_base(porta):
    from tests.test_credito_features import _demonstracoes_sinteticas

    dados = _demonstracoes_sinteticas(random.Random(1))
    f = fb.features_de_credito(dados, porta, EMPRESA, date(2026, 11, 1))
    assert [x.chave for x in f.features] == [*DAS_DEMONSTRACOES, *DA_BASE]
    assert f.cnpj == EMPRESA
    fc.conferir_ponto_no_tempo(f.features, date(2026, 11, 1))


# --- por propriedade: cortar o futuro não muda o passado ------------------------------------------
@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    return tmp_path_factory.mktemp("base")


@settings(max_examples=40, deadline=None)
@given(
    st.dates(date(2025, 1, 1), date(2027, 1, 31)),
    st.integers(0, 500),
    st.sampled_from([EMPRESA, OUTRA, MEI, NOVA]),
)
def test_cortar_o_futuro_nao_muda_o_passado(pasta, dia, dias_a_mais, cnpj):
    with (
        _porta(pasta) as completa,
        _porta(pasta, dia + timedelta(days=dias_a_mais)) as cortada,
    ):
        features = fb.features_da_base(completa, cnpj, dia)
        assert fb.features_da_base(cortada, cnpj, dia) == features
    fc.conferir_ponto_no_tempo(features, dia)
