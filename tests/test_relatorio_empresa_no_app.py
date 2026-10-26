"""A página Relatório da empresa (série 2 da base de ML, PR 7) com as amostras reais da CVM, sem
internet: todas as seções, o aviso das notas, "não se aplica" nos bancos e o link a partir de
Fundamentos."""

from streamlit.testing.v1 import AppTest

from src.banco import dados_do_usuario as repo
from src.banco import pdfs_originais as pdfs
from src.banco.usuarios import mudar_plano
from src.relatorio_empresa import SECOES
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para
from tests.ajudantes_da_ficha import FICHA_DE_17_10
from tests.test_fundamentos_no_app import _coletar


def _abrir(ticker, pagina="relatorio_empresa") -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["ticker"] = ticker
    app.run()
    return ir_para(app, pagina)


def _textos(app):
    return " ".join(
        [m.value for m in app.markdown]
        + [c.value for c in app.caption]
        + [i.value for i in app.info]
    )


def test_pagina_mostra_as_secoes_e_o_aviso(banco):
    _coletar(banco)
    app = _abrir("PETR4.SA")
    assert not app.exception
    titulos = [s.value for s in app.subheader]
    assert titulos == list(SECOES.values())
    assert "não é recomendação" in _textos(app)
    metricas = {m.label: m.value for m in app.metric}
    receita = next(v for k, v in metricas.items() if k.startswith("Receita"))
    assert receita.startswith("R$ ")


def test_cada_numero_diz_como_foi_calculado(banco):
    """Item 7 do lançamento: o rastro do número em um clique, com a fórmula, a versão, a fonte,
    a publicação e o documento original."""
    _coletar(banco)
    app = _abrir("PETR4.SA")
    linhas = [m.value for m in app.markdown]
    assert any(
        linha.startswith("**Fórmula:** EBIT ÷ receita") for linha in linhas
    )  # a margem EBIT
    assert any(
        linha.startswith("**Versão do cálculo:** fundamentos") for linha in linhas
    )
    assert any(linha.startswith("**Fonte:** cvm") for linha in linhas)
    assert any(linha.startswith("**Publicado em:** ") for linha in linhas)
    assert any(
        linha.startswith("**Documento:** DFP") and "abrir o original" in linha
        for linha in linhas
    )
    assert any(
        linha.startswith("**Contas usadas:** as linhas da demonstração")
        for linha in linhas
    )
    assert any(
        linha.startswith("**Conta:** ") and "na CVM): R\\$ " in linha
        for linha in linhas
    )  # o valor guardado, com o cifrão que não vira LaTeX


def test_formula_com_cifrao_nao_vira_latex():
    from telas.research.relatorio_empresa import _literal

    assert _literal("R$ 1 * 2 $") == r"R\$ 1 \* 2 \$"


def test_banco_mostra_nao_se_aplica(banco):
    _coletar(banco)
    app = _abrir("ITUB4.SA")
    assert not app.exception
    assert "Não se aplica" in _textos(app)


def test_sem_cadastro_explica(banco):
    app = _abrir("BTC-USD")
    assert not app.exception
    assert any("B3" in i.value for i in app.info)
    assert not app.subheader


def test_fundamentos_tem_link_para_o_relatorio(banco):
    _coletar(banco)
    app = _abrir("PETR4.SA", pagina="fundamentos")
    assert not app.exception
    rotulos = [link.proto.label for link in app.get("page_link")]
    assert any("Relatório da empresa" in r for r in rotulos)


def _baixar(app):
    return [b for b in app.get("download_button") if b.proto.label == "Baixar o PDF"]


def test_no_modo_local_gera_e_baixa_o_pdf(banco):
    _coletar(banco)
    app = _abrir("PETR4.SA")
    assert not _baixar(app)
    app.button(key="empresa_gerar_pdf").click().run()
    assert not app.exception
    assert _baixar(app)


def test_plano_gratuito_nao_gera_o_pdf_e_nada_conta(banco, monkeypatch):
    _coletar(banco)
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("relatorio_empresa")
    app.button(key="empresa_gerar_pdf").click().run()
    assert not app.exception
    assert not _baixar(app)
    assert any("plano" in w.value.lower() for w in app.warning)
    with banco.connect() as conexao:
        assert (
            repo.contar_relatorios_recentes(conexao, id_do_usuario(banco, "ana")) == 0
        )


def test_plano_pro_registra_guarda_o_original_e_reabre_na_pagina(banco, monkeypatch):
    _coletar(banco)
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()  # o primeiro acesso cria a conta
    ana = id_do_usuario(banco, "ana")
    with banco.begin() as conexao:
        mudar_plano(conexao, ana, "pro")
    app = abrir_app("relatorio_empresa")
    app.button(key="empresa_gerar_pdf").click().run()
    assert not app.exception and _baixar(app)
    with banco.connect() as conexao:
        (item,) = repo.biblioteca_de_relatorios(conexao, ana)
        assert item.tipo == "empresa" and item.parametros["ticker"] == "PETR4.SA"
        assert pdfs.baixar_pdf_original(conexao, ana, item.id).startswith(b"%PDF")
    ir_para(app, "relatorio")
    app.button(key=f"estudio_reabrir_{item.id}").click().run()
    assert not app.exception
    primeira = next(iter(SECOES.values()))
    assert [s.value for s in app.subheader][:1] == [primeira]  # voltou à página


# --- dossiê da base (plano do dossiê da empresa no app, PR 3) ---------------------------------------


def _ficha_da_petrobras(tmp_path, monkeypatch):
    """A ficha de exemplo (CPFL) gravada como se fosse a da Petrobras, na pasta das fichas."""
    import json

    bruta = json.loads(FICHA_DE_17_10.read_text(encoding="utf-8"))
    atual = tmp_path / "atual"
    atual.mkdir()
    (atual / "33000167000101.json").write_text(
        json.dumps(bruta | {"cnpj": "33000167000101"}), encoding="utf-8"
    )
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(tmp_path))


def test_no_modo_local_mostra_o_dossie_da_base(banco, tmp_path, monkeypatch):
    _coletar(banco)
    _ficha_da_petrobras(tmp_path, monkeypatch)
    app = _abrir("PETR4.SA")
    assert not app.exception
    titulos = [s.value for s in app.subheader]
    capital = titulos.index(
        SECOES["dividendos"]
    )  # capital e acionistas, depois governança
    assert titulos[capital + 1 : capital + 3] == [
        "Ofertas e fundos",
        "Auditor e controladas",
    ]
    assert "R$ 495,2 mi" in [m.value for m in app.metric]
    assert "Fundos com a empresa, mês a mês" in [e.label for e in app.expander]


def test_plano_gratuito_ve_o_convite_sem_os_numeros(banco, tmp_path, monkeypatch):
    _coletar(banco)
    _ficha_da_petrobras(tmp_path, monkeypatch)
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("relatorio_empresa")
    assert not app.exception
    assert "Auditor e controladas" in [s.value for s in app.subheader]
    assert any("plano Pro" in i.value for i in app.info)
    assert "R$ 495,2 mi" not in [m.value for m in app.metric]
    assert "PRICEWATERHOUSECOOPERS" not in _textos(app) + " ".join(
        m.value for m in app.metric
    )
    rotulos = [link.proto.label for link in app.get("page_link")]
    assert rotulos.count("Conhecer o plano Pro") == 1


def test_no_modo_local_gera_e_baixa_o_deck_em_pdf_e_ppt(banco):
    _coletar(banco)
    app = _abrir("PETR4.SA")
    assert not [b for b in app.get("download_button") if "deck" in b.proto.label]
    app.button(key="empresa_gerar_deck").click().run()
    assert not app.exception
    rotulos = [b.proto.label for b in app.get("download_button")]
    assert "Baixar o deck (PDF)" in rotulos
    assert "Baixar o deck (PPT)" in rotulos
    # o deck não conta como relatório do plano
    assert "Baixar o PDF" not in rotulos


def test_indicadores_sem_preco_aparecem_na_pagina(banco):
    """Linha 54 da fila: os números novos chegam à tela, cada um com o valor escrito."""
    _coletar(banco)
    app = _abrir("PETR4.SA")
    assert not app.exception
    metricas = {m.label: m.value for m in app.metric}
    for nome in (
        "Margem EBITDA",
        "ROA (retorno sobre o ativo)",
        "Dívida líquida / EBITDA",
        "Dívida líquida / EBIT",
        "Passivos / ativos",
        "Patrimônio / ativos",
        "Liquidez corrente",
        "Dividendo por ação",
        "Payout (pago sobre o lucro)",
        "Crescimento do dividendo por ação",
        "Ações em circulação",
    ):
        assert any(rotulo.startswith(nome) for rotulo in metricas), nome
    acoes = next(v for k, v in metricas.items() if k.startswith("Ações em circulação"))
    assert " ON e " in acoes and " PN)" in acoes


def test_trava_desligada_a_pagina_nem_pede_o_preco(banco, monkeypatch):
    """Linha 413, Y1 (a), "pode" do Tiago em 25/10/2026: com a trava desligada, a ficha mostra as
    seções sem carregar a série do ticker do topo (que vem do Yahoo)."""

    def nao_pode():
        raise AssertionError("a ficha pediu o preço com a trava desligada")

    _coletar(banco)
    monkeypatch.setenv("TICKERLAB_PRECO_NO_RELATORIO", "0")
    monkeypatch.setattr("telas.research.relatorio_empresa.carregar_contexto", nao_pode)
    app = _abrir("PETR4.SA")
    assert not app.exception
    assert [s.value for s in app.subheader] == list(SECOES.values())
