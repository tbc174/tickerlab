"""Cliente JSON-RPC do nó do Bitcoin (base de cripto, série 1, PR 2). Sem rede: o `requests.post`
é trocado por um dublê que guarda o pedido e devolve a resposta montada."""

import json
from decimal import Decimal

import pytest

from base.cripto import no_bitcoin
from base.cripto.no_bitcoin import ClienteRPC, ErroDoNo

SENHA = "senha-do-cookie-123"


class _Resposta:
    def __init__(self, texto: str, status: int = 200):
        self.text = texto
        self.status_code = status


@pytest.fixture
def cookie(tmp_path):
    arquivo = tmp_path / ".cookie"
    arquivo.write_text(f"__cookie__:{SENHA}\n", encoding="utf-8")
    return arquivo


@pytest.fixture
def pedidos(monkeypatch):
    """Guarda cada pedido; a resposta é a da vez em `pedidos.respostas` (uma lista)."""

    class Pedidos(list):
        def __init__(self):
            super().__init__()
            self.respostas: list = []

    feitos = Pedidos()

    def post(url, json, auth, timeout):
        feitos.append({"url": url, "json": json, "auth": auth, "timeout": timeout})
        return feitos.respostas.pop(0)

    monkeypatch.setattr(no_bitcoin.requests, "post", post)
    return feitos


def _resultado(valor) -> _Resposta:
    return _Resposta(json.dumps({"result": valor, "error": None, "id": "tickerlab"}))


def test_pede_com_o_cookie_e_o_metodo_certo(cookie, pedidos):
    pedidos.respostas = [_resultado(850_000)]

    altura = ClienteRPC(arquivo_do_cookie=cookie).altura_do_topo()

    assert altura == 850_000
    assert pedidos[0]["json"]["method"] == "getblockcount"
    assert pedidos[0]["auth"] == ("__cookie__", SENHA)
    assert pedidos[0]["url"] == "http://127.0.0.1:8332"


def test_bloco_vem_com_verbosity_3_e_valores_em_decimal(cookie, pedidos):
    pedidos.respostas = [
        _Resposta('{"result": {"tx": [{"value": 0.1}]}, "error": null}')
    ]

    bloco = ClienteRPC(arquivo_do_cookie=cookie).bloco("ab" * 32)

    assert pedidos[0]["json"]["params"] == ["ab" * 32, 3]
    assert bloco["tx"][0]["value"] == Decimal("0.1")


def test_total_nao_gasto_na_altura_em_satoshis(cookie, pedidos):
    pedidos.respostas = [_resultado({"total_amount": 19_500_000.12345678})]

    total = ClienteRPC(arquivo_do_cookie=cookie).total_nao_gasto(850_000)

    assert pedidos[0]["json"]["method"] == "gettxoutsetinfo"
    assert pedidos[0]["json"]["params"] == ["none", 850_000]
    assert total == 1_950_000_012_345_678


def test_liberar_ate_poda_o_no(cookie, pedidos):
    pedidos.respostas = [_resultado(840_000)]

    ClienteRPC(arquivo_do_cookie=cookie).liberar_ate(840_000)

    assert pedidos[0]["json"]["method"] == "pruneblockchain"
    assert pedidos[0]["json"]["params"] == [840_000]


def test_erro_do_no_vira_mensagem_legivel_sem_a_senha(cookie, pedidos):
    erro = {
        "result": None,
        "error": {"code": -8, "message": "Block height out of range"},
    }
    pedidos.respostas = [_Resposta(json.dumps(erro), status=500)]

    with pytest.raises(
        ErroDoNo, match="getblockhash: Block height out of range"
    ) as erro_lido:
        ClienteRPC(arquivo_do_cookie=cookie).hash_na_altura(10**9)

    assert SENHA not in str(erro_lido.value)


def test_no_que_recusa_o_acesso(cookie, pedidos):
    pedidos.respostas = [_Resposta("", status=401)]

    with pytest.raises(ErroDoNo, match="401"):
        ClienteRPC(arquivo_do_cookie=cookie).altura_do_topo()


def test_tamanho_dos_blocos_no_disco(cookie, pedidos):
    pedidos.respostas = [_resultado({"blocks": 900_000, "size_on_disk": 12_345})]

    assert ClienteRPC(arquivo_do_cookie=cookie).tamanho_dos_blocos() == 12_345
    assert pedidos[0]["json"]["method"] == "getblockchaininfo"


def test_ligar_e_desligar_a_rede_do_no(cookie, pedidos):
    pedidos.respostas = [_resultado(False)]

    ClienteRPC(arquivo_do_cookie=cookie).ligar_rede(False)

    assert pedidos[0]["json"]["method"] == "setnetworkactive"
    assert pedidos[0]["json"]["params"] == [False]
