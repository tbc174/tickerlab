"""O coletor renderiza sozinho a página que veio quase vazia e cheia de script (na linha de base de
26/11/2026, páginas montadas por JavaScript vieram com 4 e 21 caracteres de texto e foram contadas como
lidas). O renderizador é o mesmo do `renderizar=true` (Crawl4AI, depois o Firecrawl com porteiro e teto);
aqui ele é dublê. Cada tentativa de renderizar fica gravada na memória, para a medição."""

from pathlib import Path

import pytest

from pesquisa.memoria import Memoria
from pesquisa.pesquisador import Pesquisador
from pesquisa.renderizacao import BloqueioNaRenderizacao, EnvioBarrado
from tests.ajudantes_da_pesquisa import ClienteFalso, html_com_links

SITE = "https://dados.exemplo.gov.br"
CASCA = (
    b"<html><head><title>App</title><script src='/app.js'></script></head>"
    b"<body><div id='root'></div><noscript>Ative o JavaScript</noscript></body></html>"
)
MONTADA = html_com_links(
    "Painel", [("/dados.csv", "dados")], texto="Tabela de entidades " * 30
)


class _Renderizador:
    def __init__(self, resultado: bytes | Exception = MONTADA):
        self.resultado = resultado
        self.chamadas: list[str] = []

    def __call__(self, url: str) -> tuple[str, bytes]:
        self.chamadas.append(url)
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return url, self.resultado


def _pesquisador(
    tmp_path: Path, paginas: dict, renderizador: _Renderizador | None
) -> Pesquisador:
    pesquisador = Pesquisador(
        tmp_path / "d", ClienteFalso(paginas), renderizador=renderizador
    )
    assert pesquisador.iniciar_rodada("a Conab publica o painel de safras")["ok"]
    return pesquisador


def _eventos(tmp_path: Path) -> list[dict]:
    return Memoria(tmp_path / "d" / "memoria.sqlite").renderizacoes()


def test_casca_de_javascript_e_renderizada_sozinha(tmp_path: Path):
    renderizador = _Renderizador()
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/painel": CASCA}, renderizador)
    resposta = pesquisador.buscar_pagina(f"{SITE}/painel")
    assert resposta["ok"] is True and resposta["renderizada_sozinha"] is True
    assert resposta["titulo"] == "Painel"
    assert "Tabela de entidades" in resposta["texto"]  # type: ignore[operator]
    assert renderizador.chamadas == [f"{SITE}/painel"]
    assert pesquisador.estado()["buscas"] == "1/12"  # type: ignore[index]
    (evento,) = _eventos(tmp_path)
    assert evento["url"] == f"{SITE}/painel"
    assert (evento["sozinha"], evento["resultado"], evento["erro"]) == (1, "ok", None)


def test_a_memoria_guarda_a_pagina_renderizada(tmp_path: Path):
    renderizador = _Renderizador()
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/painel": CASCA}, renderizador)
    pesquisador.buscar_pagina(f"{SITE}/painel")
    de_novo = pesquisador.buscar_pagina(f"{SITE}/painel")
    assert de_novo["ja_visto"] is True and de_novo["titulo"] == "Painel"
    assert len(renderizador.chamadas) == 1


@pytest.mark.parametrize(
    "pagina",
    [
        html_com_links("Cheia", [], texto="Conteúdo de verdade " * 30),
        b"<html><body><p>vazia e sem script</p></body></html>",
    ],
)
def test_pagina_com_texto_ou_sem_script_nao_e_renderizada(
    tmp_path: Path, pagina: bytes
):
    renderizador = _Renderizador()
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/a": pagina}, renderizador)
    resposta = pesquisador.buscar_pagina(f"{SITE}/a")
    assert resposta["ok"] is True and "renderizada_sozinha" not in resposta
    assert renderizador.chamadas == [] and _eventos(tmp_path) == []


def test_sem_renderizador_a_casca_volta_como_veio(tmp_path: Path):
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/painel": CASCA}, None)
    resposta = pesquisador.buscar_pagina(f"{SITE}/painel")
    assert resposta["ok"] is True and resposta["titulo"] == "App"
    assert "renderizada_sozinha" not in resposta


@pytest.mark.parametrize(
    "erro, resultado",
    [
        (RuntimeError("Executable doesn't exist"), "falhou"),
        (BloqueioNaRenderizacao("a página respondeu HTTP 403"), "bloqueio"),
        (EnvioBarrado("o endereço tem um termo da lista de barrados"), "barrado"),
    ],
)
def test_renderizacao_que_falha_devolve_a_casca_e_grava_o_motivo(
    tmp_path: Path, erro: Exception, resultado: str
):
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/painel": CASCA}, _Renderizador(erro))
    resposta = pesquisador.buscar_pagina(f"{SITE}/painel")
    assert resposta["ok"] is True and resposta["titulo"] == "App"
    assert resposta["renderizada_sozinha"] is False
    assert pesquisador.memoria.negativo_valido(f"{SITE}/painel") is None
    (evento,) = _eventos(tmp_path)
    # Só o tipo do erro: a mensagem pode trazer texto de terceiro.
    assert (evento["sozinha"], evento["resultado"], evento["erro"]) == (
        1,
        resultado,
        type(erro).__name__,
    )


def test_renderizar_pedido_tambem_fica_gravado(tmp_path: Path):
    pesquisador = _pesquisador(tmp_path, {}, _Renderizador(RuntimeError("x")))
    resposta = pesquisador.buscar_pagina(f"{SITE}/app", renderizar=True)
    assert resposta["ok"] is False
    (evento,) = _eventos(tmp_path)
    assert (evento["sozinha"], evento["resultado"]) == (0, "falhou")


def test_renderizar_pedido_que_deu_certo_fica_gravado(tmp_path: Path):
    pesquisador = _pesquisador(tmp_path, {}, _Renderizador())
    assert pesquisador.buscar_pagina(f"{SITE}/app", renderizar=True)["ok"] is True
    (evento,) = _eventos(tmp_path)
    assert (evento["sozinha"], evento["resultado"]) == (0, "ok")


def test_robots_que_proibe_impede_ler_e_renderizar(tmp_path: Path):
    renderizador = _Renderizador()
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/privado/x": CASCA}, renderizador)
    assert pesquisador.buscar_pagina(f"{SITE}/privado/x")["ok"] is False
    assert renderizador.chamadas == []


def test_estado_conta_as_renderizacoes(tmp_path: Path):
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/painel": CASCA}, _Renderizador())
    pesquisador.buscar_pagina(f"{SITE}/painel")
    assert pesquisador.estado()["memoria"]["renderizacao"] == 1  # type: ignore[index]


# --- achados das revisões do PR 2 (b339160) --------------------------------------------------------


@pytest.mark.parametrize(
    "desafio",
    [
        b"<html><head><script src='/challenge.js'></script></head><body><noscript>verifique o navegador</noscript></body></html>",
        b"<html><head><title>Just a moment...</title><script>x()</script></head><body></body></html>",
        b"<html><body><script src='https://x.awswaf.com/c.js'></script></body></html>",
        b"<html><body><div class='g-recaptcha'></div><script>r()</script></body></html>",
        b"<html><body><h1>Request Rejected</h1><script>z()</script></body></html>",
        # F5, Sucuri, Akamai, Kasada e Radware: só um script externo e um noscript genérico (P2 da re-revisão)
        b"<html><head><script src='/TSPD/08a1?type=9'></script></head><body><noscript>x</noscript></body></html>",
        b"<html><body><script>var bobcmn = 1;</script></body></html>",
        b"<html><body><script src='/sucuri_cloudproxy.js'></script></body></html>",
        b"<html><body><script src='/bm-verify/a.js'></script></body></html>",
        b"<html><body><script>document.cookie='_abck=1'</script></body></html>",
        b"<html><body><script src='/149e9513-01fa-4fb0-aad4-566afd725d1b/2d206a39/ips.js?KPSDK'></script></body></html>",
        b"<html><body><script src='https://perfdrive.com/a.js'></script></body></html>",
        "<html><body><h1>NÃO SOU UM ROBÔ</h1><script>q()</script></body></html>".encode(),
    ],
)
def test_pagina_de_desafio_anti_robo_nao_e_renderizada_sozinha(
    tmp_path: Path, desafio: bytes
):
    """P1 da revisão de segurança: desafio servido com 2xx não pode ser resolvido por um navegador."""
    renderizador = _Renderizador()
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/painel": desafio}, renderizador)
    resposta = pesquisador.buscar_pagina(f"{SITE}/painel")
    assert resposta["ok"] is True and resposta["renderizada_sozinha"] is False
    assert renderizador.chamadas == []
    assert "desafio" in resposta["aviso"]  # type: ignore[operator]
    (evento,) = _eventos(tmp_path)
    assert evento["resultado"] == "desafio"


@pytest.mark.parametrize("status", [403, 429])
def test_host_com_bloqueio_lembrado_nao_e_renderizado_sozinho(
    tmp_path: Path, status: int
):
    """P1 da revisão cruzada: outro caminho do mesmo host já bloqueou o bot."""
    renderizador = _Renderizador()
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/painel": CASCA}, renderizador)
    pesquisador.memoria.anotar_negativo(
        f"{SITE}/api", f"a fonte respondeu HTTP {status}", status, "r0"
    )
    resposta = pesquisador.buscar_pagina(f"{SITE}/painel")
    assert resposta["ok"] is True and resposta["renderizada_sozinha"] is False
    assert renderizador.chamadas == []
    (evento,) = _eventos(tmp_path)
    assert (evento["resultado"], evento["erro"]) == ("pulada", "bloqueio no site")


def test_robots_bloqueado_impede_renderizar_sozinho(tmp_path: Path):
    from base.arquivo.coleta import Resposta
    from tests.ajudantes_da_pesquisa import erro_http

    class _RobotsBloqueado(ClienteFalso):
        def ler(self, url: str) -> Resposta:
            if url.endswith("/robots.txt"):
                raise erro_http(403)
            return super().ler(url)

    renderizador = _Renderizador()
    pesquisador = Pesquisador(
        tmp_path / "d",
        _RobotsBloqueado({f"{SITE}/painel": CASCA}),
        renderizador=renderizador,
    )
    pesquisador.iniciar_rodada("h")
    resposta = pesquisador.buscar_pagina(f"{SITE}/painel")
    assert resposta["ok"] is True and renderizador.chamadas == []


def test_bloqueio_recebido_ao_renderizar_vale_para_o_host(tmp_path: Path):
    """O bloqueio que o renderizador recebe fica lembrado para o host: a próxima casca e o mapa param."""
    renderizador = _Renderizador(BloqueioNaRenderizacao("a página respondeu HTTP 403"))
    paginas = {f"{SITE}/painel": CASCA, f"{SITE}/outro": CASCA}
    pesquisador = _pesquisador(tmp_path, paginas, renderizador)
    pesquisador.buscar_pagina(f"{SITE}/painel")
    pesquisador.buscar_pagina(f"{SITE}/outro")
    assert renderizador.chamadas == [f"{SITE}/painel"]
    assert pesquisador.memoria.bloqueio_valido_no_site("dados.exemplo.gov.br")


def test_renderizar_pedido_em_host_com_bloqueio_lembrado_recusa(tmp_path: Path):
    renderizador = _Renderizador()
    pesquisador = _pesquisador(tmp_path, {}, renderizador)
    pesquisador.memoria.anotar_negativo(
        f"{SITE}/api", "a fonte respondeu HTTP 403", 403, "r0"
    )
    resposta = pesquisador.buscar_pagina(f"{SITE}/app", renderizar=True)
    assert resposta["ok"] is False and "não se contorna" in resposta["motivo"]  # type: ignore[operator]
    assert renderizador.chamadas == []


def test_casca_com_meta_robots_ainda_e_renderizada(tmp_path: Path):
    casca = CASCA.replace(b"<head>", b"<head><meta name='robots' content='index'>")
    renderizador = _Renderizador()
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/painel": casca}, renderizador)
    assert pesquisador.buscar_pagina(f"{SITE}/painel")["renderizada_sozinha"] is True


def test_desafio_detectado_vale_para_o_host_e_barra_o_renderizar_pedido(tmp_path: Path):
    """P1 da re-revisão de segurança (82265fa): o desafio que o bot reconhece na casca vira bloqueio do
    host. Outro endereço do mesmo site com `renderizar=true` não pode passar por ele no navegador."""
    desafio = (
        b"<html><body><script src='https://x.awswaf.com/c.js'></script></body></html>"
    )
    renderizador = _Renderizador()
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/painel": desafio}, renderizador)
    pesquisador.buscar_pagina(f"{SITE}/painel")
    resposta = pesquisador.buscar_pagina(f"{SITE}/outro", renderizar=True)
    assert resposta["ok"] is False and "não se contorna" in resposta["motivo"]  # type: ignore[operator]
    assert renderizador.chamadas == []
    assert pesquisador.memoria.bloqueio_valido_no_site("dados.exemplo.gov.br")


def test_desafio_detectado_barra_o_mapa_do_site(tmp_path: Path):
    desafio = (
        b"<html><body><div class='g-recaptcha'></div><script>r()</script></body></html>"
    )
    pesquisador = _pesquisador(tmp_path, {f"{SITE}/painel": desafio}, _Renderizador())
    pesquisador.buscar_pagina(f"{SITE}/painel")
    negativo = pesquisador.memoria.bloqueio_valido_no_site("dados.exemplo.gov.br")
    assert negativo is not None and "desafio" in negativo.motivo
