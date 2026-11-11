"""O servidor de autorização do conector (OAuth 2.1): o Claude e o ChatGPT entram com a chave de cada analista.

O fluxo, do jeito que as duas IAs fazem (plano da linha 570, seção 2):

1. A IA se registra (DCR, RFC 7591). **Só os endereços de volta do Claude e do ChatGPT são aceitos**
   (`ENDERECOS_DE_VOLTA`). O `client_id` é um pacote selado com esses endereços: nada é gravado, e
   reiniciar o processo não invalida o registro (escolha da condição 2 do aceite).
2. A IA manda o analista a `/authorize` (PKCE S256 obrigatório); o conector devolve a página `/autorizar`
   com o pedido selado na URL (`pagina.py`), onde o analista cola a chave pessoal dele.
3. A chave aceita pela API vira um código de uso único que vive **60 s na memória deste processo** (o
   contêiner roda um processo só). Código reusado, vencido ou de outro cliente é recusado.
4. O código vira um token de acesso (1 h) e um de renovação (30 dias). **Os dois são a chave cifrada**
   (`selo.py`), presos ao cliente e ao recurso `/mcp`. Cada ferramenta abre o token e chama a API com a
   chave do analista: revogar a chave na API corta o conector na chamada seguinte.
5. A renovação confere a chave na API de novo e troca os dois tokens; o token de renovação usado não
   serve outra vez (lista na memória do processo até ele vencer).

Se a chave do servidor vazar, todo token capturado expõe a chave dentro dele: troque a chave do servidor
(todos entram de novo) e revogue as chaves das pessoas (`docs/conector-remoto.md`, "Incidente").
"""

import re
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl, Field

from conector_remoto.acesso import VerificadorDeChave, id_da_chave
from conector_remoto.selo import Selador

# os endereços de volta das duas IAs (documentação lida em 11/11/2026); o Claude Code entra pela chave em
# cabeçalho, então o retorno para `localhost` fica de fora (qualquer programa do PC poderia ouvir ali)
ENDERECOS_DE_VOLTA = {
    "https://claude.ai/api/mcp/auth_callback": "Claude",
    "https://chatgpt.com/connector_platform_oauth_redirect": "ChatGPT",
}
VOLTA_DO_CHATGPT_POR_ID = re.compile(
    r"https://chatgpt\.com/connector/oauth/[A-Za-z0-9_-]{1,128}"
)
METODOS_DE_ENTRADA = frozenset({"none", "client_secret_post", "client_secret_basic"})
CONCESSOES = frozenset({"authorization_code", "refresh_token"})
MAXIMO_DE_ENDERECOS = 4
MAXIMO_DO_ESCOPO = 200
MAXIMO_DO_NOME = 80
MAXIMO_DO_STATE = 1_024

VALIDADE_DO_PEDIDO_S = 600  # o tempo de o analista achar a chave e colar
VALIDADE_DO_CODIGO_S = 60
VALIDADE_DO_ACESSO_S = 3_600
VALIDADE_DA_RENOVACAO_S = 30 * 24 * 3_600
MAXIMO_DE_CODIGOS = 1_000
MAXIMO_DE_RENOVACOES_USADAS = 50_000
BYTES_DO_CODIGO = 32  # 256 bits (o mínimo do RFC 6749 é 128)

CLIENTE = "cliente"
PEDIDO = "pedido"
ACESSO = "acesso"
RENOVACAO = "renovacao"
SEGREDO_DO_CLIENTE = "segredo-do-cliente"
MENSAGEM_API_FORA = (
    "A API do TickerLab não respondeu agora; tente de novo em instantes."
)
MENSAGEM_CHAVE_REVOGADA = "A chave TickerLab deste acesso não vale mais: entre de novo."


def nome_da_ia(endereco_de_volta: str) -> str | None:
    """Qual IA usa este endereço de volta (Claude ou ChatGPT); None se ele está fora da lista fechada."""
    if endereco_de_volta in ENDERECOS_DE_VOLTA:
        return ENDERECOS_DE_VOLTA[endereco_de_volta]
    if VOLTA_DO_CHATGPT_POR_ID.fullmatch(endereco_de_volta):
        return "ChatGPT"
    return None


class CodigoComChave(AuthorizationCode):
    """O código de uso único, com a chave do analista (fica só na memória, por 60 s)."""

    code: str = Field(repr=False)
    chave_da_api: str = Field(repr=False)


class RenovacaoComChave(RefreshToken):
    """O token de renovação aberto, com a chave do analista e o id de uso único."""

    token: str = Field(repr=False)
    chave_da_api: str = Field(repr=False)
    uso_unico: str


@dataclass(frozen=True)
class PedidoDeAutorizacao:
    """O pedido de `/authorize`, como volta selado da página `/autorizar`."""

    selado: str
    client_id: str
    endereco_de_volta: str
    endereco_explicito: bool
    state: str | None
    desafio_pkce: str
    escopos: list[str]

    @property
    def ia(self) -> str:
        return nome_da_ia(self.endereco_de_volta) or "?"

    @property
    def host_de_volta(self) -> str:
        return urlsplit(self.endereco_de_volta).hostname or ""


def _textos(valor: object) -> list[str] | None:
    if isinstance(valor, list) and all(isinstance(item, str) for item in valor):
        return valor
    return None


class ProvedorOAuth:
    """O `OAuthAuthorizationServerProvider` do conector: sem banco, com o selo e 60 s de memória."""

    def __init__(
        self,
        selador: Selador,
        verificador: VerificadorDeChave,
        *,
        url_publica: str,
        recurso: str,
    ) -> None:
        self._selador = selador
        self._verificador = verificador
        self._url_publica = url_publica
        self._recurso = recurso
        # o `resource` (RFC 8707) que a IA pode pedir: o `/mcp` ou a origem do conector
        self._recursos_aceitos = frozenset({recurso, url_publica, f"{url_publica}/"})
        self._codigos: dict[str, CodigoComChave] = {}
        self._renovacoes_usadas: dict[str, int] = {}

    # ------------------------------------------------------------ registro (DCR) sem estado

    def _cliente_do_pacote(
        self, client_id: str, pacote: dict
    ) -> OAuthClientInformationFull | None:
        enderecos = _textos(pacote.get("r"))
        concessoes = _textos(pacote.get("g"))
        metodo = pacote.get("m")
        if not enderecos or concessoes is None or metodo not in METODOS_DE_ENTRADA:
            return None
        if any(nome_da_ia(e) is None for e in enderecos):
            return None
        tem_segredo = metodo != "none"
        return OAuthClientInformationFull(
            client_id=client_id,
            client_secret=self._segredo(client_id) if tem_segredo else None,
            client_secret_expires_at=0 if tem_segredo else None,
            client_id_issued_at=pacote.get("t"),
            redirect_uris=[AnyUrl(e) for e in enderecos],
            token_endpoint_auth_method=metodo,
            grant_types=concessoes,
            response_types=["code"],
            scope=pacote.get("s"),
            client_name=pacote.get("n"),
        )

    def _segredo(self, client_id: str) -> str:
        # o segredo do cliente é derivado do `client_id` com a chave do servidor: não precisa ser guardado
        return self._selador.assinar(SEGREDO_DO_CLIENTE, client_id)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """O cliente registrado, aberto do próprio `client_id`; None se o pacote não abre."""
        pacote = self._selador.abrir(CLIENTE, client_id, agora=time.time())
        return self._cliente_do_pacote(client_id, pacote) if pacote else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Aceita só o Claude e o ChatGPT; troca o `client_id` e o segredo pelos selados."""
        enderecos = [str(e) for e in client_info.redirect_uris or []]
        if not enderecos or len(enderecos) > MAXIMO_DE_ENDERECOS:
            raise RegistrationError(
                "invalid_redirect_uri", "Informe de 1 a 4 endereços de volta."
            )
        if any(nome_da_ia(e) is None for e in enderecos):
            raise RegistrationError(
                "invalid_redirect_uri",
                "Este conector aceita só o Claude e o ChatGPT (endereço de volta fora da lista).",
            )
        metodo = client_info.token_endpoint_auth_method or "client_secret_post"
        if metodo not in METODOS_DE_ENTRADA:
            raise RegistrationError(
                "invalid_client_metadata", "Método de entrada não aceito."
            )
        if not set(client_info.grant_types) <= CONCESSOES:
            raise RegistrationError(
                "invalid_client_metadata", "Só código de autorização e renovação."
            )
        if client_info.scope and len(client_info.scope) > MAXIMO_DO_ESCOPO:
            raise RegistrationError("invalid_client_metadata", "Escopo longo demais.")
        agora = time.time()
        pacote = {
            "r": enderecos,
            "m": metodo,
            "g": list(client_info.grant_types),
            "s": client_info.scope,
            "n": (client_info.client_name or "")[:MAXIMO_DO_NOME] or None,
            "t": int(agora),
        }
        client_info.client_id = self._selador.selar(CLIENTE, pacote, agora=agora)
        client_info.client_secret = (
            self._segredo(client_info.client_id) if metodo != "none" else None
        )
        client_info.client_secret_expires_at = 0 if metodo != "none" else None
        client_info.client_name = pacote["n"]

    # ------------------------------------------------------------ autorização: a página e o código

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Manda o analista à página `/autorizar`, com o pedido selado (vale 10 min)."""
        if (
            params.resource is not None
            and params.resource not in self._recursos_aceitos
        ):
            raise AuthorizeError(
                "invalid_target", "Este servidor de autorização só emite para o /mcp."
            )
        if params.state is not None and len(params.state) > MAXIMO_DO_STATE:
            raise AuthorizeError("invalid_request", "state longo demais.")
        agora = time.time()
        pacote = {
            "c": client.client_id,
            "r": str(params.redirect_uri),
            "x": params.redirect_uri_provided_explicitly,
            "s": params.state,
            "p": params.code_challenge,
            "e": params.scopes or [],
        }
        selado = self._selador.selar(
            PEDIDO, pacote, agora=agora, validade_s=VALIDADE_DO_PEDIDO_S
        )
        return f"{self._url_publica}/autorizar?pedido={selado}"

    def abrir_pedido(self, selado: str) -> PedidoDeAutorizacao | None:
        """O pedido que a página recebeu; None se foi mexido, venceu ou saiu da lista fechada."""
        pacote = self._selador.abrir(PEDIDO, selado, agora=time.time())
        if pacote is None:
            return None
        endereco, escopos = pacote.get("r"), _textos(pacote.get("e"))
        if (
            not isinstance(endereco, str)
            or nome_da_ia(endereco) is None
            or escopos is None
        ):
            return None
        return PedidoDeAutorizacao(
            selado=selado,
            client_id=str(pacote.get("c")),
            endereco_de_volta=endereco,
            endereco_explicito=bool(pacote.get("x")),
            state=pacote.get("s"),
            desafio_pkce=str(pacote.get("p")),
            escopos=escopos,
        )

    async def chave_aceita(self, chave: str) -> bool:
        """Se a API aceita a chave agora (pode lançar `httpx.HTTPError` se a API não responde)."""
        # sem a memória de 60 s do verificador: uma chave revogada agora não entra nem renova
        return (await self._verificador.conferir_na_api(chave)) is not None

    def _guardar_codigo(self, codigo: CodigoComChave) -> None:
        agora = time.time()
        if len(self._codigos) >= MAXIMO_DE_CODIGOS:
            self._codigos = {
                k: c for k, c in self._codigos.items() if c.expires_at > agora
            }
        while len(self._codigos) >= MAXIMO_DE_CODIGOS:
            del self._codigos[next(iter(self._codigos))]
        self._codigos[codigo.code] = codigo

    def emitir_codigo(self, pedido: PedidoDeAutorizacao, chave_da_api: str) -> str:
        """O endereço de volta da IA com o código de uso único (a chave já foi aceita pela API)."""
        codigo = CodigoComChave(
            code=secrets.token_urlsafe(BYTES_DO_CODIGO),
            scopes=pedido.escopos,
            expires_at=time.time() + VALIDADE_DO_CODIGO_S,
            client_id=pedido.client_id,
            code_challenge=pedido.desafio_pkce,
            redirect_uri=AnyUrl(pedido.endereco_de_volta),
            redirect_uri_provided_explicitly=pedido.endereco_explicito,
            resource=self._recurso,
            subject=id_da_chave(chave_da_api),
            chave_da_api=chave_da_api,
        )
        self._guardar_codigo(codigo)
        return construct_redirect_uri(
            pedido.endereco_de_volta, code=codigo.code, state=pedido.state
        )

    def endereco_de_recusa(self, pedido: PedidoDeAutorizacao) -> str:
        """O endereço de volta da IA dizendo que o analista cancelou."""
        return construct_redirect_uri(
            pedido.endereco_de_volta, error="access_denied", state=pedido.state
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> CodigoComChave | None:
        """Tira o código da memória (uso único: mesmo que a troca falhe adiante, ele não volta)."""
        codigo = self._codigos.pop(authorization_code, None)
        if codigo is None or codigo.client_id != client.client_id:
            return None
        return codigo if codigo.expires_at > time.time() else None

    # ------------------------------------------------------------ tokens: a chave cifrada

    def _emitir(self, client_id: str, chave: str, escopos: list[str]) -> OAuthToken:
        agora = time.time()
        acesso = self._selador.selar(
            ACESSO,
            {"k": chave, "c": client_id, "a": self._recurso},
            agora=agora,
            validade_s=VALIDADE_DO_ACESSO_S,
        )
        renovacao = self._selador.selar(
            RENOVACAO,
            {
                "k": chave,
                "c": client_id,
                "a": self._recurso,
                "j": secrets.token_urlsafe(16),
                "e": escopos,
            },
            agora=agora,
            validade_s=VALIDADE_DA_RENOVACAO_S,
        )
        return OAuthToken(
            access_token=acesso,
            expires_in=VALIDADE_DO_ACESSO_S,
            refresh_token=renovacao,
            scope=" ".join(escopos) or None,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: CodigoComChave
    ) -> OAuthToken:
        """Os tokens do código (o SDK já conferiu o PKCE, o endereço de volta e a validade)."""
        return self._emitir(
            client.client_id, authorization_code.chave_da_api, authorization_code.scopes
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RenovacaoComChave | None:
        """O token de renovação aberto, se é deste cliente e ainda não foi usado."""
        pacote = self._selador.abrir(RENOVACAO, refresh_token, agora=time.time())
        if pacote is None or pacote.get("c") != client.client_id:
            return None
        chave, uso, escopos = pacote.get("k"), pacote.get("j"), _textos(pacote.get("e"))
        if not isinstance(chave, str) or not isinstance(uso, str) or escopos is None:
            return None
        if uso in self._renovacoes_usadas:
            return None
        return RenovacaoComChave(
            token=refresh_token,
            client_id=client.client_id,
            scopes=escopos,
            expires_at=pacote.get("exp"),
            resource=self._recurso,
            subject=id_da_chave(chave),
            chave_da_api=chave,
            uso_unico=uso,
        )

    def _marcar_usada(self, renovacao: RenovacaoComChave) -> bool:
        """Marca o token de renovação como usado; False se outro pedido já o usou."""
        if renovacao.uso_unico in self._renovacoes_usadas:
            return False
        if len(self._renovacoes_usadas) >= MAXIMO_DE_RENOVACOES_USADAS:
            agora = time.time()
            self._renovacoes_usadas = {
                u: v for u, v in self._renovacoes_usadas.items() if v > agora
            }
        while len(self._renovacoes_usadas) >= MAXIMO_DE_RENOVACOES_USADAS:
            del self._renovacoes_usadas[next(iter(self._renovacoes_usadas))]
        self._renovacoes_usadas[renovacao.uso_unico] = renovacao.expires_at or 0
        return True

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RenovacaoComChave,
        scopes: list[str],
    ) -> OAuthToken:
        """Novos tokens, se a chave ainda vale na API; o token de renovação usado não serve de novo."""
        if not self._marcar_usada(refresh_token):
            raise TokenError("invalid_grant", "Este token de renovação já foi usado.")
        try:
            aceita = await self.chave_aceita(refresh_token.chave_da_api)
        except httpx.HTTPError:
            # a API não respondeu: o token não foi gasto, a IA tenta de novo depois
            self._renovacoes_usadas.pop(refresh_token.uso_unico, None)
            raise TokenError("invalid_request", MENSAGEM_API_FORA) from None
        if not aceita:
            raise TokenError("invalid_grant", MENSAGEM_CHAVE_REVOGADA)
        return self._emitir(client.client_id, refresh_token.chave_da_api, scopes)

    # ------------------------------------------------------------ o token na chamada do /mcp

    async def load_access_token(self, token: str) -> AccessToken | None:
        """O acesso do analista: o token de acesso aberto, ou a própria chave (entrada direta do PR 1)."""
        if id_da_chave(token) is not None:
            return await self._verificador.verify_token(token)
        pacote = self._selador.abrir(ACESSO, token, agora=time.time())
        if pacote is None:
            return None
        chave, cliente = pacote.get("k"), pacote.get("c")
        if not isinstance(chave, str) or not isinstance(cliente, str):
            return None
        acesso = await self._verificador.verify_token(chave)
        if acesso is None:
            return None
        return acesso.model_copy(
            update={
                "token": token,
                "client_id": cliente,
                "expires_at": pacote.get("exp"),
                "resource": pacote.get("a"),
            }
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """Sem rota de revogação: quem corta o acesso é a revogação da chave na API."""


class VerificadorDoProvedor:
    """O `TokenVerifier` do `/mcp`: abre o token pelo provedor (sem o `ProviderTokenVerifier` do SDK,
    para o conector montar as rotas do OAuth do jeito dele)."""

    def __init__(self, provedor: ProvedorOAuth) -> None:
        self._provedor = provedor

    async def verify_token(self, token: str) -> AccessToken | None:
        return await self._provedor.load_access_token(token)
