"""As ferramentas do analista que só compõem o que a API já devolve (linha 980, onda 1).

Cada uma é um ou mais pedidos à API pelo `ClienteDaApi`, com a chave do analista, e passa pela mesma
tranca de saída das outras (`Pedidos.entregar`: texto limpo, sem pessoa, dentro do teto). Nenhuma abre rota
nem direito novo: o que a chave não vê a API já nega, e a ferramenta some da lista de quem não tem o
conjunto (`CONJUNTOS_DA_FERRAMENTA`, em `ferramentas.py`, onde ficam também os títulos).
"""

import asyncio
import dataclasses
import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from conector_remoto.acesso import acesso_do_pedido
from conector_remoto.cliente_api import ParametroDaApi, RespostaDaApi
from conector_remoto.ferramentas import (
    SO_LEITURA,
    STATUS_NAO_DISPONIVEL,
    TITULOS_DAS_FERRAMENTAS,
    Cnpj,
    ComoEraEm,
    Pedidos,
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


def _registrar_credito(servidor: MCPServer, pedidos: Pedidos) -> None:
    """Os fatos de crédito da rota `/credit` (conjunto `credit`)."""

    @servidor.tool(
        title=TITULOS_DAS_FERRAMENTAS["credito_da_empresa"],
        annotations=SO_LEITURA,
        structured_output=False,
    )
    async def credito_da_empresa(cnpj: Cnpj, como_era_em: ComoEraEm = None) -> str:
        """Os fatos de crédito de uma empresa pelo CNPJ, como eram no dia: a situação cadastral e a situação
        especial na Receita, os fatos relevantes dos últimos 12 meses entregues à CVM e, para quem cede
        recebíveis a fundo de direitos creditórios (FIDC), os fundos em que cede, a maior participação como
        cedente, a carteira desses fundos e a maior inadimplência deles. Cada fato traz a fonte e o dia em que
        ficou público (`published_at`); fato não observado não aparece, e isso não quer dizer que o evento não
        aconteceu (os `limits` explicam). Serve para ler, antes da reunião, os sinais objetivos de crédito de
        uma empresa.
        Fonte: cadastro CNPJ da Receita Federal; documentos e informes de FIDC entregues à CVM.
        Não traz: rating, insolvência, elegibilidade como cedente ou sacado, nota ou opinião de crédito, o SCR
        individual do Banco Central, pessoa física, contato nem endereço."""
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


def _juntar_sem_repetir(corpos: list[object], chave: str) -> list[object]:
    """Os `limits` ou `sources` de todas as respostas, na ordem em que apareceram e sem repetir."""
    vistos: dict[str, object] = {}
    for corpo in corpos:
        achados = corpo.get(chave) if isinstance(corpo, dict) else None
        for item in achados if isinstance(achados, list) else []:
            vistos.setdefault(
                json.dumps(item, sort_keys=True, ensure_ascii=False), item
            )
    return list(vistos.values())


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
) -> dict[str, object]:
    """A resposta da ferramenta, de cada bloco consultado (`None` = a chave não vê o conjunto dele)."""
    saida: dict[str, object] = {}
    nao_consultados: list[dict[str, str]] = []
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
        raise ToolError(
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
            *_juntar_sem_repetir(todos, "limits"),
            AVISO_DA_FERRAMENTA,
            *([AVISO_DE_PAGINA_CHEIA] if parcial else []),
        ],
        "sources": _juntar_sem_repetir(todos, "sources"),
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


def _registrar_o_que_mudou(servidor: MCPServer, pedidos: Pedidos) -> None:
    """A diferença do cadastro, dos vínculos e dos eventos entre um dia passado e hoje."""

    @servidor.tool(
        title=TITULOS_DAS_FERRAMENTAS["o_que_mudou"],
        annotations=SO_LEITURA,
        structured_output=False,
    )
    async def o_que_mudou(cnpj: Cnpj, desde: Desde) -> str:
        """O que mudou numa empresa desde um dia: compara o que a base sabia em `desde` com o que sabe hoje e
        lista só a diferença, nos blocos que a chave vê: o cadastro na Receita (com as entregas de DFP e ITR),
        os vínculos e os eventos. Cada item traz o antes e o depois (ou só o que entrou ou saiu), com a fonte e o
        dia em que ficou público; republicar o mesmo valor não conta como mudança, e o lado antigo nunca traz
        nada publicado depois de `desde`. `not_consulted` lista o bloco que a chave não vê ou a base não serve,
        `before_not_available` diz que a base ainda não conhecia a empresa em `desde` e `partial`, que a página
        veio cheia. Serve para retomar uma empresa já analisada e ler, antes da reunião, o que é novo.
        Fonte: as dos blocos: cadastro CNPJ da Receita Federal; FRE, FCA e IPE da CVM.
        Não traz: mudança que ainda não foi publicada na base, sócio pessoa física, contato nem endereço,
        faturamento de empresa fechada, o motivo de cada mudança nem opinião sobre ela."""
        numeros = cnpj_do_pedido(cnpj)
        if desde >= _hoje():
            raise ToolError(
                "A data `desde` precisa ser anterior a hoje: não há o que comparar."
            )
        acesso = acesso_do_pedido()
        conjuntos = acesso.conjuntos if acesso else frozenset()
        visiveis = [
            b for b, exigidos in CONJUNTOS_DO_BLOCO.items() if exigidos & conjuntos
        ]
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
            DoisDias(respostas[i], respostas[i + 1])
            for i in range(0, len(respostas), 2)
        ]
        _exigir_que_a_api_serviu(pares)
        blocos: dict[str, DoisDias | None] = {b: None for b in CONJUNTOS_DO_BLOCO}
        blocos.update(zip(visiveis, pares, strict=True))
        for dois in (
            pares
        ):  # a tranca vê cada resposta crua, inclusive o que a comparação não repete
            for resposta in (dois.antes, dois.depois):
                if resposta.ok:
                    pedidos.entregar(resposta, "o_que_mudou")
        return pedidos.entregar(
            RespostaDaApi(200, _montar_a_saida(numeros, desde, blocos)), "o_que_mudou"
        )
