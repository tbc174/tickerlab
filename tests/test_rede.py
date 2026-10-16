"""Testes de `src/rede.py`: o `requests.get` que tenta de novo quando a fonte falha por um instante."""

import io

import pytest
import requests

from src import rede


def _resposta(status: int, retry_after: str | None = None) -> requests.Response:
    resposta = requests.Response()
    resposta.status_code = status
    resposta.raw = io.BytesIO(b"")
    if retry_after is not None:
        resposta.headers["Retry-After"] = retry_after
    return resposta


@pytest.fixture
def esperas(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Troca a espera de verdade por uma lista: os testes não dormem e veem quanto esperariam."""
    guardadas: list[float] = []
    monkeypatch.setattr(rede, "esperar", guardadas.append)
    return guardadas


def _fonte(monkeypatch: pytest.MonkeyPatch, *respostas: object) -> list[tuple]:
    """Faz o `requests.get` devolver (ou levantar) cada item, em ordem; guarda as chamadas."""
    fila = list(respostas)
    chamadas: list[tuple] = []

    def falso_get(url: str, *args: object, **kwargs: object) -> requests.Response:
        chamadas.append((url, args, kwargs))
        proxima = fila.pop(0)
        if isinstance(proxima, Exception):
            raise proxima
        assert isinstance(proxima, requests.Response)
        return proxima

    monkeypatch.setattr(requests, "get", falso_get)
    return chamadas


def test_resposta_boa_volta_na_primeira(monkeypatch, esperas):
    chamadas = _fonte(monkeypatch, _resposta(200))
    assert rede.obter("https://x").status_code == 200
    assert len(chamadas) == 1
    assert esperas == []


def test_repassa_os_argumentos_e_poe_um_tempo_limite(monkeypatch, esperas):
    chamadas = _fonte(monkeypatch, _resposta(200), _resposta(200))
    rede.obter("https://x", params={"a": 1}, headers={"User-Agent": "T"})
    rede.obter("https://x", timeout=5)
    assert chamadas[0][2] == {
        "params": {"a": 1},
        "headers": {"User-Agent": "T"},
        "timeout": rede.TEMPO_LIMITE,
    }
    assert chamadas[1][2] == {"timeout": 5}


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_erro_passageiro_tenta_de_novo(monkeypatch, esperas, status):
    chamadas = _fonte(monkeypatch, _resposta(status), _resposta(200))
    assert rede.obter("https://x").status_code == 200
    assert len(chamadas) == 2
    assert len(esperas) == 1


@pytest.mark.parametrize("status", [400, 403, 404])
def test_erro_do_pedido_volta_na_hora(monkeypatch, esperas, status):
    """Repetir um 404 não muda a resposta; quem chama decide (várias coletas pulam o 404)."""
    chamadas = _fonte(monkeypatch, _resposta(status))
    assert rede.obter("https://x").status_code == status
    assert len(chamadas) == 1
    assert esperas == []


@pytest.mark.parametrize(
    "erro", [requests.ConnectionError("caiu"), requests.Timeout("demorou")]
)
def test_conexao_que_cai_tenta_de_novo(monkeypatch, esperas, erro):
    chamadas = _fonte(monkeypatch, erro, erro, _resposta(200))
    assert rede.obter("https://x").status_code == 200
    assert len(chamadas) == 3


def test_outro_erro_nao_tenta_de_novo(monkeypatch, esperas):
    chamadas = _fonte(monkeypatch, requests.exceptions.InvalidURL("ruim"))
    with pytest.raises(requests.exceptions.InvalidURL):
        rede.obter("ruim")
    assert len(chamadas) == 1


def test_esgotadas_as_tentativas_devolve_a_ultima_resposta(monkeypatch, esperas):
    """Quem chama continua usando `raise_for_status()` como antes."""
    chamadas = _fonte(monkeypatch, *[_resposta(502) for _ in range(rede.TENTATIVAS)])
    resposta = rede.obter("https://x")
    assert resposta.status_code == 502
    assert len(chamadas) == rede.TENTATIVAS
    assert len(esperas) == rede.TENTATIVAS - 1
    with pytest.raises(requests.HTTPError):
        resposta.raise_for_status()


def test_esgotadas_as_tentativas_levanta_o_erro_original(monkeypatch, esperas):
    _fonte(monkeypatch, *[requests.Timeout("demorou") for _ in range(rede.TENTATIVAS)])
    with pytest.raises(requests.Timeout):
        rede.obter("https://x")


def test_esperas_crescem_e_tem_teto(monkeypatch, esperas):
    _fonte(monkeypatch, *[_resposta(503) for _ in range(rede.TENTATIVAS)])
    rede.obter("https://x")
    assert esperas == sorted(esperas)
    assert esperas[0] >= rede.ESPERA_INICIAL
    assert all(espera <= rede.ESPERA_MAXIMA for espera in esperas)


def test_respeita_o_retry_after_da_fonte(monkeypatch, esperas):
    _fonte(monkeypatch, _resposta(429, retry_after="30"), _resposta(200))
    rede.obter("https://x")
    assert esperas[0] >= 30


def test_retry_after_exagerado_fica_no_teto(monkeypatch, esperas):
    _fonte(monkeypatch, _resposta(503, retry_after="3600"), _resposta(200))
    rede.obter("https://x")
    assert esperas[0] == rede.ESPERA_MAXIMA


def test_retry_after_em_data_e_ignorado(monkeypatch, esperas):
    _fonte(
        monkeypatch,
        _resposta(503, retry_after="Wed, 21 Oct 2026 07:28:00 GMT"),
        _resposta(200),
    )
    rede.obter("https://x")
    assert rede.ESPERA_INICIAL <= esperas[0] <= rede.ESPERA_MAXIMA


def test_fecha_a_resposta_descartada(monkeypatch, esperas):
    """Com `stream=True` a conexão fica aberta até alguém fechar a resposta."""
    descartada = _resposta(503)
    _fonte(monkeypatch, descartada, _resposta(200))
    rede.obter("https://x", stream=True)
    assert descartada.raw.closed
