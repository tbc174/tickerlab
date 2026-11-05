"""SIGSIF do MAPA (B2 da rodada de fontes de 03/11/2026): estabelecimentos sob inspeção federal.

Três arquivos do CKAN do MAPA (CC BY, mensais, UTF-8, separador `;`):

- **estabelecimentos registrados** (`estabelecimentos_registrados`): a única fonte do CNPJ. A coluna
  `CPF_CNPJ` mistura pessoa física e jurídica, e o CPF aparece até mascarado: a linha que não tem um CNPJ de
  14 caracteres é **descartada antes de gravar**, com a razão social dela. O CPF que vem no fim da razão
  social de um MEI sai também (`tirar_cpf_da_coluna`, ADR 0106). Telefone, e-mail, endereço e nome
  fantasia não são copiados. O número do SIF repete por categoria, então a chave é CNPJ + SIF + categoria.
- **habilitados à exportação** (`habilitados_exportacao`): não tem CNPJ. Liga pelo **número do SIF**, nunca pelo
  nome (o nome da habilitação difere do cadastro). SIF desconhecido, ou ligado a mais de um CNPJ, fica sem CNPJ.
- **abates** (`abates_condenacoes`): agregado por mês, UF e categoria. Não tem empresa e **não é atribuído a
  nenhuma**.

**Sem olhar o futuro:** a fonte não dá a data de divulgação da linha; `disponivel_em` é a data da coleta.

Licença CC BY, com atribuição em todo lugar que mostra o dado (`ATRIBUICAO`). Sem Streamlit; pandas só.
"""

import io
from datetime import date

import pandas as pd

from base import cnpj
from base.pessoas.sem_cpf import tirar_cpf_da_coluna

FONTE = "mapa-sigsif"
ATRIBUICAO = (
    "Fonte: Ministério da Agricultura e Pecuária (MAPA), Serviço de Inspeção Federal (SIGSIF), CC BY, "
    "https://dados.agricultura.gov.br/dataset/servico-de-inspecao-federal-sif"
)
COLUNAS_DOS_REGISTRADOS = (
    "cnpj", "razao_social", "nr_sif", "situacao", "municipio", "uf", "area_categoria",
    "categoria_classe", "disponivel_em",
)  # fmt: skip
COLUNAS_DOS_HABILITADOS = (
    "pais", "area", "sif", "estabelecimento", "uf", "municipio", "produto", "dt_validade",
    "dt_ocorrencia", "dt_suspensao", "cnpj", "disponivel_em",
)  # fmt: skip
COLUNAS_DOS_ABATES = (
    "mes",
    "uf",
    "categoria",
    "machos",
    "femeas",
    "total",
    "disponivel_em",
)


def _csv(conteudo: bytes, obrigatorias: set[str]) -> pd.DataFrame:
    """O CSV todo como texto; UTF-8 e, se não for, CP1252."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252")
    tabela = pd.read_csv(io.StringIO(texto), sep=";", dtype=str, keep_default_na=False)
    tabela.columns = [c.strip().upper() for c in tabela.columns]
    faltam = obrigatorias - set(tabela.columns)
    if faltam:
        raise ValueError(f"SIGSIF: faltam colunas {sorted(faltam)}")
    return tabela


def _sif(valor: str) -> str:
    """O número do SIF sem espaços nem zeros à esquerda ("0123" e "123" são o mesmo SIF)."""
    return valor.strip().lstrip("0")


def ler_estabelecimentos(conteudo: bytes, coletado_em: date) -> pd.DataFrame:
    """Os estabelecimentos com CNPJ; CPF (mascarado ou não) e contato ficam de fora.

    `attrs["descartadas_sem_cnpj"]` guarda quantas linhas saíram, para a carga conferir.
    """
    bruta = _csv(conteudo, {"CPF_CNPJ", "RAZAO_SOCIAL", "NR_SIF"})
    # `completo` e não `normalizar_cnpj`: o CPF de 11 dígitos não ganha zeros e vira "CNPJ".
    cnpjs = bruta["CPF_CNPJ"].map(cnpj.completo)
    com_cnpj = cnpjs.notna()
    tabela = pd.DataFrame(
        {
            "cnpj": cnpjs[com_cnpj],
            "razao_social": tirar_cpf_da_coluna(
                bruta.loc[com_cnpj, "RAZAO_SOCIAL"].str.strip()
            ),
            "nr_sif": bruta.loc[com_cnpj, "NR_SIF"].map(_sif),
            "situacao": bruta.loc[com_cnpj, "SITUACAO"].str.strip(),
            "municipio": bruta.loc[com_cnpj, "MUNICIPIO"].str.strip(),
            "uf": bruta.loc[com_cnpj, "UF"].str.strip(),
            "area_categoria": bruta.loc[com_cnpj, "AREA_CATEGORIA"].str.strip(),
            "categoria_classe": bruta.loc[com_cnpj, "CATEGORIA_CLASSE"].str.strip(),
            "disponivel_em": pd.Timestamp(coletado_em),
        },
        columns=list(COLUNAS_DOS_REGISTRADOS),
    ).reset_index(drop=True)
    tabela.attrs["descartadas_sem_cnpj"] = int((~com_cnpj).sum())
    return tabela


def _cnpj_do_sif(registrados: pd.DataFrame) -> dict[str, str]:
    """SIF → CNPJ, só dos SIFs que têm um CNPJ único."""
    por_sif = registrados.groupby("nr_sif")["cnpj"].agg(set)
    return {sif: next(iter(c)) for sif, c in por_sif.items() if len(c) == 1}


def ler_habilitados(
    conteudo: bytes, registrados: pd.DataFrame, coletado_em: date
) -> pd.DataFrame:
    """As habilitações à exportação, com o CNPJ achado pelo número do SIF (vazio se não achar um só)."""
    bruta = _csv(conteudo, {"PAIS", "ESTABELECIMENTO", "SIF"})
    sifs = bruta["SIF"].map(_sif)
    datas = {
        coluna: pd.to_datetime(bruta[coluna].str.strip(), errors="coerce")
        for coluna in ("DT_VALIDADE", "DT_OCORRENCIA", "DT_SUSPENSAO")
    }
    return pd.DataFrame(
        {
            "pais": bruta["PAIS"].str.strip(),
            "area": bruta["AREA"].str.strip(),
            "sif": sifs,
            "estabelecimento": bruta["ESTABELECIMENTO"].str.strip(),
            "uf": bruta["UF"].str.strip(),
            "municipio": bruta["MUNICIPIO"].str.strip(),
            "produto": bruta["PRODUTO"].str.strip(),
            "dt_validade": datas["DT_VALIDADE"],
            "dt_ocorrencia": datas["DT_OCORRENCIA"],
            "dt_suspensao": datas["DT_SUSPENSAO"],
            "cnpj": sifs.map(_cnpj_do_sif(registrados)),
            "disponivel_em": pd.Timestamp(coletado_em),
        },
        columns=list(COLUNAS_DOS_HABILITADOS),
    )


def ler_abates(conteudo: bytes, coletado_em: date) -> pd.DataFrame:
    """Animais abatidos por mês, UF de procedência e categoria. Sem empresa, de propósito."""
    bruta = _csv(
        conteudo, {"MES_ANO", "UF_PROCEDENCIA", "CATEGORIA", "QTD_MACHO", "QTD_FEMEA"}
    )
    parcial = pd.DataFrame(
        {
            "mes": pd.to_datetime(bruta["MES_ANO"].str.strip(), format="%m/%Y"),
            "uf": bruta["UF_PROCEDENCIA"].str.strip(),
            "categoria": bruta["CATEGORIA"].str.strip(),
            "machos": pd.to_numeric(bruta["QTD_MACHO"], errors="coerce").fillna(0),
            "femeas": pd.to_numeric(bruta["QTD_FEMEA"], errors="coerce").fillna(0),
        }
    )
    tabela = parcial.groupby(["mes", "uf", "categoria"], as_index=False).sum()
    tabela[["machos", "femeas"]] = tabela[["machos", "femeas"]].astype("int64")
    tabela["total"] = tabela["machos"] + tabela["femeas"]
    tabela["disponivel_em"] = pd.Timestamp(coletado_em)
    return tabela[list(COLUNAS_DOS_ABATES)]
