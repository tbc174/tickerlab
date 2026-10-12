"""Newsletter do Research (etapa 4): a edição (função pura), o PDF no Report Studio e a página."""

from datetime import UTC, date, datetime, timedelta
from io import BytesIO

import pytest
import sqlalchemy as sa
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from src import newsletter as nl
from src import relatorios, research
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.eventos import Evento
from src.planos import LimiteDoPlanoError, conferir_relatorio
from src.relatorio_newsletter import relatorio_da_newsletter
from tests.ajudantes_da_conta import ir_para
from tests.test_research_no_app import _coletar

HOJE = date(2026, 10, 11)
PESOS = dict(zip(research.COMPONENTES, (25, 25, 15, 15, 15, 5), strict=True))


def _evento(ticker, tema, dias, rotulo="Comunicado", materialidade=40, fonte="cvm_ipe"):
    return Evento(
        ticker=ticker, empresa=f"EMPRESA {ticker}", rotulo=rotulo, tema=tema,
        materialidade=materialidade, assunto=f"{rotulo} de {ticker}", referencia=None,
        publicado_em=HOJE - timedelta(days=dias), link=f"https://x/{ticker}/{tema}/{dias}",
        fonte=fonte, protocolo=f"{ticker}{tema}{dias}", versao=1,
    )  # fmt: skip


def _edicao(eventos, max_itens=5, detentores=()):
    return nl.montar(
        nl.Entrada(
            lista="Minha lista",
            tickers=("PETR4.SA", "VALE3.SA", "AAPL"),
            eventos=tuple(eventos),
            pesos=PESOS,
            temas=("resultados", "risco"),
            hoje=HOJE,
            janela=30,
            max_itens=max_itens,
            gerada_em=datetime(2026, 10, 11, 20, 0, tzinfo=UTC),
            detentores=detentores,
            fontes=(("Eventos (CVM e SEC)", "coletado em 11/10/2026 às 07:00"),),
        )
    )


EVENTOS = [
    *(_evento("PETR4.SA", "eventos", d, materialidade=100) for d in range(1, 6)),
    _evento("PETR4.SA", "risco", 3, "Troca de auditor", 80, "sec_edgar"),
    _evento("VALE3.SA", "resultados", 2, "Resultados", 70),
    _evento("AAPL", "participacoes", 1, "Diretoria vendeu ações", 20, "sec_form4"),
]


# --- a edição ----------------------------------------------------------------------------------
def test_secoes_na_ordem_e_destaques_por_relevancia():
    edicao = _edicao(EVENTOS)
    assert [s.chave for s in edicao.secoes] == [
        "destaques", "alertas", "por_dentro", "resultados", "donos",
    ]  # fmt: skip
    destaques = edicao.secao("destaques").itens
    assert len(destaques) == 5
    assert (
        sum(i.titulo.startswith("PETR4") for i in destaques)
        <= research.MAXIMO_POR_EMPRESA
    )
    assert all(i.razoes for i in destaques)  # todo destaque explica por que aparece


def test_alerta_nao_some_porque_a_empresa_ja_encheu_os_destaques():
    alertas = _edicao(EVENTOS).secao("alertas").itens
    assert [i.titulo.split(" · ")[1] for i in alertas] == ["Troca de auditor"]
    assert alertas[0].sigla_da_fonte == "SEC" and alertas[0].link


def test_secao_vazia_diz_que_nao_ha_nada_e_nao_inventa():
    edicao = _edicao([_evento("VALE3.SA", "resultados", 2)])
    alertas = edicao.secao("alertas")
    assert alertas.itens == () and "Nenhum sinal de alerta" in alertas.vazio
    assert edicao.secao("donos").itens == ()


def test_detentores_entram_como_frases_prontas():
    frase = "PETR4: 314 fundos com a ação em 08/2026 (+12 desde 07/2026); 26 vendidos."
    donos = _edicao(EVENTOS, detentores=(frase,)).secao("donos").itens
    assert donos[0].titulo == "PETR4" and donos[0].texto == frase


def test_parametros_e_limites_explicitos():
    edicao = _edicao(EVENTOS, max_itens=3)
    texto = " ".join(edicao.parametros)
    assert "últimos 30 dia(s), até 11/10/2026" in texto
    assert "exposição 25%" in texto and "No máximo 3 destaques" in texto
    assert any("não é recomendação" in limite for limite in edicao.limites)
    assert (edicao.inicio, edicao.fim) == (date(2026, 9, 11), HOJE)


# --- o PDF -------------------------------------------------------------------------------------
def _texto(pdf: bytes) -> str:
    assert pdf.startswith(b"%PDF")
    leitor = PdfReader(BytesIO(pdf))
    return " ".join(" ".join(p.extract_text() for p in leitor.pages).split())


def test_pdf_tem_as_secoes_os_links_e_os_limites():
    texto = _texto(relatorio_da_newsletter(_edicao(EVENTOS)))
    for titulo in (
        "Destaques",
        "Sinais de alerta",
        "Pessoas de dentro",
        "Limites e cuidados",
    ):
        assert titulo in texto
    assert "Abrir o documento original na SEC" in texto
    assert "não é recomendação de investimento" in texto


def test_pdf_executivo_e_mais_curto():
    executivo = relatorios.Configuracao(
        secoes=tuple(
            relatorios.secoes_do_modelo(relatorios.NEWSLETTER, relatorios.EXECUTIVO)
        )
    )
    texto = _texto(relatorio_da_newsletter(_edicao(EVENTOS), config=executivo))
    assert "Resultados e documentos" not in texto and "Limites e cuidados" in texto


def test_gratuito_nao_gera_o_pdf_da_newsletter():
    with pytest.raises(LimiteDoPlanoError):
        conferir_relatorio("gratuito", relatorios.NEWSLETTER, 0)
    conferir_relatorio("plus", relatorios.NEWSLETTER, 0)


def test_migracao_0013_aceita_o_tipo_novo_e_volta(tmp_path):
    url = f"sqlite:///{(tmp_path / 'n.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    checks = " ".join(
        c["sqltext"] for c in sa.inspect(motor).get_check_constraints("relatorios")
    )
    assert "newsletter" in checks
    desfazer_ate("0012", url=url)
    checks = " ".join(
        c["sqltext"]
        for c in sa.inspect(criar_engine(url)).get_check_constraints("relatorios")
    )
    assert "newsletter" not in checks and "minha_carteira" in checks
    migrar_para("head", url=url)


# --- a página ----------------------------------------------------------------------------------
def _abrir() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    return ir_para(app, "newsletter")


def test_pagina_sem_coleta_nao_inventa(banco):
    app = _abrir()
    assert not app.exception
    assert any("Nenhum evento" in c.value for c in app.caption)


def test_pagina_mostra_a_edicao_da_demonstracao(banco):
    _coletar(banco)
    app = _abrir()
    assert not app.exception
    titulos = [m.value for m in app.markdown if m.value.startswith("#### ")]
    assert "#### Destaques" in titulos and "#### Limites" in titulos
    assert any("Abrir o documento original na CVM" in m.value for m in app.markdown)
    assert any(b.key == "newsletter_pdf" for b in app.button)


def test_estudio_gera_o_pdf_da_newsletter(banco):
    _coletar(banco)
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["tipo_de_relatorio"] = relatorios.NEWSLETTER
    app.run()
    app = ir_para(app, "relatorio")
    assert not app.exception
    assert (
        app.selectbox(key="relatorio_newsletter_lista").value
        == research.NOME_DA_DEMONSTRACAO
    )
    app.button(key="gerar_pdf").click().run()
    assert not app.exception and not app.error
    gerado = app.session_state["relatorio_gerado"]
    assert gerado["arquivo"] == "tickerlab-newsletter.pdf"
    assert "Destaques" in _texto(gerado["pdf"])
