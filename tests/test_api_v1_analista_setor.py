"""`POST /v1/analista/setor/compradores` (linha 903, PR D): quem já se mexeu num setor, na tela do analista.

O leitor tem os testes dele em `test_api_externa_compradores.py` (a mesma base de mentira); aqui fica o que é
da tela: os dois estados (nunca erro por falta de prontidão), os nomes de dentro dos sinais, nenhum nome de
campo para quem programa, só pessoa jurídica, o setor só no corpo (nunca no log), o login, o plano da ficha e a
base fora do ar.
"""

import logging

import pytest

from base.porta import Porta
from src.analista import leitura, setor
from src.api_externa import rotas as rotas_da_api_externa
from src.api_externa.conjuntos import compradores
from src.api_v1 import analista
from src.banco.usuarios import mudar_plano
from tests import test_api_externa_compradores as base_de_mentira
from tests import test_api_v1_rotas as rotas
from tests.test_api_externa_compradores import (
    pasta,  # noqa: F401 - a base de mentira dos compradores
)

chave = rotas.chave
cliente = rotas.cliente
ROTA = "/api/v1/analista/setor/compradores"
HOJE = base_de_mentira.AGORA.date()
SETOR = base_de_mentira.SETOR


def _mudar_plano(banco, plano: str) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), plano)


@pytest.fixture(autouse=True)
def base(pasta, monkeypatch, cliente, banco):  # noqa: F811
    """A base de mentira dos compradores, a prontidão pronta e a conta no Pro, no dia do cenário."""
    _mudar_plano(banco, "pro")
    monkeypatch.setattr(
        rotas_da_api_externa,
        "regras_da_api",
        lambda: base_de_mentira._regras(*base_de_mentira.TABELAS),
    )
    monkeypatch.setattr(analista, "hoje", lambda: HOJE)
    return pasta


def _pedir(cliente, **corpo):
    return cliente.post(ROTA, json={"cnae": SETOR, **corpo})


def test_os_compradores_saem_com_sinais_de_dentro_fonte_e_dia(cliente):
    resposta = _pedir(cliente)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == leitura.PRONTA
    raizes = [c["raiz_do_cnpj"] for c in dados["compradores"]]
    assert raizes == [
        base_de_mentira.FUNDO,
        base_de_mentira.COMPRADORA,
        base_de_mentira.ABERTA,
    ]
    fundo = dados["compradores"][0]
    assert fundo["sinais"] == ["entrou_como_socio", "fundo_socio"]
    assert fundo["razao_social"]["fonte"] == "rfb-cnpj"
    exemplo = dados["compradores"][1]["provas"]["entrou_como_socio"]["exemplos"][0]
    assert exemplo["empresa_do_setor"]["razao_social"]["valor"] == "ALVO SP LTDA"
    assert exemplo["campos"]["data_entrada"]["publico_em"]
    assert dados["total_de_compradores"] == 3
    assert dados["cortada"] is False
    assert dados["setor"]["empresas_ativas"] == 3
    assert {f["fonte"] for f in dados["fontes"]} >= {"rfb-cnpj", "cvm-hist-fre"}


def test_nenhum_nome_de_campo_de_quem_programa_na_resposta(cliente):
    texto = _pedir(cliente).text
    assert "known_at" not in texto
    assert "took_stake" not in texto  # o nome de fora do sinal fica na API externa
    dados = _pedir(cliente).json()
    assert any("o dia da consulta" in limite for limite in dados["limites"])
    assert "não intenção de compra" in dados["limites"][0]
    texto_dos_limites = " ".join(dados["limites"])
    assert "valia no dia da consulta" in texto_dos_limites
    assert "depois do dia da consulta" in texto_dos_limites
    assert "para esta organização" not in texto_dos_limites


def test_so_pessoa_juridica_e_a_pessoa_fora_da_lista_nao_sai(cliente):
    texto = _pedir(cliente).text
    assert base_de_mentira.SEM_LISTA not in texto


def test_a_uf_e_os_anos_recortam_o_setor(cliente):
    dados = _pedir(cliente, uf="RJ", anos=2).json()
    assert dados["setor"]["uf"] == "RJ"
    assert dados["setor"]["anos"] == 2
    assert dados["setor"]["empresas_ativas"] == 1


def test_setor_sem_empresa_sai_com_a_lista_vazia_e_nao_com_erro(cliente):
    resposta = _pedir(cliente, cnae="9999999")
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["estado"] == leitura.PRONTA
    assert dados["compradores"] == []
    assert dados["limites"]


def test_sem_prontidao_sai_nao_liberada_com_limites_e_sem_erro(cliente, monkeypatch):
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", lambda: base_de_mentira._regras()
    )
    resposta = _pedir(cliente)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["estado"] == leitura.NAO_LIBERADA
    assert dados["compradores"] == []
    assert dados["setor"] is None


def test_sinal_barrado_vai_em_sinais_nao_disponiveis_com_o_nome_de_dentro(
    cliente, monkeypatch
):
    sem_controladas = tuple(
        t for t in base_de_mentira.TABELAS if t != compradores.CONTROLADAS
    )
    monkeypatch.setattr(
        rotas_da_api_externa,
        "regras_da_api",
        lambda: base_de_mentira._regras(*sem_controladas),
    )
    dados = _pedir(cliente).json()
    assert dados["estado"] == leitura.PRONTA
    assert dados["sinais_nao_disponiveis"] == ["controla_no_setor"]
    assert all("controla_no_setor" not in c["sinais"] for c in dados["compradores"])
    assert any("sinais_nao_disponiveis" in limite for limite in dados["limites"])


@pytest.mark.parametrize(
    "corpo",
    [
        {"cnae": "62"},
        {"cnae": "abcdefg"},
        {"cnae": SETOR, "uf": "XX"},
        {"cnae": SETOR, "anos": 0},
        {"cnae": SETOR, "anos": 11},
        {"cnae": SETOR + "0" * 40},
        {"cnae": SETOR, "uf": "SPX"},
    ],
)
def test_pedido_fora_da_forma_e_422_sem_repetir_o_texto(cliente, corpo):
    resposta = cliente.post(ROTA, json=corpo)
    assert resposta.status_code == 422
    assert setor_invalido() in resposta.text or "detail" in resposta.json()
    assert "abcdefg" not in resposta.text


def setor_invalido() -> str:
    return analista.SETOR_INVALIDO


def test_o_setor_pedido_nao_vai_para_o_log(cliente, caplog):
    with caplog.at_level(logging.INFO):
        _pedir(cliente, uf="SP")
    registros = " ".join(r.getMessage() for r in caplog.records)
    assert SETOR not in registros
    assert "setor do analista: pronta" in registros


def test_sem_login_e_401(pasta):  # noqa: F811
    from fastapi.testclient import TestClient

    from src.api import criar_app

    resposta = TestClient(criar_app()).post(ROTA, json={"cnae": SETOR})
    assert resposta.status_code in (401, 403)


def test_a_conta_gratuita_sem_o_recurso_da_ficha_e_barrada(cliente, banco):
    _mudar_plano(banco, "gratuito")
    resposta = _pedir(cliente)
    assert resposta.status_code == 403


def test_a_base_fora_do_ar_e_503_sem_dizer_onde(cliente, monkeypatch):
    def sem_base(_banco):
        raise OSError("/caminho/secreto")

    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", sem_base)
    resposta = _pedir(cliente)
    assert resposta.status_code == 503
    assert "secreto" not in resposta.text


def test_a_camada_da_tela_sem_a_porta_recusa_o_cnae_curto():
    with pytest.raises(setor.PedidoInvalido):
        setor.compradores(None, "12", None, None, hoje=HOJE)  # type: ignore[arg-type]


def test_porta_de_mentira_funciona_direto(pasta, banco):  # noqa: F811
    with banco.connect() as conexao, Porta(pasta, conexao) as porta:
        resposta = setor.compradores(
            porta,
            SETOR,
            None,
            None,
            hoje=HOJE,
            regras=base_de_mentira._regras(*base_de_mentira.TABELAS),
        )
    assert resposta.estado == leitura.PRONTA
    assert resposta.linhas == 3
