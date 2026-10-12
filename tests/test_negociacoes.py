"""Negociações de pessoas de dentro (Research R2): CVM (VLMO) e SEC (Form 4), gravação, coleta e
a página, sem internet. Amostras reais e reduzidas: `tests/arquivos/cvm/vlmo_amostra.zip`
(Petrobras, WEG e Banco do Brasil em 2026) e dois Form 4 da Apple (nomes trocados por
"NOME OMITIDO": guardamos só o cargo)."""

import io
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from scripts import atualizar_eventos_sec, atualizar_negociacoes_cvm
from src import eventos as ev
from src import eventos_sec as sec
from src import negociacoes as ng
from src import negociacoes_cvm as vlmo
from src import negociacoes_sec as form4
from src.banco import eventos as repo_eventos
from src.banco import negociacoes as repo
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.relatorios import FUSO
from tests.ajudantes_da_conta import ir_para

CVM = Path(__file__).parent / "arquivos" / "cvm"
SEC = Path(__file__).parent / "arquivos" / "sec"
APPLE = 320193
PETROBRAS = "33.000.167/0001-01"


@pytest.fixture(scope="module")
def da_cvm():
    return vlmo.ler_vlmo((CVM / "vlmo_amostra.zip").read_bytes())


def _form4(arquivo="form4_venda_plano.xml", cik=APPLE, protocolo="0001-26-000001"):
    return form4.ler_form4(
        (SEC / arquivo).read_bytes(), cik, protocolo, date(2026, 10, 8), "https://x"
    )


@pytest.fixture
def motor(tmp_path):
    url = f"sqlite:///{(tmp_path / 'n.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()


# --- CVM ---------------------------------------------------------------------------------------
def test_vlmo_so_compras_e_vendas_de_acoes_da_propria_empresa(da_cvm):
    assert len(da_cvm) == 129
    assert set(da_cvm["operacao"]) == {ng.COMPRA, ng.VENDA}
    assert set(da_cvm["cargo"]) <= set(ng.CARGOS)
    assert da_cvm["ativo"].str.match("Ações|Units").all()
    assert (da_cvm["quantidade"] > 0).all() and (da_cvm["moeda"] == "BRL").all()
    assert da_cvm["link"].str.startswith("https://www.rad.cvm.gov.br/").all()
    assert da_cvm["documento"].str.fullmatch(r"[\d./-]+\|\d{4}-\d{2}").all()
    assert not (da_cvm["preco"] == 0).any()  # zero vira "não informado"


def test_vlmo_fica_so_com_a_versao_mais_nova(da_cvm):
    assert (da_cvm.groupby("documento")["versao"].nunique() == 1).all()
    assert (da_cvm["versao"] == 2).any()  # o Banco do Brasil reapresentou


def test_eventos_da_cvm_por_documento_cargo_e_operacao(da_cvm):
    eventos = ng.eventos_das_negociacoes(da_cvm)
    assert eventos["protocolo"].is_unique
    assert (eventos["rotulo"].str.len() <= 60).all() and (
        eventos["protocolo"].str.len() <= 60
    ).all()
    assert set(eventos["tema"]) == {"participacoes"}
    compra = eventos[eventos["rotulo"].str.contains("comprou")].iloc[0]
    assert compra["materialidade"] == ng.MATERIALIDADE_DA_COMPRA
    assert "/2026" in compra["assunto"]  # a CVM informa por mês


# --- SEC ---------------------------------------------------------------------------------------
def test_form4_venda_programada_so_com_o_cargo():
    tabela = _form4()
    assert len(tabela) == 1
    linha = tabela.iloc[0]
    assert (linha["cargo"], linha["operacao"], linha["plano_10b5_1"]) == (
        "diretoria",
        "venda",
        True,
    )
    assert linha["cargo_descricao"] == "SVP, GC and Government Affairs"
    assert linha["valor"] == pytest.approx(2399 * 332.01)
    assert "NOME" not in " ".join(map(str, linha.to_numpy()))  # o nome nunca é lido
    evento = ng.eventos_das_negociacoes(tabela).iloc[0]
    assert evento["materialidade"] == ng.MATERIALIDADE_DA_VENDA_PROGRAMADA
    assert "plano 10b5-1" in evento["rotulo"] and "US$ 796,5 mil" in evento["assunto"]


def test_form4_ignora_opcoes_pagamento_impostos_e_doacoes():
    tabela = _form4("form4_pagamento.xml")  # M, F, G e S no mesmo formulário
    assert len(tabela) == 4 and set(tabela["operacao"]) == {ng.VENDA}
    assert len(ng.eventos_das_negociacoes(tabela)) == 1  # um evento por formulário


def test_form4_compra_e_de_outra_empresa(tmp_path):
    xml = (SEC / "form4_venda_plano.xml").read_text(encoding="utf-8")
    compra = (
        xml.replace(
            "<transactionCode>S</transactionCode>",
            "<transactionCode>P</transactionCode>",
        )
        .replace("<aff10b5One>true</aff10b5One>", "<aff10b5One>false</aff10b5One>")
        .encode()
    )
    tabela = form4.ler_form4(compra, APPLE, "p", date(2026, 10, 8), "https://x")
    assert tabela.iloc[0]["operacao"] == ng.COMPRA
    assert (
        ng.eventos_das_negociacoes(tabela).iloc[0]["materialidade"]
        == ng.MATERIALIDADE_DA_COMPRA
    )
    assert _form4(cik=789019).empty  # o formulário é da Apple, não da Microsoft


def test_lista_de_form4_da_empresa():
    lista = form4.formularios_4(
        (SEC / "CIK0000320193.json").read_bytes(), date(2025, 1, 1)
    )
    assert len(lista) == 84 and all(
        entregue >= date(2025, 1, 1) for _, entregue, _ in lista
    )
    assert form4.xml_puro("xslF345X06/form4.xml") == "form4.xml"


# --- resumos -----------------------------------------------------------------------------------
def test_resumo_e_saldo():
    tabela = pd.concat(
        [_form4(), _form4("form4_pagamento.xml", protocolo="0001-26-000002")]
    )
    resumo = ng.resumo_por_mes(tabela)
    assert (
        len(resumo) == 1
        and resumo["vendas"].iloc[0] < 0
        and resumo["compras"].iloc[0] == 0
    )
    saldo = ng.saldo_por_empresa(tabela).iloc[0]
    assert (
        saldo["saldo"] == pytest.approx(-saldo["vendas"]) and saldo["documentos"] == 2
    )
    assert ng.formatar_valor(None, "BRL") == "valor não informado"
    assert ng.formatar_valor(2_100_000, "BRL") == "R$ 2,1 mi"


# --- gravação ----------------------------------------------------------------------------------
def test_gravar_de_novo_nao_duplica_e_versao_nova_troca_o_documento(motor, da_cvm):
    with motor.begin() as c:
        documentos = da_cvm["documento"].nunique()
        assert repo.gravar_negociacoes(c, da_cvm) == (documentos, 0)
        assert repo.gravar_negociacoes(c, da_cvm) == (0, 0)
        um = da_cvm[da_cvm["documento"] == da_cvm["documento"].iloc[0]]
        nova = um.head(1).assign(versao=um["versao"].max() + 1, quantidade=1.0)
        assert repo.gravar_negociacoes(c, nova) == (0, 1)
        guardadas = repo.negociacoes(c, date(2000, 1, 1))
    assert len(guardadas) == len(da_cvm) - len(um) + 1


def test_documentos_lidos(motor):
    with motor.begin() as c:
        repo.marcar_como_lidos(c, ng.FONTE_FORM4, ["a", "b"])
        repo.marcar_como_lidos(
            c, ng.FONTE_FORM4, ["b", "c"]
        )  # sem erro de chave repetida
        assert repo.ja_lidos(c, ng.FONTE_FORM4, ["a", "c", "d"]) == {"a", "c"}
        assert repo.ja_lidos(c, ng.FONTE_VLMO, ["a"]) == set()


def test_migracao_0011_vai_e_volta(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}"
    migrar_para("head", url=url)
    assert {"negociacoes_internas", "documentos_lidos"} <= set(
        sa.inspect(criar_engine(url)).get_table_names()
    )
    desfazer_ate("0010", url=url)
    assert "negociacoes_internas" not in sa.inspect(criar_engine(url)).get_table_names()
    migrar_para("head", url=url)


# --- coletas -----------------------------------------------------------------------------------
def test_coleta_da_cvm_sem_internet(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'c.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    ano = datetime.now(FUSO).year

    def baixar_falso(endereco: str) -> bytes | None:
        if endereco == vlmo.URL_DO_VLMO.format(ano=ano):
            return (CVM / "vlmo_amostra.zip").read_bytes()
        return None  # o arquivo do ano anterior "ainda não existe"

    monkeypatch.setattr(atualizar_negociacoes_cvm, "baixar", baixar_falso)
    assert atualizar_negociacoes_cvm.main([]) == 0
    assert atualizar_negociacoes_cvm.main([]) == 0  # de novo: nada duplica
    with criar_engine(url).connect() as c:
        assert (
            c.execute(sa.text("select count(*) from negociacoes_internas")).scalar()
            == 129
        )
        fontes = (
            c.execute(sa.text("select distinct fonte from eventos")).scalars().all()
        )
    assert fontes == [ng.FONTE_VLMO]


def test_coleta_da_sec_le_cada_form4_uma_vez_e_respeita_o_limite(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 's.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv("TICKERLAB_CONTATO", "contato@tickerlab.com.br")
    monkeypatch.setattr(atualizar_eventos_sec, "PAUSA_ENTRE_CONSULTAS", 0)
    xmls = []

    def baixar_falso(endereco: str, agente: str) -> bytes:
        if endereco == sec.URL_DOS_TICKERS:
            return (SEC / "company_tickers.json").read_bytes()
        if endereco == sec.URL_DOS_DOCUMENTOS.format(cik=APPLE):
            return (SEC / "CIK0000320193.json").read_bytes()
        if endereco.endswith(".hdr.sgml"):
            return (SEC / "cabecalho_13g.hdr.sgml").read_bytes()
        if endereco.endswith(".xml"):
            xmls.append(endereco)
            return (SEC / "form4_venda_plano.xml").read_bytes()
        raise atualizar_eventos_sec.requests.HTTPError("503")

    monkeypatch.setattr(atualizar_eventos_sec, "baixar", baixar_falso)
    argumentos = ["--dias", "3650", "--dias-form4", "3650", "--max-form4", "30"]
    assert atualizar_eventos_sec.main(argumentos) == 0
    assert len(xmls) == 30  # o limite da execução
    assert atualizar_eventos_sec.main(argumentos) == 0
    assert len(xmls) == 60 and len(set(xmls)) == 60  # na segunda, só os ainda não lidos
    with criar_engine(url).connect() as c:
        assert (
            c.execute(sa.text("select count(*) from documentos_lidos")).scalar() == 60
        )
        assert (
            c.execute(sa.text("select count(*) from negociacoes_internas")).scalar()
            == 60
        )


# --- página ------------------------------------------------------------------------------------
def _coletar(banco, da_cvm):
    """Petrobras e WEG com datas recentes (os testes não dependem do calendário)."""
    hoje = datetime.now(FUSO).date()
    tabela = da_cvm.assign(entregue_em=hoje - timedelta(days=5))
    fca = io.BytesIO()
    with zipfile.ZipFile(fca, "w") as z:
        z.writestr(
            "fca_cia_aberta_valor_mobiliario_2026.csv",
            (CVM / "fca_vm_2026.csv").read_bytes(),
        )
    with banco.begin() as c:
        repo_eventos.gravar_tickers(c, ev.ler_tickers_do_fca([fca.getvalue()]))
        repo.gravar_negociacoes(c, tabela)


def _abrir(ticker="PETR4.SA") -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["ticker"] = ticker
    app.run()
    return ir_para(app, "por_dentro")


def test_pagina_sem_coleta_explica(banco):
    app = _abrir()
    assert not app.exception
    assert any("não tem cadastro na CVM nem na SEC" in i.value for i in app.info)


def test_pagina_mostra_o_ativo_e_o_mercado(banco, da_cvm):
    _coletar(banco, da_cvm)
    app = _abrir()
    assert not app.exception
    rotulos = {m.label for m in app.metric}
    assert {"Compras", "Vendas", "Saldo (compras − vendas)", "Documentos"} <= rotulos
    tabelas = [t.value for t in app.dataframe]
    negociacoes = next(t for t in tabelas if "Cargo" in t.columns)
    assert negociacoes["Abrir"].str.startswith("https://www.rad.cvm.gov.br/").all()
    ranking = [t for t in tabelas if "Saldo" in t.columns]
    assert ranking and any(
        "WEGE3" in set(t["Ativo"]) or "PETR3" in set(t["Ativo"]) for t in ranking
    )
    assert any(e.label == "Como ler estes dados" for e in app.expander)


def test_ativo_sem_cadastro(banco, da_cvm):
    _coletar(banco, da_cvm)
    app = _abrir("BTC-USD")
    assert not app.exception
    assert any("não tem cadastro na CVM nem na SEC" in i.value for i in app.info)
