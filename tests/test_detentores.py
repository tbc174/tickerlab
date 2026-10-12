"""Quem tem cada ação (Research R3): carteiras dos fundos na CVM (CDA) e o 13F da SEC, sem
internet. Amostras reais e reduzidas: CDA de julho e agosto de 2026 (PETR4, VALE3, WEGE3, MGLU3,
ITUB4), uma base 13F com 45 gestores (AAPL e MSFT, com opções e retificações para testar o que
fica de fora) e um arquivo de "falhas de entrega" para ligar CUSIP e ticker."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from scripts import atualizar_fundos_cvm, atualizar_fundos_sec
from src import detentores as dt
from src import fundos_cvm as cda
from src import fundos_sec as f13
from src.banco import detentores as repo
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from tests.ajudantes_da_conta import ir_para

CVM = Path(__file__).parent / "arquivos" / "cvm"
SEC = Path(__file__).parent / "arquivos" / "sec"
AGOSTO, JULHO = date(2026, 8, 31), date(2026, 7, 31)


def _juntar(tabelas):
    return pd.concat(tabelas, ignore_index=True)


def _cda(mes):
    return cda.ler_posicoes((CVM / f"cda_amostra_{mes}.zip").read_bytes())


@pytest.fixture(scope="module")
def agosto():
    return _cda("202608")


@pytest.fixture(scope="module")
def mapa():
    return f13.ler_mapa_de_cusips(
        [(SEC / "cnsfails_amostra.zip").read_bytes()], {"AAPL", "MSFT"}
    )


@pytest.fixture(scope="module")
def trimestre(mapa):
    conteudo = (SEC / "form13f_amostra.zip").read_bytes()
    return f13.ler_posicoes(conteudo, f13.trimestre_da_base(conteudo), mapa)


# --- CVM (CDA) ---------------------------------------------------------------------------------
def test_cda_so_acoes_da_b3_nos_tres_tipos(agosto):
    assert set(agosto["tipo"]) == {dt.COMPRADO, dt.VENDIDO, dt.EMPRESTADO}
    assert set(agosto["codigo"]) <= {"PETR4", "VALE3", "WEGE3", "MGLU3", "ITUB4"}
    assert (agosto["competencia"] == AGOSTO).all()


def test_resumo_conta_emprestado_como_do_fundo(agosto):
    resumo = cda.resumir(agosto).set_index("codigo")
    petr4 = resumo.loc["PETR4"]
    assert petr4["detentores"] > 100 and petr4["vendidos"] > 0
    so_comprado = agosto[
        (agosto["codigo"] == "PETR4") & (agosto["tipo"] == dt.COMPRADO)
    ]
    assert petr4["valor"] > so_comprado["valor"].sum()  # + o que está emprestado
    assert petr4["valor_emprestado"] > 0


def test_maiores_fundos_em_ordem(agosto):
    maiores = cda.maiores(agosto)
    petr4 = maiores[(maiores["codigo"] == "PETR4") & (maiores["tipo"] == dt.COMPRADO)]
    assert list(petr4["posicao"]) == list(range(1, dt.MAIORES + 1))
    assert petr4["valor"].is_monotonic_decreasing
    assert set(maiores["tipo"]) == {dt.COMPRADO, dt.VENDIDO}


def test_comparar_dois_meses(agosto):
    resumo = cda.resumir(_juntar([_cda("202607"), agosto]))
    tabela = dt.comparar(resumo, AGOSTO, JULHO).set_index("codigo")
    petr4 = tabela.loc["PETR4"]
    assert petr4["variacao"] == petr4["detentores"] - petr4["detentores_antes"]
    assert 0 < petr4["fatia_vendida"] < 1


def test_mes_ainda_chegando_fica_de_fora_e_so_compara_cobertura_parecida():
    junho, setembro = date(2026, 6, 30), date(2026, 9, 30)
    # números reais de 2026: junho com o sigilo já vencido, setembro ainda chegando
    cobertura = {junho: 6653, JULHO: 3385, AGOSTO: 3496, setembro: 1966}
    assert dt.competencias_utilizaveis(cobertura) == [AGOSTO, JULHO, junho]
    assert dt.par_comparavel(cobertura) == (AGOSTO, JULHO)
    assert dt.par_comparavel({junho: 6653, JULHO: 3385}) is None  # sigilo: não compara
    assert dt.competencias_utilizaveis({}) == []


def test_meses_recentes_atravessam_o_ano():
    assert cda.meses_recentes(date(2026, 1, 15), 3) == [
        (2025, 12),
        (2025, 11),
        (2025, 10),
    ]


# --- SEC (13F) ---------------------------------------------------------------------------------
def test_mapa_de_cusips_so_para_os_tickers_pedidos(mapa):
    assert mapa == {"037833100": "AAPL", "594918104": "MSFT"}


def test_13f_so_originais_e_sem_opcoes(trimestre):
    conteudo = (SEC / "form13f_amostra.zip").read_bytes()
    assert f13.trimestre_da_base(conteudo) == "2026-06-30"
    assert set(trimestre["codigo"]) == {"AAPL", "MSFT"}
    assert (trimestre["competencia"] == date(2026, 6, 30)).all()
    assert (
        trimestre["cnpj_fundo"].nunique() <= 40
    )  # as retificações (13F-HR/A) ficam fora
    resumo = f13.resumir(trimestre).set_index("codigo")
    assert (resumo["vendidos"] == 0).all()  # o 13F não mostra vendas a descoberto
    maiores = f13.maiores(trimestre)
    assert maiores.groupby("codigo")["posicao"].max().max() == dt.MAIORES


def test_links_da_pagina():
    html = '<a href="/files/x/01jun2026-31aug2026_form13f.zip">a</a><a href="https://y/b_form13f.zip">'
    assert f13.links_da_pagina(html, "form13f") == [
        "https://www.sec.gov/files/x/01jun2026-31aug2026_form13f.zip",
        "https://y/b_form13f.zip",
    ]


# --- gravação ----------------------------------------------------------------------------------
@pytest.fixture
def motor(tmp_path):
    url = f"sqlite:///{(tmp_path / 'd.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()


def test_gravar_troca_o_mes_inteiro(motor, agosto):
    resumo, maiores = cda.resumir(agosto), cda.maiores(agosto)
    with motor.begin() as c:
        assert repo.gravar_competencia(c, resumo, maiores, 300) == len(resumo)
        assert repo.gravar_competencia(c, resumo.head(2), maiores.head(0), 280) == 2
        assert repo.cobertura(c, cda.FONTE_CDA) == {AGOSTO: 280}
        assert repo.competencias(c, cda.FONTE_CDA) == [AGOSTO]
        assert (
            c.execute(sa.text("select count(*) from detentores_por_acao")).scalar() == 2
        )
        assert (
            c.execute(sa.text("select count(*) from maiores_detentores")).scalar() == 0
        )


def test_migracao_0012_vai_e_volta(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}"
    migrar_para("head", url=url)
    desfazer_ate("0011", url=url)
    assert "detentores_por_acao" not in sa.inspect(criar_engine(url)).get_table_names()
    migrar_para("head", url=url)


# --- coletas -----------------------------------------------------------------------------------
def test_coleta_da_cvm_sem_internet(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'c.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setattr(
        cda, "meses_recentes", lambda hoje, quantos: [(2026, 9), (2026, 8), (2026, 7)]
    )

    def baixar_falso(endereco: str) -> bytes | None:
        for mes in ("202607", "202608"):
            if endereco.endswith(f"cda_fi_{mes}.zip"):
                return (CVM / f"cda_amostra_{mes}.zip").read_bytes()
        return None  # setembro ainda não saiu

    monkeypatch.setattr(atualizar_fundos_cvm, "baixar", baixar_falso)
    assert atualizar_fundos_cvm.main([]) == 0
    assert atualizar_fundos_cvm.main([]) == 0  # de novo: troca, não duplica
    with criar_engine(url).connect() as c:
        assert repo.competencias(c, cda.FONTE_CDA) == [AGOSTO, JULHO]


def test_coleta_do_13f_le_cada_base_uma_vez(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 's.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv("TICKERLAB_CONTATO", "contato@tickerlab.com.br")
    monkeypatch.setattr(atualizar_fundos_sec, "PAUSA_ENTRE_CONSULTAS", 0)
    bases = []

    def baixar_falso(endereco: str, agente: str) -> bytes:
        if endereco == f13.URL_DA_PAGINA_DO_13F:
            return b'<a href="/files/x/01jun2026-31aug2026_form13f.zip">'
        if endereco == f13.URL_DA_PAGINA_DAS_FALHAS:
            return b'<a href="/files/data/cnsfails202609a.zip">'
        if endereco.endswith("cnsfails202609a.zip"):
            return (SEC / "cnsfails_amostra.zip").read_bytes()
        if endereco.endswith("_form13f.zip"):
            bases.append(endereco)
            return (SEC / "form13f_amostra.zip").read_bytes()
        raise atualizar_fundos_sec.requests.HTTPError("404")

    monkeypatch.setattr(atualizar_fundos_sec, "baixar", baixar_falso)
    assert atualizar_fundos_sec.main([]) == 0
    assert atualizar_fundos_sec.main([]) == 0
    assert len(bases) == 1  # a base já lida não é baixada de novo
    with criar_engine(url).connect() as c:
        assert repo.competencias(c, f13.FONTE_13F) == [date(2026, 6, 30)]


def test_13f_sem_contato_nao_consulta(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "TICKERLAB_DATABASE_URL", f"sqlite:///{(tmp_path / 'x.sqlite').as_posix()}"
    )
    monkeypatch.delenv("TICKERLAB_CONTATO", raising=False)
    monkeypatch.setattr(
        atualizar_fundos_sec, "baixar", lambda *_: pytest.fail("consultou")
    )
    assert atualizar_fundos_sec.main([]) == atualizar_fundos_sec.SEM_CONTATO


# --- página ------------------------------------------------------------------------------------
def _gravar(banco, trimestre):
    with banco.begin() as c:
        for mes in ("202607", "202608"):
            posicoes = _cda(mes)
            repo.gravar_competencia(
                c,
                cda.resumir(posicoes),
                cda.maiores(posicoes),
                dt.informantes(posicoes),
            )
        repo.gravar_competencia(
            c, f13.resumir(trimestre), f13.maiores(trimestre), dt.informantes(trimestre)
        )


def _abrir(ticker) -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["ticker"] = ticker
    app.run()
    return ir_para(app, "donos")


def test_pagina_sem_coleta(banco):
    app = _abrir("PETR4.SA")
    assert not app.exception
    assert any("ainda não foram coletados" in i.value for i in app.info)


def test_pagina_de_acao_da_b3(banco, trimestre):
    _gravar(banco, trimestre)
    app = _abrir("PETR4.SA")
    assert not app.exception
    rotulos = {m.label for m in app.metric}
    assert {
        "Fundos com a ação",
        "Fatia dos fundos que informaram",
        "Fundos vendidos (aposta na queda)",
    } <= rotulos
    tabelas = [t.value for t in app.dataframe]
    assert any("Nome" in t.columns and len(t) == dt.MAIORES for t in tabelas)
    assert any("Vendido ÷ comprado" in t.columns for t in tabelas)  # aba do mercado
    assert any("long-short" in c.value for c in app.caption)


def test_pagina_de_acao_dos_eua(banco, trimestre):
    _gravar(banco, trimestre)
    app = _abrir("AAPL")
    assert not app.exception
    rotulos = {m.label for m in app.metric}
    assert (
        "Gestores com a ação" in rotulos
        and "Fundos vendidos (aposta na queda)" not in rotulos
    )
    assert any(m.value.startswith("US$ ") for m in app.metric)


def test_aviso_de_cobertura_so_quando_o_mes_tem_bem_menos_informantes():
    marco = date(2026, 3, 31)
    cobertura = {marco: 3216, JULHO: 959, AGOSTO: 1082}
    aviso = dt.aviso_de_cobertura(cobertura, AGOSTO, "fundos")
    assert "1082 fundos informaram posições em 08/2026, contra 3216 em 03/2026" in aviso
    assert dt.aviso_de_cobertura({marco: 3216, AGOSTO: 3100}, AGOSTO, "fundos") is None
