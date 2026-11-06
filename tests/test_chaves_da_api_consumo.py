"""Medição do consumo da API externa (N7, PR 2, tarefa 2.2; plano D10).

Risco 6 do plano: quota furada ou contagem errada. A soma do mês é a dos pedidos aceitos (os negados
contam à parte), a virada do mês zera, e uma organização nunca vê o consumo da outra (risco 1).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.banco import chaves_da_api as cb
from src.banco.modelo import consumo_da_api
from src.banco.usuarios import entrar

AGORA = datetime(2026, 10, 22, 12, tzinfo=UTC)
CONJUNTO = "cvm-dfp-itr"


@pytest.fixture
def conexao(banco):
    with banco.begin() as conexao:
        yield conexao


@pytest.fixture
def admin(conexao):
    return entrar(conexao, "g-admin-n7", "admin-n7@exemplo.com")[0]


def _contexto(conexao, admin, nome="Alfa Gestora"):
    organizacao = cb.criar_organizacao(
        conexao, nome=nome, ator_id=admin.id, agora=AGORA
    )
    chave = cb.emitir_chave(
        conexao, organizacao_id=organizacao.id, ator_id=admin.id, agora=AGORA
    )
    contexto = cb.conferir_chave(conexao, chave.valor, agora=AGORA)
    assert isinstance(contexto, cb.ContextoDaChave)
    return contexto


def _registrar(conexao, contexto, agora=AGORA, **extras):
    valores = {"conjunto": CONJUNTO, "finalidade": "analise", "linhas": 10}
    cb.registrar_consumo(conexao, contexto, agora=agora, **(valores | extras))


def test_pedidos_do_mes_somam_aceitos_linhas_e_negados(conexao, admin):
    alfa = _contexto(conexao, admin)
    _registrar(conexao, alfa, linhas=10)
    _registrar(conexao, alfa, linhas=5, agora=AGORA + timedelta(minutes=1))
    _registrar(conexao, alfa, linhas=0, negado=True)
    _registrar(conexao, alfa, linhas=7, finalidade="credito", conjunto="cnpj")
    consumo = cb.consumo_do_mes(conexao, alfa.organizacao_id, AGORA.date())
    assert consumo == cb.ConsumoDoMes(pedidos=3, linhas=22, negados=1)


def test_uma_linha_por_dia_chave_canal_finalidade_e_conjunto(conexao, admin):
    alfa = _contexto(conexao, admin)
    _registrar(conexao, alfa)
    _registrar(conexao, alfa)
    _registrar(conexao, alfa, finalidade="credito")
    linhas = conexao.execute(
        sa.select(consumo_da_api).order_by(consumo_da_api.c.finalidade)
    ).all()
    assert [(l.finalidade, l.canal, l.pedidos, l.linhas) for l in linhas] == [
        ("analise", "api_externa", 2, 20),
        ("credito", "api_externa", 1, 10),
    ]
    assert {l.chave_id for l in linhas} == {alfa.chave_id}


def test_negado_conta_a_parte_e_nao_soma_linhas(conexao, admin):
    alfa = _contexto(conexao, admin)
    _registrar(conexao, alfa, linhas=50, negado=True)
    consumo = cb.consumo_do_mes(conexao, alfa.organizacao_id, AGORA.date())
    assert consumo == cb.ConsumoDoMes(pedidos=0, linhas=0, negados=1)


def test_virada_do_mes_zera(conexao, admin):
    alfa = _contexto(conexao, admin)
    fim_de_outubro = datetime(2026, 10, 31, 23, 59, tzinfo=UTC)
    _registrar(conexao, alfa, agora=fim_de_outubro)
    _registrar(conexao, alfa, agora=fim_de_outubro + timedelta(minutes=2))
    outubro = cb.consumo_do_mes(conexao, alfa.organizacao_id, fim_de_outubro.date())
    novembro = cb.consumo_do_mes(
        conexao, alfa.organizacao_id, (fim_de_outubro + timedelta(days=1)).date()
    )
    assert outubro.pedidos == 1
    assert novembro.pedidos == 1


def test_mes_sem_pedido_e_zero(conexao, admin):
    alfa = _contexto(conexao, admin)
    assert cb.consumo_do_mes(
        conexao, alfa.organizacao_id, AGORA.date()
    ) == cb.ConsumoDoMes(0, 0, 0)


def test_consumo_de_uma_organizacao_nao_aparece_na_outra(conexao, admin):
    alfa = _contexto(conexao, admin)
    beta = _contexto(conexao, admin, nome="Beta Crédito")
    _registrar(conexao, alfa)
    _registrar(conexao, alfa)
    assert cb.consumo_do_mes(conexao, beta.organizacao_id, AGORA.date()).pedidos == 0
    assert cb.consumo_do_mes(conexao, uuid.uuid4(), AGORA.date()).pedidos == 0


@pytest.mark.parametrize("finalidade", ["treino", "outra", ""])
def test_finalidade_fora_da_organizacao_recusada(conexao, admin, finalidade):
    alfa = _contexto(conexao, admin)
    with pytest.raises(ValueError, match="finalidade"):
        _registrar(conexao, alfa, finalidade=finalidade)


@pytest.mark.parametrize("conjunto", ["", "   ", "x" * 81])
def test_conjunto_invalido_recusado(conexao, admin, conjunto):
    alfa = _contexto(conexao, admin)
    with pytest.raises(ValueError, match="conjunto"):
        _registrar(conexao, alfa, conjunto=conjunto)


def test_linhas_negativas_recusadas(conexao, admin):
    alfa = _contexto(conexao, admin)
    with pytest.raises(ValueError, match="linhas"):
        _registrar(conexao, alfa, linhas=-1)


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    pedidos=st.lists(
        st.tuples(
            st.integers(0, 3),  # qual das 4 chaves (2 por organização)
            st.booleans(),  # negado
            st.integers(0, 1_000),  # linhas
            st.sampled_from(["analise", "credito"]),
            st.integers(0, 3),  # minutos depois de AGORA
        ),
        max_size=30,
    )
)
def test_soma_do_mes_igual_aos_pedidos_aceitos_em_qualquer_ordem(banco, pedidos):
    with banco.connect() as conexao, conexao.begin() as transacao:
        admin = entrar(conexao, "g-admin-propriedade", "prop@exemplo.com")[0]
        alfa = _contexto(conexao, admin)
        beta = _contexto(conexao, admin, nome="Beta")
        chaves = [alfa, beta]
        for organizacao in (alfa, beta):
            nova = cb.emitir_chave(
                conexao,
                organizacao_id=organizacao.organizacao_id,
                ator_id=admin.id,
                agora=AGORA,
            )
            contexto = cb.conferir_chave(conexao, nova.valor, agora=AGORA)
            chaves.append(contexto)
        esperado = {alfa.organizacao_id: [0, 0, 0], beta.organizacao_id: [0, 0, 0]}
        for indice, negado, linhas, finalidade, minutos in pedidos:
            contexto = chaves[indice]
            cb.registrar_consumo(
                conexao,
                contexto,
                conjunto=CONJUNTO,
                finalidade=finalidade,
                linhas=linhas,
                negado=negado,
                agora=AGORA + timedelta(minutes=minutos),
            )
            soma = esperado[contexto.organizacao_id]
            if negado:
                soma[2] += 1
            else:
                soma[0] += 1
                soma[1] += linhas
        for organizacao_id, (aceitos, linhas, negados) in esperado.items():
            assert cb.consumo_do_mes(
                conexao, organizacao_id, AGORA.date()
            ) == cb.ConsumoDoMes(aceitos, linhas, negados)
        transacao.rollback()
