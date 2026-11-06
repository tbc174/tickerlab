"""Fatos dos posts das assessorias de M&A: uma linha por negócio (ADR 0082, série 5 do plano de M&A).

O arquivista guardou cada página como veio (`base/arquivo/assessorias.py`); aqui só se lê o que a
página e o título dizem, sem texto do post e sem pessoa física. A página da IGC é feita de listas
(Webflow): a empresa que a assessoria assessorou (`advised-company`), a contraparte
(`target-company`) e o país. O título (o fim do endereço) diz o tipo e o sentido do negócio ("a X foi
adquirida pela Y", "X vendeu participação minoritária para Y", "X concluiu a emissão de um CRI").

Como os papéis saem (testes em `tests/test_base_ma_assessorias.py`):
- o tipo vem de palavras do título, numa ordem fixa (`REGRAS`): dívida, fusão, joint venture, venda
  de ativo, minoritária, majoritária, participação sem tamanho, financiamento, rodada, aquisição;
- o verbo divide o título: na voz passiva ("foi adquirida pela", "vendeu ... para") quem vem antes é
  a alvo; na ativa ("adquiriu", "acquired") quem vem antes compra;
- cada empresa da página vai para o papel do pedaço do título em que o nome dela aparece; a
  controladora citada ("subsidiária da W", "empresa do grupo W") vira vendedor do lado da alvo e
  outra parte do lado de quem compra;
- nome que não aparece no título: se o papel do lado dele ficou vazio, a página decide (assessorada
  de um lado, contraparte do outro; `papeis_por = "pagina"`); senão vai para `outras_partes`;
- fusão e joint venture não têm alvo nem comprador; dívida e financiamento, só quem captou.

O que nunca entra: a lista `team` (a equipe da assessoria) nem é lida; nenhuma coluna guarda texto do
título (só códigos, números e os nomes das empresas tirados dos campos da página); o setor e o valor
ficam vazios quando a página não diz.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pandas as pd

LIMITE_DO_TEXTO = 300  # nenhuma célula passa disso (regra do dicionário de M&A)
SEPARADOR = "; "
SEM_TIPO = "desconhecido"
COLUNAS = (
    "assessoria",
    "url",
    "sha256",
    "coletado_em",
    "tipo",
    "regra",
    "alvo",
    "comprador",
    "vendedor",
    "outras_partes",
    "cliente",
    "contraparte",
    "papeis_por",
    "lado_da_assessoria",
    "setor",
    "paises",
    "valor",
    "moeda",
    "conferencia",
)

# --- leitura da página ------------------------------------------------------------------------------
CLIENTE = "advised-company"
CONTRAPARTE = "target-company"
PAISES = "countries"
LISTAS_LIDAS = (
    CLIENTE,
    CONTRAPARTE,
    PAISES,
)  # `team` (a equipe) fica fora de propósito


@dataclass
class Empresa:
    chave: str  # o fim de `/transaction-company/<chave>`
    nome: str | None = None


@dataclass
class Pagina:
    clientes: list[Empresa] = field(default_factory=list)
    contrapartes: list[Empresa] = field(default_factory=list)
    paises: list[str] = field(default_factory=list)


class _Leitor(HTMLParser):
    """Anda pelas listas do Webflow (`fs-list-instance`) e guarda só as três que interessam."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pagina = Pagina()
        self._lista: str | None = None
        self._profundidade = 0
        self._empresa: Empresa | None = None
        self._no_titulo = False
        self._no_pais = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if self._lista is None:
            if tag == "div" and a.get("fs-list-element") == "wrapper":
                instancia = a.get("fs-list-instance")
                if instancia in LISTAS_LIDAS:
                    self._lista, self._profundidade = instancia, 1
            return
        if tag == "div":
            self._profundidade += 1
            self._no_pais = (
                self._lista == PAISES and a.get("fs-list-field") == "country"
            )
        elif tag == "a" and self._lista in (CLIENTE, CONTRAPARTE):
            self._empresa = self._da_lista(a.get("href") or "")
        elif tag == "h3":
            self._no_titulo = True

    def _da_lista(self, href: str) -> Empresa | None:
        chave = href.rstrip("/").rsplit("/", 1)[-1]
        if not chave:
            return None
        empresas = (
            self.pagina.clientes if self._lista == CLIENTE else self.pagina.contrapartes
        )
        for empresa in empresas:
            if empresa.chave == chave:
                return empresa
        empresas.append(Empresa(chave))
        return empresas[-1]

    def handle_endtag(self, tag: str) -> None:
        if self._lista is None:
            return
        if tag == "h3":
            self._no_titulo = False
        elif tag == "div":
            self._no_pais = False
            self._profundidade -= 1
            if self._profundidade == 0:
                self._lista, self._empresa = None, None

    def handle_data(self, data: str) -> None:
        texto = " ".join(data.split())
        if not texto:
            return
        if self._no_pais and texto not in self.pagina.paises:
            self.pagina.paises.append(texto)
        elif self._no_titulo and self._empresa is not None and not self._empresa.nome:
            self._empresa.nome = texto[:LIMITE_DO_TEXTO]


def ler_pagina(html: bytes) -> Pagina:
    leitor = _Leitor()
    leitor.feed(html.decode("utf-8", errors="replace"))
    leitor.close()
    return leitor.pagina


# --- o título ---------------------------------------------------------------------------------------
def palavras(texto: str) -> str:
    """Minúsculas, sem acento, só letras e números separados por um espaço."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", sem_acento.lower()))


def titulo_da_url(url: str) -> str:
    return palavras(urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1])


@dataclass(frozen=True)
class Regra:
    codigo: str
    tipo: str
    palavras: str  # expressão regular sobre o título já em `palavras`


# a primeira que casa decide o tipo (ordem medida nas 272 páginas da IGC em 16/10/2026)
REGRAS = (
    Regra(
        "divida",
        "DCM",
        r"\b(cri|cra|certificados? de recebiveis|debentures?|notas? comercia(l|is)|cpr f|fidcs?)\b",
    ),
    Regra(
        "fusao", "FUSAO", r"\b(fusao|fundiram|uniram suas operacoes|merged|merger)\b"
    ),
    Regra(
        "jv",
        "JV",
        r"\b(joint venture|alianca estrategica|parceria estrategica|strategic alliance)\b",
    ),
    Regra(
        "venda_de_ativo",
        "VENDA_ATIVO",
        r"\b(ativos|assets|division|platform|usinas|hoteis|rede de escolas|complex)\b",
    ),
    Regra(
        "minoritaria",
        "AQ_MINORITARIA",
        r"\b(minoritari[ao]|minority)\b",
    ),
    Regra(
        "majoritaria",
        "AQ_CONTROLE",
        r"\b(majoritari[ao]|majority|acquired 100|vende 100|adquiriu 100)\b",
    ),
    Regra(
        "participacao",
        SEM_TIPO,  # vendeu uma fatia sem dizer quanto: as partes ficam, o tipo não
        r"\b(participacao|participacoes|stake|quotas)\b",
    ),
    Regra("financiamento", SEM_TIPO, r"\b(financiamento|linha de|emprestimo)\b"),
    Regra(
        "rodada",
        "PE_VC",
        r"\b(rodada|round|series [a-e]|serie [a-e]|investimento|investment|raised|captacao)\b",
    ),
    Regra(
        "aquisicao",
        "AQ_CONTROLE",
        # "W vendeu X para Y" sem dizer participação nem ativo: a empresa inteira mudou de dono
        r"\b(adquirid[ao]s?|acquired|adquiriu|adquire|acquires|vendeu|vende|venderam|sold)\b",
    ),
)
CAPTACAO = {"divida", "financiamento"}  # quem a assessoria assessorou captou dinheiro
PARTES = {"fusao", "jv"}  # fusão e joint venture: só partes, sem alvo nem comprador

# o verbo que divide o título; `antes` diz o papel de quem vem antes dele
PASSIVA = re.compile(
    r"\b((foi|e|foram|was|were|has been|have been) (adquirid[ao]s?|acquired)"
    r"|vendeu|vende|venderam|sold|transferiu|recebeu|receberam|received|recieved|secures"
    r"|realizou|realizaram|completed|held|raised|captou|concluiu|conclui)\b"
)
ATIVA = re.compile(
    r"\b(adquiriu|adquire|acquired|acquires|acquiring|realizou investimento)\b"
)
VENDA = re.compile(r"^(vendeu|vende|venderam|sold|transferiu)$")
PARA = re.compile(r"\b(para|to|ao|aos)\b")  # "vendeu a X para Y": X é a alvo, Y compra
DE = re.compile(r"\bfrom\b")  # "acquired X from Y": Y vende
# controladora citada logo antes do nome ("subsidiária da W") ou logo depois ("W portfolio company")
CONTROLADORA = re.compile(
    r"\b(empresa d[ao]( grupo| portfolio d[ao])?|subsidiaria d[ao]|parte d[ao]|companhias d[ao]"
    r"|do grupo|subsidiary of( the [a-z]+ group)?|(?<![0-9] )of|empresa investida (pel[ao]|d[ao])"
    r"|acionista d[ao])$"
)
CONTROLADORA_DEPOIS = re.compile(r"^(an? )?portfolio company\b")
# palavras que não distinguem uma empresa de outra no título
GENERICAS = frozenset(
    {"a", "o", "e", "de", "da", "do", "das", "dos", "the", "and", "of", "grupo", "group", "banco", "bank", "sa", "s", "inc", "ltda", "capital", "partners", "investimentos", "investments", "participacoes", "holding", "holdings", "brasil", "brazil", "international", "corporation", "company", "companhia", "cia", "management", "gestao", "asset", "private", "equity", "fund", "fundo", "ventures", "solutions", "tecnologia", "technologies", "sistemas", "global", "latam", "latin", "energia", "energy", "seguros", "saude", "health", "digital", "rede", "casa", "br"}
)  # fmt: skip
SUFIXO_DO_SITE = re.compile(
    r"(?=[a-z]*\d)[a-z0-9]{5}|\d+"
)  # Webflow: "beta-x7k2p", "beta-2"


def _formas(empresa: Empresa) -> list[str]:
    """Como o nome pode aparecer no título: pela chave do endereço e pelo nome na página."""
    formas = []
    for texto in (empresa.chave.replace("-", " "), empresa.nome or ""):
        partes = palavras(texto).split()
        if len(partes) > 1 and SUFIXO_DO_SITE.fullmatch(partes[-1]):
            partes = partes[:-1]
        if partes and " ".join(partes) not in formas:
            formas.append(" ".join(partes))
    return formas


def _onde(empresa: Empresa, titulo: str) -> int | None:
    """Onde o nome aparece no título (posição da primeira letra), ou None."""
    texto = f" {titulo} "
    achados = []
    for forma in _formas(empresa):
        if (i := texto.find(f" {forma} ")) >= 0:
            achados.append(i)
            continue
        junto = forma.replace(" ", "")
        if len(junto) >= 5 and (i := titulo.replace(" ", "").find(junto)) >= 0:
            # posição aproximada: conta as letras até ali no título com espaços
            letras = 0
            for j, c in enumerate(titulo):
                if letras == i:
                    achados.append(j)
                    break
                letras += c != " "
            continue
        for palavra in forma.split():
            if (
                len(palavra) >= 2
                and palavra not in GENERICAS
                and (i := texto.find(f" {palavra} ")) >= 0
            ):
                achados.append(i)
                break
    return min(achados) if achados else None


def _controladora(titulo: str, posicao: int, empresa: Empresa) -> bool:
    antes = titulo[:posicao].strip()
    depois = titulo[posicao:]
    forma = next((f for f in _formas(empresa) if depois.startswith(f)), "")
    return bool(CONTROLADORA.search(antes)) or bool(
        forma and CONTROLADORA_DEPOIS.match(depois[len(forma) :].strip())
    )


@dataclass
class _Papeis:
    alvo: list[str] = field(default_factory=list)
    comprador: list[str] = field(default_factory=list)
    vendedor: list[str] = field(default_factory=list)
    outras: list[str] = field(default_factory=list)
    lado: str | None = None
    por: str | None = None


def _nome(empresa: Empresa) -> str:
    return (empresa.nome or empresa.chave)[:LIMITE_DO_TEXTO]


def _papel_pela_posicao(
    titulo: str, posicao: int, verbo: re.Match[str], ativa: bool
) -> str:
    """alvo, comprador ou vendedor, conforme o pedaço do título em que o nome está.

    `sujeito_da_venda`: quem vem antes de "vendeu"; é a alvo ("X vendeu participação para Y") ou o
    vendedor ("W vendeu a X para Y"), o que só se sabe depois de ver os outros nomes.
    """
    if posicao < verbo.start():
        if ativa:
            return "comprador"
        return "sujeito_da_venda" if VENDA.match(verbo.group(0)) else "alvo"
    resto = titulo[verbo.end() :]
    deslocamento = posicao - verbo.end()
    if ativa:
        de = DE.search(resto)
        return "vendedor" if de and deslocamento >= de.start() else "alvo"
    if VENDA.match(verbo.group(0)):
        para = PARA.search(resto)
        return "alvo" if para and deslocamento < para.start() else "comprador"
    return "comprador"


def _pelo_titulo(
    pagina: Pagina, titulo: str, verbo: re.Match[str], ativa: bool, venda_de_ativo: bool
) -> tuple[_Papeis, dict[str, str], dict[str, list[Empresa]]]:
    """Os papéis de quem aparece no título; devolve também o papel de cada empresa assessorada e
    quem ficou de fora."""
    papeis = _Papeis()
    lado_de: dict[
        str, str
    ] = {}  # nome da assessorada → papel, para saber o lado da assessoria
    sem_lugar: dict[str, list[Empresa]] = {CLIENTE: [], CONTRAPARTE: []}
    achadas: list[tuple[str, Empresa, int, str]] = []
    for lista, empresas in (
        (CLIENTE, pagina.clientes),
        (CONTRAPARTE, pagina.contrapartes),
    ):
        for empresa in empresas:
            posicao = _onde(empresa, titulo)
            if posicao is None:
                sem_lugar[lista].append(empresa)
            else:
                papel = _papel_pela_posicao(titulo, posicao, verbo, ativa)
                achadas.append((lista, empresa, posicao, papel))
    vendeu_outra = any(papel == "alvo" for *_, papel in achadas)
    for lista, empresa, posicao, papel in achadas:
        if papel == "sujeito_da_venda":
            papel = "vendedor" if vendeu_outra or venda_de_ativo else "alvo"
        if venda_de_ativo and papel == "alvo":
            papel = (
                "vendedor"  # quem vende o ativo; o ativo em si não é empresa da página
            )
        if _controladora(titulo, posicao, empresa):
            papel = "vendedor" if papel in ("alvo", "vendedor") else "outras"
        getattr(papeis, papel).append(_nome(empresa))
        if lista == CLIENTE:
            lado_de[_nome(empresa)] = papel
    papeis.por = "titulo" if pagina.clientes or pagina.contrapartes else None
    return papeis, lado_de, sem_lugar


def _pela_pagina(
    papeis: _Papeis,
    lado_de: dict[str, str],
    sem_lugar: dict[str, list[Empresa]],
    venda_de_ativo: bool,
) -> None:
    """Quem não apareceu no título: a página diz de que lado está (assessorada ou contraparte)."""
    lado_vendido = "vendedor" if venda_de_ativo else "alvo"
    compra = "comprador" in lado_de.values() or (
        not lado_de and bool(papeis.alvo + papeis.vendedor)
    )  # a assessorada comprou, ou a contraparte já ficou com o lado vendido
    lado_do_cliente = "comprador" if compra else lado_vendido
    lado_da_contraparte = lado_vendido if compra else "comprador"
    for lista, papel in (
        (CLIENTE, lado_do_cliente),
        (CONTRAPARTE, lado_da_contraparte),
    ):
        for empresa in sem_lugar[lista]:
            if getattr(papeis, papel):
                papeis.outras.append(_nome(empresa))
                continue
            getattr(papeis, papel).append(_nome(empresa))
            papeis.por = "pagina"
            if lista == CLIENTE:
                lado_de[_nome(empresa)] = papel


def _papeis(pagina: Pagina, titulo: str, regra: Regra | None) -> _Papeis:
    if regra is None:
        return _Papeis()
    if regra.codigo in CAPTACAO:
        return _Papeis(lado="captacao")
    if regra.codigo in PARTES:
        return _Papeis(lado="parte")
    ativa_ = ATIVA.search(titulo)
    verbo = min(
        (v for v in (ativa_, PASSIVA.search(titulo)) if v),
        key=lambda v: v.start(),
        default=None,
    )
    if verbo is None:
        return _Papeis()
    venda_de_ativo = regra.tipo == "VENDA_ATIVO"
    papeis, lado_de, sem_lugar = _pelo_titulo(
        pagina, titulo, verbo, verbo is ativa_, venda_de_ativo
    )
    _pela_pagina(papeis, lado_de, sem_lugar, venda_de_ativo)
    if {"alvo", "vendedor"} & set(lado_de.values()):
        papeis.lado = "venda"
    elif "comprador" in lado_de.values():
        papeis.lado = "compra"
    return papeis


# --- valor e país ----------------------------------------------------------------------------------
MOEDAS = {"r": "BRL", "us": "USD"}
VALOR_POR_EXTENSO = re.compile(r"\b(r|us) (\d+) (milhoes|milhao|bilhoes|bilhao)\b")
VALOR_EM_ALGARISMOS = re.compile(r"\b(r|us) (\d{1,3}(?: \d{3})+)(?: (\d{2}))?\b")
ESCALAS = {"milhoes": 1e6, "milhao": 1e6, "bilhoes": 1e9, "bilhao": 1e9}


def valor_do_titulo(titulo: str) -> tuple[float | None, str | None]:
    """O valor que o título escreve ("r 70 000 000 00", "r 64 milhoes"), ou (None, None)."""
    if achado := VALOR_POR_EXTENSO.search(titulo):
        return float(achado.group(2)) * ESCALAS[achado.group(3)], MOEDAS[
            achado.group(1)
        ]
    if achado := VALOR_EM_ALGARISMOS.search(titulo):
        inteiro = float(achado.group(2).replace(" ", ""))
        centavos = float(achado.group(3) or 0) / 100
        return inteiro + centavos, MOEDAS[achado.group(1)]
    return None, None


# os países como a IGC escreve (em inglês) → ISO 3166-1; o que não estiver aqui fica como veio
PAISES_ISO = {
    "Argentina": "AR", "Belgium": "BE", "Bermuda": "BM", "Brazil": "BR", "Canada": "CA",
    "Chile": "CL", "China": "CN", "Colombia": "CO", "Denmark": "DK", "Finland": "FI",
    "France": "FR", "Germany": "DE", "India": "IN", "Ireland": "IE", "Israel": "IL",
    "Italy": "IT", "Japan": "JP", "Luxembourg": "LU", "Mexico": "MX", "Netherlands": "NL",
    "Norway": "NO", "Paraguay": "PY", "Peru": "PE", "Portugal": "PT", "Russia": "RU",
    "Singapore": "SG", "South Africa": "ZA", "South Korea": "KR", "Spain": "ES",
    "Sweden": "SE", "Switzerland": "CH", "United Arab Emirates": "AE",
    "United Kingdom": "GB", "United States": "US", "Uruguay": "UY",
}  # fmt: skip


def _juntar(nomes: Iterable[str], separador: str = SEPARADOR) -> str | None:
    unicos = list(dict.fromkeys(nomes))
    return separador.join(unicos)[:LIMITE_DO_TEXTO] if unicos else None


# --- a linha ---------------------------------------------------------------------------------------
def regra_do_titulo(titulo: str) -> Regra | None:
    return next((r for r in REGRAS if re.search(r.palavras, titulo)), None)


def extrair(
    html: bytes, url: str, sha256: str, coletado_em: datetime, assessoria: str
) -> dict[str, object]:
    """Os fatos de uma página de negócio: uma linha com as colunas de `COLUNAS`."""
    pagina = ler_pagina(html)
    titulo = titulo_da_url(url)
    regra = regra_do_titulo(titulo)
    papeis = _papeis(pagina, titulo, regra)
    valor, moeda = valor_do_titulo(titulo)
    return {
        "assessoria": assessoria,
        "url": url,
        "sha256": sha256,
        "coletado_em": coletado_em,
        "tipo": regra.tipo if regra else SEM_TIPO,
        "regra": regra.codigo if regra else None,
        "alvo": _juntar(papeis.alvo),
        "comprador": _juntar(papeis.comprador),
        "vendedor": _juntar(papeis.vendedor),
        "outras_partes": _juntar(papeis.outras),
        "cliente": _juntar(_nome(e) for e in pagina.clientes),
        "contraparte": _juntar(_nome(e) for e in pagina.contrapartes),
        "papeis_por": papeis.por,
        "lado_da_assessoria": papeis.lado,
        "setor": None,  # a página da IGC não diz; vem do CNPJ na ligação com as entidades
        "paises": _juntar((PAISES_ISO.get(p, p) for p in pagina.paises), ";"),
        "valor": valor,
        "moeda": moeda,
        "conferencia": "assessoria",
    }


def tabela(linhas: list[dict[str, object]]) -> pd.DataFrame:
    tabela = pd.DataFrame(linhas, columns=list(COLUNAS))
    tabela["coletado_em"] = pd.to_datetime(tabela["coletado_em"], utc=True)
    tabela["valor"] = tabela["valor"].astype("float64")
    return tabela.sort_values("url", ignore_index=True)
