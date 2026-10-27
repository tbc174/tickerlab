"""Busca pública: só três destaques, nenhuma conta, pessoa ou dado de preço."""

import json
import shutil
from dataclasses import asdict
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from base import vitrine
from src import dossie
from src.api_v1 import VARIAVEL_DA_CHAVE
from src.banco.modelo import setores_cvm, tickers_dos_emissores
from tests.ajudantes_da_api import cliente_do_gateway

CNPJ = "02429144000193"
ROTA = "/api/v1/base/destaques"


@pytest.fixture
def ficha():
    return dossie.ler_ficha(dossie.FICHA_DE_EXEMPLO)


def test_destaques_publicos_sao_so_tres_agregados_com_fonte_e_data(ficha):
    destaques = vitrine.destaques_publicos(ficha)
    assert [d.chave for d in destaques] == ["fundos", "ofertas", "setor"]
    assert all(d.texto and d.fonte and d.data for d in destaques)


def test_pessoa_e_texto_livre_nao_saem_na_resposta(ficha):
    for secao in ficha.secoes:
        secao.paragrafos.append("Pessoa Privada 529.982.247-25")
        secao.fontes = ["Pessoa Privada 529.982.247-25"]
        for linhas in secao.tabelas.values():
            for linha in linhas:
                linha["nome_pessoa"] = "Pessoa Privada"
    texto = json.dumps([asdict(d) for d in vitrine.destaques_publicos(ficha)])
    assert "Pessoa Privada" not in texto
    assert "529.982" not in texto
    assert "yahoo" not in texto.lower()
    assert len(vitrine.destaques_publicos(ficha)) == 3


def test_destaques_respeitam_o_portao_da_fonte(ficha, monkeypatch):
    monkeypatch.setattr("base.dossie.pode_mostrar", lambda _: False)
    assert vitrine.destaques_publicos(ficha) == []


@pytest.fixture
def cliente(banco, tmp_path, monkeypatch):
    from src.api_v1 import base_publica

    base_publica.limpar_cache()
    atual = tmp_path / "dossies" / "atual"
    atual.mkdir(parents=True)
    shutil.copyfile(dossie.FICHA_DE_EXEMPLO, atual / f"{CNPJ}.json")
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(atual.parent))
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    with banco.begin() as c:
        c.execute(
            sa.insert(setores_cvm).values(cnpj=CNPJ, setor="Energia", situacao="ATIVO")
        )
        c.execute(
            sa.insert(tickers_dos_emissores).values(
                ticker="CPFE3.SA",
                codigo="CPFE3",
                cnpj=CNPJ,
                empresa="CPFL ENERGIA S.A.",
                atualizado_em=datetime.now(UTC),
            )
        )
    yield cliente_do_gateway({VARIAVEL_DA_CHAVE: "1"})
    base_publica.limpar_cache()


@pytest.mark.parametrize("q", [CNPJ, "02.429.144/0001-93", "CPFE3", "cpfl"])
def test_busca_sem_login_por_cnpj_nome_ou_ticker(cliente, q):
    r = cliente.get(
        ROTA, params={"q": q}, headers={"Origin": "https://tickerlab.com.br"}
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["cnpj"] == CNPJ
    assert len(corpo["destaques"]) == 3
    assert corpo["medido_em"] and corpo["fonte"]
    assert not {"secoes", "tabelas", "preco", "usuario_id"} & corpo.keys()
    assert r.headers["cache-control"] == "public, max-age=86400"
    assert r.headers["access-control-allow-origin"] == "https://tickerlab.com.br"
    assert "set-cookie" not in r.headers


@pytest.mark.parametrize(
    "q", ["52998224725", "00000000000000", "02.429.144/0001-00", "", "a" * 121]
)
def test_entrada_invalida_e_422(cliente, q):
    assert cliente.get(ROTA, params={"q": q}).status_code == 422


def test_empresa_sem_ficha_nao_puxa_receita_e_da_sugestao(cliente, monkeypatch):
    monkeypatch.setattr(
        "src.cadastro_da_receita.vista_do_cnpj",
        lambda *a, **k: pytest.fail("Receita fora da busca"),
        raising=False,
    )
    r = cliente.get(ROTA, params={"q": "33000167000101"})
    assert r.status_code == 404
    assert "base aberta" in r.json()["detail"]["mensagem"]
    assert r.json()["detail"]["sugestoes"]
    assert r.headers.get("cache-control") != "public, max-age=86400"


def test_limite_ip_conta_cache_e_separa_ips_do_proxy_confiavel(cliente):
    for _ in range(60):
        assert cliente.get(ROTA, params={"q": CNPJ}).status_code == 200
    assert cliente.get(ROTA, params={"q": CNPJ}).status_code == 429
    assert (
        cliente.get(
            ROTA, params={"q": CNPJ}, headers={"CF-Connecting-IP": "192.0.2.5"}
        ).status_code
        == 200
    )


def test_ficha_lida_uma_vez_no_dia_e_portao_reconferido(cliente, monkeypatch):
    original = dossie.ficha_do
    chamadas = []

    def ler(*a, **k):
        chamadas.append(a)
        return original(*a, **k)

    monkeypatch.setattr(dossie, "ficha_do", ler)
    assert cliente.get(ROTA, params={"q": CNPJ}).status_code == 200
    assert cliente.get(ROTA, params={"q": CNPJ}).status_code == 200
    assert len(chamadas) == 1
    monkeypatch.setattr("base.dossie.pode_mostrar", lambda _: False)
    assert cliente.get(ROTA, params={"q": CNPJ}).status_code != 200


def test_origem_de_fora_nao_recebe_cors(cliente):
    r = cliente.get(
        ROTA, params={"q": CNPJ}, headers={"Origin": "https://fora.example"}
    )
    assert "access-control-allow-origin" not in r.headers


def test_cnpj_de_companhia_aberta_sem_ticker_tambem_tem_ficha(cliente, banco):
    with banco.begin() as c:
        c.execute(sa.delete(tickers_dos_emissores))
    assert cliente.get(ROTA, params={"q": CNPJ}).status_code == 200


def test_ip_forjado_nao_fura_limite_sem_proxy_confiavel(cliente):
    from fastapi.testclient import TestClient

    from src import api

    direto = TestClient(
        api.criar_app({VARIAVEL_DA_CHAVE: "1"}), client=("192.0.2.10", 50000)
    )
    for i in range(60):
        assert (
            direto.get(
                ROTA,
                params={"q": CNPJ},
                headers={"CF-Connecting-IP": f"198.51.100.{i}"},
            ).status_code
            == 200
        )
    assert (
        direto.get(
            ROTA, params={"q": CNPJ}, headers={"CF-Connecting-IP": "198.51.100.200"}
        ).status_code
        == 429
    )


@pytest.mark.parametrize("q", ["%' OR 1=1 --", "../../dados", "_", "%"])
def test_consulta_nao_interpreta_sql_nem_caminhos(cliente, q):
    assert cliente.get(ROTA, params={"q": q}).status_code in (404, 422)


def test_banco_indisponivel_da_503_sem_detalhe_interno(cliente, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    from src.api_v1 import base_publica

    def falhar(*a, **k):
        raise SQLAlchemyError("segredo interno")

    monkeypatch.setattr(base_publica, "obter_engine", falhar)
    r = cliente.get(ROTA, params={"q": CNPJ})
    assert r.status_code == 503
    assert "segredo interno" not in r.text


def test_cadastro_com_ficha_ausente_ou_de_outra_empresa_nao_vaza(
    cliente, monkeypatch, ficha
):
    from src.api_v1 import base_publica

    with monkeypatch.context() as m:
        m.setattr(base_publica, "_ficha", lambda *a: None)
        assert cliente.get(ROTA, params={"q": CNPJ}).status_code == 404
        ficha.cnpj = "33000167000101"
        m.setattr(base_publica, "_ficha", lambda *a: ficha)
        assert cliente.get(ROTA, params={"q": CNPJ}).status_code == 404
        assert base_publica._resposta("00000000000000", base_publica.hoje()) is None
