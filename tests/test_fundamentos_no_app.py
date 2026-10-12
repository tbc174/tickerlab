"""A página Fundamentos (Research, etapa 3c) com as amostras reais da CVM, sem internet."""

import io
import zipfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src import demonstracoes as dm
from src import eventos as ev
from src.banco import demonstracoes as repo
from src.banco import eventos as repo_eventos
from src.presets import Preset
from tests.ajudantes_da_conta import ir_para

CVM = Path(__file__).parent / "arquivos" / "cvm"


def _zip(nome, arquivo):
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, (CVM / arquivo).read_bytes())
    return saida.getvalue()


def _coletar(banco):
    tickers = ev.ler_tickers_do_fca(
        [
            _zip("fca_cia_aberta_valor_mobiliario_2024.csv", "fca_vm_2024.csv"),
            _zip("fca_cia_aberta_valor_mobiliario_2026.csv", "fca_vm_2026.csv"),
        ]
    )
    with banco.begin() as c:
        repo_eventos.gravar_tickers(c, tickers)
        repo.gravar_setores(
            c, dm.ler_setores((CVM / "fundamentos" / "cad_cia_aberta.csv").read_bytes())
        )
        for arquivo, documento in (
            ("dfp_cia_aberta_2024.zip", "DFP"),
            ("dfp_cia_aberta_2025.zip", "DFP"),
            ("itr_cia_aberta_2026.zip", "ITR"),
        ):
            repo.gravar_demonstracoes(
                c,
                *dm.ler_demonstracoes(
                    (CVM / "fundamentos" / arquivo).read_bytes(), documento
                ),
            )


def _abrir(ticker, parametros=None) -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["ticker"] = ticker
    if parametros:
        app.session_state["presets_locais"] = [
            Preset(escopo="global", parametros=parametros)
        ]
    app.run()
    return ir_para(app, "fundamentos")


def _metricas(app):
    return {m.label: m.value for m in app.metric}


def test_sem_cadastro_explica_a_cobertura(banco):
    app = _abrir("BTC-USD")
    assert not app.exception
    assert any("não tem cadastro na CVM nem na SEC" in i.value for i in app.info)
    assert not app.metric


def test_empresa_comum_mostra_indicadores_documentos_e_metodo(banco):
    _coletar(banco)
    app = _abrir("PETR4.SA")
    assert not app.exception
    metricas = _metricas(app)
    assert metricas["Receita (12 meses)"].startswith("R$ ") and metricas[
        "Receita (12 meses)"
    ].endswith(" bi")
    assert (
        metricas["Margem EBIT"].endswith("%")
        and metricas["P/L (preço / lucro por ação)"] != "—"
    )
    legendas = " ".join(c.value for c in app.caption)
    assert "aplicado a todas as classes de ação" in legendas
    tabelas = [t.value for t in app.dataframe]
    documentos = next(t for t in tabelas if "Abrir" in t.columns)
    assert documentos["Abrir"].str.startswith("https://www.rad.cvm.gov.br/").all()
    assert set(documentos["Documento"]) == {"Anual (DFP)", "Trimestral (ITR)"}
    assert any(e.label == "Como estes números são calculados" for e in app.expander)


def test_banco_mostra_o_aviso_e_nao_se_aplica(banco):
    _coletar(banco)
    app = _abrir("ITUB4.SA")
    assert not app.exception
    assert any("bancos e seguradoras" in i.value for i in app.info)
    metricas = _metricas(app)
    assert (
        metricas["Margem EBIT"] == "—"
        and metricas["ROE (retorno sobre o patrimônio)"] != "—"
    )
    assert "milhares" in " ".join(
        c.value for c in app.caption
    )  # ações do Itaú corrigidas


def test_parametros_do_usuario_mudam_o_horizonte_e_os_filtros(banco):
    _coletar(banco)
    padrao = _metricas(_abrir("WEGE3.SA"))
    assert (
        padrao["Crescimento da receita (5 anos, ao ano)"] == "—"
    )  # só 2 anos nas amostras
    app = _abrir(
        "WEGE3.SA",
        {
            "fundamentalista.anos": 1,
            "fundamentalista.roic_minimo": 50.0,
            "fundamentalista.pl_maximo": 100.0,
        },
    )
    metricas = _metricas(app)
    assert metricas["Crescimento da receita (1 anos, ao ano)"].endswith("%")
    texto = " ".join(m.value for m in app.markdown)
    assert (
        "abaixo do seu filtro de 50%" in texto
        and "dentro do seu filtro de até 100" in texto
    )
    assert "Usando os seus parâmetros" in " ".join(c.value for c in app.caption)
