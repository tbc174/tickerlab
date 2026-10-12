"""Carteira no Research (etapa 5, decisão 0020): só os pesos, com consentimento; a relevância
pela exposição; a exportação e a exclusão (LGPD); e a página Minha carteira."""

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from src import auditoria, carteira_research, research
from src import newsletter as nl
from src.banco import dados_do_usuario as repo
from src.banco import usuarios as contas
from src.banco.eventos import Evento
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.usuarios import mudar_plano
from src.carteira_b3 import ArquivoDaB3Error, CarteiraB3, ler_carteira
from src.conformidade import apagar_conta, exportar_meus_dados
from src.planos import LimiteDoPlanoError
from telas.research.minha_carteira import guardar_fotografia
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para

EXEMPLO = Path(__file__).parent.parent / "conteudo" / "carteira_de_exemplo.xlsx"
HOJE = date(2026, 10, 12)
PESOS_DO_EXEMPLO = {
    "PETR4.SA": 0.2877,
    "VALE3.SA": 0.1644,
    "ITUB4.SA": 0.1438,
    "WEGE3.SA": 0.0616,
}


def _exemplo() -> CarteiraB3:
    return ler_carteira(EXEMPLO.read_bytes(), EXEMPLO.name)


# --- a fotografia ---------------------------------------------------------------------------------
def test_fotografia_guarda_so_os_pesos_na_carteira_inteira():
    foto = carteira_research.fotografia(_exemplo(), HOJE)
    assert foto.pesos == PESOS_DO_EXEMPLO  # o Tesouro entra no total (soma 65,75%)
    assert list(foto.pesos) == list(PESOS_DO_EXEMPLO)  # do maior ao menor
    assert foto.enviada_em == HOJE


def test_fotografia_sem_ativos_com_valor_e_recusada():
    vazia = CarteiraB3(
        pd.DataFrame(columns=["codigo", "ticker", "tipo", "quantidade", "valor"]),
        pd.DataFrame([{"tipo": "Tesouro Direto", "produto": "Selic", "valor": 100.0}]),
    )
    with pytest.raises(ArquivoDaB3Error, match="não há o que guardar"):
        carteira_research.fotografia(vazia, HOJE)


def test_exposicao_maior_posicao_vale_um():
    assert carteira_research.exposicao({"A": 0.24, "B": 0.12}) == {"A": 1.0, "B": 0.5}
    assert carteira_research.exposicao({}) == {}


# --- a relevância (5b) ---------------------------------------------------------------------------
def _evento(ticker: str) -> Evento:
    return Evento(
        ticker=ticker, empresa=ticker, rotulo="Fato relevante", tema="eventos",
        materialidade=80, assunto="", referencia=None, publicado_em=HOJE, link="https://x",
        fonte="cvm_ipe", protocolo=ticker, versao=1,
    )  # fmt: skip


PESOS_DA_RELEVANCIA = dict(
    zip(research.COMPONENTES, (40, 20, 10, 10, 10, 10), strict=True)
)


def test_maior_posicao_vem_primeiro_e_explica_o_peso():
    foto = carteira_research.Fotografia(PESOS_DO_EXEMPLO, date(2026, 10, 10))
    eventos = [_evento("WEGE3.SA"), _evento("PETR4.SA"), _evento("VALE3.SA")]
    itens = research.ordenar(
        eventos,
        PESOS_DA_RELEVANCIA,
        [],
        HOJE,
        30,
        research.NOME_DA_CARTEIRA,
        carteira=foto,
    )
    assert [i.evento.ticker for i in itens] == ["PETR4.SA", "VALE3.SA", "WEGE3.SA"]
    assert itens[0].componentes["exposicao"] == 1.0
    assert itens[0].razoes[0] == (
        "A posição em PETR4 era 28,8% da sua carteira na fotografia de 10/10/2026."
    )


def test_sem_carteira_todo_ativo_pesa_igual():
    item = research.pontuar(
        _evento("WEGE3.SA"), PESOS_DA_RELEVANCIA, [], HOJE, 30, "Favoritos"
    )
    assert item.componentes["exposicao"] == 1.0
    assert item.razoes[0] == "Você acompanha WEGE3 na lista Favoritos."


def test_newsletter_da_carteira_diz_de_quando_e_a_fotografia():
    foto = carteira_research.Fotografia(PESOS_DO_EXEMPLO, date(2026, 10, 10))
    edicao = nl.montar(
        nl.Entrada(
            lista=research.NOME_DA_CARTEIRA, tickers=tuple(foto.pesos),
            eventos=(_evento("WEGE3.SA"), _evento("PETR4.SA")), pesos=PESOS_DA_RELEVANCIA,
            temas=(), hoje=HOJE, janela=7, max_itens=5,
            gerada_em=datetime(2026, 10, 12, 7, 0, tzinfo=UTC), carteira=foto,
        )
    )  # fmt: skip
    assert edicao.secao("destaques").itens[0].titulo.startswith("PETR4")
    assert any("fotografia da carteira de 10/10/2026" in p for p in edicao.parametros)


# --- o banco e a LGPD ----------------------------------------------------------------------------
def _usuario(conexao, sub):
    usuario, _ = contas.entrar(conexao, sub, f"{sub}@exemplo.com")
    return usuario.id


def _acoes_na_auditoria(conexao, usuario_id):
    return [
        linha.acao
        for linha in conexao.execute(
            sa.select(tabela_da_auditoria)
            .where(tabela_da_auditoria.c.alvo_id == usuario_id)
            .order_by(tabela_da_auditoria.c.criado_em)
        )
    ]


def test_so_o_pro_guarda_a_carteira(banco):
    foto = carteira_research.fotografia(_exemplo(), HOJE)
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        for plano in ("gratuito", "plus"):
            with pytest.raises(LimiteDoPlanoError, match="faz parte do Pro"):
                repo.salvar_carteira(c, ana, foto, plano=plano)
        repo.salvar_carteira(c, ana, foto, plano="pro")
        assert repo.carregar_carteira(c, ana) == foto


def test_guardar_de_novo_troca_a_fotografia(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.salvar_carteira(c, ana, carteira_research.fotografia(_exemplo(), HOJE))
        nova = carteira_research.Fotografia({"BBAS3.SA": 0.5}, date(2026, 10, 13))
        repo.salvar_carteira(c, ana, nova)
        assert repo.carregar_carteira(c, ana) == nova


def test_revogar_apaga_e_fica_so_o_registro(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.salvar_carteira(c, ana, carteira_research.fotografia(_exemplo(), HOJE))
        assert repo.revogar_carteira(c, ana)
        assert repo.carregar_carteira(c, ana) is None
        assert not repo.revogar_carteira(c, ana)  # nada mais a revogar
        assert _acoes_na_auditoria(c, ana) == [
            auditoria.ACAO_CARTEIRA_CONSENTIDA,
            auditoria.ACAO_CARTEIRA_REVOGADA,
        ]
        detalhes = c.execute(
            sa.select(tabela_da_auditoria.c.detalhes).where(
                tabela_da_auditoria.c.acao == auditoria.ACAO_CARTEIRA_CONSENTIDA
            )
        ).scalar_one()
    assert dict(detalhes) == {"versao": carteira_research.VERSAO_DO_CONSENTIMENTO}


def test_um_usuario_nao_ve_a_carteira_do_outro(banco):
    with banco.begin() as c:
        ana, bia = _usuario(c, "ana"), _usuario(c, "bia")
        repo.salvar_carteira(c, ana, carteira_research.fotografia(_exemplo(), HOJE))
        assert repo.carregar_carteira(c, bia) is None
        assert not repo.revogar_carteira(c, bia)
        assert repo.carregar_carteira(c, ana) is not None


def test_carteira_entra_na_exportacao_e_some_com_a_conta(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.salvar_carteira(c, ana, carteira_research.fotografia(_exemplo(), HOJE))
        (exportada,) = exportar_meus_dados(c, ana)["carteira_do_research"]
        assert exportada["pesos"] == PESOS_DO_EXEMPLO
        assert set(exportada) == {
            "pesos", "enviada_em", "versao_do_consentimento", "consentido_em",
        }  # fmt: skip
        assert apagar_conta(c, ana)
        assert repo.carregar_carteira(c, ana) is None


@pytest.mark.parametrize("nome", ["Minha carteira", "favoritos", "DEMONSTRAÇÃO"])
def test_listas_nao_usam_os_nomes_do_app(banco, nome):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        with pytest.raises(repo.DadosInvalidosError, match="nome de uma lista do app"):
            repo.salvar_watchlist(c, ana, nome, ["PETR4"])


# --- a página -------------------------------------------------------------------------------------
def _ana_no_plano(banco, monkeypatch, plano):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    ana = id_do_usuario(banco, "ana")
    with banco.begin() as c:
        mudar_plano(c, ana, plano)
    return ana


def test_pro_guarda_pela_tela_ve_e_revoga(banco, monkeypatch):
    # chama direto a função do botão (o AppTest não envia arquivos)
    ana = _ana_no_plano(banco, monkeypatch, "pro")
    with banco.connect() as c:
        usuario = contas.buscar_por_id(c, ana)
    ok, mensagem = guardar_fotografia(usuario, EXEMPLO.read_bytes(), EXEMPLO.name)
    assert ok and "4 ativos" in mensagem
    app = abrir_app("carteira_research")
    assert not app.exception
    tabela = app.dataframe[0].value
    assert list(tabela["Ativo"]) == ["PETR4", "VALE3", "ITUB4", "WEGE3"]
    assert "quantidade" not in " ".join(tabela.columns).lower()
    assert app.button(key="minha_carteira_revogar").disabled  # pede a confirmação antes
    app.checkbox(key="minha_carteira_confirma").check().run()
    app.button(key="minha_carteira_revogar").click().run()
    assert any("foi apagada" in s.value for s in app.success)
    with banco.connect() as c:
        assert repo.carregar_carteira(c, ana) is None


def test_carteira_aparece_como_lista_no_research(banco, monkeypatch):
    ana = _ana_no_plano(banco, monkeypatch, "pro")
    with banco.begin() as c:
        repo.salvar_carteira(c, ana, carteira_research.fotografia(_exemplo(), HOJE))
    app = abrir_app("research")
    assert research.NOME_DA_CARTEIRA in app.selectbox(key="research_lista").options


def test_planilha_ruim_mostra_o_erro(banco, monkeypatch):
    ana = _ana_no_plano(banco, monkeypatch, "pro")
    with banco.connect() as c:
        usuario = contas.buscar_por_id(c, ana)
    ok, mensagem = guardar_fotografia(usuario, b"nada a ver", "posicao.csv")
    assert not ok and mensagem
    with banco.connect() as c:
        assert repo.carregar_carteira(c, ana) is None


def test_gratuito_ve_que_e_do_pro_e_nao_ve_o_envio(banco, monkeypatch):
    _ana_no_plano(banco, monkeypatch, "gratuito")
    app = abrir_app("carteira_research")
    assert not app.exception
    assert any("faz parte do plano Pro" in i.value for i in app.info)
    assert not any(b.key == "minha_carteira_guardar" for b in app.button)


def test_sem_conta_pede_o_login(banco):
    app = AppTest.from_file("../app.py", default_timeout=120)  # modo local, sem login
    app.session_state["usar_exemplo"] = True
    app.run()
    app = ir_para(app, "carteira_research")
    assert not app.exception
    assert not any(b.key == "minha_carteira_guardar" for b in app.button)
    assert any("entre com o Google" in i.value for i in app.info)
