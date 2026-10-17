"""Controladas e coligadas de cada companhia aberta, pelo FRE da CVM (série B13).

O FRE traz, de 2010 a 2026, a tabela `participacao_sociedade`: para cada companhia, as sociedades em
que ela tem participação, com CNPJ, razão social, tipo (controlada ou coligada) e a porcentagem. É a
ponte entre quem os reguladores enxergam (a Ipiranga, a Hapvida Assistência Médica, a Rumo Malha
Paulista) e a companhia listada (Ultrapar, Hapvida, Rumo): `base/empresa_serie.py`.

- `conhecido_em` = data de entrega do documento à CVM (`DT_RECEB` do arquivo principal do FRE,
  ligado pelo `ID_DOC`), como em `base/auditores.py`; de cada documento fica a versão mais nova.
- O CNPJ da sociedade vem às vezes como número ("8884213000135.0"); sociedade sem CNPJ (de fora do
  país) fica com `cnpj` vazio.
- Só dado de pessoa jurídica: a tabela não tem pessoas.
"""

import io
import re
import zipfile

import pandas as pd

from base import fre
from base.cnpj import normalizar_cnpj

COLUNAS = (
    "cnpj_companhia", "companhia", "referencia", "versao", "id_documento", "conhecido_em",
    "cnpj", "razao_social", "tipo", "participacao",
)  # fmt: skip
PRINCIPAL = re.compile(r"^fre_cia_aberta_\d{4}\.csv$")


def cnpj14(valor: object) -> str | None:
    """O CNPJ com 14 caracteres ("00.000.000/0001-91", 8884213000135.0 ou com letras); senão None.

    É o `base.cnpj.normalizar_cnpj` (o nome fica porque a base inteira o usa).
    """
    return normalizar_cnpj(valor)


def _entregas(conteudo_do_zip: bytes) -> dict[str, str]:
    """`ID_DOC` -> `DT_RECEB` do arquivo principal do FRE."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nome = next((n for n in arquivo.namelist() if PRINCIPAL.match(n)), None)
        if nome is None:
            return {}
        principal = pd.read_csv(
            arquivo.open(nome), sep=";", encoding=fre.CODIFICACAO_DA_CVM, dtype=str,
            keep_default_na=False,
        )  # fmt: skip
    return dict(
        zip(principal["ID_DOC"].str.strip(), principal["DT_RECEB"], strict=True)
    )


def ler_controladas_do_fre(conteudo_do_zip: bytes) -> pd.DataFrame:
    """As participações em sociedades de um arquivo anual do FRE, com a data de entrega."""
    bruto = fre._ler(conteudo_do_zip, "participacao_sociedade")
    if bruto.empty:
        return pd.DataFrame(columns=list(COLUNAS))
    entregue = _entregas(conteudo_do_zip)
    documento = bruto["ID_Documento"].str.strip()
    tabela = pd.DataFrame(
        {
            "cnpj_companhia": bruto["CNPJ_Companhia"].map(cnpj14),
            "companhia": bruto["Nome_Companhia"].str.strip(),
            "referencia": pd.to_datetime(
                bruto["Data_Referencia"], errors="coerce"
            ).dt.date,
            "versao": bruto["Versao"],
            "id_documento": documento,
            "conhecido_em": pd.to_datetime(
                documento.map(entregue), errors="coerce"
            ).dt.date,
            "cnpj": bruto["CNPJ"].map(cnpj14),
            "razao_social": bruto["Razao_Social"].str.strip(),
            "tipo": bruto["Tipo_Sociedade"].str.strip().str.lower(),
            "participacao": pd.to_numeric(
                bruto["Participacao_Emissor"], errors="coerce"
            ),
        }
    )
    ligadas = tabela.dropna(subset=["cnpj_companhia"]).reset_index(drop=True)
    return pd.DataFrame(ligadas[list(COLUNAS)])
