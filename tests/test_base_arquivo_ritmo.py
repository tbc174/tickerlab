"""O ritmo do arquivista (base/arquivo/ritmo.py): pausa por site e respeito ao 429. Sem internet:
o relógio, a espera e o robots.txt são dublês."""

import logging
from datetime import UTC, datetime

import pytest
import requests

from base.arquivo import robots
from base.arquivo.cliente_http import ClienteHttp
from base.arquivo.ritmo import (
    ESPERA_MAXIMA_EM_SEGUNDOS,
    ESPERA_SEM_RETRY_AFTER_EM_SEGUNDOS,
    PAUSA_DOS_PORTAIS_CKAN_EM_SEGUNDOS,
    PAUSAS_DE_RESERVA,
    TENTATIVAS_SE_429,
    TETO_DA_PAUSA_EM_SEGUNDOS,
    Ritmo,
    espera_do_retry_after,
)

PORTAL = "https://dados.exemplo.gov.br"
ROBOTS_COM_PAUSA = "User-agent: *\nCrawl-delay: 10\nDisallow: /privado\n"


class Relogio:
    """Tempo falso: `esperar` só avança o relógio."""

    def __init__(self) -> None:
        self.agora = 1000.0
        self.esperas: list[float] = []

    def __call__(self) -> float:
        return self.agora

    def esperar(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.agora += segundos


def _ritmo(texto: str | None, relogio: Relogio) -> Ritmo:
    return Ritmo(lambda url: texto, relogio=relogio, esperar=relogio.esperar)


def test_crawl_delay_do_robots_vira_pausa():
    assert robots.pausa_pedida(ROBOTS_COM_PAUSA) == 10.0
    assert robots.pausa_pedida("User-agent: *\nDisallow: /x\n") is None
    assert robots.pausa_pedida("User-agent: *\nCrawl-delay: depressa\n") is None
    # o grupo do nosso agente vale mais que o `*`
    assert (
        robots.pausa_pedida(
            "User-agent: *\nCrawl-delay: 10\n\nUser-agent: TickerLab\nCrawl-delay: 2\n"
        )
        == 2.0
    )


def test_crawl_delay_nao_atrapalha_as_regras_de_caminho():
    assert robots.pode_buscar(ROBOTS_COM_PAUSA, "/dados")
    assert not robots.pode_buscar(ROBOTS_COM_PAUSA, "/privado/x")


def test_pausa_sai_do_robots_e_vale_para_toda_chamada_ao_site():
    relogio = Relogio()
    ritmo = _ritmo(ROBOTS_COM_PAUSA, relogio)
    ritmo.esperar_a_vez(
        f"{PORTAL}/api/3/action/package_show?id=a"
    )  # o primeiro não espera
    relogio.agora += 3  # 3 s de download
    ritmo.esperar_a_vez(f"{PORTAL}/arquivo.csv")
    assert relogio.esperas == [7.0]  # os 10 s contam desde o pedido anterior
    ritmo.esperar_a_vez(f"{PORTAL}/api/3/action/package_show?id=b")
    assert relogio.esperas == [7.0, 10.0]


def test_robots_e_lido_uma_vez_por_site():
    lidos: list[str] = []
    ritmo = Ritmo(
        lambda url: lidos.append(url) or ROBOTS_COM_PAUSA, esperar=lambda s: None
    )
    ritmo.esperar_a_vez(f"{PORTAL}/a")
    ritmo.esperar_a_vez(f"{PORTAL}/b")
    ritmo.esperar_a_vez("https://outro.exemplo.gov.br/a")
    assert lidos == [f"{PORTAL}/robots.txt", "https://outro.exemplo.gov.br/robots.txt"]


def test_sem_robots_vale_a_tabela_de_reserva():
    relogio = Relogio()
    ritmo = _ritmo(None, relogio)
    assert ritmo.pausa_do("https://dados.cvm.gov.br/dados/x") == (
        PAUSA_DOS_PORTAIS_CKAN_EM_SEGUNDOS
    )
    assert len(PAUSAS_DE_RESERVA) == 7
    assert ritmo.pausa_do("https://site.desconhecido.com.br/x") == 0.0


def test_portal_sem_crawl_delay_mantem_o_ritmo_de_hoje():
    relogio = Relogio()
    ritmo = _ritmo("User-agent: *\nDisallow: /privado\n", relogio)
    ritmo.esperar_a_vez(f"{PORTAL}/a")
    ritmo.esperar_a_vez(f"{PORTAL}/b")
    assert relogio.esperas == []
    # robots que respondeu sem pausa vale mais que a tabela
    assert _ritmo("User-agent: *\n", relogio).pausa_do("https://dados.cvm.gov.br/") == 0


def test_pausa_absurda_tem_teto():
    ritmo = _ritmo("User-agent: *\nCrawl-delay: 99999\n", Relogio())
    assert ritmo.pausa_do(PORTAL) == TETO_DA_PAUSA_EM_SEGUNDOS


def test_servidor_local_nunca_espera():
    relogio = Relogio()
    ritmo = Ritmo(
        lambda url: pytest.fail("não lê robots local"), esperar=relogio.esperar
    )
    assert ritmo.pausa_do("http://127.0.0.1:8000/x") == 0.0


@pytest.mark.parametrize(
    ("cabecalhos", "esperado"),
    [
        ({"Retry-After": "30"}, 30.0),
        ({"retry-after": "5"}, 5.0),
        ({"Retry-After": "99999"}, ESPERA_MAXIMA_EM_SEGUNDOS),
        ({}, ESPERA_SEM_RETRY_AFTER_EM_SEGUNDOS),
        ({"Retry-After": "logo"}, ESPERA_SEM_RETRY_AFTER_EM_SEGUNDOS),
    ],
)
def test_retry_after_em_segundos(cabecalhos, esperado):
    assert espera_do_retry_after(cabecalhos) == esperado


def test_retry_after_em_data_http():
    agora = datetime(2026, 10, 22, 7, 0, 0, tzinfo=UTC)
    data = {"Retry-After": "Thu, 22 Oct 2026 07:00:45 GMT"}
    assert espera_do_retry_after(data, agora) == 45.0


class _Resposta:
    def __init__(self, status: int, cabecalhos: dict[str, str] | None = None):
        self.status_code = status
        self.headers = cabecalhos or {}
        self.content = b'{"ok": true}'
        self.url = PORTAL
        self.fechada = False

    def close(self) -> None:
        self.fechada = True

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)  # type: ignore[arg-type]


def _cliente_com_respostas(respostas: list[_Resposta], relogio: Relogio):
    cliente = ClienteHttp(_ritmo(ROBOTS_COM_PAUSA, relogio))
    pedidos: list[str] = []

    def request(metodo, url, **opcoes):
        pedidos.append(url)
        return respostas.pop(0)

    cliente.sessao.request = request  # type: ignore[method-assign]
    return cliente, pedidos


def test_429_espera_o_retry_after_e_tenta_de_novo(caplog):
    relogio = Relogio()
    primeira = _Resposta(429, {"Retry-After": "30"})
    cliente, pedidos = _cliente_com_respostas([primeira, _Resposta(200)], relogio)
    with caplog.at_level(logging.WARNING):
        resposta = cliente.ler(f"{PORTAL}/api/x?token=segredo")
    assert resposta.conteudo == b'{"ok": true}'
    assert len(pedidos) == 2
    assert 30.0 in relogio.esperas and primeira.fechada
    assert "429" in caplog.text and "segredo" not in caplog.text
    assert "dados.exemplo.gov.br" in caplog.text


def test_429_que_nao_passa_desiste_depois_das_tentativas():
    relogio = Relogio()
    respostas = [
        _Resposta(429, {"Retry-After": "1"}) for _ in range(TENTATIVAS_SE_429 + 1)
    ]
    cliente, pedidos = _cliente_com_respostas(respostas, relogio)
    with pytest.raises(requests.HTTPError):
        cliente.ler(f"{PORTAL}/api/x")
    assert len(pedidos) == 1 + TENTATIVAS_SE_429


def test_pedidos_seguidos_ao_portal_esperam_a_pausa():
    relogio = Relogio()
    cliente, _ = _cliente_com_respostas([_Resposta(200), _Resposta(200)], relogio)
    cliente.ler(f"{PORTAL}/api/3/action/package_show?id=a")
    cliente.ler(f"{PORTAL}/api/3/action/package_show?id=b")
    assert relogio.esperas == [10.0]


def test_cliente_le_o_robots_do_site_e_cai_na_reserva_se_ele_falha():
    cliente = ClienteHttp()
    pedidos: list[str] = []

    def get(url, **opcoes):
        pedidos.append(url)
        raise requests.ConnectionError("fora do ar")

    cliente.sessao.get = get  # type: ignore[method-assign]
    assert cliente.ritmo.pausa_do("https://dados.ons.org.br/dataset/x") == 10.0
    assert pedidos == ["https://dados.ons.org.br/robots.txt"]
