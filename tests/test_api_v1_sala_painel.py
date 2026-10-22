"""A rota que alimenta a tela da sala (src/api_v1/sala_painel.py, B-20 PR 5).

Mesmo ambiente de `test_api_v1_sala_trabalho.py`. O que estes testes travam: toda conta logada entra (401
sem login) e só na própria sala; outra conta não vê a sala alheia nem com o id certo; os
textos e rótulos vêm da API e cobrem todos os estados do banco; a contradição já chega descrita; o
aviso de prazo aparece nos últimos 14 dias; e toda rota da sala está no mapa de páginas.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from src import api
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso
from src.api_v1 import sala as rotas_da_sala
from src.api_v1 import sala_painel as rotas_do_painel
from src.api_v1 import sala_trabalho as rotas_do_trabalho
from src.banco import modelo
from src.banco.usuarios import entrar, mudar_papel
from src.conformidade import registrar_aceite
from src.sala import cofre, guarda, retencao, textos
from tests import ajudantes_da_sala as gerar
from tests.ajudantes_da_api import AGORA, da_sessao

OPERACAO = {"tipo": "ma", "nome": "Aquisição da Alfa", "prazo_em_dias": 180}


@pytest.fixture(autouse=True)
def ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, cofre.gerar_chave_mestra())
    monkeypatch.setenv(guarda.VARIAVEL_DA_PASTA, str(tmp_path / "dados_sala"))
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    acesso.LIMITE.zerar()
    rotas_da_sala.LIMITE_DE_ENVIOS.zerar()


@pytest.fixture
def app():
    return api.criar_app({VARIAVEL_DA_CHAVE: "1"})


def _conta(banco, app, sub, admin=True):
    with banco.begin() as conexao:
        usuario = entrar(conexao, sub, f"{sub}@exemplo.com", sub.title())[0]
        registrar_aceite(conexao, usuario.id)
        if admin:
            mudar_papel(conexao, usuario.id, "admin")
    return TestClient(app, headers=da_sessao(banco, usuario))


@pytest.fixture
def ana(banco, app):
    return _conta(banco, app, "ana")


@pytest.fixture
def bia(banco, app):
    return _conta(banco, app, "bia")


@pytest.fixture
def carla(banco, app):
    """Uma conta que não é admin."""
    return _conta(banco, app, "carla", admin=False)


def _criar(cliente, **mudancas):
    resposta = cliente.post("/v1/operacoes", json={**OPERACAO, **mudancas})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def _documento(cliente, operacao_id, nome, texto):
    resposta = cliente.post(
        f"/v1/operacoes/{operacao_id}/documentos",
        files={"arquivo": (nome, gerar.pdf(texto), "application/pdf")},
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def _evidencia(cliente, operacao_id, documento_id, valor):
    resposta = cliente.post(
        f"/v1/operacoes/{operacao_id}/evidencias",
        json={
            "documento_id": documento_id,
            "metrica": "receita_liquida",
            "periodo": "2025",
            "valor_numero": valor,
            "unidade": "milhares",
            "moeda": "BRL",
            "pagina": 1,
            "trecho": f"Receita liquida {valor}",
        },
    )
    assert resposta.status_code == 201, resposta.text


def _sala_com_contradicao(cliente):
    operacao = _criar(cliente)
    primeiro = _documento(cliente, operacao, "dfs.pdf", "Receita liquida 1000")
    segundo = _documento(cliente, operacao, "apresentacao.pdf", "Receita liquida 1200")
    _evidencia(cliente, operacao, primeiro, "1000")
    _evidencia(cliente, operacao, segundo, "1200")
    return operacao


# --- quem entra ---------------------------------------------------------------------------


def test_toda_rota_do_painel_exige_conta_logada():
    rotas = rotas_do_painel.router.routes
    assert len(rotas) == 2
    for rota in rotas:
        dependencias = {d.call for d in rota.dependant.dependencies}  # type: ignore[attr-defined]
        assert rotas_da_sala.conta_logada in dependencias, rota.path  # type: ignore[attr-defined]


def test_quem_nao_e_admin_ve_so_o_painel_da_propria_sala(carla, ana):
    operacao_da_ana = _criar(ana)
    propria = _criar(carla)
    assert carla.get("/v1/sala").status_code == 200
    assert [o["id"] for o in carla.get("/v1/sala").json()["operacoes"]] == [propria]
    assert carla.get(f"/v1/operacoes/{propria}/painel").status_code == 200
    assert carla.get(f"/v1/operacoes/{operacao_da_ana}/painel").status_code == 404


def test_sem_login_a_sala_responde_401(app):
    anonimo = TestClient(app)
    assert anonimo.get("/v1/sala").status_code == 401


def test_outra_conta_nao_ve_a_sala_alheia(ana, bia):
    operacao = _sala_com_contradicao(ana)
    assert bia.get(f"/v1/operacoes/{operacao}/painel").status_code == 404
    assert bia.get("/v1/sala").json()["operacoes"] == []


# --- o que a página mostra ----------------------------------------------------------------


def test_a_sala_vazia_traz_os_textos_e_as_opcoes(ana):
    dados = ana.get("/v1/sala").json()
    assert dados["operacoes"] == []
    assert set(dados["conceitos"]) == set(textos.CONCEITOS)
    assert {t["valor"] for t in dados["tipos"]} == set(modelo.TIPOS_DE_OPERACAO)
    assert dados["prazos_em_dias"] == [90, 180, 365]
    assert dados["prazo_padrao_em_dias"] == 180


def test_cada_estado_do_banco_tem_rotulo():
    assert set(textos.TIPOS_DE_OPERACAO) == set(modelo.TIPOS_DE_OPERACAO)
    assert set(textos.ESTADOS_DA_CONTRADICAO) == set(modelo.ESTADOS_DA_CONTRADICAO)
    assert set(textos.ESTADOS_DO_ITEM) == set(modelo.ESTADOS_DO_CHECKLIST)
    assert set(textos.ESTADOS_DO_DOCUMENTO) == set(modelo.SITUACOES_DO_DOCUMENTO)


def test_a_lista_traz_documentos_contradicoes_abertas_e_dias(ana):
    _sala_com_contradicao(ana)
    (operacao,) = ana.get("/v1/sala").json()["operacoes"]
    assert operacao["documentos"] == 2
    assert operacao["contradicoes_abertas"] == 1
    assert operacao["dias_ate_sumir"] == 180
    assert operacao["aviso_de_prazo"] is None


def test_o_painel_descreve_a_contradicao_sem_a_tela_cruzar_ids(ana):
    operacao = _sala_com_contradicao(ana)
    painel = ana.get(f"/v1/operacoes/{operacao}/painel").json()
    (contradicao,) = painel["contradicoes"]
    assert contradicao["metrica"] == "receita_liquida"
    assert {contradicao["documento_a"], contradicao["documento_b"]} == {
        "dfs.pdf",
        "apresentacao.pdf",
    }
    assert {contradicao["valor_a"], contradicao["valor_b"]} == {
        "1000.000000 milhares BRL",
        "1200.000000 milhares BRL",
    }
    assert contradicao["rotulo_do_estado"] == "Aberta"
    assert painel["tipo_rotulo"] == textos.TIPOS_DE_OPERACAO["ma"]
    assert [d["rotulo_da_situacao"] for d in painel["documentos"]]
    assert {e["documento"] for e in painel["evidencias"]} == {
        "dfs.pdf",
        "apresentacao.pdf",
    }


def test_o_painel_traz_o_checklist_com_rotulos_e_o_que_falta_revisar(ana):
    operacao = _criar(ana)
    painel = ana.get(f"/v1/operacoes/{operacao}/painel").json()
    assert painel["checklist"]
    assert painel["itens_a_revisar"] == len(painel["checklist"])
    assert {e["valor"] for e in painel["estados_do_checklist"]} == set(
        modelo.ESTADOS_DO_CHECKLIST
    )
    codigo = painel["checklist"][0]["codigo"]
    resposta = ana.patch(
        f"/v1/operacoes/{operacao}/checklist/{codigo}", json={"estado": "revisado"}
    )
    assert resposta.status_code == 200
    depois = ana.get(f"/v1/operacoes/{operacao}/painel").json()
    assert depois["itens_a_revisar"] == len(depois["checklist"]) - 1
    assert depois["checklist"][0]["rotulo_do_estado"] == "Revisado por você"


# --- o aviso de prazo ---------------------------------------------------------------------


def test_aviso_so_nos_ultimos_14_dias():
    hoje = date(2026, 10, 21)
    assert textos.aviso_de_prazo("aberta", date(2026, 11, 5), hoje) is None  # 15 dias
    assert "em 14 dias" in textos.aviso_de_prazo("aberta", date(2026, 11, 4), hoje)  # type: ignore[operator]
    assert "amanhã" in textos.aviso_de_prazo("aberta", date(2026, 10, 22), hoje)  # type: ignore[operator]
    assert "hoje" in textos.aviso_de_prazo("aberta", hoje, hoje)  # type: ignore[operator]
    assert "encerrada" in textos.aviso_de_prazo("encerrada", date(2026, 10, 25), hoje)  # type: ignore[operator]


def test_dias_ate_sumir_nunca_fica_negativo():
    assert retencao.dias_ate_sumir(date(2026, 10, 1), date(2026, 10, 21)) == 0


def test_operacao_encerrada_leva_o_aviso_na_lista(ana):
    operacao = _criar(ana)
    ana.post(f"/v1/operacoes/{operacao}/encerrar")
    (item,) = ana.get("/v1/sala").json()["operacoes"]
    assert item["dias_ate_sumir"] == retencao.DIAS_PARA_BAIXAR_DEPOIS_DE_ENCERRAR
    assert item["aviso_de_prazo"] is None  # 30 dias: ainda longe do aviso


# --- toda rota da sala está no mapa -------------------------------------------------------


def test_toda_rota_da_sala_pertence_a_pagina_da_sala():
    """Rota nova da sala sem entrar no contrato da página (`src/paginas.py`) falha aqui."""
    from src.paginas import ROTAS_DA_SALA, pagina

    pagina_da_sala = pagina("sala_de_dados")
    assert pagina_da_sala.so_no_app_novo and not pagina_da_sala.somente_admin
    rotas = {
        (metodo, r.path)
        for roteador in (rotas_da_sala, rotas_do_trabalho, rotas_do_painel)
        for r in roteador.router.routes
        for metodo in r.methods  # type: ignore[attr-defined]
    }
    assert rotas == ROTAS_DA_SALA
