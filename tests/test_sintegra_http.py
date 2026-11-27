"""O cliente consulta robots antes dos TXT, nunca contorna desafio ou redireção."""

import pytest

from base import sintegra_http as http
from base.arquivo.agente import AGENTE
from base.sintegra_estadual import URLS_PR


class _Resposta:
    def __init__(self, conteudo=b"", status=200, cabecalhos=None):
        self.conteudo = conteudo
        self.status_code = status
        self.headers = cabecalhos or {}
        self.fechada = False
        self.raw = self
        self._inicio = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.fechada = True

    def read1(self, tamanho, *, decode_content):
        assert not decode_content
        bloco = self.conteudo[self._inicio : self._inicio + tamanho]
        self._inicio += len(bloco)
        return bloco


class _Sessao:
    def __init__(self, respostas):
        self.respostas = respostas
        self.pedidos = []
        self.headers = {}
        self.fechada = False

    def get(self, url, **opcoes):
        self.pedidos.append((url, opcoes))
        return self.respostas[len(self.pedidos) - 1]

    def close(self):
        self.fechada = True


def _cliente(monkeypatch, respostas):
    sessao = _Sessao(respostas)
    monkeypatch.setattr(http.requests, "Session", lambda: sessao)
    monkeypatch.setattr(
        http, "espaco_do_disco", lambda pasta: (1000 * 1024**3, 800 * 1024**3)
    )
    return http.ClienteSintegra(), sessao


def test_robots_404_permite_um_download_por_arquivo_sem_retry(tmp_path, monkeypatch):
    respostas = [_Resposta(status=404), _Resposta(b"ativo"), _Resposta(b"cancelado")]
    cliente, sessao = _cliente(monkeypatch, respostas)
    for nome, url in URLS_PR.items():
        cliente.baixar(url, tmp_path / nome)
    assert len(sessao.pedidos) == 3
    assert sessao.headers["User-Agent"] == AGENTE
    assert all(p[1]["allow_redirects"] is False for p in sessao.pedidos)
    assert all(r.fechada for r in respostas)


@pytest.mark.parametrize(
    "robots",
    [
        _Resposta(b"User-agent: *\nDisallow: /arquivos/"),
        _Resposta(status=403),
        _Resposta(status=500),
        _Resposta(status=302),
        _Resposta(b"<html>desafio</html>", cabecalhos={"Content-Type": "text/html"}),
    ],
)
def test_robots_proibido_ou_inacessivel_impede_o_arquivo(tmp_path, monkeypatch, robots):
    cliente, sessao = _cliente(monkeypatch, [robots])
    with pytest.raises(ValueError):
        cliente.baixar(URLS_PR["ativos"], tmp_path / "entrada")
    assert len(sessao.pedidos) == 1
    assert not list(tmp_path.iterdir())


def test_crawl_delay_e_respeitado(tmp_path, monkeypatch):
    cliente, sessao = _cliente(
        monkeypatch,
        [
            _Resposta(b"User-agent: *\nCrawl-delay: 5"),
            _Resposta(b"dados"),
        ],
    )
    esperas = []
    monkeypatch.setattr(http.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(http.time, "sleep", esperas.append)
    cliente.baixar(URLS_PR["ativos"], tmp_path / "entrada")
    assert esperas == [5.0]
    assert len(sessao.pedidos) == 2


@pytest.mark.parametrize(
    "resposta",
    [
        _Resposta(status=302, cabecalhos={"Location": "https://example.invalid/login"}),
        _Resposta(status=429),
        _Resposta(status=403),
        _Resposta(cabecalhos={"cf-mitigated": "challenge"}),
        _Resposta(b"<html>desafio</html>", cabecalhos={"Content-Type": "text/html"}),
    ],
)
def test_arquivo_bloqueado_nao_e_repetido_nem_redirecionado(
    tmp_path, monkeypatch, resposta
):
    cliente, sessao = _cliente(monkeypatch, [_Resposta(status=404), resposta])
    with pytest.raises(ValueError):
        cliente.baixar(URLS_PR["ativos"], tmp_path / "entrada")
    assert len(sessao.pedidos) == 2 and resposta.fechada


def test_url_fora_da_lista_nao_faz_rede(tmp_path, monkeypatch):
    cliente, sessao = _cliente(monkeypatch, [])
    with pytest.raises(ValueError):
        cliente.baixar("https://example.invalid/arquivo", tmp_path / "entrada")
    assert not sessao.pedidos


@pytest.mark.parametrize(
    "cabecalhos,conteudo",
    [
        ({"Content-Length": "4"}, b"x"),
        ({"Content-Length": "incorreto"}, b"x"),
        ({"Content-Length": "999999999"}, b"x"),
        ({}, b"acima do limite"),
    ],
)
def test_limite_ou_download_truncado_recusa_arquivo(
    tmp_path, monkeypatch, cabecalhos, conteudo
):
    cliente, _ = _cliente(
        monkeypatch, [_Resposta(status=404), _Resposta(conteudo, cabecalhos=cabecalhos)]
    )
    monkeypatch.setattr(http, "MAX_TEXTO", 5)
    with pytest.raises(ValueError):
        cliente.baixar(URLS_PR["ativos"], tmp_path / "entrada")


def test_cli_valida_todas_as_ufs_antes_de_criar_cliente(monkeypatch, caplog):
    from scripts import carga_sintegra_estadual as carga

    monkeypatch.setattr(
        carga, "ClienteSintegra", lambda: pytest.fail("não pode criar cliente")
    )
    assert carga.main(["--uf", "PR", "--uf", "RS", "--uf", "MG"]) == 1
    assert "robots.txt" in caplog.text
    assert carga.main(["--uf", "MG"]) == 1
    assert "404" in caplog.text


def test_cli_nao_imprime_erro_da_fonte_e_fecha_cliente(tmp_path, monkeypatch, caplog):
    from scripts import carga_sintegra_estadual as carga

    cliente, sessao = _cliente(monkeypatch, [])
    monkeypatch.setattr(carga, "ClienteSintegra", lambda: cliente)
    monkeypatch.setattr(carga, "exigir_versao_do_codigo", lambda: "abc")

    def falhar(*args):
        raise ValueError("CAMPO PROIBIDO")

    monkeypatch.setattr(carga, "carregar_uf", falhar)
    assert carga.main(["--uf", "PR", "--pasta", str(tmp_path)]) == 1
    assert "CAMPO PROIBIDO" not in caplog.text
    assert sessao.fechada


def test_desafio_no_robots_mesmo_com_404_impede_download(tmp_path, monkeypatch):
    cliente, sessao = _cliente(
        monkeypatch,
        [
            _Resposta(status=404, cabecalhos={"cf-mitigated": "challenge"}),
            _Resposta(b"dados"),
        ],
    )
    with pytest.raises(ValueError):
        cliente.baixar(URLS_PR["ativos"], tmp_path / "entrada")
    assert len(sessao.pedidos) == 1


def test_crawl_delay_acima_do_teto_recusa_sem_reduzir_pausa(tmp_path, monkeypatch):
    cliente, sessao = _cliente(
        monkeypatch,
        [_Resposta(b"User-agent: *\nCrawl-delay: 999999"), _Resposta(b"dados")],
    )
    esperas = []
    monkeypatch.setattr(http.time, "sleep", esperas.append)
    with pytest.raises(ValueError, match="Crawl-delay"):
        cliente.baixar(URLS_PR["ativos"], tmp_path / "entrada")
    assert not esperas and len(sessao.pedidos) == 1


def test_prazo_total_esgotado_impede_novo_pedido(tmp_path, monkeypatch):
    agora = [100.0]
    monkeypatch.setattr(http.time, "monotonic", lambda: agora[0])
    cliente, sessao = _cliente(
        monkeypatch, [_Resposta(status=404), _Resposta(b"dados")]
    )
    agora[0] += 3600
    with pytest.raises(TimeoutError):
        cliente.baixar(URLS_PR["ativos"], tmp_path / "entrada")
    assert not sessao.pedidos


def test_prazo_total_interrompe_leitura_em_andamento(tmp_path, monkeypatch):
    agora = [100.0]
    monkeypatch.setattr(http.time, "monotonic", lambda: agora[0])
    monkeypatch.setattr(http, "MAX_DURACAO", 5)
    resposta = _Resposta(b"dados")
    ler = resposta.read1

    def lento(*args, **kwargs):
        agora[0] += 6
        return ler(*args, **kwargs)

    resposta.read1 = lento
    cliente, _ = _cliente(monkeypatch, [_Resposta(status=404), resposta])
    with pytest.raises(TimeoutError):
        cliente.baixar(URLS_PR["ativos"], tmp_path / "entrada")
    assert resposta.fechada


def test_erro_do_socket_e_traduzido_sem_conteudo_da_fonte(tmp_path, monkeypatch):
    from urllib3.exceptions import ProtocolError

    resposta = _Resposta()

    def interrompido(*args, **kwargs):
        raise ProtocolError("CAMPO PROIBIDO")

    resposta.read1 = interrompido
    cliente, _ = _cliente(monkeypatch, [_Resposta(status=404), resposta])
    with pytest.raises(http.requests.RequestException) as erro:
        cliente.baixar(URLS_PR["ativos"], tmp_path / "entrada")
    assert "CAMPO PROIBIDO" not in str(erro.value)
    assert resposta.fechada
