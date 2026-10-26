"""A vitrine da base: o catálogo de contratos vira o que o site aberto mostra (plano do site para quem
analisa, 18/10/2026, PR 3; ADR 0099, itens 4 e 7).

Tudo aqui é função pura sobre o dicionário de `base/contratos/catalogo.json` (`{"tabelas": {...}}`):
nenhum número da página Dados é digitado à mão, e tabela ou fonte nova aparece sozinha no próximo
build. O que sai para o site aberto passa por três filtros: o órgão sai do texto da licença por uma
tabela fixa (licença nova que não casa **dá erro**, em vez de sumir), a frequência vira um rótulo curto
e a frase da tabela e o atraso perdem o que é conversa interna (código, ADR, servidor).
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

import pandas as pd

from base.cnpj import normalizar_cnpj
from base.dossie import CONTAS_DA_DRE, exigir_que_pode_mostrar
from base.regras import LINHA_DO_LUCRO, RECEITA, TOLERANCIA_EM_REAIS

# o texto da licença → o órgão que o site mostra; uma linha por fonte do catálogo (são 16 em 19/10/2026)
ORGAOS: tuple[tuple[str, str], ...] = (
    (r"da CVM", "CVM"),
    (r"do Banco Central", "Banco Central"),
    (r"assessorias de M&A", "Assessorias de M&A"),
    (r"da ANP\b", "ANP"),
    (r"da ANAC\b", "ANAC"),
    (r"da ANTT\b", "ANTT"),
    (r"da CCEE\b", "CCEE"),
    (r"do ONS\b", "ONS"),
    (r"da ANEEL\b", "ANEEL"),
    (r"da Anatel\b", "Anatel"),
    (r"da ANS\b", "ANS"),
    (r"da SUSEP\b", "SUSEP"),
    (r"Receita", "Receita Federal"),
    (r"da PGFN\b", "PGFN"),
    (r"Tesouro", "Tesouro Nacional"),
    (r"Internet Archive", "Internet Archive"),
    (r"a CFTC\b", "CFTC"),
    (r"\(CONAB\)", "CONAB"),
    (r"do USDA\b", "USDA"),
    (r"\(FAO;", "FAO"),
    (r"\bMDIC\b", "MDIC"),
    (r"do INMET\b", "INMET"),
    (r"\bMapBiomas\b", "MapBiomas"),
    (r"guardadas? só como prova", "Imprensa e páginas públicas"),
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


# --- a base em números (plano do site para quem analisa, PR 4) ------------------------------------
# a fotografia é medida no servidor de casa (`scripts/medir_base_para_o_site.py`, só leitura pela porta)
FOTOGRAFIA = (
    Path(__file__).resolve().parent.parent
    / "dados_de_exemplo"
    / "base"
    / "numeros.json"
)
DEMONSTRACOES = "demonstracoes_como_era"
EVENTOS = "eventos"
# só estas tabelas entram na faixa de números; cada uma tem de estar no catálogo e poder ser mostrada
TABELAS_DOS_NUMEROS = (DEMONSTRACOES, EVENTOS)


class PortaQueConta(Protocol):
    """O que `numeros_da_base` pede da porta (`base.porta.Porta` e as portas falsas dos testes)."""

    def distintos(self, tabela: str, coluna: str) -> set[object]: ...

    def contar(self, tabela: str, ao_menos: dict[str, float] | None = None) -> int: ...


@dataclass(frozen=True)
class NumerosDaBase:
    """Os números da faixa da página Dados, todos medidos na base em `medido_em` (AAAA-MM-DD)."""

    empresas: int  # companhias com demonstrações
    linhas_de_demonstracoes: int
    versoes: int  # linhas de demonstrações reapresentadas (a versão 2 em diante): a primeira não se apaga
    eventos: int  # documentos de eventos (fatos relevantes, comunicados...)
    originais_com_hash: (
        int  # arquivos originais dos eventos, cada um com o SHA-256 guardado
    )
    medido_em: str


def numeros_da_base(porta: PortaQueConta, catalogo: dict, hoje: date) -> NumerosDaBase:
    """Mede a base pela porta. Tabela fora do catálogo ou que a licença não deixa mostrar dá erro: o
    número público nunca sai de uma tabela interna."""
    ausentes = [t for t in TABELAS_DOS_NUMEROS if t not in catalogo["tabelas"]]
    if ausentes:
        raise ValueError(
            f"fora do catálogo, não vira número público: {', '.join(ausentes)}"
        )
    exigir_que_pode_mostrar(TABELAS_DOS_NUMEROS)
    return NumerosDaBase(
        empresas=len(porta.distintos(DEMONSTRACOES, "cnpj")),
        linhas_de_demonstracoes=porta.contar(DEMONSTRACOES),
        versoes=porta.contar(DEMONSTRACOES, ao_menos={"versao": 2}),
        eventos=porta.contar(EVENTOS),
        originais_com_hash=len(porta.distintos(EVENTOS, "origem_sha256")),
        medido_em=hoje.isoformat(),
    )


def numeros_da_fotografia(dados: dict) -> NumerosDaBase:
    """A fotografia gravada de volta em números; campo a mais ou a menos é erro, não número escondido."""
    return NumerosDaBase(**dados)


def dia_e_mes(iso: str) -> str:
    """'2026-10-26' → '26/10' (o "medido em" da página)."""
    _, mes, dia = iso.split("-")
    return f"{dia}/{mes}"


def base_em_numeros(fotografia: Path = FOTOGRAFIA) -> dict:
    """O `web/conteudo/base.json`: a fotografia como está e a data curta que a página mostra."""
    numeros = numeros_da_fotografia(json.loads(fotografia.read_text(encoding="utf-8")))
    return {"numeros": asdict(numeros), "medido_em_curto": dia_e_mes(numeros.medido_em)}


# --- vagas da vitrine da página inicial (plano do site para quem analisa, PR 5, tarefa 8) --------

PRONTA = "pronta"
EM_BREVE = "em_breve"


@dataclass(frozen=True)
class Vaga:
    """Um lugar da vitrine da página inicial: pronta (com link para a página que existe) ou em breve.

    Em breve não tem link nem data: a vaga só acende no PR que entrega a página, para o site nunca
    prometer prazo nem apontar para o vazio.
    """

    chave: str
    titulo: str
    para_que_serve: str
    estado: str
    link: str | None = None

    def __post_init__(self) -> None:
        if self.estado == PRONTA and not self.link:
            raise ValueError(f"vaga pronta sem link: {self.chave}")
        if self.estado == EM_BREVE and self.link is not None:
            raise ValueError(f"vaga em breve com link: {self.chave}")
        if self.estado not in (PRONTA, EM_BREVE):
            raise ValueError(f"estado desconhecido na vaga {self.chave}: {self.estado}")


VAGAS_DA_VITRINE: tuple[Vaga, ...] = (
    Vaga(
        "setor",
        "Relatório do setor",
        "As elétricas: quem atende os consumidores do país e quem audita as companhias abertas, "
        "com a fonte e a data de cada número.",
        PRONTA,
        "/relatorio-de-setor-eletricas.html",
    ),
    Vaga(
        "ficha",
        "Ficha da empresa",
        "A CPFL Energia lida na base: ofertas, rodízio do auditor, setor regulado e negócios, "
        "cruzando a CVM e as agências.",
        PRONTA,
        "/relatorio-de-exemplo.html",
    ),
    Vaga(
        "cnpj",
        "Busca por CNPJ",
        "Um CNPJ vira o grupo inteiro, a partir do quadro de sócios da Receita Federal, "
        "com as bases públicas conferidas.",
        EM_BREVE,
    ),
    Vaga(
        "ma",
        "Precedentes de M&A",
        "Compras e vendas de empresas no Brasil, com o valor pago e o documento público de onde ele saiu.",
        EM_BREVE,
    ),
    Vaga(
        "cruzamentos",
        "Cruzamentos da base",
        "O que só aparece juntando fontes: um balanço refeito depois da troca de auditor, por exemplo.",
        PRONTA,
        "/#cruzamentos",
    ),
)


# --- cruzamentos da base na página inicial (plano do site para quem analisa, PR 6, tarefa 10) -----
# Fatos que só aparecem juntando duas tabelas ou mais. São moldes fixos e **só contagens**: nenhum nome
# de companhia, auditor ou pessoa sai daqui (um fato com nome pode expor alguém a dano; a passagem do
# PR 6 pede a contagem na dúvida). A medição é no servidor de casa (`scripts/medir_base_para_o_site.py`),
# só leitura pela porta; a fotografia guarda os números, e as frases saem dela aqui, num lugar só.
FOTOGRAFIA_DOS_CRUZAMENTOS = FOTOGRAFIA.with_name("fatos.json")
TROCAS_DE_AUDITOR = "trocas_de_auditor"
OFERTAS = "ofertas_resolucao_160"
CONTROLADAS = "controladas"
TABELAS_DOS_CRUZAMENTOS = (DEMONSTRACOES, TROCAS_DE_AUDITOR, OFERTAS, CONTROLADAS)
LIMITE_DO_FATO = 240  # o cartão da página inicial: duas ou três linhas
# o lucro mudou quando a diferença passa de 1% do valor publicado e do arredondamento da CVM (R$ 1 mil)
MUDANCA_QUE_CONTA = 0.01
# um balanço anual e o do ano seguinte: de 10 a 14 meses entre os dois fins (o exercício que mudou de
# data ainda conta; um ano sem balanço no meio, não)
DIAS_ENTRE_BALANCOS = (300, 430)
# a oferta que saiu: as caducadas, revogadas e suspensas não captaram
OFERTAS_QUE_SAIRAM = ("Oferta Encerrada", "Registro Concedido")
# só os títulos que a própria empresa emite para captar: cotas de fundo não são de empresa, e o CRI, o CRA
# e afins saem pela securitizadora com o dinheiro de outra (o devedor, que a tabela não traz). Lista
# fechada: um tipo novo da CVM fica de fora até alguém o pôr aqui (medido em 26/10: são 1/4 das ofertas)
TITULOS_DE_EMPRESA = (
    "Ações",
    "Debêntures",
    "Notas Comerciais",
    "Notas Promissórias",
    "Cédula de Produto Rural Financeira",
)
CONTROLADA = "controlada"
BILHAO = 1e9
COLUNAS_DO_LUCRO = (
    "cnpj",
    "grupo",
    "conta",
    "descricao",
    "fim",
    "referencia",
    "valor",
    "versao",
    "ordem",
    "divulgado_em",
    "publico_em",
)
COLUNAS_DAS_OFERTAS = (
    "cnpj_emissor",
    "data_registro",
    "status_requerimento",
    "valor_mobiliario",
    "valor_total_registrado",
)


class PortaQueLe(Protocol):
    """O que `medir_cruzamentos` pede da porta (`base.porta.Porta` e as portas falsas dos testes)."""

    def ler(
        self,
        tabela: str,
        versao: str | None = None,
        como_era_em: object = None,
        filtros: Mapping[str, object] | None = None,
        colunas: Sequence[str] | None = None,
    ) -> pd.DataFrame: ...

    def distintos(self, tabela: str, coluna: str) -> set[object]: ...


@dataclass(frozen=True)
class LucrosRefeitos:
    """Balanços anuais cujo lucro do ano mudou no balanço do ano seguinte (a coluna do ano anterior)."""

    balancos: int  # balanços anuais que já têm o do ano seguinte
    refeitos: int
    companhias_refeitas: int
    companhias: int
    primeiro_exercicio: int
    ultimo_exercicio: int


@dataclass(frozen=True)
class TrocasDeAuditor:
    """Trocas de auditor e o primeiro balanço depois delas, com a taxa dos balanços sem troca ao lado."""

    trocas: int
    trocas_com_balanco: (
        int  # o primeiro balanço depois da troca e o do ano anterior estão na base
    )
    trocas_refeitas: int
    balancos_sem_troca: int
    refeitos_sem_troca: int


@dataclass(frozen=True)
class OfertasDoGrupo:
    """Ofertas da Resolução CVM 160 de um ano e as que saíram de um grupo de companhia aberta."""

    ano: int
    ofertas: int
    valor: float  # R$
    do_grupo: int  # a própria companhia aberta ou uma controlada que ela declara no FRE
    valor_do_grupo: float
    grupos: int
    por_controlada: int
    valor_por_controlada: float


@dataclass(frozen=True)
class Cruzamentos:
    """Os números dos fatos da página inicial, medidos com o que era público em `medido_em`."""

    lucros: LucrosRefeitos
    auditor: TrocasDeAuditor
    ofertas: OfertasDoGrupo
    medido_em: str


@dataclass(frozen=True)
class Fato:
    """Um cartão dos cruzamentos: o número em destaque, a frase, a fonte e como foi calculado."""

    chave: str
    numero: str
    texto: str
    fonte: str
    tabelas: tuple[str, ...]
    data: str  # AAAA-MM-DD: o dia da medição (só entra o que já era público nele)
    como_foi_calculado: str


def _cnpjs(valores: pd.Series) -> pd.Series:
    return valores.map(normalizar_cnpj)


def _centavos(reais: float) -> float:
    """A soma em reais com duas casas: o resto do ponto flutuante não vai para a fotografia."""
    return round(float(reais), 2)


def _so_o_publico(linhas: pd.DataFrame, ate: date) -> pd.DataFrame:
    return linhas[pd.to_datetime(linhas["publico_em"]) <= pd.Timestamp(ate)]


def linhas_do_lucro(porta: PortaQueLe, ate: date) -> pd.DataFrame:
    """O lucro do período de cada DFP já pública em `ate`, com todas as versões e a coluna do ano
    anterior, no consolidado (ou no individual, na companhia que não publica consolidado)."""
    linhas = porta.ler(
        DEMONSTRACOES,
        filtros={
            "demonstracao": "DRE",
            "documento": "DFP",
            "conta": [c for c in CONTAS_DA_DRE if c != RECEITA],
        },
        colunas=list(COLUNAS_DO_LUCRO),
    )
    linhas = _so_o_publico(linhas, ate)
    descricao = linhas["descricao"].fillna("").astype(str).str.strip()
    linhas = linhas[descricao.str.match(LINHA_DO_LUCRO)].copy()
    consolidado = linhas["grupo"] == "con"
    tem_consolidado = consolidado.groupby(linhas["cnpj"]).transform("any")
    linhas = linhas[consolidado | ~tem_consolidado].copy()
    for coluna in ("fim", "referencia", "divulgado_em"):
        linhas[coluna] = pd.to_datetime(linhas[coluna])
    # mais de uma conta com a descrição do lucro no mesmo documento: fica a de menor número
    return linhas.sort_values(["cnpj", "fim", "referencia", "versao", "conta"])


def balancos_anuais(lucros: pd.DataFrame) -> pd.DataFrame:
    """Um balanço anual por linha (`cnpj`, `fim`): o lucro na primeira versão que a base guarda, o dia em
    que ela saiu e, quando a base tem o balanço do ano seguinte, o mesmo lucro como o seguinte o mostra
    e se ele mudou (`mudou`; vazio sem o seguinte). A base só guarda a linha "penúltimo" quando o valor
    mudou: sem ela, o seguinte mostra o número da última versão do próprio balanço."""
    proprios = lucros[
        (lucros["ordem"] == "ultimo") & (lucros["fim"] == lucros["referencia"])
    ]
    versoes = proprios.groupby(["cnpj", "fim"])
    balancos = pd.DataFrame(
        {
            "original": versoes["valor"].first(),
            "ultimo": versoes["valor"].last(),
            "saiu_em": versoes["divulgado_em"].first(),
        }
    ).reset_index()
    seguinte = balancos.groupby("cnpj")["fim"].shift(-1)
    dias = (seguinte - balancos["fim"]).dt.days
    minimo, maximo = DIAS_ENTRE_BALANCOS
    balancos["fim_seguinte"] = seguinte.where(dias.between(minimo, maximo))
    anteriores = lucros[lucros["ordem"] == "penultimo"]
    refeito = (
        anteriores.groupby(["cnpj", "fim", "referencia"])["valor"]
        .last()
        .rename("refeito")
        .reset_index()
        .rename(columns={"referencia": "fim_seguinte"})
    )
    balancos = balancos.merge(refeito, on=["cnpj", "fim", "fim_seguinte"], how="left")
    mostrado = balancos["refeito"].fillna(balancos["ultimo"])
    diferenca = (mostrado - balancos["original"]).abs()
    limite = (MUDANCA_QUE_CONTA * balancos["original"].abs()).clip(
        lower=TOLERANCIA_EM_REAIS
    )
    balancos["mudou"] = (diferenca > limite).where(balancos["fim_seguinte"].notna())
    return balancos[["cnpj", "fim", "saiu_em", "fim_seguinte", "mudou"]]


def _com_seguinte(balancos: pd.DataFrame) -> pd.DataFrame:
    return balancos[balancos["fim_seguinte"].notna()]


def lucros_refeitos(balancos: pd.DataFrame) -> LucrosRefeitos:
    seguidos = _com_seguinte(balancos)
    mudaram = seguidos[seguidos["mudou"].astype(bool)]
    return LucrosRefeitos(
        balancos=len(seguidos),
        refeitos=len(mudaram),
        companhias_refeitas=mudaram["cnpj"].nunique(),
        companhias=seguidos["cnpj"].nunique(),
        primeiro_exercicio=int(seguidos["fim"].min().year),
        ultimo_exercicio=int(seguidos["fim"].max().year),
    )


def _olhado_pela_troca(balancos: pd.DataFrame, publico_em: pd.Timestamp) -> int | None:
    """O balanço que a troca olha (o do ano anterior ao primeiro balanço depois dela), se a base o tem."""
    depois = balancos[balancos["saiu_em"] > publico_em]
    if depois.empty:
        return None
    primeiro_depois = depois.loc[depois["saiu_em"].idxmin(), "fim"]
    anterior = balancos[balancos["fim_seguinte"] == primeiro_depois]
    return int(anterior.index[0]) if not anterior.empty else None


def trocas_de_auditor(trocas: pd.DataFrame, balancos: pd.DataFrame) -> TrocasDeAuditor:
    """Cada troca olha o primeiro balanço anual que saiu depois dela (o do auditor novo) e se ele refez
    o lucro do ano anterior. Os balanços com seguinte que nenhuma troca olhou dão a taxa de comparação."""
    balancos = balancos.assign(cnpj=_cnpjs(balancos["cnpj"]))
    por_cnpj = dict(tuple(balancos.groupby("cnpj")))
    olhados = []
    for cnpj, publico_em in zip(
        _cnpjs(trocas["cnpj"]), pd.to_datetime(trocas["publico_em"]), strict=True
    ):
        da_companhia = por_cnpj.get(cnpj)
        olhado = (
            None
            if da_companhia is None
            else _olhado_pela_troca(da_companhia, publico_em)
        )
        if olhado is not None:
            olhados.append(olhado)
    com_troca = balancos.loc[olhados]
    sem_troca = _com_seguinte(balancos.drop(index=list(set(olhados))))
    return TrocasDeAuditor(
        trocas=len(trocas),
        trocas_com_balanco=len(com_troca),
        trocas_refeitas=int(com_troca["mudou"].astype(bool).sum()),
        balancos_sem_troca=len(sem_troca),
        refeitos_sem_troca=int(sem_troca["mudou"].astype(bool).sum()),
    )


def ofertas_do_grupo(
    ofertas: pd.DataFrame,
    controladas: pd.DataFrame,
    companhias_abertas: set[str],
    ano: int,
) -> OfertasDoGrupo:
    """As ofertas de títulos de empresa registradas no ano que saíram e as que vieram de um grupo: a
    companhia aberta ou uma controlada que ela declara no FRE (coligada e ligação sem o tipo ficam de
    fora)."""
    registro = pd.to_datetime(ofertas["data_registro"])
    do_ano = ofertas[
        (registro.dt.year == ano)
        & ofertas["status_requerimento"].isin(OFERTAS_QUE_SAIRAM)
        & ofertas["valor_mobiliario"].isin(TITULOS_DE_EMPRESA)
    ]
    emissor = _cnpjs(do_ano["cnpj_emissor"])
    so_controladas = controladas[controladas["tipo"] == CONTROLADA]
    # a controlada de mais de uma companhia (controle indireto) fica no grupo de menor CNPJ
    controladora = (
        pd.DataFrame(
            {
                "cnpj": _cnpjs(so_controladas["cnpj"]),
                "companhia": _cnpjs(so_controladas["cnpj_companhia"]),
            }
        )
        .groupby("cnpj")["companhia"]
        .min()
    )
    aberta = emissor.isin(companhias_abertas)
    por_controlada = ~aberta & emissor.isin(controladora.index)
    grupo = emissor.where(aberta, emissor.map(controladora))
    valor = do_ano["valor_total_registrado"].astype(float)
    do_grupo = aberta | por_controlada
    return OfertasDoGrupo(
        ano=ano,
        ofertas=len(do_ano),
        valor=_centavos(valor.sum()),
        do_grupo=int(do_grupo.sum()),
        valor_do_grupo=_centavos(valor[do_grupo].sum()),
        grupos=grupo[do_grupo].nunique(),
        por_controlada=int(por_controlada.sum()),
        valor_por_controlada=_centavos(valor[por_controlada].sum()),
    )


def medir_cruzamentos(porta: PortaQueLe, catalogo: dict, ate: date) -> Cruzamentos:
    """Mede os cruzamentos pela porta, só com o que era público em `ate`. Tabela fora do catálogo ou que
    a licença não deixa mostrar dá erro, como nos números da página Dados."""
    ausentes = [t for t in TABELAS_DOS_CRUZAMENTOS if t not in catalogo["tabelas"]]
    if ausentes:
        raise ValueError(
            f"fora do catálogo, não vira fato público: {', '.join(ausentes)}"
        )
    exigir_que_pode_mostrar(TABELAS_DOS_CRUZAMENTOS)
    balancos = balancos_anuais(linhas_do_lucro(porta, ate))
    trocas = porta.ler(
        TROCAS_DE_AUDITOR, como_era_em=ate, colunas=["cnpj", "publico_em"]
    )
    ano = ate.year - 1  # o último ano completo
    fim_do_ano = date(ano, 12, 31)
    ofertas = porta.ler(OFERTAS, como_era_em=ate, colunas=list(COLUNAS_DAS_OFERTAS))
    controladas = porta.ler(
        CONTROLADAS, como_era_em=fim_do_ano, colunas=["cnpj_companhia", "cnpj", "tipo"]
    )
    abertas = {
        c for c in map(normalizar_cnpj, porta.distintos(DEMONSTRACOES, "cnpj")) if c
    }
    return Cruzamentos(
        lucros=lucros_refeitos(balancos),
        auditor=trocas_de_auditor(trocas, balancos),
        ofertas=ofertas_do_grupo(ofertas, controladas, abertas, ano),
        medido_em=ate.isoformat(),
    )


def cruzamentos_da_fotografia(dados: dict) -> Cruzamentos:
    """A fotografia gravada de volta nos números; campo a mais ou a menos é erro."""
    return Cruzamentos(
        lucros=LucrosRefeitos(**dados["lucros"]),
        auditor=TrocasDeAuditor(**dados["auditor"]),
        ofertas=OfertasDoGrupo(**dados["ofertas"]),
        medido_em=dados["medido_em"],
    )


def _milhar(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def _porcento(parte: int, todo: int) -> str:
    return f"{100 * parte / todo:.1f}%".replace(".", ",")


def _bilhoes(reais: float) -> str:
    return (
        f"R$ {reais / BILHAO:,.1f} bilhões".replace(",", "_")
        .replace(".", ",")
        .replace("_", ".")
    )


def _fato_dos_lucros(lucros: LucrosRefeitos, data: str) -> Fato:
    return Fato(
        chave="lucros",
        numero=_porcento(lucros.refeitos, lucros.balancos),
        texto=(
            f"dos {_milhar(lucros.balancos)} balanços anuais de {lucros.primeiro_exercicio} a "
            f"{lucros.ultimo_exercicio} tiveram o lucro do ano mudado em mais de 1% até o balanço do "
            f"ano seguinte: {_milhar(lucros.refeitos)} balanços, de {_milhar(lucros.companhias_refeitas)} "
            f"de {_milhar(lucros.companhias)} companhias."
        ),
        fonte="CVM: demonstrações financeiras padronizadas (DFP)",
        tabelas=(DEMONSTRACOES,),
        data=data,
        como_foi_calculado=(
            "O lucro do período de cada balanço anual, na primeira versão que a base guarda, comparado "
            "com o número que o balanço do ano seguinte mostra para o mesmo ano (a coluna do ano "
            "anterior). A mudança pode vir de uma nova versão do próprio balanço ou do seguinte. Conta "
            "como mudado quando a diferença passa de 1% e de R$ 1 mil. Usa o consolidado e, na companhia que não o publica, "
            "o individual. Só entram os balanços que já têm o do ano seguinte. Mudar não quer dizer erro: "
            "entram reclassificação, norma contábil nova e operação descontinuada."
        ),
    )


def _fato_do_auditor(auditor: TrocasDeAuditor, data: str) -> Fato:
    sem_balanco = auditor.trocas - auditor.trocas_com_balanco
    return Fato(
        chave="auditor",
        numero=_porcento(auditor.trocas_refeitas, auditor.trocas_com_balanco),
        texto=(
            f"das {_milhar(auditor.trocas_com_balanco)} trocas de auditor vieram com o lucro do ano "
            f"anterior mudado em mais de 1% no primeiro balanço depois da troca "
            f"({_milhar(auditor.trocas_refeitas)} trocas). Nos balanços sem troca, foram "
            f"{_porcento(auditor.refeitos_sem_troca, auditor.balancos_sem_troca)}."
        ),
        fonte="CVM: formulário cadastral (FCA) e demonstrações financeiras (DFP)",
        tabelas=(TROCAS_DE_AUDITOR, DEMONSTRACOES),
        data=data,
        como_foi_calculado=(
            "Cada troca de firma de auditoria olha o primeiro balanço anual publicado depois dela e "
            "compara o lucro do ano anterior com a mesma regra do número dos balanços refeitos. "
            f"{_milhar(sem_balanco)} das {_milhar(auditor.trocas)} trocas ficam de fora: ainda não têm "
            "esse balanço, ou a base não tem o do ano anterior. A comparação com os balanços sem troca "
            "mostra uma frequência, não uma causa."
        ),
    )


def _fato_das_ofertas(ofertas: OfertasDoGrupo, data: str) -> Fato:
    return Fato(
        chave="ofertas",
        numero=_milhar(ofertas.do_grupo),
        texto=(
            f"das {_milhar(ofertas.ofertas)} ofertas de ações, debêntures e notas registradas na CVM em {ofertas.ano} "
            f"vieram de "
            f"{_milhar(ofertas.grupos)} grupos de companhias abertas, com {_bilhoes(ofertas.valor_do_grupo)}. "
            f"Em {_milhar(ofertas.por_controlada)} delas, quem emitiu foi uma controlada, não a companhia."
        ),
        fonte="CVM: ofertas da Resolução 160, formulário de referência (FRE) e DFP",
        tabelas=(OFERTAS, CONTROLADAS, DEMONSTRACOES),
        data=data,
        como_foi_calculado=(
            f"As ofertas da Resolução CVM 160 com registro em {ofertas.ano}, encerradas ou com registro "
            "concedido (as caducadas, revogadas e suspensas ficam de fora), de ações, debêntures, notas "
            "comerciais e promissórias e CPR financeira. Cotas de fundo e títulos de securitização (CRI, "
            "CRA) ficam de fora: não são captação da empresa que aparece como emissora. O grupo é a companhia "
            "aberta "
            "com as controladas que ela declara no formulário de referência, como ele era em "
            f"31/12/{ofertas.ano}; coligadas e ligações sem o tipo não entram. O valor é o registrado "
            f"na oferta; as {_milhar(ofertas.ofertas)} ofertas desses títulos somam {_bilhoes(ofertas.valor)}."
        ),
    )


def fatos_agregados(cruzamentos: Cruzamentos) -> list[Fato]:
    """Os cartões dos cruzamentos, na ordem da página inicial."""
    data = cruzamentos.medido_em
    return [
        _fato_dos_lucros(cruzamentos.lucros, data),
        _fato_do_auditor(cruzamentos.auditor, data),
        _fato_das_ofertas(cruzamentos.ofertas, data),
    ]


def fatos_da_base(fotografia: Path = FOTOGRAFIA_DOS_CRUZAMENTOS) -> dict:
    """O `web/conteudo/fatos_da_base.json`: os cartões da fotografia e a data curta que a página mostra."""
    cruzamentos = cruzamentos_da_fotografia(
        json.loads(fotografia.read_text(encoding="utf-8"))
    )
    return {
        "fatos": [asdict(f) for f in fatos_agregados(cruzamentos)],
        "medido_em_curto": dia_e_mes(cruzamentos.medido_em),
    }
