"""Compressão gzip das respostas da API externa (linha 848).

O `financials` de uma empresa chega a 1,2 MB de JSON; em gzip cai para uma fração. Só quem manda
`Accept-Encoding: gzip` recebe comprimido, o corpo descomprimido é o mesmo e o contrato não muda.
Fica restrito a `/data/` (e `/api/data/`): as demais rotas do app não mudam. A API externa autentica por
chave no cabeçalho, sem cookie nem texto de quem pede refletido na resposta, então a compressão não abre
a brecha de tipo BREACH.
"""

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

TAMANHO_MINIMO = 1024  # abaixo disso o gzip não compensa
NIVEL = 5  # equilíbrio entre CPU e tamanho (o padrão do Starlette é 9)
PREFIXOS = ("/data/", "/api/data/")


class GzipSoNaApiExterna(GZipMiddleware):
    """O `GZipMiddleware` do Starlette, ligado só nos caminhos da API externa."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app, minimum_size=TAMANHO_MINIMO, compresslevel=NIVEL)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith(PREFIXOS):
            await super().__call__(scope, receive, send)
        else:
            await self.app(scope, receive, send)
