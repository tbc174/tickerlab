"""Registro de acesso da API (Marco Civil, art. 15): IP real só de proxy confiável, sem dado da conta."""

import json

from fastapi.testclient import TestClient

from src import api
from src.registro_de_acesso import (
    VARIAVEL_DO_ARQUIVO,
    VARIAVEL_DOS_PROXIES,
    ip_do_cliente,
    ler_proxies_confiaveis,
)

GATEWAY = "172.18.0.1"
VISITANTE = "203.0.113.7"
FORJADO = "198.51.100.99"


def _app(tmp_path, proxies=GATEWAY):
    arquivo = tmp_path / "acesso-api.log"
    ambiente = {VARIAVEL_DO_ARQUIVO: str(arquivo), VARIAVEL_DOS_PROXIES: proxies}
    return api.criar_app(ambiente), arquivo


def _linhas(arquivo):
    return [json.loads(linha) for linha in arquivo.read_text("utf-8").splitlines()]


def test_ip_do_proxy_confiavel_vale_o_cabecalho_da_cloudflare():
    redes = ler_proxies_confiaveis(GATEWAY)
    assert ip_do_cliente(GATEWAY, {"cf-connecting-ip": VISITANTE}, redes) == VISITANTE


def test_cabecalho_de_origem_nao_confiavel_e_ignorado():
    redes = ler_proxies_confiaveis(GATEWAY)
    cabecalhos = {"cf-connecting-ip": FORJADO, "x-forwarded-for": FORJADO}
    assert ip_do_cliente("192.0.2.5", cabecalhos, redes) == "192.0.2.5"


def test_sem_proxies_configurados_nenhum_cabecalho_vale():
    assert ip_do_cliente(GATEWAY, {"cf-connecting-ip": FORJADO}, ()) == GATEWAY


def test_sem_cf_usa_o_ultimo_da_cadeia_e_nao_o_primeiro():
    redes = ler_proxies_confiaveis(GATEWAY)
    cadeia = {"x-forwarded-for": f"{FORJADO}, {VISITANTE}"}
    assert ip_do_cliente(GATEWAY, cadeia, redes) == VISITANTE


def test_cabecalho_invalido_cai_no_ip_de_origem():
    redes = ler_proxies_confiaveis(GATEWAY)
    assert ip_do_cliente(GATEWAY, {"cf-connecting-ip": "lixo"}, redes) == GATEWAY


def test_aceita_rede_e_ignora_entrada_invalida():
    redes = ler_proxies_confiaveis("172.18.0.0/16, banana, ")
    assert len(redes) == 1
    assert (
        ip_do_cliente("172.18.5.5", {"cf-connecting-ip": VISITANTE}, redes) == VISITANTE
    )


def test_registra_ip_real_hora_pedido_codigo_e_navegador(tmp_path):
    app, arquivo = _app(tmp_path)
    cliente = TestClient(app, client=(GATEWAY, 5000))
    resposta = cliente.get(
        "/saude?codigo=segredo",
        headers={"CF-Connecting-IP": VISITANTE, "User-Agent": "Navegador/1"},
    )
    (linha,) = _linhas(arquivo)
    assert linha["ip"] == VISITANTE
    assert linha["metodo"] == "GET"
    assert linha["caminho"] == "/saude"
    assert linha["status"] == resposta.status_code
    assert linha["navegador"] == "Navegador/1"
    assert linha["hora"]


def test_registro_nao_leva_query_string_nem_dado_da_conta(tmp_path):
    app, arquivo = _app(tmp_path)
    cliente = TestClient(app, client=(GATEWAY, 5000))
    cliente.get(
        "/newsletter/sair?codigo=senha-do-link",
        headers={
            "CF-Connecting-IP": VISITANTE,
            "Authorization": "Bearer token-secreto",
        },
    )
    texto = arquivo.read_text("utf-8")
    assert "senha-do-link" not in texto
    assert "token-secreto" not in texto
    assert set(_linhas(arquivo)[0]) == {
        "hora",
        "ip",
        "metodo",
        "caminho",
        "status",
        "navegador",
    }


def test_cabecalho_forjado_por_quem_nao_e_proxy_nao_entra_no_registro(tmp_path):
    app, arquivo = _app(tmp_path)
    cliente = TestClient(app, client=("192.0.2.5", 5000))
    cliente.get("/saude", headers={"CF-Connecting-IP": FORJADO})
    assert _linhas(arquivo)[0]["ip"] == "192.0.2.5"


def test_sem_arquivo_configurado_nao_registra_nada(tmp_path):
    app = api.criar_app({})
    TestClient(app).get("/saude")
    assert list(tmp_path.iterdir()) == []


def test_falha_ao_gravar_nao_derruba_o_pedido(tmp_path):
    ambiente = {
        VARIAVEL_DO_ARQUIVO: str(tmp_path / "pasta" / "que" / "nao" / "existe.log")
    }
    resposta = TestClient(api.criar_app(ambiente)).get("/saude")
    assert resposta.status_code in (200, 503)
