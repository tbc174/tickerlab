"""O aviso de piloto no deck da API externa (linha 875; ADR 0108, Emenda 2, D11.3).

A organização com a marca de piloto recebe no `.pptx` o que recebe no JSON, e todo slide leva a frase
`base.prontidao.AVISO_DE_PILOTO` (slide de piloto sem o aviso é defeito P1); a organização comum não recebe o
campo de piloto nem a frase. As bases de mentira são as de `test_api_externa_deck.py`.
"""

import dataclasses
from datetime import date, datetime
from io import BytesIO

import pytest
from pptx import Presentation

from base import prontidao
from base.prontidao import AVISO_DE_PILOTO, Prontidao, ProntidaoDePiloto, Prova
from src import portao_externo as portao
from src.api_externa import deck, rotas
from src.api_externa.conjuntos import empresas, ficha, setores
from src.apresentacao import CAPA, LIMITES, TABELA, Apresentacao, Slide
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_deck as do_deck
from tests.test_api_externa_setores import TABELAS_DO_SETOR

AGORA = do_deck.AGORA
TABELA_DA_ANEEL = "aneel_samp"


def _regras(prontas: tuple[str, ...], de_piloto: tuple[str, ...]) -> portao.Regras:
    """As regras de verdade, com `prontas` na prontidão cheia e `de_piloto` só no registro de piloto."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in prontas},
        prontidao_de_piloto={
            t: ProntidaoDePiloto(versoes[t], prova, prova) for t in de_piloto
        },
        # a marca de pessoa decidida é das linhas de dados; aqui o teste a dá às tabelas de piloto
        pessoa_decidida=frozenset(de_piloto),
    )


def _duas(banco, monkeypatch, conjunto: str):
    """Duas organizações com o contrato do `conjunto`; só a primeira tem a marca de piloto."""
    ator = aj.admin(banco)
    chaves = {}
    for nome in ("piloto", "comum"):
        org = aj.organizacao(banco, ator, nome=f"Organização {nome}")
        aj.contrato(banco, ator, org, conjunto=conjunto)
        chaves[nome] = aj.chave(banco, ator, org)
        if nome == "piloto":
            with banco.begin() as conexao:
                cb.conceder_direito(
                    conexao,
                    organizacao_id=org.id,
                    conjunto=cb.CONJUNTO_DO_PILOTO,
                    finalidade="analise",
                    vigente_desde=date(2026, 11, 1),
                    ator_id=ator.id,
                    agora=AGORA,
                )
    return aj.cliente_da_api(monkeypatch, AGORA), chaves


def _textos_por_slide(conteudo: bytes) -> list[str]:
    """O texto de cada slide: as caixas e as células das tabelas."""
    saida = []
    for slide in Presentation(BytesIO(conteudo)).slides:
        partes = []
        for forma in slide.shapes:
            if forma.has_text_frame:
                partes.append(forma.text_frame.text)
            if forma.has_table:
                partes += [c.text for linha in forma.table.rows for c in linha.cells]
        saida.append("\n".join(partes))
    return saida


def _slides_sem_aviso(conteudo: bytes) -> list[int]:
    return [
        numero
        for numero, texto in enumerate(_textos_por_slide(conteudo), start=1)
        if AVISO_DE_PILOTO not in texto
    ]


# ---------------------------------------------------------------- o deck da empresa


@pytest.fixture
def empresa(banco, monkeypatch, tmp_path):
    """As entregas à CVM só no registro de piloto; o cadastro da Receita na prontidão cheia."""
    do_deck._base_do_perfil(tmp_path, monkeypatch)
    monkeypatch.setattr(
        rotas,
        "regras_da_api",
        lambda: _regras(tuple(empresas.TABELAS), (ficha.TABELA_DAS_ENTREGAS,)),
    )
    return _duas(banco, monkeypatch, ficha.CONJUNTO)


def test_deck_da_empresa_do_piloto_tem_a_frase_em_todo_slide(empresa) -> None:
    cliente, chaves = empresa
    resposta = do_deck._get(cliente, chaves["piloto"], do_deck.DECK_DA_EMPRESA)
    assert resposta.status_code == 200
    texto = "\n".join(_textos_por_slide(resposta.content))
    assert "DFP" in texto and "Fonte: cvm-hist-dfp" in texto  # o dado de piloto entrou
    assert _slides_sem_aviso(resposta.content) == []


def test_deck_da_empresa_comum_nao_tem_o_dado_nem_a_frase(empresa) -> None:
    cliente, chaves = empresa
    resposta = do_deck._get(cliente, chaves["comum"], do_deck.DECK_DA_EMPRESA)
    assert resposta.status_code == 200
    texto = "\n".join(_textos_por_slide(resposta.content))
    assert "cvm-hist-dfp" not in texto and "Zona cinzenta" not in texto
    assert "11.111.111/0001-91" in texto  # o cadastro, pronto, sai
    assert AVISO_DE_PILOTO not in texto


def test_deck_da_empresa_tudo_pronto_nao_tem_a_frase(empresa, monkeypatch) -> None:
    """Sem campo de piloto na resposta, o deck da organização do piloto é o de sempre."""
    cliente, chaves = empresa
    prontas = (*empresas.TABELAS, ficha.TABELA_DAS_ENTREGAS)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(prontas, ()))
    resposta = do_deck._get(cliente, chaves["piloto"], do_deck.DECK_DA_EMPRESA)
    texto = "\n".join(_textos_por_slide(resposta.content))
    assert "Fonte: cvm-hist-dfp" in texto
    assert AVISO_DE_PILOTO not in texto


# ---------------------------------------------------------------- o deck do setor


@pytest.fixture
def setor(banco, monkeypatch, tmp_path):
    """A ANEEL sem a prontidão cheia; as três tabelas do setor no registro de piloto (o piloto vale só se toda
    tabela da linha do pedido está nele); os membros (CVM) seguem na prontidão cheia."""
    do_deck.gravar_noite(tmp_path)
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(tmp_path))
    prontas = tuple(t for t in TABELAS_DO_SETOR if t != TABELA_DA_ANEEL)
    monkeypatch.setattr(
        rotas, "regras_da_api", lambda: _regras(prontas, TABELAS_DO_SETOR)
    )
    return _duas(banco, monkeypatch, setores.CONJUNTO)


def test_deck_do_setor_do_piloto_tem_a_frase_em_todo_slide(setor) -> None:
    cliente, chaves = setor
    resposta = do_deck._get(cliente, chaves["piloto"], do_deck.DECK_DO_SETOR)
    assert resposta.status_code == 200
    texto = "\n".join(_textos_por_slide(resposta.content))
    assert "HHI (pontos)" in texto and "aneel-samp" in texto  # o dado de piloto entrou
    assert _slides_sem_aviso(resposta.content) == []


def test_deck_do_setor_comum_nao_tem_o_dado_nem_a_frase(setor) -> None:
    cliente, chaves = setor
    resposta = do_deck._get(cliente, chaves["comum"], do_deck.DECK_DO_SETOR)
    assert resposta.status_code == 200
    texto = "\n".join(_textos_por_slide(resposta.content))
    assert "HHI (pontos)" not in texto and "aneel-samp" not in texto
    assert "CPFL ENERGIA S.A." in texto  # os membros, prontos, saem
    assert AVISO_DE_PILOTO not in texto


# ---------------------------------------------------------------- a regra, sem rota


def _deck_de_exemplo() -> Apresentacao:
    return Apresentacao(
        "Título",
        "Subtítulo",
        "Aviso do deck",
        (
            Slide(CAPA, "Capa", notas=("Como era em 10/11/2026",)),
            Slide(
                TABELA,
                "Tabela",
                cabecalho=("a",),
                linhas=(("1",),),
                notas=("Fonte: x · público em 01/11/2026",),
            ),
            Slide(LIMITES, "Limites", topicos=("Um limite",)),
        ),
    )


def test_a_frase_vai_em_todo_slide_primeiro_nas_notas_e_nos_limites() -> None:
    marcado = deck.com_aviso_de_piloto(_deck_de_exemplo())
    assert all(slide.notas[0] == AVISO_DE_PILOTO for slide in marcado.slides)
    assert marcado.slides[1].notas[1] == "Fonte: x · público em 01/11/2026"
    assert marcado.slides[2].topicos == ("Um limite", AVISO_DE_PILOTO)
    assert marcado.slides[1].linhas == (("1",),)  # o dado não muda


def test_a_frase_sobrevive_ao_arquivo() -> None:
    """A frase passa pela limpeza do texto (`_limpo`) e chega a todo slide do `.pptx`."""
    marcado = deck.com_aviso_de_piloto(_deck_de_exemplo())
    conteudo = deck.em_arquivo(marcado, datetime(2026, 11, 12, 13, 0, tzinfo=deck.FUSO))
    assert _slides_sem_aviso(conteudo) == []
