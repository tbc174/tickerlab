"""Eventos das empresas dos EUA pela SEC: leitura, classificação, gravação, coleta e telas, sem
internet (amostras reais e reduzidas em `tests/arquivos/sec/`: o mapa de tickers e os documentos
da Apple entregues desde 2025)."""

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import requests
import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from scripts import atualizar_eventos_sec
from src import eventos_sec as sec
from src.banco import eventos as repo
from src.banco.conexao import criar_engine, migrar_para
from src.relatorios import FUSO
from tests.ajudantes_da_conta import ir_para

PASTA = Path(__file__).parent / "arquivos" / "sec"
APPLE = "CIK0000320193"
DESDE_2025 = date(2025, 1, 1)


@pytest.fixture(scope="module")
def mapa():
    return sec.ler_tickers((PASTA / "company_tickers.json").read_bytes())


@pytest.fixture(scope="module")
def apple():
    return sec.ler_documentos((PASTA / "CIK0000320193.json").read_bytes(), DESDE_2025)


@pytest.fixture
def motor(tmp_path):
    url = f"sqlite:///{(tmp_path / 'sec.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()


# --- leitura e classificação -------------------------------------------------------------------
@pytest.mark.parametrize(
    ("formulario", "itens", "tema", "materialidade"),
    [
        ("8-K", "2.02,9.01", "resultados", 70),  # o anexo 9.01 não conta
        ("8-K", "5.02,1.03", "eventos", 100),  # vale o item mais material
        ("8-K/A", "4.02", "risco", 90),
        ("10-K", "", "resultados", 70),
        ("10-Q/A", "", "resultados", 60),
    ],
)
def test_classificacao_dos_documentos(formulario, itens, tema, materialidade):
    classe = sec.classificar(formulario, itens)
    assert (classe.tema, classe.materialidade) == (tema, materialidade)


@pytest.mark.parametrize(
    ("formulario", "itens"), [("8-K", "9.01"), ("4", ""), ("144", "")]
)
def test_anexos_e_formularios_de_pouco_interesse_nao_viram_evento(formulario, itens):
    assert sec.classificar(formulario, itens) is None


def test_alertas_e_participacoes():
    assert sec.classificar("8-K", "4.01,9.01").rotulo == "Troca de auditor"
    assert sec.classificar("NT 10-K", "").tema == "risco"
    ativo, passivo = (
        sec.classificar("SC 13D/A", ""),
        sec.classificar("SCHEDULE 13G", ""),
    )
    assert (ativo.tema, ativo.materialidade) == ("participacoes", 70)
    assert passivo.materialidade < ativo.materialidade
    assert sec.e_participacao("SC 13G/A") and not sec.e_participacao("8-K")


def test_cabecalho_diz_a_empresa_alvo():
    cabecalho = (PASTA / "cabecalho_13g.hdr.sgml").read_text(encoding="latin-1")
    assert (
        sec.empresa_alvo(cabecalho) == 320193
    )  # a Apple; quem entregou foi a Vanguard
    assert sec.empresa_alvo("<SEC-HEADER>sem empresa-alvo") is None


def test_mapa_de_tickers_usa_o_codigo_do_yahoo_e_o_cik_no_lugar_do_cnpj(mapa):
    linhas = mapa.set_index("ticker")
    assert linhas.loc["AAPL", "cnpj"] == APPLE
    assert "BRK-B" in linhas.index  # BRK.B na SEC
    assert linhas.loc["GOOGL", "cnpj"] == linhas.loc["GOOG", "cnpj"]  # mesma empresa
    so_dois = sec.ler_tickers(
        (PASTA / "company_tickers.json").read_bytes(), {"AAPL", "MSFT"}
    )
    assert set(so_dois["ticker"]) == {"AAPL", "MSFT"}


def test_documentos_da_apple(apple):
    # desde 2025: 16 8-K e 1 8-K/A (todos com item que interessa), 6 10-Q, 1 10-K e 3 13G de
    # investidores (1 novo e 2 atualizações); formulários 4, 144 etc. ficam fora
    assert len(apple) == 27 and apple["protocolo"].is_unique
    assert set(apple["categoria"]) == {
        "8-K", "8-K/A", "10-Q", "10-K", "SCHEDULE 13G", "SCHEDULE 13G/A",
    }  # fmt: skip
    assert (apple["cnpj"] == APPLE).all() and (
        apple["publicado_em"] >= DESDE_2025
    ).all()
    assert apple["publicado_em"].is_monotonic_decreasing
    assert (
        apple["link"]
        .str.startswith("https://www.sec.gov/Archives/edgar/data/320193/")
        .all()
    )
    resultado = apple[apple["tipo"] == "2.02,9.01"].iloc[0]
    assert (resultado["tema"], resultado["assunto"]) == ("resultados", "Resultados")
    reapresentado = apple[apple["categoria"] == "8-K/A"].iloc[0]
    assert reapresentado["versao"] == 2 and "reapresentação" in reapresentado["rotulo"]
    atualizacao = apple[apple["categoria"] == "SCHEDULE 13G/A"].iloc[0]
    assert atualizacao["versao"] == 1  # "/A" num 13G é atualização, não reapresentação
    assert (
        atualizacao["tema"] == "participacoes"
        and "(atualização)" in atualizacao["rotulo"]
    )
    assert (apple["rotulo"].str.len() <= 60).all()  # cabe na coluna do PostgreSQL
    recentes = sec.ler_documentos(
        (PASTA / "CIK0000320193.json").read_bytes(), date(2026, 7, 1)
    )
    assert (
        len(recentes) < len(apple)
        and (recentes["publicado_em"] >= date(2026, 7, 1)).all()
    )


# --- gravação ----------------------------------------------------------------------------------
def test_mapa_da_sec_e_o_da_cvm_nao_se_apagam(motor, mapa):
    cvm = mapa.head(0).copy()
    cvm.loc[0] = ["PETR4.SA", "PETR4", "33.000.167/0001-01", "PETROBRAS", "Ação"]
    with motor.begin() as c:
        repo.gravar_tickers(c, cvm)
        repo.gravar_tickers(c, mapa, origem=repo.ORIGEM_SEC)
        repo.gravar_tickers(c, cvm)  # a coleta da CVM do dia seguinte
        empresas = repo.empresas_dos_tickers(c, ["PETR4.SA", "AAPL"])
    assert empresas["AAPL"][0] == APPLE and "PETR4.SA" in empresas


def test_eventos_dos_eua_chegam_pelo_ticker(motor, mapa, apple):
    with motor.begin() as c:
        repo.gravar_tickers(c, mapa, origem=repo.ORIGEM_SEC)
        assert repo.gravar_eventos(c, apple, fonte=sec.FONTE_SEC) == (len(apple), 0)
        assert repo.gravar_eventos(c, apple, fonte=sec.FONTE_SEC) == (0, 0)
        eventos = repo.eventos_dos_tickers(c, ["AAPL"], DESDE_2025)
    assert len(eventos) == len(apple)
    assert {e.fonte for e in eventos} == {sec.FONTE_SEC} and {
        e.ticker for e in eventos
    } == {"AAPL"}


# --- coleta ------------------------------------------------------------------------------------
def test_sem_contato_nao_consulta_a_sec(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "TICKERLAB_DATABASE_URL", f"sqlite:///{(tmp_path / 'a.sqlite').as_posix()}"
    )
    monkeypatch.delenv("TICKERLAB_CONTATO", raising=False)

    def nao_pode(*_):
        raise AssertionError("consultou a SEC sem o e-mail de contato")

    monkeypatch.setattr(atualizar_eventos_sec, "baixar", nao_pode)
    assert atualizar_eventos_sec.main([]) == atualizar_eventos_sec.SEM_CONTATO


def test_coleta_se_identifica_e_pula_a_empresa_que_falha(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'c.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv("TICKERLAB_CONTATO", "contato@tickerlab.com.br")
    monkeypatch.setattr(atualizar_eventos_sec, "PAUSA_ENTRE_CONSULTAS", 0)
    agentes, cabecalhos = set(), []

    def baixar_falso(endereco: str, agente: str) -> bytes:
        agentes.add(agente)
        if endereco == sec.URL_DOS_TICKERS:
            return (PASTA / "company_tickers.json").read_bytes()
        if endereco == sec.URL_DOS_DOCUMENTOS.format(cik=320193):
            return (PASTA / "CIK0000320193.json").read_bytes()
        if endereco.endswith(".hdr.sgml"):
            cabecalhos.append(endereco)
            cabecalho = (PASTA / "cabecalho_13g.hdr.sgml").read_bytes()
            if "0000932471-25-000778" in endereco:  # este finge ser sobre outra empresa
                cabecalho = cabecalho.replace(b"<CIK>0000320193", b"<CIK>0000789019")
            return cabecalho
        raise requests.HTTPError("503")  # as outras empresas falham e são puladas

    monkeypatch.setattr(atualizar_eventos_sec, "baixar", baixar_falso)
    assert atualizar_eventos_sec.main(["--dias", "3650"]) == 0
    assert agentes == {"TickerLab contato@tickerlab.com.br"}
    with criar_engine(url).connect() as c:
        assert c.execute(sa.text("select count(*) from eventos")).scalar() == 26
        assert (
            c.execute(sa.text("select count(*) from tickers_dos_emissores")).scalar()
            == 6
        )
    assert len(cabecalhos) == 3  # só os 13G pedem o cabeçalho
    assert atualizar_eventos_sec.main(["--dias", "3650"]) == 0
    assert len(cabecalhos) == 4  # de novo: só o recusado (não guardado) pede outra vez


# --- telas -------------------------------------------------------------------------------------
def _coletar_apple(banco, mapa, apple):
    """Grava a Apple com datas recentes (os testes não dependem do calendário)."""
    hoje = datetime.now(FUSO).date()
    tabela = apple.assign(
        publicado_em=[hoje - timedelta(days=i % 20) for i in range(len(apple))]
    )
    with banco.begin() as c:
        repo.gravar_tickers(c, mapa, origem=repo.ORIGEM_SEC)
        repo.gravar_eventos(c, tabela, fonte=sec.FONTE_SEC)


def _abrir(pagina, **estado) -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    for chave, valor in estado.items():
        app.session_state[chave] = valor
    app.run()
    return ir_para(app, pagina)


def test_acontecimentos_mostra_a_apple_com_link_para_a_sec(banco, mapa, apple):
    _coletar_apple(banco, mapa, apple)
    app = _abrir("research", favoritos=["AAPL"])
    app.selectbox(key="research_lista").set_value("Favoritos").run()
    assert not app.exception
    botoes = app.get("link_button")
    assert botoes and all(
        b.proto.url.startswith("https://www.sec.gov/") for b in botoes
    )
    assert all(b.proto.label == "Abrir na SEC" for b in botoes)
    assert "Sem cobertura ainda" not in " ".join(c.value for c in app.caption)


def test_fundamentos_dos_eua_explicam_que_chegam_depois(banco, mapa):
    with banco.begin() as c:
        repo.gravar_tickers(c, mapa, origem=repo.ORIGEM_SEC)
    app = _abrir("fundamentos", ticker="AAPL")
    assert not app.exception
    assert any("chegam numa próxima etapa" in i.value for i in app.info)
    assert not app.metric
