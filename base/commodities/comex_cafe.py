"""Exportações de café por NCM, UF de origem e país de destino, recortadas do Comex Stat (café, PR 6).

O arquivista já guarda os CSVs de exportação do Comex (`EXP_AAAA.csv`) e a tabela de países. Aqui só
se recortam as NCMs do café. A NCM **não separa arábica de conilon**: o `tipo` é sempre "total", e o
Espírito Santo (quase só conilon) vai marcado como pista (`proxy_conilon`), sem dividir o volume.

`divulgado_em` é a data da coleta do arquivista (ADR 0024): o MDIC revisa meses antigos, então cada
coleta vira linhas novas e `como_estava_em` devolve só o que já estava guardado em D.
"""

import io
from datetime import date

import pandas as pd

from base.setoriais import prazos

FONTE = "comexstat"
CODIFICACAO = "latin-1"
NCMS_DO_CAFE = ("09011110", "09011190", "09012100", "21011110")
KG_POR_SACA = 60
TIPO = "total"
UF_PROXY_DE_CONILON = "ES"
CHAVE = ["competencia", "ncm", "uf_origem", "codigo_do_pais"]
COLUNAS = (
    "competencia", "ncm", "uf_origem", "codigo_do_pais", "pais_destino", "vl_fob_usd",
    "kg_liquido", "sacas", "tipo", "proxy_conilon", "divulgado_em",
)  # fmt: skip


def recortar_cafe(comex: pd.DataFrame) -> pd.DataFrame:
    """As NCMs do café do CSV de exportação do Comex (colunas `CO_*` como texto), somando as vias."""
    cafe = comex[comex["CO_NCM"].isin(NCMS_DO_CAFE)]
    tabela = pd.DataFrame(
        {
            "competencia": prazos.fim_do_mes(cafe["CO_ANO"], cafe["CO_MES"]),
            "ncm": cafe["CO_NCM"],
            "uf_origem": cafe["SG_UF_NCM"],
            "codigo_do_pais": cafe["CO_PAIS"],
            "vl_fob_usd": pd.to_numeric(cafe["VL_FOB"]).astype(float),
            "kg_liquido": pd.to_numeric(cafe["KG_LIQUIDO"]).astype(float),
        }
    )
    soma = tabela.groupby(CHAVE, as_index=False).sum()
    soma["sacas"] = soma["kg_liquido"] / KG_POR_SACA
    soma["tipo"] = TIPO
    soma["proxy_conilon"] = soma["uf_origem"] == UF_PROXY_DE_CONILON
    return soma


def _ler_csv(conteudo: bytes) -> pd.DataFrame:
    return pd.read_csv(
        io.BytesIO(conteudo),
        sep=";",
        encoding=CODIFICACAO,
        dtype=str,
        keep_default_na=False,
    )


def ler(exportacao: bytes, paises: bytes, coletado_em: date) -> pd.DataFrame:
    """O café de um `EXP_AAAA.csv` com o nome do país (da tabela `PAIS.csv`) e a data da coleta."""
    nomes = _ler_csv(paises).set_index("CO_PAIS")["NO_PAIS"]
    tabela = recortar_cafe(_ler_csv(exportacao))
    tabela["pais_destino"] = tabela["codigo_do_pais"].map(nomes)
    tabela["divulgado_em"] = pd.Timestamp(coletado_em)
    return tabela.reindex(columns=list(COLUNAS))


def como_estava_em(tabela: pd.DataFrame, dia: date) -> pd.DataFrame:
    """Só o que o arquivista já tinha coletado até `dia`, a versão mais recente de cada linha."""
    visivel = tabela[tabela["divulgado_em"] <= pd.Timestamp(dia)]
    ultima = visivel.sort_values("divulgado_em").drop_duplicates(CHAVE, keep="last")
    return ultima.reset_index(drop=True)
