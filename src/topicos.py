"""O assunto (tópico) de cada fato relevante: leitor v2 (ADR 0069, plano do leitor de fatos relevantes).

Três camadas, nesta ordem; a primeira que decide vale:

1. **Regras sobre o título** que a empresa dá ao fato no IPE da CVM (o campo "Assunto"). Vale para todo o
   histórico, desde 2003, sem baixar nenhum documento. Este módulo.
2. **Regras sobre o texto**, quando o PDF foi lido e o título é genérico ("Fato Relevante").
3. **Modelo de linguagem**, só para o que as regras deixam em "Outros" (ADR 0069: lista fechada e trecho
   literal do documento).

As regras são frases sobre o título sem acento e em minúsculas, em ordem de prioridade: a mais específica
primeiro (cisão antes de incorporação; OPA e recompra antes de aquisição, porque "aquisição de ações de
própria emissão" é recompra; decisão de regulador antes de resultados). O tópico principal é o da regra
de maior prioridade que casou; os secundários, os seguintes (até 2). O trecho é o pedaço do título que
decidiu, como a empresa escreveu.

Os tópicos de operação usam os códigos do dicionário da base de M&A (ADR 0063): são os candidatos dela.
É uma classificação editorial, explicável e versionada; não é opinião sobre a empresa.
"""

import math
import re
import unicodedata
from dataclasses import dataclass

from src import leitura

VERSAO = "1"
REGRA_DO_TITULO = "regra_titulo"
MAX_SECUNDARIOS = 2

TOPICOS: dict[str, str] = {
    # operações (candidatos da base de M&A)
    "AQUISICAO": "Aquisição",
    "VENDA_ATIVO": "Venda de ativo ou participação",
    "FUSAO_INCORPORACAO": "Fusão ou incorporação",
    "CISAO": "Cisão",
    "JV": "Joint venture",
    "ALIEN_CONTROLE": "Mudança de controle",
    "OPA": "OPA",
    "FECHAMENTO_CAPITAL": "Fechamento de capital",
    "REORG": "Reorganização societária",
    # o resto
    "DIVIDENDOS": "Dividendos e JCP",
    "RECOMPRA": "Recompra de ações",
    "DIVIDA": "Dívida e captação",
    "OFERTA_ACOES": "Oferta de ações e mudanças no capital",
    "RJ_INSOLVENCIA": "Recuperação judicial e falência",
    "ADMINISTRACAO": "Mudança na administração",
    "RESULTADOS_PROJECOES": "Resultados e projeções",
    "PROCESSOS": "Processos e decisões de reguladores",
    "OUTROS": "Outros",
}
OPERACOES = frozenset(
    {"AQUISICAO", "VENDA_ATIVO", "FUSAO_INCORPORACAO", "CISAO", "JV", "ALIEN_CONTROLE", "OPA",
     "FECHAMENTO_CAPITAL", "REORG"}
)  # fmt: skip
OUTROS = "OUTROS"

# (tópico, frases) em ordem de prioridade; as frases valem sobre o título sem acento e minúsculo.
# Cisão com "incorporação do acervo cindido" é cisão; incorporação com deslistagem é incorporação;
# "dvidendos" é um erro de digitação comum no IPE.
REGRAS: tuple[tuple[str, str], ...] = (
    ("CISAO", r"\bcisao\b"),
    ("FUSAO_INCORPORACAO", (r"\bfusao\b|\bincorporac|\bincorpora(r|da|do|dos|das)?\b"
                            r"|combinacao de negocios")),
    ("FECHAMENTO_CAPITAL", (r"cancelamento d[eo] registro|fechamento de capital"
                            r"|saida do novo mercado|deslistage")),
    ("OPA", r"\bopas?\b|oferta publica (de|para) aquisicao|\btag along\b"),
    ("RECOMPRA", (r"recompra|tesouraria|aquisicao de acoes de (propria|sua) emissao"
                  r"|aquisicao de acoes de emissao propria")),
    ("ALIEN_CONTROLE", (r"(alienacao|transferencia|mudanca|troca) d[eo] controle"
                        r"|novo controlador|privatiza|desestatiza")),
    ("JV", r"joint venture|\bjv\b"),
    ("DIVIDA", (r"debenture|notas? comercia|notas? promissoria|\bbonds?\b|bondholder"
                r"|titulos? globa|titulos? de divida|\bdividas?\b|captacao|financiamento"
                r"|emprestimo|\brating\b|vencimento antecipado|alienacao fiduciaria"
                r"|\bcr[ia]s?\b|senior notes")),
    ("VENDA_ATIVO", (r"\bupi\b|unidade produtiva isolada|desinvest|\baliena(cao|r|da|do)\b"
                     r"|\bvenda d|\bvende\b|cessao de carteira|leaseback")),
    ("AQUISICAO", r"aquisic|\badquir|\bcompra d"),
    ("REORG", r"reorganizacao societaria|reestruturacao societaria"),
    ("RJ_INSOLVENCIA", (r"recuperacao (judicial|extrajudicial)|falencia"
                        r"|liquidacao extrajudicial|\brj\b|assembleia geral (de|dos) credores")),
    ("DIVIDENDOS", r"di?vidend|juros sobre (o )?capital|\bjcp\b|provento|bonificac"),
    ("OFERTA_ACOES", (r"oferta publica|follow[- ]?on|\bipo\b|oferta restrita"
                      r"|oferta (primaria|secundaria)|aumento de capital|reducao de capital"
                      r"|subscric|desdobramento|grupamento|\bafac\b")),
    ("ADMINISTRACAO", (r"renuncia|\beleic|\beleit|diretor|presidente|\bceo\b|\bcfo\b|conselh"
                       r"|nomeac|\bposse\b|administrador|sucessao")),
    ("PROCESSOS", (r"processo|arbitragem|acao (judicial|civil)|investigac|auto de infracao"
                   r"|leniencia|\bdecisao\b|tribunal|sentenca|liminar|tutela|cautelar"
                   r"|ajustamento de conduta|condenac|\bmulta\b")),
    ("RESULTADOS_PROJECOES", (r"resultado|guidance|projec|demonstracoes financeiras"
                              r"|\b[1-4]t\d{2}\b|\b[1-4]itr\b|\bitr\b|\bdfp\b|producao e vendas"
                              r"|previa operacional")),
)  # fmt: skip
Regras = tuple[tuple[str, re.Pattern[str]], ...]
_COMPILADAS: Regras = tuple((topico, re.compile(frase)) for topico, frase in REGRAS)
_PRIORIDADE = {topico: i for i, (topico, _) in enumerate(REGRAS)}
# No texto, "Conselho de Administração aprovou" e "Diretor de Relações com Investidores" aparecem
# em quase todo fato relevante: lá, administração só conta com um acontecimento.
ADMINISTRACAO_NO_TEXTO = (
    r"renuncia|\beleic|\beleit|nomeac|\bposse\b|sucessao|desligamento"
    r"|nov[oa] (diretor|presidente|ceo|cfo|conselheir)"
)
_COMPILADAS_DO_TEXTO: Regras = tuple(
    (t, re.compile(ADMINISTRACAO_NO_TEXTO) if t == "ADMINISTRACAO" else regra)
    for t, regra in _COMPILADAS
)

# notícia negada ou boato sem operação: "não há negociação", "desconhece"
NEGACAO = re.compile(r"\bnao (ha|existe|houve|ter)\b|\bdesconhece|\bdesmente|\bnega\b")
SEPARADOR_DE_ASSUNTOS = "||"  # o IPE junta vários assuntos num campo só


@dataclass(frozen=True)
class LeituraDoTopico:
    """O assunto de um fato relevante e como foi decidido."""

    principal: str  # um código de TOPICOS
    secundarios: tuple[str, ...]  # até 2, sem repetir o principal
    trecho: str  # o pedaço do documento que decidiu; vazio em "Outros"
    metodo: str  # regra_titulo, regra_texto ou modelo
    versao: str
    modelo: str = ""  # só na camada do modelo: qual modelo e qual versão do prompt


def _sem_acento(texto: str) -> str:
    """Minúsculo e sem acento."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def _topicos_da_parte(parte: str, regras: Regras = _COMPILADAS) -> list[str]:
    limpo = _sem_acento(parte)
    if NEGACAO.search(limpo):
        return []
    return [topico for topico, regra in regras if regra.search(limpo)]


def topico_do_titulo(titulo: str) -> LeituraDoTopico:
    """O tópico de um fato relevante pelo título do IPE (camada 1 do leitor v2)."""
    achados: list[tuple[int, str, str]] = []  # (prioridade, tópico, parte do título)
    for parte in (p.strip() for p in (titulo or "").split(SEPARADOR_DE_ASSUNTOS)):
        if parte:
            achados += [(_PRIORIDADE[t], t, parte) for t in _topicos_da_parte(parte)]
    if not achados:
        return LeituraDoTopico(OUTROS, (), "", REGRA_DO_TITULO, VERSAO)
    achados.sort()
    _, principal, trecho = achados[0]
    secundarios = tuple(dict.fromkeys(t for _, t, _ in achados if t != principal))
    return LeituraDoTopico(
        principal, secundarios[:MAX_SECUNDARIOS], trecho, REGRA_DO_TITULO, VERSAO
    )


# --- camada 2: o texto (quando o PDF foi lido) ----------------------------------------------------

REGRA_DO_TEXTO = "regra_texto"
MIN_FRASES_LIDAS = (
    5  # o assunto está no começo: lê o primeiro terço, e pelo menos 5 frases
)


def topico_do_texto(texto: str) -> LeituraDoTopico:
    """O tópico pelo texto do fato relevante (camada 2): a primeira frase que trata de um assunto.

    Sem o cabeçalho e a assinatura; só o começo do documento (o fim costuma ter ressalvas e histórico).
    Na frase que decide, vale a regra de maior prioridade; os secundários vêm dela e das seguintes.
    """
    frases = leitura.dividir_em_frases(leitura.sem_cabecalho_e_assinatura(texto or ""))
    janela = frases[: max(MIN_FRASES_LIDAS, math.ceil(len(frases) / 3))]
    principal, trecho, vistos = OUTROS, "", []
    for frase in janela:
        achados = sorted(
            _topicos_da_parte(frase, _COMPILADAS_DO_TEXTO), key=_PRIORIDADE.__getitem__
        )
        if achados and principal == OUTROS:
            principal, trecho = achados[0], frase
        vistos += [t for t in achados if t != principal and t not in vistos]
    return LeituraDoTopico(
        principal, tuple(vistos[:MAX_SECUNDARIOS]), trecho, REGRA_DO_TEXTO, VERSAO
    )


def topico_do_documento(titulo: str, texto: str) -> LeituraDoTopico:
    """O título decide quando é claro; o texto, quando o título é genérico ("Fato Relevante")."""
    pelo_titulo = topico_do_titulo(titulo)
    if pelo_titulo.principal != OUTROS or not (texto or "").strip():
        return pelo_titulo
    return topico_do_texto(texto)
