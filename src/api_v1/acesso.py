"""Quem pode chamar a API de leitura: a conta do TickerLab, pelo login do Google.

A interface nova faz o login com o Google no navegador e manda o token (um "ID token", assinado pelo
Google) no cabeçalho `Authorization: Bearer ...`. Aqui ele é conferido: assinatura com as chaves
públicas do Google, feito para o TickerLab (`aud`), emitido pelo Google (`iss`), dentro da validade e
com o e-mail verificado. Depois, a conta precisa já existir (o primeiro login é pelo app) e ter
aceitado os termos atuais.

A chave liga/desliga fica em `src/api_v1/__init__.py`; aqui ela é conferida de novo a cada pedido.
"""

import os
import threading
import time
from collections import deque
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from src.api_v1 import api_v1_ligada
from src.autenticacao import IdentidadeDoGoogle, LoginInvalidoError, ler_identidade
from src.banco.conexao import obter_engine
from src.banco.usuarios import Usuario, buscar_por_google_sub
from src.conformidade import precisa_aceitar_os_termos

VARIAVEL_DO_CLIENT_ID = (
    "TICKERLAB_GOOGLE_CLIENT_ID"  # o mesmo client_id do login do app
)

EMISSORES_DO_GOOGLE = ["https://accounts.google.com", "accounts.google.com"]
ENDERECO_DAS_CHAVES = "https://www.googleapis.com/oauth2/v3/certs"
VALIDADE_DAS_CHAVES = 6 * 3600  # segundos: o Google troca as chaves de tempos em tempos
FOLGA_DO_RELOGIO = (
    60  # segundos de diferença aceitos entre o nosso relógio e o do Google
)
ALGORITMOS = ["RS256"]  # o único que o Google usa; nunca aceitar "none" ou HS256
PEDIDOS_POR_MINUTO = 60


class TokenInvalidoError(ValueError):
    """O token não prova quem é a pessoa (assinatura, validade, destino ou e-mail)."""


def agora() -> int:
    """Segundos desde 1970 (os testes trocam esta função)."""
    return int(time.time())


def verificar_token(
    token: str, chaves: KeySet, client_id: str, momento: int
) -> IdentidadeDoGoogle:
    """A identidade do Google que o token prova, ou `TokenInvalidoError`."""
    try:
        decodificado = jwt.decode(token, chaves, algorithms=ALGORITMOS)
        regras = jwt.JWTClaimsRegistry(
            now=momento,
            leeway=FOLGA_DO_RELOGIO,
            iss={"essential": True, "values": EMISSORES_DO_GOOGLE},
            aud={"essential": True, "value": client_id},
            exp={"essential": True},
            sub={"essential": True},
        )
        regras.validate(decodificado.claims)
    except (JoseError, ValueError) as erro:
        raise TokenInvalidoError(f"Token recusado: {type(erro).__name__}.") from erro
    if decodificado.claims.get("email_verified") is not True:
        raise TokenInvalidoError("O Google não confirmou o e-mail desta conta.")
    try:
        return ler_identidade(decodificado.claims)
    except LoginInvalidoError as erro:
        raise TokenInvalidoError(str(erro)) from erro


class LimiteDePedidos:
    """No máximo `por_minuto` pedidos por conta numa janela de 60 segundos.

    Fica na memória do processo: com um processo só da API (como hoje), vale para todos os pedidos.
    """

    def __init__(self, por_minuto: int = PEDIDOS_POR_MINUTO) -> None:
        self.por_minuto = por_minuto
        self._pedidos: dict[str, deque[float]] = {}
        self._trava = threading.Lock()

    def permitir(self, conta: str, momento: float) -> bool:
        with self._trava:
            fila = self._pedidos.setdefault(conta, deque())
            while fila and fila[0] <= momento - 60:
                fila.popleft()
            if len(fila) >= self.por_minuto:
                return False
            fila.append(momento)
            return True

    def zerar(self) -> None:
        with self._trava:
            self._pedidos.clear()


LIMITE = LimiteDePedidos()

_chaves_em_cache: tuple[int, KeySet] | None = None


def chaves_do_google() -> KeySet:
    """As chaves públicas do Google, baixadas no máximo a cada `VALIDADE_DAS_CHAVES`."""
    global _chaves_em_cache
    if _chaves_em_cache is None or agora() - _chaves_em_cache[0] > VALIDADE_DAS_CHAVES:
        try:
            resposta = httpx.get(ENDERECO_DAS_CHAVES, timeout=10)
            resposta.raise_for_status()
            _chaves_em_cache = (agora(), KeySet.import_key_set(resposta.json()))
        except (httpx.HTTPError, ValueError) as erro:
            raise HTTPException(
                status_code=503, detail="Não deu para conferir o login agora."
            ) from erro
    return _chaves_em_cache[1]


def exigir_api_ligada() -> None:
    if not api_v1_ligada():
        raise HTTPException(status_code=404, detail="Not Found")


def _token_do_cabecalho(authorization: str | None) -> str:
    tipo, _, token = (authorization or "").partition(" ")
    if tipo.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Faça o login com o Google e mande o token (Authorization: Bearer).",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


def conta_logada(
    chaves: Annotated[KeySet, Depends(chaves_do_google)],
    authorization: Annotated[str | None, Header()] = None,
) -> Usuario:
    """A conta do TickerLab de quem chamou, ou o erro HTTP certo (401, 403, 429 ou 503)."""
    token = _token_do_cabecalho(authorization)
    client_id = os.environ.get(VARIAVEL_DO_CLIENT_ID, "").strip()
    if not client_id:
        raise HTTPException(status_code=503, detail="Login da API não configurado.")
    try:
        identidade = verificar_token(token, chaves, client_id, agora())
    except TokenInvalidoError as erro:
        raise HTTPException(status_code=401, detail=str(erro)) from erro
    with obter_engine().connect() as conexao:
        usuario = buscar_por_google_sub(conexao, identidade.sub)
    if usuario is None:
        raise HTTPException(
            status_code=401, detail="Conta não encontrada: entre uma vez pelo app."
        )
    if precisa_aceitar_os_termos(usuario):
        raise HTTPException(
            status_code=403, detail="Aceite os termos atuais no app para continuar."
        )
    if not LIMITE.permitir(str(usuario.id), agora()):
        raise HTTPException(status_code=429, detail="Muitos pedidos: espere um minuto.")
    return usuario
