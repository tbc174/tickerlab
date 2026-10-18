"""Informes mensais de CRI, CRA e outros títulos de securitização (OTS) da CVM, sem dado pessoal
(vertical de crédito do produto Base, ADR 0084; plano de 18/10/2026).

- **Um informe por certificado e mês** (`inf_mensal_<produto>_<ano>.zip`), um CSV por quadro (`geral`,
  `ativo_passivo`, `classe`, `cedente_devedor`...). O CRI tem quadros próprios até a Resolução CVM 60
  (`carteira`, `creditos`...); CRA e OTS seguem o modelo novo. Cada quadro vira uma tabela, no
  formato da fonte, com a chave na frente: `competencia` (o 1º dia do mês: o OTS informa o último, CRI
  e CRA o primeiro), `cnpj_securitizadora` (formatado) e `codigo_certificado`.
- **Linhas repetidas:** a CVM guarda só a última versão de cada informe, mas, se vierem duas, fica a
  de maior `Versao` (pelo número); linha repetida inteira entra uma vez. Num certificado e mês, mais de uma linha é normal em `classe` (uma por série) e em
  `cedente_devedor`; o OTS de 2026 tem até um informe entregue duas vezes com conteúdo diferente, e os
  dois ficam (não há como saber qual vale).
- **Linhas quebradas:** um `;` dentro de um campo (o CRA de 2026 tem uma) desalinha a linha; ela sai,
  contada por quadro em `Leitura.linhas_quebradas` e avisada no log, e a contagem vai para o manifesto.
- **Sem dado pessoal:** o quadro `responsavel` (nome e cargo de quem assina, CRI até 2019) fica fora;
  nas colunas de documento (`CNPJ` dos cedentes e devedores, `Retentor_Risco`, `CNPJ_*`, `CPF_*`) só
  fica CNPJ válido, formatado (`base.fidc.documento_de_empresa`: na dúvida entre CPF e CNPJ, sai); os
  campos de texto livre (garantias, contingências, impactos de pré-pagamento...), que podem citar
  avalista ou devedor pessoa física, também saem. Tudo continua bruto no acervo.
"""

import io
import logging
import re
import zipfile
from dataclasses import dataclass

import pandas as pd

from base.fidc import CODIFICACAO_DA_CVM, documento_de_empresa

log = logging.getLogger(__name__)
PRODUTOS = ("cri", "cra", "ots")
CHAVE = ("competencia", "cnpj_securitizadora", "codigo_certificado")
COLUNAS_DA_SECURITIZADORA = ("CNPJ_Emissora", "CNPJ_Securitizadora")  # o OTS usa a 2ª
COLUNA_DO_CERTIFICADO = "Codigo_Identificacao_Certificado"
COLUNA_DA_REFERENCIA = "Data_Referencia"
COLUNA_DA_VERSAO = "Versao"
QUADROS_DE_PESSOAS = ("responsavel",)
PREFIXOS_DE_DOCUMENTO = ("CNPJ", "CPF")
COLUNAS_DE_DOCUMENTO = ("Retentor_Risco",)  # documento sem o prefixo no nome
# texto livre (META da CVM: varchar de 255, preenchido à mão); categorias curtas (agência de
# rating, segmento, periodicidade) e taxas ficam
TEXTOS_LIVRES = (
    "Analise_Impacto_Demais_Fatos",
    "Analise_Impacto_Eventos_Pre_Pagamento",
    "Analise_Impacto_Outros_Eventos",
    "Contingencias_Principais_Fatos",
    "Contingencias_Valores_Envolvidos",
    "Descricao_Outros_Valores",
    "Desempenho_Emissao",
    "Detalhamento_Lastro",
    "Especificacao_Tipo_Segmento",
    "Impacto_Eventos_Pre_Pagamento",
    "Justificativa",
    "Outras_Caracteristicas",
    "Outras_Caracteristicas_Emissao",
    "Outras_Consideracoes",
    "Outras_Contigencias_Relevantes",
    "Pre_Pagamento_Impacto",
    "Principais_Caracteristicas_Lastro",
    "Recomposicao_Indice",
    "Sobrecolateralizacao",
    "Tipo_Retencao_Risco",
    "Tipos_Garantias_Coobrigacao_Securitizadora",
    "Tipos_Garantias_Coobrigacao_Terceiros",
)


@dataclass(frozen=True)
class Leitura:
    """As tabelas de um arquivo do informe (uma por quadro) e as linhas quebradas de cada quadro."""

    tabelas: dict[str, pd.DataFrame]
    linhas_quebradas: dict[str, int]


def _nome_do_quadro(produto: str) -> re.Pattern[str]:
    if produto not in PRODUTOS:
        raise ValueError(f"produto {produto!r} não é um de {PRODUTOS}")
    return re.compile(rf"inf_mensal_{produto}_([a-z_]+?)_\d{{4,6}}\.csv$")


def quadros_do_arquivo(conteudo_do_zip: bytes, produto: str) -> set[str]:
    """Os quadros (`geral`, `classe`...) que um arquivo do informe traz, sem ler os dados."""
    nome_do_quadro = _nome_do_quadro(produto)
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        quadros = {
            a.group(1) for n in arquivo.namelist() if (a := nome_do_quadro.search(n))
        }
    return quadros - set(QUADROS_DE_PESSOAS)


def _ler_csv(arquivo: zipfile.ZipFile, nome: str) -> tuple[pd.DataFrame, int]:
    """A tabela do CSV e quantas linhas quebradas (com campos a mais) ficaram de fora."""
    quebradas: list[list[str]] = []

    def guardar_quebrada(campos: list[str]) -> None:
        quebradas.append(campos)  # devolver None tira a linha da tabela

    tabela = pd.read_csv(
        arquivo.open(nome), sep=";", encoding=CODIFICACAO_DA_CVM, encoding_errors="replace",
        dtype=str, keep_default_na=False, engine="python", on_bad_lines=guardar_quebrada,
    ).replace("", None)  # fmt: skip
    return tabela, len(quebradas)


def _so_a_maior_versao(tabela: pd.DataFrame, chave: list[str]) -> pd.DataFrame:
    versao = pd.to_numeric(tabela[COLUNA_DA_VERSAO], errors="coerce").fillna(0)
    maior = versao.groupby([tabela[c] for c in chave], dropna=False).transform("max")
    return tabela[versao == maior].reset_index(drop=True)


def _e_documento(coluna: str) -> bool:
    return coluna.startswith(PREFIXOS_DE_DOCUMENTO) or coluna in COLUNAS_DE_DOCUMENTO


def _sem_pessoas(tabela: pd.DataFrame) -> pd.DataFrame:
    tabela = tabela.drop(columns=[c for c in TEXTOS_LIVRES if c in tabela.columns])
    for coluna in [c for c in tabela.columns if _e_documento(c)]:
        tabela[coluna] = tabela[coluna].map(documento_de_empresa)
    return tabela


def _com_chave(tabela: pd.DataFrame) -> pd.DataFrame:
    securitizadora = next(c for c in COLUNAS_DA_SECURITIZADORA if c in tabela.columns)
    chave_bruta = [securitizadora, COLUNA_DO_CERTIFICADO, COLUNA_DA_REFERENCIA]
    tabela = _so_a_maior_versao(tabela.drop_duplicates(), chave_bruta)
    referencia = pd.to_datetime(tabela[COLUNA_DA_REFERENCIA], errors="coerce")
    chave = pd.DataFrame(
        {
            "competencia": referencia.dt.to_period("M").dt.to_timestamp(),
            "cnpj_securitizadora": tabela[securitizadora].map(documento_de_empresa),
            "codigo_certificado": tabela[COLUNA_DO_CERTIFICADO].str.strip(),
        }
    )
    resto = tabela.drop(columns=[securitizadora, COLUNA_DO_CERTIFICADO])
    return pd.concat([chave, resto], axis=1)


def ler_informe(conteudo_do_zip: bytes, produto: str) -> Leitura:
    """Uma tabela por quadro do informe, com a chave na frente e sem dado pessoal."""
    nome_do_quadro = _nome_do_quadro(produto)
    tabelas, quebradas = {}, {}
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        for nome in sorted(arquivo.namelist()):
            achado = nome_do_quadro.search(nome)
            if not achado or achado.group(1) in QUADROS_DE_PESSOAS:
                continue
            quadro = achado.group(1)
            tabela, quantas = _ler_csv(arquivo, nome)
            tabelas[quadro] = _sem_pessoas(_com_chave(tabela))
            if quantas:
                quebradas[quadro] = quantas
                log.warning("%s: %d linha(s) quebrada(s) fora da tabela", nome, quantas)
    return Leitura(tabelas, quebradas)
