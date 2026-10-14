"""Research etapa 2b: relevância explicável, watchlists e a página Acontecimentos."""

import io
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import eventos as ev
from src import research
from src.banco import dados_do_usuario as repo
from src.banco import eventos as repo_eventos
from src.banco import usuarios as contas
from src.banco.eventos import Evento
from src.banco.usuarios import mudar_plano
from src.conformidade import apagar_conta, exportar_meus_dados
from src.planos import LimiteDoPlanoError
from src.relatorios import FUSO
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para

PASTA = Path(__file__).parent / "arquivos" / "cvm"
HOJE = date(2026, 10, 11)
PESOS = {
    c: v for c, v in zip(research.COMPONENTES, (25, 25, 15, 15, 15, 5), strict=True)
}


def _evento(ticker="PETR4.SA", rotulo="Comunicado ao mercado", tema="eventos",
            materialidade=40, dias=1, versao=1):  # fmt: skip
    return Evento(
        ticker=ticker, empresa="EMPRESA", rotulo=rotulo, tema=tema,
        materialidade=materialidade, assunto="Assunto", referencia=None,
        publicado_em=HOJE - timedelta(days=dias), link="https://www.rad.cvm.gov.br/x",
        fonte="cvm_ipe", protocolo=f"p{ticker}{dias}{materialidade}", versao=versao,
    )  # fmt: skip


# --- relevância --------------------------------------------------------------------------------
def test_relevancia_soma_os_componentes_com_os_pesos():
    item = research.pontuar(
        _evento(materialidade=100, tema="eventos", dias=0),
        PESOS,
        ["eventos"],
        HOJE,
        30,
        "Teste",
    )
    assert item.relevancia == 1.0  # tudo no máximo
    item = research.pontuar(
        _evento(materialidade=40, tema="risco", dias=15),
        PESOS,
        ["eventos"],
        HOJE,
        30,
        "Teste",
    )
    esperado = (25 * 1 + 25 * 0.4 + 15 * 1 + 15 * 1 + 15 * 0 + 5 * 0.5) / 100
    assert item.relevancia == pytest.approx(esperado)


def test_razoes_explicam_cada_parte():
    item = research.pontuar(
        _evento(versao=2), PESOS, ["eventos"], HOJE, 30, "Favoritos"
    )
    texto = " ".join(item.razoes)
    assert "Você acompanha PETR4 na lista Favoritos" in texto
    assert "materialidade 40" in texto and "entre os seus temas" in texto
    assert "reapresentação (versão 2)" in texto and "há 1 dia" in texto


def test_pesos_do_usuario_mudam_a_ordem():
    fato_antigo = _evento(rotulo="Fato relevante", materialidade=100, dias=25)
    comunicado_novo = _evento(ticker="VALE3.SA", materialidade=40, dias=0)
    so_recencia = dict.fromkeys(research.COMPONENTES, 0) | {"recencia": 100}
    so_materialidade = dict.fromkeys(research.COMPONENTES, 0) | {"materialidade": 100}
    eventos = [fato_antigo, comunicado_novo]
    assert (
        research.ordenar(eventos, so_recencia, [], HOJE, 30, "L")[0].evento
        is comunicado_novo
    )
    assert (
        research.ordenar(eventos, so_materialidade, [], HOJE, 30, "L")[0].evento
        is fato_antigo
    )


def test_uma_empresa_nao_domina_a_lista():
    muitos = [_evento(dias=d) for d in range(8)] + [_evento(ticker="VALE3.SA", dias=9)]
    itens = research.ordenar(muitos, PESOS, [], HOJE, 30, "L", maximo_por_ativo=3)
    assert sum(i.evento.ticker == "PETR4.SA" for i in itens) == 3
    assert any(i.evento.ticker == "VALE3.SA" for i in itens)


# --- watchlists no banco ------------------------------------------------------------------------
def _usuario(conexao, sub):
    usuario, _ = contas.entrar(conexao, sub, f"{sub}@exemplo.com")
    return usuario.id


def test_watchlist_cria_normaliza_e_recusa_nome_repetido(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.salvar_watchlist(c, ana, "  Bancos  ", ["itub4", "BBAS3.SA", "itub4"])
        (lista,) = repo.listar_watchlists(c, ana)
        assert (lista.nome, lista.tickers) == ("Bancos", ["ITUB4.SA", "BBAS3.SA"])
        with pytest.raises(repo.DadosInvalidosError, match="já tem uma lista"):
            repo.salvar_watchlist(c, ana, "bancos", ["PETR4"])
        with pytest.raises(repo.DadosInvalidosError, match="inválido"):
            repo.salvar_watchlist(c, ana, "Outra", ["não é ticker!"])


def test_limites_das_listas_por_plano(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.salvar_watchlist(c, ana, "Uma", ["PETR4"], plano="gratuito")
        with pytest.raises(LimiteDoPlanoError, match="1 lista"):
            repo.salvar_watchlist(c, ana, "Duas", ["VALE3"], plano="gratuito")
        with pytest.raises(LimiteDoPlanoError, match="até 10 ativos"):
            repo.salvar_watchlist(c, ana, "Uma", [f"AAAA{i}" for i in range(11)], plano="gratuito",
                                  watchlist_id=repo.listar_watchlists(c, ana)[0].id)  # fmt: skip
        assert repo.salvar_watchlist(c, ana, "Duas", ["VALE3"], plano="pro")


def test_um_usuario_nao_mexe_na_lista_do_outro(banco):
    with banco.begin() as c:
        ana, bia = _usuario(c, "ana"), _usuario(c, "bia")
        lista = repo.salvar_watchlist(c, ana, "Minha", ["PETR4"])
        assert repo.listar_watchlists(c, bia) == []
        with pytest.raises(repo.DadosInvalidosError, match="não encontrada"):
            repo.salvar_watchlist(c, bia, "Roubada", ["VALE3"], watchlist_id=lista)
        assert not repo.apagar_watchlist(c, bia, lista)
        assert repo.listar_watchlists(c, ana)[0].nome == "Minha"


def test_listas_entram_na_exportacao_e_somem_com_a_conta(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.salvar_watchlist(c, ana, "Minha", ["PETR4"])
        assert exportar_meus_dados(c, ana)["listas_do_research"][0]["tickers"] == [
            "PETR4.SA"
        ]
        assert apagar_conta(c, ana)
        assert repo.listar_watchlists(c, ana) == []


# --- a página ----------------------------------------------------------------------------------
def _zip(nome, arquivo):
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, (PASTA / arquivo).read_bytes())
    return saida.getvalue()


def _coletar(banco):
    """Grava a amostra real da CVM com datas recentes (os testes não dependem do calendário)."""
    hoje = datetime.now(FUSO).date()  # o mesmo "hoje" da página (São Paulo)
    tabela = ev.ler_ipe(_zip("ipe_cia_aberta_2026.csv", "ipe_amostra.csv")).reset_index(
        drop=True
    )
    tabela["publicado_em"] = [hoje - timedelta(days=i % 20) for i in range(len(tabela))]
    tickers = ev.ler_tickers_do_fca(
        [_zip("fca_cia_aberta_valor_mobiliario_2026.csv", "fca_vm_2026.csv")]
    )
    with banco.begin() as c:
        repo_eventos.gravar_tickers(c, tickers)
        repo_eventos.gravar_eventos(c, tabela)


def _app_local(favoritos=None) -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    if favoritos:
        app.session_state["favoritos"] = favoritos
    app.run()
    return ir_para(app, "research")


def test_sem_coleta_a_pagina_explica_e_nao_inventa_nada(banco):
    app = _app_local()
    assert not app.exception
    assert any("ainda não foram coletados" in i.value for i in app.info)


def test_demonstracao_mostra_eventos_com_link_e_razoes(banco):
    _coletar(banco)
    app = _app_local()
    assert not app.exception
    assert app.selectbox(key="research_lista").value == "Demonstração"
    legendas = " ".join(c.value for c in app.caption)
    assert "dados abertos da CVM" in legendas and "coletados em" in legendas
    assert app.get("link_button") and all(
        b.proto.url.startswith("https://www.rad.cvm.gov.br/")
        for b in app.get("link_button")
    )
    assert any(e.label == "Por que isso aparece?" for e in app.expander)
    assert "Você acompanha" in " ".join(m.value for m in app.markdown)


def test_favoritos_mostram_quem_nao_tem_cobertura(banco):
    _coletar(banco)
    app = _app_local(favoritos=["PETR4.SA", "AAPL"])
    app.selectbox(key="research_lista").set_value("Favoritos").run()
    assert not app.exception
    assert "Sem cobertura ainda: AAPL" in " ".join(c.value for c in app.caption)


def test_analisar_a_partir_do_evento_abre_a_visao_geral(banco):
    _coletar(banco)
    app = _app_local()
    chave = next(
        b.key for b in app.button if b.key and b.key.startswith("research_analisar_")
    )
    app.button(key=chave).click().run()
    assert not app.exception
    assert app.session_state["ticker"].endswith(".SA")


def test_com_conta_cria_edita_e_apaga_uma_lista(banco, monkeypatch):
    _coletar(banco)
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("research")
    app.text_input(key="research_nova_nome").set_value("Petróleo")
    app.multiselect(key="research_nova_tickers").set_value(["PETR4.SA"])
    app.button(key="rsb_criar").click().run()
    assert not app.exception
    ana = id_do_usuario(banco, "ana")
    with banco.connect() as c:
        (lista,) = repo.listar_watchlists(c, ana)
    assert lista.tickers == ["PETR4.SA"]
    app.run()
    assert app.selectbox(key="research_lista").value == "Petróleo"
    app.button(key="rsb_apagar").click().run()
    with banco.connect() as c:
        assert repo.listar_watchlists(c, ana) == []


def test_gratuito_nao_cria_a_segunda_lista(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app("research")
    ana = id_do_usuario(banco, "ana")
    with banco.begin() as c:
        repo.salvar_watchlist(c, ana, "Uma", ["PETR4"])
        mudar_plano(c, ana, "gratuito")
    app = abrir_app("research")
    app.text_input(key="research_nova_nome").set_value("Duas")
    app.multiselect(key="research_nova_tickers").set_value(["VALE3.SA"])
    app.button(key="rsb_criar").click().run()
    assert any("1 lista" in e.value for e in app.error)


# --- leitor v2: o assunto dos fatos relevantes (ADR 0069, PR 4) ----------------------------------


def _textos_da_pagina(app) -> str:
    return " ".join(m.value for m in app.markdown)


def _com_todos_os_eventos(app):
    """Sem tema marcado aparecem todos, e sem o limite por empresa (os fatos são tema "eventos")."""
    app.button_group(key="research_temas").set_value([]).run()
    return app.toggle(key="research_todos").set_value(True).run()


def test_fato_relevante_mostra_o_assunto_e_o_por_que(banco):
    _coletar(banco)
    app = _com_todos_os_eventos(_app_local())
    assert not app.exception
    # "Relatório de Produção e Vendas 4T25": o assunto sai do título, com o selo
    assert ":blue-badge[Resultados e projeções]" in _textos_da_pagina(app)
    porques = [e for e in app.expander if e.label == "Por que isso aparece?"]
    textos = " ".join(m.value for e in porques for m in e.markdown)
    assert "Assunto (pelo título): “Relatório de Produção e Vendas 4T25”" in textos
    # os que ficam em "Outros" não ganham selo
    assert ":blue-badge[Outros]" not in _textos_da_pagina(app)


def test_filtro_pelo_assunto_dos_fatos_relevantes(banco):
    _coletar(banco)
    app = _com_todos_os_eventos(_app_local())
    filtro = app.multiselect(key="research_topicos")
    assert filtro.options == [
        "Resultados e projeções"
    ]  # só os assuntos que aparecem na lista
    app = filtro.select("Resultados e projeções").run()
    assert not app.exception
    titulos = [
        m.value for m in app.markdown if "Relatório de Produção e Vendas" in m.value
    ]
    assert titulos
    assert "Reservas Provadas" not in _textos_da_pagina(app)
