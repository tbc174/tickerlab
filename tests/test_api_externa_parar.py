"""Os botões de parar da API externa valem na hora, em todas as rotas (B-32a, PR 6, tarefa 12).

Revogar a chave, suspender a organização, suspender um conjunto para todos e a rotação com prazo, cada
um conferido no app de verdade, em cada rota de `/data/v1`, no pedido seguinte (sem esperar cache nem
reinício). As rotas de dado conferem os mesmos botões nos próprios testes (os fundos em
`test_api_externa_fundos.py`, que precisa da base de exemplo); aqui, o conjunto suspenso é conferido
também no `acesso.autorizar`, por onde todas elas passam.
"""

from datetime import timedelta

import pytest

from src.api_externa import acesso, rotas
from src.banco import chaves_da_api as cb
from src.chaves_da_api import ContextoDaChave
from src.portao_externo import codigo_publico
from tests import ajudantes_da_api_externa as aj

ROTAS = ("/data/v1/catalog", "/data/v1/usage")
OUTRO_CONJUNTO = "itr"


@pytest.fixture
def cenario(banco, monkeypatch):
    """Uma organização com chave e contrato de dois conjuntos, e o portão liberando os dois."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=OUTRO_CONJUNTO)
    monkeypatch.setattr(
        rotas,
        "regras_da_api",
        lambda: aj.portao_liberando(
            aj.linha_do_portao(), aj.linha_do_portao(conjunto=OUTRO_CONJUNTO)
        ),
    )
    return ator, org, chave


def _status(cliente, chave, rota):
    return cliente.get(rota, headers=aj.bearer(chave.valor)).status_code


@pytest.mark.parametrize("rota", ROTAS)
def test_chave_revogada_da_401_no_pedido_seguinte(banco, monkeypatch, cenario, rota):
    ator, org, chave = cenario
    cliente = aj.cliente_da_api(monkeypatch)
    assert _status(cliente, chave, rota) == 200
    with banco.begin() as conexao:
        assert cb.revogar_chave(
            conexao, organizacao_id=org.id, chave_id=chave.chave_id, ator_id=ator.id
        )
    resposta = cliente.get(rota, headers=aj.bearer(chave.valor))
    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "invalid_api_key"}


@pytest.mark.parametrize("rota", ROTAS)
def test_organizacao_suspensa_da_401(banco, monkeypatch, cenario, rota):
    ator, org, chave = cenario
    cliente = aj.cliente_da_api(monkeypatch)
    assert _status(cliente, chave, rota) == 200
    with banco.begin() as conexao:
        cb.suspender_organizacao(
            conexao, organizacao_id=org.id, motivo="pagamento", ator_id=ator.id
        )
    resposta = cliente.get(rota, headers=aj.bearer(chave.valor))
    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "invalid_api_key"}  # não diz que foi suspensa
    with banco.begin() as conexao:
        cb.reativar_organizacao(conexao, organizacao_id=org.id, ator_id=ator.id)
    assert _status(cliente, chave, rota) == 200


def _conjuntos_do_catalogo(cliente, chave) -> list[str]:
    resposta = cliente.get("/data/v1/catalog", headers=aj.bearer(chave.valor))
    assert resposta.status_code == 200
    return [item["dataset"] for item in resposta.json()["datasets"]]


def _autorizar(banco, chave, conjunto):
    with banco.connect() as conexao:
        contexto = cb.conferir_chave(conexao, chave.valor, agora=aj.AGORA)
        assert isinstance(contexto, ContextoDaChave)
        return acesso.autorizar(
            conexao,
            contexto,
            fonte="cvm-dfp",
            conjunto=conjunto,
            campo="valor",
            finalidade="analise",
            hoje=aj.HOJE,
            regras=rotas.regras_da_api(),
        )


def test_conjunto_suspenso_some_do_catalogo_e_da_not_available(
    banco, monkeypatch, cenario
):
    ator, _org, chave = cenario
    cliente = aj.cliente_da_api(monkeypatch)
    assert _conjuntos_do_catalogo(cliente, chave) == [aj.CONJUNTO, OUTRO_CONJUNTO]
    assert _autorizar(banco, chave, aj.CONJUNTO).libera

    with banco.begin() as conexao:
        cb.suspender_conjunto(
            conexao, conjunto=aj.CONJUNTO, motivo="fonte", ator_id=ator.id
        )
    assert _conjuntos_do_catalogo(cliente, chave) == [OUTRO_CONJUNTO]
    negado = _autorizar(banco, chave, aj.CONJUNTO)
    assert codigo_publico(negado) == "not_available"  # o mesmo de toda negação
    assert _autorizar(banco, chave, OUTRO_CONJUNTO).libera
    assert _status(cliente, chave, "/data/v1/usage") == 200  # a chave segue valendo

    with banco.begin() as conexao:
        cb.reativar_conjunto(conexao, conjunto=aj.CONJUNTO, ator_id=ator.id)
    assert _conjuntos_do_catalogo(cliente, chave) == [aj.CONJUNTO, OUTRO_CONJUNTO]


@pytest.mark.parametrize("rota", ROTAS)
def test_rotacao_aceita_a_antiga_ate_o_prazo(banco, monkeypatch, cenario, rota):
    ator, org, antiga = cenario
    with banco.begin() as conexao:
        nova = cb.rotacionar_chave(
            conexao,
            organizacao_id=org.id,
            chave_id=antiga.chave_id,
            ator_id=ator.id,
            agora=aj.AGORA,
        )
    prazo = aj.AGORA + cb.PRAZO_DA_ROTACAO
    antes = aj.cliente_da_api(monkeypatch, prazo - timedelta(seconds=1))
    assert _status(antes, antiga, rota) == 200
    assert _status(antes, nova, rota) == 200
    depois = aj.cliente_da_api(monkeypatch, prazo + timedelta(seconds=1))
    assert _status(depois, antiga, rota) == 401
    assert _status(depois, nova, rota) == 200
