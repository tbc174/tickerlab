"""Ratings pelos documentos da CVM: notas das agências que as companhias entregam no IPE.

Prova e plano: `reports/2026-10-16-provas-gdelt-e-ratings.md` e
`planos/2026-10-16-ratings-pelos-documentos-da-cvm.md` (pasta privada). O IPE (`cvm-hist-ipe`, desde
2003) tem um tipo próprio, "Relatório de Agência de Rating" (~4 mil documentos), e comunicados, fatos
relevantes e editais de assembleia que falam do rating no assunto (~1.900). Cada documento é baixado
do sistema da CVM (fonte `cvm-ipe-rating`) e a nota sai do texto.

**Data pública** (`publico_em`) = data de entrega à CVM daquela versão do documento. A data do
relatório da agência (`Data_Referencia`) costuma ser um dia antes, mas há entregas meses depois e
referências depois da entrega (erro de preenchimento): nunca é usada como data pública. Cada versão
reapresentada é um documento à parte, com a própria data, para que a base "como era na data" use só
o que já tinha sido entregue. Licença: ODbL (CVM).
"""

import io
import re
import unicodedata
import zipfile

import pandas as pd

from src import eventos
from src.links_das_fontes import link_da_fonte

FONTE_DOS_PDFS = "cvm-ipe-rating"
FONTE_DO_IPE = "cvm-hist-ipe"
URL_DO_IPE = eventos.URL_DO_IPE  # arquivo anual do IPE, como o arquivista guarda
CODIFICACAO_DA_CVM = "cp1252"
TIPO_DO_RELATORIO = "relatorio de agencia de rating"
# assunto (sem acento, minúsculas) que fala de rating; agência pelo nome ou pela palavra
ASSUNTO_COM_RATING = re.compile(
    r"\brating|classificacao de risco|agencia de (?:classificacao|risco)|nota de risco"
    r"|moody|fitch|standard ?(?:&(?:amp;?)?|and) ?poor|\bs ?&(?:amp;?)? ?p\b|austin rating"
    r"|liberum|\bsr rating|\blf rating|am best"
)
# "nota de crédito" fica de fora de propósito: no IPE quase sempre é a Nota de Crédito à Exportação
COLUNAS = (
    "cnpj",
    "empresa",
    "codigo_cvm",
    "evidencia",
    "categoria",
    "tipo",
    "assunto",
    "referencia",
    "publico_em",
    "protocolo",
    "versao",
    "link",
)


def _simples(texto: object) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode(
        "ascii", "ignore"
    )
    return sem_acento.decode().lower().strip()


def _ler_ipe_bruto(conteudo_do_zip: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nome = next(n for n in arquivo.namelist() if "ipe_cia_aberta" in n)
        with arquivo.open(nome) as csv:
            return pd.read_csv(
                csv,
                sep=";",
                encoding=CODIFICACAO_DA_CVM,
                encoding_errors="replace",
                dtype=str,
            ).fillna("")


def evidencias(bruto: pd.DataFrame) -> pd.Series:
    """Por que cada documento entra: `relatorio_de_agencia` (o tipo próprio do IPE), `assunto` (o
    assunto fala de rating) ou vazio (não entra). Vetorizado: o IPE inteiro tem ~750 mil linhas e a
    coleta relê a lista a cada rodada."""
    relatorio = bruto["Tipo"].map(_simples).eq(TIPO_DO_RELATORIO)
    no_assunto = bruto["Assunto"].map(_simples).str.contains(ASSUNTO_COM_RATING)
    escolha = pd.Series(None, index=bruto.index, dtype=object)
    escolha[no_assunto] = "assunto"
    escolha[relatorio] = "relatorio_de_agencia"
    return escolha


def documentos_com_rating(bruto: pd.DataFrame) -> pd.DataFrame:
    """Os documentos do IPE que trazem rating, um por versão entregue, com a data pública."""
    escolha = evidencias(bruto)
    linhas = bruto[escolha.notna()]
    tabela = pd.DataFrame(
        {
            "cnpj": linhas["CNPJ_Companhia"].str.strip(),
            "empresa": linhas["Nome_Companhia"].str.strip(),
            "codigo_cvm": linhas["Codigo_CVM"].str.strip(),
            "evidencia": escolha[escolha.notna()],
            "categoria": linhas["Categoria"].str.strip(),
            "tipo": linhas["Tipo"].str.strip(),
            "assunto": linhas["Assunto"].str.strip(),
            "referencia": pd.to_datetime(
                linhas["Data_Referencia"], errors="coerce"
            ).dt.date,
            "publico_em": pd.to_datetime(
                linhas["Data_Entrega"], errors="coerce"
            ).dt.date,
            # de 2003 a 2014 o protocolo vem vazio: o link identifica o documento
            "protocolo": linhas["Protocolo_Entrega"]
            .str.strip()
            .where(
                linhas["Protocolo_Entrega"].str.strip() != "", linhas["Link_Download"]
            ),
            "versao": pd.to_numeric(linhas["Versao"], errors="coerce").astype("Int64"),
            "link": linhas["Link_Download"].map(link_da_fonte),
        },
        columns=list(COLUNAS),
    )
    tabela = tabela.dropna(subset=["publico_em", "link"])
    tabela = tabela.drop_duplicates("link")
    return tabela.sort_values(["publico_em", "protocolo", "versao"]).reset_index(
        drop=True
    )


def ler_documentos_do_ipe(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os documentos com rating de um arquivo anual do IPE."""
    return documentos_com_rating(_ler_ipe_bruto(conteudo_do_zip))
