"""A resposta da API em tabelas para a pessoa ler; toda saída termina com a fonte e a data de cada bloco.

A formatação é genérica sobre o envelope da API (`value`, `source`, `published_at`): campo novo que a API
passar a servir aparece sozinho, sem mudar a CLI. Os nomes dos campos saem como a API os dá (os mesmos do
`--json`), para a pessoa e o agente falarem dos mesmos nomes. Nenhum número é recalculado aqui.
"""

from collections.abc import Iterable, Mapping, Sequence

VAZIO = "—"
LARGURA_MAXIMA = 40  # caracteres por célula; o resto vira "…" (o --json traz tudo)
IDENTIFICACAO = {
    "cnpj": "CNPJ",
    "sector": "Setor",
    "name": "Nome",
    "known_at": "Como era em",
}
SEM_MILHAR = frozenset(
    {"year", "years"}
)  # campos que são um ano ou uma contagem de anos: 2025, não 2.025
AVISO_DE_CORTE = "Atenção: a resposta foi cortada no limite de linhas do plano; há mais dados que estes."
AVISO = "Nada aqui é recomendação de investimento."


CHAVE_DO_AVISO_DE_PILOTO = "pilot_notice"
CHAVE_DO_PILOTO = "pilot"
SEM_FRASE_DE_PILOTO = (
    "Dado de piloto: a resposta marcou o dado como de piloto mas não trouxe o aviso."
)


def e_de_piloto(valor: object) -> bool:
    """O campo (envelope) vem marcado pela API como dado de piloto."""
    return isinstance(valor, Mapping) and valor.get(CHAVE_DO_PILOTO) is True


def frase_do_envelope(envelope: Mapping) -> str:
    """A frase de piloto do próprio envelope; sem ela, a linha que diz que a resposta não a trouxe."""
    frase = envelope.get(CHAVE_DO_AVISO_DE_PILOTO)
    return frase if isinstance(frase, str) and frase.strip() else SEM_FRASE_DE_PILOTO


def frase_de_piloto_da_linha(linha: object) -> str | None:
    """A frase de piloto de uma linha (de qualquer profundidade dela), ou None se a linha não é de piloto."""
    for bloco in _percorrer(linha):
        if e_de_piloto(bloco):
            return frase_do_envelope(bloco)
    return None


def colunas_da_linha(linhas: Iterable[Mapping]) -> list[str]:
    """As colunas de uma tabela de linhas: as chaves dos itens, sem as marcas de piloto (vão na coluna própria)."""
    nomes = dict.fromkeys(nome for linha in linhas for nome in linha)
    return [n for n in nomes if n not in (CHAVE_DO_PILOTO, CHAVE_DO_AVISO_DE_PILOTO)]


def _percorrer(dado: object) -> Iterable[Mapping]:
    """Todo dicionário da resposta, de qualquer nível."""
    if isinstance(dado, Mapping):
        yield dado
        for valor in dado.values():
            yield from _percorrer(valor)
    elif isinstance(dado, list):
        for item in dado:
            yield from _percorrer(item)


def avisos_de_piloto(dado: object) -> list[str]:
    """As frases de piloto que a API mandou, distintas e na ordem; a CLI não escreve a frase, só repassa a que
    veio. Dado marcado como piloto sem frase vira uma linha que diz isso (nunca some em silêncio)."""
    frases: dict[str, None] = {}
    sem_frase = False
    for bloco in _percorrer(dado):
        frase = bloco.get(CHAVE_DO_AVISO_DE_PILOTO)
        if isinstance(frase, str) and frase.strip():
            frases[frase] = None
        elif e_de_piloto(bloco):
            sem_frase = True
    if sem_frase and not frases:
        frases[SEM_FRASE_DE_PILOTO] = None
    return list(frases)


def com_aviso_de_piloto(texto: str, dado: object) -> str:
    """Garante que toda frase de piloto da resposta aparece na saída (rede de segurança de toda tela)."""
    faltam = [f for f in avisos_de_piloto(dado) if f not in texto]
    if not faltam:
        return texto
    return "\n".join(f"Aviso de piloto: {f}" for f in faltam) + "\n\n" + texto


# A API diz o que a organização não pode consultar em campos `unavailable_<o que>` (lista; a lista de dados
# não diz nada sobre eles). Rótulo da tela por campo; o que não está aqui sai pelo próprio nome do campo.
PREFIXO_NAO_DISPONIVEL = "unavailable_"
ROTULOS_NAO_DISPONIVEIS = {
    "unavailable_event_types": "tipos de evento",
    "unavailable_link_types": "tipos de vínculo",
    "unavailable_signals": "sinais de comprador",
    "unavailable_filings": "entregas à CVM",
    "unavailable_figures": "números dos comparáveis",
    "unavailable_registration_fields": "campos do cadastro na Receita",
}


def nao_disponiveis(dado: object) -> dict[str, list[str]]:
    """O que a API disse que não está disponível para a organização, por rótulo (de qualquer nível da resposta)."""
    achados: dict[str, list[str]] = {}
    for bloco in _percorrer(dado):
        for chave, valores in bloco.items():
            if not (
                isinstance(chave, str)
                and chave.startswith(PREFIXO_NAO_DISPONIVEL)
                and isinstance(valores, list)
            ):
                continue
            rotulo = ROTULOS_NAO_DISPONIVEIS.get(
                chave, chave.removeprefix(PREFIXO_NAO_DISPONIVEL).replace("_", " ")
            )
            for valor in valores:
                if str(valor) not in achados.setdefault(rotulo, []):
                    achados[rotulo].append(str(valor))
    return {rotulo: valores for rotulo, valores in achados.items() if valores}


def aviso_de_nao_disponivel(dado: object) -> str | None:
    """A frase de tela: o que não está disponível para a organização e que o resultado não diz nada sobre isso."""
    itens = nao_disponiveis(dado)
    if not itens:
        return None
    lista = "; ".join(
        f"{rotulo}: {', '.join(valores)}" for rotulo, valores in itens.items()
    )
    return (
        f"Parte dos dados não está disponível para a sua organização ({lista}). Não foi consultada: o "
        "resultado abaixo não diz nada sobre ela."
    )


def com_aviso_de_nao_disponivel(texto: str, dado: object) -> str:
    """Garante que o aviso de indisponível aparece na saída de toda tela (rede de segurança)."""
    aviso = aviso_de_nao_disponivel(dado)
    if aviso is None or aviso in texto:
        return texto
    return aviso + "\n\n" + texto


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


def celula(valor: object, nome: str = "") -> str:
    """Um valor como texto curto: número no jeito brasileiro (o ano sem milhar), sim e não, vazio como
    travessão. `nome` é o do campo."""
    if e_envelope(valor):
        valor = valor["value"]  # type: ignore[index]
    if valor is None or valor == "":
        texto = VAZIO
    elif isinstance(valor, bool):
        texto = "sim" if valor else "não"
    elif nome in SEM_MILHAR and isinstance(valor, int):
        texto = str(valor)
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


def _rodape_de_piloto(frases: Iterable[str | None]) -> list[str]:
    """Abaixo de uma tabela com dado de piloto, a frase de cada linha marcada (uma vez por frase)."""
    return [f"Aviso de piloto: {f}" for f in dict.fromkeys(f for f in frases if f)]


def _tabela_de_campos(campos: Mapping[str, Mapping]) -> str:
    com_piloto = any(e_de_piloto(env) for env in campos.values())
    cabecalho = ["campo", "valor", "fonte", "público em"] + (
        ["piloto"] if com_piloto else []
    )
    corpo = [
        [nome, celula(env, nome), str(env["source"]), _data_do_envelope(env)]
        + (["sim" if e_de_piloto(env) else ""] if com_piloto else [])
        for nome, env in campos.items()
    ]
    frases = [frase_de_piloto_da_linha(env) for env in campos.values()]
    return "\n".join([tabela(cabecalho, corpo), *_rodape_de_piloto(frases)])


def _fonte_e_data_da_linha(linha: Mapping) -> tuple[str, str]:
    """A fonte e a data de uma linha: as do primeiro campo dela (a API dá uma fonte por linha)."""
    for valor in linha.values():
        if e_envelope(valor):
            return str(valor["source"]), _data_do_envelope(valor)
    return VAZIO, VAZIO


def _tabela_de_linhas(linhas: Sequence[Mapping]) -> str:
    colunas = colunas_da_linha(linhas)
    com_fonte = any(e_envelope(v) for linha in linhas for v in linha.values())
    frases = [frase_de_piloto_da_linha(linha) for linha in linhas]
    com_piloto = any(frases)
    cabecalho = [
        *colunas,
        *(("fonte", "público em") if com_fonte else ()),
        *(("piloto",) if com_piloto else ()),
    ]
    corpo = []
    for linha, frase in zip(linhas, frases, strict=True):
        celulas = [celula(linha.get(nome), nome) for nome in colunas]
        if com_fonte:
            celulas += _fonte_e_data_da_linha(linha)
        if com_piloto:
            celulas.append("sim" if frase else "")
        corpo.append(celulas)
    return "\n".join([tabela(cabecalho, corpo), *_rodape_de_piloto(frases)])


def tem_listas(item: Mapping) -> bool:
    """O item da lista guarda outras listas (as séries do setor): vira um bloco, não uma linha de tabela."""
    return any(isinstance(valor, list) for valor in item.values())


def rotulo_do_item(item: Mapping, posicao: int) -> str:
    """O nome do bloco de um item: o primeiro texto solto dele (a série), ou a posição na lista."""
    for valor in item.values():
        if isinstance(valor, str):
            return valor
    return str(posicao)


def _lista(titulo: str, itens: list, partes: list[str]) -> None:
    """Uma lista da resposta: linhas numa tabela, textos como itens, e o item com listas dentro em blocos."""
    dicionarios = [item for item in itens if isinstance(item, Mapping)]
    if dicionarios and all(tem_listas(item) for item in dicionarios):
        for posicao, item in enumerate(dicionarios, start=1):
            _blocos(f"{titulo} › {rotulo_do_item(item, posicao)}", item, partes)
        return
    partes.append(f"## {titulo}")
    if dicionarios:
        partes.append(_tabela_de_linhas(dicionarios))
    elif textos := [str(item) for item in itens if isinstance(item, str)]:
        partes.append("\n".join(f"- {texto}" for texto in textos))
    else:
        partes.append(VAZIO)


def _blocos(titulo: str, dado: Mapping, partes: list[str]) -> None:
    """Um bloco por nível da resposta: campos com fonte numa tabela, listas em tabela, o resto em linhas."""
    campos = {nome: valor for nome, valor in dado.items() if e_envelope(valor)}
    soltos = [
        f"{IDENTIFICACAO.get(nome, nome)}: {celula(valor, nome)}"
        for nome, valor in dado.items()
        if not e_envelope(valor)
        and not isinstance(valor, Mapping | list)
        and nome not in ("truncated", CHAVE_DO_AVISO_DE_PILOTO, CHAVE_DO_PILOTO)
    ]
    if titulo:
        partes.append(f"## {titulo}")
    if isinstance(dado.get(CHAVE_DO_AVISO_DE_PILOTO), str):
        partes.append(f"Aviso de piloto: {dado[CHAVE_DO_AVISO_DE_PILOTO]}")
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
            _lista(filho, valor, partes)
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


def _paginada(corpo: Mapping, lista: str, nome: str, vazia: str) -> str:
    """Uma resposta em páginas: quantas linhas vieram, se há mais, e cada linha com a fonte e a data."""
    linhas = [e for e in corpo.get(lista) or [] if isinstance(e, Mapping)]
    topo = f"{len(linhas)} {nome} nesta resposta." if linhas else vazia
    faltou = aviso_de_nao_disponivel(corpo)
    if faltou:  # o "nenhum" só vale para o que foi consultado
        topo = f"{faltou} " + (
            f"{len(linhas)} {nome} nesta resposta."
            if linhas
            else f"Nos demais, nenhum dos {nome} até o dia. Sem evento não quer dizer que nada aconteceu."
        )
    if corpo.get("next_cursor"):
        topo += (
            " Há mais: rode de novo com --todas para buscar as outras páginas (cada página é um pedido "
            "da quota)."
        )
    resto = {chave: valor for chave, valor in corpo.items() if chave != "next_cursor"}
    return f"{topo}\n\n{resposta_de_dado(resto)}"


def prospeccao(corpo: Mapping) -> str:
    """A busca de empresas: quantas vieram, se há mais, e cada empresa com a fonte e a data."""
    return _paginada(
        corpo,
        "companies",
        "empresas",
        "Nenhuma empresa com estes filtros. Afrouxe algum (CNAE mais curto, sem município...).",
    )


def _ponta(ponta: object) -> str:
    """Uma ponta do vínculo em uma célula: a razão social que valia no dia e a raiz do CNPJ."""
    if not isinstance(ponta, Mapping):
        return VAZIO
    nome = ponta.get("legal_name")
    nome = nome.get("value") if isinstance(nome, Mapping) else None
    raiz = f"({ponta.get('cnpj_root') or VAZIO})"
    return f"{nome} {raiz}" if nome else raiz


def vinculos_em_linhas(corpo: Mapping) -> dict:
    """A resposta dos vínculos com as pontas `from` e `to` achatadas em `de` e `para` (tabela e planilha);
    o `--json` não passa por aqui. A fonte do nome (Receita) continua em `sources`."""
    linhas = []
    for vinculo in corpo.get("links") or []:
        if not isinstance(vinculo, Mapping):
            continue
        resto = {k: v for k, v in vinculo.items() if k not in ("from", "to")}
        origem, destino = vinculo.get("from"), vinculo.get("to")
        achatada = {
            "hops": resto.pop("hops", None),
            "kind": resto.pop("kind", None),
            "de": _ponta(origem),
            "para": _ponta(destino),
            **resto,
        }
        # a ponta achatada em texto perderia a marca de piloto do nome: a linha a leva
        frase = frase_de_piloto_da_linha([origem, destino])
        if frase and frase_de_piloto_da_linha(resto) is None:
            achatada[CHAVE_DO_PILOTO] = True
            achatada[CHAVE_DO_AVISO_DE_PILOTO] = frase
        linhas.append(achatada)
    return {**corpo, "links": linhas}


def eventos(corpo: Mapping) -> str:
    """Os eventos da empresa: quantos vieram, se há mais, e cada um com a fonte e a data."""
    return _paginada(
        corpo,
        "events",
        "eventos",
        "Nenhum evento da empresa até o dia. Sem evento não quer dizer que nada aconteceu.",
    )


def dossie(corpo: Mapping) -> str:
    """O dossiê: quantos pedidos gastou, o que ficou de fora, e depois cada seção com fonte e data."""
    lacunas = [g for g in corpo.get("gaps") or [] if isinstance(g, Mapping)]
    topo = f"Dossiê: {corpo.get('requests_used')} pedidos gastos da quota."
    if lacunas:
        topo += " Ficou de fora: " + "; ".join(
            f"{g.get('section')} ({g.get('reason')})" for g in lacunas
        )
    return f"{topo}\n\n{resposta_de_dado(corpo)}"


def setores(corpo: Mapping) -> str:
    """Os setores que a ficha da noite tem, com o dia dela; a lista não traz dado nem gasta a quota."""
    lista = [s for s in corpo.get("sectors") or [] if isinstance(s, Mapping)]
    if not lista:
        return (
            "Nenhum setor disponível agora: a ficha da noite ainda não gravou nenhum."
        )
    topo = tabela(
        ("setor", "nome", "como era em"),
        [
            (celula(s.get("sector")), celula(s.get("name")), celula(s.get("known_at")))
            for s in lista
        ],
    )
    exemplo = celula(lista[0].get("sector"))
    return (
        f"{topo}\n\nPeça um setor com `tickerlab setor {exemplo}` (mercado, concentração e as companhias "
        "abertas dele, com a fonte de cada número)."
    )


def _marca_do_recorte(recorte: object) -> str:
    """Avisa, fora das aspas, que o trecho é só um pedaço do original (nada inventado dentro delas)."""
    partes = {
        "inicio": "o original continua antes",
        "fim": "o original continua depois",
        "ambos": "o original continua antes e depois",
    }
    aviso = partes.get(str(recorte))
    return f"  [recorte: {aviso}]" if aviso else ""


def novidades(corpo: Mapping) -> str:
    """As fontes que a pesquisa provou na janela: órgão, data, trecho literal e o hash do original."""
    itens = [i for i in corpo.get("items") or [] if isinstance(i, Mapping)]
    if not itens:
        return "Nenhuma fonte nova provada na semana."
    blocos = [
        f"{celula(i.get('agency'))} · {celula(i.get('date'))}\n"
        f"  “{i.get('excerpt')}”{_marca_do_recorte(i.get('excerpt_cut'))}\n"
        f"  original: {i.get('source_url')}\n"
        f"  sha256: {i.get('original_sha256')}"
        for i in itens
    ]
    cabeca = f"{len(itens)} fonte(s) provada(s) pela pesquisa (trecho literal e hash do original):"
    return "\n\n".join([cabeca, *blocos, AVISO])


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


def planilha_gravada(arquivos: Sequence[object], corpo: Mapping) -> str:
    """A confirmação de que a planilha foi gravada: onde, as fontes a citar e o aviso."""
    lista = "\n".join(f"- {arquivo}" for arquivo in arquivos)
    return "\n\n".join(
        [
            f"Planilha gravada (cada linha com a fonte e a data):\n{lista}",
            *(f"Aviso de piloto: {f}" for f in avisos_de_piloto(corpo)),
            *([aviso] if (aviso := aviso_de_nao_disponivel(corpo)) else []),
            fontes(corpo.get("sources")),
            AVISO,
        ]
    )
