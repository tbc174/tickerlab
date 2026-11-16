"""A porta e o cache dividos entre pedidos de organizações diferentes (linha 956, condições 1 e 2 da Diretoria).

Duas organizações com o contrato do `buyers`, na MESMA porta aberta uma vez: uma com a marca de piloto (o FRE só
sai pelo registro de piloto, e o bloco leva o aviso) e a outra comum (o sinal do FRE fica barrado). Nada que
dependa do pedido pode ficar na porta nem na chave do cache: a resposta de uma não pode aparecer na outra.
"""
# ruff: noqa: F811  (as fixtures vêm do arquivo do buyers e se repetem nos argumentos)

import dataclasses
from datetime import date

import pytest

from base import prontidao
from base.prontidao import AVISO_DE_PILOTO, Prontidao, ProntidaoDePiloto, Prova
from src import portao_externo as portao
from src.api_externa import piloto, porta_compartilhada, rotas
from src.api_externa.conjuntos import compradores
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests.test_api_externa_compradores import (  # noqa: F401  (fixtures reaproveitadas)
    ABERTA,
    AGORA,
    ROTA,
    SETOR,
    TABELAS,
    _raizes,
    pasta,
)


def _regras(prontas: tuple[str, ...], de_piloto: tuple[str, ...]) -> portao.Regras:
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in prontas},
        prontidao_de_piloto={
            t: ProntidaoDePiloto(versoes[t], prova, prova) for t in de_piloto
        },
        pessoa_decidida=frozenset(de_piloto),
    )


@pytest.fixture
def duas_na_mesma_porta(banco, monkeypatch, pasta):
    """Uma organização de piloto e uma comum; a porta é a compartilhada de verdade (abre uma vez)."""
    aberturas: list[int] = []
    from base.porta import Porta

    def abrir() -> Porta:
        aberturas.append(1)
        return Porta(pasta)

    porta_compartilhada.zerar()
    compradores.zerar_o_cache()
    monkeypatch.setattr(porta_compartilhada, "abrir_a_base", abrir)
    monkeypatch.setattr(porta_compartilhada, "_pasta_da_base", lambda: pasta)
    monkeypatch.setattr(rotas, "abrir_porta", porta_compartilhada.porta_do_pedido)
    sem_fre = tuple(t for t in TABELAS if t != compradores.CONTROLADAS)
    monkeypatch.setattr(
        rotas, "regras_da_api", lambda: _regras(sem_fre, (compradores.CONTROLADAS,))
    )
    ator = aj.admin(banco)
    chaves = {}
    for nome in ("piloto", "comum"):
        org = aj.organizacao(banco, ator, nome=f"Organização {nome}")
        aj.contrato(banco, ator, org, conjunto=compradores.CONJUNTO)
        chaves[nome] = aj.chave(banco, ator, org).valor
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
    yield aj.cliente_da_api(monkeypatch, AGORA), chaves, aberturas
    porta_compartilhada.zerar()
    compradores.zerar_o_cache()


def _pede(cliente, chave: str):
    return cliente.get(ROTA, params={"cnae": SETOR}, headers=aj.bearer(chave))


def test_duas_organizacoes_na_mesma_porta_cada_uma_com_o_seu(duas_na_mesma_porta):
    cliente, chaves, aberturas = duas_na_mesma_porta
    # a comum primeiro: é a resposta dela que fica guardada no cache
    comum = _pede(cliente, chaves["comum"])
    assert comum.status_code == 200
    assert ABERTA not in _raizes(comum)
    assert comum.json()["unavailable_signals"] == ["controls_in_sector"]
    assert piloto.MARCA not in repr(comum.json()) and AVISO_DE_PILOTO not in repr(
        comum.json()
    )
    # a de piloto depois, na mesma porta: o FRE sai e o bloco leva a marca e a frase
    com_piloto = _pede(cliente, chaves["piloto"])
    assert com_piloto.status_code == 200
    assert ABERTA in _raizes(com_piloto)
    assert com_piloto.json()["unavailable_signals"] == []
    assert AVISO_DE_PILOTO in repr(com_piloto.json())
    # e a comum de novo: não herda nada da de piloto (nem a lista, nem a marca)
    comum_de_novo = _pede(cliente, chaves["comum"])
    assert comum_de_novo.json() == comum.json()
    assert AVISO_DE_PILOTO not in repr(comum_de_novo.json())
    # o cache não leu a resposta de uma na outra: duas entradas (os sinais entram na chave)
    assert len(compradores._CACHE) == 2
    assert len(aberturas) == 1  # uma porta só para os seis pedidos


def test_a_resposta_de_piloto_guardada_nao_sai_sem_a_marca_para_a_comum(
    duas_na_mesma_porta,
):
    """A de piloto vem primeiro e deixa o resultado no cache; a comum, com outros sinais, não o aproveita."""
    cliente, chaves, _aberturas = duas_na_mesma_porta
    com_piloto = _pede(cliente, chaves["piloto"])
    assert ABERTA in _raizes(com_piloto)
    comum = _pede(cliente, chaves["comum"])
    assert ABERTA not in _raizes(comum)
    assert comum.json()["unavailable_signals"] == ["controls_in_sector"]
    assert AVISO_DE_PILOTO not in repr(comum.json())
    # a de piloto pela segunda vez sai do cache e continua marcada (a marca é do pedido, não do cache)
    de_novo = _pede(cliente, chaves["piloto"])
    assert de_novo.json() == com_piloto.json()
    assert AVISO_DE_PILOTO in repr(de_novo.json())
