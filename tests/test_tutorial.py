"""O tutorial por objetivo: roteiros coerentes e, no app, os três caminhos de ponta a ponta."""

from io import BytesIO

import pandas as pd
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from src import relatorios, tutorial
from src.banco import dados_do_usuario as repo
from src.carteira_b3 import ler_carteira
from src.paginas import PAGINAS
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para

CHAVES_DAS_PAGINAS = {p.chave for p in PAGINAS}
ACOES_CONHECIDAS = {
    "escolheu_ativo",
    "leu_os_numeros",
    "viu_a_previa",
    "carregou_a_carteira",
    "trocou_o_estilo",
    "salvou_favorito",
}


# --- os roteiros ----------------------------------------------------------------------------
def test_todo_passo_acontece_numa_pagina_que_existe_e_diz_o_que_falta():
    for objetivo in tutorial.OBJETIVOS:
        roteiro = tutorial.passos(objetivo)
        assert 3 <= len(roteiro) <= 5  # 2 a 4 minutos, não uma aula
        for passo in roteiro:
            assert passo.pagina in CHAVES_DAS_PAGINAS
            if passo.condicao:
                assert passo.condicao in ACOES_CONHECIDAS and passo.pendente
        assert roteiro[-1].condicao is None  # o último passo é só fechar


def test_tarefas_apontam_para_paginas_que_existem():
    assert {t.pagina for t in tutorial.TAREFAS} <= CHAVES_DAS_PAGINAS
    assert tutorial.tarefas_pendentes({t.chave for t in tutorial.TAREFAS}) == []


def test_passo_atual_nunca_sai_do_roteiro():
    assert tutorial.passo_atual(tutorial.ANALISAR, -3).chave == "busque"
    assert tutorial.passo_atual(tutorial.ANALISAR, 99).chave == "pronto"


def test_carteira_de_exemplo_sai_marcada_como_demonstracao():
    with open("conteudo/carteira_de_exemplo.xlsx", "rb") as arquivo:
        carteira = ler_carteira(arquivo.read(), "carteira_de_exemplo.xlsx")
    fechamentos = pd.DataFrame(
        {
            t: pd.read_csv(f"dados_de_exemplo/{t}.csv", index_col=0, parse_dates=True)[
                "Close"
            ]
            for t in carteira.posicoes["ticker"]
        }
    )
    pdf = relatorios.relatorio_da_minha_carteira(
        carteira, fechamentos, demonstracao=True
    )
    leitor = PdfReader(BytesIO(pdf))
    assert "EXEMPLO DEMONSTRATIVO" in leitor.pages[0].extract_text()
    assert "FICTÍCIA" in leitor.pages[0].extract_text()
    # o cabeçalho de todas as páginas leva o título com "fictícia"
    assert all("fictícia" in p.extract_text() for p in leitor.pages[1:])


# --- no app ---------------------------------------------------------------------------------
def _inicio() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    return app.run()


def _botao(app, chave):
    return next(b for b in app.button if b.key == chave)


def _tem(app, chave) -> bool:
    return any(b.key == chave for b in app.button)


def test_inicio_mostra_as_tres_portas_e_a_lista_de_tarefas():
    app = _inicio()
    assert not app.exception
    for objetivo in tutorial.OBJETIVOS:
        assert _tem(app, f"tut_porta_{objetivo}")
    assert "Primeiros passos" in " ".join(m.value for m in app.markdown)
    app.button(key="tut_esconder").click().run()
    assert "Primeiros passos" not in " ".join(m.value for m in app.markdown)


def test_pular_esconde_as_portas_e_da_para_reabrir():
    app = _inicio()
    app.button(key="tut_pular_portas").click().run()
    assert not _tem(app, "tut_porta_analisar")
    app.button(key="tut_reabrir").click().run()
    assert _tem(app, "tut_porta_analisar")


def test_minha_primeira_analise_de_ponta_a_ponta():
    app = _inicio()
    app.button(key="tut_porta_analisar").click().run()
    assert _botao(app, "tut_seguir").disabled  # ainda não escolheu o ativo
    app.button_group(key="atalho_do_inicio").set_value("VALE3.SA").run()
    ir_para(app, "visao_geral")  # a escolha leva para a Visão geral
    assert not app.exception
    assert app.session_state["ticker"] == "VALE3.SA"
    assert not _botao(app, "tut_seguir").disabled
    app.button(key="tut_seguir").click().run()  # → período (só leitura)
    app.button(key="tut_seguir").click().run()  # → leia dois números
    assert _botao(app, "tut_seguir").disabled
    app.button(key="tut_ler").click().run()
    texto = " ".join(m.value for m in app.markdown)
    assert "Retorno total" in texto and "Maior queda" in texto and "passado" in texto
    app.button(key="tut_seguir").click().run()  # → guarde: abre o estúdio no Executivo
    ir_para(app, "relatorio")
    assert not app.exception
    assert app.session_state["relatorio_modelo"] == "executivo"
    assert app.session_state["relatorio_previas"]  # a prévia apareceu
    assert not _botao(app, "tut_seguir").disabled
    app.button(key="tut_seguir").click().run()  # → pronto
    app.button(key="tut_favoritar").click().run()
    assert "VALE3.SA" in app.session_state["favoritos"]
    app.button(key="tut_seguir").click().run()  # Concluir
    assert "tutorial" not in app.session_state
    assert app.session_state["tutorial_visto"]


def test_minha_carteira_com_o_exemplo_ficticio():
    app = _inicio()
    app.button(key="tut_porta_carteira").click().run()
    ir_para(app, "relatorio")
    assert not app.exception
    assert app.session_state["tipo_de_relatorio"] == "minha_carteira"
    assert _botao(app, "tut_seguir").disabled
    app.toggle(key="relatorio_carteira_exemplo").set_value(True).run()
    assert not app.exception
    assert "Exemplo demonstrativo" in " ".join(w.value for w in app.warning)
    assert not _botao(app, "tut_seguir").disabled
    app.button(key="tut_seguir").click().run()  # a prévia já está lá
    assert not _botao(app, "tut_seguir").disabled


def test_meu_primeiro_relatorio_pede_para_trocar_o_estilo():
    app = _inicio()
    app.button(key="tut_porta_relatorio").click().run()
    ir_para(app, "relatorio")
    app.button(key="tut_seguir").click().run()  # a prévia já apareceu
    assert _botao(app, "tut_seguir").disabled
    app.button_group(key="relatorio_estilo").set_value("terminal").run()
    assert not _botao(app, "tut_seguir").disabled


def test_com_conta_pular_fica_guardado(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    app.button(key="tut_pular_portas").click().run()
    with banco.connect() as conexao:
        guardadas = repo.carregar_preferencias(conexao, id_do_usuario(banco, "ana"))
    assert guardadas["tutorial_visto"] is True
    nova = abrir_app()  # outra sessão: as portas não voltam
    assert not _tem(nova, "tut_porta_analisar")
    ir_para(nova, "inicio")
    assert _tem(nova, "tut_reabrir")
