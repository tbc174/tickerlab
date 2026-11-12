"""O aviso de piloto chega a quem usa o conector remoto (ADR 0108, Emenda 2, D11; linha 865).

O conector roda de verdade e fala com a API externa de verdade (`httpx.ASGITransport`), sem rede, com a
base de mentira das demonstrações de `test_api_externa_piloto.py`. Risco: o bloco de piloto sair da API com
a marca e chegar ao analista, pela ferramenta do conector, sem a frase (P1 no D11).
"""

import httpx
import pytest

from base.prontidao import AVISO_DE_PILOTO
from src import api
from src.api_externa import VARIAVEL_DA_CHAVE
from tests import ajudantes_do_conector as aj_conector
from tests.test_api_externa_demonstracoes import CNPJ_DA_BASE
from tests.test_api_externa_piloto import (  # noqa: F401 (fixtures)
    _envelopes,
    _sem_aviso,
    duas,
    pasta,
)


@pytest.fixture
def conector(duas):  # noqa: F811 (a fixture importada)
    """O conector falando com a API das duas organizações (só a primeira tem a marca)."""
    _cliente_da_api, chaves, _ator, _org = duas
    transporte = httpx.ASGITransport(app=api.criar_app({VARIAVEL_DA_CHAVE: "1"}))
    with aj_conector.conector(transporte) as cliente:
        yield cliente, chaves


def test_a_ferramenta_entrega_a_frase_em_todo_bloco_de_piloto(conector) -> None:
    cliente, chaves = conector
    corpo = aj_conector.chamar_ok(
        cliente, chaves["piloto"], "demonstracoes", cnpj=CNPJ_DA_BASE
    )
    envelopes = list(_envelopes(corpo))
    assert envelopes, "a ferramenta não entregou nenhum bloco com fonte e data"
    assert _sem_aviso(corpo) == []
    assert isinstance(corpo, dict)
    assert corpo["pilot_notice"] == AVISO_DE_PILOTO
    for _nome, envelope in envelopes:  # a frase fica ao lado da fonte e da data
        assert envelope["source"] and envelope["published_at"]


def test_a_frase_passa_inteira_pela_limpeza_da_saida(conector) -> None:
    cliente, chaves = conector
    erro, texto = aj_conector.chamar(
        cliente, chaves["piloto"], "demonstracoes", cnpj=CNPJ_DA_BASE
    )
    assert not erro, texto
    assert AVISO_DE_PILOTO in texto


def test_a_organizacao_comum_nao_recebe_o_dado_de_piloto(conector) -> None:
    cliente, chaves = conector
    erro, texto = aj_conector.chamar(
        cliente, chaves["comum"], "demonstracoes", cnpj=CNPJ_DA_BASE
    )
    assert erro
    assert AVISO_DE_PILOTO not in texto
    assert "pilot" not in texto
