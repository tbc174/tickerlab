"""A rota pública da ferramenta "Quanto daria? Foi sorte?" (src/api_v1/ferramentas.py, ADR 0070).

Sem login, só números soltos (nenhuma lista de números na resposta), limite por IP, a mesma pergunta
no mesmo dia vem do cache, CORS só para o site, e o interruptor que desliga o Yahoo.
"""

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src import api
from src.api_v1 import VARIAVEL_DA_CHAVE, ferramentas
from src.ferramentas import ponte_dados

HOJE = date(2026, 10, 15)
MESES = [
    f"{2015 + i // 12}-{i % 12 + 1:02d}" for i in range(140)
]  # jan/2015 a ago/2026
ARQUIVO = {
    "cdi_mensal": {"meses": [[m, 0.008] for m in MESES], "ultimo": MESES[-1]},
    "poupanca_mensal": {"meses": [[m, 0.005] for m in MESES], "ultimo": MESES[-1]},
    "dolar_mensal": {
        "meses": [[m, 3.0 + i / 50] for i, m in enumerate(MESES)],
        "ultimo": MESES[-1],
    },
    "ipca": {"meses": [[m, 0.004] for m in MESES], "ultimo": MESES[-1]},
}
YAHOO = {
    "ibovespa": pd.Series(
        [50_000 * 1.007**i for i in range(140)],
        index=pd.to_datetime([f"{m}-01" for m in MESES]),
    ),
    "bitcoin": pd.Series(
        [1_000 * 1.03**i for i in range(100)],
        index=pd.to_datetime([f"{m}-01" for m in MESES[40:]]),
    ),
}
ORIGEM = "https://tickerlab.com.br"


@pytest.fixture
def chamadas(monkeypatch):
    feitas = {"arquivo": 0, "yahoo": 0}

    def arquivo(hoje):
        feitas["arquivo"] += 1
        return ARQUIVO

    def yahoo(ativo, hoje, dolar):
        feitas["yahoo"] += 1
        return YAHOO[ativo]

    monkeypatch.setattr(ponte_dados, "obter_arquivo", arquivo)
    monkeypatch.setattr(ponte_dados, "obter_curva_do_yahoo", yahoo)
    monkeypatch.setattr(ferramentas, "hoje", lambda: HOJE)
    monkeypatch.setattr(ponte_dados, "_hora_agora", lambda: 12)
    monkeypatch.delenv("TICKERLAB_PONTE_COM_YAHOO", raising=False)
    ferramentas.LIMITE_POR_IP.zerar()
    ferramentas.CALCULADOS.clear()
    return feitas


@pytest.fixture
def cliente(chamadas, monkeypatch):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    return TestClient(api.criar_app({VARIAVEL_DA_CHAVE: "1"}))


def _pedir(cliente, desde="2020-01-02", valor="1000", **kwargs):
    return cliente.get(
        "/api/v1/ferramentas/quanto-daria",
        params={"desde": desde, "valor": valor},
        **kwargs,
    )


def test_sem_login_devolve_os_seis_ativos_com_numeros_soltos(cliente):
    resposta = _pedir(cliente)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [a["ativo"] for a in corpo["ativos"]] == [
        "cdi",
        "poupanca",
        "dolar",
        "parado",
        "ibovespa",
        "bitcoin",
    ]
    cdi = corpo["ativos"][0]
    assert cdi["inicio"] == "2020-01-01"
    assert cdi["valor_final"] == pytest.approx(1000 * 1.008 ** (len(MESES) - 60))
    assert cdi["janelas"]["quantas"] > 1
    assert corpo["indisponiveis"] == []
    assert "não é recomendação" in corpo["aviso"]


def _listas_de_numeros(esquema, definicoes, caminho=""):
    """Os caminhos do esquema que são listas de números (o que a ADR 0070 proíbe: a série)."""
    if "$ref" in esquema:
        nome = esquema["$ref"].split("/")[-1]
        return _listas_de_numeros(definicoes[nome], definicoes, caminho)
    achados = []
    if esquema.get("type") == "array":
        itens = esquema.get("items", {})
        if itens.get("type") in ("number", "integer") or "prefixItems" in esquema:
            achados.append(caminho)
        achados += _listas_de_numeros(itens, definicoes, caminho + "[]")
    for nome, sub in esquema.get("properties", {}).items():
        achados += _listas_de_numeros(sub, definicoes, f"{caminho}.{nome}")
    for sub in esquema.get("anyOf", []):
        achados += _listas_de_numeros(sub, definicoes, caminho)
    return achados


def test_a_resposta_nao_tem_nenhuma_lista_de_numeros():
    esquema = ferramentas.QuantoDariaV1.model_json_schema()
    assert _listas_de_numeros(esquema, esquema.get("$defs", {})) == []


@pytest.mark.parametrize(
    ("desde", "valor"),
    [
        ("2020-01-02", "0"),
        ("2020-01-02", "20000000"),
        ("2026-10-01", "1000"),
        ("ontem", "1000"),
    ],
)
def test_pedido_fora_dos_limites_e_422(cliente, desde, valor):
    assert _pedir(cliente, desde, valor).status_code == 422


def test_o_31o_pedido_do_mesmo_ip_no_minuto_e_429(cliente):
    for _ in range(ferramentas.PEDIDOS_POR_MINUTO_POR_IP):
        assert (
            _pedir(cliente, headers={"cf-connecting-ip": "203.0.113.9"}).status_code
            == 200
        )
    assert (
        _pedir(cliente, headers={"cf-connecting-ip": "203.0.113.9"}).status_code == 429
    )
    assert (
        _pedir(cliente, headers={"cf-connecting-ip": "203.0.113.10"}).status_code == 200
    )


def test_cors_so_para_o_site(cliente):
    do_site = _pedir(cliente, headers={"origin": ORIGEM})
    assert do_site.headers["access-control-allow-origin"] == ORIGEM
    assert "origin" in do_site.headers["vary"].lower()
    de_fora = _pedir(cliente, headers={"origin": "https://outro.exemplo"})
    assert "access-control-allow-origin" not in de_fora.headers


def test_a_mesma_pergunta_no_mesmo_dia_vem_do_cache_e_o_valor_so_multiplica(
    cliente, chamadas
):
    um = _pedir(cliente, valor="1000").json()
    dois = _pedir(cliente, desde="2020-01-20", valor="2000").json()  # o mesmo mês
    assert chamadas["arquivo"] == 1
    assert dois["ativos"][0]["valor_final"] == pytest.approx(
        2 * um["ativos"][0]["valor_final"]
    )


def test_sem_o_yahoo_ligado_ficam_so_os_ativos_do_banco_central(cliente, monkeypatch):
    monkeypatch.setenv("TICKERLAB_PONTE_COM_YAHOO", "0")
    corpo = _pedir(cliente).json()
    assert [a["ativo"] for a in corpo["ativos"]] == [
        "cdi",
        "poupanca",
        "dolar",
        "parado",
    ]


def test_ativo_que_falha_ou_ainda_nao_existia_entra_nos_indisponiveis(
    cliente, monkeypatch
):
    def yahoo(ativo, hoje, dolar):
        if ativo == "ibovespa":
            raise ponte_dados.CurvaIndisponivelError("fora do ar")
        return YAHOO[ativo]

    monkeypatch.setattr(ponte_dados, "obter_curva_do_yahoo", yahoo)
    corpo = _pedir(
        cliente, desde="2016-01-04"
    ).json()  # antes do 1º mês do bitcoin aqui
    nomes = [i["nome"] for i in corpo["indisponiveis"]]
    assert nomes == ["Ibovespa", "Bitcoin"]
    assert "começam em" in corpo["indisponiveis"][1]["motivo"]


def test_sem_o_arquivo_de_dados_e_503(cliente, monkeypatch):
    def sem_arquivo(hoje):
        raise ponte_dados.CurvaIndisponivelError("fora do ar")

    monkeypatch.setattr(ponte_dados, "obter_arquivo", sem_arquivo)
    assert _pedir(cliente).status_code == 503


def test_arquivo_ainda_sem_o_dolar_deixa_so_o_dolar_e_o_bitcoin_de_fora(
    cliente, monkeypatch
):
    # na 1ª vez no ar, o cron ainda não gerou o dólar mês a mês: o resto funciona
    sem_dolar = {k: v for k, v in ARQUIVO.items() if k != "dolar_mensal"}
    monkeypatch.setattr(ponte_dados, "obter_arquivo", lambda hoje: sem_dolar)
    corpo = _pedir(cliente).json()
    assert [a["ativo"] for a in corpo["ativos"]] == [
        "cdi",
        "poupanca",
        "parado",
        "ibovespa",
    ]
    assert [i["nome"] for i in corpo["indisponiveis"]] == ["Dólar", "Bitcoin"]


def test_o_cache_de_ontem_e_jogado_fora(cliente, monkeypatch):
    _pedir(cliente)
    assert len(ferramentas.CALCULADOS) == 1
    monkeypatch.setattr(ferramentas, "hoje", lambda: date(2026, 10, 16))
    _pedir(cliente, desde="2019-01-01")
    assert [momento[0] for _, momento in ferramentas.CALCULADOS] == [date(2026, 10, 16)]


def test_data_de_seculos_atras_e_422(cliente):
    assert _pedir(cliente, desde="0001-01-01").status_code == 422


@pytest.mark.parametrize(
    ("desde", "valor", "status"),
    [("2026-10-01", "1000", 422), ("ontem", "1000", 422), ("2020-01-02", "muito", 422)],
)
def test_erros_tambem_levam_o_cors_para_o_site_ler_a_mensagem(
    cliente, desde, valor, status
):
    resposta = _pedir(cliente, desde, valor, headers={"origin": ORIGEM})
    assert resposta.status_code == status
    assert resposta.headers["access-control-allow-origin"] == ORIGEM
    assert isinstance(resposta.json()["detail"], str)


def test_o_429_tambem_leva_o_cors(cliente):
    cabecalhos = {"origin": ORIGEM, "cf-connecting-ip": "203.0.113.20"}
    for _ in range(ferramentas.PEDIDOS_POR_MINUTO_POR_IP):
        _pedir(cliente, headers=cabecalhos)
    resposta = _pedir(cliente, headers=cabecalhos)
    assert resposta.status_code == 429
    assert resposta.headers["access-control-allow-origin"] == ORIGEM


def test_falha_do_yahoo_nao_fica_no_cache_do_resultado(cliente, monkeypatch):
    estado = {"fora": True}

    def yahoo(ativo, hoje, dolar):
        if estado["fora"]:
            raise ponte_dados.CurvaIndisponivelError("fora do ar")
        return YAHOO[ativo]

    monkeypatch.setattr(ponte_dados, "obter_curva_do_yahoo", yahoo)
    assert len(_pedir(cliente).json()["indisponiveis"]) == 2
    estado["fora"] = False  # o Yahoo voltou
    assert _pedir(cliente).json()["indisponiveis"] == []
