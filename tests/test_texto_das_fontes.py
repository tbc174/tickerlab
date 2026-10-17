"""Achado 7d do Codex: assunto e frases das fontes (CVM, SEC) não viram Markdown na tela.

Um assunto com `[Validar cadastro](https://...)` ou `![](https://...)` virava link ou imagem
dentro do Research e da Newsletter. O texto das fontes entra escapado.
"""

import contextlib
from datetime import date
from types import SimpleNamespace

from src.banco.eventos import Evento
from src.conteudo import texto_da_fonte
from src.newsletter import Item, Secao
from src.research import ItemDoResearch
from telas.research import acontecimentos, newsletter

ISCA = "Veja [Validar cadastro](https://exemplo.invalid/login) ![x](https://exemplo.invalid/i.png)"


def test_texto_da_fonte_desliga_link_imagem_e_formula():
    escapado = texto_da_fonte(ISCA + " e R$ 10 **forte** <b>")
    assert "[Validar cadastro](" not in escapado
    assert "![x](" not in escapado
    assert r"\[Validar cadastro\]\(https\://exemplo\.invalid/login\)" in escapado
    assert r"R\$ 10 \*\*forte\*\* \<b\>" in escapado
    assert texto_da_fonte("") == "" and texto_da_fonte(None) is None


class _Gravador:
    """Um `st` de mentira: guarda todo texto mandado a markdown/caption, em qualquer coluna."""

    def __init__(self):
        self.textos = []

    def markdown(self, texto, **_):
        self.textos.append(texto)

    caption = markdown

    def columns(self, spec, **_):
        return [self for _ in spec]

    def container(self, *_, **__):
        return contextlib.nullcontext()

    expander = container

    def link_button(self, *a, **k):
        pass

    button = link_button


def _evento():
    return Evento(
        ticker="PETR4.SA", empresa="EMPRESA [x](https://exemplo.invalid)",
        rotulo="Fato Relevante", tema="eventos", materialidade=80, assunto=ISCA,
        referencia=None, publicado_em=date(2026, 10, 10), link="https://www.rad.cvm.gov.br/x",
        fonte="cvm_ipe", protocolo="p1", versao=1,
    )  # fmt: skip


def _sem_link(textos):
    juntos = "\n".join(textos)
    assert "](https://exemplo.invalid" not in juntos, juntos


def test_acontecimentos_escapam_assunto_empresa_e_frases(monkeypatch):
    gravador = _Gravador()
    monkeypatch.setattr(acontecimentos, "st", gravador)
    item = ItemDoResearch(_evento(), 0.5, {}, ["razão"])
    resumo = {"frases": [ISCA], "numeros": [ISCA], "assuntos": [ISCA]}
    acontecimentos._mostrar_item(item, "a", resumo=resumo)
    _sem_link(gravador.textos)
    assert any(r"\[Validar cadastro\]" in t for t in gravador.textos)


def test_newsletter_escapa_titulo_texto_e_trechos(monkeypatch):
    gravador = _Gravador()
    monkeypatch.setattr(newsletter, "st", gravador)
    secao = Secao(
        chave="fatos", titulo="Fatos", vazio="",
        itens=(Item(titulo=ISCA, texto=ISCA, trechos=(ISCA,), razoes=("razão",)),),
    )  # fmt: skip
    newsletter._mostrar_secao_da_newsletter(secao)
    _sem_link(gravador.textos)


def test_link_oficial_da_newsletter_continua_clicavel(monkeypatch):
    gravador = _Gravador()
    monkeypatch.setattr(newsletter, "st", gravador)
    item = Item(
        titulo="PETR4",
        texto="Assunto",
        link="https://www.rad.cvm.gov.br/x",
        sigla_da_fonte="CVM",
    )
    newsletter._mostrar_secao_da_newsletter(
        SimpleNamespace(titulo="Fatos", vazio="", itens=(item,))
    )
    assert any("](https://www.rad.cvm.gov.br/x)" in t for t in gravador.textos)
