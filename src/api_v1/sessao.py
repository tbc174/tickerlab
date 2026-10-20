"""O cookie da sessão do app novo e a proteção contra pedidos vindos de outros sites (CSRF).

O token da sessão (src/banco/sessoes.py) vai num cookie `__Host-`: o navegador só o aceita com
`Secure`, `Path=/` e sem `Domain`, então ele fica preso ao endereço do app e só viaja por HTTPS.
`HttpOnly` deixa o token fora do alcance do JavaScript da página (um script injetado não o lê) e
`SameSite=Lax` impede que outro site o mande em POSTs.

Como o navegador manda o cookie sozinho, todo pedido que muda algo e chega com ele precisa provar que
saiu do próprio app: o cabeçalho `X-TickerLab-Pedido: 1` (um site de fora só conseguiria pô-lo com a
permissão de CORS, que a API não dá) e a origem (`Origin`) igual ao endereço do app. A API fica no
mesmo endereço do app (`/api/v1`), então nada disso atrapalha o app.
"""

from urllib.parse import urlsplit

from fastapi import Request, Response

from src.banco.sessoes import DURACAO

NOME_DO_COOKIE = "__Host-tl_sessao"
CABECALHO_DO_PEDIDO = "X-TickerLab-Pedido"
METODOS_QUE_SO_LEEM = frozenset({"GET", "HEAD", "OPTIONS"})


def por_o_cookie(resposta: Response, token: str) -> None:
    resposta.set_cookie(
        NOME_DO_COOKIE,
        token,
        max_age=int(DURACAO.total_seconds()),
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def tirar_o_cookie(resposta: Response) -> None:
    resposta.delete_cookie(
        NOME_DO_COOKIE, path="/", secure=True, httponly=True, samesite="lax"
    )


def token_do_cookie(pedido: Request) -> str | None:
    return (pedido.cookies.get(NOME_DO_COOKIE) or "").strip() or None


def _endereco_publico(pedido: Request) -> str:
    # só o Host: a API não fica atrás do nginx (o túnel da Cloudflare entrega o endereço que o navegador
    # usou). O X-Forwarded-Host não vale: quem chega direto à API poderia mandar o que quisesse nele
    return pedido.headers.get("host", "").lower()


def pedido_do_proprio_site(pedido: Request) -> bool:
    """O pedido tem o cabeçalho do app e a origem do próprio endereço?"""
    if pedido.headers.get(CABECALHO_DO_PEDIDO) != "1":
        return False
    origem = urlsplit(pedido.headers.get("origin", "")).netloc.lower()
    return bool(origem) and origem == _endereco_publico(pedido)


def precisa_provar_a_origem(pedido: Request) -> bool:
    """Pedido que muda algo e chega com o cookie da sessão."""
    return (
        pedido.method not in METODOS_QUE_SO_LEEM and token_do_cookie(pedido) is not None
    )
