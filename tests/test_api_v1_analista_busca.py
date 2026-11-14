"""A busca de empresas da tela do analista (linha 798, PR 3): `POST /v1/analista/empresas` e a planilha.

A regra tem os testes dela em `test_analista_busca.py`; aqui fica o que é da rota: login, termos e plano (a
página `encontrar_empresas`, o mesmo recurso da ficha), a base fora do ar (503), os estados da tela, os
filtros inválidos (422) e a planilha. A porta e as regras do portão são as da API externa: os testes trocam
as mesmas funções que os testes de lá. Nenhuma consulta é por conta (a base é a mesma para todos), então não
há teste de duas contas da leitura. O que muda de uma conta para outra é o plano e, enquanto as tabelas só
têm a prontidão de piloto, a marca de piloto da organização da conta (seção "piloto", com duas organizações).
"""

import io
import logging
from datetime import timedelta

import openpyxl
import pytest
from fastapi.testclient import TestClient

from base.porta import Porta
from base.prontidao import AVISO_DE_PILOTO
from src import paginas
from src.analista import busca
from src.api_externa import rotas as rotas_da_api_externa
from src.api_v1 import analista
from src.banco import chaves_da_api as cb
from src.banco import membros_da_organizacao as mb
from src.banco.usuarios import entrar, mudar_plano
from src.conformidade import registrar_aceite
from tests import test_analista_busca as busca_de_mentira
from tests import test_api_v1_rotas as rotas
from tests.ajudantes_da_api import da_sessao

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


def test_capital_estabelecimentos_e_ordem_pela_rota(cliente):
    pedido = {"ufs": ["SP", "MG"], "capital_minimo": 50_000, "ordem": "menor_capital"}
    dados = cliente.post(ROTA, json=pedido).json()
    assert [e["cnpj"] for e in dados["empresas"]] == ["22222222000191", ALFA]
    assert dados["empresas"][1]["capital_social"]["valor"] == 6_000_000.0
    assert dados["empresas"][1]["n_estabelecimentos"]["valor"] == 1
    assert dados["ordens"] == busca.ordens_como_lista()
    pedido = {"ufs": ["SP", "MG"], "estabelecimentos_minimo": 2}
    assert cliente.post(ROTA, json=pedido).json()["empresas"] == []


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
        {"capital_minimo": -1},
        {"capital_minimo": 2, "capital_maximo": 1},
        {"estabelecimentos_minimo": 0},
        {"ufs": ["SP"], "ordem": "faturamento"},
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


# ---------------------------------------------------------------- piloto (D11)
# Em produção nenhuma tabela da busca tem a prontidão cheia: quem busca é a conta da organização com a marca
# de piloto, conferida no servidor a cada pedido, e a resposta leva o aviso. Riscos: a marca de uma
# organização valer para a conta de outra (ou de nenhuma); o dado de piloto sair sem o aviso.


@pytest.fixture
def so_de_piloto(monkeypatch):
    monkeypatch.setattr(
        rotas_da_api_externa, "regras_da_api", busca_de_mentira._so_de_piloto
    )


def _organizacao_com(banco, nome, conta_id, *, marca=True, desde=None, ate=None):
    """Uma organização com a conta de membro e, se `marca`, a marca de piloto vigente desde ontem."""
    ontem = busca_de_mentira.HOJE - timedelta(days=1)
    with banco.begin() as conexao:
        admin = entrar(conexao, "g-admin-piloto", "admin-piloto@exemplo.com")[0]
        organizacao = cb.criar_organizacao(conexao, nome=nome, ator_id=admin.id)
        mb.vincular_membro(
            conexao,
            organizacao_id=organizacao.id,
            usuario_id=conta_id,
            ator_id=admin.id,
        )
        if marca:
            cb.conceder_direito(
                conexao,
                organizacao_id=organizacao.id,
                conjunto=cb.CONJUNTO_DO_PILOTO,
                finalidade=mb.FINALIDADE_DA_TELA,
                vigente_desde=desde or ontem,
                vigente_ate=ate,
                ator_id=admin.id,
            )
    return organizacao, admin


@pytest.fixture
def da_bia(cliente, banco):
    """Outra conta logada no Pro, com os termos aceitos (a Bia)."""
    with banco.begin() as conexao:
        bia = entrar(conexao, "g-bia-piloto", "bia-piloto@exemplo.com")[0]
        registrar_aceite(conexao, bia.id)
        mudar_plano(conexao, bia.id, "pro")
    return bia, TestClient(cliente.app, headers=da_sessao(banco, bia))


def _da_ana(banco):
    return rotas._id_da_ana_no(banco)


@pytest.mark.usefixtures("so_de_piloto")
def test_membro_da_organizacao_do_piloto_busca_e_a_resposta_leva_o_aviso(
    cliente, banco
):
    _organizacao_com(banco, "Casa Exemplo", _da_ana(banco))
    resposta = cliente.post(ROTA, json={"setores": ["J"]})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["estado"] == "pronta"
    assert [e["cnpj"] for e in dados["empresas"]] == [ALFA]
    assert dados["aviso_de_piloto"] == AVISO_DE_PILOTO


@pytest.mark.usefixtures("so_de_piloto")
def test_conta_sem_organizacao_ou_de_organizacao_sem_a_marca_continua_sem_a_busca(
    cliente, banco
):
    sem_organizacao = cliente.post(ROTA, json={"setores": ["J"]}).json()
    assert sem_organizacao["estado"] == "nao_liberada"
    assert sem_organizacao["empresas"] == []
    assert sem_organizacao["aviso_de_piloto"] is None
    _organizacao_com(banco, "Casa sem marca", _da_ana(banco), marca=False)
    sem_marca = cliente.post(ROTA, json={"setores": ["J"]}).json()
    assert sem_marca["estado"] == "nao_liberada"
    assert cliente.post(PLANILHA, json={"setores": ["J"]}).status_code == 404


@pytest.mark.usefixtures("so_de_piloto")
def test_a_marca_de_uma_organizacao_nao_abre_a_busca_para_a_conta_de_outra(
    cliente, banco, da_bia
):
    bia, cliente_da_bia = da_bia
    _organizacao_com(banco, "Casa Exemplo", _da_ana(banco))
    _organizacao_com(banco, "Outra Casa", bia.id, marca=False)
    assert cliente.post(ROTA, json={"ufs": ["SP"]}).json()["estado"] == "pronta"
    da_outra = cliente_da_bia.post(ROTA, json={"ufs": ["SP"]}).json()
    assert da_outra["estado"] == "nao_liberada" and da_outra["empresas"] == []
    assert cliente_da_bia.post(PLANILHA, json={"ufs": ["SP"]}).status_code == 404


@pytest.mark.usefixtures("so_de_piloto")
@pytest.mark.parametrize(
    "vigencia",
    [
        {"desde": busca_de_mentira.HOJE + timedelta(days=1)},  # ainda não vale
        {"ate": busca_de_mentira.HOJE - timedelta(days=1)},  # já venceu
    ],
)
def test_marca_fora_da_vigencia_nao_abre_a_busca(cliente, banco, vigencia):
    desde = busca_de_mentira.HOJE - timedelta(days=30)
    _organizacao_com(
        banco, "Casa Exemplo", _da_ana(banco), **({"desde": desde} | vigencia)
    )
    assert cliente.post(ROTA, json={"ufs": ["SP"]}).json()["estado"] == "nao_liberada"


@pytest.mark.usefixtures("so_de_piloto")
def test_organizacao_suspensa_perde_a_busca_do_piloto(cliente, banco):
    organizacao, admin = _organizacao_com(banco, "Casa Exemplo", _da_ana(banco))
    assert cliente.post(ROTA, json={"ufs": ["SP"]}).json()["estado"] == "pronta"
    with banco.begin() as conexao:
        cb.suspender_organizacao(
            conexao, organizacao_id=organizacao.id, motivo="contrato", ator_id=admin.id
        )
    assert cliente.post(ROTA, json={"ufs": ["SP"]}).json()["estado"] == "nao_liberada"


def test_sem_filtro_nao_confere_o_piloto_nem_abre_a_base(cliente, monkeypatch):
    monkeypatch.setattr(rotas_da_api_externa, "abrir_porta", _nao_abre)
    monkeypatch.setattr(mb, "e_do_piloto", _nao_abre)
    assert cliente.post(ROTA, json={}).json()["estado"] == busca.SEM_FILTRO


@pytest.mark.usefixtures("so_de_piloto")
def test_planilha_do_piloto_leva_o_aviso_em_cada_linha_e_nas_fontes(cliente, banco):
    _organizacao_com(banco, "Casa Exemplo", _da_ana(banco))
    resposta = cliente.post(PLANILHA, json={"ufs": ["SP", "MG"]})
    assert resposta.status_code == 200, resposta.text
    pasta = openpyxl.load_workbook(io.BytesIO(resposta.content))
    linhas = list(pasta["empresas"].values)
    cabecalho = linhas[0]
    assert len(linhas) == 3
    assert all(
        linha[cabecalho.index("piloto")] == AVISO_DE_PILOTO for linha in linhas[1:]
    )
    assert ("aviso de piloto", AVISO_DE_PILOTO, None) in list(pasta["fontes"].values)


def test_prontidao_cheia_sai_sem_aviso_de_piloto(cliente, banco):
    _organizacao_com(banco, "Casa Exemplo", _da_ana(banco))
    dados = cliente.post(ROTA, json={"setores": ["J"]}).json()
    assert dados["estado"] == "pronta" and dados["aviso_de_piloto"] is None
    resposta = cliente.post(PLANILHA, json={"ufs": ["SP", "MG"]})
    pasta = openpyxl.load_workbook(io.BytesIO(resposta.content))
    assert "piloto" not in next(pasta["empresas"].values)
    assert all(linha[0] != "aviso de piloto" for linha in pasta["fontes"].values)
