"""A ficha da empresa em Markdown pela API do app (`GET /v1/relatorio-empresa/markdown`, linha 653).

Mesmo acesso e mesmo plano da rota JSON: o texto sai do mesmo `relatorio_em_markdown` que o botão da
página usa, sem montar nada à parte. O campo malicioso em fonte e rótulo já é coberto em
`test_relatorio_empresa_markdown.py`; aqui vale a rota: portão (login e plano), isolamento entre contas,
cabeçalhos do arquivo e os erros.
"""

from fastapi.testclient import TestClient

from src.banco.usuarios import entrar, mudar_plano
from src.relatorio_empresa import SECOES
from tests.ajudantes_da_api import da_sessao
from tests.test_api_v1_rotas import (  # noqa: F401
    _com_a_petrobras_coletada,
    _id_da_ana_no,
    chave,
    cliente,
)

ROTA = "/api/v1/relatorio-empresa/markdown"
LIMITES = SECOES["limites"]
AUDITOR = "PRICEWATERHOUSECOOPERS"  # só a seção de base, só para o Pro


def _como_pro(banco) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, _id_da_ana_no(banco), "pro")


def test_ficha_em_markdown_do_pro_traz_secoes_numeros_e_limites(
    cliente,  # noqa: F811
    banco,
    tmp_path,
    monkeypatch,
) -> None:
    _com_a_petrobras_coletada(banco, tmp_path, monkeypatch)
    _como_pro(banco)
    resposta = cliente.get(ROTA, params={"ticker": "petr4"})
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"].startswith("text/markdown")
    assert resposta.headers["cache-control"] == "no-store"
    assert "tickerlab-empresa-PETR4.md" in resposta.headers["content-disposition"]
    texto = resposta.text
    assert texto.startswith("# Ficha da empresa")
    assert "495,2 mi" in texto.replace("\\", "")
    assert f"## {LIMITES}" in texto
    assert "33.000.167/0001-01" in texto


def test_ficha_em_markdown_do_gratuito_vem_trancada_sem_numeros(
    cliente,  # noqa: F811
    banco,
    tmp_path,
    monkeypatch,
) -> None:
    _com_a_petrobras_coletada(banco, tmp_path, monkeypatch)
    resposta = cliente.get(ROTA, params={"ticker": "PETR4.SA"})
    assert resposta.status_code == 200, resposta.text
    assert (
        "495,2 mi" not in resposta.text.replace("\\", "")
        and AUDITOR not in resposta.text
    )
    assert f"## {LIMITES}" in resposta.text


def test_plano_de_uma_conta_nao_abre_a_ficha_de_outra(
    cliente,  # noqa: F811
    banco,
    tmp_path,
    monkeypatch,
) -> None:
    """Duas contas, dois cookies: a Pro vê os números; a Gratuita, no mesmo pedido, não."""
    _com_a_petrobras_coletada(banco, tmp_path, monkeypatch)
    _como_pro(banco)
    with banco.begin() as conexao:
        bia = entrar(conexao, "bia", "bia@exemplo.com")[0]
        from src.conformidade import registrar_aceite

        registrar_aceite(conexao, bia.id)
    da_bia = TestClient(cliente.app, headers=da_sessao(banco, bia))
    pedido = {"ticker": "PETR4.SA"}
    assert "495,2 mi" in cliente.get(ROTA, params=pedido).text.replace("\\", "")
    assert "495,2 mi" not in da_bia.get(ROTA, params=pedido).text
    # o pedido da Bia não mexeu na sessão da Ana
    assert "495,2 mi" in cliente.get(ROTA, params=pedido).text.replace("\\", "")


def test_ficha_em_markdown_sem_login_da_401(cliente) -> None:  # noqa: F811
    sem_login = TestClient(cliente.app)
    assert sem_login.get(ROTA, params={"ticker": "PETR4.SA"}).status_code == 401


def test_ficha_em_markdown_de_ticker_sem_empresa_da_404(cliente) -> None:  # noqa: F811
    resposta = cliente.get(ROTA, params={"ticker": "ZZZZ9.SA"})
    assert resposta.status_code == 404


def test_ficha_em_markdown_exige_ticker_valido(cliente) -> None:  # noqa: F811
    assert cliente.get(ROTA).status_code == 422
    assert cliente.get(ROTA, params={"ticker": "../etc/passwd"}).status_code == 422


def test_ticker_com_quebra_de_linha_nao_vira_nome_de_arquivo(cliente) -> None:  # noqa: F811
    """O nome do arquivo vem do ticker já validado: cabeçalho nunca leva texto do pedido."""
    resposta = cliente.get(ROTA, params={"ticker": "PETR4\r\nX-Preso: 1"})
    assert resposta.status_code == 422
    assert "x-preso" not in resposta.headers
