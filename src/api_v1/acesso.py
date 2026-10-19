"""Quem pode chamar a API de leitura: a conta do TickerLab, pelo login do Google.

A interface nova faz o login com o Google no navegador e manda o token (um "ID token", assinado pelo
Google) no cabeçalho `Authorization: Bearer ...`. Aqui ele é conferido: assinatura com as chaves
públicas do Google, feito para o TickerLab (`aud`), emitido pelo Google (`iss`), dentro da validade e
com o e-mail verificado. Depois, a conta precisa já existir (o primeiro login é pelo app) e ter
aceitado os termos atuais (menos para baixar os próprios dados: LGPD). Por último, o plano da conta precisa abrir a página da rota (o contrato da
página em src/paginas.py diz qual é; a regra é a mesma do Streamlit, ADR 0062).

A chave liga/desliga fica em `src/api_v1/__init__.py`; aqui ela é conferida de novo a cada pedido.
"""

import os
import threading
import time
from collections import deque
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, Request
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from src.api_v1 import api_v1_ligada
from src.autenticacao import IdentidadeDoGoogle, LoginInvalidoError, ler_identidade
from src.banco.conexao import obter_engine
from src.banco.usuarios import Usuario, buscar_por_google_sub
from src.conformidade import precisa_aceitar_os_termos
from src.paginas import PREFIXO_DA_API, motivo_da_pagina, pagina_da_rota

# o motivo de um 401 ou 403, para a tela mostrar o caminho certo (entrar de novo, entrar pelo app
# uma vez ou aceitar os termos): "sem-token", "token-invalido", "conta-nova" ou "termos"
CABECALHO_DO_MOTIVO = "X-TickerLab-Motivo"


def _recusa(status: int, detalhe: str, motivo: str) -> HTTPException:
    cabecalhos = {CABECALHO_DO_MOTIVO: motivo}
    if status == 401:
        cabecalhos["WWW-Authenticate"] = "Bearer"
    return HTTPException(status_code=status, detail=detalhe, headers=cabecalhos)


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
MAXIMO_DE_CHAVES = (
    10_000  # contas ou IPs lembrados antes de esquecer quem parou de pedir
)


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

    def __init__(
        self,
        por_minuto: int = PEDIDOS_POR_MINUTO,
        maximo_de_chaves: int = MAXIMO_DE_CHAVES,
    ) -> None:
        self.por_minuto = por_minuto
        self.maximo_de_chaves = maximo_de_chaves
        self._pedidos: dict[str, deque[float]] = {}
        self._trava = threading.Lock()

    def _esquecer_quem_parou(self, momento: float) -> None:
        """Tira as chaves sem pedido no último minuto (com chave por IP, a lista não para de crescer)."""
        paradas = [
            c for c, f in self._pedidos.items() if not f or f[-1] <= momento - 60
        ]
        for chave in paradas:
            del self._pedidos[chave]

    def chaves(self) -> int:
        with self._trava:
            return len(self._pedidos)

    def permitir(self, conta: str, momento: float) -> bool:
        with self._trava:
            if (
                conta not in self._pedidos
                and len(self._pedidos) >= self.maximo_de_chaves
            ):
                self._esquecer_quem_parou(momento)
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
        raise _recusa(
            401,
            "Faça o login com o Google e mande o token (Authorization: Bearer).",
            "sem-token",
        )
    return token.strip()


def identidade_logada(
    chaves: Annotated[KeySet, Depends(chaves_do_google)],
    authorization: Annotated[str | None, Header()] = None,
) -> IdentidadeDoGoogle:
    """Quem o token do Google prova ser (ainda sem procurar a conta), ou 401 ou 503."""
    token = _token_do_cabecalho(authorization)
    client_id = os.environ.get(VARIAVEL_DO_CLIENT_ID, "").strip()
    if not client_id:
        raise HTTPException(status_code=503, detail="Login da API não configurado.")
    try:
        return verificar_token(token, chaves, client_id, agora())
    except TokenInvalidoError as erro:
        raise _recusa(401, str(erro), "token-invalido") from erro


def conta_sem_o_aceite(
    identidade: Annotated[IdentidadeDoGoogle, Depends(identidade_logada)],
) -> Usuario:
    """A conta de quem chamou, mesmo sem os termos atuais aceitos (só a rota do aceite usa)."""
    with obter_engine().connect() as conexao:
        usuario = buscar_por_google_sub(conexao, identidade.sub)
    if usuario is None:
        raise _recusa(401, "Conta não encontrada: entre de novo.", "conta-nova")
    if not LIMITE.permitir(str(usuario.id), agora()):
        raise HTTPException(status_code=429, detail="Muitos pedidos: espere um minuto.")
    return usuario


# rotas dos direitos da LGPD (art. 18): valem sem o aceite dos termos atuais. Quem não quer
# aceitar termos novos ainda baixa os próprios dados (achado 6c da auditoria do Codex, 17/10/2026)
ROTAS_SEM_O_ACEITE = frozenset({"/v1/meus-dados"})


def conta_logada(
    request: Request,
    usuario: Annotated[Usuario, Depends(conta_sem_o_aceite)],
) -> Usuario:
    """A conta do TickerLab de quem chamou, ou o erro HTTP certo (401, 403, 429 ou 503)."""
    rota: str = request.scope["route"].path
    sem_o_aceite = rota.removeprefix(PREFIXO_DA_API) in ROTAS_SEM_O_ACEITE
    if precisa_aceitar_os_termos(usuario) and not sem_o_aceite:
        raise _recusa(403, "Aceite os termos atuais para continuar.", "termos")
    return usuario


# rotas da v1 que falam só da própria conta, não de uma página: pedem login, mas nenhum plano
ROTAS_DA_CONTA = frozenset(
    {
        "/v1/eu",
        "/v1/revogar-link",
        "/v1/salvar-simulacao",
        "/v1/apagar-simulacao",
        "/v1/meus-dados",
        "/v1/pagamento-da-assinatura",
        "/v1/portal-da-assinatura",
        # molde B: pede login; o plano só decide se as seções da base vêm trancadas (ainda sem a
        # página "Busca por CNPJ", que chega no PR 3 do plano e leva a rota para o contrato dela)
        "/v1/busca-por-cnpj",
    }
)


def conta_com_acesso(
    request: Request, conta: Annotated[Usuario, Depends(conta_logada)]
) -> Usuario:
    """A conta logada, se o plano dela abre a página da rota; senão 403 com o motivo.

    Fecha por padrão: rota que não é da conta nem tem contrato de página responde 500 (e o teste
    `test_toda_rota_da_v1_tem_contrato_ou_e_da_conta` falha antes de chegar à produção).
    """
    rota: str = request.scope["route"].path
    if rota.removeprefix(PREFIXO_DA_API) in ROTAS_DA_CONTA:
        return conta
    pagina = pagina_da_rota(rota)
    if pagina is None:
        raise HTTPException(status_code=500, detail="Rota sem contrato de página.")
    motivo = motivo_da_pagina(conta.plano, pagina.chave)
    if motivo is not None:
        raise _recusa(403, motivo, "plano")
    return conta
