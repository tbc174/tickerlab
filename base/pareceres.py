"""Parecer do auditor por documento da CVM: opinião, ênfase e continuidade operacional (série T, T2).

Fonte: os CSVs `dfp_cia_aberta_parecer_AAAA` (desde 2010) e `itr_cia_aberta_parecer_AAAA` (desde 2011), nos
mesmos zips do DFP e do ITR que o arquivista já guarda; a data de entrega vem do arquivo principal do
zip (`DT_RECEB`), ligado pela chave (CNPJ, referência, versão). Duas tabelas com o mesmo formato:
`pareceres_dfp` (relatório do auditor independente) e `pareceres_itr` (relatório da revisão especial).

- **Opinião** é campo da CVM (`TP_RELAT_AUD` no DFP, `TP_RELAT_ESP` no ITR); "Negativa de Opinião" é
  `abstencao`. Vazio (parte do DFP de 2010) ou texto novo da CVM fica `nao_classificado`.
- **Ênfase** e **continuidade operacional** não têm campo: saem do texto livre, só por títulos que o
  auditor escreve (NBC TA 570 e 706). A palavra solta não vale: o texto padrão de toda opinião fala em
  "continuidade operacional" e "incerteza relevante" nas responsabilidades. O que não dá para decidir
  fica `nao_classificado` (relatório curto demais, "chamamos a atenção" sem título de ênfase, título
  "Continuidade operacional" que pode ser só assunto principal de auditoria), nunca `sim` ou `nao` no chute.
- Só entra o relatório do auditor: a declaração dos diretores, o parecer do conselho fiscal e o resumo do
  comitê de auditoria ficam de fora, e o texto do relatório não é guardado (só a classificação), o que
  também deixa de fora nomes de pessoas. A firma não está neste CSV: liga-se a `auditores` por CNPJ e data.
"""

import io
import re
import unicodedata
import zipfile
from datetime import date

import pandas as pd

CODIFICACAO_DA_CVM = "latin-1"
COLUNAS = (
    "cnpj", "empresa", "referencia", "versao", "id_documento", "disponivel_em", "opiniao",
    "enfase", "continuidade_operacional", "caracteres_do_relatorio",
)  # fmt: skip
SIM, NAO, NAO_CLASSIFICADO = "sim", "nao", "nao_classificado"
# abaixo disso o "relatório" é só um anexo ou um aviso: não dá para dizer que não tem ênfase
MINIMO_DE_CARACTERES = 800
OPINIOES = {
    "sem ressalva": "sem_ressalva",
    "com ressalva": "com_ressalva",
    "adverso": "adversa",
    "negativa de opiniao": "abstencao",
}
# o início do tipo de parecer, sem acento e em minúsculas, que é o relatório do auditor
RELATORIOS = ("relatorio do auditor independente", "relatorio da revisao especial")
CHAVE = ["CNPJ_CIA", "DT_REFER", "VERSAO"]
# títulos, no texto sem acento e com a caixa original: "Ênfase", "Ênfases", "Ênfase - Reapresentação"
# (a "ênfase" de uma frase corrida, como "com ênfase nas operações", vem em minúsculas)
ENFASE = re.compile(r"\bEnfases?(?![a-z])|\bENFASES?\b")
CONTINUIDADE = re.compile(
    r"incerteza\s+(?:relevante\s+)?(?:relacionada|quanto|sobre)\b[^.]{0,40}continuidade",
    re.IGNORECASE,
)
CONTINUIDADE_SO_NO_TITULO = re.compile(r"\bContinuidade operacional")
CHAMAMOS_A_ATENCAO = re.compile(r"chamamos\s+(?:a\s+)?atencao", re.IGNORECASE)


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def classificar_texto(texto: str) -> tuple[str, str]:
    """(ênfase, continuidade operacional) de um relatório do auditor: `sim`, `nao` ou `nao_classificado`."""
    simples = _sem_acento(texto)
    if len(simples) < MINIMO_DE_CARACTERES:
        return NAO_CLASSIFICADO, NAO_CLASSIFICADO
    continuidade = bool(CONTINUIDADE.search(simples))
    if continuidade:
        continuidade_do_texto = SIM
    elif CONTINUIDADE_SO_NO_TITULO.search(simples):
        continuidade_do_texto = NAO_CLASSIFICADO
    else:
        continuidade_do_texto = NAO
    if ENFASE.search(simples):
        enfase = SIM
    elif CHAMAMOS_A_ATENCAO.search(simples) and not continuidade:
        enfase = NAO_CLASSIFICADO
    else:
        enfase = NAO
    return enfase, continuidade_do_texto


def _opiniao(tipo: object) -> str:
    return OPINIOES.get(_sem_acento(str(tipo)).strip().lower(), NAO_CLASSIFICADO)


def _ler(arquivo: zipfile.ZipFile, trecho: str) -> pd.DataFrame:
    nome = next(n for n in arquivo.namelist() if trecho in n)
    return pd.read_csv(
        arquivo.open(nome), sep=";", encoding=CODIFICACAO_DA_CVM, dtype=str,
        keep_default_na=False,
    )  # fmt: skip


def _entregas(principal: pd.DataFrame) -> pd.DataFrame:
    """A primeira entrega de cada (CNPJ, referência, versão): o `DT_RECEB` mais cedo e o documento dele."""
    entregas = principal.assign(
        disponivel_em=pd.to_datetime(principal["DT_RECEB"], errors="coerce").dt.date,
        id_documento=principal["ID_DOC"].str.strip(),
    ).dropna(subset=["disponivel_em"])
    return entregas.sort_values("disponivel_em", kind="stable").drop_duplicates(CHAVE)[
        [*CHAVE, "disponivel_em", "id_documento"]
    ]


def _relatorios(parecer: pd.DataFrame, coluna_da_opiniao: str) -> pd.DataFrame:
    """Uma linha por documento com relatório do auditor: opinião, o texto inteiro e o nome da empresa."""
    tipo = parecer["TP_PARECER_DECL"].map(_sem_acento).str.strip().str.lower()
    relatorio = parecer[tipo.str.startswith(RELATORIOS)].copy()
    relatorio["item"] = pd.to_numeric(
        relatorio["NUM_ITEM_PARECER_DECL"], errors="coerce"
    )
    relatorio["opiniao"] = relatorio[coluna_da_opiniao].map(_opiniao)
    relatorio = relatorio.sort_values("item", kind="stable")
    return (
        relatorio.groupby(CHAVE, sort=False)
        .agg(
            empresa=("DENOM_CIA", "last"),
            texto=("TXT_PARECER_DECL", " ".join),
            opiniao=("opiniao", lambda o: next((x for x in o if x != NAO_CLASSIFICADO), NAO_CLASSIFICADO)),
        )
        .reset_index()
    )  # fmt: skip


def _ler_pareceres(
    conteudo_do_zip: bytes, trecho_principal: str, coluna_da_opiniao: str
) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        parecer = _ler(arquivo, "_parecer_")
        principal = _ler(arquivo, trecho_principal)
    if parecer.empty:
        return pd.DataFrame(columns=list(COLUNAS))
    documentos = _relatorios(parecer, coluna_da_opiniao).merge(
        _entregas(principal), on=CHAVE, how="inner"
    )
    classes = documentos["texto"].map(classificar_texto)
    tabela = pd.DataFrame(
        {
            "cnpj": documentos["CNPJ_CIA"].str.strip(),
            "empresa": documentos["empresa"].str.strip(),
            "referencia": pd.to_datetime(
                documentos["DT_REFER"], errors="coerce"
            ).dt.date,
            "versao": pd.to_numeric(documentos["VERSAO"], errors="coerce"),
            "id_documento": documentos["id_documento"],
            "disponivel_em": documentos["disponivel_em"],
            "opiniao": documentos["opiniao"],
            "enfase": classes.str[0],
            "continuidade_operacional": classes.str[1],
            "caracteres_do_relatorio": documentos["texto"].str.len(),
        }
    )
    return tabela[list(COLUNAS)].reset_index(drop=True)


def ler_pareceres_do_dfp(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os relatórios do auditor independente de um arquivo anual do DFP."""
    return _ler_pareceres(conteudo_do_zip, "dfp_cia_aberta_2", "TP_RELAT_AUD")


def ler_pareceres_do_itr(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os relatórios da revisão especial de um arquivo anual do ITR."""
    return _ler_pareceres(conteudo_do_zip, "itr_cia_aberta_2", "TP_RELAT_ESP")


def entregues_ate(tabela: pd.DataFrame, data: date) -> pd.DataFrame:
    """O que se sabia em `data`: cada linha só depende do próprio documento, então cortar antes ou depois dá o mesmo."""
    return tabela[tabela["disponivel_em"] <= data].reset_index(drop=True)
