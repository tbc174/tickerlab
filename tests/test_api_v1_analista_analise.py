"""`POST /v1/analista/ficha/analise` (19/11/2026): a análise completa da empresa na ficha do app.

A regra tem os testes dela em `test_analista_analise.py`; aqui fica o que é da rota: o corpo com frase, blocos,
linha do tempo, leituras, o que não foi achado e o que a tela não consulta; os estados (nunca erro por falta de
prontidão); pessoa física fora; o CNPJ só no corpo e fora do log; o login e o plano da ficha; e a base fora do ar.
"""

import dataclasses
import logging

import pytest

from base.dossie import COLUNAS_DE_PESSOA
from base.porta import Porta
from src import paginas
from src.analista import analise, leitura
from src.api_externa import rotas as rotas_da_api_externa
from src.api_v1 import analista
from src.banco.usuarios import mudar_plano
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_analise as analise_de_mentira
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_socios_pj as socios_de_mentira
from tests import test_api_v1_rotas as rotas

chave = rotas.chave
cliente = rotas.cliente
ROTA = "/api/v1/analista/ficha/analise"
EMPRESA = empresas_de_mentira.EMPRESA


def _mudar_plano(banco, plano: str) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), plano)


@pytest.fixture(autouse=True)
def base(tmp_path, monkeypatch, cliente, banco):
    """A base de mentira dos sócios pela porta da API externa, a prontidão pronta e a conta no Pro."""
    _mudar_plano(banco, "pro")
    pasta = socios_de_mentira.base_com_socios(tmp_path)
    monkeypatch.setattr(
        rotas_da_api_externa, "abrir_porta", lambda banco_: Porta(pasta, banco_)
    )
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", analise_de_mentira._regras
    )
    monkeypatch.setattr(analista, "hoje", lambda: analise_de_mentira.AGORA.date())
    return pasta


def _pedir(cliente, cnpj: str = EMPRESA):
    return cliente.post(ROTA, json={"cnpj": cnpj})


def test_analise_pronta_com_frase_blocos_fontes_e_o_que_nao_traz(cliente):
    resposta = _pedir(cliente)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == leitura.PRONTA
    assert dados["cnpj"] == EMPRESA
    assert dados["frase"]["texto"].startswith("ALFA")
    assert dados["blocos"][0]["nome"] == "cadastro"
    assert "socios_pj" in {b["nome"] for b in dados["blocos"]}
    assert all(b["titulo"] for b in dados["blocos"])
    assert all(item["tipo"] == "inference" for item in dados["leituras"])
    assert analise.CREDITO_NAO_DISPONIVEL in dados["ainda_nao_traz"]
    assert {f["fonte"] for f in dados["fontes"]} >= {"rfb-cnpj"}
    assert dados["limites"]
    assert resposta.headers.get("content-type", "").startswith("application/json")


def test_sem_pessoa_na_resposta(cliente):
    dados = _pedir(cliente).json()
    assert not aj.chaves_de(dados) & COLUNAS_DE_PESSOA
    texto = str(dados)
    assert socios_de_mentira.SEM_LISTA not in texto
    assert socios_de_mentira.EMPRESARIO not in texto


@pytest.mark.parametrize(
    "cnpj",
    [
        empresas_de_mentira.INEXISTENTE,
        empresas_de_mentira.MEI,
        empresas_de_mentira.EMPRESARIO_INDIVIDUAL,
    ],
)
def test_pessoa_e_cnpj_desconhecido_dao_a_mesma_resposta(cliente, cnpj):
    dados = _pedir(cliente, cnpj).json()
    assert dados["estado"] == leitura.NAO_DISPONIVEL
    assert dados["blocos"] == []
    assert dados["fontes"] == []
    assert dados["limites"] == list(analise.LIMITES)


def test_sem_prontidao_e_estado_da_tela_nao_erro(cliente, monkeypatch):
    sem = dataclasses.replace(analise_de_mentira._regras(), prontidao={})
    monkeypatch.setattr(rotas_da_api_externa, "regras_da_api", lambda: sem)
    resposta = _pedir(cliente)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["estado"] == leitura.NAO_LIBERADA
    assert dados["blocos"] == []
    assert dados["limites"] == list(analise.LIMITES)


@pytest.mark.parametrize("cnpj", ["123", "abc", "", "1" * 400])
def test_cnpj_invalido_422_sem_repetir_o_texto(cliente, cnpj):
    resposta = _pedir(cliente, cnpj)
    assert resposta.status_code == 422
    assert "1" * 20 not in resposta.text


def test_sem_login_401(cliente):
    cliente.headers.pop("Cookie")
    assert _pedir(cliente).status_code == 401


def test_plano_sem_o_dossie_da_base_403_sem_ler_a_base(cliente, banco, monkeypatch):
    _mudar_plano(banco, "gratuito")

    def nao_abre(_banco):
        raise AssertionError("a base não pode ser aberta para quem o plano recusa")

    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", nao_abre)
    resposta = _pedir(cliente)
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == paginas.motivo_da_pagina(
        "gratuito", analista.PAGINA
    )


def test_base_fora_do_ar_503_sem_dizer_onde(cliente, monkeypatch):
    def falha(_banco):
        raise OSError("C:/caminho/da/base")

    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", falha)
    resposta = _pedir(cliente)
    assert resposta.status_code == 503
    assert "caminho" not in resposta.text


def test_o_log_leva_so_o_estado_nunca_o_cnpj(cliente, caplog):
    with caplog.at_level(logging.INFO):
        _pedir(cliente)
    assert any("análise do analista" in r.message for r in caplog.records)
    assert EMPRESA not in caplog.text
