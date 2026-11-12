"""`POST /v1/analista/ficha/vinculos` (linha 798, PR 5): controle, coligação, participação e auditoria na ficha.

O leitor tem os testes dele em `test_api_externa_por_cnpj_vinculos.py`; aqui fica o que é da tela: os três
estados (nunca erro por falta de prontidão), pessoa e fundo fora da lista, o nome da rede (o de hoje) fora da
resposta, o CNPJ só no corpo, o login e o plano da ficha, e a base fora do ar.
"""

import logging

import pytest

from base.porta import Porta
from src import paginas
from src.analista import leitura, vinculos
from src.api_externa import rotas as rotas_da_api_externa
from src.api_v1 import analista
from src.banco.usuarios import mudar_plano
from tests import test_analista_leitura as leitura_de_mentira
from tests import test_api_externa_por_cnpj_vinculos as vinculos_de_mentira
from tests import test_api_v1_rotas as rotas

chave = rotas.chave
cliente = rotas.cliente
ROTA = "/api/v1/analista/ficha/vinculos"
ALFA = vinculos_de_mentira.ALFA
TABELAS = ("ligacoes", "entidades", "identificadores", "cnpj_empresas_pj")


def _mudar_plano(banco, plano: str) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), plano)


@pytest.fixture(autouse=True)
def base(tmp_path, monkeypatch, cliente, banco):
    """A base de mentira dos vínculos pela porta da API externa, a prontidão pronta e a conta no Pro."""
    _mudar_plano(banco, "pro")
    pasta = vinculos_de_mentira.gravar_base(tmp_path / "base")
    monkeypatch.setattr(
        rotas_da_api_externa, "abrir_porta", lambda banco_: Porta(pasta, banco_)
    )
    monkeypatch.setattr(
        rotas_da_api_externa,
        "regras_da_api",
        lambda: leitura_de_mentira._regras(TABELAS),
    )
    monkeypatch.setattr(analista, "hoje", lambda: leitura_de_mentira.HOJE)
    return pasta


def _pedir(cliente, cnpj: str = ALFA):
    return cliente.post(ROTA, json={"cnpj": cnpj})


def test_vinculos_prontos_com_fonte_data_e_limites(cliente):
    resposta = _pedir(cliente)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == leitura.PRONTA
    tipos = {v["campos"]["tipo"]["valor"] for v in dados["vinculos"]}
    assert {"subsidiary_of", "affiliate_of", "audits"} <= tipos
    controlada = next(
        v for v in dados["vinculos"] if v["campos"]["tipo"]["valor"] == "subsidiary_of"
    )
    assert controlada["campos"]["tipo"]["fonte"] == "cvm-hist-fre"
    assert controlada["campos"]["tipo"]["publico_em"]
    assert {f["fonte"] for f in dados["fontes"]} >= {"cvm-hist-fre", "cvm-hist-fca"}
    assert dados["limites"] == list(vinculos.LIMITES)
    assert all("known_at" not in limite for limite in dados["limites"])


def test_a_ponta_traz_o_nome_do_dia_nunca_o_da_rede(cliente):
    texto = _pedir(cliente).text
    assert "ALFA HOLDING S.A." in texto or "ALFA LTDA" in texto  # histórico da Receita
    assert "COLIGADA PELO GLEIF" not in texto  # o nome da rede é o de hoje e não sai


def test_pessoa_fundo_e_outras_ligacoes_nao_saem(cliente):
    texto = _pedir(cliente).text
    assert "FUNDO X" not in texto
    assert "P0123456789abcdef0123" not in texto
    dados = _pedir(cliente).json()
    for vinculo in dados["vinculos"]:
        assert vinculo["campos"]["tipo"]["valor"] in {
            "subsidiary_of",
            "affiliate_of",
            "investee_of",
            "audits",
        }


def test_o_mesmo_numero_de_vinculos_da_leitura(cliente, base):
    dados = _pedir(cliente).json()
    with Porta(base) as porta:
        esperado = vinculos.vinculos(
            porta,
            ALFA,
            hoje=leitura_de_mentira.HOJE,
            regras=leitura_de_mentira._regras(TABELAS),
        )
    assert len(dados["vinculos"]) == len(esperado.corpo["vinculos"])
    assert dados["cortada"] == esperado.corpo["cortada"]


@pytest.mark.parametrize(
    "cnpj", [vinculos_de_mentira.PESSOA, vinculos_de_mentira.FORA_DA_REDE]
)
def test_pessoa_e_cnpj_que_a_rede_nao_conhece_dao_a_mesma_resposta(cliente, cnpj):
    dados = _pedir(cliente, cnpj).json()
    assert dados["estado"] == leitura.NAO_DISPONIVEL
    assert dados["vinculos"] == []
    assert dados["limites"] == list(vinculos.LIMITES)


def test_sem_prontidao_e_estado_da_tela_nao_erro(cliente, monkeypatch):
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", leitura_de_mentira._sem_prontidao
    )
    resposta = _pedir(cliente)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["estado"] == leitura.NAO_LIBERADA
    assert dados["vinculos"] == []


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
    assert any("vínculos do analista" in r.message for r in caplog.records)
    assert ALFA not in caplog.text
