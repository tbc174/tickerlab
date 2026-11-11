"""Comparar empresas na tela do analista (linha 798, PR 2): `POST /v1/analista/comparar` e a planilha.

A regra tem os testes dela em `test_analista_comparacao.py`; aqui fica o que é da rota: login, termos e plano (a
página `comparar_empresas`, o mesmo recurso da ficha), a base fora do ar (503), os estados da tela, o pedido
fora da regra (422, sem repetir o que foi pedido) e a planilha. Nenhuma consulta é por conta (a base é a mesma
para todos), então não há teste de duas contas: o que muda de uma conta para outra é só o plano, testado aqui.
"""

import io
import logging

import openpyxl
import pytest

from base.porta import Porta
from src import paginas
from src.analista import comparacao
from src.api_externa import rotas as rotas_da_api_externa
from src.api_v1 import analista
from src.banco.usuarios import mudar_plano
from tests import test_analista_comparacao as comparacao_de_mentira
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_v1_rotas as rotas

chave = rotas.chave  # as fixtures da conta logada, as mesmas dos outros testes da API
cliente = rotas.cliente
ROTA = "/api/v1/analista/comparar"
PLANILHA = "/api/v1/analista/comparar/planilha"
EMPRESA = empresas_de_mentira.EMPRESA
MEI = empresas_de_mentira.MEI
PEDIDO = {"cnpjs": [EMPRESA, MEI]}


@pytest.fixture(autouse=True)
def base(tmp_path, monkeypatch, cliente, banco):
    """A base de mentira (ficha e busca) pela porta da API externa, as tabelas prontas e a conta no Pro."""
    _mudar_plano(banco, "pro")
    pasta = comparacao_de_mentira.base_de_teste(tmp_path)
    monkeypatch.setattr(
        rotas_da_api_externa, "abrir_porta", lambda banco_: Porta(pasta, banco_)
    )
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", comparacao_de_mentira._regras
    )
    monkeypatch.setattr(analista, "hoje", lambda: comparacao_de_mentira.HOJE)
    return pasta


def _mudar_plano(banco, plano: str) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), plano)


def _nao_abre(_banco):
    raise AssertionError("a base não pode ser aberta aqui")


# ---------------------------------------------------------------- o que sai


def test_comparacao_pronta_na_ordem_do_pedido(cliente):
    resposta = cliente.post(ROTA, json=PEDIDO)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == "pronta"
    assert dados["como_era_em"] == comparacao_de_mentira.HOJE.isoformat()
    empresa, mei = dados["empresas"]
    assert empresa["cnpj"] == EMPRESA and empresa["estado"] == "pronta"
    assert empresa["situacao_cadastral"]["fonte"] == "rfb-cnpj"
    assert empresa["uf"]["valor"] == "MG"
    assert empresa["capital_social"]["valor"] == 6_000_000.0
    assert empresa["porte_descricao"] == "Demais"
    assert empresa["entregas_conhecidas"] >= 1
    assert empresa["ultima_entrega_situacao"]["valor"]
    # o MEI sai igual a um CNPJ que não existe: só o CNPJ pedido e o estado
    assert {nome: valor for nome, valor in mei.items() if valor is not None} == {
        "cnpj": MEI,
        "estado": "nao_disponivel",
    }
    assert dados["limites"] == list(comparacao.LIMITES)
    assert "rfb-cnpj" in {f["fonte"] for f in dados["fontes"]}


def test_sem_prontidao_e_estado_da_tela_nao_erro(cliente, monkeypatch):
    monkeypatch.setattr(
        rotas_da_api_externa,
        "regras_da_api",
        lambda: comparacao_de_mentira._regras(()),
    )
    resposta = cliente.post(ROTA, json=PEDIDO)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["estado"] == "nao_liberada"
    assert dados["empresas"] == [] and dados["fontes"] == []


# ---------------------------------------------------------------- o que não sai


@pytest.mark.parametrize(
    "cnpjs",
    [
        [],
        [EMPRESA],
        [EMPRESA, "123"],
        [EMPRESA, EMPRESA],
        [EMPRESA, "1" * 40],
        [EMPRESA, MEI, "1", "2", "3", "4"],
    ],
)
def test_pedido_fora_da_regra_e_422_sem_repetir_o_pedido(cliente, cnpjs):
    for rota in (ROTA, PLANILHA):
        resposta = cliente.post(rota, json={"cnpjs": cnpjs})
        assert resposta.status_code == 422
        assert resposta.json() == {"detail": analista.COMPARACAO_INVALIDA}


def test_sem_login_401(cliente):
    cliente.headers.pop("Cookie")
    assert cliente.post(ROTA, json=PEDIDO).status_code == 401
    assert cliente.post(PLANILHA, json=PEDIDO).status_code == 401


def test_plano_sem_o_dossie_da_base_403_sem_ler_a_base(cliente, banco, monkeypatch):
    _mudar_plano(banco, "gratuito")
    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", _nao_abre)
    resposta = cliente.post(ROTA, json=PEDIDO)
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == paginas.motivo_da_pagina(
        "gratuito", analista.PAGINA_DA_COMPARACAO
    )
    assert cliente.post(PLANILHA, json=PEDIDO).status_code == 403


def test_base_fora_do_ar_503_sem_dizer_onde(cliente, monkeypatch):
    def falha(_banco):
        raise OSError("C:/caminho/da/base")

    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", falha)
    for rota in (ROTA, PLANILHA):
        resposta = cliente.post(rota, json=PEDIDO)
        assert resposta.status_code == 503
        assert resposta.json() == {"detail": analista.BASE_FORA_DO_AR}


def test_o_log_grava_so_o_estado(cliente, caplog):
    with caplog.at_level(logging.DEBUG):
        cliente.post(ROTA, json=PEDIDO)
    assert EMPRESA not in caplog.text and MEI not in caplog.text


# ---------------------------------------------------------------- planilha


def test_planilha_uma_linha_por_empresa_com_as_fontes(cliente):
    resposta = cliente.post(PLANILHA, json=PEDIDO)
    assert resposta.status_code == 200, resposta.text
    disposicao = resposta.headers["content-disposition"]
    assert (
        disposicao
        == f'attachment; filename="{analista.NOME_DA_PLANILHA_DA_COMPARACAO}"'
    )
    assert resposta.headers["cache-control"] == "no-store"
    pasta = openpyxl.load_workbook(io.BytesIO(resposta.content))
    assert "empresas" in pasta.sheetnames and "fontes" in pasta.sheetnames
    linhas = list(pasta["empresas"].values)
    cabecalho = linhas[0]
    assert "capital_social" in cabecalho and "estado" in cabecalho
    assert [linha[cabecalho.index("cnpj")] for linha in linhas[1:]] == [EMPRESA, MEI]


def test_planilha_sem_prontidao_404(cliente, monkeypatch):
    monkeypatch.setattr(
        rotas_da_api_externa,
        "regras_da_api",
        lambda: comparacao_de_mentira._regras(()),
    )
    resposta = cliente.post(PLANILHA, json=PEDIDO)
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": analista.COMPARACAO_INDISPONIVEL}
