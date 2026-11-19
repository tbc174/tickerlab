"""O recorte que faz a resposta de uma companhia aberta caber na conversa (ensaio de 19/11, linhas 984 e 955).

A API entrega tudo o que a chave vê, e cada valor vem com a fonte, o dia em que ficou público e, na organização do
piloto, a marca e a frase de piloto (ADR 0108, Emenda 2, D11.3: um bloco de piloto sem a frase é defeito). Uma linha
de demonstração tem 12 valores desses e pesa uns 2,5 mil caracteres; um período de uma companhia grande passa de
300 linhas e a ferramenta falhava mesmo com `fim_do_periodo`. A ficha de uma companhia aberta traz 60 e poucas
entregas de DFP e ITR, também inteiras. O corte é aqui, no conector: a frase de piloto de cada valor que sai
continua onde a API a pôs; o que não cabe fica de fora e **diz** que ficou, em `truncated` e `limits`.

Nada aqui vem da API como texto: as frases são fixas e só citam parâmetros que a ferramenta tem.
"""

from collections import Counter

from conector_remoto import saida

CHAVE_DAS_ENTREGAS = "periodic_filings"
CHAVE_DAS_LINHAS = "rows"
LIMITE_PADRAO_DAS_ENTREGAS = 8
LIMITE_MAXIMO_DAS_ENTREGAS = 100
# a folga para as frases de `limits` e para o resto do corpo
FOLGA_EM_CARACTERES = 4_000
# do que mais se pergunta ao que menos: resultado, balanço, caixa, valor adicionado, o resto, as mutações
ORDEM_DOS_DEMONSTRATIVOS = ("DRE", "BPA", "BPP", "DFC", "DVA", "DRA", "DMPL")
CONSOLIDADO, INDIVIDUAL = "con", "ind"


def _com_aviso(corpo: dict, avisos: list[str]) -> dict:
    """O corpo com `truncated` e os avisos em `limits`, depois dos que a API já pôs."""
    limites = corpo.get("limits")
    return corpo | {
        "truncated": True,
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


def _so_o_grupo_pedido(linhas: list[dict], visao: str) -> list[dict]:
    """`consolidado`: o consolidado de cada conta e, onde ela não tem, o individual; `individual` ou `ambos`."""
    if visao == "ambos":
        return linhas
    if visao == "individual":
        return [linha for linha in linhas if _valor(linha, "group") == INDIVIDUAL]
    com_consolidado = {
        _fato(linha)[:1] + _fato(linha)[2:]
        for linha in linhas
        if _valor(linha, "group") == CONSOLIDADO
    }
    return [
        linha
        for linha in linhas
        if _valor(linha, "group") == CONSOLIDADO
        or _fato(linha)[:1] + _fato(linha)[2:] not in com_consolidado
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
    no_corte: Counter,
    entregues: Counter,
) -> list[str]:
    avisos = []
    if outros_periodos:
        avisos.append(
            f"Período entregue: o que termina em {periodo}, o mais novo da base. A base tem também os que "
            f"terminam em {', '.join(outros_periodos[:6])}; peça um deles com `fim_do_periodo`."
        )
    if antigas:
        avisos.append(
            f"De cada conta, só a versão mais nova: {antigas} linha(s) de versão mais antiga ficaram de fora."
        )
    if do_grupo_de_fora:
        avisos.append(
            f"Consolidado onde a conta existe, individual onde não existe: {do_grupo_de_fora} linha(s) do outro "
            "grupo ficaram de fora; peça `visao` individual ou ambos."
        )
    if no_corte:
        avisos.append(
            "A resposta foi cortada para caber na conversa; ficaram de fora "
            f"{_lista_de(no_corte)} linha(s) por demonstrativo. Peça um `demonstrativo` (DRE, BPA, BPP, DFC, "
            "DVA, DRA, DMPL) ou uma `conta` (ex.: 3.01) para ver o resto."
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
