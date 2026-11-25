"""Quem já se mexeu num setor conta a entrada em empresa que depois foi baixada (linha 1042).

Consolidador que incorpora o que compra faz a empresa sumir do retrato ativo da Receita; antes, a entrada nela não
contava e o histórico dele sumia da lista. A base de mentira é a de `test_api_externa_compradores` (a COMPRADORA entrou
em 2025-03-10 na ALVO_SP, na BAIXADA e numa empresa de fora do setor). Riscos: contar o que não é do setor (fora do
CNAE ou da UF), contar fundador e entrada do mesmo grupo, olhar o futuro e mudar a conta de empresas ativas.
"""
# ruff: noqa: F811  (a fixture `pasta` vem do arquivo do buyers e se repete nos argumentos)

from datetime import date

import pandas as pd
import pytest

from base.porta import Porta
from src.api_externa.conjuntos import compradores
from tests.test_api_externa_compradores import (
    ALVO_SP,
    BAIXADA,
    COMPRADORA,
    FORA,
    HOLDING,
    IRMA,
    NOMES,
    SETOR,
    _entradas,
    _estabelecimentos,
    _gravar,
    pasta,  # noqa: F401  (fixture reaproveitada)
)

HOJE = date(2026, 11, 10)
OUTRA_BAIXADA, BAIXADA_DE_OUTRO_SETOR, BAIXADA_DO_RJ = (
    "15000001",
    "15000002",
    "15000003",
)


@pytest.fixture(autouse=True)
def _cache_limpo():
    compradores.zerar_o_cache()
    yield
    compradores.zerar_o_cache()


def _lista(pasta, cnae=SETOR, uf=None, anos=3):
    leitor = compradores.LeitorDeCompradores(Porta(pasta), lambda *_: True, 50)
    servido = leitor.compradores(
        compradores.PedidoDeCompradores(cnae, uf, anos, 50), HOJE
    )
    assert servido is not None
    return servido.corpo


def _comprador(corpo, raiz):
    (achado,) = [c for c in corpo["compradores"] if c["raiz_do_cnpj"] == raiz]
    return achado


def test_a_entrada_em_empresa_baixada_conta(pasta):
    corpo = _lista(pasta)
    entradas = _comprador(corpo, COMPRADORA)["provas"][compradores.ENTROU]
    empresas = {e["empresa_do_setor"]["raiz_do_cnpj"] for e in entradas["exemplos"]}
    assert (
        entradas["quantas"] == 2
    )  # a ALVO_SP e a BAIXADA; a de fora do setor não conta
    assert empresas == {ALVO_SP, BAIXADA}


def test_quem_so_entrou_em_empresa_baixada_aparece(pasta):
    ENTRADAS_E_BAIXADA = _entradas()
    so_na_baixada = ENTRADAS_E_BAIXADA[ENTRADAS_E_BAIXADA["cnpj_basico"] != ALVO_SP]
    _gravar(pasta / compradores.ENTRADAS / "parte.parquet", so_na_baixada)
    corpo = _lista(pasta)
    assert COMPRADORA in {c["raiz_do_cnpj"] for c in corpo["compradores"]}


def test_a_conta_de_empresas_ativas_do_setor_nao_muda(pasta):
    assert _lista(pasta)["setor"]["empresas_ativas"] == 3  # a baixada nunca entra aqui


def test_o_nome_da_empresa_baixada_sai_na_prova(pasta):
    entradas = _comprador(_lista(pasta), COMPRADORA)["provas"][compradores.ENTROU]
    (baixada,) = [
        e
        for e in entradas["exemplos"]
        if e["empresa_do_setor"]["raiz_do_cnpj"] == BAIXADA
    ]
    assert baixada["empresa_do_setor"]["razao_social"]["valor"] == NOMES[BAIXADA]
    assert baixada["uf"] == "SP"


def _com_baixadas_a_mais(pasta):
    """Três baixadas novas: uma do mesmo CNAE em SP, uma de outro CNAE e uma do RJ, com a COMPRADORA entrando em todas."""
    novas = [
        (OUTRA_BAIXADA, "08", "2012-01-01", SETOR, "SP", "2026-10", "2026-10-31"),
        (
            BAIXADA_DE_OUTRO_SETOR,
            "08",
            "2012-01-01",
            "4711302",
            "SP",
            "2026-10",
            "2026-10-31",
        ),
        (BAIXADA_DO_RJ, "08", "2012-01-01", SETOR, "RJ", "2026-10", "2026-10-31"),
    ]
    estabelecimentos = _estabelecimentos()
    extras = pd.DataFrame(
        novas,
        columns=["cnpj_basico", "situacao_cadastral", "data_inicio_atividade", "cnae_principal", "uf",
                 "mes_do_retrato", "disponivel_em"],
    )  # fmt: skip
    extras["cnpj"] = extras["cnpj_basico"] + "000100"
    extras["matriz"] = True
    extras["municipio"] = "7107"
    extras["data_inicio_atividade"] = pd.to_datetime(extras["data_inicio_atividade"])
    extras["disponivel_em"] = pd.to_datetime(extras["disponivel_em"]).dt.date
    for coluna in ("origem_sha256", "montado_em", "versao_do_codigo"):
        extras[coluna] = estabelecimentos[coluna].iloc[0]
    _gravar(
        pasta / compradores.ESTABELECIMENTOS / "11.parquet",
        pd.concat([estabelecimentos, extras], ignore_index=True),
    )
    nomes = pd.read_parquet(pasta / compradores.EMPRESAS / "11.parquet")
    novos = nomes.iloc[:2].assign(
        cnpj_basico=[OUTRA_BAIXADA, BAIXADA_DO_RJ],
        razao_social=["OUTRA LTDA", "RJ LTDA"],
    )
    _gravar(
        pasta / compradores.EMPRESAS / "11.parquet",
        pd.concat([nomes, novos], ignore_index=True),
    )
    entradas = _entradas()
    mais = pd.DataFrame(
        [
            (COMPRADORA, raiz, "2025-04-10", "2025-05", "2025-06-30", "entrou")
            for raiz in (OUTRA_BAIXADA, BAIXADA_DE_OUTRO_SETOR, BAIXADA_DO_RJ)
        ],
        columns=[
            "raiz_socio_pj",
            "cnpj_basico",
            "data_entrada",
            "mes_do_retrato",
            "disponivel_em",
            "movimento",
        ],
    )
    mais["data_entrada"] = pd.to_datetime(mais["data_entrada"]).dt.date
    mais["disponivel_em"] = pd.to_datetime(mais["disponivel_em"]).dt.date
    mais = mais.assign(
        qualificacao="22",
        **{
            c: entradas[c].iloc[0]
            for c in ("origem_sha256", "montado_em", "versao_do_codigo")
        },
    )
    _gravar(
        pasta / compradores.ENTRADAS / "parte.parquet",
        pd.concat([entradas, mais], ignore_index=True),
    )


def test_baixada_de_outro_cnae_ou_de_outra_uf_nao_conta(pasta):
    _com_baixadas_a_mais(pasta)
    todas = _comprador(_lista(pasta), COMPRADORA)["provas"][compradores.ENTROU]
    so_sp = _comprador(_lista(pasta, uf="SP"), COMPRADORA)["provas"][compradores.ENTROU]
    assert (
        todas["quantas"] == 4
    )  # ALVO_SP, BAIXADA, OUTRA_BAIXADA e a do RJ; a de outro CNAE nunca
    assert so_sp["quantas"] == 3  # sem a do RJ
    raizes = {e["empresa_do_setor"]["raiz_do_cnpj"] for e in todas["exemplos"]}
    assert BAIXADA_DE_OUTRO_SETOR not in raizes and FORA not in raizes


def test_entrada_em_empresa_baixada_antes_da_abertura_nao_conta(pasta):
    """O fundador não é comprador, nem numa empresa que depois baixou: a BAIXADA abriu em 2012."""
    entradas = _entradas()
    fundadora = entradas[entradas["cnpj_basico"] == BAIXADA].assign(
        data_entrada=date(2012, 1, 1)
    )
    resto = entradas[entradas["cnpj_basico"] != BAIXADA]
    _gravar(
        pasta / compradores.ENTRADAS / "parte.parquet",
        pd.concat([resto, fundadora], ignore_index=True),
    )
    entradas_da_compradora = _comprador(_lista(pasta, anos=10), COMPRADORA)["provas"][
        compradores.ENTROU
    ]
    assert entradas_da_compradora["quantas"] == 1  # só a ALVO_SP


def test_entrada_do_mesmo_grupo_em_empresa_baixada_nao_conta(pasta):
    """A HOLDING já era sócia da BAIXADA e da IRMA: a IRMA entrar na BAIXADA depois é reorganização, não compra."""
    entradas = _entradas()
    modelo = entradas[entradas["cnpj_basico"] == BAIXADA].iloc[0]
    antiga = modelo.copy()
    antiga["raiz_socio_pj"], antiga["data_entrada"] = HOLDING, date(2012, 1, 2)
    antiga["mes_do_retrato"], antiga["disponivel_em"] = "2023-05", date(2023, 6, 30)
    irma = modelo.copy()
    irma["raiz_socio_pj"], irma["data_entrada"] = IRMA, date(2025, 6, 1)
    irma["mes_do_retrato"], irma["disponivel_em"] = "2025-07", date(2025, 8, 31)
    mais = (
        pd.DataFrame([antiga, irma])
        .drop(columns=["movimento"])
        .assign(movimento="entrou")
    )
    _gravar(
        pasta / compradores.ENTRADAS / "parte.parquet",
        pd.concat([entradas, mais], ignore_index=True),
    )
    assert IRMA not in {c["raiz_do_cnpj"] for c in _lista(pasta)["compradores"]}


def test_entrada_em_empresa_baixada_ainda_nao_publica_nao_aparece(pasta):
    """Sem olhar o futuro: a entrada só conta depois de pública (publico_em)."""
    entradas = _entradas()
    mudada = entradas[entradas["cnpj_basico"] == BAIXADA].assign(
        disponivel_em=date(2026, 11, 30)
    )
    resto = entradas[entradas["cnpj_basico"] != BAIXADA]
    _gravar(
        pasta / compradores.ENTRADAS / "parte.parquet",
        pd.concat([resto, mudada], ignore_index=True),
    )
    entradas_da_compradora = _comprador(_lista(pasta), COMPRADORA)["provas"][
        compradores.ENTROU
    ]
    assert entradas_da_compradora["quantas"] == 1
