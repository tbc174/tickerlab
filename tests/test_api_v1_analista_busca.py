"""A busca de empresas da tela do analista (linha 798, PR 3): `POST /v1/analista/empresas` e a planilha.

A regra tem os testes dela em `test_analista_busca.py`; aqui fica o que é da rota: login, termos e plano (a
página `encontrar_empresas`, o mesmo recurso da ficha), a base fora do ar (503), os estados da tela, os
filtros inválidos (422) e a planilha. A porta e as regras do portão são as da API externa: os testes trocam
as mesmas funções que os testes de lá. Nenhuma consulta é por conta (a base é a mesma para todos), então não
há teste de duas contas: o que muda de uma conta para outra é só o plano, testado aqui.
"""

import io
import logging

import openpyxl
import pytest

from base.porta import Porta
from src import paginas
from src.analista import busca
from src.api_externa import rotas as rotas_da_api_externa
from src.api_v1 import analista
from src.banco.usuarios import mudar_plano
from tests import test_analista_busca as busca_de_mentira
from tests import test_api_v1_rotas as rotas

chave = rotas.chave  # as fixtures da conta logada, as mesmas dos outros testes da API
cliente = rotas.cliente
ROTA = "/api/v1/analista/empresas"
PLANILHA = "/api/v1/analista/empresas/planilha"
ALFA = "11111111000191"


@pytest.fixture(autouse=True)
def base(tmp_path, monkeypatch, cliente, banco):
    """A base de mentira da prospecção pela porta da API externa, as tabelas prontas e a conta no Pro."""
    _mudar_plano(banco, "pro")
    pasta = busca_de_mentira.base_de_teste(tmp_path)
    monkeypatch.setattr(
        rotas_da_api_externa, "abrir_porta", lambda banco_: Porta(pasta, banco_)
    )
    monkeypatch.setattr(rotas_da_api_externa, "regras_da_api", busca_de_mentira._regras)
    monkeypatch.setattr(analista, "hoje", lambda: busca_de_mentira.HOJE)
    return pasta


def _mudar_plano(banco, plano: str) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), plano)


def _nao_abre(_banco):
    raise AssertionError("a base não pode ser aberta aqui")


# ---------------------------------------------------------------- o que sai


def test_busca_pronta_com_nomes_fontes_limites_e_opcoes(cliente):
    resposta = cliente.post(ROTA, json={"setores": ["J"]})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == "pronta"
    assert dados["como_era_em"] == busca_de_mentira.HOJE.isoformat()
    (empresa,) = dados["empresas"]
    assert empresa["cnpj"] == ALFA
    assert empresa["razao_social"]["valor"] == "ALFA TECNOLOGIA S.A."
    assert empresa["razao_social"]["fonte"] == "rfb-cnpj"
    assert empresa["municipio_nome"] == "BELO HORIZONTE"
    assert empresa["porte_descricao"] == "Demais"
    assert dados["cortada"] is False and dados["proximo_cursor"] is None
    assert [f["fonte"] for f in dados["fontes"]] == ["rfb-cnpj"]
    assert dados["limites"] == list(busca.LIMITES)
    assert dados["setores"] == busca.setores_como_lista()
    assert dados["ufs"] == list(busca.UFS)


def test_carregar_mais_pelo_cursor(cliente, monkeypatch):
    monkeypatch.setattr(busca, "TAMANHO_DA_PAGINA", 1)
    primeira = cliente.post(ROTA, json={"ufs": ["SP", "MG"]}).json()
    assert [e["cnpj"] for e in primeira["empresas"]] == [ALFA]
    segunda = cliente.post(
        ROTA, json={"ufs": ["SP", "MG"], "cursor": primeira["proximo_cursor"]}
    ).json()
    assert [e["cnpj"] for e in segunda["empresas"]] == ["22222222000191"]


def test_sem_filtro_traz_as_opcoes_sem_abrir_a_base(cliente, monkeypatch):
    # a tela abre o formulário com este pedido: nem a base fora do ar o derruba
    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", _nao_abre)
    resposta = cliente.post(ROTA, json={})
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["estado"] == busca.SEM_FILTRO
    assert dados["empresas"] == [] and dados["como_era_em"] is None
    assert len(dados["setores"]) == len(busca.SETORES)


def test_sem_prontidao_e_estado_da_tela_nao_erro(cliente, monkeypatch):
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", busca_de_mentira._sem_prontidao
    )
    resposta = cliente.post(ROTA, json={"ufs": ["SP"]})
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["estado"] == "nao_liberada"
    assert dados["empresas"] == [] and dados["fontes"] == []


# ---------------------------------------------------------------- o que não sai


@pytest.mark.parametrize(
    "pedido",
    [
        {"setores": ["T"]},
        {"setores": ["A", "C", "G", "J"]},
        {"ufs": ["XX"]},
        {"idade_minima": 0},
        {"idade_minima": busca.IDADE_MAXIMA + 1},
        {"ufs": ["SP"], "cursor": "nao-e-cursor"},
        {"ufs": ["SP"] * (len(busca.UFS) + 1)},
    ],
)
def test_filtro_fora_do_que_a_tela_oferece_e_422(cliente, pedido):
    assert cliente.post(ROTA, json=pedido).status_code == 422
    assert cliente.post(PLANILHA, json=pedido).status_code == 422


def test_sem_login_401(cliente):
    cliente.headers.pop("Cookie")
    assert cliente.post(ROTA, json={"ufs": ["SP"]}).status_code == 401
    assert cliente.post(PLANILHA, json={"ufs": ["SP"]}).status_code == 401


def test_plano_sem_o_dossie_da_base_403_sem_ler_a_base(cliente, banco, monkeypatch):
    _mudar_plano(banco, "gratuito")
    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", _nao_abre)
    resposta = cliente.post(ROTA, json={"ufs": ["SP"]})
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == paginas.motivo_da_pagina(
        "gratuito", analista.PAGINA_DA_BUSCA
    )
    assert cliente.post(PLANILHA, json={"ufs": ["SP"]}).status_code == 403


def test_base_fora_do_ar_503_sem_dizer_onde(cliente, monkeypatch):
    def falha(_banco):
        raise OSError("C:/caminho/da/base")

    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", falha)
    for rota in (ROTA, PLANILHA):
        resposta = cliente.post(rota, json={"ufs": ["SP"]})
        assert resposta.status_code == 503
        assert resposta.json() == {"detail": analista.BASE_FORA_DO_AR}


def test_o_log_grava_so_o_estado(cliente, caplog):
    with caplog.at_level(logging.DEBUG):
        cliente.post(ROTA, json={"setores": ["J"]})
    assert ALFA not in caplog.text and "ALFA TECNOLOGIA" not in caplog.text


# ---------------------------------------------------------------- planilha


def test_planilha_com_as_empresas_os_nomes_e_as_fontes(cliente):
    resposta = cliente.post(PLANILHA, json={"ufs": ["SP", "MG"]})
    assert resposta.status_code == 200, resposta.text
    disposicao = resposta.headers["content-disposition"]
    assert disposicao == f'attachment; filename="{analista.NOME_DA_PLANILHA_DA_BUSCA}"'
    assert resposta.headers["cache-control"] == "no-store"
    pasta = openpyxl.load_workbook(io.BytesIO(resposta.content))
    assert pasta.sheetnames == ["campos", "empresas", "fontes"]
    linhas = list(pasta["empresas"].values)
    cabecalho = linhas[0]
    assert "municipio_nome" in cabecalho and "fonte" in cabecalho
    assert [linha[cabecalho.index("cnpj")] for linha in linhas[1:]] == [
        ALFA,
        "22222222000191",
    ]


def test_planilha_sem_filtro_ou_sem_prontidao_404(cliente, monkeypatch):
    assert cliente.post(PLANILHA, json={}).status_code == 404
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", busca_de_mentira._sem_prontidao
    )
    assert cliente.post(PLANILHA, json={"ufs": ["SP"]}).status_code == 404
