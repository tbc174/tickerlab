"""Origem do cadastro lida do cookie próprio `tl_origem` (campanha, PR 1).

O site grava o cookie quando a pessoa chega por um link com UTMs ou `?ref=`; o app lê no primeiro
login. Só passam campos curtos com letras minúsculas, números e hífen: assim nenhum dado pessoal
(um e-mail colado num `utm_*`, um nome) chega ao banco.
"""

import re
from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from src.origem import NOME_DO_COOKIE, Origem, ler_origem

CAMPO_VALIDO = re.compile(r"[a-z0-9-]{1,60}")
CAMPOS_DE_TEXTO = ("source", "medium", "campaign", "content", "ref")


def test_nome_do_cookie():
    assert NOME_DO_COOKIE == "tl_origem"


def test_ler_origem_valida():
    valor = "s=google|m=cpc|c=testamos-ifr2|t=reel-1|r=|v=2026-12-07"

    assert ler_origem(valor) == Origem(
        source="google",
        medium="cpc",
        campaign="testamos-ifr2",
        content="reel-1",
        ref=None,
        primeira_visita=date(2026, 12, 7),
    )


def test_so_o_ref_basta():
    assert ler_origem("r=clube-do-robo") == Origem(ref="clube-do-robo")


def test_aceita_o_valor_codificado_para_url():
    # O JS do site pode gravar com encodeURIComponent: "|" vira %7C e "=" vira %3D.
    assert ler_origem("s%3Dyoutube%7Cm%3Dvideo") == Origem(
        source="youtube", medium="video"
    )


def test_campo_desconhecido_e_ignorado():
    assert ler_origem("s=google|x=qualquer-coisa") == Origem(source="google")


def test_campo_com_mais_de_60_caracteres_fica_vazio():
    assert ler_origem("s=" + "a" * 61 + "|m=cpc") == Origem(medium="cpc")


def test_data_invalida_fica_vazia():
    assert ler_origem("s=google|v=2026-13-40") == Origem(source="google")
    assert ler_origem("s=google|v=ontem") == Origem(source="google")


@given(
    antes=st.text(alphabet="abcdefghij0123-", max_size=20),
    proibido=st.sampled_from(["@", " ", "A", "Z", "É", ".", "+", "%40"]),
    depois=st.text(alphabet="abcdefghij0123-", max_size=20),
)
def test_origem_recusa_email_e_texto_livre(antes, proibido, depois):
    origem = ler_origem(f"s={antes}{proibido}{depois}|m=cpc")

    assert origem == Origem(medium="cpc")


@given(st.text(max_size=300))
def test_qualquer_texto_so_deixa_passar_campos_limpos(valor):
    origem = ler_origem(valor)

    if origem is not None:
        for campo in CAMPOS_DE_TEXTO:
            texto = getattr(origem, campo)
            assert texto is None or CAMPO_VALIDO.fullmatch(texto)


def test_cookie_vazio_ou_quebrado():
    assert ler_origem(None) is None
    assert ler_origem("") is None
    assert ler_origem("   ") is None
    assert ler_origem("lixo") is None
    assert ler_origem("s=|m=|r=") is None
    assert ler_origem("s=Fulano@gmail.com") is None
    assert ler_origem("s=google|" * 200) is None  # grande demais: não é o nosso cookie
