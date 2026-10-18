"""Candidatos a operação de M&A no IPE da CVM (série 1 da base de M&A, PR 1; ADR 0063).

Plano: `planos/2026-10-14-base-de-m-e-a.md` (pasta privada). Lê os arquivos anuais do IPE já guardados
(`cvm-hist-ipe`, desde 2003; não baixa nada) e escolhe os documentos que podem anunciar uma operação:
fatos relevantes pelo assunto, comunicados ao mercado com o tipo no assunto e todo edital de OPA. A
lista favorece a cobertura: o assunto padrão do sistema da CVM ("Reorganização Societária -
Incorporação, Cisão ou Fusão", "Mudança de Controle"...) e o vazio entram sem tipo, e quem separa a
operação do que não é operação é a leitura do texto (PR 2).

**Cobertura** contra uma lista independente, as reestruturações que as companhias declaram no FRE
(2010 a 2015): das operações com algum fato relevante da companhia no ano anterior, 80% têm um
fato relevante ou edital candidato nessa janela, 92% somando os comunicados (as regras antigas,
de `tickerlab-fontes/ma/candidatas_ma.py`, pegavam 74%);
lidas à mão 40 perdidas, só 4 tinham um fato relevante sobre a operação, ou seja, cobertura de ~97%
dos fatos relevantes que existem (otimista: o acerto pode ser outra operação da mesma companhia). As
outras 36 não tinham fato relevante sobre a operação: operações pequenas dentro do grupo. Amostra de
ouro (100 conferidas): 84 de 85 operações seguem candidatas (a perdida é uma oferta de ações, fora do
escopo).

**Data pública** (`publico_em`) = entrega à CVM daquela versão do documento, como em `base/ratings.py`.
Licença: ODbL (CVM).
"""

import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base.parquet import LINHAGEM, gravar_se_mudou
from base.ratings import FONTE_DO_IPE, URL_DO_IPE, ler_ipe_bruto, tabela_do_ipe
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.versao_do_codigo import versao_do_codigo

log = logging.getLogger("tickerlab.ma_ipe")

__all__ = ["FONTE_DO_IPE", "URL_DO_IPE"]

FATO_RELEVANTE = "fato relevante"
COMUNICADO = "comunicado ao mercado"
EDITAL_DE_OPA = "opa - edital de oferta publica de acoes"
# comunicados que não anunciam operação da companhia: participação relevante de terceiros (art. 12)
# e apresentações
TIPO_DE_COMUNICADO_FORA = re.compile(r"art\. 12|apresenta")

# pista do tipo pelo assunto (sem acento, minúsculas); vale a primeira da lista que casar.
# AQUISICAO = controle ou minoritária (o texto decide); NEGOCIACAO = etapa (memorando,
# exclusividade), não um tipo
TIPOS = (
    (
        "OPA",
        (
            r"\bopa\b|oferta publica (?:de |para )?(?:aquisicao|compra)|fechamento de capital"
            r"|oferta publica (?:voluntaria|concorrente|unificada)"
        ),
    ),
    ("INC_ACOES", r"incorporacao (?:de|das) acoes"),
    ("FUSAO", r"\bfusao\b|combinacao de negocios|combinacao de atividades|\bmerger\b"),
    ("CISAO", r"\bcisao\b|\bcindid"),
    ("INC_EMPRESA", r"incorpora"),
    ("JV", r"joint.?venture|\bjv\b|\bassociacao\b|parceria estrategica|\bconsorcio\b"),
    ("UPI", r"\bupi\b|unidade produtiva isolada"),
    ("PRIVATIZACAO", r"privatiza|desestatiza"),
    (
        "ALIEN_CONTROLE",
        (
            r"alienacao (?:do|de) controle|transferencia (?:do|de) controle|contrato de transferencia"
            r"|controle acionario|passa(?:ra)? (?:a )?ser (?:a )?controladora|aquisicao (?:do|de) controle"
            r"|bloco de controle|composicao (?:societaria|acionaria)|distribuicao acionaria"
            r"|estrutura (?:societaria|acionaria)"
        ),
    ),
    (
        "VENDA_ATIVO",
        (
            r"desinvest|alienacao d|\bvenda\b|\bvende\b|\balienacao\b"
            r"|cessao de (?:participacao|quotas|acoes)|cessao de direitos (?!creditorios)"
        ),
    ),
    (
        "AQUISICAO",
        (
            r"aquisi|adquir|\bcompras?\b|investimento em participacao"
            r"|participacao (?:societaria|acionaria)"
            r"|(?:aumento|reducao|anuncia) (?:de |da |sua )?participacao"
            r"|participacao (?:na|no|em) (?!leilao|evento|live|conferencia|lucros|reuniao|feira)"
            r"|subscricao de acoes|contrato de subscricao|acordo de (?:realizacao de )?investimento"
            r"|investimento em ativos|composicao do capital|investimento (?:na|no) "
        ),
    ),
    (
        "NEGOCIACAO",
        (
            r"memorando de entendimento|\bmou\b|\bnegociac|tratativa|exclusividade"
            r"|proposta (?:nao )?vinculante|oferta (?:nao )?vinculante|carta de intencoes"
            r"|due diligence"
        ),
    ),
)
# tipos que entram mesmo com palavra de exclusão no assunto ("incorporação com aumento de capital")
TIPOS_FORTES = frozenset(
    (
        "OPA",
        "INC_ACOES",
        "FUSAO",
        "CISAO",
        "INC_EMPRESA",
        "ALIEN_CONTROLE",
        "PRIVATIZACAO",
        "UPI",
    )
)
# o assunto padrão do sistema da CVM que lista três tipos não diz qual foi: fica sem tipo
PADRAO_SEM_TIPO = re.compile(r"incorporacao, cisao ou fusao")
# assunto padrão, vazio ou de esclarecimento, que esconde o tipo: o fato relevante entra sem tipo
GENERICO = re.compile(
    r"^\W*$|^fato relevante\W*$|^comunicado|reorganizacao societaria|reestruturacao societaria"
    r"|reestruturacao de participac|^reestruturacao\W*$|cancelamento de registro|cancelar o registro"
    r"|mudanca (?:de|do|no) controle|mudanca da composicao do patrimonio"
    r"|celebracao ou extincao de contrato|acordo de acionistas|operacao societaria"
    r"|evento societario|incorporacao, cisao ou fusao|esclarec|noticia|imprensa|\bmidia\b|rumor"
    r"|laudo de avaliacao(?! de terras)|lista triplice|avaliadora"
)
# o que parece operação mas não é: recompra, proventos, dívida, oferta de ações, aluguel
EXCLUI = re.compile(
    r"remuneracao|dividend|\bjcp\b|juros sobre|guidance|projec|recompra"
    r"|acoes de (?:emissao da )?propria|de emissao da (?:propria )?companhia|tesouraria"
    r"|renegociac|debentur|nota promissoria|direitos creditorios|formador de mercado|desdobramento"
    r"|grupamento|aumento de capital|reducao de capital"
    r"|oferta (?:publica )?(?:global |primaria |secundaria |restrita )?de (?:distribuicao|acoes ordinarias|units)"
    r"|follow.?on|\bipo\b|contrato de locacao|aluguel|beneficiaria de recursos"
    r"|sociedade beneficiaria|de terras"
)

POR_CATEGORIA = "categoria"  # edital de OPA
POR_ASSUNTO = "assunto"  # o assunto dá o tipo provável
POR_ASSUNTO_GENERICO = "assunto_generico"  # entra sem tipo; o texto decide
EVIDENCIAS = (POR_ASSUNTO, POR_ASSUNTO_GENERICO, POR_CATEGORIA)

COLUNAS = (
    "cnpj",
    "empresa",
    "codigo_cvm",
    "categoria",
    "tipo",
    "assunto",
    "tipo_provavel",
    "evidencia",
    "referencia",
    "publico_em",
    "protocolo",
    "versao",
    "link",
)
# o arquivo anual de onde veio a linha
LINHAGEM_DO_ARQUIVO = ("origem_sha256", "origem_coletada_em")
ORDEM = ["publico_em", "protocolo", "versao"]
PASTA_DA_TABELA = Path("ma") / "candidatos" / "candidatos"


def _simples(textos: pd.Series) -> pd.Series:
    """Sem acento, minúsculas, sem espaço nas pontas (o IPE mistura grafias)."""
    return (
        textos.str.normalize("NFKD")
        .str.encode("ascii", "ignore")
        .str.decode("ascii")
        .str.lower()
        .str.strip()
    )


def tipo_pelo_assunto(assuntos: pd.Series) -> pd.Series:
    """O tipo provável de cada assunto (já simplificado), ou vazio."""
    tipo = pd.Series(None, index=assuntos.index, dtype=object)
    # de trás para a frente: a primeira da lista vence
    for nome, regra in reversed(TIPOS):
        tipo[assuntos.str.contains(regra)] = nome
    return tipo.mask(assuntos.str.contains(PADRAO_SEM_TIPO))


def pistas(bruto: pd.DataFrame) -> pd.DataFrame:
    """`tipo_provavel` e `evidencia` de cada linha do IPE cru; `evidencia` vazia = não entra."""
    categoria = _simples(bruto["Categoria"])
    assunto = _simples(bruto["Assunto"])
    tipo = tipo_pelo_assunto(assunto)
    com_tipo = tipo.notna() & (~assunto.str.contains(EXCLUI) | tipo.isin(TIPOS_FORTES))
    generico = assunto.str.contains(GENERICO)
    fato = categoria.eq(FATO_RELEVANTE)
    comunicado = categoria.eq(COMUNICADO) & ~_simples(bruto["Tipo"]).str.contains(
        TIPO_DE_COMUNICADO_FORA
    )
    opa = categoria.eq(EDITAL_DE_OPA)

    evidencia = pd.Series(None, index=bruto.index, dtype=object)
    evidencia[fato & generico & ~com_tipo] = POR_ASSUNTO_GENERICO
    evidencia[(fato | comunicado) & com_tipo] = POR_ASSUNTO
    evidencia[opa] = POR_CATEGORIA
    tipo = tipo.where(evidencia.eq(POR_ASSUNTO))
    tipo[opa] = "OPA"
    return pd.DataFrame({"tipo_provavel": tipo, "evidencia": evidencia})


def candidatos(bruto: pd.DataFrame) -> pd.DataFrame:
    """Os documentos do IPE que podem anunciar uma operação, um por versão entregue."""
    escolha = pistas(bruto)
    entra = escolha["evidencia"].notna()
    return tabela_do_ipe(
        bruto[entra],
        COLUNAS,
        tipo_provavel=escolha.loc[entra, "tipo_provavel"],
        evidencia=escolha.loc[entra, "evidencia"],
    )


def ler_candidatos_do_ipe(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os candidatos de um arquivo anual do IPE."""
    return candidatos(ler_ipe_bruto(conteudo_do_zip))


# --- montagem pelo acervo (servidor de casa) -----------------------------------------------------
def montar(conexao: sa.Connection, pasta: Path, agora: datetime) -> dict[str, int]:
    """`<pasta>/ma/candidatos/candidatos.parquet` com todos os arquivos anuais do IPE guardados;
    devolve quantos candidatos há por evidência. Remontada inteira (`gravar_se_mudou` só regrava o
    que mudou; o passado que muda vira `.vN`)."""
    anuais = [
        original
        for original in originais_mais_recentes(conexao, FONTE_DO_IPE)
        if "ipe_cia_aberta_" in original.url
    ]
    tabelas = [
        ler_candidatos_do_ipe(conteudo).assign(
            origem_sha256=o.sha256,
            origem_coletada_em=pd.Timestamp(o.baixado_em).isoformat(),
        )
        for o in anuais
        if (conteudo := acervo.ler_original(o.caminho_do_original))
    ]
    tabela = (
        pd.concat(tabelas, ignore_index=True).drop_duplicates("link")
        if tabelas
        else pd.DataFrame(columns=[*COLUNAS, *LINHAGEM_DO_ARQUIVO])
    )
    tabela = tabela.astype({"versao": "Int64"}).sort_values(ORDEM, kind="stable")
    gravar_se_mudou(
        tabela.reset_index(drop=True).assign(
            montado_em=agora.isoformat(), versao_do_codigo=versao_do_codigo()
        ),
        pasta / PASTA_DA_TABELA,
        [{"url": o.url, "sha256": o.sha256} for o in anuais],
        ORDEM,
        carimbos=LINHAGEM,
    )
    contagem = tabela["evidencia"].value_counts()
    return {e: int(contagem.get(e, 0)) for e in EVIDENCIAS}
