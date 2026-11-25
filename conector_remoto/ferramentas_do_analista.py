"""As ferramentas do analista que só compõem o que a API já devolve (linha 980, onda 1).

Cada uma é um ou mais pedidos à API pelo `ClienteDaApi`, com a chave do analista, e passa pela mesma
tranca de saída das outras (`Pedidos.entregar`: texto limpo, sem pessoa, dentro do teto). Nenhuma abre rota
nem direito novo: o que a chave não vê a API já nega, e a ferramenta some da lista de quem não tem o
conjunto. O título, a descrição e os conjuntos de cada uma ficam na lista única das portas
(`conector_remoto/consultas_das_portas.py`).
"""

import asyncio
import dataclasses
import json
import re
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from conector_remoto.acesso import acesso_do_pedido
from conector_remoto.cliente_api import ParametroDaApi, RespostaDaApi
from conector_remoto.enxugar import LIMITE_MAXIMO_DAS_MUDANCAS, enxugar_o_que_mudou
from conector_remoto.ferramentas import (
    STATUS_NAO_DISPONIVEL,
    STATUS_OK,
    Cnpj,
    ComoEraEm,
    Pedidos,
    anunciar,
    cnpj_do_pedido,
    mensagem_do_erro,
)


def _hoje() -> date:
    """O dia de hoje (UTC), para recusar um `desde` que não é passado."""
    return datetime.now(UTC).date()


def _dia(valor: date | None) -> str | None:
    """O dia como a API o pede (AAAA-MM-DD), ou None se não veio."""
    return valor.isoformat() if valor else None


def registrar(servidor: MCPServer, pedidos: Pedidos) -> None:
    """Põe as ferramentas do analista no servidor (chamada por `registrar_ferramentas`)."""
    _registrar_credito(servidor, pedidos)
    _registrar_o_que_mudou(servidor, pedidos)
    _registrar_comparar_empresas(servidor, pedidos)
    _registrar_de_onde_vem(servidor, pedidos)


def _registrar_credito(servidor: MCPServer, pedidos: Pedidos) -> None:
    """Os fatos de crédito da rota `/credit` (conjunto `credit`)."""

    @anunciar(servidor, "credito_da_empresa")
    async def credito_da_empresa(cnpj: Cnpj, como_era_em: ComoEraEm = None) -> str:
        numeros = cnpj_do_pedido(cnpj)
        return await pedidos.pedir(
            "credito_da_empresa", f"/credit/{numeros}", {"known_at": _dia(como_era_em)}
        )


# ---------------------------------------------------------------- o_que_mudou
#
# Compara o que a API devolvia com `known_at = desde` e o que devolve hoje, em até três blocos (o que a chave
# vê): o cadastro (a ficha), os vínculos e os eventos. Nada aqui consulta o que a API não consulta: são os
# mesmos caminhos das ferramentas `ficha_da_empresa`, `vinculos` e `eventos`.

CONJUNTOS_DO_BLOCO: dict[str, frozenset[str]] = {
    "registration": frozenset({"profiles", "companies"}),
    "links": frozenset({"links"}),
    "events": frozenset({"events"}),
}
# a lista de cada bloco que se compara item a item (o cadastro compara também campo a campo)
LISTA_DO_BLOCO = {
    "registration": "periodic_filings",
    "links": "links",
    "events": "events",
}
PROVENIENCIA = frozenset({"source", "published_at", "observed_at"})
# o mês do retrato da Receita diz qual retrato a base leu, não o que mudou na empresa: fora da comparação
CAMPOS_DO_RETRATO = frozenset({"snapshot_month", "registry_snapshot_month"})
# o campo que faz um item existir naquele dia (o vínculo existe pelo `kind`, que vem do FRE ou do FCA): se ele
# ficou público depois de `desde`, o item inteiro é do futuro, ainda que as pontas tenham datas antigas
DEFINIDOR_DO_ITEM = {"links": "kind"}
EVENTOS_POR_BLOCO = (
    100  # a página cheia da API: quem tem mais que isso recebe `partial`
)
MOTIVO_SEM_CONJUNTO = "not_in_key"
MOTIVO_NAO_PEDIDO = "not_requested"
# o nome que o analista usa (o mesmo da CLI e da descrição) -> o bloco do `o_que_mudou`
BLOCOS_PEDIDOS = {
    "cadastro": "registration",
    "vinculos": "links",
    "eventos": "events",
}
MOTIVO_NAO_DISPONIVEL = "not_available"
AVISO_DA_FERRAMENTA = {
    "code": "o_que_mudou",
    "text": (
        "Compara o que a base sabia no dia pedido com o que sabe hoje. Mudança na empresa que ainda não "
        "foi publicada na base não aparece, e o que a chave não vê vem em `not_consulted`."
    ),
}
AVISO_DE_PAGINA_CHEIA = {
    "code": "partial",
    "text": (
        f"A API entrega até {EVENTOS_POR_BLOCO} itens por pedido: nos blocos com `partial`, o que passou "
        "disso não foi comparado e `removed` não lista o que saiu da lista, só o que mudou ou entrou."
    ),
}


@dataclasses.dataclass(frozen=True)
class Retrato:
    """O que um bloco dizia num dia: os campos com envelope (`folhas`, pelo caminho) e a lista de itens."""

    folhas: dict[str, dict]
    itens: list[dict]
    cortado: bool


def _e_envelope(no: object) -> bool:
    return isinstance(no, dict) and "value" in no and "published_at" in no


def _depois_de(dia: object, limite: str) -> bool:
    return isinstance(dia, str) and dia[:10] > limite


def _folhas(no: object, caminho: str = "") -> dict[str, dict]:
    """Os campos com envelope de um bloco, pelo caminho (`legal_name`, `address.city`); as listas ficam de fora."""
    if _e_envelope(no):
        return {caminho: no}
    if not isinstance(no, dict):
        return {}
    achadas: dict[str, dict] = {}
    for chave, filho in no.items():
        if chave not in CAMPOS_DO_RETRATO:
            achadas |= _folhas(filho, f"{caminho}.{chave}" if caminho else chave)
    return achadas


def _itens(corpo: dict, lista: str) -> list[dict]:
    achados = corpo.get(lista)
    return (
        [i for i in achados if isinstance(i, dict)] if isinstance(achados, list) else []
    )


def _retrato(bloco: str, corpo: object) -> Retrato:
    """O bloco como a API o devolveu, separado em campos e itens. O cadastro vem em `registration`, ou plano."""
    if not isinstance(corpo, dict):
        return Retrato({}, [], False)
    cadastro = corpo.get("registration") if bloco == "registration" else None
    base = cadastro if isinstance(cadastro, dict) else corpo
    folhas = _folhas(base) if bloco == "registration" else {}
    return Retrato(
        folhas, _itens(corpo, LISTA_DO_BLOCO[bloco]), corpo.get("truncated") is True
    )


def _datas(no: object) -> Iterator[str]:
    """Os dias em que algo ficou público dentro de `no` (cada envelope e o `published_at` solto do item)."""
    if isinstance(no, dict):
        if isinstance(no.get("published_at"), str):
            yield no["published_at"][:10]
        for chave, filho in no.items():
            if chave != "published_at":
                yield from _datas(filho)
    elif isinstance(no, list):
        for filho in no:
            yield from _datas(filho)


def _sem_envelopes_depois_de(no: object, limite: str) -> object:
    if isinstance(no, dict):
        return {
            chave: _sem_envelopes_depois_de(filho, limite)
            for chave, filho in no.items()
            if not (_e_envelope(filho) and _depois_de(filho["published_at"], limite))
        }
    if isinstance(no, list):
        return [_sem_envelopes_depois_de(filho, limite) for filho in no]
    return no


def _item_ate(item: dict, limite: str, definidor: str | None = None) -> dict | None:
    """O item sem o que ficou público depois de `limite`; None se o campo que o define, ou tudo o que tem de
    datado, é posterior."""
    marca = item.get(definidor) if definidor else None
    if isinstance(marca, dict) and _depois_de(marca.get("published_at"), limite):
        return None
    datas = list(_datas(item))
    if datas and all(dia > limite for dia in datas):
        return None
    podado = _sem_envelopes_depois_de(item, limite)
    return podado if isinstance(podado, dict) else None


def _ate_o_dia(bloco: str, retrato: Retrato, limite: str) -> Retrato:
    """O retrato do dia `limite`: se a API deixou passar algo publicado depois dele, sai daqui (sem olhar o futuro)."""
    folhas = {
        campo: envelope
        for campo, envelope in retrato.folhas.items()
        if not _depois_de(envelope["published_at"], limite)
    }
    definidor = DEFINIDOR_DO_ITEM.get(bloco)
    itens = [
        podado for i in retrato.itens if (podado := _item_ate(i, limite, definidor))
    ]
    return dataclasses.replace(retrato, folhas=folhas, itens=itens)


def _valores(no: object) -> object:
    """O que o dado diz, sem a fonte nem o dia: é o que se compara (republicar o mesmo valor não é mudança)."""
    if _e_envelope(no):
        return no["value"]
    if isinstance(no, dict):
        return {
            c: _valores(f)
            for c, f in no.items()
            if c not in PROVENIENCIA | CAMPOS_DO_RETRATO
        }
    if isinstance(no, list):
        return [_valores(f) for f in no]
    return no


def _identidade_padrao(item: dict) -> str:
    return json.dumps(_valores(item), sort_keys=True, ensure_ascii=False)


def _ponta(ponta: object) -> str | None:
    if not isinstance(ponta, dict):
        return None
    achada = ponta.get("entity_id") or ponta.get("cnpj_root") or ponta.get("id")
    return str(achada) if achada else None


def _identidade_do_vinculo(item: dict) -> str:
    """O vínculo é o mesmo se tem o tipo, as duas pontas e o começo iguais; a participação e o fim podem ter
    mudado. O começo entra porque a rede pode ter duas linhas do mesmo tipo e das mesmas pontas."""
    tipo, de, para = (
        _valores(item.get("kind")),
        _ponta(item.get("from")),
        _ponta(item.get("to")),
    )
    if tipo and de and para:
        return json.dumps(
            [tipo, de, para, _valores(item.get("valid_from"))], ensure_ascii=False
        )
    return _identidade_padrao(item)


def _identidade_da_entrega(item: dict) -> str:
    """A entrega de DFP ou ITR é o mesmo documento do mesmo período; a situação e o atraso mudam com o dia."""
    documento, periodo = (
        _valores(item.get("document")),
        _valores(item.get("reference_period")),
    )
    if documento and periodo:
        return json.dumps([documento, periodo], ensure_ascii=False)
    return _identidade_padrao(item)


IDENTIDADE_DO_BLOCO: dict[str, Callable[[dict], str]] = {
    "registration": _identidade_da_entrega,
    "links": _identidade_do_vinculo,
    "events": _identidade_padrao,
}


def _diferenca_dos_campos(
    antes: Retrato | None, depois: Retrato | None
) -> dict[str, list[dict]]:
    antigos = antes.folhas if antes else {}
    atuais = depois.folhas if depois else {}
    saida: dict[str, list[dict]] = {"changed": [], "added": [], "removed": []}
    for campo in sorted(antigos.keys() | atuais.keys()):
        antigo, atual = antigos.get(campo), atuais.get(campo)
        if antigo is None:
            saida["added"].append({"field": campo, "after": atual})
        elif atual is None:
            saida["removed"].append({"field": campo, "before": antigo})
        elif _valores(antigo) != _valores(atual):
            saida["changed"].append({"field": campo, "before": antigo, "after": atual})
    return saida


def _diferenca_dos_itens(
    lista: str,
    identidade: Callable[[dict], str],
    antes: Retrato | None,
    depois: Retrato | None,
    pagina_inteira: bool,
) -> dict[str, list[dict]]:
    antigos = {identidade(i): i for i in (antes.itens if antes else [])}
    atuais = {identidade(i): i for i in (depois.itens if depois else [])}
    saida: dict[str, list[dict]] = {"changed": [], "added": [], "removed": []}
    for chave, atual in atuais.items():
        antigo = antigos.get(chave)
        if antigo is None:
            saida["added"].append({"field": lista, "item": atual})
        elif _valores(antigo) != _valores(atual):
            saida["changed"].append({"field": lista, "before": antigo, "after": atual})
    # com a página cheia o que sobrou fora dela não saiu da base: não se pode dizer que saiu
    if pagina_inteira:
        saida["removed"] = [
            {"field": lista, "item": antigo}
            for chave, antigo in antigos.items()
            if chave not in atuais
        ]
    return saida


def _comparar(
    bloco: str, antes: Retrato | None, depois: Retrato | None
) -> dict[str, object]:
    """A diferença de um bloco entre os dois dias. `antes` ou `depois` None = a API não serviu aquele dia."""
    cortado = any(r is not None and r.cortado for r in (antes, depois))
    campos = _diferenca_dos_campos(antes, depois)
    itens = _diferenca_dos_itens(
        LISTA_DO_BLOCO[bloco], IDENTIDADE_DO_BLOCO[bloco], antes, depois, not cortado
    )
    resultado: dict[str, object] = {tipo: campos[tipo] + itens[tipo] for tipo in campos}
    if antes is None:
        resultado["before_not_available"] = True
    if depois is None:
        resultado["after_not_available"] = True
    if cortado:
        resultado["partial"] = True
    return resultado


def _quantas(diferenca: dict[str, object]) -> int:
    return sum(len(diferenca[tipo]) for tipo in ("changed", "added", "removed"))


def _pedido_do_bloco(
    bloco: str, numeros: str, dia: str | None, conjuntos: frozenset[str]
) -> tuple[str, dict[str, ParametroDaApi]]:
    """O caminho e os parâmetros do bloco, os mesmos das ferramentas `ficha_da_empresa`, `vinculos` e `eventos`."""
    base = f"/companies/{numeros}"
    if bloco == "links":
        return f"{base}/links", {"known_at": dia, "depth": "1"}
    if bloco == "events":
        return f"{base}/events", {"known_at": dia, "limit": str(EVENTOS_POR_BLOCO)}
    caminho = f"{base}/profile" if "profiles" in conjuntos else base
    return caminho, {"known_at": dia}


async def _buscar(
    pedidos: Pedidos,
    bloco: str,
    numeros: str,
    dia: str | None,
    conjuntos: frozenset[str],
) -> RespostaDaApi:
    caminho, parametros = _pedido_do_bloco(bloco, numeros, dia, conjuntos)
    resposta = await pedidos.resposta(caminho, parametros)
    reserva = (
        bloco == "registration" and "profiles" in conjuntos and "companies" in conjuntos
    )
    if reserva and resposta.status == STATUS_NAO_DISPONIVEL:
        # a ficha cai no cadastro plano quando não há perfil (a mesma regra de `ficha_da_empresa`)
        resposta = await pedidos.resposta(f"/companies/{numeros}", parametros)
    return resposta


def juntar_sem_repetir(corpos: list[object], chave: str) -> list[object]:
    """Os `limits` ou `sources` de todas as respostas, na ordem em que apareceram e sem repetir."""
    vistos: dict[str, object] = {}
    for corpo in corpos:
        achados = corpo.get(chave) if isinstance(corpo, dict) else None
        for item in achados if isinstance(achados, list) else []:
            vistos.setdefault(
                json.dumps(item, sort_keys=True, ensure_ascii=False), item
            )
    return list(vistos.values())


class EmpresaNaoDisponivel(ToolError):
    """A base não serve nenhum bloco da empresa nos dois dias (a mesma frase do 404 das outras ferramentas)."""


@dataclasses.dataclass(frozen=True)
class DoisDias:
    """As respostas de um bloco, uma por dia (`desde` e hoje)."""

    antes: RespostaDaApi
    depois: RespostaDaApi


def _exigir_que_a_api_serviu(respostas: list[DoisDias]) -> None:
    """Só 200 e 404 entregam: qualquer outra coisa (limite, chave, API fora) para tudo, em vez de omitir o bloco."""
    for dois in respostas:
        for resposta in (dois.antes, dois.depois):
            if not resposta.ok and resposta.status != STATUS_NAO_DISPONIVEL:
                raise ToolError(mensagem_do_erro(resposta))


def _montar_a_saida(
    numeros: str,
    desde: date,
    blocos: dict[str, DoisDias | None],
    fora_do_pedido: tuple[str, ...] = (),
) -> dict[str, object]:
    """A resposta da ferramenta, de cada bloco consultado (`None` = a chave não vê o conjunto dele);
    `fora_do_pedido` são os blocos que o analista deixou de pedir (`blocos`)."""
    saida: dict[str, object] = {}
    nao_consultados: list[dict[str, str]] = [
        {"block": bloco, "reason": MOTIVO_NAO_PEDIDO} for bloco in fora_do_pedido
    ]
    todos: list[object] = []
    achadas = 0
    for bloco, dois in blocos.items():
        if dois is None:
            nao_consultados.append({"block": bloco, "reason": MOTIVO_SEM_CONJUNTO})
            continue
        if not dois.antes.ok and not dois.depois.ok:
            nao_consultados.append({"block": bloco, "reason": MOTIVO_NAO_DISPONIVEL})
            continue
        antes = (
            _ate_o_dia(bloco, _retrato(bloco, dois.antes.corpo), desde.isoformat())
            if dois.antes.ok
            else None
        )
        depois = _retrato(bloco, dois.depois.corpo) if dois.depois.ok else None
        saida[bloco] = diferenca = _comparar(bloco, antes, depois)
        achadas += _quantas(diferenca)
        todos += [r.corpo for r in (dois.antes, dois.depois) if r.ok]
    if not saida:
        raise EmpresaNaoDisponivel(
            mensagem_do_erro(
                RespostaDaApi(STATUS_NAO_DISPONIVEL, {"detail": MOTIVO_NAO_DISPONIVEL})
            )
        )
    parcial = any(isinstance(d, dict) and d.get("partial") for d in saida.values())
    atual = next(
        (
            b.depois.corpo.get("known_at")
            for b in blocos.values()
            if b and b.depois.ok and isinstance(b.depois.corpo, dict)
        ),
        None,
    )
    return {
        "cnpj": numeros,
        "since": desde.isoformat(),
        "until": atual or _hoje().isoformat(),
        "changes_found": achadas,
        **saida,
        "not_consulted": nao_consultados,
        "limits": [
            *juntar_sem_repetir(todos, "limits"),
            AVISO_DA_FERRAMENTA,
            *([AVISO_DE_PAGINA_CHEIA] if parcial else []),
        ],
        "sources": juntar_sem_repetir(todos, "sources"),
    }


Desde = Annotated[
    date,
    Field(
        description=(
            "O dia (AAAA-MM-DD) de onde comparar: o que a base sabia nesse dia contra o que sabe hoje. "
            "Tem de ser anterior a hoje."
        )
    ),
]


BlocosPedidos = Annotated[
    list[Literal["cadastro", "vinculos", "eventos"]] | None,
    Field(
        description=(
            "Só estes blocos: cadastro, vinculos e/ou eventos. Sem ele, vão todos os que a chave vê; pedir um "
            "bloco por vez dá a cada um o espaço inteiro da resposta."
        )
    ),
]
LimiteDeMudancas = Annotated[
    int | None,
    Field(
        ge=1,
        le=LIMITE_MAXIMO_DAS_MUDANCAS,
        description=(
            "No máximo quantas mudanças trazer por lista (alteradas, novas e removidas de cada bloco). "
            "Sem ele, vai o que couber na conversa."
        ),
    ),
]


def _blocos_do_pedido(
    blocos: list[str] | None, conjuntos: frozenset[str]
) -> tuple[list[str], tuple[str, ...]]:
    """Os blocos que a chave vê e o analista pediu, e os que ele não pediu (na ordem do bloco)."""
    pedidos_ = (
        {BLOCOS_PEDIDOS[b] for b in blocos} if blocos else set(CONJUNTOS_DO_BLOCO)
    )
    visiveis = [
        b
        for b, exigidos in CONJUNTOS_DO_BLOCO.items()
        if exigidos & conjuntos and b in pedidos_
    ]
    return visiveis, tuple(b for b in CONJUNTOS_DO_BLOCO if b not in pedidos_)


def blocos_visiveis(blocos: list[str] | None, conjuntos: frozenset[str]) -> list[str]:
    """Os blocos (nomes da API) que a chave vê entre os que o analista pediu (todos, se não pediu)."""
    return _blocos_do_pedido(blocos, conjuntos)[0]


def _registrar_o_que_mudou(servidor: MCPServer, pedidos: Pedidos) -> None:
    """A diferença do cadastro, dos vínculos e dos eventos entre um dia passado e hoje."""

    @anunciar(servidor, "o_que_mudou")
    async def o_que_mudou(
        cnpj: Cnpj,
        desde: Desde,
        blocos: BlocosPedidos = None,
        limite: LimiteDeMudancas = None,
    ) -> str:
        numeros = cnpj_do_pedido(cnpj)
        exigir_desde_no_passado(desde)
        saida = await diferenca_da_empresa(
            pedidos, numeros, desde, blocos, ferramenta="o_que_mudou"
        )
        return pedidos.entregar(
            RespostaDaApi(200, enxugar_o_que_mudou(saida, limite=limite)),
            "o_que_mudou",
        )


def exigir_desde_no_passado(desde: date) -> None:
    """`ToolError` se `desde` é hoje ou depois: não há o que comparar."""
    if desde >= _hoje():
        raise ToolError(
            "A data `desde` precisa ser anterior a hoje: não há o que comparar."
        )


async def diferenca_da_empresa(
    pedidos: Pedidos,
    numeros: str,
    desde: date,
    blocos: list[str] | None,
    *,
    ferramenta: str,
) -> dict[str, object]:
    """A diferença de uma empresa entre `desde` e hoje, nos blocos que a chave vê e o analista pediu, antes de
    enxugar. `EmpresaNaoDisponivel` se a base não serve nenhum bloco dela; outro erro da API para tudo.
    `ferramenta` é a que aparece no registro quando a tranca de pessoa recusa uma resposta."""
    acesso = acesso_do_pedido()
    conjuntos = acesso.conjuntos if acesso else frozenset()
    visiveis, fora_do_pedido = _blocos_do_pedido(blocos, conjuntos)
    dias = (desde.isoformat(), None)
    # os dois dias de cada bloco correm juntos: a espera é a de um pedido, não a soma de seis
    resultados = await asyncio.gather(
        *(
            _buscar(pedidos, b, numeros, dia, conjuntos)
            for b in visiveis
            for dia in dias
        ),
        return_exceptions=True,
    )
    for resultado in resultados:
        if isinstance(resultado, BaseException):
            raise resultado
    respostas = [r for r in resultados if isinstance(r, RespostaDaApi)]
    pares = [
        DoisDias(respostas[i], respostas[i + 1]) for i in range(0, len(respostas), 2)
    ]
    _exigir_que_a_api_serviu(pares)
    dos_blocos: dict[str, DoisDias | None] = {
        b: None for b in CONJUNTOS_DO_BLOCO if b not in fora_do_pedido
    }
    dos_blocos.update(zip(visiveis, pares, strict=True))
    # a tranca de pessoa vê cada resposta crua, inclusive o que a comparação não repete; o teto de tamanho
    # só vale para o que vai à IA, que é a diferença (uma ficha crua de companhia aberta já passa de 90 mil)
    for dois in pares:
        for resposta in (dois.antes, dois.depois):
            pedidos.conferir_pessoa(resposta, ferramenta)
    return _montar_a_saida(numeros, desde, dos_blocos, fora_do_pedido)


# ---------------------------------------------------------------- comparar_empresas
#
# A ficha de 2 a 5 empresas lado a lado: uma linha por campo, uma coluna por empresa (a chave é o CNPJ). É o
# mesmo pedido de `ficha_da_empresa` repetido por empresa, sem rota nova e com o mesmo conjunto.

MINIMO_DE_EMPRESAS = 2
MAXIMO_DE_EMPRESAS = 5
MAXIMO_DE_ENTREGAS = 8  # por empresa: as mais novas; o histórico inteiro de 5 companhias passaria do teto
CELULA_SEM_DADO = "não disponível"
AVISO_DA_COMPARACAO = {
    "code": "comparar_empresas",
    "text": (
        f"Cada coluna é a ficha de uma empresa. `{CELULA_SEM_DADO}` quer dizer que a base não tem aquele campo "
        "para ela, não que o valor seja zero; a empresa que a base não serve vem em `not_available`. Cada empresa "
        f"mostra as {MAXIMO_DE_ENTREGAS} entregas mais novas (`filings_cut` diz quantas a base tem). "
        "`unavailable_filings` e `unavailable_registration_fields` dizem o que a chave não consultou de cada "
        "empresa: a lista que falta ali não quer dizer que a empresa não entregou."
    ),
}


def _cnpjs_do_pedido(textos: list[str]) -> list[str]:
    """Os CNPJs pedidos, só números, sem repetir; `ToolError` se são menos de 2, mais de 5 ou algum não é CNPJ."""
    if not MINIMO_DE_EMPRESAS <= len(textos) <= MAXIMO_DE_EMPRESAS:
        raise ToolError(
            f"Compare de {MINIMO_DE_EMPRESAS} a {MAXIMO_DE_EMPRESAS} empresas por vez: vieram {len(textos)}. "
            "Para mais, divida em duas comparações ou use `buscar_empresas`."
        )
    numeros = [cnpj_do_pedido(t) for t in textos]
    if len(set(numeros)) != len(numeros):
        raise ToolError("Há CNPJ repetido na lista: cada empresa entra uma vez.")
    return numeros


def _entregas(corpo: object) -> list[dict] | str:
    """As entregas mais novas (até `MAXIMO_DE_ENTREGAS`, pelo período); a célula sem dado se a API não as consultou.
    A API só manda `periodic_filings` quando consultou algum documento: lista que falta não é lista vazia."""
    if not isinstance(corpo, dict) or not isinstance(
        corpo.get("periodic_filings"), list
    ):
        return CELULA_SEM_DADO
    todas = _itens(corpo, "periodic_filings")
    return sorted(todas, key=_periodo_da_entrega, reverse=True)[:MAXIMO_DE_ENTREGAS]


def _periodo_da_entrega(entrega: dict) -> str:
    periodo = entrega.get("reference_period")
    valor = periodo.get("value") if isinstance(periodo, dict) else None
    return valor if isinstance(valor, str) else ""


def _quantas_entregas(corpo: object) -> int:
    lista = corpo.get("periodic_filings") if isinstance(corpo, dict) else None
    return len(lista) if isinstance(lista, list) else 0


def _avisos_por_empresa(
    ok: dict[str, RespostaDaApi], chave: str
) -> dict[str, list[object]]:
    """O que a API disse que não consultou (`chave`), só das empresas em que ela disse alguma coisa."""
    avisos: dict[str, list[object]] = {}
    for cnpj, resposta in ok.items():
        lista = resposta.corpo.get(chave) if isinstance(resposta.corpo, dict) else None
        if isinstance(lista, list) and lista:
            avisos[cnpj] = lista
    return avisos


def _tabela_de_campos(fichas: dict[str, Retrato | None]) -> list[dict[str, object]]:
    """Uma linha por campo (em ordem alfabética), com o envelope de cada empresa ou a célula sem dado."""
    campos = sorted({c for r in fichas.values() if r for c in r.folhas})
    return [
        {
            "field": campo,
            "values": {
                cnpj: (retrato.folhas.get(campo) if retrato else None)
                or CELULA_SEM_DADO
                for cnpj, retrato in fichas.items()
            },
        }
        for campo in campos
    ]


def _montar_a_comparacao(respostas: dict[str, RespostaDaApi]) -> dict[str, object]:
    """A tabela da comparação. Resposta 404 é coluna sem dado; qualquer outra que não seja 200 já parou antes."""
    ok = {cnpj: r for cnpj, r in respostas.items() if r.ok}
    if not ok:
        raise ToolError(
            mensagem_do_erro(
                RespostaDaApi(STATUS_NAO_DISPONIVEL, {"detail": MOTIVO_NAO_DISPONIVEL})
            )
        )
    fichas: dict[str, Retrato | None] = {
        cnpj: _retrato("registration", r.corpo) if r.ok else None
        for cnpj, r in respostas.items()
    }
    corpos = [r.corpo for r in ok.values()]
    saida: dict[str, object] = {
        "cnpjs": list(respostas),
        "fields": _tabela_de_campos(fichas),
        "periodic_filings": {
            cnpj: _entregas(r.corpo) if r.ok else CELULA_SEM_DADO
            for cnpj, r in respostas.items()
        },
        "not_available": [cnpj for cnpj, r in respostas.items() if not r.ok],
        "limits": [*juntar_sem_repetir(corpos, "limits"), AVISO_DA_COMPARACAO],
        "sources": juntar_sem_repetir(corpos, "sources"),
    }
    cortadas = {
        cnpj: _quantas_entregas(r.corpo)
        for cnpj, r in ok.items()
        if _quantas_entregas(r.corpo) > MAXIMO_DE_ENTREGAS
    }
    if cortadas:
        saida["filings_cut"] = cortadas
    for chave in ("unavailable_filings", "unavailable_registration_fields"):
        if avisos := _avisos_por_empresa(ok, chave):
            saida[chave] = avisos
    return saida


def _registrar_comparar_empresas(servidor: MCPServer, pedidos: Pedidos) -> None:
    """A ficha de 2 a 5 empresas lado a lado."""

    @anunciar(servidor, "comparar_empresas")
    async def comparar_empresas(
        cnpjs: Annotated[
            list[Annotated[str, Field(max_length=40)]],
            Field(
                description=(
                    f"De {MINIMO_DE_EMPRESAS} a {MAXIMO_DE_EMPRESAS} CNPJs (14 caracteres; com ou sem "
                    "pontuação). Só pessoa jurídica."
                )
            ),
        ],
    ) -> str:
        numeros = _cnpjs_do_pedido(cnpjs)
        acesso = acesso_do_pedido()
        conjuntos = acesso.conjuntos if acesso else frozenset()
        # as fichas correm juntas: a espera é a de um pedido, não a soma de cinco
        resultados = await asyncio.gather(
            *(_buscar(pedidos, "registration", n, None, conjuntos) for n in numeros),
            return_exceptions=True,
        )
        for resultado in resultados:
            if isinstance(resultado, BaseException):
                raise resultado
        respostas = dict(
            zip(
                numeros,
                (r for r in resultados if isinstance(r, RespostaDaApi)),
                strict=True,
            )
        )
        for resposta in respostas.values():
            if not resposta.ok and resposta.status != STATUS_NAO_DISPONIVEL:
                raise ToolError(mensagem_do_erro(resposta))
        for resposta in respostas.values():  # a tranca vê cada resposta crua
            if resposta.ok:
                pedidos.entregar(resposta, "comparar_empresas")
        return pedidos.entregar(
            RespostaDaApi(200, _montar_a_comparacao(respostas)), "comparar_empresas"
        )


# ---------------------------------------------------------------- de_onde_vem
#
# Explica um conjunto ou um campo pelo catálogo que a chave já lê (`/catalog`, o mesmo de `o_que_posso_ver`):
# a fonte, a licença, a atribuição e a marca de piloto de cada campo. Não pede dado de empresa.

PERGUNTA_VALIDA = re.compile(r"[a-z0-9_]{1,80}")
MAXIMO_DE_ACHADOS = 50
LIMITE_DO_CATALOGO = (
    "O catálogo da chave traz o conjunto, o campo, a fonte, a licença e a marca de piloto; não traz o "
    "significado de cada campo nem o dia do retrato (o dia de cada valor vem em `published_at`, na resposta "
    "do dado)."
)


def _pergunta(texto: str) -> str:
    """O nome pedido, em minúsculas e sem espaço nas pontas; `ToolError` se não é nome de conjunto ou campo."""
    pergunta = texto.strip().lower()
    if not PERGUNTA_VALIDA.fullmatch(pergunta):
        raise ToolError(
            "Diga o nome de um conjunto ou de um campo, só com letras, números e `_`, como `credit` ou "
            "`legal_name`. A lista do que a sua chave vê está em `o_que_posso_ver`."
        )
    return pergunta


def _campos_do_conjunto(conjunto: dict) -> list[dict]:
    campos = conjunto.get("fields")
    return (
        [c for c in campos if isinstance(c, dict)] if isinstance(campos, list) else []
    )


def _campo_enxuto(campo: dict) -> dict[str, object]:
    enxuto: dict[str, object] = {
        "field": campo.get("field"),
        "source": campo.get("source"),
    }
    if campo.get("pilot") is True:
        enxuto["pilot"] = True
    return enxuto


def _achados(corpo: object, pergunta: str) -> tuple[str, list[dict[str, object]]]:
    """Os conjuntos de nome `pergunta` ou, se não há, os campos de nome `pergunta`, cada um com o conjunto."""
    lista = corpo.get("datasets") if isinstance(corpo, dict) else None
    conjuntos = (
        [c for c in lista if isinstance(c, dict)] if isinstance(lista, list) else []
    )
    de_conjunto = [
        {
            "dataset": c.get("dataset"),
            "purpose": c.get("purpose"),
            "fields": [_campo_enxuto(f) for f in _campos_do_conjunto(c)],
        }
        for c in conjuntos
        if str(c.get("dataset", "")).lower() == pergunta
    ]
    if de_conjunto:
        return "dataset", de_conjunto
    de_campo = [
        {"dataset": c.get("dataset"), "purpose": c.get("purpose")} | _campo_enxuto(f)
        for c in conjuntos
        for f in _campos_do_conjunto(c)
        if str(f.get("field", "")).lower() == pergunta
    ]
    return "field", de_campo


def _campos_do_achado(achado: dict[str, object]) -> list[dict]:
    """Os campos de um achado: os do conjunto, ou o próprio achado quando é um campo."""
    campos = achado.get("fields")
    return campos if isinstance(campos, list) else [achado]


def _fontes_do_achado(corpo: object, achados: list[dict[str, object]]) -> list[dict]:
    """A licença e a atribuição das fontes que aparecem nos achados, uma vez cada, em ordem alfabética."""
    usadas = {
        campo.get("source")
        for achado in achados
        for campo in _campos_do_achado(achado)
        if isinstance(campo.get("source"), str)
    }
    lista = corpo.get("sources") if isinstance(corpo, dict) else None
    por_nome = {
        f["source"]: f
        for f in (lista if isinstance(lista, list) else [])
        if isinstance(f, dict) and isinstance(f.get("source"), str)
    }
    return [por_nome.get(nome, {"source": nome}) for nome in sorted(usadas, key=str)]


def _campos_de_piloto(achados: list[dict[str, object]]) -> list[str]:
    return sorted(
        {
            f"{achado.get('dataset')}.{campo.get('field')}"
            for achado in achados
            for campo in _campos_do_achado(achado)
            if campo.get("pilot") is True
        }
    )


def _explicacao(corpo: object, pergunta: str) -> dict[str, object]:
    """A explicação de `pergunta`, com o aviso de piloto uma vez só; `ToolError` se a chave não vê nada assim."""
    tipo, achados = _achados(corpo, pergunta)
    if not achados:
        raise ToolError(
            "A sua chave não vê um conjunto nem um campo com esse nome. "
            "A lista do que ela vê está em `o_que_posso_ver`."
        )
    cortado = len(achados) > MAXIMO_DE_ACHADOS
    achados = achados[:MAXIMO_DE_ACHADOS]
    saida: dict[str, object] = {
        "asked": pergunta,
        "kind": tipo,
        "matches": achados,
        "sources": _fontes_do_achado(corpo, achados),
        "limits": [LIMITE_DO_CATALOGO],
    }
    if cortado:
        saida["truncated"] = True
    de_piloto = _campos_de_piloto(achados)
    aviso = corpo.get("pilot_notice") if isinstance(corpo, dict) else None
    if de_piloto and isinstance(aviso, str):
        saida["pilot_fields"] = de_piloto
        saida["pilot_notice"] = aviso
    return saida


def _registrar_de_onde_vem(servidor: MCPServer, pedidos: Pedidos) -> None:
    """A explicação de um conjunto ou de um campo, tirada do catálogo da chave."""

    @anunciar(servidor, "de_onde_vem")
    async def de_onde_vem(
        sobre: Annotated[
            str,
            Field(
                max_length=80,
                description="O nome de um conjunto ou de um campo da lista de `o_que_posso_ver`, como `credit` ou `legal_name`.",
            ),
        ],
    ) -> str:
        pergunta = _pergunta(sobre)
        catalogo = await pedidos.resposta("/catalog")
        if not catalogo.ok:
            raise ToolError(mensagem_do_erro(catalogo))
        return pedidos.entregar(
            RespostaDaApi(STATUS_OK, _explicacao(catalogo.corpo, pergunta)),
            "de_onde_vem",
        )
