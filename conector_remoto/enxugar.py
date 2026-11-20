"""O recorte que faz a resposta de uma companhia aberta caber na conversa (ensaio de 19/11, linhas 984 e 955).

A API entrega tudo o que a chave vê, e cada valor vem com a fonte, o dia em que ficou público e, na organização do
piloto, a marca e a frase de piloto (ADR 0108, Emenda 2, D11.3: um bloco de piloto sem a frase é defeito). Uma linha
de demonstração tem 12 valores desses e pesa uns 2,5 mil caracteres; um período de uma companhia grande passa de
300 linhas e a ferramenta falhava mesmo com `fim_do_periodo`. A ficha de uma companhia aberta traz 60 e poucas
entregas de DFP e ITR, também inteiras. O corte é aqui, no conector: a frase de piloto de cada valor que sai
continua onde a API a pôs; o que não cabe fica de fora e **diz** que ficou, em `truncated` e `limits`.

Nada aqui vem da API como texto: as frases são fixas e só citam parâmetros que a ferramenta tem.
"""

import re
from collections import Counter

from conector_remoto import saida

CHAVE_DAS_ENTREGAS = "periodic_filings"
CHAVE_DAS_LINHAS = "rows"
LIMITE_PADRAO_DAS_ENTREGAS = 8
LIMITE_MAXIMO_DAS_ENTREGAS = 100
# a folga para as frases de `limits` e para o resto do corpo
FOLGA_EM_CARACTERES = 4_000
# do que mais se pergunta ao que menos: resultado, balanço, caixa, valor adicionado, o resto, as mutações
# a DMPL não está aqui: a rota de demonstrações não a serve (ela fica em tabela própria, `base/dmpl.py`)
ORDEM_DOS_DEMONSTRATIVOS = ("DRE", "BPA", "BPP", "DFC", "DVA", "DRA")
CONSOLIDADO, INDIVIDUAL = "con", "ind"


def _com_aviso(corpo: dict, avisos: list[str], *, cortou: bool = True) -> dict:
    """O corpo com os avisos em `limits`, depois dos que a API já pôs, e `truncated` (só se `cortou`: um aviso
    que só explica o que o filtro faz não diz que faltou algo)."""
    limites = corpo.get("limits")
    return corpo | {
        **({"truncated": True} if cortou else {}),
        "limits": [*limites, *avisos] if isinstance(limites, list) else avisos,
    }


# ---------------------------------------------------------------- a ficha: as entregas mais novas


def cortar_entregas(corpo: object, limite: int) -> object:
    """As `limite` entregas de DFP e ITR mais novas (a ordem é a da API, da mais nova à mais velha), com
    `truncated` e a contagem total em `limits` quando cortou. O resto da ficha fica como veio."""
    if not isinstance(corpo, dict):
        return corpo
    entregas = corpo.get(CHAVE_DAS_ENTREGAS)
    if not isinstance(entregas, list) or len(entregas) <= limite:
        return corpo
    aviso = (
        f"O conector entregou as {limite} entregas de DFP e ITR mais novas das {len(entregas)} que a base tem; "
        f"peça mais com `limite_de_entregas` (até {LIMITE_MAXIMO_DAS_ENTREGAS})."
    )
    return _com_aviso(corpo | {CHAVE_DAS_ENTREGAS: entregas[:limite]}, [aviso])


# ---------------------------------------------------------------- as demonstrações: um período, o consolidado


def _valor(linha: dict, campo: str) -> object:
    envelope = linha.get(campo)
    return envelope.get("value") if isinstance(envelope, dict) else None


def _publicado_em(linha: dict) -> str:
    envelope = linha.get("value")
    dia = envelope.get("published_at") if isinstance(envelope, dict) else None
    return dia if isinstance(dia, str) else ""


def _fato(linha: dict) -> tuple:
    """O que identifica uma conta num período: duas linhas do mesmo fato são versões uma da outra."""
    return tuple(
        _valor(linha, campo)
        for campo in ("statement", "group", "account", "start", "end")
    )


def _versao(linha: dict) -> tuple[str, int]:
    numero = _valor(linha, "revision")
    return (_publicado_em(linha), numero if isinstance(numero, int) else 0)


def _so_a_versao_mais_nova(linhas: list[dict]) -> list[dict]:
    """De cada conta de cada período, a linha de versão mais nova (a mais recente entrega; empate, a maior versão)."""
    melhor: dict[tuple, dict] = {}
    for linha in linhas:
        fato = _fato(linha)
        if fato not in melhor or _versao(linha) > _versao(melhor[fato]):
            melhor[fato] = linha
    return [linha for linha in linhas if melhor[_fato(linha)] is linha]


def _do_demonstrativo_e_periodo(linha: dict) -> tuple:
    return (_valor(linha, "statement"), _valor(linha, "end"))


def _so_o_grupo_pedido(linhas: list[dict], visao: str) -> list[dict]:
    """`consolidado`: o consolidado de cada demonstrativo e, no que não tem consolidado naquele período, o
    individual (as contas detalhadas do individual não somam nas do consolidado: os grupos não se misturam
    dentro de um demonstrativo); `individual` ou `ambos`."""
    if visao == "ambos":
        return linhas
    if visao == "individual":
        return [linha for linha in linhas if _valor(linha, "group") == INDIVIDUAL]
    com_consolidado = {
        _do_demonstrativo_e_periodo(linha)
        for linha in linhas
        if _valor(linha, "group") == CONSOLIDADO
    }
    return [
        linha
        for linha in linhas
        if _valor(linha, "group") == CONSOLIDADO
        or _do_demonstrativo_e_periodo(linha) not in com_consolidado
    ]


def _do_demonstrativo(linha: dict, demonstrativo: str) -> bool:
    nome = str(_valor(linha, "statement") or "").upper()
    return nome == demonstrativo or nome.startswith(demonstrativo + "_")


def _da_conta(linha: dict, conta: str) -> bool:
    codigo = str(_valor(linha, "account") or "")
    return codigo == conta or codigo.startswith(conta + ".")


def _posto(linha: dict) -> int:
    nome = str(_valor(linha, "statement") or "").upper()
    for posto, base in enumerate(ORDEM_DOS_DEMONSTRATIVOS):
        if nome == base or nome.startswith(base + "_"):
            return posto
    return len(ORDEM_DOS_DEMONSTRATIVOS)


def _caber(corpo: dict, linhas: list[dict]) -> list[dict]:
    """As primeiras linhas que, com o resto do corpo, cabem no teto da resposta."""
    sobra = (
        saida.TETO_DE_CARACTERES
        - FOLGA_EM_CARACTERES
        - saida.tamanho_em_caracteres(corpo | {CHAVE_DAS_LINHAS: []})
    )
    pesos = [saida.tamanho_em_caracteres(linha) + 1 for linha in linhas]
    usado, quantas = 0, 0
    for peso in pesos:
        if usado + peso > sobra:
            break
        usado += peso
        quantas += 1
    return linhas[:quantas]


def _lista_de(contagem: Counter) -> str:
    return ", ".join(f"{nome} ({quantas})" for nome, quantas in contagem.items())


def _avisos(
    periodo: str | None,
    outros_periodos: list[str],
    antigas: int,
    do_grupo_de_fora: int,
    visao: str,
    no_corte: Counter,
    entregues: Counter,
) -> list[str]:
    avisos = []
    if outros_periodos:
        avisos.append(
            f"Período entregue: o que termina em {periodo}, o mais novo da base. A base tem também os que "
            f"terminam em {', '.join(outros_periodos[:6])}"
            f"{' e mais' if len(outros_periodos) > 6 else ''}; peça um deles com `fim_do_periodo`."
        )
    if antigas:
        avisos.append(
            f"De cada conta, só a versão mais nova: {antigas} linha(s) de versão mais antiga ficaram de fora."
        )
    if do_grupo_de_fora and visao == "individual":
        avisos.append(
            f"Só o individual: {do_grupo_de_fora} linha(s) do consolidado ficaram de fora; peça `visao` "
            "consolidado ou ambos."
        )
    elif do_grupo_de_fora:
        avisos.append(
            f"Consolidado em cada demonstrativo que o tem, individual no que não tem consolidado: "
            f"{do_grupo_de_fora} linha(s) do individual ficaram de fora; peça `visao` individual ou ambos."
        )
    if no_corte:
        avisos.append(
            "A resposta foi cortada para caber na conversa; ficaram de fora "
            f"{_lista_de(no_corte)} linha(s) por demonstrativo. Peça um `demonstrativo` (DRE, BPA, BPP, DFC, "
            "DVA, DRA) ou uma `conta` (ex.: 3.01) para ver o resto."
        )
    if entregues and no_corte:
        avisos.append(f"Entregues: {_lista_de(entregues)} linha(s) por demonstrativo.")
    return avisos


def enxugar_demonstracoes(
    corpo: object,
    *,
    demonstrativo: str | None = None,
    visao: str = "consolidado",
    conta: str | None = None,
    periodo_pedido: bool = False,
) -> object:
    """As linhas de demonstração que cabem na conversa: um período, a versão mais nova de cada conta, o
    consolidado quando houver, só o demonstrativo e a conta pedidos. O que ficou de fora vai em `limits`, com
    `truncated`. Corpo que não tem a lista de linhas passa como veio."""
    if not isinstance(corpo, dict):
        return corpo
    linhas = corpo.get(CHAVE_DAS_LINHAS)
    if not isinstance(linhas, list) or not all(isinstance(l, dict) for l in linhas):
        return corpo
    da_api = Counter(str(_valor(l, "statement")) for l in linhas)
    if demonstrativo:
        linhas = [l for l in linhas if _do_demonstrativo(l, demonstrativo.upper())]
    if conta:
        linhas = [l for l in linhas if _da_conta(l, conta)]
    total = len(linhas)
    linhas = _so_a_versao_mais_nova(linhas)
    antigas = total - len(linhas)
    periodos = sorted(
        {str(_valor(l, "end")) for l in linhas if _valor(l, "end")}, reverse=True
    )
    periodo = None if periodo_pedido or not periodos else periodos[0]
    if periodo is not None:
        linhas = [l for l in linhas if _valor(l, "end") == periodo]
    antes = len(linhas)
    linhas = _so_o_grupo_pedido(linhas, visao)
    do_grupo_de_fora = antes - len(linhas)
    linhas = sorted(
        linhas, key=_posto
    )  # estável: dentro de cada demonstrativo fica a ordem da API
    cabem = _caber(corpo, linhas)
    no_corte = Counter(str(_valor(l, "statement")) for l in linhas[len(cabem) :])
    avisos = _avisos(
        periodo,
        [p for p in periodos if p != periodo] if periodo else [],
        antigas,
        do_grupo_de_fora,
        visao,
        no_corte,
        Counter(str(_valor(l, "statement")) for l in cabem),
    )
    if not cabem and (demonstrativo or conta) and da_api:
        avisos.append(
            "Nenhuma linha para esse demonstrativo e essa conta neste período; a API mandou linhas dos "
            f"demonstrativos: {_lista_de(da_api)}. Nada foi estimado."
        )
    novo = corpo | {CHAVE_DAS_LINHAS: cabem}
    return _com_aviso(novo, avisos) if avisos else novo


# ---------------------------------------------------------------- a divisão do orçamento entre listas


def _quantos_cabem[C](
    base: dict, listas: dict[C, list], teto: int = saida.TETO_DE_CARACTERES
) -> dict[C, int]:
    """Quantos itens de cada lista cabem no `teto` junto com o resto do corpo (`base`, com as listas vazias).

    O orçamento se reparte de item em item entre as listas, na ordem em que vieram: uma lista enorme não toma o
    lugar das outras. Dentro de cada lista a ordem é a da API e o corte é sempre no fim."""
    sobra = teto - FOLGA_EM_CARACTERES - saida.tamanho_em_caracteres(base)
    pesos = {
        c: [saida.tamanho_em_caracteres(i) + 1 for i in itens]
        for c, itens in listas.items()
    }
    ficam = dict.fromkeys(listas, 0)
    parados: set[C] = set()
    usado = 0
    for rodada in range(max((len(p) for p in pesos.values()), default=0)):
        for chave, peso in pesos.items():
            if chave in parados or rodada >= len(peso):
                continue
            if usado + peso[rodada] > sobra:
                parados.add(chave)
                continue
            usado += peso[rodada]
            ficam[chave] += 1
    return ficam


# ---------------------------------------------------------------- os ativos: o que cabe, filtrado

# o nome que o analista usa (o mesmo da descrição da ferramenta) -> o bloco da resposta da API
BLOCOS_DOS_ATIVOS = {
    "petroleo_e_gas": "oil_gas_contracts",
    "barragens": "mining_dams",
    "royalties": "mining_royalties",
}
NOMES_DOS_BLOCOS_DE_ATIVOS = {
    "oil_gas_contracts": "contratos de petróleo e gás",
    "mining_dams": "barragens de mineração",
    "mining_royalties": "processos de royalties de mineração",
}
BLOCOS_DE_ATIVOS_COM_UF = ("mining_dams", "mining_royalties")
BLOCO_DE_ATIVOS_COM_OPERADOR = "oil_gas_contracts"
CHAVE_DOS_ITENS = "items"
LIMITE_MAXIMO_DOS_ATIVOS = 500


def _envelope_do_item(item: object, campo: str) -> object:
    envelope = item.get(campo) if isinstance(item, dict) else None
    return envelope.get("value") if isinstance(envelope, dict) else None


def _lista_de_itens(bloco: object) -> list | None:
    itens = bloco.get(CHAVE_DOS_ITENS) if isinstance(bloco, dict) else None
    return itens if isinstance(itens, list) else None


def _filtrar_ativos(
    itens: dict[str, list], tipo: str | None, uf: str | None, so_operador: bool
) -> tuple[dict[str, list], list[str]]:
    """Os itens que passam nos filtros do pedido, e o que dizer de cada filtro."""
    avisos: list[str] = []
    if uf:
        sigla = uf.upper()
        for bloco in BLOCOS_DE_ATIVOS_COM_UF:
            if bloco in itens:
                antes = len(itens[bloco])
                itens[bloco] = [
                    i
                    for i in itens[bloco]
                    if _envelope_do_item(i, "state_code") == sigla
                ]
                if antes != len(itens[bloco]):
                    avisos.append(
                        f"Só a UF {sigla}: {antes - len(itens[bloco])} item(ns) de outras UFs ficaram de fora "
                        f"de {NOMES_DOS_BLOCOS_DE_ATIVOS[bloco]}."
                    )
        if BLOCO_DE_ATIVOS_COM_OPERADOR in itens:
            avisos.append(
                f"`uf` não filtra os {NOMES_DOS_BLOCOS_DE_ATIVOS[BLOCO_DE_ATIVOS_COM_OPERADOR]}: "
                "a fonte (ANP) não traz a UF do contrato."
            )
    if so_operador and BLOCO_DE_ATIVOS_COM_OPERADOR in itens:
        antes = len(itens[BLOCO_DE_ATIVOS_COM_OPERADOR])
        itens[BLOCO_DE_ATIVOS_COM_OPERADOR] = [
            i
            for i in itens[BLOCO_DE_ATIVOS_COM_OPERADOR]
            if _envelope_do_item(i, "is_operator") is True
        ]
        avisos.append(
            f"Só os contratos em que a empresa opera: {antes - len(itens[BLOCO_DE_ATIVOS_COM_OPERADOR])} "
            "contrato(s) em que ela não opera ficaram de fora."
        )
    return itens, avisos


def _so_o_bloco_pedido(corpo: dict, tipo: str) -> tuple[dict, list[str]]:
    """O corpo só com o bloco do tipo pedido; os outros blocos de ativos saem, dizendo quais."""
    escolhido = BLOCOS_DOS_ATIVOS[tipo]
    de_fora = [b for b in NOMES_DOS_BLOCOS_DE_ATIVOS if b != escolhido and b in corpo]
    novo = {c: v for c, v in corpo.items() if c not in de_fora}
    avisos = []
    if de_fora:
        avisos.append(
            f"Só o bloco pedido (`tipo_de_ativo` {tipo}); ficaram de fora: "
            f"{', '.join(NOMES_DOS_BLOCOS_DE_ATIVOS[b] for b in de_fora)}. Peça sem `tipo_de_ativo` ou com outro tipo."
        )
    if escolhido not in corpo:
        avisos.append(
            f"O bloco pedido ({NOMES_DOS_BLOCOS_DE_ATIVOS[escolhido]}) não veio: a chave não o vê ou a rota "
            "ainda não o serve (veja `not_covered`)."
        )
    return novo, avisos


def enxugar_ativos(
    corpo: object,
    *,
    tipo: str | None = None,
    uf: str | None = None,
    so_operador: bool = False,
    limite: int | None = None,
) -> object:
    """Os ativos que cabem na conversa: só o tipo, a UF e o operador pedidos, no máximo `limite` itens por bloco
    e, de qualquer jeito, o que couber no teto (cada item leva ~2,6 mil caracteres, e uma petroleira tem
    centenas de contratos). O que ficou de fora vai em `limits`, com `truncated` (no bloco e na resposta)."""
    if not isinstance(corpo, dict):
        return corpo
    avisos: list[str] = []
    blocos_de_fora = False
    if tipo:
        sem_o_resto, avisos = _so_o_bloco_pedido(corpo, tipo)
        blocos_de_fora = len(sem_o_resto) < len(corpo)
        corpo = sem_o_resto
    itens = {
        b: lista
        for b in NOMES_DOS_BLOCOS_DE_ATIVOS
        if (lista := _lista_de_itens(corpo.get(b))) is not None
    }
    if not itens:
        return _com_aviso(corpo, avisos, cortou=blocos_de_fora) if avisos else corpo
    antes_dos_filtros = sum(len(lista) for lista in itens.values())
    itens, dos_filtros = _filtrar_ativos(itens, tipo, uf, so_operador)
    avisos += dos_filtros
    totais = {b: len(lista) for b, lista in itens.items()}
    if limite:
        itens = {b: lista[:limite] for b, lista in itens.items()}
    base = corpo | {b: corpo[b] | {CHAVE_DOS_ITENS: []} for b in itens}
    ficam = _quantos_cabem(base, itens)
    cortados = {b: totais[b] - ficam[b] for b in itens if totais[b] > ficam[b]}
    novo = corpo | {
        b: corpo[b]
        | {CHAVE_DOS_ITENS: itens[b][: ficam[b]]}
        | ({"truncated": True} if b in cortados else {})
        for b in itens
    }
    if cortados:
        de_cada = ", ".join(
            f"{NOMES_DOS_BLOCOS_DE_ATIVOS[b]} ({ficam[b]} de {totais[b]})"
            for b in cortados
        )
        avisos.append(
            f"A resposta foi cortada (pelo que cabe na conversa ou por `limite`); entregues: {de_cada}. Peça o "
            "resto por partes, com `tipo_de_ativo`, `uf` ou `somente_operador`."
        )
    cortou = blocos_de_fora or antes_dos_filtros > sum(ficam.values())
    return _com_aviso(novo, avisos, cortou=cortou) if avisos else novo


# ---------------------------------------------------------------- o que mudou: as mudanças que cabem

BLOCOS_DO_QUE_MUDOU = ("registration", "links", "events")
TIPOS_DE_MUDANCA = ("changed", "added", "removed")
LIMITE_MAXIMO_DAS_MUDANCAS = 200


def enxugar_o_que_mudou(corpo: object, *, limite: int | None = None) -> object:
    """As mudanças que cabem na conversa: no máximo `limite` por lista (alteradas, novas e removidas de cada
    bloco) e, de qualquer jeito, o que couber no teto (uma entrega de DFP ou ITR que mudou leva o antes e o
    depois, uns 3 mil caracteres, e uma companhia aberta tem 60 e poucas). `changes_found` continua sendo a
    contagem inteira; o que ficou de fora vai em `limits`, com `truncated` e `changes_shown`."""
    if not isinstance(corpo, dict):
        return corpo
    blocos = [b for b in BLOCOS_DO_QUE_MUDOU if isinstance(corpo.get(b), dict)]
    listas = {
        (b, t): corpo[b][t]
        for b in blocos
        for t in TIPOS_DE_MUDANCA
        if isinstance(corpo[b].get(t), list)
    }
    if not listas:
        return corpo
    totais = {chave: len(lista) for chave, lista in listas.items()}
    if limite:
        listas = {chave: lista[:limite] for chave, lista in listas.items()}
    vazios = {b: corpo[b] | {t: [] for (bb, t) in listas if bb == b} for b in blocos}
    ficam = _quantos_cabem(corpo | vazios, listas)
    cortados = {
        chave: totais[chave] - ficam[chave]
        for chave in listas
        if totais[chave] > ficam[chave]
    }
    if not cortados:
        return corpo
    cortes_por_bloco = {b for b, _ in cortados}
    novo = corpo | {
        b: corpo[b]
        | {t: listas[(bb, t)][: ficam[(bb, t)]] for (bb, t) in listas if bb == b}
        | ({"truncated": True} if b in cortes_por_bloco else {})
        for b in blocos
    }
    entregues = sum(ficam.values())
    de_cada = ", ".join(
        f"{b}.{t} ({ficam[(b, t)]} de {totais[(b, t)]})" for b, t in cortados
    )
    aviso = (
        f"A resposta foi cortada (pelo que cabe na conversa ou por `limite`): {entregues} de "
        f"{sum(totais.values())} mudanças entregues; ficaram de fora {de_cada}. `changes_found` é a contagem "
        "inteira. Peça um bloco por vez com `blocos` (cadastro, vinculos ou eventos) para ver o resto."
    )
    return _com_aviso(novo | {"changes_shown": entregues}, [aviso])


# ---------------------------------------------------------------- a análise completa: o que cabe

# O app do analista recusa a resposta de ferramenta grande demais; a análise de uma companhia aberta passou de
# 63 mil caracteres (ensaio de 20/11/2026). O teto é uma suposição nossa, abaixo do `TETO_DE_CARACTERES` das
# outras ferramentas, e o primeiro número a rever se o app voltar a recusar.
TETO_DA_ANALISE = 50_000
LIMITE_MAXIMO_DA_ANALISE = 500
LISTAS_DO_TOPO_DA_ANALISE = ("timeline", "inferences")
# o bloco da análise -> a ferramenta que o traz sozinho, com o espaço todo da resposta
FERRAMENTA_DO_BLOCO_DA_ANALISE = {
    "credit": "credito_da_empresa",
    "comparables": "comparaveis",
    "links": "vinculos",
    "events": "eventos",
    "assets": "ativos",
}
TOPO = ""  # o "bloco" das listas que ficam no topo da análise
# `blocks.<bloco>.<lista>` e `blocks.<bloco>.<grupo>.<lista>` (os ativos e as tabelas por CNPJ guardam os itens
# um nível abaixo)
PROFUNDIDADE_DAS_LISTAS = 2
# a API entrega a linha do tempo do mais velho para o mais novo: ao cortar, ficam os mais novos
LISTAS_DOS_MAIS_NOVOS = {(TOPO, "timeline")}
NOME_DE_BLOCO = re.compile(r"[a-z][a-z0-9_]{1,39}")

type Caminho = tuple[str, ...]


def _lista_de_dicts(valor: object) -> bool:
    return (
        isinstance(valor, list)
        and bool(valor)
        and all(isinstance(i, dict) for i in valor)
    )


def _listas_do_bloco(
    conteudo: dict, caminho: Caminho, fundo: int
) -> dict[Caminho, list]:
    """As listas de itens de um bloco (ou de um grupo dele), até `fundo` níveis."""
    achadas: dict[Caminho, list] = {}
    for chave, valor in conteudo.items():
        if _lista_de_dicts(valor):
            achadas[(*caminho, chave)] = valor
        elif isinstance(valor, dict) and fundo > 1:
            achadas |= _listas_do_bloco(valor, (*caminho, chave), fundo - 1)
    return achadas


def _listas_da_analise(corpo: dict) -> dict[Caminho, list]:
    """As listas que a análise corta: as de cada bloco e as do topo (`(TOPO, nome)`), na ordem em que vieram."""
    listas: dict[Caminho, list] = {}
    for bloco, conteudo in corpo["blocks"].items():
        if isinstance(conteudo, dict):
            listas |= _listas_do_bloco(conteudo, (bloco,), PROFUNDIDADE_DAS_LISTAS)
    for chave in LISTAS_DO_TOPO_DA_ANALISE:
        if _lista_de_dicts(corpo.get(chave)):
            listas[(TOPO, chave)] = corpo[chave]
    return listas


def _so_os_blocos_pedidos(
    corpo: dict, pedidos: list[str] | None
) -> tuple[dict, list[str]]:
    """O corpo só com os blocos pedidos, e os avisos do que o pedido tirou ou não encontrou."""
    if not pedidos:
        return corpo, []
    avisos = []
    fora = [b for b in corpo["blocks"] if b not in pedidos]
    if fora:
        avisos.append(
            f"Só os blocos pedidos (`blocos`); ficaram de fora: {', '.join(fora)}. Peça sem `blocos`, ou com "
            "outro nome, para vê-los."
        )
    ausentes = [b for b in pedidos if b not in corpo["blocks"]]
    if ausentes:
        avisos.append(
            f"Não vieram na análise: {', '.join(ausentes)} (a chave não os vê, a API não os trouxe ou o nome "
            "não existe; os nomes são os de `blocks`)."
        )
    ficam = {b: v for b, v in corpo["blocks"].items() if b in pedidos}
    return corpo | {"blocks": ficam}, avisos


def _aviso_dos_atrasados(corpo: dict) -> list[str]:
    """Dos blocos que a API deu como `timed_out`: dizer que não é falta de dado e como pedir de novo. Só entra
    nome com a forma de nome de bloco (o texto da API não vai solto para `limits`), uma vez cada."""
    atrasados = corpo.get("timed_out")
    nomes = list(
        dict.fromkeys(
            item["block"]
            for item in (atrasados if isinstance(atrasados, list) else [])
            if isinstance(item, dict)
            and isinstance(item.get("block"), str)
            and NOME_DE_BLOCO.fullmatch(item["block"])
        )
    )
    if not nomes:
        return []
    sozinhos = [
        f"{b} (`{FERRAMENTA_DO_BLOCO_DA_ANALISE[b]}`)"
        for b in nomes
        if b in FERRAMENTA_DO_BLOCO_DA_ANALISE
    ]
    dica = (
        f" Alguns saem sozinhos pela ferramenta do bloco: {', '.join(sozinhos)}."
        if sozinhos
        else ""
    )
    return [
        (
            f"Não responderam no prazo da API: {', '.join(nomes)}. Isso não quer dizer que não há dado; peça a "
            f"análise de novo.{dica}"
        )
    ]


def _fatia(caminho: Caminho, lista: list, quantos: int) -> list:
    """Os `quantos` primeiros itens da lista (os mais novos, na linha do tempo)."""
    if quantos <= 0:
        return []
    return lista[-quantos:] if caminho in LISTAS_DOS_MAIS_NOVOS else lista[:quantos]


def _trocar_lista(conteudo: dict, caminho: Caminho, nova: list) -> dict:
    """O conteúdo do bloco com a lista do `caminho` (dentro dele) trocada."""
    chave = caminho[0]
    if len(caminho) == 1:
        return conteudo | {chave: nova}
    return conteudo | {chave: _trocar_lista(conteudo[chave], caminho[1:], nova)}


def _analise_com_as_listas(
    corpo: dict,
    listas: dict[Caminho, list],
    ficam: dict[Caminho, int],
    cortados: set[Caminho],
) -> dict:
    """A análise com cada lista nos itens que couberam; o bloco que perdeu itens leva `truncated`."""
    blocos = corpo["blocks"]
    topo: dict[str, list] = {}
    for caminho, lista in listas.items():
        nova = _fatia(caminho, lista, ficam[caminho])
        if caminho[0] == TOPO:
            topo[caminho[1]] = nova
        else:
            blocos = blocos | {
                caminho[0]: _trocar_lista(blocos[caminho[0]], caminho[1:], nova)
            }
    for bloco in {c[0] for c in cortados if c[0] != TOPO}:
        blocos = blocos | {bloco: blocos[bloco] | {"truncated": True}}
    return corpo | {"blocks": blocos} | topo


def _nome_da_lista(caminho: Caminho) -> str:
    nome = ".".join(parte for parte in caminho if parte)
    return f"{nome}, os mais novos" if caminho in LISTAS_DOS_MAIS_NOVOS else nome


def enxugar_analise(
    corpo: object, *, blocos: list[str] | None = None, limite: int | None = None
) -> object:
    """A análise completa no que cabe na conversa (`TETO_DA_ANALISE`): só os `blocos` pedidos, no máximo `limite`
    itens por lista e, de qualquer jeito, o que couber no teto, repartido de item em item entre as listas de todos
    os blocos, também as que ficam um grupo abaixo (ativos, tabelas por CNPJ): nenhuma fica sem espaço por causa de
    outra. Dentro de cada lista a ordem é a da API e o corte é no fim (na linha do tempo, no começo: ficam os
    marcos mais novos). O que ficou de fora vai em `limits`, com `truncated`; o bloco que a API deu como
    `timed_out` ganha um aviso de como pedir de novo (esperar não é cortar: sem `truncated`)."""
    if not isinstance(corpo, dict) or not isinstance(corpo.get("blocks"), dict):
        return corpo
    sem_blocos, avisos = _so_os_blocos_pedidos(corpo, blocos)
    tirou_blocos = len(sem_blocos["blocks"]) < len(corpo["blocks"])
    listas = _listas_da_analise(sem_blocos)
    totais = {caminho: len(lista) for caminho, lista in listas.items()}
    if limite:
        listas = {c: _fatia(c, lista, limite) for c, lista in listas.items()}
    base = _analise_com_as_listas(sem_blocos, listas, dict.fromkeys(listas, 0), set())
    # a ordem de entrada no orçamento é a de leitura: nos mais novos, de trás para a frente
    na_ordem_de_leitura = {
        c: lista[::-1] if c in LISTAS_DOS_MAIS_NOVOS else lista
        for c, lista in listas.items()
    }
    ficam = _quantos_cabem(base, na_ordem_de_leitura, TETO_DA_ANALISE)
    cortados = {c for c in listas if totais[c] > ficam[c]}
    novo = _analise_com_as_listas(sem_blocos, listas, ficam, cortados)
    if cortados:
        de_cada = ", ".join(
            f"{_nome_da_lista(c)} ({ficam[c]} de {totais[c]})" for c in cortados
        )
        avisos.append(
            f"A resposta foi cortada (pelo que cabe na conversa ou por `limite`); entregues: {de_cada}. Peça o "
            "resto por partes, com `blocos` (os nomes de `blocks`) ou menos itens por lista com `limite`."
        )
    avisos += _aviso_dos_atrasados(corpo)
    if not avisos:
        return novo
    return _com_aviso(novo, avisos, cortou=bool(cortados) or tirou_blocos)


# ---------------------------------------------------------------- as novidades: dizer por que veio vazio


def avisar_novidades_vazias(corpo: object) -> object:
    """Lista vazia de novidades com a frase que separa "nada mudou" de "o arquivo da pesquisa não chegou":
    `generated_at` vazio quer dizer que o servidor não tem o arquivo, e aí a lista vazia não prova ausência de
    novidade (ensaio de 20/11/2026: 7 dias, `total_news` 0 e `generated_at` nulo). Sem `truncated`."""
    if not isinstance(corpo, dict) or not isinstance(corpo.get("items"), list):
        return corpo
    if corpo["items"] or corpo.get("total_news"):
        return corpo
    gerado = corpo.get("generated_at")
    if not isinstance(gerado, str) or not gerado:
        aviso = (
            "O arquivo da pesquisa de novidades não chegou ao servidor (`generated_at` vazio): a lista vazia não "
            "quer dizer que nada mudou, só que não há leitura para dizer. O TickerLab precisa publicar o arquivo."
        )
    else:
        dias = corpo.get("days")
        periodo = f"nos últimos {dias} dias" if isinstance(dias, int) else "no período"
        aviso = (
            f"Sem novidade provada {periodo}; última geração do arquivo da pesquisa em {gerado[:10]}. "
            "Para olhar mais para trás, peça mais dias (`dias`, até 30)."
        )
    return _com_aviso(corpo, [aviso], cortou=False)
