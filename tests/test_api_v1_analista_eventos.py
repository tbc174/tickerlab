"""`POST /v1/analista/ficha/eventos` (linha 798, PR 4): os documentos à CVM e as trocas de auditor na ficha.

O leitor tem os testes dele em `test_api_externa_por_cnpj_eventos.py`; aqui fica o que é da tela: os três
estados (nunca erro por falta de prontidão), o mesmo corpo do leitor, o assunto livre e o auditor que pode ser
pessoa fora da resposta, a página com cursor, o CNPJ só no corpo, o login e o plano da ficha, e a base fora do ar.
"""

import logging

import pytest

from base.porta import Porta
from src import paginas
from src.analista import eventos, leitura
from src.api_externa import rotas as rotas_da_api_externa
from src.api_v1 import analista
from src.banco.usuarios import mudar_plano
from tests import test_analista_leitura as leitura_de_mentira
from tests import test_api_externa_por_cnpj_eventos as eventos_de_mentira
from tests import test_api_v1_rotas as rotas

chave = rotas.chave
cliente = rotas.cliente
ROTA = "/api/v1/analista/ficha/eventos"
ALFA = eventos_de_mentira.ALFA
TABELAS = ("eventos", "trocas_de_auditor")


def _mudar_plano(banco, plano: str) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), plano)


@pytest.fixture(autouse=True)
def base(tmp_path, monkeypatch, cliente, banco):
    """A base de mentira dos eventos pela porta da API externa, a prontidão pronta e a conta no Pro."""
    _mudar_plano(banco, "pro")
    pasta = eventos_de_mentira.gravar_base(tmp_path / "base")
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


def _pedir(cliente, **corpo):
    return cliente.post(ROTA, json={"cnpj": ALFA, **corpo})


def test_eventos_prontos_com_fonte_data_e_limites(cliente):
    resposta = _pedir(cliente)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == leitura.PRONTA
    assert {e["tipo"] for e in dados["eventos"]} == {"ipe_filing", "auditor_change"}
    documento = next(e for e in dados["eventos"] if e["tipo"] == "ipe_filing")
    assert documento["campos"]["categoria"]["fonte"] == "cvm-hist-ipe"
    assert documento["campos"]["categoria"]["publico_em"]
    assert {f["fonte"] for f in dados["fontes"]} == {"cvm-hist-ipe", "cvm-hist-fca"}
    assert dados["limites"] == list(eventos.LIMITES)
    assert all("known_at" not in limite for limite in dados["limites"])


def test_a_rota_devolve_os_eventos_do_leitor_sem_assunto_livre_nem_auditor_pessoa(
    cliente,
):
    texto = _pedir(cliente).text
    assert "Aquisição da Gama" not in texto  # o assunto livre da companhia nunca sai
    assert "FULANO AUDITOR" not in texto  # auditor que pode ser pessoa física não sai
    assert "AUDITORA UM" in texto


def test_o_mesmo_corpo_da_leitura(cliente, base):
    dados = _pedir(cliente).json()
    with Porta(base) as porta:
        esperado = eventos.eventos(
            porta,
            ALFA,
            hoje=leitura_de_mentira.HOJE,
            regras=leitura_de_mentira._regras(TABELAS),
        )
    assert len(dados["eventos"]) == len(esperado.corpo["eventos"])
    assert dados["proximo_cursor"] == esperado.corpo["proximo_cursor"]


def test_as_paginas_seguem_pelo_cursor_sem_perder_nem_repetir(cliente, monkeypatch):
    monkeypatch.setattr(eventos, "LINHAS_POR_PAGINA", 2)
    todos, cursor = [], None
    for _ in range(10):
        dados = _pedir(cliente, cursor=cursor).json()
        todos += [(e["tipo"], str(e["campos"])) for e in dados["eventos"]]
        cursor = dados["proximo_cursor"]
        if cursor is None:
            break
    assert cursor is None
    assert len(todos) == len(set(todos)) >= 3


def test_cnpj_que_a_base_nao_conhece_nao_esta_disponivel(cliente):
    dados = _pedir(cliente, cnpj=eventos_de_mentira.FORA_DA_REDE).json()
    assert dados["estado"] == leitura.NAO_DISPONIVEL
    assert dados["eventos"] == []
    assert dados["limites"] == list(eventos.LIMITES)


def test_sem_prontidao_e_estado_da_tela_nao_erro(cliente, monkeypatch):
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", leitura_de_mentira._sem_prontidao
    )
    resposta = _pedir(cliente)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["estado"] == leitura.NAO_LIBERADA
    assert dados["eventos"] == []


@pytest.mark.parametrize("cnpj", ["123", "abc", "", "1" * 400])
def test_cnpj_invalido_422_sem_repetir_o_texto(cliente, cnpj):
    resposta = _pedir(cliente, cnpj=cnpj)
    assert resposta.status_code == 422
    assert "1" * 20 not in resposta.text


@pytest.mark.parametrize("cursor", ["lixo", "x" * 500])
def test_cursor_que_nao_e_nosso_422_sem_repetir_o_texto(cliente, cursor):
    resposta = _pedir(cliente, cursor=cursor)
    assert resposta.status_code == 422
    assert cursor not in resposta.text


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
    assert any("eventos do analista" in r.message for r in caplog.records)
    assert ALFA not in caplog.text
