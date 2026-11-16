"""O cache em memória do `buyers` (linha 848): a resposta com e sem cache é a mesma, e ele nunca serve base velha.

Reaproveita a base de mentira dos testes do `buyers`. O cache guarda só o resultado já filtrado pelos sinais e
pelo limite da chamada (a chave os leva), nunca nada da conta, da chave ou da organização.
"""
# ruff: noqa: F811  (as fixtures vêm do arquivo do buyers e se repetem nos argumentos)

from datetime import date

import pytest

from base.porta import Porta
from src.api_externa import rotas
from src.api_externa.conjuntos import compradores
from tests.test_api_externa_compradores import (  # noqa: F401  (fixtures reaproveitadas)
    ABERTA,
    COMPRADORA,
    ENTRADAS,
    SETOR,
    TABELAS,
    _get,
    _gravar,
    _raizes,
    _regras,
    cenario,
    cliente,
    pasta,
)
from tests.test_api_externa_compradores import _entradas as _entradas_de_mentira


@pytest.fixture(autouse=True)
def _cache_limpo():
    compradores.zerar_o_cache()
    yield
    compradores.zerar_o_cache()


def _sem_cache(cliente, cenario, **parametros):
    compradores.zerar_o_cache()
    return _get(cliente, cenario, **parametros)


def test_a_segunda_chamada_sai_do_cache_e_e_igual_a_primeira(cliente, cenario):
    primeira = _get(cliente, cenario)
    assert len(compradores._CACHE) == 1
    segunda = _get(cliente, cenario)
    assert len(compradores._CACHE) == 1
    assert segunda.status_code == 200
    assert segunda.json() == primeira.json()


@pytest.mark.parametrize(
    "parametros",
    [{}, {"state": "sp"}, {"years": 10}, {"limit": 1}, {"cnae": "0111301"}],
)
def test_com_e_sem_cache_a_resposta_e_identica(cliente, cenario, parametros):
    com_cache = _get(cliente, cenario, **parametros)
    do_cache = _get(cliente, cenario, **parametros)
    do_zero = _sem_cache(cliente, cenario, **parametros)
    assert com_cache.json() == do_zero.json() == do_cache.json()


def test_pedidos_diferentes_nao_dividem_a_entrada(cliente, cenario):
    todos = _get(cliente, cenario)
    so_sp = _get(cliente, cenario, state="sp")
    assert len(compradores._CACHE) == 2
    assert _raizes(todos) != _raizes(so_sp)
    # a volta ao primeiro pedido não devolve o do segundo
    assert _get(cliente, cenario).json() == todos.json()


def test_cada_chamada_recebe_uma_copia_e_o_cache_fica_intacto(pasta, banco):
    leitor = compradores.LeitorDeCompradores(Porta(pasta, banco), lambda *_: True, 50)
    pedido = compradores.PedidoDeCompradores(SETOR, None, 3, 20)
    primeira = leitor.compradores(pedido, date(2026, 11, 10))
    segunda = leitor.compradores(pedido, date(2026, 11, 10))
    terceira = leitor.compradores(pedido, date(2026, 11, 10))
    assert primeira is not segunda is not terceira
    assert primeira == segunda == terceira
    assert primeira is not None and primeira.linhas


def test_base_nova_invalida_o_cache(cliente, cenario, pasta):
    antes = _get(cliente, cenario)
    assert COMPRADORA in _raizes(antes)
    # a Receita republica: a compra da COMPRADORA some do arquivo de entradas
    sem_compra = _entradas_de_mentira()
    sem_compra = sem_compra[sem_compra["raiz_socio_pj"] != COMPRADORA]
    assert len(sem_compra) < len(ENTRADAS)
    _gravar(pasta / compradores.ENTRADAS / "parte.parquet", sem_compra)
    depois = _get(cliente, cenario)
    assert COMPRADORA not in _raizes(depois)
    assert depois.json() == _sem_cache(cliente, cenario).json()


def test_arquivo_novo_na_base_invalida_o_cache(cliente, cenario, pasta):
    antes = _get(cliente, cenario)
    extra = _entradas_de_mentira().iloc[0:0]
    _gravar(pasta / compradores.ENTRADAS / "outra_parte.parquet", extra)
    _get(cliente, cenario)
    assert (
        len(compradores._CACHE) == 2
    )  # a impressão mudou: entrada nova, a velha fica para sair
    assert _get(cliente, cenario).json() == antes.json()


def test_o_cache_e_limitado(cliente, cenario):
    for anos in range(1, compradores.TAMANHO_DO_CACHE + 6):
        _get(cliente, cenario, years=min(anos, 30))
    assert len(compradores._CACHE) <= compradores.TAMANHO_DO_CACHE


def test_nada_da_conta_vai_na_chave_nem_no_valor(cliente, cenario):
    _get(cliente, cenario)
    ((chave, valor),) = compradores._CACHE.items()
    texto = (repr(chave) + repr(valor)).lower()
    _ator, _org, chave_da_api = cenario
    assert chave_da_api.valor.lower() not in texto
    assert "cpf" not in texto


def test_permissao_diferente_nao_aproveita_a_entrada_da_outra(
    cliente, cenario, monkeypatch
):
    completo = _get(cliente, cenario)
    assert ABERTA in _raizes(completo)
    # a conta passa a não ter o FRE (controladas): os sinais mudam e a chave com eles
    sem_fre = tuple(t for t in TABELAS if t != compradores.CONTROLADAS)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(*sem_fre))
    reduzido = _get(cliente, cenario)
    assert ABERTA not in _raizes(reduzido)
    assert len(compradores._CACHE) == 2
    # e a volta da permissão devolve a lista completa, não a reduzida
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(*TABELAS))
    assert _get(cliente, cenario).json() == completo.json()


def test_limite_da_conta_entra_na_chave(cliente, cenario):
    _get(cliente, cenario, limit=1)
    _get(cliente, cenario, limit=2)
    assert len(compradores._CACHE) == 2


def test_known_at_antigo_nao_le_a_resposta_de_hoje(cliente, cenario):
    hoje = _get(cliente, cenario)
    assert COMPRADORA in _raizes(hoje)
    # a entrada da COMPRADORA só ficou pública em 31/05/2025: antes disso ela não pode aparecer
    antes = _get(cliente, cenario, known_at="2025-04-30")
    if antes.status_code == 200:
        assert COMPRADORA not in _raizes(antes)
        assert (
            antes.json() == _sem_cache(cliente, cenario, known_at="2025-04-30").json()
        )
    assert len(compradores._CACHE) >= 1
    assert _get(cliente, cenario).json() == hoje.json()
