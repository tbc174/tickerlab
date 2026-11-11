"""O conector remoto falando com a API externa de verdade (linha 570), sem rede: duas organizações.

A API roda dentro do teste (`httpx.ASGITransport`), com o banco da fixture e a base de mentira da busca de
empresas (os CNPJs são de ninguém). Riscos: uma organização ver a ferramenta ou o dado de outra, a chave
revogada continuar valendo pelo conector (a memória de 60 s é só da lista de ferramentas) e o conector
deixar passar um filtro que a API recusaria.
"""

from datetime import UTC, datetime

import httpx
import pytest

from base.porta import Porta
from src import api
from src.api_externa import VARIAVEL_DA_CHAVE, acesso, rotas
from src.api_externa.conjuntos import prospeccao
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj_api
from tests import ajudantes_do_conector as aj
from tests.test_api_externa_prospeccao import (
    AGORA,
    _empresas,
    _estabelecimentos,
    _gravar,
    _regras_da_busca,
)

DEPOIS = datetime(2026, 11, 10, 13, tzinfo=UTC)


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    """A base de mentira da busca de empresas (a mesma do teste da rota)."""
    base = tmp_path / "base"
    _gravar(base, prospeccao.ESTABELECIMENTOS, _estabelecimentos())
    _gravar(base, prospeccao.EMPRESAS, _empresas())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    ator = aj_api.admin(banco)
    com_busca = aj_api.organizacao(banco, ator, "Organização com busca")
    sem_nada = aj_api.organizacao(banco, ator, "Organização sem contrato")
    aj_api.contrato(banco, ator, com_busca, conjunto=prospeccao.CONJUNTO)
    monkeypatch.setattr(rotas, "regras_da_api", _regras_da_busca)
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    acesso.zerar_limites()
    return {
        "ator": ator,
        "com_busca": com_busca,
        "chave_com_busca": aj_api.chave(banco, ator, com_busca),
        "chave_sem_nada": aj_api.chave(banco, ator, sem_nada),
    }


@pytest.fixture
def cliente(cenario):
    transporte = httpx.ASGITransport(app=api.criar_app({VARIAVEL_DA_CHAVE: "1"}))
    with aj.conector(transporte) as cliente:
        yield cliente


def test_cada_organizacao_ve_so_as_ferramentas_do_seu_contrato(cliente, cenario):
    com_busca = cenario["chave_com_busca"].valor
    sem_nada = cenario["chave_sem_nada"].valor
    assert aj.nomes_das_ferramentas(cliente, com_busca) == [
        "buscar_empresas",
        "o_que_posso_ver",
    ]
    assert aj.nomes_das_ferramentas(cliente, sem_nada) == ["o_que_posso_ver"]
    erro, _ = aj.chamar(cliente, sem_nada, "buscar_empresas", uf=["SP"])
    assert erro


def test_a_busca_chega_pela_ia_com_fonte_e_sem_pessoa(cliente, cenario):
    corpo = aj.chamar_ok(
        cliente,
        cenario["chave_com_busca"].valor,
        "buscar_empresas",
        cnae=["62"],
        uf=["MG"],
    )
    assert isinstance(corpo, dict)
    empresas = corpo["companies"]
    assert [e["cnpj"] for e in empresas] == ["11111111000191"]
    texto = str(corpo)
    assert "source" in texto and "published_at" in texto
    assert not aj_api.chaves_de(corpo) & {"partners", "cpf", "socios", "email", "phone"}


def test_o_passado_vem_como_era_conhecido(cliente, cenario):
    # em 30/09 a 11111111 estava em SP; o retrato de outubro (MG) só ficou público em 31/10
    corpo = aj.chamar_ok(
        cliente,
        cenario["chave_com_busca"].valor,
        "buscar_empresas",
        cnae=["62"],
        uf=["SP"],
        como_era_em="2026-10-15",
    )
    assert isinstance(corpo, dict)
    assert "11111111000191" in [e["cnpj"] for e in corpo["companies"]]
    hoje = aj.chamar_ok(
        cliente,
        cenario["chave_com_busca"].valor,
        "buscar_empresas",
        cnae=["62"],
        uf=["SP"],
    )
    assert isinstance(hoje, dict)
    assert "11111111000191" not in [e["cnpj"] for e in hoje["companies"]]


def test_filtro_que_a_api_recusa_volta_como_frase(cliente, cenario):
    erro, texto = aj.chamar(
        cliente, cenario["chave_com_busca"].valor, "buscar_empresas"
    )
    assert erro and "filter_required" in texto


def test_chave_revogada_para_de_valer_na_hora(cliente, cenario, banco):
    valor = cenario["chave_com_busca"].valor
    aj.chamar_ok(cliente, valor, "buscar_empresas", uf=["SP"])
    with banco.begin() as conexao:
        cb.revogar_chave(
            conexao,
            organizacao_id=cenario["com_busca"].id,
            chave_id=cenario["chave_com_busca"].chave_id,
            ator_id=cenario["ator"].id,
            agora=DEPOIS,
        )
    # a lista de ferramentas ainda está na memória (até 60 s), mas o dado vem da API com a chave
    erro, texto = aj.chamar(cliente, valor, "buscar_empresas", uf=["SP"])
    assert erro and "chave" in texto.lower()
    assert valor not in texto
