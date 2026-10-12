"""Busca na hora (Research R4): uma ação dos EUA fora do S&P 500 buscada na SEC quando alguém
pede, guardada e incluída na coleta diária. Sem internet: a SEC é simulada com as amostras reais
(os documentos da Apple fazem o papel dos da SoFi)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from scripts import atualizar_eventos_sec
from src import coleta_sec
from src import eventos_sec as sec
from src import fundamentos_sec as fs
from src.banco import sob_demanda
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.eventos import empresas_dos_tickers
from tests.ajudantes_da_conta import ir_para

SEC = Path(__file__).parent / "arquivos" / "sec"
SOFI = 1818874
AGORA = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


def _como_sofi(arquivo: str) -> bytes:
    dados = json.loads((SEC / arquivo).read_text(encoding="utf-8"))
    dados["cik"] = SOFI
    dados["name" if "name" in dados else "entityName"] = "SoFi Technologies, Inc."
    return json.dumps(dados).encode()


def _sec_simulada(pedidos: list[str]):
    def transporte(url: str, agente: str) -> bytes:
        pedidos.append(url)
        if url == sec.URL_DOS_TICKERS:
            return (SEC / "company_tickers.json").read_bytes()
        if url == sec.URL_DOS_DOCUMENTOS.format(cik=SOFI):
            return _como_sofi("CIK0000320193.json")
        if url == fs.URL_DOS_FATOS.format(cik=SOFI):
            return _como_sofi("fatos_apple.json")
        if url.endswith(".hdr.sgml"):
            return (
                SEC / "cabecalho_13g.hdr.sgml"
            ).read_bytes()  # sobre a Apple: fica fora
        if url.endswith(".xml"):
            return (SEC / "form4_venda_plano.xml").read_bytes()  # da Apple: não conta
        raise AssertionError(f"consulta inesperada: {url}")

    return transporte


@pytest.fixture
def motor(tmp_path):
    url = f"sqlite:///{(tmp_path / 'r4.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()


@pytest.fixture(scope="module")
def mapa():
    return sec.ler_tickers((SEC / "company_tickers.json").read_bytes())


def _cliente(pedidos):
    return coleta_sec.ClienteSec(
        "TickerLab contato@tickerlab.com.br", 0, _sec_simulada(pedidos)
    )


def test_busca_grava_a_empresa_e_a_poe_na_coleta(motor, mapa):
    pedidos = []
    empresa, eventos, lidos = coleta_sec.buscar_agora(
        motor, _cliente(pedidos), "SOFI", mapa, AGORA
    )
    assert empresa == "SoFi Technologies, Inc." and eventos > 0
    assert (
        lidos == coleta_sec.FORM4_NA_BUSCA
    )  # só os mais recentes; o resto na coleta diária
    with motor.connect() as c:
        assert empresas_dos_tickers(c, ["SOFI"])["SOFI"][0] == "CIK0001818874"
        assert sob_demanda.tickers(c) == {"SOFI"}
        documentos = c.execute(
            sa.text(
                "select count(*) from documentos_financeiros where cnpj = 'CIK0001818874'"
            )
        ).scalar()
    assert documentos > 0  # os balanços vieram junto


def test_ticker_fora_da_sec_e_recusado_sem_consultar(motor, mapa):
    pedidos = []
    with pytest.raises(coleta_sec.BuscaRecusada, match="não está na lista"):
        coleta_sec.buscar_agora(motor, _cliente(pedidos), "XYZW", mapa, AGORA)
    assert pedidos == []


def test_limite_por_hora_protege_a_sec(motor, mapa):
    with motor.begin() as c:
        for i in range(coleta_sec.BUSCAS_POR_HORA):
            sob_demanda.registrar(c, f"T{i}", f"CIK{i:010d}", "X")
    pedidos = []
    with pytest.raises(coleta_sec.BuscaRecusada, match="Muitas buscas"):
        coleta_sec.buscar_agora(
            motor,
            _cliente(pedidos),
            "SOFI",
            mapa,
            datetime.now(UTC) + timedelta(minutes=1),
        )
    assert pedidos == []


def test_coleta_diaria_inclui_as_buscadas(tmp_path, monkeypatch, mapa):
    url = f"sqlite:///{(tmp_path / 'd.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv("TICKERLAB_CONTATO", "contato@tickerlab.com.br")
    monkeypatch.setattr(atualizar_eventos_sec, "PAUSA_ENTRE_CONSULTAS", 0)
    migrar_para("head", url=url)
    with criar_engine(url).begin() as c:
        sob_demanda.registrar(c, "SOFI", "CIK0001818874", "SoFi Technologies, Inc.")
    pedidos = []
    simulada = _sec_simulada(pedidos)

    def baixar(endereco: str, agente: str) -> bytes:
        try:
            return simulada(endereco, agente)
        except (
            AssertionError
        ):  # as empresas do S&P 500 "falham": só a SoFi interessa aqui
            raise atualizar_eventos_sec.requests.HTTPError("503") from None

    monkeypatch.setattr(atualizar_eventos_sec, "baixar", baixar)
    assert atualizar_eventos_sec.main(["--max-form4", "0"]) == 0
    assert sec.URL_DOS_DOCUMENTOS.format(cik=SOFI) in pedidos
    with criar_engine(url).connect() as c:
        assert "SOFI" in empresas_dos_tickers(
            c, ["SOFI"]
        )  # o mapa novo não apagou a SoFi


def test_migracao_0014_vai_e_volta(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}"
    migrar_para("head", url=url)
    desfazer_ate("0013", url=url)
    assert "tickers_sob_demanda" not in sa.inspect(criar_engine(url)).get_table_names()
    migrar_para("head", url=url)


# --- na tela -----------------------------------------------------------------------------------
def _abrir(ticker, pagina="fundamentos") -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["ticker"] = ticker
    app.run()
    return ir_para(app, pagina)


def test_acao_dos_eua_fora_da_base_oferece_a_busca(banco, monkeypatch):
    monkeypatch.setenv("TICKERLAB_CONTATO", "contato@tickerlab.com.br")
    chamadas = []

    def buscar_falso(motor, cliente, ticker, mapa, agora):
        chamadas.append(ticker)
        with motor.begin() as c:
            sob_demanda.registrar(c, ticker, "CIK0000320193", "Apple Inc.")
        return "Apple Inc.", 3, 0

    monkeypatch.setattr(coleta_sec, "buscar_agora", buscar_falso)
    monkeypatch.setattr(
        coleta_sec.ClienteSec,
        "baixar",
        lambda self, url: (SEC / "company_tickers.json").read_bytes(),
    )
    app = _abrir("AAPL")
    assert not app.exception
    assert any("ainda não está na base" in i.value for i in app.info)
    app.button(key="buscar_na_sec_AAPL").click().run()
    assert not app.exception and chamadas == ["AAPL"]
    assert any("entra na coleta diária" in s.value for s in app.success)


def test_indice_e_cripto_nao_oferecem_a_busca(banco):
    app = _abrir("BTC-USD", "por_dentro")
    assert not app.exception
    assert not any(b.key and b.key.startswith("buscar_na_sec_") for b in app.button)
    assert any("não tem cadastro na CVM nem na SEC" in i.value for i in app.info)
