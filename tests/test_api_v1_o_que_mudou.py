"""A rota da página "O que mudou" (linha 804): `GET /v1/o-que-mudou`.

Livre para toda conta logada (a página não tem recurso de plano); sem login, 401. O corpo é o registro de
`src/o_que_mudou.py`, sem tradução.
"""

from src import o_que_mudou
from src.banco.usuarios import mudar_plano
from tests import test_api_v1_rotas as rotas

chave = rotas.chave  # as fixtures da conta logada, as mesmas dos outros testes da API
cliente = rotas.cliente
ROTA = "/api/v1/o-que-mudou"


def test_conta_gratuita_ve_o_que_mudou(cliente, banco):
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "gratuito")
    resposta = cliente.get(ROTA)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {"entregas": o_que_mudou.como_lista()}


def test_sem_login_401(cliente):
    cliente.headers.pop("Cookie")
    assert cliente.get(ROTA).status_code == 401
