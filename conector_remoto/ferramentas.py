"""As ferramentas do conector: todas só leem, e cada uma é um pedido à API externa com a chave do analista.

Nomes e descrições em português, para o analista ler no Claude ou no ChatGPT o que a IA está chamando;
os parâmetros viram os da API (em inglês) aqui. Cada ferramenta devolve o JSON da API como texto, já
limpo, conferido sem pessoa física e dentro do teto (`saida.preparar_saida`). Erro da API vira uma frase
em português que a IA pode repetir ao analista, sem nada da chave.
"""

import dataclasses
import json
import logging
import re
from collections.abc import Callable
from datetime import date
from typing import Annotated, Any, Literal, NoReturn

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from conector_remoto.acesso import acesso_do_pedido
from conector_remoto.cliente_api import ClienteDaApi, ParametroDaApi, RespostaDaApi
from conector_remoto.consultas_das_portas import (
    FERRAMENTAS,
    ORDENS_DA_BUSCA,
    PORTES,
    TIPOS_DA_ANVISA,
    TIPOS_DE_EVENTO,
    TIPOS_DE_VINCULO,
    chave_do_setor,
    ferramenta,
)
from conector_remoto.enxugar import (
    LIMITE_MAXIMO_DA_ANALISE,
    LIMITE_MAXIMO_DAS_ENTREGAS,
    LIMITE_MAXIMO_DOS_ATIVOS,
    LIMITE_PADRAO_DAS_ENTREGAS,
    avisar_novidades_vazias,
    cortar_entregas,
    enxugar_analise,
    enxugar_ativos,
    enxugar_demonstracoes,
)
from conector_remoto.pessoa import RespostaComPessoa, exigir_sem_pessoa
from conector_remoto.proximo_passo import com_proximo_passo
from conector_remoto.saida import (
    TETO_DE_CARACTERES,
    RespostaGrandeDemais,
    limpar_texto,
    preparar_saida,
    tamanho_em_caracteres,
)
from conector_remoto.socios_e_donos import (
    CAMINHO as CAMINHO_DAS_PESSOAS,
)
from conector_remoto.socios_e_donos import (
    CONJUNTO as CONJUNTO_DAS_PESSOAS,
)
from conector_remoto.socios_e_donos import preparar_pessoas

registro = logging.getLogger("conector_remoto")

SO_LEITURA = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
# o nome, o título, a descrição, os conjuntos e a dica de cada ferramenta vêm da lista única das portas
# (`conector_remoto/consultas_das_portas.py`, frente 2 do foco de 24/11/2026); estes dicionários são só atalhos para ela.
# A ferramenta aparece só para a chave que pode ver um dos conjuntos dela; vazio = sempre.
CONJUNTOS_DA_FERRAMENTA: dict[str, frozenset[str]] = {
    f.nome: f.conjuntos for f in FERRAMENTAS
}
# o nome que o analista vê no cliente (no Claude, ao lado de cada chamada): curto, em português, sem promessa
TITULOS_DAS_FERRAMENTAS: dict[str, str] = {f.nome: f.titulo for f in FERRAMENTAS}
# 12 caracteres (letras na raiz desde o CNPJ alfanumérico) e 2 dígitos verificadores; a API confere os DV
_CNPJ = re.compile(r"[0-9A-Z]{12}[0-9]{2}")
_PONTUACAO_DO_CNPJ = re.compile(r"[\s./-]")
_CODIGO_DA_API = re.compile(r"[a-z_]{1,40}")
LIMITE_MAXIMO_DA_BUSCA = 100
LIMITE_PADRAO_DA_BUSCA = 50
ESPERA_PADRAO_S = 60
# os mapas do português para a API (TIPOS_DE_EVENTO, TIPOS_DA_ANVISA...) vêm da lista única das portas, os mesmos
# da CLI
REGISTROS_MAXIMOS_DA_ANVISA = 10_000_000  # o teto da API para o mínimo de registros
PROFUNDIDADE_MAXIMA = 3  # a da API (`src/api_externa/conjuntos/vinculos.py`)
# os da API (`src/api_externa/conjuntos/compradores.py`)
ANOS_MAXIMO_DOS_COMPRADORES = 10
LIMITE_MAXIMO_DOS_COMPRADORES = 50
# Um evento pesa ~750 caracteres e a IA aceita ~150 mil por resposta: sem teto próprio, a 1ª página de uma
# companhia grande (1.000 eventos) passava do limite e a ferramenta falhava.
LIMITE_MAXIMO_DOS_EVENTOS = 100
LIMITE_PADRAO_DOS_EVENTOS = 50
DIAS_MAXIMO_DAS_NOVIDADES = 30  # o da API (`src/api_externa/conjuntos/novidades.py`)
# Um par pesa ~4 mil caracteres: os ~80 de um grupo grande (a CPFL deu ~322 mil) passavam do teto (ensaio de
# 16/11, linha 955). O corte é no conector: a API manda todos e calcula as medianas sobre todos.
LIMITE_MAXIMO_DOS_PARES = 50
LIMITE_PADRAO_DOS_PARES = 10
# O que dizer quando a resposta não cabe: só parâmetro que a ferramenta tem (um teste confere cada uma)
DICAS_DE_RESPOSTA_GRANDE: dict[str, str] = {
    f.nome: f.dica_se_grande for f in FERRAMENTAS if f.dica_se_grande is not None
}
DICA_SEM_PARAMETRO = "Esta ferramenta não tem como pedir menos: diga ao analista que este pedido não cabe na conversa."

MENSAGEM_DE_PESSOA = (
    "Resposta recusada: ela trazia um campo de pessoa física, que este conector não entrega. "
    "O TickerLab foi avisado; os outros pedidos seguem normais."
)
MENSAGEM_DE_PESSOA_PROIBIDA = (
    "Resposta recusada: ela trazia um dado que o conector nunca entrega (CPF, contato ou endereço). "
    "O TickerLab foi avisado; os outros pedidos seguem normais."
)
MENSAGEM_SEM_CHAVE = "Pedido sem chave do TickerLab: refaça a ligação do conector."
MENSAGEM_NAO_LIBERADA = "Esta ferramenta não está disponível para a chave usada."
# a pergunta "quanto a fechada fatura?" merece um "não temos" claro, não um vazio (linha 831, item d)
MENSAGEM_SEM_DEMONSTRACAO = (
    "Não disponível: a base só tem demonstrações financeiras de companhia aberta, entregues à CVM, "
    "e não as tem para esse pedido, ou a chave não tem acesso a elas (a API não diz qual dos dois, "
    "de propósito). Faturamento de empresa fechada a base não tem: capital social, porte e "
    "financiamento não são receita, e o TickerLab não estima."
)
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


def _portes_da_api(portes: list[str] | None) -> list[str] | None:
    """O porte como a API o recebe: o nome em português passa pelo mapa do registro; o da API segue igual."""
    return None if portes is None else [PORTES.get(porte, porte) for porte in portes]


def ferramenta_liberada(nome: str, conjuntos: frozenset[str]) -> bool:
    """A ferramenta existe e a chave pode ver pelo menos um dos conjuntos dela."""
    exigidos = CONJUNTOS_DA_FERRAMENTA.get(nome)
    if exigidos is None:
        return False
    return not exigidos or bool(exigidos & conjuntos)


def anunciar[F: Callable[..., Any]](servidor: MCPServer, nome: str) -> Callable[[F], F]:
    """Põe a ferramenta `nome` no servidor com o título e a descrição da lista única das portas (só leitura)."""
    do_registro = ferramenta(nome)
    return servidor.tool(
        name=nome,
        title=do_registro.titulo,
        description=do_registro.descricao,
        annotations=SO_LEITURA,
        structured_output=False,
    )


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
            "ele (a API não diz qual dos dois, de propósito). Para ver o que a chave enxerga, chame "
            "`o_que_posso_ver`; não estime o que faltou."
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


def mensagem_de_resposta_grande(ferramenta: str, tamanho: int) -> str:
    """A frase da resposta que passou do teto, com o jeito de pedir menos que essa ferramenta tem."""
    dica = DICAS_DE_RESPOSTA_GRANDE.get(ferramenta, DICA_SEM_PARAMETRO)
    return f"A resposta tem {tamanho} caracteres, grande demais para a conversa. {dica}"


def cortar_pares(corpo: object, limite: int) -> object:
    """Os `limite` primeiros pares, na ordem da API (pela receita, da maior para a menor, quando a chave
    pode ver a receita; senão pelo CNPJ), com `truncated` e o aviso
    em `limits` quando cortou. As medianas ficam como vieram: a API as calcula sobre todos os pares."""
    if not isinstance(corpo, dict):
        return corpo
    pares = corpo.get("peers")
    if not isinstance(pares, list) or len(pares) <= limite:
        return corpo
    limites = corpo.get("limits")
    aviso = (
        f"O conector entregou os {limite} primeiros dos {len(pares)} pares que a API mandou, na ordem dela "
        f"(pela receita, da maior para a menor, quando a chave pode vê-la; senão pelo CNPJ); peça mais com `limite` (até {LIMITE_MAXIMO_DOS_PARES}). As medianas em "
        "`peer_medians` usam todos os pares."
    )
    return corpo | {
        "peers": pares[:limite],
        "truncated": True,
        "limits": [*limites, aviso] if isinstance(limites, list) else [aviso],
    }


def _com_ativos_enxutos(
    resposta: RespostaDaApi,
    tipo: str | None,
    uf: str | None,
    so_operador: bool,
    limite: int | None,
) -> RespostaDaApi:
    """A resposta dos ativos no que cabe na conversa (`enxugar.py`); o resto fica como veio."""
    if not resposta.ok:
        return resposta
    corpo = enxugar_ativos(
        resposta.corpo, tipo=tipo, uf=uf, so_operador=so_operador, limite=limite
    )
    return dataclasses.replace(resposta, corpo=corpo)


def _com_entregas_cortadas(resposta: RespostaDaApi, limite: int) -> RespostaDaApi:
    """A resposta da ficha só com as entregas de DFP e ITR mais novas (o resto fica como veio)."""
    if not resposta.ok:
        return resposta
    return dataclasses.replace(resposta, corpo=cortar_entregas(resposta.corpo, limite))


def _com_demonstracoes_enxutas(
    resposta: RespostaDaApi,
    demonstrativo: str | None,
    visao: str,
    conta: str | None,
    periodo_pedido: bool,
) -> RespostaDaApi:
    """A resposta das demonstrações no que cabe na conversa (`enxugar.py`); o resto fica como veio."""
    if not resposta.ok:
        return resposta
    corpo = enxugar_demonstracoes(
        resposta.corpo,
        demonstrativo=demonstrativo,
        visao=visao,
        conta=conta,
        periodo_pedido=periodo_pedido,
    )
    return dataclasses.replace(resposta, corpo=corpo)


def _como_texto(corpo: object) -> str:
    return json.dumps(corpo, ensure_ascii=False, separators=(",", ":"))


def _dia(valor: date | None) -> str | None:
    return valor.isoformat() if valor else None


class Pedidos:
    """Faz o pedido da ferramenta à API com a chave do analista e prepara a resposta."""

    def __init__(self, cliente: ClienteDaApi, com_proximo_passo: bool = False) -> None:
        self._cliente = cliente
        self._com_proximo_passo = com_proximo_passo

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

    def conferir_pessoa(self, resposta: RespostaDaApi, ferramenta: str) -> None:
        """Só a trava de pessoa física, sem o teto de tamanho: para a resposta crua que a ferramenta compõe e não
        entrega inteira (a que vai à IA passa depois por `entregar`, com o teto)."""
        if not resposta.ok:
            return
        try:
            exigir_sem_pessoa(limpar_texto(resposta.corpo))
        except RespostaComPessoa as recusa:
            self._recusar_pessoa(ferramenta, recusa, MENSAGEM_DE_PESSOA)

    def _recusar_pessoa(
        self, ferramenta: str, recusa: RespostaComPessoa, frase: str
    ) -> NoReturn:
        acesso = acesso_do_pedido()
        registro.error(
            "resposta_com_pessoa_recusada",
            extra={
                "ferramenta": ferramenta,
                "caminhos": recusa.caminhos[:20],
                "chave": acesso.subject if acesso else None,
            },
        )
        raise ToolError(frase) from None

    def entregar(
        self,
        resposta: RespostaDaApi,
        ferramenta: str,
        preparar: Callable[[object], object] = preparar_saida,
        recusa_de_pessoa: str = MENSAGEM_DE_PESSOA,
    ) -> str:
        """O texto que vai para a IA, ou `ToolError` com a frase do problema. `preparar` é a tranca da
        saída: a de toda ferramenta recusa qualquer pessoa; a dos sócios e donos, só o que nunca sai."""
        if not resposta.ok:
            raise ToolError(mensagem_do_erro(resposta))
        try:
            saida = preparar(resposta.corpo)
            if self._com_proximo_passo:
                saida = com_proximo_passo(ferramenta, saida)
                if tamanho_em_caracteres(saida) > TETO_DE_CARACTERES:
                    raise RespostaGrandeDemais(tamanho_em_caracteres(saida))
            return _como_texto(saida)
        except RespostaComPessoa as recusa:
            self._recusar_pessoa(ferramenta, recusa, recusa_de_pessoa)
        except RespostaGrandeDemais as grande:
            raise ToolError(
                mensagem_de_resposta_grande(ferramenta, grande.tamanho)
            ) from None

    async def pedir(
        self,
        ferramenta: str,
        caminho: str,
        parametros: dict[str, ParametroDaApi] | None = None,
    ) -> str:
        """Pede e entrega: o caminho comum de quase toda ferramenta."""
        return self.entregar(await self.resposta(caminho, parametros), ferramenta)


def _pode_ver_pessoas() -> bool:
    """A chave deste pedido lista a permissão de pessoa física no catálogo (a API confere de novo no `/people`)."""
    acesso = acesso_do_pedido()
    return acesso is not None and CONJUNTO_DAS_PESSOAS in acesso.conjuntos


async def pedir_pessoas(pedidos: Pedidos, numeros: str) -> str:
    """Os sócios e donos do CNPJ (já sem pontuação), com a tranca própria da pessoa física. É o encaixe da
    análise completa do CNPJ: a mesma chamada, a mesma tranca. `ToolError` quando a API não serve (a chave sem
    a permissão recebe o mesmo "não disponível" de um dado que não existe)."""
    resposta = await pedidos.resposta(CAMINHO_DAS_PESSOAS.format(numeros=numeros))
    return pedidos.entregar(
        resposta, "socios_e_donos", preparar_pessoas, MENSAGEM_DE_PESSOA_PROIBIDA
    )


def registrar_ferramentas(
    servidor: MCPServer, cliente: ClienteDaApi, com_proximo_passo: bool = False
) -> None:
    """Põe as ferramentas no servidor (a lista de cada chave é filtrada no `ServidorDoConector`).

    `com_proximo_passo` liga o rodapé das listas (`proximo_passo.py`): só o conector o quer, porque o texto
    cita ferramentas que o chat do app não tem."""
    pedidos = Pedidos(cliente, com_proximo_passo)

    @anunciar(servidor, "buscar_empresas")
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
                description="Municípios pelo código da Receita (4 dígitos) ou pelo nome; vale junto com a UF."
            ),
        ] = None,
        porte: Annotated[
            list[
                Literal[
                    "micro",
                    "pequena",
                    "demais",
                    "nao_informado",
                    "small",
                    "other",
                    "not_informed",
                ]
            ]
            | None,
            Field(
                description=(
                    "Porte na Receita: micro, pequena, demais (os demais; a Receita não tem 'médio' nem "
                    "'grande') ou nao_informado. Os nomes da API (small, other, not_informed) também valem."
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
        anvisa_tipo: Annotated[
            Literal["cosmeticos", "produtos_saude", "saneantes", "todos"] | None,
            Field(
                description=(
                    "Tipo de registro na Anvisa que os mínimos abaixo contam: cosmeticos, produtos_saude, "
                    "saneantes ou todos (a soma dos três; é o padrão quando só o mínimo vem)."
                )
            ),
        ] = None,
        anvisa_ativos_min: Annotated[
            int | None,
            Field(
                ge=1,
                le=REGISTROS_MAXIMOS_DA_ANVISA,
                description="Só empresas com pelo menos este número de registros ativos na Anvisa.",
            ),
        ] = None,
        anvisa_total_min: Annotated[
            int | None,
            Field(
                ge=1,
                le=REGISTROS_MAXIMOS_DA_ANVISA,
                description="Só empresas com pelo menos este número de registros na Anvisa, ativos ou não.",
            ),
        ] = None,
        ordenar_por: Annotated[
            Literal["anvisa"] | None,
            Field(
                description="Em vez de por CNPJ: 'anvisa' põe primeiro quem tem mais registros ativos na Anvisa."
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
        return await pedidos.pedir(
            "buscar_empresas",
            "/companies",
            {
                "cnae": cnae, "state": uf, "municipality": municipio, "size": _portes_da_api(porte),
                "legal_nature": natureza_juridica, "registration_status": situacao_cadastral,
                "opened_before": _dia(aberta_antes_de), "opened_after": _dia(aberta_depois_de),
                "head_office": so_matriz, "limit": limite, "cursor": cursor,
                "known_at": _dia(como_era_em),
                "anvisa_type": TIPOS_DA_ANVISA.get(anvisa_tipo or ""),
                "anvisa_active_min": anvisa_ativos_min, "anvisa_total_min": anvisa_total_min,
                "sort": ORDENS_DA_BUSCA.get(ordenar_por or ""),
            },
        )  # fmt: skip

    @anunciar(servidor, "ficha_da_empresa")
    async def ficha_da_empresa(
        cnpj: Cnpj,
        como_era_em: ComoEraEm = None,
        limite_de_entregas: Annotated[
            int,
            Field(
                ge=1,
                le=LIMITE_MAXIMO_DAS_ENTREGAS,
                description="Quantas entregas de DFP e ITR trazer, das mais novas para as mais velhas (companhia aberta).",
            ),
        ] = LIMITE_PADRAO_DAS_ENTREGAS,
    ) -> str:
        numeros = cnpj_do_pedido(cnpj)
        dia: dict[str, ParametroDaApi] = {"known_at": _dia(como_era_em)}
        acesso = acesso_do_pedido()
        conjuntos = acesso.conjuntos if acesso else frozenset()
        if "profiles" in conjuntos:
            resposta = await pedidos.resposta(f"/companies/{numeros}/profile", dia)
            if resposta.status != STATUS_NAO_DISPONIVEL or "companies" not in conjuntos:
                return pedidos.entregar(
                    _com_entregas_cortadas(resposta, limite_de_entregas),
                    "ficha_da_empresa",
                )
        resposta = await pedidos.resposta(f"/companies/{numeros}", dia)
        return pedidos.entregar(
            _com_entregas_cortadas(resposta, limite_de_entregas), "ficha_da_empresa"
        )

    @anunciar(servidor, "comparaveis")
    async def comparaveis(
        cnpj: Cnpj,
        como_era_em: ComoEraEm = None,
        limite: Annotated[
            int,
            Field(
                ge=1,
                le=LIMITE_MAXIMO_DOS_PARES,
                description="Quantos pares entregar (até 50), na ordem da API: pela receita, ou pelo CNPJ se a chave não a vê.",
            ),
        ] = LIMITE_PADRAO_DOS_PARES,
    ) -> str:
        numeros = cnpj_do_pedido(cnpj)
        resposta = await pedidos.resposta(
            f"/companies/{numeros}/comparables", {"known_at": _dia(como_era_em)}
        )
        if resposta.ok:
            resposta = dataclasses.replace(
                resposta, corpo=cortar_pares(resposta.corpo, limite)
            )
        return pedidos.entregar(resposta, "comparaveis")

    @anunciar(servidor, "demonstracoes")
    async def demonstracoes(
        cnpj: Cnpj,
        como_era_em: ComoEraEm = None,
        fim_do_periodo: Annotated[
            date | None,
            Field(
                description="Só o período que termina neste dia (AAAA-MM-DD), ex.: 2025-12-31. Sem ele vem o mais novo."
            ),
        ] = None,
        demonstrativo: Annotated[
            str | None,
            Field(
                pattern=r"^[A-Za-z_]{2,8}$",
                description="Só um demonstrativo: DRE, BPA, BPP, DFC, DVA ou DRA. Sem ele vêm todos, na ordem, até caber.",
            ),
        ] = None,
        visao: Annotated[
            Literal["consolidado", "individual", "ambos"],
            Field(
                description="`consolidado` (o padrão: o consolidado de cada demonstrativo e, no que não tem consolidado, o individual), `individual` ou `ambos`."
            ),
        ] = "consolidado",
        conta: Annotated[
            str | None,
            Field(
                pattern=r"^[0-9]{1,2}(\.[0-9]{1,2}){0,5}$",
                description="Só esta conta e as de dentro dela, pelo código do plano de contas da CVM, ex.: 3.01.",
            ),
        ] = None,
    ) -> str:
        numeros = cnpj_do_pedido(cnpj)
        resposta = await pedidos.resposta(
            f"/companies/{numeros}/financials",
            {"known_at": _dia(como_era_em), "period_end": _dia(fim_do_periodo)},
        )
        if resposta.status == STATUS_NAO_DISPONIVEL:
            raise ToolError(MENSAGEM_SEM_DEMONSTRACAO)
        enxuta = _com_demonstracoes_enxutas(
            resposta, demonstrativo, visao, conta, fim_do_periodo is not None
        )
        return pedidos.entregar(enxuta, "demonstracoes")

    _registrar_eventos_rede_e_fundo(servidor, pedidos)
    _registrar_novidades(servidor, pedidos)
    _registrar_analise(servidor, pedidos)
    # linha 980: as ferramentas que só compõem o que a API devolve; import aqui por causa do ciclo (o módulo
    # delas usa `Pedidos` e os tipos deste)
    from conector_remoto import ferramentas_do_analista

    ferramentas_do_analista.registrar(servidor, pedidos)

    @anunciar(servidor, "setores")
    async def setores() -> str:
        return await pedidos.pedir("setores", "/sectors")

    @anunciar(servidor, "setor")
    async def setor(
        chave: Annotated[
            str,
            Field(
                max_length=80, description="A chave do setor, da lista de `setores`."
            ),
        ],
        como_era_em: ComoEraEm = None,
    ) -> str:
        da_api = chave_do_setor(chave)
        if da_api is None:
            raise ToolError(
                "Chave de setor inválida; use uma chave da lista de `setores`."
            )
        return await pedidos.pedir(
            "setor", f"/sectors/{da_api}", {"known_at": _dia(como_era_em)}
        )

    @anunciar(servidor, "o_que_posso_ver")
    async def o_que_posso_ver() -> str:
        catalogo = await pedidos.resposta("/catalog")
        consumo = await pedidos.resposta("/usage")
        for resposta in (catalogo, consumo):
            if not resposta.ok:
                raise ToolError(mensagem_do_erro(resposta))
        juntos = RespostaDaApi(
            STATUS_OK, {"catalog": catalogo.corpo, "usage": consumo.corpo}
        )
        return pedidos.entregar(juntos, "o_que_posso_ver")


def _registrar_analise(servidor: MCPServer, pedidos: Pedidos) -> None:
    """A análise completa do CNPJ (frente 3): um pedido à API, que junta os blocos que a chave vê."""

    @anunciar(servidor, "analise_completa")
    async def analise_completa(
        cnpj: Cnpj,
        como_era_em: ComoEraEm = None,
        blocos: Annotated[
            list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")]] | None,
            Field(
                max_length=30,
                description="Só estes blocos da análise, pelos nomes de `blocks` (ex.: profile, links, credit). Vazio = todos, até caber.",
            ),
        ] = None,
        limite: Annotated[
            int | None,
            Field(
                ge=1,
                le=LIMITE_MAXIMO_DA_ANALISE,
                description="No máximo tantos itens por lista (as entregas do cadastro, os vínculos, os eventos...). Vazio = o que couber.",
            ),
        ] = None,
    ) -> str | list[str]:
        numeros = cnpj_do_pedido(cnpj)
        resposta = await pedidos.resposta(
            f"/companies/{numeros}/analysis", {"known_at": _dia(como_era_em)}
        )
        # a trava de pessoa lê a análise inteira, também o que o corte deixa de fora
        pedidos.conferir_pessoa(resposta, "analise_completa")
        if resposta.ok:
            resposta = dataclasses.replace(
                resposta,
                corpo=enxugar_analise(resposta.corpo, blocos=blocos, limite=limite),
            )
        analise = pedidos.entregar(resposta, "analise_completa")
        if como_era_em is not None or not _pode_ver_pessoas():
            return analise
        try:
            return [analise, await pedir_pessoas(pedidos, numeros)]
        except ToolError:
            # sem a permissão no servidor (404), acervo fora do ar (503) ou resposta recusada pela tranca:
            # a análise vale sozinha, e a tranca já registrou o motivo, sem o valor
            return analise


def _registrar_novidades(servidor: MCPServer, pedidos: Pedidos) -> None:
    """A ferramenta das novidades da pesquisa (linha 830)."""

    @anunciar(servidor, "novidades")
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
        resposta = await pedidos.resposta("/research/news", {
            "days": None if dias is None else str(dias),
        })  # fmt: skip
        if resposta.ok:
            resposta = dataclasses.replace(
                resposta, corpo=avisar_novidades_vazias(resposta.corpo)
            )
        return pedidos.entregar(resposta, "novidades")


def _registrar_eventos_rede_e_fundo(servidor: MCPServer, pedidos: Pedidos) -> None:
    """Eventos, vínculos, ativos, compradores do setor e fundo (à parte, para a
    `registrar_ferramentas` não crescer demais); chamada no meio dela, para a ordem da lista ficar."""

    @anunciar(servidor, "eventos")
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
        limite: Annotated[
            int,
            Field(
                ge=1,
                le=LIMITE_MAXIMO_DOS_EVENTOS,
                description="Eventos por página (até 100).",
            ),
        ] = LIMITE_PADRAO_DOS_EVENTOS,
        cursor: Annotated[
            str | None,
            Field(
                max_length=200,
                description="O `next_cursor` da página anterior, para a seguinte.",
            ),
        ] = None,
        como_era_em: ComoEraEm = None,
    ) -> str:
        numeros = cnpj_do_pedido(cnpj)
        return await pedidos.pedir("eventos", f"/companies/{numeros}/events", {
            "types": [TIPOS_DE_EVENTO[tipo] for tipo in tipos or ()],
            "limit": str(limite),
            "cursor": cursor,
            "known_at": _dia(como_era_em),
        })  # fmt: skip

    @anunciar(servidor, "vinculos")
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
        numeros = cnpj_do_pedido(cnpj)
        return await pedidos.pedir("vinculos", f"/companies/{numeros}/links", {
            "known_at": _dia(como_era_em),
            "depth": str(profundidade),  # como a CLI
            "types": [TIPOS_DE_VINCULO[tipo] for tipo in tipos or ()],
        })  # fmt: skip

    @anunciar(servidor, "socios_e_donos")
    async def socios_e_donos(cnpj: Cnpj) -> str:
        return await pedir_pessoas(pedidos, cnpj_do_pedido(cnpj))

    @anunciar(servidor, "ativos")
    async def ativos(
        cnpj: Cnpj,
        como_era_em: ComoEraEm = None,
        tipo_de_ativo: Annotated[
            Literal["petroleo_e_gas", "barragens", "royalties"] | None,
            Field(
                description="Só um tipo de ativo: contratos de petróleo e gás, barragens de mineração ou royalties de mineração."
            ),
        ] = None,
        uf: Annotated[
            str | None,
            Field(
                pattern=r"^[A-Za-z]{2}$",
                description="Só os itens dessa UF (sigla, ex.: MG). Vale para barragens e royalties; os contratos de petróleo e gás não têm UF.",
            ),
        ] = None,
        somente_operador: Annotated[
            bool,
            Field(
                description="Só os contratos de petróleo e gás em que a empresa é a operadora."
            ),
        ] = False,
        limite: Annotated[
            int | None,
            Field(
                ge=1,
                le=LIMITE_MAXIMO_DOS_ATIVOS,
                description="No máximo quantos itens trazer por bloco, na ordem da API. Sem ele, vai o que couber na conversa.",
            ),
        ] = None,
    ) -> str:
        numeros = cnpj_do_pedido(cnpj)
        resposta = await pedidos.resposta(
            f"/companies/{numeros}/assets", {"known_at": _dia(como_era_em)}
        )
        return pedidos.entregar(
            _com_ativos_enxutos(resposta, tipo_de_ativo, uf, somente_operador, limite),
            "ativos",
        )

    @anunciar(servidor, "compradores_do_setor")
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
        return await pedidos.pedir("compradores_do_setor", "/buyers", {
            "cnae": cnae,
            "state": uf,
            "years": None if anos is None else str(anos),
            "limit": None if limite is None else str(limite),
            "known_at": _dia(como_era_em),
        })  # fmt: skip

    @anunciar(servidor, "fundo")
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
