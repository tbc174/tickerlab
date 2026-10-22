"""As rotas `GET /v1/setores` e `GET /v1/relatorio-setor` (molde D, PR 3, tarefa 3.5): login, plano,
setor fora da lista e o formato da resposta."""

import pytest

from src.banco.usuarios import mudar_plano
from tests import test_api_v1_rotas as rotas
from tests.test_relatorio_setor import gravar_noite

chave = rotas.chave  # as fixtures da conta logada, as mesmas dos outros testes da API
cliente = rotas.cliente
ROTA = "/api/v1/relatorio-setor"


@pytest.fixture
def com_a_noite(banco, tmp_path, monkeypatch):
    from tests.test_fundamentos_no_app import _coletar

    _coletar(banco)
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(tmp_path))
    return gravar_noite(tmp_path)


def _como_pro(banco) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "pro")


def test_api_setores(cliente, com_a_noite) -> None:
    resposta = cliente.get("/api/v1/setores")
    assert resposta.status_code == 200, resposta.text
    setores = resposta.json()["setores"]
    assert [s["chave"] for s in setores] == [
        "eletricas",
        "bancos",
        "seguros",
        "saude_suplementar",
        "telecom",
    ]
    por_chave = {s["chave"]: s for s in setores}
    assert por_chave["eletricas"]["como_era_em"] == "2026-10-17"
    assert por_chave["bancos"] == {
        "chave": "bancos",
        "nome": "Bancos",
        "empresas": 1,  # o Itaú do FCA de exemplo
        "como_era_em": None,
    }


def test_api_relatorio_setor(cliente, banco, com_a_noite) -> None:
    _como_pro(banco)
    resposta = cliente.get(ROTA, params={"setor": "eletricas"})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["setor"] == "eletricas" and dados["como_era_em"] == "2026-10-17"
    assert [s["chave"] for s in dados["secoes"]] == [
        "membros",
        "tamanho",
        "concentracao",
        "participacao",
        "lado_a_lado",
        "cruzamentos",
        "o_que_os_dados_mostram",
        "nao_temos",
        "metodologia",
    ]
    assert all(not s["trancada"] for s in dados["secoes"])
    assert dados["frases"] and all(f["ids"] for f in dados["frases"])
    assert dados["nao_temos"] and dados["limites"] and dados["fontes"]
    concentracao = next(s for s in dados["secoes"] if s["chave"] == "concentracao")
    tabela = concentracao["tabelas"][0]
    assert (
        tabela["titulo"].startswith("Concentração")
        and "HHI (pontos)" in tabela["colunas"]
    )


def test_api_do_gratuito_vem_trancada(cliente, com_a_noite) -> None:
    resposta = cliente.get(ROTA, params={"setor": "eletricas"})
    assert resposta.status_code == 200
    dados = resposta.json()
    abertas = {s["chave"] for s in dados["secoes"] if not s["trancada"]}
    assert abertas == {"membros", "nao_temos", "metodologia"}
    assert dados["frases"] == []
    # nenhum número da base sem o plano (a metodologia, aberta, explica o HHI sem número)
    assert "4.626" not in resposta.text and "HHI (pontos)" not in resposta.text


@pytest.mark.parametrize("setor", ["aviacao", "inventado", "../eletricas"])
def test_api_setor_desconhecido_404(cliente, com_a_noite, setor) -> None:
    resposta = cliente.get(ROTA, params={"setor": setor})
    assert resposta.status_code == 404
    assert setor not in resposta.text


def test_api_setor_comprido_demais_422(cliente) -> None:
    assert cliente.get(ROTA, params={"setor": "x" * 400}).status_code == 422


def test_api_sem_setor_422(cliente) -> None:
    assert cliente.get(ROTA).status_code == 422


@pytest.mark.parametrize("rota", [ROTA + "?setor=eletricas", "/api/v1/setores"])
def test_api_sem_login_401(cliente, rota) -> None:
    cliente.headers.pop("Cookie")  # sem a sessão, só o cabeçalho do app
    assert cliente.get(rota).status_code == 401
