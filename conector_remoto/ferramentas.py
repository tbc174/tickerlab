"""As ferramentas do conector: todas só leem, e cada uma é um pedido à API externa com a chave do analista.

Nomes e descrições em português, para o analista ler no Claude ou no ChatGPT o que a IA está chamando;
os parâmetros viram os da API (em inglês) aqui. Cada ferramenta devolve o JSON da API como texto, já
limpo, conferido sem pessoa física e dentro do teto (`saida.preparar_saida`). Erro da API vira uma frase
em português que a IA pode repetir ao analista, sem nada da chave.
"""

import json
import logging
import re
from datetime import date
from typing import Annotated, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from conector_remoto.acesso import acesso_do_pedido
from conector_remoto.cliente_api import ClienteDaApi, ParametroDaApi, RespostaDaApi
from conector_remoto.pessoa import RespostaComPessoa
from conector_remoto.saida import RespostaGrandeDemais, preparar_saida

registro = logging.getLogger("conector_remoto")

SO_LEITURA = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
# a ferramenta aparece só para a chave que pode ver um destes conjuntos do catálogo; vazio = sempre
CONJUNTOS_DA_FERRAMENTA: dict[str, frozenset[str]] = {
    "buscar_empresas": frozenset({"prospecting"}),
    "ficha_da_empresa": frozenset({"profiles", "companies"}),
    "comparaveis": frozenset({"comparables"}),
    "demonstracoes": frozenset({"financials"}),
    "eventos": frozenset({"events"}),
    "fundo": frozenset({"funds"}),
    "vinculos": frozenset({"links"}),
    "compradores_do_setor": frozenset({"buyers"}),
    "novidades": frozenset({"research"}),
    "setores": frozenset({"sectors"}),
    "setor": frozenset({"sectors"}),
    "o_que_posso_ver": frozenset(),
}
# 12 caracteres (letras na raiz desde o CNPJ alfanumérico) e 2 dígitos verificadores; a API confere os DV
_CNPJ = re.compile(r"[0-9A-Z]{12}[0-9]{2}")
_PONTUACAO_DO_CNPJ = re.compile(r"[\s./-]")
# como as chaves de `setores` (minúsculas e `_`): sem ponto, nada de `..` virar outra rota
_CHAVE_DO_SETOR = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}")
_CODIGO_DA_API = re.compile(r"[a-z_]{1,40}")
LIMITE_MAXIMO_DA_BUSCA = 100
LIMITE_PADRAO_DA_BUSCA = 50
ESPERA_PADRAO_S = 60
# o nome em português (o mesmo da CLI) -> o tipo de evento da API
TIPOS_DE_EVENTO = {"documento": "ipe_filing", "auditor": "auditor_change"}
# o nome em português (o mesmo da CLI, linha 773) -> o tipo de vínculo da API
TIPOS_DE_VINCULO = {
    "controlada": "subsidiary_of",
    "coligada": "affiliate_of",
    "participada": "investee_of",
    "auditor": "audits",
}
PROFUNDIDADE_MAXIMA = 3  # a da API (`src/api_externa/conjuntos/vinculos.py`)
# os da API (`src/api_externa/conjuntos/compradores.py`)
ANOS_MAXIMO_DOS_COMPRADORES = 10
LIMITE_MAXIMO_DOS_COMPRADORES = 50
DIAS_MAXIMO_DAS_NOVIDADES = 30  # o da API (`src/api_externa/conjuntos/novidades.py`)

MENSAGEM_DE_PESSOA = (
    "Resposta recusada: ela trazia um campo de pessoa física, que este conector não entrega. "
    "O TickerLab foi avisado; os outros pedidos seguem normais."
)
MENSAGEM_SEM_CHAVE = "Pedido sem chave do TickerLab: refaça a ligação do conector."
MENSAGEM_NAO_LIBERADA = "Esta ferramenta não está disponível para a chave usada."
STATUS_OK = 200
STATUS_PEDIDO_INVALIDO = 400
STATUS_CHAVE_RECUSADA = 401
STATUS_NAO_DISPONIVEL = 404
STATUS_PARAMETRO_INVALIDO = 422
STATUS_LIMITE = 429
STATUS_FORA_DO_AR = 503
CODIGO_DO_MINUTO = "rate_limited"

Cnpj = Annotated[
    str,
    Field(
        description="CNPJ da empresa (14 caracteres; com ou sem pontuação). Só pessoa jurídica.",
        max_length=40,
    ),
]
ComoEraEm = Annotated[
    date | None,
    Field(
        description=(
            "Data (AAAA-MM-DD) para ver o dado como era conhecido nesse dia, sem nada publicado "
            "depois. Vazio = hoje."
        )
    ),
]


def ferramenta_liberada(nome: str, conjuntos: frozenset[str]) -> bool:
    """A ferramenta existe e a chave pode ver pelo menos um dos conjuntos dela."""
    exigidos = CONJUNTOS_DA_FERRAMENTA.get(nome)
    if exigidos is None:
        return False
    return not exigidos or bool(exigidos & conjuntos)


def cnpj_do_pedido(texto: str) -> str:
    """Os 14 caracteres do CNPJ, sem pontuação e em maiúsculas; `ToolError` se não tem a forma."""
    limpo = _PONTUACAO_DO_CNPJ.sub("", texto).upper()
    if not _CNPJ.fullmatch(limpo):
        raise ToolError(
            "Isso não é um CNPJ (14 caracteres). O conector consulta só empresas, nunca CPF."
        )
    return limpo


def mensagem_do_erro(resposta: RespostaDaApi) -> str:
    """A frase, em português, que explica à IA (e ao analista) por que a API não serviu."""
    codigo = (
        resposta.codigo if _CODIGO_DA_API.fullmatch(resposta.codigo or "") else None
    )
    if resposta.status == STATUS_CHAVE_RECUSADA:
        return (
            "A chave foi recusada pela API (revogada ou vencida). "
            "Peça uma chave nova a quem administra a conta da organização no TickerLab."
        )
    if resposta.status == STATUS_NAO_DISPONIVEL:
        return (
            "Não disponível: o dado não está na base para esse pedido, ou a chave não tem acesso a "
            "ele (a API não diz qual dos dois, de propósito)."
        )
    if resposta.status == STATUS_LIMITE and codigo == CODIGO_DO_MINUTO:
        espera = resposta.espera_s or ESPERA_PADRAO_S
        return (
            f"Limite de pedidos por minuto da organização; tente de novo em {espera} s."
        )
    if resposta.status == STATUS_LIMITE:
        return "A quota de pedidos do mês da organização acabou; ela volta no dia 1º do mês que vem."
    if resposta.status == STATUS_PEDIDO_INVALIDO:
        return f"A API recusou o pedido ({codigo or 'pedido inválido'}); confira os parâmetros."
    if resposta.status == STATUS_PARAMETRO_INVALIDO:
        return "Parâmetro em formato errado (datas em AAAA-MM-DD; números sem texto)."
    if resposta.status == STATUS_FORA_DO_AR:
        return "A base deste dado está fora do ar agora; tente de novo mais tarde."
    return f"A API respondeu com um erro inesperado (status {resposta.status})."


def _como_texto(corpo: object) -> str:
    return json.dumps(corpo, ensure_ascii=False, separators=(",", ":"))


def _dia(valor: date | None) -> str | None:
    return valor.isoformat() if valor else None


class Pedidos:
    """Faz o pedido da ferramenta à API com a chave do analista e prepara a resposta."""

    def __init__(self, cliente: ClienteDaApi) -> None:
        self._cliente = cliente

    async def resposta(
        self, caminho: str, parametros: dict[str, ParametroDaApi] | None = None
    ) -> RespostaDaApi:
        """A resposta crua da API (para quem decide pelo status, como a ficha)."""
        acesso = acesso_do_pedido()
        if acesso is None:
            raise ToolError(MENSAGEM_SEM_CHAVE)
        try:
            return await self._cliente.get(acesso.chave_da_api, caminho, parametros)
        except httpx.HTTPError:
            registro.warning("api_sem_resposta", extra={"caminho": caminho})
            raise ToolError(
                "A API do TickerLab não respondeu; tente de novo em instantes."
            ) from None

    def entregar(self, resposta: RespostaDaApi, ferramenta: str) -> str:
        """O texto que vai para a IA, ou `ToolError` com a frase do problema."""
        if not resposta.ok:
            raise ToolError(mensagem_do_erro(resposta))
        try:
            return _como_texto(preparar_saida(resposta.corpo))
        except RespostaComPessoa as recusa:
            acesso = acesso_do_pedido()
            registro.error(
                "resposta_com_pessoa_recusada",
                extra={
                    "ferramenta": ferramenta,
                    "caminhos": recusa.caminhos[:20],
                    "chave": acesso.subject if acesso else None,
                },
            )
            raise ToolError(MENSAGEM_DE_PESSOA) from None
        except RespostaGrandeDemais as grande:
            raise ToolError(
                f"A resposta tem {grande.tamanho} caracteres, grande demais para a conversa. "
                "Peça menos linhas (parâmetro `limite`) ou filtre mais."
            ) from None

    async def pedir(
        self,
        ferramenta: str,
        caminho: str,
        parametros: dict[str, ParametroDaApi] | None = None,
    ) -> str:
        """Pede e entrega: o caminho comum de quase toda ferramenta."""
        return self.entregar(await self.resposta(caminho, parametros), ferramenta)


def registrar_ferramentas(servidor: MCPServer, cliente: ClienteDaApi) -> None:
    """Põe as ferramentas no servidor (a lista de cada chave é filtrada no `ServidorDoConector`)."""
    pedidos = Pedidos(cliente)

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def buscar_empresas(
        cnae: Annotated[
            list[str] | None,
            Field(
                description="Códigos CNAE, 2 a 7 dígitos; prefixo vale ('62' traz a divisão inteira)."
            ),
        ] = None,
        uf: Annotated[
            list[str] | None, Field(description="Siglas das UFs, ex.: ['SP', 'MG'].")
        ] = None,
        municipio: Annotated[
            list[str] | None,
            Field(
                description="Municípios pelo código da Receita (4 dígitos) ou pelo nome; use com a UF."
            ),
        ] = None,
        porte: Annotated[
            list[Literal["micro", "small", "other", "not_informed"]] | None,
            Field(
                description=(
                    "Porte na Receita: micro, small (pequeno), other (os demais; a Receita não tem "
                    "'médio' nem 'grande'), not_informed."
                )
            ),
        ] = None,
        natureza_juridica: Annotated[
            list[str] | None,
            Field(
                description="Código da natureza jurídica, ex.: 2062 (Ltda.), 2054 (S.A. fechada)."
            ),
        ] = None,
        situacao_cadastral: Annotated[
            list[Literal["ativa", "baixada", "inapta", "suspensa", "nula"]] | None,
            Field(description="Situação na Receita; vazio = só as ativas."),
        ] = None,
        aberta_antes_de: Annotated[
            date | None,
            Field(description="Só as abertas antes desta data (AAAA-MM-DD)."),
        ] = None,
        aberta_depois_de: Annotated[
            date | None,
            Field(description="Só as abertas depois desta data (AAAA-MM-DD)."),
        ] = None,
        so_matriz: Annotated[
            bool | None,
            Field(
                description="true = só a matriz; false = só as filiais; vazio = todas."
            ),
        ] = None,
        limite: Annotated[
            int,
            Field(
                ge=1,
                le=LIMITE_MAXIMO_DA_BUSCA,
                description="Empresas por página (até 100).",
            ),
        ] = LIMITE_PADRAO_DA_BUSCA,
        cursor: Annotated[
            str | None,
            Field(
                max_length=200,
                description="O `next_cursor` da página anterior, para a seguinte.",
            ),
        ] = None,
        como_era_em: ComoEraEm = None,
    ) -> str:
        """Acha empresas brasileiras por filtros do cadastro da Receita (CNAE, UF, município, porte,
        natureza jurídica, data de abertura). Pelo menos um filtro. Devolve razão social, CNAE, UF,
        município, porte e data de abertura, cada valor com a fonte e o dia em que ficou público.
        Só pessoa jurídica: sem sócio, contato ou endereço."""
        return await pedidos.pedir(
            "buscar_empresas",
            "/companies",
            {
                "cnae": cnae, "state": uf, "municipality": municipio, "size": porte,
                "legal_nature": natureza_juridica, "registration_status": situacao_cadastral,
                "opened_before": _dia(aberta_antes_de), "opened_after": _dia(aberta_depois_de),
                "head_office": so_matriz, "limit": limite, "cursor": cursor,
                "known_at": _dia(como_era_em),
            },
        )  # fmt: skip

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def ficha_da_empresa(cnpj: Cnpj, como_era_em: ComoEraEm = None) -> str:
        """A ficha de uma empresa: o cadastro na Receita (razão social, situação, abertura, CNAE,
        porte, natureza jurídica, Simples) e, se for companhia aberta, as entregas de DFP e ITR à
        CVM com prazo e atraso. Cada valor traz a fonte e o dia em que ficou público."""
        numeros = cnpj_do_pedido(cnpj)
        dia: dict[str, ParametroDaApi] = {"known_at": _dia(como_era_em)}
        acesso = acesso_do_pedido()
        conjuntos = acesso.conjuntos if acesso else frozenset()
        if "profiles" in conjuntos:
            resposta = await pedidos.resposta(f"/companies/{numeros}/profile", dia)
            if resposta.status != STATUS_NAO_DISPONIVEL or "companies" not in conjuntos:
                return pedidos.entregar(resposta, "ficha_da_empresa")
        return await pedidos.pedir("ficha_da_empresa", f"/companies/{numeros}", dia)

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def comparaveis(cnpj: Cnpj, como_era_em: ComoEraEm = None) -> str:
        """As companhias abertas comparáveis à pedida (mesmo grupo de setores na CVM), cada uma com
        receita, EBITDA, lucro, dívida líquida e as razões do último DFP entregue, e a mediana dos
        pares. Só para companhia aberta com formulário cadastral na CVM."""
        numeros = cnpj_do_pedido(cnpj)
        return await pedidos.pedir(
            "comparaveis",
            f"/companies/{numeros}/comparables",
            {"known_at": _dia(como_era_em)},
        )

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def demonstracoes(
        cnpj: Cnpj,
        como_era_em: ComoEraEm = None,
        fim_do_periodo: Annotated[
            date | None,
            Field(
                description="Só o período que termina neste dia (AAAA-MM-DD), ex.: 2025-12-31."
            ),
        ] = None,
    ) -> str:
        """As demonstrações financeiras (DFP e ITR) da companhia aberta na CVM: um valor por conta e
        período, com o documento, a versão e a data em que ficou público."""
        numeros = cnpj_do_pedido(cnpj)
        return await pedidos.pedir(
            "demonstracoes",
            f"/companies/{numeros}/financials",
            {"known_at": _dia(como_era_em), "period_end": _dia(fim_do_periodo)},
        )

    _registrar_eventos_rede_e_fundo(servidor, pedidos)
    _registrar_novidades(servidor, pedidos)

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def setores() -> str:
        """A lista de setores que o TickerLab acompanha, com a chave de cada um (para a ferramenta
        `setor`)."""
        return await pedidos.pedir("setores", "/sectors")

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def setor(
        chave: Annotated[
            str,
            Field(
                max_length=80, description="A chave do setor, da lista de `setores`."
            ),
        ],
        como_era_em: ComoEraEm = None,
    ) -> str:
        """Um setor: as séries de mercado, a concentração (CR4 e HHI) e a participação de cada
        empresa, com a fonte de cada número."""
        if not _CHAVE_DO_SETOR.fullmatch(chave):
            raise ToolError(
                "Chave de setor inválida; use uma chave da lista de `setores`."
            )
        return await pedidos.pedir(
            "setor", f"/sectors/{chave}", {"known_at": _dia(como_era_em)}
        )

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def o_que_posso_ver() -> str:
        """O que a chave do analista pode consultar (conjuntos, campos, fontes e licenças) e o
        consumo do mês da organização, com os limites do plano."""
        catalogo = await pedidos.resposta("/catalog")
        consumo = await pedidos.resposta("/usage")
        for resposta in (catalogo, consumo):
            if not resposta.ok:
                raise ToolError(mensagem_do_erro(resposta))
        juntos = RespostaDaApi(
            STATUS_OK, {"catalog": catalogo.corpo, "usage": consumo.corpo}
        )
        return pedidos.entregar(juntos, "o_que_posso_ver")


def _registrar_novidades(servidor: MCPServer, pedidos: Pedidos) -> None:
    """A ferramenta das novidades da pesquisa (linha 830)."""

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def novidades(
        dias: Annotated[
            int | None,
            Field(
                ge=1,
                le=DIAS_MAXIMO_DAS_NOVIDADES,
                description="Quantos dias para trás olhar (1 a 30). Vazio = 7.",
            ),
        ] = None,
    ) -> str:
        """As fontes que a pesquisa do TickerLab provou na semana: de cada uma, o órgão público, a data, o
        trecho literal e o hash (sha256) do original, que prova que o trecho está lá. Só entra o que tem
        prova gravada; sem nada novo, a lista vem vazia: diga ao analista que não há fonte nova provada."""
        return await pedidos.pedir("novidades", "/research/news", {
            "days": None if dias is None else str(dias),
        })  # fmt: skip


def _registrar_eventos_rede_e_fundo(servidor: MCPServer, pedidos: Pedidos) -> None:
    """Eventos, vínculos, compradores do setor e fundo (à parte, para a
    `registrar_ferramentas` não crescer demais); chamada no meio dela, para a ordem da lista ficar."""

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def eventos(
        cnpj: Cnpj,
        tipos: Annotated[
            list[Literal["documento", "auditor"]] | None,
            Field(
                max_length=len(TIPOS_DE_EVENTO),
                description=(
                    "Só estes tipos: documento (o que a companhia entregou à CVM pelo IPE: fato "
                    "relevante, comunicado, assembleia...) ou auditor (troca de auditor, pelo FCA). "
                    "Vazio = todos."
                ),
            ),
        ] = None,
        cursor: Annotated[
            str | None,
            Field(
                max_length=200,
                description="O `next_cursor` da página anterior, para a seguinte.",
            ),
        ] = None,
        como_era_em: ComoEraEm = None,
    ) -> str:
        """Os eventos da empresa, do mais novo ao mais velho: cada documento entregue à CVM (protocolo,
        categoria, tipo, data de referência e endereço; o assunto escrito pela companhia não sai) e cada
        troca de auditor (a firma anterior, a nova, o dia e os anos com a anterior). Cada valor traz a
        fonte e o dia em que ficou público; a página vai até o limite do plano e `next_cursor` traz a
        seguinte."""
        numeros = cnpj_do_pedido(cnpj)
        return await pedidos.pedir("eventos", f"/companies/{numeros}/events", {
            "types": [TIPOS_DE_EVENTO[tipo] for tipo in tipos or ()],
            "cursor": cursor,
            "known_at": _dia(como_era_em),
        })  # fmt: skip

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def vinculos(
        cnpj: Cnpj,
        profundidade: Annotated[
            int,
            Field(
                ge=1,
                le=PROFUNDIDADE_MAXIMA,
                description="Quantos saltos a partir da empresa (1 a 3): 2 traz os vínculos dos vínculos.",
            ),
        ] = 1,
        tipos: Annotated[
            list[Literal["controlada", "coligada", "participada", "auditor"]] | None,
            Field(
                max_length=len(TIPOS_DE_VINCULO),
                description=(
                    "Só estes tipos: controlada, coligada ou participada (a sociedade e a participação "
                    "no capital, pelo FRE) ou auditor (a firma que auditava a companhia, pelo FCA). "
                    "Vazio = todos."
                ),
            ),
        ] = None,
        como_era_em: ComoEraEm = None,
    ) -> str:
        """Os vínculos da empresa como eram no dia: controladas, coligadas, participadas e o auditor.
        Cada vínculo traz as duas pontas (id na rede, raiz do CNPJ e a razão social que valia no dia),
        a participação no capital como o FRE informou e as datas. Só companhia aberta informa controle
        e coligação, uma vez por ano: leia os `limits`. Sócio pessoa física não sai."""
        numeros = cnpj_do_pedido(cnpj)
        return await pedidos.pedir("vinculos", f"/companies/{numeros}/links", {
            "known_at": _dia(como_era_em),
            "depth": str(profundidade),  # como a CLI
            "types": [TIPOS_DE_VINCULO[tipo] for tipo in tipos or ()],
        })  # fmt: skip

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def compradores_do_setor(
        cnae: Annotated[
            str,
            Field(
                min_length=5,
                max_length=12,
                description="CNAE do setor: a classe (5 dígitos) ou a subclasse (7 dígitos); pontuação vale.",
            ),
        ],
        uf: Annotated[
            str | None,
            Field(
                pattern=r"^[A-Za-z]{2}$",
                description="Sigla da UF, ex.: 'SP'. Vazio = o país todo.",
            ),
        ] = None,
        anos: Annotated[
            int | None,
            Field(
                ge=1,
                le=ANOS_MAXIMO_DOS_COMPRADORES,
                description="Quantos anos para trás olhar (1 a 10). Vazio = 3.",
            ),
        ] = None,
        limite: Annotated[
            int | None,
            Field(
                ge=1,
                le=LIMITE_MAXIMO_DOS_COMPRADORES,
                description="Quantos compradores trazer (1 a 50). Vazio = 20.",
            ),
        ] = None,
        como_era_em: ComoEraEm = None,
    ) -> str:
        """Quem já se mexeu num setor: as empresas que entraram como sócias de empresas ativas do CNAE (na
        UF, se dada), os fundos (FIP) sócios delas e as companhias abertas com controlada no setor, nos
        últimos `anos`, como era no dia. Cada comprador traz os sinais e até 5 exemplos por sinal, com fonte
        e data. Só pessoa jurídica. A ordem é pelo número de sinais: é movimento passado, não intenção de
        compra (leia os `limits`)."""
        return await pedidos.pedir("compradores_do_setor", "/buyers", {
            "cnae": cnae,
            "state": uf,
            "years": None if anos is None else str(anos),
            "limit": None if limite is None else str(limite),
            "known_at": _dia(como_era_em),
        })  # fmt: skip

    @servidor.tool(annotations=SO_LEITURA, structured_output=False)
    async def fundo(
        cnpj: Cnpj,
        como_era_em: ComoEraEm = None,
        retorno_suposto: Annotated[
            float | None,
            Field(
                gt=-1,
                le=1,
                description=(
                    "Retorno anual suposto, em fração (0.10 = 10% ao ano), só para calcular quanto a "
                    "taxa custa em 5 e 20 anos. É uma hipótese de quem pergunta, não uma previsão."
                ),
            ),
        ] = None,
    ) -> str:
        """O raio-x de um fundo de investimento na CVM: cadastro (classe, situação, patrimônio e
        taxas), a carteira da competência mais nova já pública e, com `retorno_suposto`, o custo da
        taxa em 5 e 20 anos. Cada valor traz a fonte e o dia em que ficou público."""
        numeros = cnpj_do_pedido(cnpj)
        return await pedidos.pedir(
            "fundo",
            f"/funds/{numeros}",
            {
                "known_at": _dia(como_era_em),
                # como a CLI: o número como texto, sem arredondar
                "assumed_return": None
                if retorno_suposto is None
                else repr(retorno_suposto),
            },
        )
