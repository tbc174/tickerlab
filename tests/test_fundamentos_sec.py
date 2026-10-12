"""Fundamentos das empresas dos EUA pelo XBRL da SEC (`companyfacts`), sem internet.

Amostras reais e reduzidas (só os conceitos usados, relatórios desde 2019): Apple (ano fiscal
termina em setembro), Walmart (em janeiro, com minoritários) e JPMorgan (banco).
"""

from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from scripts import atualizar_eventos_sec
from src import eventos_sec as sec
from src import fundamentos as fu
from src import fundamentos_sec as fs
from src.banco import demonstracoes as repo
from src.banco import eventos as repo_eventos
from src.banco.conexao import criar_engine
from src.banco.demonstracoes import DadosDaEmpresa
from src.demonstracoes import ACUMULADO, ACUMULADO_ANTERIOR, EXERCICIO, POSICAO
from tests.ajudantes_da_conta import ir_para

SEC = Path(__file__).parent / "arquivos" / "sec"
HOJE = date(2026, 10, 11)


def _ler(nome):
    return fs.ler_companyfacts((SEC / f"fatos_{nome}.json").read_bytes(), HOJE)


def _calcular(nome, setor="", preco=None):
    contas, docs = _ler(nome)
    dados = DadosDaEmpresa(
        contas.drop(columns="cnpj"), docs.drop(columns="cnpj"), setor
    )
    return fu.calcular(dados, preco, aliquota=fu.ALIQUOTA_DOS_EUA)


# --- leitura -----------------------------------------------------------------------------------
def test_apple_vira_contas_e_documentos_no_formato_da_cvm():
    contas, docs = _ler("apple")
    assert set(docs["documento"]) == {"DFP", "ITR"}
    assert (contas["cnpj"] == "CIK0000320193").all()
    assert (
        docs["link"]
        .str.startswith("https://www.sec.gov/Archives/edgar/data/320193/")
        .all()
    )
    ultimo = contas[
        contas["referencia"] == date(2026, 6, 27)
    ]  # 10-Q do 3º trimestre fiscal
    periodos = set(zip(ultimo["conta"], ultimo["periodo"], strict=True))
    assert {
        ("receita", ACUMULADO),
        ("receita", ACUMULADO_ANTERIOR),
        ("acoes_total", POSICAO),
    } <= periodos
    anual = contas[(contas["documento"] == "DFP") & (contas["periodo"] == EXERCICIO)]
    assert set(anual["referencia"]) >= {
        date(2025, 9, 27)
    }  # o ano fiscal termina em setembro


def test_receita_muda_de_nome_e_continua_achada():
    contas, _ = _ler("apple")
    anos = contas[(contas["conta"] == "receita") & (contas["periodo"] == EXERCICIO)]
    assert {r.year for r in anos["referencia"]} >= {2020, 2021, 2022, 2023, 2024, 2025}


def test_ultimo_relatorio_da_lista_de_documentos():
    ultimo, _ = fs.ultimo_relatorio((SEC / "CIK0000320193.json").read_bytes())
    assert ultimo == date(2026, 6, 27)


# --- cálculo -----------------------------------------------------------------------------------
def test_apple_doze_meses_com_ano_fiscal_em_setembro():
    resultado = _calcular("apple", "Electronic Computers", preco=330.0)
    assert not resultado.financeira
    receita = resultado["receita"]
    assert receita.base == "12 meses até 27/06/2026"
    assert 4.0e11 < receita.valor < 5.5e11  # ~US$ 467 bi
    assert resultado["p_l"].disponivel and resultado["roic"].disponivel
    assert resultado.notas == []  # ações conferidas com o lucro por ação


def test_walmart_usa_o_anual_de_janeiro_e_os_minoritarios():
    contas, _ = _ler("walmart")
    _, base, usados = fu.doze_meses(contas)
    assert base == "12 meses até 31/07/2026"
    assert usados == [("DFP", date(2026, 1, 31)), ("ITR", date(2026, 7, 31))]
    resultado = _calcular("walmart", "Retail-Variety Stores")
    assert resultado["roe"].disponivel


def test_jpmorgan_e_banco():
    resultado = _calcular("jpmorgan", "National Commercial Banks")
    assert resultado.financeira
    assert not resultado["margem_ebit"].disponivel and resultado["roe"].disponivel
    assert _calcular(
        "jpmorgan"
    ).financeira  # sem setor: a falta de EBIT denuncia o banco


def test_anual_velho_demais_nao_entra_nos_doze_meses():
    contas, _ = _ler("apple")
    sem_o_ultimo_anual = contas[
        ~((contas["documento"] == "DFP") & (contas["referencia"] == date(2025, 9, 27)))
    ]
    _, base, usados = fu.doze_meses(sem_o_ultimo_anual)
    assert base.startswith("exercício encerrado") and usados == [
        ("DFP", date(2024, 9, 28))
    ]


def test_roic_usa_o_imposto_do_pais():
    contas, docs = _ler("apple")
    dados = DadosDaEmpresa(contas.drop(columns="cnpj"), docs.drop(columns="cnpj"), "")
    eua = fu.calcular(dados, None, aliquota=fu.ALIQUOTA_DOS_EUA)["roic"].valor
    brasil = fu.calcular(dados, None)["roic"].valor
    assert eua / brasil == pytest.approx((1 - 0.21) / (1 - 0.34))


# --- gravação e coleta -------------------------------------------------------------------------
def test_setores_da_cvm_e_da_sec_nao_se_apagam(banco):
    with banco.begin() as c:
        repo.gravar_setor(c, "CIK0000320193", "Electronic Computers")
        repo.gravar_setores(
            c, __import__("pandas").DataFrame({"cnpj": ["1"], "setor": ["Bancos"]})
        )
        setores = dict(c.execute(sa.text("select cnpj, setor from setores_cvm")).all())
    assert setores == {"CIK0000320193": "Electronic Computers", "1": "Bancos"}


def test_coleta_da_sec_grava_os_balancos_so_quando_ha_relatorio_novo(
    tmp_path, monkeypatch
):
    url = f"sqlite:///{(tmp_path / 'f.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv("TICKERLAB_CONTATO", "contato@tickerlab.com.br")
    monkeypatch.setattr(atualizar_eventos_sec, "PAUSA_ENTRE_CONSULTAS", 0)
    pedidos = []

    def baixar_falso(endereco: str, agente: str) -> bytes:
        if endereco == sec.URL_DOS_TICKERS:
            return (SEC / "company_tickers.json").read_bytes()
        if endereco == sec.URL_DOS_DOCUMENTOS.format(cik=320193):
            return (SEC / "CIK0000320193.json").read_bytes()
        if endereco == fs.URL_DOS_FATOS.format(cik=320193):
            pedidos.append(endereco)
            return (SEC / "fatos_apple.json").read_bytes()
        if endereco.endswith(".hdr.sgml"):
            return (SEC / "cabecalho_13g.hdr.sgml").read_bytes()
        raise atualizar_eventos_sec.requests.HTTPError("503")

    monkeypatch.setattr(atualizar_eventos_sec, "baixar", baixar_falso)
    argumentos = ["--max-form4", "0"]  # sem Form 4 neste teste
    assert atualizar_eventos_sec.main(argumentos) == 0
    assert atualizar_eventos_sec.main(argumentos) == 0
    assert len(pedidos) == 1  # na segunda vez o último 10-Q já estava guardado
    with criar_engine(url).connect() as c:
        documentos = c.execute(
            sa.text(
                "select count(*) from documentos_financeiros where cnpj = 'CIK0000320193'"
            )
        ).scalar()
        dados = repo.dados_da_empresa(c, "CIK0000320193")
    assert documentos > 0 and not dados.contas.empty


# --- página ------------------------------------------------------------------------------------
def _abrir(ticker) -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["ticker"] = ticker
    app.run()
    return ir_para(app, "fundamentos")


def _coletar_apple(banco):
    contas, docs = _ler("apple")
    mapa = sec.ler_tickers((SEC / "company_tickers.json").read_bytes(), {"AAPL"})
    with banco.begin() as c:
        repo_eventos.gravar_tickers(c, mapa, origem=repo_eventos.ORIGEM_SEC)
        repo.gravar_setor(c, "CIK0000320193", "Electronic Computers")
        repo.gravar_demonstracoes(c, contas, docs)


def test_pagina_fundamentos_de_empresa_dos_eua(banco):
    _coletar_apple(banco)
    app = _abrir("AAPL")
    assert not app.exception
    metricas = {m.label: m.value for m in app.metric}
    assert metricas["Receita (12 meses)"].startswith("US$ ")
    assert "CIK 320193" in " ".join(m.value for m in app.markdown)
    documentos = next(t.value for t in app.dataframe if "Abrir" in t.value.columns)
    assert "Entregue à SEC" in documentos.columns
    assert set(documentos["Documento"]) <= {"Anual (10-K)", "Trimestral (10-Q)"}
    assert documentos["Abrir"].str.startswith("https://www.sec.gov/").all()
    metodo = next(
        e for e in app.expander if e.label == "Como estes números são calculados"
    )
    assert "21%" in metodo.markdown[0].value and "10-K" in metodo.markdown[0].value


def test_empresa_dos_eua_ainda_sem_balancos(banco):
    mapa = sec.ler_tickers((SEC / "company_tickers.json").read_bytes(), {"AAPL"})
    with banco.begin() as c:
        repo_eventos.gravar_tickers(c, mapa, origem=repo_eventos.ORIGEM_SEC)
    app = _abrir("AAPL")
    assert not app.exception
    assert any("Ainda não há demonstrações coletadas" in i.value for i in app.info)
