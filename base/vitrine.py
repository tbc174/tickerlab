"""A vitrine da base: o catálogo de contratos vira o que o site aberto mostra (plano do site para quem
analisa, 18/10/2026, PR 3; ADR 0099, itens 4 e 7).

Tudo aqui é função pura sobre o dicionário de `base/contratos/catalogo.json` (`{"tabelas": {...}}`):
nenhum número da página Dados é digitado à mão, e tabela ou fonte nova aparece sozinha no próximo
build. O que sai para o site aberto passa por três filtros: o órgão sai do texto da licença por uma
tabela fixa (licença nova que não casa **dá erro**, em vez de sumir), a frequência vira um rótulo curto
e a frase da tabela e o atraso perdem o que é conversa interna (código, ADR, servidor).
"""

import re
from dataclasses import dataclass

# o texto da licença → o órgão que o site mostra; uma linha por fonte do catálogo (são 15 em 18/10/2026)
ORGAOS: tuple[tuple[str, str], ...] = (
    (r"da CVM", "CVM"),
    (r"do Banco Central", "Banco Central"),
    (r"assessorias de M&A", "Assessorias de M&A"),
    (r"da ANP\b", "ANP"),
    (r"da ANAC\b", "ANAC"),
    (r"do ONS\b", "ONS"),
    (r"da ANEEL\b", "ANEEL"),
    (r"da Anatel\b", "Anatel"),
    (r"da ANS\b", "ANS"),
    (r"da SUSEP\b", "SUSEP"),
    (r"Receita", "Receita Federal"),
    (r"da PGFN\b", "PGFN"),
    (r"Tesouro", "Tesouro Nacional"),
    (r"Internet Archive", "Internet Archive"),
    (r"do USDA\b", "USDA"),
)
# o nome de cada módulo do catálogo, como o site o escreve
NOMES_DOS_MODULOS = {
    "mercado_e_empresas": "Mercado e empresas",
    "credito_e_fidc": "Crédito e FIDC",
    "ma": "M&A",
    "rede": "Rede de entidades",
    "governo_e_sancoes": "Governo e sanções",
    "macro": "Macro",
}
# o que a página diz sobre repassar os dados da fonte (o texto do contrato fala de ML e de revenda)
REPASSE_COM_ATRIBUICAO = "Pode ser repassado, citando a fonte."
REPASSE_ODBL = "Pode ser repassado, citando a fonte e compartilhando igual (ODbL)."
REPASSE_EM_CONSULTA = "Sem resposta escrita da fonte sobre uso comercial: tratado como não comercial até a resposta."
LIMITE_DA_FRASE = 200
LIMITE_DO_ATRASO = 110
SEM_CALENDARIO = "Sem calendário fixo"
EM_CONSULTA = "em consulta"
LICENCIADA = "licenciada"
# o que não vai para o site aberto: conversa interna (servidor, ADR, código)
_INTERNO = re.compile(
    r"servidor|VPS|arquivista|\bporta\b|cron|\bADR\b|Kuma|coletor|montagem|acervo|\bPR\b|\w+_\w+",
    re.IGNORECASE,
)
_ENTRE_PARENTESES = re.compile(r"\s*\([^)]*\)")
# o parêntese que cita uma decisão (ADR 0075, PR 2) ou um arquivo do repositório (base/regras.py)
_PARENTESES_INTERNO = re.compile(
    r"\s*\((?:(?:ADR|PR|passo|série|modelo)\b[^)]*|[^)]*\b\w+/\w+\.py[^)]*)\)",
    re.IGNORECASE,
)
_INTERNO_NA_FRASE = re.compile(
    r"servidor|VPS|\bADR\b|\b\w+/\w+\.py|lista de trabalho|\bdo app\b|\bdo Capital\b|\bB13\b",
    re.IGNORECASE,
)
# a frase acabou numa palavra que pede continuação (o código entre crases foi tirado do texto)
_FIM_PENDURADO = {"de", "da", "do", "desde", "a", "o", "em", "até", "com", "por"}
_FREQUENCIAS = (
    (r"(diária|toda noite)", "Diária"),
    (r"semanal", "Semanal"),
    (r"(mensal|um corte por fim de mês)", "Mensal"),
    (r"trimestral", "Trimestral"),
    (r"anual", "Anual"),
)


@dataclass(frozen=True)
class Fonte:
    orgao: str
    licenca: str  # o texto do contrato, sem número de decisão (`licenca_do_site`)
    repasse: str  # o que pode ser repassado (`repasse_do_site`)
    situacao: str  # "licenciada" ou "em consulta"
    modulos: tuple[str, ...]
    tabelas: int
    historico_desde: str  # a tabela mais antiga da fonte (ISO)


@dataclass(frozen=True)
class Modulo:
    chave: str
    nome: str
    tabelas: int


@dataclass(frozen=True)
class TabelaDoSite:
    tabela: str
    modulo: str
    frase: str
    orgao: str
    situacao: str
    frequencia: str
    atraso: str | None
    historico_desde: str


def orgao_da_licenca(licenca: str) -> str:
    for trecho, orgao in ORGAOS:
        if re.search(trecho, licenca):
            return orgao
    raise ValueError(
        f"licença sem órgão em base/vitrine.py::ORGAOS: {licenca!r} (acrescente a linha dela)"
    )


def situacao_da_licenca(licenca: str, revenda: str) -> str:
    """ "Licenciada" só quando a licença está escrita e a revenda confirmada; senão "em consulta"."""
    sem_resposta = revenda.startswith(("a confirmar", "não comercial"))
    if "perguntar" in licenca.lower() or sem_resposta:
        return EM_CONSULTA
    return LICENCIADA


def licenca_do_site(licenca: str) -> str:
    """O texto da licença sem a decisão interna entre parênteses ("(ADR 0082)")."""
    sem_decisao = _PARENTESES_INTERNO.sub("", licenca)
    return sem_decisao.replace("perguntar a licença", "reuso em consulta")


def repasse_do_site(licenca: str, situacao: str) -> str:
    if situacao == EM_CONSULTA:
        return REPASSE_EM_CONSULTA
    return REPASSE_ODBL if "ODbL" in licenca else REPASSE_COM_ATRIBUICAO


def fontes_do_catalogo(catalogo: dict) -> list[Fonte]:
    """Uma fonte por texto de licença, as de mais tabelas primeiro."""
    grupos: dict[str, list[dict]] = {}
    for tabela in catalogo["tabelas"].values():
        grupos.setdefault(tabela["licenca"], []).append(tabela)
    fontes = []
    for licenca, tabelas in grupos.items():
        revendas = [t["revenda"] for t in tabelas]
        em_consulta = [
            r for r in revendas if situacao_da_licenca(licenca, r) == EM_CONSULTA
        ]
        situacao = situacao_da_licenca(licenca, (em_consulta or revendas)[0])
        fontes.append(
            Fonte(
                orgao=orgao_da_licenca(licenca),
                licenca=licenca_do_site(licenca),
                repasse=repasse_do_site(licenca, situacao),
                situacao=situacao,
                modulos=tuple(sorted({t["modulo"] for t in tabelas})),
                tabelas=len(tabelas),
                historico_desde=min(
                    t["historico_desde"] for t in tabelas if t["historico_desde"]
                ),
            )
        )
    return sorted(fontes, key=lambda f: (-f.tabelas, f.orgao))


def modulos_do_catalogo(catalogo: dict) -> list[Modulo]:
    """Os módulos com a contagem de tabelas, os maiores primeiro."""
    contagem: dict[str, int] = {}
    for tabela in catalogo["tabelas"].values():
        contagem[tabela["modulo"]] = contagem.get(tabela["modulo"], 0) + 1
    for chave in contagem:
        if chave not in NOMES_DOS_MODULOS:
            raise ValueError(
                f"módulo sem nome em base/vitrine.py::NOMES_DOS_MODULOS: {chave!r}"
            )
    return [
        Modulo(chave, NOMES_DOS_MODULOS[chave], total)
        for chave, total in sorted(contagem.items(), key=lambda par: (-par[1], par[0]))
    ]


def tabelas_do_catalogo(catalogo: dict, frases: dict[str, str]) -> list[TabelaDoSite]:
    """Uma linha por tabela, na ordem do catálogo; a frase vem do dicionário (`primeira_frase`)."""
    return [
        TabelaDoSite(
            tabela=nome,
            modulo=t["modulo"],
            frase=frases[nome],
            orgao=orgao_da_licenca(t["licenca"]),
            situacao=situacao_da_licenca(t["licenca"], t["revenda"]),
            frequencia=frequencia_do_site(t["frequencia"]),
            atraso=atraso_do_site(t["atraso"]),
            historico_desde=t["historico_desde"],
        )
        for nome, t in catalogo["tabelas"].items()
    ]


# --- o texto que sai para o site aberto ----------------------------------------------------------


def frequencia_do_site(texto: str) -> str:
    """O texto longo do contrato vira um de seis rótulos (a frase inteira fica no contrato)."""
    minusculo = texto.lower()
    for padrao, rotulo in _FREQUENCIAS:
        if re.match(padrao, minusculo):
            return rotulo
    return SEM_CALENDARIO


def _fim_da_primeira_frase(texto: str) -> int:
    """Onde acaba a primeira frase: o primeiro ponto final **fora** de parênteses."""
    fundo = 0
    for i, letra in enumerate(texto):
        if letra == "(":
            fundo += 1
        elif letra == ")":
            fundo = max(0, fundo - 1)
        elif letra in ".!?" and fundo == 0 and texto[i + 1 : i + 2] in ("", " "):
            return i + 1
    return len(texto)


def primeira_frase(texto: str) -> str:
    """A primeira frase da descrição, sem código, sem número de ADR e com até `LIMITE_DA_FRASE` letras."""
    limpo = _PARENTESES_INTERNO.sub("", texto.replace("`", "")).strip()
    frase = limpo[: _fim_da_primeira_frase(limpo)].strip()
    interno = _INTERNO_NA_FRASE.search(frase)
    if interno:  # fica o que vem antes da última vírgula que precede o termo interno
        antes = re.split(r"[,:;]\s", frase[: interno.start()])
        if len(antes) > 1:
            frase = ", ".join(antes[:-1]).rstrip(",;:")
    cortada = len(frase) > LIMITE_DA_FRASE
    if cortada:
        corte = frase[:LIMITE_DA_FRASE]
        ultima = max(corte.rfind(separador) for separador in (", ", "; ", ": "))
        if (
            ultima >= LIMITE_DA_FRASE // 2
        ):  # prefere acabar numa vírgula a cortar no meio
            frase, cortada = corte[:ultima], False
        else:
            frase = corte.rsplit(" ", 1)[0]
    if frase.count("(") > frase.count(")"):  # nunca deixa um parêntese aberto
        frase = frase[: frase.rindex("(")]
    frase = frase.rstrip(",;: ")
    if cortada:
        return f"{frase}…"
    return frase if frase.endswith((".", "!", "?")) else f"{frase}."


def atraso_do_site(texto: str) -> str | None:
    """O atraso em uma frase curta; texto que fala de servidor, código ou montagem não sai (None)."""
    limpo = _ENTRE_PARENTESES.sub("", texto.replace("`", ""))
    curto = re.split(r";|\.\s", limpo.strip())[0].strip().rstrip(".:,")
    if not curto or len(curto) > LIMITE_DO_ATRASO or _INTERNO.search(curto):
        return None
    if curto.split()[-1].lower() in _FIM_PENDURADO:
        return None
    return curto
