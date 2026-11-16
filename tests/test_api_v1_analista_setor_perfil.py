"""`POST /v1/analista/setor/perfil` (linha 903, tela de Setor): os números do setor por CNAE, na tela do analista.

O leitor tem os testes dele em `test_api_externa_perfil_do_setor.py`; aqui fica o que é da tela: os dois estados,
o bloco barrado que vem `None` (nunca zero), nenhum nome de campo para quem programa, só contagens, o CNAE só no
corpo (nunca no log), o login, o plano da ficha e a base fora do ar. Usa a base de mentira da lista de compradores,
que lê as mesmas tabelas.
"""

import logging

import pytest

from src.analista import leitura, setor
from src.api_externa import rotas as rotas_da_api_externa
from src.api_externa.conjuntos import perfil_do_setor
from src.api_v1 import analista
from src.banco.usuarios import mudar_plano
from tests import test_api_externa_compradores as base_de_mentira
from tests import test_api_v1_rotas as rotas
from tests.test_api_externa_compradores import (
    pasta,  # noqa: F401 - a base de mentira dos compradores
)

chave = rotas.chave
cliente = rotas.cliente
ROTA = "/api/v1/analista/setor/perfil"
HOJE = base_de_mentira.AGORA.date()
SETOR = base_de_mentira.SETOR


def _mudar_plano(banco, plano: str) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), plano)


@pytest.fixture(autouse=True)
def base_do_dia(pasta, monkeypatch, cliente, banco):  # noqa: F811
    """A base de mentira, a prontidão pronta e a conta no Pro, no dia do cenário."""
    _mudar_plano(banco, "pro")
    monkeypatch.setattr(
        rotas_da_api_externa,
        "regras_da_api",
        lambda: base_de_mentira._regras(*base_de_mentira.TABELAS),
    )
    monkeypatch.setattr(analista, "hoje", lambda: HOJE)
    return pasta


def _pedir(cliente, cnae: str = SETOR):
    return cliente.post(ROTA, json={"cnae": cnae})


def test_o_perfil_sai_com_total_uf_aberturas_fonte_e_dia(cliente):
    resposta = _pedir(cliente)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == leitura.PRONTA
    assert dados["cnae_principal"] == SETOR
    assert dados["empresas_ativas"] == 3  # o mesmo número da lista de compradores
    assert {u["uf"] for u in dados["por_uf"]} >= {"SP", "RJ"}
    anos = [a["ano"] for a in dados["aberturas_por_ano"]]
    assert anos == list(range(HOJE.year - 10, HOJE.year + 1))
    assert dados["blocos_nao_disponiveis"] == []
    assert dados["data_do_retrato"]
    assert dados["publico_em"]
    assert {f["fonte"] for f in dados["fontes"]} == {"rfb-cnpj"}


def test_o_total_bate_com_o_da_lista_de_compradores(cliente):
    lista = cliente.post(
        "/api/v1/analista/setor/compradores", json={"cnae": SETOR}
    ).json()
    assert (
        _pedir(cliente).json()["empresas_ativas"] == lista["setor"]["empresas_ativas"]
    )


def test_so_contagens_sem_empresa_nome_nem_pessoa(cliente):
    dados = _pedir(cliente).json()
    assert set(dados) == {
        "estado", "cnae_principal", "como_era_em", "data_do_retrato", "publico_em", "empresas_ativas",
        "por_uf", "aberturas_por_ano", "blocos_nao_disponiveis", "fontes", "limites",
    }  # fmt: skip
    texto = " ".join(str(dados[campo]) for campo in ("por_uf", "aberturas_por_ano"))
    assert base_de_mentira.COMPRADORA not in texto
    assert base_de_mentira.SEM_LISTA not in texto


def test_nenhum_nome_de_campo_de_quem_programa_e_o_limite_do_mei(cliente):
    dados = _pedir(cliente).json()
    texto = " ".join(dados["limites"])
    assert "known_at" not in texto
    assert "unavailable_sections" not in texto
    assert "para esta organização" not in texto
    assert "MEI" in texto  # MEI e empresário individual não entram, dito à vista
    assert "no dia da consulta" in texto


def test_cnae_sem_empresa_sai_com_zero_de_verdade_e_nao_com_erro(cliente):
    dados = _pedir(cliente, "9999999").json()
    assert dados["estado"] == leitura.PRONTA
    assert dados["empresas_ativas"] == 0
    assert dados["por_uf"] == []


def test_sem_prontidao_sai_nao_liberada_sem_numero_nenhum(cliente, monkeypatch):
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", lambda: base_de_mentira._regras()
    )
    resposta = _pedir(cliente)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["estado"] == leitura.NAO_LIBERADA
    assert dados["empresas_ativas"] is None
    assert dados["por_uf"] is None
    assert dados["aberturas_por_ano"] is None


def test_bloco_barrado_vem_none_e_nomeado_nunca_zero(cliente, monkeypatch):
    def sem_o_bloco(*_args, **_kwargs):
        from src.analista.leitura import Resposta

        corpo = {
            "como_era_em": HOJE.isoformat(),
            "cnae_principal": SETOR,
            "data_do_retrato": "2026-10",
            "publico_em": "2026-10-31",
            "empresas_ativas": 3,
            "por_uf": None,
            "aberturas_por_ano": [{"ano": HOJE.year, "aberturas": 0}],
            "blocos_nao_disponiveis": ["por_uf"],
            "limites": ["Os blocos em blocos_nao_disponiveis não foram consultados."],
        }
        return Resposta(leitura.PRONTA, corpo, [], 1)

    monkeypatch.setattr(setor, "perfil", sem_o_bloco)
    dados = _pedir(cliente).json()
    assert dados["por_uf"] is None
    assert dados["blocos_nao_disponiveis"] == ["por_uf"]


def test_o_limite_do_bloco_barrado_fala_do_campo_da_tela():
    limites = setor.limites_da_tela(
        [perfil_do_setor.LIMITE_DO_BLOCO_NAO_DISPONIVEL],
        perfil_do_setor.NAO_DISPONIVEIS,
    )
    assert "blocos_nao_disponiveis" in limites[0]
    assert "unavailable_sections" not in limites[0]


@pytest.mark.parametrize("cnae", ["62", "abcdefg", "6" * 40, ""])
def test_cnae_fora_da_forma_e_422_sem_repetir_o_texto(cliente, cnae):
    resposta = _pedir(cliente, cnae)
    assert resposta.status_code == 422
    assert "abcdefg" not in resposta.text


def test_o_cnae_nao_vai_para_o_log(cliente, caplog):
    with caplog.at_level(logging.INFO):
        _pedir(cliente)
    registros = " ".join(r.getMessage() for r in caplog.records)
    assert SETOR not in registros
    assert "perfil do setor do analista: pronta" in registros


def test_sem_login_e_401(pasta):  # noqa: F811
    from fastapi.testclient import TestClient

    from src.api import criar_app

    resposta = TestClient(criar_app()).post(ROTA, json={"cnae": SETOR})
    assert resposta.status_code in (401, 403)


def test_a_conta_gratuita_sem_o_recurso_da_ficha_e_barrada(cliente, banco):
    _mudar_plano(banco, "gratuito")
    assert _pedir(cliente).status_code == 403


def test_a_base_fora_do_ar_e_503_sem_dizer_onde(cliente, monkeypatch):
    def sem_base(_banco):
        raise OSError("/caminho/secreto")

    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", sem_base)
    resposta = _pedir(cliente)
    assert resposta.status_code == 503
    assert "secreto" not in resposta.text
