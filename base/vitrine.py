"""A vitrine da base: o catálogo de contratos vira o que o site aberto mostra (plano do site para quem
analisa, 18/10/2026, PR 3; ADR 0099, itens 4 e 7).

Tudo aqui é função pura sobre o dicionário de `base/contratos/catalogo.json` (`{"tabelas": {...}}`):
nenhum número da página Dados é digitado à mão, e tabela ou fonte nova aparece sozinha no próximo
build. O que sai para o site aberto passa por três filtros: o órgão sai do texto da licença por uma
tabela fixa (licença nova que não casa **dá erro**, em vez de sumir), a frequência vira um rótulo curto
e a frase da tabela e o atraso perdem o que é conversa interna (código, ADR, servidor).
"""

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.destaques import Destaque
    from src.dossie import Ficha

import pandas as pd

from base.cnpj import normalizar_cnpj
from base.dossie import (
    CONTAS_DA_DRE,
    TABELAS_SO_EM_CONTAGEM,
    exigir_que_pode_contar,
    exigir_que_pode_mostrar,
)
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
    (r"da Anvisa\b", "Anvisa"),
    (r"do MAPA\b", "MAPA"),
    (r"da ANM\b", "ANM"),
    (r"da Ancine\b", "Ancine"),
    (r"do MME\b", "MME"),
    (r"da SUSEP\b", "SUSEP"),
    (r"Receita", "Receita Federal"),
    (r"da PGFN\b", "PGFN"),
    (r"da CGU\b", "CGU"),
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
    """ "Licenciada" só quando a licença está escrita e a revenda confirmada; senão "em consulta".

    "Só uso interno" também fica em consulta: a página não diz "pode ser repassado" do que a marca
    manda nunca vender nem exportar (as sanções da CGU)."""
    sem_resposta = revenda.startswith(
        ("a confirmar", "não comercial", "só uso interno")
    )
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
        "Busque uma companhia aberta por CNPJ, nome ou ticker: até três destaques, com a fonte e a data.",
        PRONTA,
        "/#busca-base",
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
# Em 29/10/2026 o Tiago trocou o cartão das ofertas por quatro cruzamentos que dizem mais ("Pode: site
# com S1 a S4 (tira o cartão das ofertas)"; plano "mais cruzamentos da base", na pasta privada).
FOTOGRAFIA_DOS_CRUZAMENTOS = FOTOGRAFIA.with_name("fatos.json")
TROCAS_DE_AUDITOR = "trocas_de_auditor"
ROTULOS_DE_ATRASO = "rotulos_atraso"
REMUNERACAO = "fre_remuneracao"
PROVENTOS = "proventos"
PARECERES = "pareceres_dfp"
INSOLVENCIA = "insolvencia"
# o atraso só entra como contagem (`TABELAS_SO_EM_CONTAGEM`, em `base/dossie.py`)
TABELAS_DOS_CRUZAMENTOS = (
    DEMONSTRACOES,
    TROCAS_DE_AUDITOR,
    ROTULOS_DE_ATRASO,
    REMUNERACAO,
    PROVENTOS,
    PARECERES,
    INSOLVENCIA,
)
LIMITE_DO_FATO = 240  # o cartão da página inicial: duas ou três linhas
# o lucro mudou quando a diferença passa de 1% do valor publicado e do arredondamento da CVM (R$ 1 mil)
MUDANCA_QUE_CONTA = 0.01
# um balanço anual e o do ano seguinte: de 10 a 14 meses entre os dois fins (o exercício que mudou de
# data ainda conta; um ano sem balanço no meio, não)
DIAS_ENTRE_BALANCOS = (300, 430)
DFP = "DFP"
DIRETORIA = "Diretoria Estatutária"
# o lucro "caiu" ou "cresceu" quando mudou mais que isso em relação ao ano anterior (ou virou prejuízo)
VARIACAO_DO_LUCRO = 0.2
# a tabela de proventos do FRE não traz a data em que cada versão ficou pública: vale o prazo de
# entrega do formulário (cinco meses depois do fim do exercício a que ele se refere)
MESES_DO_PRAZO_DO_FRE = 5
# a janela depois do parecer em que se olha a insolvência; o parecer mais novo que isso ainda não fechou a janela
MESES_DEPOIS_DO_PARECER = 24
SIM, NAO = (
    "sim",
    "nao",
)  # os valores do rótulo `continuidade_operacional` (fora o `nao_classificado`)
# o pedido ou decreto da própria companhia: a exposição a terceiro e o pedido de falência feito por um
# credor não dizem que ela ficou insolvente
ROTULOS_DE_INSOLVENCIA = (
    "recuperacao_judicial",
    "recuperacao_extrajudicial",
    "recuperacao_judicial_ou_extrajudicial",
    "falencia",
    "liquidacao",
)
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
COLUNAS_DO_ATRASO = ("cnpj", "documento", "referencia", "atrasou", "atraso_grave")
COLUNAS_DA_REMUNERACAO = (
    "cnpj",
    "referencia",
    "versao",
    "inicio_do_exercicio",
    "fim_do_exercicio",
    "orgao",
    "total_do_orgao",
    "publico_em",
)
COLUNAS_DOS_PROVENTOS = ("cnpj", "referencia", "versao", "exercicio", "dividendo_total")
COLUNAS_DOS_PARECERES = (
    "cnpj",
    "referencia",
    "versao",
    "continuidade_operacional",
    "publico_em",
)
COLUNAS_DA_INSOLVENCIA = ("cnpj", "rotulo", "publico_em")


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
class AtrasoERefeito:
    """Balanços anuais entregues depois do prazo da CVM e quantos tiveram o lucro refeito no balanço
    seguinte, com a taxa dos entregues no prazo ao lado."""

    atrasados: int
    atrasados_refeitos: int
    graves: int  # mais de 30 dias corridos de atraso
    graves_refeitos: int
    no_prazo: int
    no_prazo_refeitos: int


@dataclass(frozen=True)
class RemuneracaoELucro:
    """Pares de exercícios seguidos com o lucro do ano e a remuneração da diretoria estatutária nos dois."""

    pares: int
    remuneracao_subiu: int
    lucro_caiu: int  # mais de 20%, ou virou prejuízo
    lucro_caiu_e_remuneracao_subiu: int
    lucro_subiu: int  # mais de 20%
    lucro_subiu_e_remuneracao_subiu: int
    companhias: int
    primeiro_exercicio: int
    ultimo_exercicio: int


@dataclass(frozen=True)
class DividendoELucro:
    """Exercícios com dividendo declarado no FRE ao lado do lucro do ano na DFP."""

    exercicios: int
    companhias: int
    acima_do_lucro: (
        int  # o dividendo passou do lucro do ano (os de ano com prejuízo estão aqui)
    )
    companhias_acima: int
    com_prejuizo: int
    primeiro_exercicio: int
    ultimo_exercicio: int


@dataclass(frozen=True)
class ParecerEInsolvencia:
    """Pareceres de auditoria da DFP com e sem incerteza sobre a continuidade, e quantos foram seguidos
    de recuperação, falência ou liquidação nos 24 meses depois."""

    com_duvida: int
    com_duvida_e_insolvencia: int
    sem_duvida: int
    sem_duvida_e_insolvencia: int
    companhias_com_duvida: int
    primeiro_exercicio: int
    ultimo_exercicio: int


@dataclass(frozen=True)
class Cruzamentos:
    """Os números dos fatos da página inicial, medidos com o que era público em `medido_em`."""

    lucros: LucrosRefeitos
    auditor: TrocasDeAuditor
    atraso: AtrasoERefeito
    remuneracao: RemuneracaoELucro
    dividendo: DividendoELucro
    parecer: ParecerEInsolvencia
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


def _so_o_publico(linhas: pd.DataFrame, ate: date) -> pd.DataFrame:
    return linhas[pd.to_datetime(linhas["publico_em"]) <= pd.Timestamp(ate)]


def linhas_do_lucro(porta: PortaQueLe, ate: date) -> pd.DataFrame:
    """O lucro do período de cada DFP já pública em `ate`, com todas as versões e a coluna do ano
    anterior, no consolidado (ou no individual, na companhia que não publica consolidado)."""
    linhas = porta.ler(
        DEMONSTRACOES,
        filtros={
            "demonstracao": "DRE",
            "documento": DFP,
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


def _proprios(lucros: pd.DataFrame) -> pd.DataFrame:
    """As linhas em que o balanço fala do próprio exercício (não a coluna do ano anterior)."""
    return lucros[
        (lucros["ordem"] == "ultimo") & (lucros["fim"] == lucros["referencia"])
    ]


def balancos_anuais(lucros: pd.DataFrame) -> pd.DataFrame:
    """Um balanço anual por linha (`cnpj`, `fim`): o lucro na primeira versão que a base guarda, o dia em
    que ela saiu e, quando a base tem o balanço do ano seguinte, o mesmo lucro como o seguinte o mostra
    e se ele mudou (`mudou`; vazio sem o seguinte). A base só guarda a linha "penúltimo" quando o valor
    mudou: sem ela, o seguinte mostra o número da última versão do próprio balanço."""
    versoes = _proprios(lucros).groupby(["cnpj", "fim"])
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


def lucro_por_exercicio(lucros: pd.DataFrame) -> pd.DataFrame:
    """O lucro do ano de cada balanço anual (`cnpj` normalizado, `fim`, `lucro`), como a última versão
    já pública o mostra: é o número com que o dividendo e a remuneração se comparam."""
    ultimo = _proprios(lucros).groupby(["cnpj", "fim"])["valor"].last().rename("lucro")
    por_exercicio = ultimo.reset_index()
    return por_exercicio.assign(cnpj=_cnpjs(por_exercicio["cnpj"]))


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


def atraso_e_refeito(rotulos: pd.DataFrame, balancos: pd.DataFrame) -> AtrasoERefeito:
    """Cada balanço anual que já tem o seguinte, com o rótulo de atraso da DFP do mesmo exercício: os
    entregues depois do prazo refizeram o lucro mais vezes que os entregues no prazo?"""
    dfp = rotulos[rotulos["documento"] == DFP]
    rotulo = pd.DataFrame(
        {
            "cnpj": _cnpjs(dfp["cnpj"]),
            "fim": pd.to_datetime(dfp["referencia"]),
            "atrasou": dfp["atrasou"].astype(bool),
            "atraso_grave": dfp["atraso_grave"].astype(bool),
        }
    )
    seguidos = _com_seguinte(balancos)
    juntos = seguidos.assign(cnpj=_cnpjs(seguidos["cnpj"])).merge(
        rotulo, on=["cnpj", "fim"]
    )
    mudou = juntos["mudou"].astype(bool)
    atrasou, grave = juntos["atrasou"], juntos["atraso_grave"]
    return AtrasoERefeito(
        atrasados=int(atrasou.sum()),
        atrasados_refeitos=int((atrasou & mudou).sum()),
        graves=int(grave.sum()),
        graves_refeitos=int((grave & mudou).sum()),
        no_prazo=int((~atrasou).sum()),
        no_prazo_refeitos=int((~atrasou & mudou).sum()),
    )


def _pares_seguidos(linhas: pd.DataFrame, valores: Sequence[str]) -> pd.DataFrame:
    """Cada exercício (`cnpj`, `fim`) com os valores do exercício anterior (`<valor>_antes`), quando o
    anterior é o ano seguido (de 10 a 14 meses antes); sem o anterior, a linha sai."""
    ordenado = linhas.sort_values(["cnpj", "fim"]).copy()
    por_companhia = ordenado.groupby("cnpj")
    dias = (ordenado["fim"] - por_companhia["fim"].shift(1)).dt.days
    minimo, maximo = DIAS_ENTRE_BALANCOS
    seguido = dias.between(minimo, maximo)
    for valor in valores:
        ordenado[f"{valor}_antes"] = por_companhia[valor].shift(1).where(seguido)
    return ordenado[seguido]


def remuneracao_e_lucro(
    remuneracao: pd.DataFrame, lucro: pd.DataFrame
) -> RemuneracaoELucro:
    """A remuneração total da diretoria estatutária em cada exercício inteiro já encerrado quando o FRE
    saiu (a última versão pública; o valor previsto para o ano em curso fica de fora), ao lado do lucro
    do ano, em pares de exercícios seguidos."""
    diretoria = remuneracao[remuneracao["orgao"] == DIRETORIA].copy()
    for coluna in (
        "inicio_do_exercicio",
        "fim_do_exercicio",
        "referencia",
        "publico_em",
    ):
        diretoria[coluna] = pd.to_datetime(diretoria[coluna])
    duracao = (diretoria["fim_do_exercicio"] - diretoria["inicio_do_exercicio"]).dt.days
    inteiro = duracao >= DIAS_ENTRE_BALANCOS[0]
    encerrado = diretoria["fim_do_exercicio"] < diretoria["publico_em"]
    diretoria = diretoria[inteiro & encerrado & (diretoria["total_do_orgao"] > 0)]
    ultima = (
        diretoria.sort_values(["cnpj", "fim_do_exercicio", "referencia", "versao"])
        .groupby(["cnpj", "fim_do_exercicio"])["total_do_orgao"]
        .last()
        .rename("remuneracao")
        .reset_index()
        .rename(columns={"fim_do_exercicio": "fim"})
    )
    juntos = ultima.assign(cnpj=_cnpjs(ultima["cnpj"])).merge(lucro, on=["cnpj", "fim"])
    pares = _pares_seguidos(juntos, ["remuneracao", "lucro"])
    subiu = pares["remuneracao"] > pares["remuneracao_antes"]
    tinha_lucro = pares["lucro_antes"] > 0
    caiu = tinha_lucro & (
        pares["lucro"] < (1 - VARIACAO_DO_LUCRO) * pares["lucro_antes"]
    )
    cresceu = tinha_lucro & (
        pares["lucro"] > (1 + VARIACAO_DO_LUCRO) * pares["lucro_antes"]
    )
    return RemuneracaoELucro(
        pares=len(pares),
        remuneracao_subiu=int(subiu.sum()),
        lucro_caiu=int(caiu.sum()),
        lucro_caiu_e_remuneracao_subiu=int((caiu & subiu).sum()),
        lucro_subiu=int(cresceu.sum()),
        lucro_subiu_e_remuneracao_subiu=int((cresceu & subiu).sum()),
        companhias=pares["cnpj"].nunique(),
        primeiro_exercicio=int(pares["fim"].min().year),
        ultimo_exercicio=int(pares["fim"].max().year),
    )


def dividendo_e_lucro(
    proventos: pd.DataFrame, lucro: pd.DataFrame, ate: date
) -> DividendoELucro:
    """O dividendo total que o FRE declara para cada exercício (a última versão cujo prazo de entrega já
    tinha passado em `ate`) ao lado do lucro do ano na DFP; só os exercícios com dividendo."""
    prazo = pd.to_datetime(proventos["referencia"]) + pd.DateOffset(
        months=MESES_DO_PRAZO_DO_FRE
    )
    entregues = proventos[prazo <= pd.Timestamp(ate)].copy()
    entregues["exercicio"] = pd.to_datetime(entregues["exercicio"])
    ultimo = (
        entregues.sort_values(["cnpj", "exercicio", "referencia", "versao"])
        .groupby(["cnpj", "exercicio"])["dividendo_total"]
        .last()
        .rename("dividendo")
        .reset_index()
        .rename(columns={"exercicio": "fim"})
    )
    juntos = ultimo.assign(cnpj=_cnpjs(ultimo["cnpj"])).merge(lucro, on=["cnpj", "fim"])
    com_dividendo = juntos[juntos["dividendo"] > 0]
    acima = com_dividendo["dividendo"] > com_dividendo["lucro"]
    return DividendoELucro(
        exercicios=len(com_dividendo),
        companhias=com_dividendo["cnpj"].nunique(),
        acima_do_lucro=int(acima.sum()),
        companhias_acima=com_dividendo[acima]["cnpj"].nunique(),
        com_prejuizo=int((com_dividendo["lucro"] <= 0).sum()),
        primeiro_exercicio=int(com_dividendo["fim"].min().year),
        ultimo_exercicio=int(com_dividendo["fim"].max().year),
    )


def _primeira_insolvencia(insolvencia: pd.DataFrame) -> pd.Series:
    """O dia em que cada companhia comunicou o primeiro pedido ou decreto próprio (CNPJ → data)."""
    propria = insolvencia[insolvencia["rotulo"].isin(ROTULOS_DE_INSOLVENCIA)]
    return pd.to_datetime(propria["publico_em"]).groupby(_cnpjs(propria["cnpj"])).min()


def parecer_e_insolvencia(
    pareceres: pd.DataFrame, insolvencia: pd.DataFrame, ate: date
) -> ParecerEInsolvencia:
    """Cada parecer de DFP (a última versão pública de cada exercício) publicado há mais de 24 meses:
    o auditor apontou incerteza sobre a continuidade, e a companhia entrou em recuperação, falência ou
    liquidação nos 24 meses seguintes? A companhia que já estava insolvente no dia do parecer sai."""
    pareceres = pareceres.assign(publico_em=pd.to_datetime(pareceres["publico_em"]))
    ultimo = (
        pareceres.sort_values(["cnpj", "referencia", "versao"])
        .groupby(["cnpj", "referencia"])
        .last()
        .reset_index()
    )
    janela = pd.DateOffset(months=MESES_DEPOIS_DO_PARECER)
    fechados = ultimo[ultimo["publico_em"] + janela <= pd.Timestamp(ate)].copy()
    fechados["cnpj"] = _cnpjs(fechados["cnpj"])
    fechados["insolvencia_em"] = fechados["cnpj"].map(
        _primeira_insolvencia(insolvencia)
    )
    ja_estava = fechados["insolvencia_em"] <= fechados["publico_em"]
    fechados = fechados[~ja_estava]
    depois = (fechados["insolvencia_em"] > fechados["publico_em"]) & (
        fechados["insolvencia_em"] <= fechados["publico_em"] + janela
    )
    duvida = fechados["continuidade_operacional"] == SIM
    sem_duvida = fechados["continuidade_operacional"] == NAO
    classificados = fechados[duvida | sem_duvida]
    return ParecerEInsolvencia(
        com_duvida=int(duvida.sum()),
        com_duvida_e_insolvencia=int((duvida & depois).sum()),
        sem_duvida=int(sem_duvida.sum()),
        sem_duvida_e_insolvencia=int((sem_duvida & depois).sum()),
        companhias_com_duvida=fechados[duvida]["cnpj"].nunique(),
        primeiro_exercicio=int(pd.to_datetime(classificados["referencia"]).min().year),
        ultimo_exercicio=int(pd.to_datetime(classificados["referencia"]).max().year),
    )


def medir_cruzamentos(porta: PortaQueLe, catalogo: dict, ate: date) -> Cruzamentos:
    """Mede os cruzamentos pela porta, só com o que era público em `ate`. Tabela fora do catálogo ou que
    a licença não deixa mostrar dá erro, como nos números da página Dados; o atraso só pode ser contado."""
    ausentes = [t for t in TABELAS_DOS_CRUZAMENTOS if t not in catalogo["tabelas"]]
    if ausentes:
        raise ValueError(
            f"fora do catálogo, não vira fato público: {', '.join(ausentes)}"
        )
    exigir_que_pode_mostrar(
        t for t in TABELAS_DOS_CRUZAMENTOS if t not in TABELAS_SO_EM_CONTAGEM
    )
    exigir_que_pode_contar(TABELAS_SO_EM_CONTAGEM)
    lucros = linhas_do_lucro(porta, ate)
    balancos = balancos_anuais(lucros)
    lucro = lucro_por_exercicio(lucros)
    trocas = porta.ler(
        TROCAS_DE_AUDITOR, como_era_em=ate, colunas=["cnpj", "publico_em"]
    )
    rotulos = porta.ler(
        ROTULOS_DE_ATRASO, como_era_em=ate, colunas=list(COLUNAS_DO_ATRASO)
    )
    remuneracao = porta.ler(
        REMUNERACAO, como_era_em=ate, colunas=list(COLUNAS_DA_REMUNERACAO)
    )
    # sem `publico_em` no contrato dos proventos: o prazo do FRE decide o que já era público
    proventos = porta.ler(PROVENTOS, colunas=list(COLUNAS_DOS_PROVENTOS))
    pareceres = porta.ler(
        PARECERES, como_era_em=ate, colunas=list(COLUNAS_DOS_PARECERES)
    )
    insolvencia = porta.ler(
        INSOLVENCIA, como_era_em=ate, colunas=list(COLUNAS_DA_INSOLVENCIA)
    )
    return Cruzamentos(
        lucros=lucros_refeitos(balancos),
        auditor=trocas_de_auditor(trocas, balancos),
        atraso=atraso_e_refeito(rotulos, balancos),
        remuneracao=remuneracao_e_lucro(remuneracao, lucro),
        dividendo=dividendo_e_lucro(proventos, lucro, ate),
        parecer=parecer_e_insolvencia(pareceres, insolvencia, ate),
        medido_em=ate.isoformat(),
    )


def cruzamentos_da_fotografia(dados: dict) -> Cruzamentos:
    """A fotografia gravada de volta nos números; campo a mais ou a menos é erro."""
    return Cruzamentos(
        lucros=LucrosRefeitos(**dados["lucros"]),
        auditor=TrocasDeAuditor(**dados["auditor"]),
        atraso=AtrasoERefeito(**dados["atraso"]),
        remuneracao=RemuneracaoELucro(**dados["remuneracao"]),
        dividendo=DividendoELucro(**dados["dividendo"]),
        parecer=ParecerEInsolvencia(**dados["parecer"]),
        medido_em=dados["medido_em"],
    )


def _milhar(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def _porcento(parte: int, todo: int) -> str:
    return f"{100 * parte / todo:.1f}%".replace(".", ",")


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


def _fato_do_atraso(atraso: AtrasoERefeito, data: str) -> Fato:
    return Fato(
        chave="atraso",
        numero=_porcento(atraso.atrasados_refeitos, atraso.atrasados),
        texto=(
            f"dos {_milhar(atraso.atrasados)} balanços anuais entregues à CVM depois do prazo tiveram o "
            f"lucro do ano mudado em mais de 1% até o balanço seguinte. Nos {_milhar(atraso.no_prazo)} "
            f"entregues no prazo, foram {_porcento(atraso.no_prazo_refeitos, atraso.no_prazo)}; nos "
            f"{_milhar(atraso.graves)} com mais de 30 dias de atraso, "
            f"{_porcento(atraso.graves_refeitos, atraso.graves)}."
        ),
        fonte="CVM: demonstrações financeiras padronizadas (DFP) e as datas de entrega",
        tabelas=(ROTULOS_DE_ATRASO, DEMONSTRACOES),
        data=data,
        como_foi_calculado=(
            "O prazo da DFP é o da CVM (três meses depois do fim do exercício) e o atraso é um rótulo "
            "nosso: a primeira entrega registrada no sistema da CVM depois do prazo, contada em dias "
            "úteis; grave quando passa de 30 dias corridos. O lucro mudado segue a regra do primeiro "
            "cartão, e só entram os balanços que já têm o do ano seguinte. Atrasar não quer dizer "
            "erro no balanço: o cartão mostra uma frequência, não uma causa."
        ),
    )


def _fato_da_remuneracao(remuneracao: RemuneracaoELucro, data: str) -> Fato:
    return Fato(
        chave="remuneracao",
        numero=_porcento(
            remuneracao.lucro_caiu_e_remuneracao_subiu, remuneracao.lucro_caiu
        ),
        texto=(
            f"dos {_milhar(remuneracao.lucro_caiu)} exercícios em que o lucro caiu mais de 20% (ou virou "
            f"prejuízo) tiveram a remuneração total da diretoria estatutária maior que no ano anterior. "
            f"Quando o lucro cresceu mais de 20%, ela subiu em "
            f"{_porcento(remuneracao.lucro_subiu_e_remuneracao_subiu, remuneracao.lucro_subiu)} dos "
            f"{_milhar(remuneracao.lucro_subiu)}."
        ),
        fonte="CVM: formulário de referência (FRE, remuneração dos administradores) e DFP",
        tabelas=(REMUNERACAO, DEMONSTRACOES),
        data=data,
        como_foi_calculado=(
            "A remuneração total reconhecida da diretoria estatutária em cada exercício, como o último "
            "formulário de referência público a informa (a CVM reescreve os anos antigos), só nos "
            "exercícios inteiros já encerrados quando o formulário saiu: o valor previsto para o ano em "
            "curso fica de fora. O lucro é o do período na DRE da DFP, consolidado ou individual. Cada "
            f"par é um exercício e o anterior: {_milhar(remuneracao.pares)} pares, de "
            f"{remuneracao.primeiro_exercicio} a {remuneracao.ultimo_exercicio}, em "
            f"{_milhar(remuneracao.companhias)} companhias; em todos eles, a remuneração subiu em "
            f"{_porcento(remuneracao.remuneracao_subiu, remuneracao.pares)}. Ela pode subir porque "
            "entraram diretores ou porque o pagamento foi combinado antes do resultado."
        ),
    )


def _fato_do_dividendo(dividendo: DividendoELucro, data: str) -> Fato:
    return Fato(
        chave="dividendo",
        numero=_milhar(dividendo.acima_do_lucro),
        texto=(
            f"dos {_milhar(dividendo.exercicios)} exercícios com dividendo declarado no formulário de "
            f"referência, de {dividendo.primeiro_exercicio} a {dividendo.ultimo_exercicio}, pagaram mais "
            f"do que o lucro do ano no balanço ({_milhar(dividendo.companhias_acima)} companhias). Em "
            f"{_milhar(dividendo.com_prejuizo)} deles, o ano fechou em prejuízo."
        ),
        fonte="CVM: formulário de referência (FRE, proventos) e DFP",
        tabelas=(PROVENTOS, DEMONSTRACOES),
        data=data,
        como_foi_calculado=(
            "O dividendo total do exercício (dividendos e juros sobre capital próprio) que o formulário "
            "de referência declara, na última versão cujo prazo de entrega (cinco meses depois do fim "
            "do exercício a que o formulário se refere) já tinha passado, comparado com o lucro do "
            "período na DRE do mesmo exercício, consolidado ou individual. Pagar mais do que o lucro do "
            "ano é permitido: sai de reservas ou de lucros de anos anteriores; o cartão só conta. A CVM "
            "tirou a tabela de proventos do formulário aberto depois de 2022, e a série para ali. "
            f"São {_milhar(dividendo.companhias)} companhias."
        ),
    )


def _fato_do_parecer(parecer: ParecerEInsolvencia, data: str) -> Fato:
    return Fato(
        chave="parecer",
        numero=_porcento(parecer.com_duvida_e_insolvencia, parecer.com_duvida),
        texto=(
            f"dos {_milhar(parecer.com_duvida)} pareceres de auditoria com incerteza relevante sobre a "
            f"continuidade da companhia foram seguidos, em 24 meses, de recuperação judicial ou "
            f"extrajudicial, falência ou liquidação. Entre os {_milhar(parecer.sem_duvida)} sem esse "
            f"alerta, foram {_porcento(parecer.sem_duvida_e_insolvencia, parecer.sem_duvida)}."
        ),
        fonte="CVM: relatório do auditor na DFP e comunicados das companhias",
        tabelas=(PARECERES, INSOLVENCIA),
        data=data,
        como_foi_calculado=(
            "Cada parecer de auditoria da DFP (a última versão pública de cada exercício) publicado há "
            f"mais de 24 meses, de {parecer.primeiro_exercicio} a {parecer.ultimo_exercicio}. O alerta é "
            "o parágrafo de incerteza relevante sobre a continuidade operacional, lido pelo nosso "
            "rótulo no texto do relatório; o relatório curto ou ambíguo fica de fora. A insolvência é o "
            "primeiro pedido ou decreto que a própria companhia comunicou à CVM (fato relevante ou "
            "formulário); a companhia que já estava em recuperação quando o parecer saiu não entra. "
            f"São {_milhar(parecer.companhias_com_duvida)} companhias com o alerta. O auditor descreve o "
            "que vê: o cartão mostra uma frequência, não uma previsão."
        ),
    )


def fatos_agregados(cruzamentos: Cruzamentos) -> list[Fato]:
    """Os cartões dos cruzamentos, na ordem da página inicial."""
    data = cruzamentos.medido_em
    return [
        _fato_dos_lucros(cruzamentos.lucros, data),
        _fato_do_auditor(cruzamentos.auditor, data),
        _fato_do_atraso(cruzamentos.atraso, data),
        _fato_da_remuneracao(cruzamentos.remuneracao, data),
        _fato_do_dividendo(cruzamentos.dividendo, data),
        _fato_do_parecer(cruzamentos.parecer, data),
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


# --- busca aberta: três agregados; nenhum nome de auditor, texto livre ou preço ------------------


def _tabela_publica(nome: str) -> bool:
    from base import dossie
    from base.dicionario import TABELAS
    from src.banco.coletas import licenca_da_fonte, revenda_da_fonte

    tabela = TABELAS.get(nome)
    return bool(
        tabela
        and dossie.pode_mostrar(nome)
        and revenda_da_fonte(tabela.familia_da_fonte).startswith("vendável")
        and situacao_da_licenca(
            licenca_da_fonte(tabela.familia_da_fonte),
            revenda_da_fonte(tabela.familia_da_fonte),
        )
        == LICENCIADA
    )


def _linhas_numericas(
    linhas: list[dict], numeros: tuple[str, ...], datas: tuple[str, ...]
) -> list[dict]:
    """Só os campos usados pelo molde, com números finitos e datas válidas."""
    saida = []
    for linha in linhas:
        try:
            limpa = {c: float(linha[c]) for c in numeros}
            if not all(math.isfinite(v) for v in limpa.values()):
                continue
            for coluna in datas:
                limpa[coluna] = date.fromisoformat(str(linha[coluna])[:10]).isoformat()
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        saida.append(limpa)
    return saida


def destaques_publicos(ficha: "Ficha") -> list["Destaque"]:
    """Até três agregados licenciados da ficha; a resposta nunca contém uma seção completa."""
    from base import dossie as regras
    from src.destaques import destaques_da_ficha
    from src.dossie import SecaoDaFicha

    secoes = []
    for secao in ficha.secoes:
        tabelas = {}
        fontes = set()
        if secao.chave == "ofertas_e_fundos":
            campos = (
                (
                    "fundos_por_mes",
                    ("fundos", "valor"),
                    ("competencia",),
                    ("painel_dos_fundos",),
                ),
                (
                    "ofertas_por_ano",
                    ("ano", "ofertas", "valor_total"),
                    (),
                    ("ofertas_antigas", "ofertas_resolucao_160"),
                ),
            )
        elif secao.chave == "setor_regulado":
            campos = tuple(
                (s.nome, ("ano", "valor", "participacao"), ("ultimo_mes",), (s.tabela,))
                for s in regras.SERIES_DAS_AGENCIAS
            )
        else:
            continue
        for nome, numeros, datas, origens in campos:
            if not all(_tabela_publica(o) for o in origens):
                continue
            linhas = _linhas_numericas(secao.tabelas.get(nome, []), numeros, datas)
            if linhas:
                tabelas[nome] = linhas
                fontes.update(regras.fontes_das_tabelas(origens))
        if tabelas:
            secoes.append(
                SecaoDaFicha(
                    chave=secao.chave, titulo="", tabelas=tabelas, fontes=sorted(fontes)
                )
            )
    limpa = ficha.model_copy(update={"secoes": secoes})
    saida = destaques_da_ficha(limpa)[:3]
    regras.conferir_sem_pessoas({"destaques": [asdict(d) for d in saida]}, set())
    return saida


def empresas_da_base() -> list[dict[str, str]]:
    """Fichas de exemplo verificadas, disponíveis mesmo quando a API não responde."""
    from src import amostra_do_relatorio, dossie

    ficha = dossie.ler_ficha(dossie.FICHA_DE_EXEMPLO)
    if ficha is None or not destaques_publicos(ficha):
        return []
    return [
        {
            "cnpj": ficha.cnpj,
            "empresa": amostra_do_relatorio.NOME,
            "ticker": amostra_do_relatorio.TICKER,
            "link": "/relatorio-de-exemplo.html",
        }
    ]
