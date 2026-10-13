"""Versões das demonstrações, negociações e detentores (Radar, PR 4): a fonte reapresenta, a
versão anterior fica guardada; refazer com o mesmo arquivo não cria versão. Sem internet (amostras
reais em `tests/arquivos/`)."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa

from src import demonstracoes as dm
from src import fundos_cvm as cda
from src import negociacoes_cvm as vlmo
from src.banco import demonstracoes as repo_dm
from src.banco import detentores as repo_dt
from src.banco import negociacoes as repo_ng
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import (
    demonstracoes,
    demonstracoes_versoes,
    detentores_por_acao,
    detentores_por_acao_versoes,
    documentos_financeiros_versoes,
    maiores_detentores_versoes,
    negociacoes_internas_versoes,
)
from src.banco.versoes import como_estava_em, historico, versionar

CVM = Path(__file__).parent / "arquivos" / "cvm"
ANTES = datetime(2026, 10, 1, 7, tzinfo=UTC)
DEPOIS = ANTES + timedelta(days=5)
AGOSTO = date(2026, 8, 31)


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{(tmp_path / 'v.sqlite').as_posix()}"


@pytest.fixture
def motor(url):
    migrar_para("head", url=url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()


@pytest.fixture(scope="module")
def itr():
    return dm.ler_demonstracoes(
        (CVM / "fundamentos" / "itr_cia_aberta_2026.zip").read_bytes(), "ITR"
    )


def _um_documento(itr, versao: int, valor: float | None = None):
    contas, documentos = itr
    doc = documentos.head(1).assign(versao=versao)
    chave = doc.iloc[0]
    dele = contas[
        (contas["cnpj"] == chave["cnpj"])
        & (contas["referencia"] == chave["referencia"])
    ]
    dele = dele.assign(versao=versao)
    return (dele if valor is None else dele.assign(valor=valor)), doc


def _contar(c, tabela) -> int:
    return c.execute(sa.select(sa.func.count()).select_from(tabela)).scalar()


# --- demonstrações --------------------------------------------------------------------------------
def test_reapresentacao_da_demonstracao_guarda_as_duas(motor, itr):
    contas, doc = _um_documento(itr, 1)
    chave = doc.iloc[0]
    filtro = {
        "cnpj": chave["cnpj"],
        "documento": "ITR",
        "referencia": chave["referencia"],
    }
    with motor.begin() as c:
        repo_dm.gravar_demonstracoes(c, contas, doc, agora=ANTES)
        repo_dm.gravar_demonstracoes(c, contas, doc, agora=ANTES)  # mesma versão: nada
        repo_dm.gravar_demonstracoes(c, *_um_documento(itr, 2, 1.0), agora=DEPOIS)
        assert _contar(c, demonstracoes) == len(contas)  # a vigente só tem a nova
        linhas = historico(c, demonstracoes_versoes, **filtro)
        assert len(linhas) == 2 * len(contas)
        antes = como_estava_em(
            c, demonstracoes_versoes, ANTES + timedelta(days=1), **filtro
        )
        depois = como_estava_em(c, demonstracoes_versoes, DEPOIS, **filtro)
        indice = historico(c, documentos_financeiros_versoes, **filtro)
    assert {l.versao for l in antes} == {1} and len(antes) == len(contas)
    assert {(l.versao, l.valor) for l in depois} == {(2, 1.0)}
    assert [(l.versao, l.substituido_em is None) for l in indice] == [
        (1, False),
        (2, True),
    ]


# --- negociações ----------------------------------------------------------------------------------
def test_reapresentacao_da_negociacao_guarda_as_duas(motor):
    da_cvm = vlmo.ler_vlmo((CVM / "vlmo_amostra.zip").read_bytes())
    um = da_cvm[da_cvm["documento"] == da_cvm["documento"].iloc[0]]
    nova = um.head(1).assign(versao=um["versao"].max() + 1, quantidade=1.0)
    filtro = {"fonte": um["fonte"].iloc[0], "documento": um["documento"].iloc[0]}
    with motor.begin() as c:
        repo_ng.gravar_negociacoes(c, da_cvm, agora=ANTES)
        repo_ng.gravar_negociacoes(c, da_cvm, agora=ANTES)
        assert _contar(c, negociacoes_internas_versoes) == len(da_cvm)
        repo_ng.gravar_negociacoes(c, nova, agora=DEPOIS)
        versoes = historico(c, negociacoes_internas_versoes, **filtro)
        hoje = como_estava_em(c, negociacoes_internas_versoes, DEPOIS, **filtro)
    assert len(versoes) == len(um) + 1
    assert [l.quantidade for l in hoje] == [1.0]


# --- detentores -----------------------------------------------------------------------------------
def test_mes_refeito_igual_nao_cria_versao_e_mudado_cria(motor):
    agosto = cda.ler_posicoes((CVM / "cda_amostra_202608.zip").read_bytes())
    resumo, maiores = cda.resumir(agosto), cda.maiores(agosto)
    filtro = {"fonte": cda.FONTE_CDA, "competencia": AGOSTO}
    with motor.begin() as c:
        repo_dt.gravar_competencia(c, resumo, maiores, 300, agora=ANTES)
        repo_dt.gravar_competencia(c, resumo, maiores, 300, agora=ANTES + timedelta(1))
        assert _contar(c, detentores_por_acao_versoes) == len(resumo)
        assert _contar(c, maiores_detentores_versoes) == len(maiores)
        # fundos atrasados entregaram: o mês muda
        repo_dt.gravar_competencia(
            c, resumo.head(2), maiores.head(0), 280, agora=DEPOIS
        )
        assert _contar(c, detentores_por_acao) == 2
        antes = como_estava_em(
            c, detentores_por_acao_versoes, DEPOIS - timedelta(1), **filtro
        )
        depois = como_estava_em(c, detentores_por_acao_versoes, DEPOIS, **filtro)
        maiores_hoje = como_estava_em(c, maiores_detentores_versoes, DEPOIS, **filtro)
    assert (len(antes), len(depois), maiores_hoje) == (len(resumo), 2, [])


def test_chave_errada_e_recusada(motor):
    with motor.begin() as c, pytest.raises(ValueError, match="Chave errada"):
        versionar(c, detentores_por_acao_versoes, {"fonte": "x"}, [], ANTES)


# --- migração -------------------------------------------------------------------------------------
def test_migracao_copia_o_que_ja_existia_e_volta(url, itr):
    migrar_para("0024", url=url)
    motor = criar_engine(url)
    try:
        contas, _ = _um_documento(itr, 1)
        with motor.begin() as c:
            # gravação de antes da PR 4: as tabelas de versões ainda não existem
            c.execute(
                sa.insert(demonstracoes),
                [
                    {k: getattr(l, k) for k in
                     ("cnpj", "documento", "referencia", "periodo", "fim", "conta", "valor")}
                    | {"inicio": None, "versao": 1}
                    for l in contas.itertuples(index=False)
                ],
            )  # fmt: skip
        migrar_para("head", url=url)
        with motor.connect() as c:
            assert _contar(c, demonstracoes_versoes) == len(contas)
            agora = datetime.now(UTC) + timedelta(minutes=1)
            assert len(como_estava_em(c, demonstracoes_versoes, agora)) == len(contas)
        desfazer_ate("0024", url=url)
        with motor.connect() as c:
            tabelas = sa.inspect(c).get_table_names()
            assert not [
                t for t in tabelas if t.endswith("_versoes") and t != "eventos_versoes"
            ]
            assert _contar(c, demonstracoes) == len(contas)
    finally:
        motor.dispose()


# --- contas novas no leitor (série 2 da base de ML, PR 1) -------------------------------------------
CONTAS_NOVAS = {"contas_a_receber", "estoques", "custo", "capex", "depreciacao"}


def test_contas_novas_nao_criam_versao_falsa(motor):
    contas, documentos = dm.ler_demonstracoes(
        (CVM / "fundamentos" / "dfp_cia_aberta_2025.zip").read_bytes(), "DFP"
    )
    antigas = contas[~contas["conta"].isin(CONTAS_NOVAS)]  # o que o leitor lia antes
    with motor.begin() as c:
        repo_dm.gravar_demonstracoes(c, antigas, documentos, agora=ANTES)
        linhas_antes = _contar(c, demonstracoes_versoes)
    with motor.begin() as c:
        acrescentadas = repo_dm.acrescentar_contas_novas(
            c, contas, documentos, agora=DEPOIS
        )
        assert (
            repo_dm.acrescentar_contas_novas(c, contas, documentos, agora=DEPOIS) == 0
        )
    novas = contas["conta"].isin(CONTAS_NOVAS).sum()
    assert acrescentadas == novas > 0
    with motor.connect() as c:
        versoes = c.execute(sa.select(demonstracoes_versoes)).all()
        assert len(versoes) == linhas_antes + novas
        assert all(
            v.substituido_em is None for v in versoes
        )  # nada virou reapresentação
        logo_depois = ANTES + timedelta(seconds=1)
        foto = como_estava_em(c, demonstracoes_versoes, logo_depois)
        assert {
            l.conta for l in foto
        } >= CONTAS_NOVAS  # valem desde a versão, não desde hoje
        vigentes = {l.conta for l in c.execute(sa.select(demonstracoes.c.conta))}
        assert vigentes >= CONTAS_NOVAS


def test_acrescentar_nao_mexe_em_documento_de_outra_versao(motor):
    contas, documentos = dm.ler_demonstracoes(
        (CVM / "fundamentos" / "dfp_cia_aberta_2025.zip").read_bytes(), "DFP"
    )
    with motor.begin() as c:
        repo_dm.gravar_demonstracoes(
            c, contas[~contas["conta"].isin(CONTAS_NOVAS)], documentos, agora=ANTES
        )
    mais_nova = documentos.assign(versao=documentos["versao"] + 1)
    with motor.begin() as c:
        # versão nova é reapresentação: quem grava é gravar_demonstracoes, não o acréscimo
        assert repo_dm.acrescentar_contas_novas(c, contas, mais_nova, agora=DEPOIS) == 0
