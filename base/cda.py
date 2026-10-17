"""Carteiras dos fundos desde 2005, "como era na data" (série 3 da base de ML, PR 4; pedido 1 da
sessão "FactSet").

Lê o bloco de ações do CDA (`cda_fi_BLC_4_*.csv`) dos arquivos anuais (2005–2022) e mensais (2023
em diante). O inventário de 14/10/2026 achou as mesmas 21 colunas de 2005 a 2022; na CVM 175 só
mudam `CNPJ_FUNDO` → `CNPJ_FUNDO_CLASSE` e `TP_FUNDO` → `TP_FUNDO_CLASSE`. Os tipos de posição
(comprado, emprestado, vendido) e a codificação são os do app (`src/fundos_cvm.py`), para a tela e a
base dizerem o mesmo.

- **Em pedaços:** o bloco de 2022 tem 510 MB descompactado; só as colunas usadas são lidas.
- **Código permanente:** o `CD_ISIN` está em todas as linhas; o emissor sai dele (`base/fca.py`).
- **"Como era na data":** o arquivo não diz quando ficou público. A posição só vale a partir de 90
  dias depois da competência (o arquivo sai uns 40 dias depois e o sigilo pode ir a 90) ou do fim do
  sigilo (`DT_CONFID_APLIC`), o que vier depois. Regra conservadora: pode atrasar um número, nunca
  adiantar. Quem entrega atrasado só vale do dia em que a carteira apareceu na CVM (`visto_em`,
  `base/publicacao.py`).

**Bloco 8** ("demais ativos não codificados"; achado da série 4): muitos fundos informam ações da bolsa
sem o código estruturado, só com a descrição ("PETR3 - PETROBRAS") e o CNPJ do emissor. Em 2020, R$ 1,14
tri (soma dos meses) em ações de companhias com ticker, ~26% a mais sobre o bloco 4, e quase nada
repetido entre os blocos (0,9% do valor com a mesma empresa no mesmo fundo e mês). `ler_acoes_do_bloco_8`
lê as ações e os certificados de depósito com o **CNPJ que o fundo informa**: a linha de emissor pessoa
física (o bloco 8 traz o CPF) é descartada na leitura, e também a marcada como PJ cujo número pode ser
um CPF (`base/fidc.py::documento_de_empresa`).

**Bloco 2** (cotas de fundos; relatório da base de crédito, 16/10/2026): quem compra cotas de FIDC (em
jun/2026, R$ 291,8 bi de 4.531 fundos). `ler_cotas_de_fundos` lê os dois layouts do inventário de
16/10/2026 (64 arquivos, um cabeçalho por arquivo: `CNPJ_FUNDO_COTA` até 2023, `CNPJ_FUNDO_CLASSE_COTA` e
`ID_SUBCLASSE` depois), sem tratar aspas (há nomes com aspas sem fechar) e, com dois nomes para o mesmo
dado no arquivo, pelo primeiro não vazio de cada linha (lição do #333). Só fundos: nenhuma pessoa.
"""

import csv
import io
import zipfile
from collections.abc import Iterator
from datetime import date

import pandas as pd

from base.fca import emissor_do_isin
from base.fidc import documento_de_empresa
from src.detentores import COMPRADO, EMPRESTADO, VENDIDO
from src.fundos_cvm import CODIFICACAO_DA_CVM, TIPOS

TIPOS_DE_POSICAO = (COMPRADO, EMPRESTADO, VENDIDO)  # os valores da coluna `tipo`

LINHAS_POR_PEDACO = 500_000
DIAS_ATE_FICAR_PUBLICA = 90
COLUNAS = (
    "competencia", "cnpj_fundo", "tipo_do_fundo", "fundo", "tipo", "codigo", "isin", "emissor",
    "descricao", "quantidade", "valor", "compras", "vendas", "confidencial_ate",
)  # fmt: skip
# o nome de antes da CVM 175 → o de depois (o mesmo dado)
NOMES_NOVOS = {"CNPJ_FUNDO": "CNPJ_FUNDO_CLASSE", "TP_FUNDO": "TP_FUNDO_CLASSE"}
USADAS = (
    "CNPJ_FUNDO_CLASSE", "TP_FUNDO_CLASSE", "DENOM_SOCIAL", "DT_COMPTC", "TP_APLIC", "CD_ATIVO",
    "CD_ISIN", "DS_ATIVO", "QT_POS_FINAL", "VL_MERC_POS_FINAL", "VL_AQUIS_NEGOC", "VL_VENDA_NEGOC",
    "DT_CONFID_APLIC",
)  # fmt: skip


COLUNAS_DO_BLOCO_8 = (
    "competencia", "cnpj_fundo", "tipo_do_fundo", "fundo", "tipo", "tipo_do_ativo", "cnpj_emissor",
    "nome_do_emissor", "descricao", "quantidade", "valor", "compras", "vendas", "confidencial_ate",
)  # fmt: skip
USADAS_NO_BLOCO_8 = (
    "CNPJ_FUNDO_CLASSE", "TP_FUNDO_CLASSE", "DENOM_SOCIAL", "DT_COMPTC", "TP_APLIC", "TP_ATIVO",
    "DS_ATIVO", "QT_POS_FINAL", "VL_MERC_POS_FINAL", "VL_AQUIS_NEGOC", "VL_VENDA_NEGOC",
    "DT_CONFID_APLIC", "PF_PJ_EMISSOR", "CPF_CNPJ_EMISSOR", "EMISSOR",
)  # fmt: skip
PESSOA_JURIDICA = "PJ"


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").fillna(0.0)


def _texto(serie: pd.Series) -> pd.Series:
    return serie.str.strip().replace("", None)


def _do_pedaco(bruto: pd.DataFrame) -> pd.DataFrame:
    bruto = bruto.rename(columns=NOMES_NOVOS)
    bruto = bruto[bruto["TP_APLIC"].isin(TIPOS)]
    isin = _texto(bruto["CD_ISIN"])
    return pd.DataFrame(
        {
            "competencia": pd.to_datetime(bruto["DT_COMPTC"], errors="coerce"),
            "cnpj_fundo": bruto["CNPJ_FUNDO_CLASSE"].str.strip(),
            "tipo_do_fundo": _texto(bruto["TP_FUNDO_CLASSE"]),
            "fundo": bruto["DENOM_SOCIAL"].str.strip().str[:200],
            "tipo": bruto["TP_APLIC"].map(TIPOS),
            "codigo": _texto(bruto["CD_ATIVO"]),
            "isin": isin,
            "emissor": isin.map(emissor_do_isin),
            "descricao": _texto(bruto["DS_ATIVO"]),
            "quantidade": _numero(bruto["QT_POS_FINAL"]),
            "valor": _numero(bruto["VL_MERC_POS_FINAL"]),
            "compras": _numero(bruto["VL_AQUIS_NEGOC"]),
            "vendas": _numero(bruto["VL_VENDA_NEGOC"]),
            "confidencial_ate": pd.to_datetime(
                bruto["DT_CONFID_APLIC"], errors="coerce"
            ),
        }
    ).dropna(subset=["competencia"])


def ler_posicoes_historicas(
    conteudo_do_zip: bytes, tamanho: int = LINHAS_POR_PEDACO
) -> Iterator[pd.DataFrame]:
    """As posições em ações de todos os fundos num arquivo do CDA, em pedaços de `tamanho` linhas.

    Lê em fluxo de dentro do zip: o bloco descompactado (510 MB em 2022) nunca fica inteiro na memória.
    """
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nome = next(n for n in arquivo.namelist() if "_BLC_4_" in n)
        with arquivo.open(nome) as cabeca:
            cabecalho = pd.read_csv(
                cabeca, sep=";", encoding=CODIFICACAO_DA_CVM, nrows=0
            ).columns
        usadas = [c for c in cabecalho if NOMES_NOVOS.get(c, c) in USADAS]
        with arquivo.open(nome) as fluxo:
            for bruto in pd.read_csv(
                fluxo, sep=";", encoding=CODIFICACAO_DA_CVM, encoding_errors="replace",
                dtype=str, keep_default_na=False, usecols=usadas, chunksize=tamanho,
            ):  # fmt: skip
                yield _do_pedaco(bruto).reset_index(drop=True)[list(COLUNAS)]


def _acoes_do_pedaco_do_bloco_8(bruto: pd.DataFrame) -> pd.DataFrame:
    bruto = bruto.rename(columns=NOMES_NOVOS)
    # pessoa física (CPF) sai aqui, antes de qualquer outra coluna ser lida
    pj = bruto[bruto["PF_PJ_EMISSOR"].str.strip().eq(PESSOA_JURIDICA)]
    cnpj = pj["CPF_CNPJ_EMISSOR"].map(documento_de_empresa)
    pj = pj.assign(_cnpj=cnpj)[pj["TP_APLIC"].isin(TIPOS) & cnpj.notna()]
    return pd.DataFrame(
        {
            "competencia": pd.to_datetime(pj["DT_COMPTC"], errors="coerce"),
            "cnpj_fundo": pj["CNPJ_FUNDO_CLASSE"].str.strip(),
            "tipo_do_fundo": _texto(pj["TP_FUNDO_CLASSE"]),
            "fundo": pj["DENOM_SOCIAL"].str.strip().str[:200],
            "tipo": pj["TP_APLIC"].map(TIPOS),
            "tipo_do_ativo": _texto(pj["TP_ATIVO"]),
            "cnpj_emissor": pj["_cnpj"],
            "nome_do_emissor": _texto(pj["EMISSOR"]).str[:200],
            "descricao": _texto(pj["DS_ATIVO"]),
            "quantidade": _numero(pj["QT_POS_FINAL"]),
            "valor": _numero(pj["VL_MERC_POS_FINAL"]),
            "compras": _numero(pj["VL_AQUIS_NEGOC"]),
            "vendas": _numero(pj["VL_VENDA_NEGOC"]),
            "confidencial_ate": pd.to_datetime(pj["DT_CONFID_APLIC"], errors="coerce"),
        }
    ).dropna(subset=["competencia"])


def ler_acoes_do_bloco_8(
    conteudo_do_zip: bytes, tamanho: int = LINHAS_POR_PEDACO
) -> Iterator[pd.DataFrame]:
    """As ações e os certificados de depósito do bloco 8, com o CNPJ do emissor que o fundo informa,
    em pedaços (nada, se o arquivo não tem o bloco 8). Pessoa física nunca entra."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nome = next((n for n in arquivo.namelist() if "_BLC_8_" in n), None)
        if nome is None:
            return
        with arquivo.open(nome) as cabeca:
            cabecalho = pd.read_csv(
                cabeca, sep=";", encoding=CODIFICACAO_DA_CVM, nrows=0
            ).columns
        usadas = [c for c in cabecalho if NOMES_NOVOS.get(c, c) in USADAS_NO_BLOCO_8]
        with arquivo.open(nome) as fluxo:
            for bruto in pd.read_csv(
                fluxo, sep=";", encoding=CODIFICACAO_DA_CVM, encoding_errors="replace",
                dtype=str, keep_default_na=False, usecols=usadas, chunksize=tamanho,
                quoting=csv.QUOTE_NONE,
            ):  # fmt: skip
                yield _acoes_do_pedaco_do_bloco_8(bruto).reset_index(drop=True)[
                    list(COLUNAS_DO_BLOCO_8)
                ]


def _chaves_do_csv(arquivo: zipfile.ZipFile, nome: str) -> pd.DataFrame:
    with arquivo.open(nome) as cabeca:
        cabecalho = pd.read_csv(
            cabeca, sep=";", encoding=CODIFICACAO_DA_CVM, nrows=0
        ).columns
    usadas = [
        c
        for c in cabecalho
        if NOMES_NOVOS.get(c, c) in ("CNPJ_FUNDO_CLASSE", "DT_COMPTC")
    ]
    partes = []
    with arquivo.open(nome) as fluxo:
        for bruto in pd.read_csv(
            fluxo, sep=";", encoding=CODIFICACAO_DA_CVM, encoding_errors="replace",
            dtype=str, keep_default_na=False, usecols=usadas, chunksize=LINHAS_POR_PEDACO,
        ):  # fmt: skip
            bruto = bruto.rename(columns=NOMES_NOVOS)
            partes.append(
                pd.DataFrame(
                    {
                        "competencia": pd.to_datetime(
                            bruto["DT_COMPTC"], errors="coerce"
                        ),
                        "cnpj_fundo": bruto["CNPJ_FUNDO_CLASSE"].str.strip(),
                    }
                ).drop_duplicates()
            )
    return pd.concat(partes, ignore_index=True)


def chaves_do_cda(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os fundos de cada mês do arquivo (`competencia`, `cnpj_fundo`): do arquivo de PL (um fundo por
    linha, ~3 MB) ou, sem ele, do bloco 4. De cada versão guardada sai o dia em que a carteira
    apareceu na CVM (`base/publicacao.py`)."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nomes = arquivo.namelist()
        nome = next((n for n in nomes if "_PL_" in n), None) or next(
            n for n in nomes if "_BLC_4_" in n
        )
        chaves = _chaves_do_csv(arquivo, nome)
    chaves = chaves.dropna().drop_duplicates()
    return chaves[chaves["cnpj_fundo"] != ""].reset_index(drop=True)


def disponivel_em(posicoes: pd.DataFrame) -> pd.Series:
    """Desde quando cada posição era pública: competência + 90 dias, ou o fim do sigilo se depois."""
    prazo = posicoes["competencia"] + pd.Timedelta(days=DIAS_ATE_FICAR_PUBLICA)
    return pd.concat([prazo, posicoes["confidencial_ate"]], axis=1).max(axis=1)


def como_era_em(posicoes: pd.DataFrame, data: date) -> pd.DataFrame:
    """Só as posições que já eram públicas em `data` (a coluna `disponivel_em` precisa existir)."""
    return posicoes[posicoes["disponivel_em"] <= pd.Timestamp(data)]


# --- bloco 2: as cotas de fundos que cada fundo tem (relatório da base de crédito, 16/10/2026)
COLUNAS_DAS_COTAS = (
    "competencia", "cnpj_fundo", "tipo_do_fundo", "tipo_do_ativo", "emissor_ligado",
    "cnpj_fundo_investido", "id_subclasse", "quantidade", "valor", "compras", "vendas",
    "confidencial_ate",
)  # fmt: skip
# cada dado → os nomes que ele já teve no arquivo (o da CVM 175 primeiro); vale o primeiro não vazio.
# Os nomes dos fundos e o tipo de aplicação ("Cotas de Fundos" em 99,9% das linhas) ficam de fora: os
# nomes estão no cadastro de fundos e, em 2022 (2,2 mi de linhas), a gravação passava de 2 GB de memória
# no servidor de casa (8 GB para tudo)
NOMES_NO_BLOCO_2 = {
    "CNPJ_FUNDO_CLASSE": ("CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO"),
    "TP_FUNDO_CLASSE": ("TP_FUNDO_CLASSE", "TP_FUNDO"),
    "DT_COMPTC": ("DT_COMPTC",),
    "TP_ATIVO": ("TP_ATIVO",),
    "EMISSOR_LIGADO": ("EMISSOR_LIGADO",),
    "CNPJ_COTA": ("CNPJ_FUNDO_CLASSE_COTA", "CNPJ_FUNDO_COTA"),
    "ID_SUBCLASSE": ("ID_SUBCLASSE",),
    "QT_POS_FINAL": ("QT_POS_FINAL",),
    "VL_MERC_POS_FINAL": ("VL_MERC_POS_FINAL",),
    "VL_AQUIS_NEGOC": ("VL_AQUIS_NEGOC",),
    "VL_VENDA_NEGOC": ("VL_VENDA_NEGOC",),
    "DT_CONFID_APLIC": ("DT_CONFID_APLIC",),
}
SIM_OU_NAO = {"S": True, "N": False}


def _primeira_preenchida(bruto: pd.DataFrame, nomes: tuple[str, ...]) -> pd.Series:
    """O primeiro nome não vazio de cada linha (lição do #333: nunca só a primeira coluna)."""
    valores = pd.Series(
        None, index=bruto.index, dtype="str"
    )  # texto compacto: 2022 tem 2,2 mi de linhas
    for nome in nomes:
        if nome in bruto.columns:
            valores = valores.fillna(_texto(bruto[nome]))
    return valores


def _cotas_do_pedaco(bruto: pd.DataFrame) -> pd.DataFrame:
    campo = {
        dado: _primeira_preenchida(bruto, nomes)
        for dado, nomes in NOMES_NO_BLOCO_2.items()
    }
    return pd.DataFrame(
        {
            "competencia": pd.to_datetime(campo["DT_COMPTC"], errors="coerce"),
            "cnpj_fundo": campo["CNPJ_FUNDO_CLASSE"],
            "tipo_do_fundo": campo["TP_FUNDO_CLASSE"],
            "tipo_do_ativo": campo["TP_ATIVO"],
            "emissor_ligado": campo["EMISSOR_LIGADO"].map(SIM_OU_NAO).astype("boolean"),
            "cnpj_fundo_investido": campo["CNPJ_COTA"],
            "id_subclasse": campo["ID_SUBCLASSE"],
            "quantidade": _numero(campo["QT_POS_FINAL"]),
            "valor": _numero(campo["VL_MERC_POS_FINAL"]),
            "compras": _numero(campo["VL_AQUIS_NEGOC"]),
            "vendas": _numero(campo["VL_VENDA_NEGOC"]),
            "confidencial_ate": pd.to_datetime(
                campo["DT_CONFID_APLIC"], errors="coerce"
            ),
        }
    ).dropna(
        subset=["competencia"]
    )  # um cabeçalho repetido no meio do arquivo sai aqui


def ler_cotas_de_fundos(
    conteudo_do_zip: bytes, tamanho: int = LINHAS_POR_PEDACO
) -> Iterator[pd.DataFrame]:
    """As cotas de fundos que cada fundo tem (bloco 2 do CDA), em pedaços (nada, se o arquivo não tem
    o bloco 2). Lido sem tratar aspas: os nomes têm aspas sem fechar."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nome = next((n for n in arquivo.namelist() if "_BLC_2_" in n), None)
        if nome is None:
            return
        with arquivo.open(nome) as cabeca:
            cabecalho = pd.read_csv(
                cabeca,
                sep=";",
                encoding=CODIFICACAO_DA_CVM,
                nrows=0,
                quoting=csv.QUOTE_NONE,
            ).columns
        conhecidos = {n for nomes in NOMES_NO_BLOCO_2.values() for n in nomes}
        usadas = [c for c in cabecalho if c in conhecidos]
        with arquivo.open(nome) as fluxo:
            for bruto in pd.read_csv(
                fluxo, sep=";", encoding=CODIFICACAO_DA_CVM, encoding_errors="replace",
                dtype=str, keep_default_na=False, usecols=usadas, chunksize=tamanho,
                quoting=csv.QUOTE_NONE,
            ):  # fmt: skip
                yield _cotas_do_pedaco(bruto).reset_index(drop=True)[
                    list(COLUNAS_DAS_COTAS)
                ]
