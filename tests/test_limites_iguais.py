"""O Streamlit e a API v1 decidem igual quem abre cada página (ADR 0062).

Os dois leem a mesma regra (`src.paginas.motivo_da_pagina`), mas por caminhos diferentes: a tela
mostra um aviso com `st.info`; a API responde 403 com o motivo, antes de calcular. Aqui cada página
ganha uma rota de teste com a mesma dependência das rotas de verdade (`rotas.Conta`), e o gerador
procura um plano e uma página em que os dois discordem. As rotas de verdade têm o próprio teste
(`test_rotas_reais_seguem_o_contrato`).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import example, given, settings
from hypothesis import strategies as st

from src import paginas
from src.api_v1 import acesso, rotas
from src.banco.modelo import PLANOS
from telas.conta import assinatura

RAIZ = Path(__file__).resolve().parent.parent
CHAVES = tuple(p.chave for p in paginas.PAGINAS)
# planos de verdade e o que um banco estragado ou um plano futuro poderia trazer
PLANOS_ESTRANHOS = (None, "", "PRO", "Pro ", "empresa")


def _rota_de_teste(chave: str) -> str:
    return f"/v1/teste-{paginas.pagina(chave).url}"


@pytest.fixture(scope="module")
def api_de_teste():
    """Uma rota por página, todas com `rotas.Conta`; a conta logada é trocada pelo plano do caso."""
    app = FastAPI()
    for chave in CHAVES:

        def rota(_conta: rotas.Conta) -> dict:
            return {"ok": True}

        app.add_api_route(_rota_de_teste(chave), rota)
    plano_do_caso = {"plano": None}
    app.dependency_overrides[acesso.conta_logada] = lambda: SimpleNamespace(
        plano=plano_do_caso["plano"]
    )
    with pytest.MonkeyPatch.context() as mp:
        for chave in CHAVES:
            mp.setitem(paginas.POR_ROTA, _rota_de_teste(chave), paginas.pagina(chave))
        yield TestClient(app), plano_do_caso


def _decisao_da_api(api_de_teste, plano, chave) -> str | None:
    cliente, plano_do_caso = api_de_teste
    plano_do_caso["plano"] = plano
    resposta = cliente.get(_rota_de_teste(chave))
    if resposta.status_code == 200:
        return None
    assert resposta.status_code == 403, resposta.text
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "plano"
    return resposta.json()["detail"]


def _decisao_do_streamlit(monkeypatch, plano, chave) -> str | None:
    avisos = []
    monkeypatch.setattr(assinatura, "plano_atual", lambda: plano)
    monkeypatch.setattr(assinatura.st, "info", avisos.append)
    monkeypatch.setattr(assinatura.st, "expander", lambda *_a, **_k: _Nada())
    monkeypatch.setattr(assinatura.st, "caption", lambda *_a, **_k: None)
    monkeypatch.setattr(assinatura, "mostrar_planos", lambda: None)
    monkeypatch.setattr(assinatura, "mostrar_assinatura", lambda _chave: None)
    abre = assinatura.exigir_pagina(chave)
    assert abre == (avisos == [])
    return None if abre else avisos[0]


class _Nada:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _concordam(api_de_teste, plano, chave) -> None:
    with pytest.MonkeyPatch.context() as mp:
        na_tela = _decisao_do_streamlit(mp, plano, chave)
    assert na_tela == _decisao_da_api(api_de_teste, plano, chave), (plano, chave)


@pytest.mark.parametrize("plano", (*PLANOS, *PLANOS_ESTRANHOS))
def test_streamlit_e_api_decidem_igual_em_toda_pagina(api_de_teste, plano):
    """Todas as combinações dos planos conhecidos com todas as páginas (são poucas: sem sorteio)."""
    for chave in CHAVES:
        _concordam(api_de_teste, plano, chave)


@pytest.fixture(scope="module")
def no_gratuito(api_de_teste):
    """O que a API decide no Gratuito, página a página (calculado uma vez para o módulo)."""
    return {chave: _decisao_da_api(api_de_teste, "gratuito", chave) for chave in CHAVES}


# quase todo texto sorteado é "plano desconhecido": poucos exemplos bastam (cada um testa as 23 páginas)
@settings(max_examples=30, deadline=None)
@given(plano=st.one_of(st.none(), st.text(max_size=20)))
@example(plano="pro\n")
@example(plano="Gratuito")
def test_qualquer_texto_de_plano_decide_igual_e_vale_como_gratuito(
    api_de_teste, no_gratuito, plano
):
    """Um plano que não é um dos de verdade (banco estragado, plano futuro) vale como Gratuito."""
    for chave in CHAVES:
        with pytest.MonkeyPatch.context() as mp:
            na_tela = _decisao_do_streamlit(mp, plano, chave)
        na_api = _decisao_da_api(api_de_teste, plano, chave)
        assert na_tela == na_api, (plano, chave)
        if plano not in PLANOS:
            assert na_api == no_gratuito[chave], (plano, chave)


@pytest.mark.parametrize("chave", CHAVES)
def test_plano_mais_caro_abre_tudo_o_que_o_mais_barato_abre(chave):
    abre = [paginas.motivo_da_pagina(plano, chave) is None for plano in PLANOS]
    assert abre == sorted(
        abre
    )  # Gratuito ≤ Plus ≤ Pro: depois de abrir, não fecha mais


def test_telas_nao_decidem_pagina_paga_por_conta_propria():
    """Página paga passa por `exigir_pagina`/`motivo_da_pagina`, não por uma constante na tela."""
    arquivos = [RAIZ / "app.py", *sorted((RAIZ / "telas").rglob("*.py"))]
    for arquivo in arquivos:
        texto = arquivo.read_text(encoding="utf-8")
        for recurso in ("APRENDIZADO_DE_MAQUINA", "PARES"):
            assert f"import {recurso}" not in texto and f" {recurso}," not in texto, (
                arquivo,
                recurso,
            )
