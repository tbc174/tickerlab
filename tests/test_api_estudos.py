"""Rotas públicas do pregão do dia (plano `2026-10-28-raio-x-todo-dia`, PR 5).

Servem o texto do pregão pelo molde aprovado, no mesmo formato que a página do site já lê; sem
conta e só leitura da pasta que o servidor de casa manda. A data do pedido nunca vira caminho.
"""

import json
import shutil

import pytest

from src import texto_do_pregao as tp
from src.api_v1 import VARIAVEL_DA_CHAVE, estudos
from tests.ajudantes_da_api import cliente_do_gateway

ROTA = "/api/v1/estudos/pregao"
EXEMPLO = tp.PASTA_DOS_PREGOES / "2026-10-27.json"


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    """A pasta recebida com dois pregões: 26/10 (cópia do exemplo com outra data) e 27/10."""
    recebidos = tmp_path / "pregao"
    recebidos.mkdir()
    shutil.copyfile(EXEMPLO, recebidos / "2026-10-27.json")
    resumo = json.loads(EXEMPLO.read_text(encoding="utf-8"))
    resumo["pregao"] = "2026-10-26"
    (recebidos / "2026-10-26.json").write_text(json.dumps(resumo), encoding="utf-8")
    monkeypatch.setenv(estudos.VARIAVEL_DA_PASTA, str(recebidos))
    return recebidos


@pytest.fixture
def cliente(pasta, monkeypatch):
    del pasta  # a pasta do pregão já está no ambiente
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    estudos.limpar_cache()
    yield cliente_do_gateway({VARIAVEL_DA_CHAVE: "1"})
    estudos.limpar_cache()


def test_api_pregao_ultimo(cliente, pasta):
    r = cliente.get(f"{ROTA}/ultimo")
    assert r.status_code == 200
    assert r.json() == tp.para_o_site(pasta)
    assert r.json()["pregao"]["pregao"] == "2026-10-27"
    assert r.json()["molde_aprovado"] == tp.IMPRESSAO_DO_MOLDE_APROVADO


def test_api_pregao_por_data(cliente):
    r = cliente.get(f"{ROTA}/2026-10-26")
    assert r.status_code == 200
    assert r.json()["pregao"]["pregao"] == "2026-10-26"


def test_resposta_tem_so_o_texto_sem_a_origem(cliente):
    """O resumo guarda caminhos e SHA do acervo (`origem`): nada disso sai na API."""
    texto = cliente.get(f"{ROTA}/ultimo").text
    assert "origem" not in texto
    assert "sha256" not in texto
    assert "bruto/" not in texto


@pytest.mark.parametrize(
    "data",
    ["2026-13-01", "27-10-2026", "2026-10-31", "2026-10-27.json", "20261027", "hoje"],
)
def test_api_pregao_data_invalida_404(cliente, data):
    assert cliente.get(f"{ROTA}/{data}").status_code == 404


@pytest.mark.parametrize(
    "data", ["..%2Fsegredo", "%2e%2e%2fsegredo", "..%5Csegredo", "2026-10-27%00"]
)
def test_api_pregao_sem_caminho_relativo(cliente, pasta, data):
    (pasta.parent / "segredo.json").write_text('{"senha": "x"}', encoding="utf-8")
    r = cliente.get(f"{ROTA}/{data}")
    assert r.status_code == 404
    assert "senha" not in r.text


def test_api_pregao_recusa_molde_nao_aprovado(cliente, monkeypatch):
    """Molde trocado sem o "pode" (impressão digital diferente da aprovada) não sai."""
    monkeypatch.setattr(tp, "IMPRESSAO_DO_MOLDE_APROVADO", "outra")
    r = cliente.get(f"{ROTA}/ultimo")
    assert r.status_code == 503
    assert "outra" not in r.text


def test_pasta_vazia_da_404(cliente, pasta):
    for arquivo in pasta.iterdir():
        arquivo.unlink()
    assert cliente.get(f"{ROTA}/ultimo").status_code == 404


def test_resumo_estragado_da_503_sem_detalhe_interno(cliente, pasta):
    (pasta / "2026-10-28.json").write_text('{"pregao": "2026-10-28"', encoding="utf-8")
    r = cliente.get(f"{ROTA}/ultimo")
    assert r.status_code == 503
    assert str(pasta) not in r.text
    assert "Traceback" not in r.text


def test_pregao_corrigido_pela_b3_sai_novo(cliente, pasta):
    """O servidor refaz o arquivo quando a B3 corrige o dia: a API não pode servir o velho."""
    assert cliente.get(f"{ROTA}/2026-10-26").status_code == 200
    resumo = json.loads((pasta / "2026-10-26.json").read_text(encoding="utf-8"))
    resumo["ibovespa"]["pontos"] = 123456.0
    novo = pasta / "2026-10-26.json"
    novo.write_text(json.dumps(resumo), encoding="utf-8")
    texto = cliente.get(f"{ROTA}/2026-10-26").text
    assert "123.456" in texto


def test_cors_so_para_o_site(cliente):
    do_site = cliente.get(f"{ROTA}/ultimo", headers={"Origin": estudos.ORIGEM_DO_SITE})
    assert do_site.headers["access-control-allow-origin"] == estudos.ORIGEM_DO_SITE
    de_fora = cliente.get(f"{ROTA}/ultimo", headers={"Origin": "https://fora.example"})
    assert "access-control-allow-origin" not in de_fora.headers


def test_limite_por_ip(cliente):
    for _ in range(estudos.PEDIDOS_POR_MINUTO):
        assert cliente.get(f"{ROTA}/ultimo").status_code == 200
    assert cliente.get(f"{ROTA}/ultimo").status_code == 429
    outro_ip = {"CF-Connecting-IP": "192.0.2.5"}
    assert cliente.get(f"{ROTA}/ultimo", headers=outro_ip).status_code == 200


@pytest.mark.usefixtures("pasta")
def test_sem_a_api_ligada_nao_responde():
    estudos.limpar_cache()
    desligada = cliente_do_gateway({})
    assert desligada.get(f"{ROTA}/ultimo").status_code == 404
