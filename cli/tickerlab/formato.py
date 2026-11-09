"""A resposta da API em tabelas para a pessoa ler; toda saída termina com a fonte e a data de cada bloco.

A formatação é genérica sobre o envelope da API (`value`, `source`, `published_at`): campo novo que a API
passar a servir aparece sozinho, sem mudar a CLI. Os nomes dos campos saem como a API os dá (os mesmos do
`--json`), para a pessoa e o agente falarem dos mesmos nomes. Nenhum número é recalculado aqui.
"""

from collections.abc import Iterable, Mapping, Sequence

VAZIO = "—"
LARGURA_MAXIMA = 40  # caracteres por célula; o resto vira "…" (o --json traz tudo)
IDENTIFICACAO = {"cnpj": "CNPJ", "known_at": "Como era em"}
AVISO_DE_CORTE = "Atenção: a resposta foi cortada no limite de linhas do plano; há mais dados que estes."
AVISO = "Nada aqui é recomendação de investimento."


def e_envelope(valor: object) -> bool:
    """Diz se o valor é um campo no envelope da API (valor, fonte e data)."""
    return isinstance(valor, Mapping) and "value" in valor and "source" in valor


def _numero(valor: float) -> str:
    if valor == int(valor) and abs(valor) < 1e15:
        texto = f"{int(valor):,}"
    else:
        texto = f"{valor:,.2f}"
    # o jeito brasileiro: ponto nos milhares, vírgula nos decimais
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def celula(valor: object) -> str:
    """Um valor como texto curto: número no jeito brasileiro, sim e não, vazio como travessão."""
    if e_envelope(valor):
        valor = valor["value"]  # type: ignore[index]
    if valor is None or valor == "":
        texto = VAZIO
    elif isinstance(valor, bool):
        texto = "sim" if valor else "não"
    elif isinstance(valor, int | float):
        texto = _numero(float(valor))
    else:
        texto = str(valor)
    if len(texto) > LARGURA_MAXIMA:
        texto = texto[: LARGURA_MAXIMA - 1] + "…"
    return texto


def tabela(cabecalho: Sequence[str], linhas: Iterable[Sequence[str]]) -> str:
    """Uma tabela de texto com as colunas alinhadas."""
    linhas = [list(linha) for linha in linhas]
    larguras = [
        max([len(titulo), *(len(linha[i]) for linha in linhas)])
        for i, titulo in enumerate(cabecalho)
    ]

    def montar(celulas: Sequence[str]) -> str:
        return "  ".join(c.ljust(larguras[i]) for i, c in enumerate(celulas)).rstrip()

    regua = "  ".join("-" * largura for largura in larguras)
    return "\n".join([montar(cabecalho), regua, *(montar(linha) for linha in linhas)])


def _data_do_envelope(envelope: Mapping) -> str:
    return celula(envelope.get("published_at"))


def _tabela_de_campos(campos: Mapping[str, Mapping]) -> str:
    return tabela(
        ("campo", "valor", "fonte", "público em"),
        [
            (nome, celula(env), str(env["source"]), _data_do_envelope(env))
            for nome, env in campos.items()
        ],
    )


def _fonte_e_data_da_linha(linha: Mapping) -> tuple[str, str]:
    """A fonte e a data de uma linha: as do primeiro campo dela (a API dá uma fonte por linha)."""
    for valor in linha.values():
        if e_envelope(valor):
            return str(valor["source"]), _data_do_envelope(valor)
    return VAZIO, VAZIO


def _tabela_de_linhas(linhas: Sequence[Mapping]) -> str:
    colunas = list(dict.fromkeys(nome for linha in linhas for nome in linha))
    com_fonte = any(e_envelope(v) for linha in linhas for v in linha.values())
    cabecalho = [*colunas, *(("fonte", "público em") if com_fonte else ())]
    corpo = []
    for linha in linhas:
        celulas = [celula(linha.get(nome)) for nome in colunas]
        if com_fonte:
            celulas += _fonte_e_data_da_linha(linha)
        corpo.append(celulas)
    return tabela(cabecalho, corpo)


def _blocos(titulo: str, dado: Mapping, partes: list[str]) -> None:
    """Um bloco por nível da resposta: campos com fonte numa tabela, listas em tabela, o resto em linhas."""
    campos = {nome: valor for nome, valor in dado.items() if e_envelope(valor)}
    soltos = [
        f"{IDENTIFICACAO.get(nome, nome)}: {celula(valor)}"
        for nome, valor in dado.items()
        if not e_envelope(valor)
        and not isinstance(valor, Mapping | list)
        and nome != "truncated"
    ]
    if titulo:
        partes.append(f"## {titulo}")
    if soltos:
        partes.append("\n".join(soltos))
    if campos:
        partes.append(_tabela_de_campos(campos))
    for nome, valor in dado.items():
        if nome == "sources" or e_envelope(valor):
            continue
        filho = f"{titulo} › {nome}" if titulo else nome
        if isinstance(valor, Mapping):
            _blocos(filho, valor, partes)
        elif isinstance(valor, list):
            partes.append(f"## {filho}")
            dicionarios = [item for item in valor if isinstance(item, Mapping)]
            partes.append(_tabela_de_linhas(dicionarios) if dicionarios else VAZIO)
    if dado.get("truncated") is True:
        partes.append(AVISO_DE_CORTE)


def fontes(lista: object) -> str:
    """O bloco final: cada fonte usada, com a licença e a frase de atribuição que ela pede."""
    itens = [item for item in lista or [] if isinstance(item, Mapping)]  # type: ignore[union-attr]
    if not itens:
        return "Fontes: nenhuma fonte nesta resposta."
    return "Fontes (cite ao usar estes números):\n" + "\n".join(
        f"- {item.get('source')}: {item.get('attribution')} (licença: {item.get('license')})"
        for item in itens
    )


def resposta_de_dado(corpo: Mapping) -> str:
    """Empresa, demonstrações ou fundo: os blocos, a fonte e a data de cada um, e as fontes no fim."""
    partes: list[str] = []
    _blocos("", corpo, partes)
    partes += [fontes(corpo.get("sources")), AVISO]
    return "\n\n".join(partes)


def catalogo(corpo: Mapping) -> str:
    """O que a chave pode pedir hoje: conjunto, finalidade, campo e fonte, e as licenças no fim."""
    conjuntos = [c for c in corpo.get("datasets") or [] if isinstance(c, Mapping)]
    if not conjuntos:
        topo = (
            "A sua chave ainda não tem nenhum conjunto liberado. Fale com o TickerLab para conferir o "
            "contrato da sua organização."
        )
    else:
        topo = tabela(
            ("conjunto", "finalidade", "campo", "fonte"),
            [
                (
                    str(c.get("dataset")),
                    str(c.get("purpose")),
                    str(campo.get("field")),
                    str(campo.get("source")),
                )
                for c in conjuntos
                for campo in c.get("fields") or []
            ],
        )
    return "\n\n".join([topo, fontes(corpo.get("sources"))])


def consumo(corpo: Mapping) -> str:
    """O consumo do mês da organização e os limites do plano; a fonte é a própria conta na API."""
    limites = corpo.get("limits") or {}
    linhas = [
        ("mês", corpo.get("month")),
        ("plano", corpo.get("plan")),
        ("pedidos no mês", corpo.get("requests")),
        ("pedidos que ainda cabem", corpo.get("remaining_requests")),
        ("linhas servidas", corpo.get("rows")),
        ("pedidos negados", corpo.get("denied")),
        ("limite por minuto", limites.get("requests_per_minute")),
        ("limite por mês", limites.get("requests_per_month")),
        ("linhas por resposta", limites.get("rows_per_response")),
    ]
    texto = tabela(("item", "valor"), [(nome, celula(v)) for nome, v in linhas])
    return f"{texto}\n\nFonte: TickerLab, consumo da sua organização no mês {corpo.get('month')} (UTC)."
