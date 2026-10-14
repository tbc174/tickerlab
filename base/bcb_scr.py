"""SCR.data do Banco Central: carteira de crédito, atraso e inadimplência por UF, segmento, tipo de
cliente, CNAE (PJ) ou ocupação (PF), porte, modalidade, origem e indexador, por mês (série 3 da base
de ML, PR 7).

- **Versão 2** (`https://www.bcb.gov.br/pda/desig/scrdata_<ano>.zip`), licença ODbL, de jul/2012 em
  diante, um CSV por mês. A versão 1 (`planilha_<ano>.zip`) parou em jun/2025 e fica fora.
- **Formato** (inventário de 14/10/2026): UTF-8 com BOM, `;`, tudo entre aspas (há CNAE com `;` no
  nome), vírgula decimal, 24 colunas iguais em 2012 e 2026; ~210 mil linhas por mês em 2012, ~310 mil
  em 2026. Valores em reais. `numero_de_operacoes` = -1 quando o BC não informa: vira vazio.
- **Agregado:** não há pessoa nem instituição identificada.
- **"Como era na data":** o BC publica 30 dias depois do fim do mês, no último dia útil (ago/2026 já
  estava no arquivo em 09/10); a base usa data-base + 60 dias. O BC regrava anos passados (o de 2025
  em set/2026): cada regravação vira versão.
"""

import io
import zipfile

import pandas as pd

ENDERECO = "https://www.bcb.gov.br/pda/desig/scrdata_{ano}.zip"
PRIMEIRO_ANO = 2012
DIAS_ATE_FICAR_PUBLICO = 60
SEM_NUMERO = -1
COLUNAS_DE_TEXTO = (
    "data_base",
    "uf",
    "segmento",
    "cliente",
    "cnae_ocupacao",
    "porte",
    "modalidade",
    "submodalidade",
    "origem",
    "indexador",
)


def endereco_do_ano(ano: int) -> str:
    return ENDERECO.format(ano=ano)


def _ler_mes(arquivo: zipfile.ZipFile, nome: str) -> pd.DataFrame:
    bruto = pd.read_csv(
        arquivo.open(nome),
        sep=";",
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    )
    mes = pd.DataFrame({"data_base": pd.to_datetime(bruto["data_base"])})
    for coluna in COLUNAS_DE_TEXTO[1:]:
        mes[coluna] = bruto[coluna].replace("", None).astype("category")
    for coluna in bruto.columns.difference(COLUNAS_DE_TEXTO, sort=False):
        mes[coluna] = pd.to_numeric(bruto[coluna].str.replace(",", ".", regex=False))
    mes["numero_de_operacoes"] = (
        mes["numero_de_operacoes"].astype("Int64").mask(lambda n: n == SEM_NUMERO)
    )
    return mes


def ler_ano(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os meses do arquivo de um ano, um embaixo do outro, com os tipos certos."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        meses = [_ler_mes(arquivo, nome) for nome in sorted(arquivo.namelist())]
    ano = pd.concat(meses, ignore_index=True)
    for coluna in COLUNAS_DE_TEXTO[1:]:
        ano[coluna] = ano[coluna].astype(str).replace("None", None).astype("category")
    return ano


def disponivel_em(tabela: pd.DataFrame) -> pd.Series:
    """Desde quando o mês era público: data-base + 60 dias (o BC publica em ~30 a 40)."""
    return tabela["data_base"] + pd.Timedelta(days=DIAS_ATE_FICAR_PUBLICO)
