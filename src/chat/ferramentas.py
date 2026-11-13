"""As ferramentas do chat (linha 903): as 12 do conector remoto, só de leitura, pelo mesmo código dele.

O chat não reescreve ferramenta nenhuma: monta um `ServidorDoConector` (`conector_remoto/`) com as mesmas
ferramentas, os mesmos nomes, as mesmas descrições, a mesma conferência sem pessoa física e o mesmo teto de
tamanho. A diferença é de onde vem a API: em vez de rede e chave, um app interno da API externa
(`/data/v1`), no próprio processo, em que a porta da chave foi trocada pelo contexto da organização da conta
(o mesmo contrato, o mesmo limite do minuto e a mesma quota do mês). Por isso o caminho é o sem pessoa
mesmo para a organização com `pessoa_na_tela`: a API por chave não serve pessoa, e o conector ainda confere
cada resposta antes de ela ir ao modelo.

O que a ferramenta devolve vai ao modelo marcado como dado (`<dados_da_ferramenta>`), e as instruções dizem
para não obedecer a nada que venha de dentro da marca. Cada resultado e o total de uma pergunta têm teto
de caracteres (`LIMITES_DO_CHAT`).
"""

import logging
import re
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

from conector_remoto.acesso import AcessoDoAnalista, conjuntos_do_catalogo
from conector_remoto.cliente_api import ClienteDaApi
from conector_remoto.ferramentas import TITULOS_DAS_FERRAMENTAS, registrar_ferramentas
from conector_remoto.servidor import ServidorDoConector
from src.chaves_da_api import ContextoDaChave
from src.planos import LimitesDoChat

registro = logging.getLogger(__name__)

# As 12 do conector, escritas aqui de propósito: ferramenta nova no conector não entra no chat sem passar
# por este arquivo (há teste que confere que a lista bate com a do conector).
NOMES_DAS_FERRAMENTAS = frozenset(
    {
        "buscar_empresas",
        "ficha_da_empresa",
        "comparaveis",
        "demonstracoes",
        "setores",
        "setor",
        "o_que_posso_ver",
        "novidades",
        "eventos",
        "vinculos",
        "compradores_do_setor",
        "fundo",
    }
)
URL_INTERNA = "http://chat.interno"
# nunca chega a uma porta de chave: no app interno a porta é trocada pelo contexto da organização
CHAVE_INTERNA = "chat-interno"
CLIENTE_DO_CHAT = "tickerlab-chat"
TEMPO_LIMITE_S = 30.0
MARCA = "dados_da_ferramenta"
_FECHO_DA_MARCA = re.compile(rf"</\s*{MARCA}", re.IGNORECASE)

MENSAGEM_FORA_DA_LISTA = "Esta ferramenta não está disponível no chat."
MENSAGEM_PARAMETROS = "Os parâmetros precisam ser um objeto JSON."
MENSAGEM_FALHA = "A ferramenta falhou por um erro interno; tente outra consulta."
MENSAGEM_TETO_DA_PERGUNTA = "Limite de dados desta pergunta atingido: responda com o que já foi consultado e diga o que faltou."


class FerramentasIndisponiveis(Exception):
    """A API interna não respondeu o catálogo da organização: o chat não abre."""


def app_interno(contexto: ContextoDaChave) -> FastAPI:
    """A API externa dentro do processo, com a porta da chave trocada pelo contexto da organização."""
    # importada aqui: a API externa puxa a base (DuckDB), e o chat desligado não precisa dela
    from src.api_externa import acesso
    from src.api_externa.rotas import router

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(router)

    def com_quota_do_mes() -> ContextoDaChave:
        acesso.conferir_contexto(contexto, com_quota_do_mes=True)
        return contexto

    def sem_quota_do_mes() -> ContextoDaChave:
        acesso.conferir_contexto(contexto, com_quota_do_mes=False)
        return contexto

    app.dependency_overrides[acesso.exigir_chave] = com_quota_do_mes
    app.dependency_overrides[acesso.exigir_chave_sem_quota_do_mes] = sem_quota_do_mes
    return app


def transporte_interno(contexto: ContextoDaChave) -> httpx.AsyncBaseTransport:
    """O transporte que leva os pedidos do conector ao app interno, sem rede."""
    return httpx.ASGITransport(app=app_interno(contexto))


@dataclass(frozen=True)
class DefinicaoDeFerramenta:
    """Uma ferramenta como o modelo a recebe."""

    nome: str
    titulo: str
    descricao: str
    esquema: Mapping[str, object]

    def para_o_modelo(self) -> dict[str, object]:
        return {
            "name": self.nome,
            "description": f"{self.titulo}. {self.descricao}".strip(),
            "input_schema": dict(self.esquema),
            # a entrada chega aos poucos no streaming; quem confere o formato é o conector (pydantic)
            "eager_input_streaming": True,
        }


@dataclass(frozen=True)
class ResultadoDaFerramenta:
    """O texto que volta ao modelo e se é um erro (`is_error` do `tool_result`)."""

    texto: str
    erro: bool


def marcar_como_dado(ferramenta: str, texto: str) -> str:
    """O texto entre as marcas de dado; um fecho da marca dentro do texto é desarmado."""
    limpo = _FECHO_DA_MARCA.sub(f"<\\/{MARCA}", texto)
    return f'<{MARCA} ferramenta="{ferramenta}">\n{limpo}\n</{MARCA}>'


@contextmanager
def _como_o_analista(acesso: AcessoDoAnalista) -> Generator[None]:
    """O acesso da organização no lugar em que as ferramentas do conector o leem."""
    marca = auth_context_var.set(AuthenticatedUser(acesso))
    try:
        yield
    finally:
        auth_context_var.reset(marca)


def _texto_do_resultado(resultado: object) -> str | None:
    if not isinstance(resultado, CallToolResult) or resultado.is_error:
        return None
    return "".join(c.text for c in resultado.content if isinstance(c, TextContent))


class CaixaDeFerramentas:
    """As ferramentas de uma pergunta: a lista para o modelo e a execução com os tetos."""

    def __init__(
        self,
        servidor: ServidorDoConector,
        acesso: AcessoDoAnalista,
        definicoes: tuple[DefinicaoDeFerramenta, ...],
        limites: LimitesDoChat,
    ) -> None:
        self._servidor = servidor
        self._acesso = acesso
        self.definicoes = definicoes
        self._nomes = frozenset(d.nome for d in definicoes)
        self._limites = limites
        self.caracteres_entregues = 0

    @classmethod
    async def abrir(
        cls,
        transporte: httpx.AsyncBaseTransport,
        *,
        identificador: str,
        limites: LimitesDoChat,
        chave: str = CHAVE_INTERNA,
    ) -> "CaixaDeFerramentas":
        """Confere o catálogo da organização e monta as ferramentas que ela pode usar.

        `identificador` é o que vai para o registro de uso do conector (ids, nunca nome)."""
        cliente = ClienteDaApi(
            URL_INTERNA, tempo_limite_s=TEMPO_LIMITE_S, transporte=transporte
        )
        try:
            catalogo = await cliente.get(chave, "/catalog")
        except httpx.HTTPError as erro:
            raise FerramentasIndisponiveis(type(erro).__name__) from None
        if not catalogo.ok:
            raise FerramentasIndisponiveis(f"catálogo respondeu {catalogo.status}")
        acesso = AcessoDoAnalista(
            token=chave,
            client_id=CLIENTE_DO_CHAT,
            scopes=[],
            subject=identificador,
            chave_da_api=chave,
            conjuntos=conjuntos_do_catalogo(catalogo.corpo),
        )
        servidor = ServidorDoConector(CLIENTE_DO_CHAT)
        registrar_ferramentas(servidor, cliente)
        with _como_o_analista(acesso):
            ferramentas = await servidor.list_tools()
        definicoes = tuple(
            DefinicaoDeFerramenta(
                nome=f.name,
                titulo=f.title or TITULOS_DAS_FERRAMENTAS.get(f.name, f.name),
                descricao=f.description or "",
                esquema=f.input_schema,
            )
            for f in ferramentas
            if f.name in NOMES_DAS_FERRAMENTAS
        )
        return cls(servidor, acesso, definicoes, limites)

    def titulo(self, nome: str) -> str:
        return TITULOS_DAS_FERRAMENTAS.get(nome, nome)

    async def executar(self, nome: str, entrada: object) -> ResultadoDaFerramenta:
        """Roda a ferramenta; o erro volta como texto para o modelo explicar ao analista."""
        if nome not in self._nomes:
            return ResultadoDaFerramenta(MENSAGEM_FORA_DA_LISTA, erro=True)
        if not isinstance(entrada, dict):
            return ResultadoDaFerramenta(MENSAGEM_PARAMETROS, erro=True)
        teto = self._limites.caracteres_de_dados_por_pergunta
        if self.caracteres_entregues >= teto:
            return ResultadoDaFerramenta(MENSAGEM_TETO_DA_PERGUNTA, erro=True)
        try:
            with _como_o_analista(self._acesso):
                resultado = await self._servidor.call_tool(nome, entrada)
        except ToolError as erro:
            # a mensagem é do conector, mas pode repetir o `detail` da API: vai marcada como dado também
            return ResultadoDaFerramenta(marcar_como_dado(nome, str(erro)), erro=True)
        except Exception as erro:  # noqa: BLE001 - nada de uma ferramenta derruba a conversa
            # o log JSON leva só a mensagem: o nome da ferramenta e a classe do erro, nunca o texto dele
            registro.warning(
                "chat_ferramenta_falhou ferramenta=%s erro=%s",
                nome,
                type(erro).__name__,
            )
            return ResultadoDaFerramenta(MENSAGEM_FALHA, erro=True)
        texto = _texto_do_resultado(resultado)
        if texto is None:
            return ResultadoDaFerramenta(MENSAGEM_FALHA, erro=True)
        if len(texto) > self._limites.caracteres_por_resultado:
            return ResultadoDaFerramenta(
                f"A resposta tem {len(texto)} caracteres, grande demais para o chat. "
                "Peça menos linhas (parâmetro `limite`) ou filtre mais.",
                erro=True,
            )
        if self.caracteres_entregues + len(texto) > teto:
            self.caracteres_entregues = teto
            return ResultadoDaFerramenta(MENSAGEM_TETO_DA_PERGUNTA, erro=True)
        self.caracteres_entregues += len(texto)
        return ResultadoDaFerramenta(marcar_como_dado(nome, texto), erro=False)
