"""A rota da página "Conectar" (linha 832): `GET /v1/conectar`.

Livre para toda conta logada; sem login, 401. O endereço do conector é o do próprio conector, e nenhuma
chave de verdade aparece: só o exemplo `tld_...`.
"""

import re

from conector_remoto.configuracao import URL_PUBLICA_PADRAO
from src import conectar
from src.banco.usuarios import mudar_plano
from tests import test_api_v1_rotas as rotas

chave = rotas.chave  # as fixtures da conta logada, as mesmas dos outros testes da API
cliente = rotas.cliente
ROTA = "/api/v1/conectar"


def test_conta_gratuita_ve_a_pagina(cliente, banco):
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "gratuito")
    resposta = cliente.get(ROTA)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == conectar.como_dicionario()


def test_o_endereco_e_o_do_conector_de_verdade():
    assert f"{URL_PUBLICA_PADRAO}/mcp" == conectar.ENDERECO_DO_CONECTOR


def test_nenhuma_chave_de_verdade_no_texto():
    """Só o exemplo `tld_...`: nada que pareça uma chave inteira (tld_ seguido de letras e números)."""
    texto = str(conectar.como_dicionario())
    assert conectar.CHAVE_DE_EXEMPLO == "tld_..."
    assert re.search(r"tld_[A-Za-z0-9_-]{8,}", texto) is None


def test_o_cnpj_de_exemplo_nao_e_de_empresa_de_verdade():
    assert conectar.CNPJ_DE_EXEMPLO == "00.000.000/0001-00"
    assert "tickerlab login" in str(conectar.COMANDOS_DA_CLI)


def test_sem_login_401(cliente):
    cliente.headers.pop("Cookie")
    assert cliente.get(ROTA).status_code == 401
