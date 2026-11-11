"""A página `/autorizar`: onde o analista cola a chave pessoal dele para ligar o Claude ou o ChatGPT.

Cuidados (condição 3 do aceite da linha 570):

- diz **qual IA** pede o acesso, tirada da lista fechada de endereços de volta (nunca do nome que o
  cliente mandou no registro), e o aviso "só continue se foi você que começou esta ligação agora";
- a chave só vai no corpo do POST, nunca na URL; o pedido selado na URL não leva chave nenhuma;
- não abre dentro de outra página (`frame-ancestors 'none'` e `X-Frame-Options`), não fica em cache
  (`no-store`) e não manda `Referer` para fora do conector;
- CSRF por cookie duplicado (`__Host-`, HttpOnly, Secure, SameSite=Strict) conferido no POST;
- erro de chave é sempre o mesmo texto, e cada falha conta no limite por IP (o IP de verdade atrás do
  túnel, `limite.py`): passou do limite, 429 até a janela andar.
"""

import html
import secrets
from dataclasses import dataclass

import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from conector_remoto.limite import LimitePorIp, Rede, ip_do_pedido
from conector_remoto.oauth import (
    VALIDADE_DO_PEDIDO_S,
    PedidoDeAutorizacao,
    ProvedorOAuth,
)

CAMINHO = "/autorizar"
COOKIE_DO_CSRF = "__Host-tickerlab-csrf"
BYTES_DO_CSRF = 32
FALHAS_POR_JANELA = 20
JANELA_DO_LIMITE_S = 15 * 60
MAXIMO_DO_CORPO = 16_384

CABECALHOS_DA_PAGINA = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; "
        "form-action 'self' https://claude.ai https://claude.com https://chatgpt.com; "
        "frame-ancestors 'none'; base-uri 'none'"
    ),
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    # `same-origin`, e não `no-referrer`: com `no-referrer` o navegador manda `Origin: null` no POST do
    # formulário (Fetch, "append a request Origin header"), e a proteção de Origin recusaria o analista
    "Referrer-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
}

ERRO_DA_CHAVE = (
    "A chave não foi aceita. Confira se colou a chave inteira (começa com tld_) e se ela não foi "
    "revogada; na dúvida, peça uma nova a quem administra o TickerLab na sua empresa."
)
ERRO_DA_API = "O TickerLab não respondeu agora. Tente de novo em alguns instantes."
ERRO_DO_PEDIDO = (
    "Este pedido de ligação venceu ou não é válido. Volte ao Claude ou ao ChatGPT e comece a ligação "
    "de novo."
)
ERRO_DO_CSRF = (
    "A página ficou velha. Volte ao Claude ou ao ChatGPT e comece a ligação de novo."
)
ERRO_DO_LIMITE = "Tentativas demais deste endereço. Espere 15 minutos e tente de novo."

ESTILO = """
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#f6f7f9;color:#1b1f24;
margin:0;padding:24px 16px}
main{max-width:480px;margin:0 auto;background:#fff;border:1px solid #dde1e6;border-radius:12px;
padding:24px}
h1{font-size:1.25rem;margin:0 0 12px}
p{line-height:1.5}
.aviso{background:#fff6e0;border:1px solid #f0c36d;border-radius:8px;padding:12px}
.erro{background:#fdecec;border:1px solid #e5a3a3;border-radius:8px;padding:12px}
label{display:block;font-weight:600;margin:16px 0 6px}
input[type=password]{width:100%;box-sizing:border-box;padding:10px;font-size:1rem;
border:1px solid #b9c0c8;border-radius:8px}
.botoes{display:flex;gap:12px;margin-top:16px}
button{padding:10px 16px;font-size:1rem;border-radius:8px;border:1px solid #1b1f24;cursor:pointer}
.ligar{background:#1b1f24;color:#fff}
.cancelar{background:#fff;color:#1b1f24}
small{color:#5b6570}
"""


def _pagina(titulo: str, corpo: str, status: int) -> HTMLResponse:
    documento = (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex">'
        f"<title>{html.escape(titulo)}</title><style>{ESTILO}</style></head>"
        f"<body><main>{corpo}</main></body></html>"
    )
    return HTMLResponse(documento, status_code=status, headers=CABECALHOS_DA_PAGINA)


def _pagina_de_erro(mensagem: str, status: int) -> HTMLResponse:
    corpo = f'<h1>TickerLab</h1><p class="erro">{html.escape(mensagem)}</p>'
    return _pagina("TickerLab", corpo, status)


def _formulario(pedido: PedidoDeAutorizacao, csrf: str, erro: str | None) -> str:
    ia = html.escape(pedido.ia)
    host = html.escape(pedido.host_de_volta)
    aviso_de_erro = f'<p class="erro">{html.escape(erro)}</p>' if erro else ""
    return (
        f"<h1>Ligar o {ia} ao TickerLab</h1>"
        f'<p class="aviso"><strong>Só continue se foi você que começou esta ligação agora</strong>, '
        f"no {ia}. Se você não pediu isto, feche esta página.</p>"
        f"<p>O {ia} (<code>{host}</code>) pede para consultar os dados do TickerLab em seu nome. "
        "Cole abaixo a <strong>sua</strong> chave pessoal: cada pessoa usa a própria chave, e tudo o "
        "que o assistente consultar conta nela.</p>"
        f"{aviso_de_erro}"
        f'<form method="post" action="{CAMINHO}">'
        f'<input type="hidden" name="pedido" value="{html.escape(pedido.selado)}">'
        f'<input type="hidden" name="csrf" value="{html.escape(csrf)}">'
        '<label for="chave">Sua chave do TickerLab</label>'
        '<input type="password" id="chave" name="chave" autocomplete="off" spellcheck="false" '
        'placeholder="tld_..." required>'
        '<div class="botoes">'
        '<button class="ligar" type="submit" name="acao" value="ligar">Ligar</button>'
        '<button class="cancelar" type="submit" name="acao" value="cancelar" formnovalidate>'
        "Cancelar</button></div>"
        "</form>"
        "<p><small>A chave não fica no assistente: ele recebe um acesso que vence e que para de "
        "funcionar quando a chave é revogada. Nada aqui é recomendação de investimento.</small></p>"
    )


@dataclass
class PaginaDeAutorizacao:
    """Os dois lados da página: GET mostra o formulário, POST confere a chave e devolve o código."""

    provedor: ProvedorOAuth
    limite: LimitePorIp
    redes_confiaveis: tuple[Rede, ...]

    def _mostrar(
        self, pedido: PedidoDeAutorizacao, csrf: str, erro: str | None, status: int
    ) -> HTMLResponse:
        resposta = _pagina(
            "Ligar ao TickerLab", _formulario(pedido, csrf, erro), status
        )
        resposta.set_cookie(
            COOKIE_DO_CSRF,
            csrf,
            max_age=VALIDADE_DO_PEDIDO_S,
            path="/",
            secure=True,
            httponly=True,
            samesite="strict",
        )
        return resposta

    async def mostrar(self, pedido_http: Request) -> Response:
        """GET: o formulário, com um CSRF novo."""
        pedido = self.provedor.abrir_pedido(pedido_http.query_params.get("pedido", ""))
        if pedido is None:
            return _pagina_de_erro(ERRO_DO_PEDIDO, 400)
        return self._mostrar(pedido, secrets.token_urlsafe(BYTES_DO_CSRF), None, 200)

    async def receber(self, pedido_http: Request) -> Response:
        """POST: confere o limite, o pedido, o CSRF e a chave; certo, volta à IA com o código."""
        ip = ip_do_pedido(pedido_http, self.redes_confiaveis)
        if self.limite.bloqueado(ip):
            return _pagina_de_erro(ERRO_DO_LIMITE, 429)
        formulario = await pedido_http.form()
        campos = {
            nome: valor
            for nome in ("pedido", "csrf", "chave", "acao")
            if isinstance(valor := formulario.get(nome), str)
        }
        pedido = self.provedor.abrir_pedido(campos.get("pedido", ""))
        if pedido is None:
            self.limite.falhou(ip)
            return _pagina_de_erro(ERRO_DO_PEDIDO, 400)
        csrf = pedido_http.cookies.get(COOKIE_DO_CSRF, "")
        if not csrf or not secrets.compare_digest(
            csrf.encode(), campos.get("csrf", "").encode()
        ):
            self.limite.falhou(ip)
            return _pagina_de_erro(ERRO_DO_CSRF, 403)
        if campos.get("acao") == "cancelar":
            return self._voltar(self.provedor.endereco_de_recusa(pedido))
        chave = campos.get("chave", "").strip()
        try:
            aceita = await self.provedor.chave_aceita(chave)
        except httpx.HTTPError:
            return self._mostrar(pedido, csrf, ERRO_DA_API, 503)
        if not aceita:
            self.limite.falhou(ip)
            return self._mostrar(pedido, csrf, ERRO_DA_CHAVE, 401)
        return self._voltar(self.provedor.emitir_codigo(pedido, chave))

    @staticmethod
    def _voltar(endereco: str) -> Response:
        resposta = RedirectResponse(
            endereco, status_code=303, headers=CABECALHOS_DA_PAGINA
        )
        resposta.delete_cookie(
            COOKIE_DO_CSRF, path="/", secure=True, httponly=True, samesite="strict"
        )
        return resposta


def nova_pagina(
    provedor: ProvedorOAuth, redes_confiaveis: tuple[Rede, ...]
) -> PaginaDeAutorizacao:
    """A página com o limite padrão: 20 falhas por IP a cada 15 minutos."""
    return PaginaDeAutorizacao(
        provedor, LimitePorIp(FALHAS_POR_JANELA, JANELA_DO_LIMITE_S), redes_confiaveis
    )
