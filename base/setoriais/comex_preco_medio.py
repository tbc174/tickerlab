"""Preço médio do Comex Stat (série T, PR T8): o valor FOB por quilo de cada produto (NCM) que entra ou sai
de cada porto ou recinto (URF), mês a mês, derivado dos CSVs `EXP_AAAA.csv` e `IMP_AAAA.csv` do MDIC que
o arquivista já guarda (a fonte não publica preço; ele é conta nossa: FOB ÷ quilo líquido).

Uso interno até a licença do MDIC (a família `comexstat` está "a confirmar" em `src/banco/coletas.py`;
a marca da tabela vem de lá, não de uma lista aqui): fora da exportação e do app público.

- Uma linha por fluxo (`exportacao` ou `importacao`), mês, NCM e URF: as vias, os países e as UFs de
  cada linha da fonte são somados. Quilo zero deixa o preço vazio (vazio não é zero).
- O MDIC publica o mês seguinte nos primeiros dias úteis do outro mês e revisa meses passados. Como em
  `prazos.disponivel_mensal`, a regra usa 60 dias depois do fim do mês (folga; pode atrasar, nunca
  adiantar), e a revisão vale desde o dia da coleta (`base/setoriais/revisoes.py`).
- O nome da URF está em `URF.csv` (outra tabela da fonte): a tabela guarda só o código.
"""

import io
import re

import pandas as pd

from base.setoriais import prazos

FONTE = "comexstat"
CODIFICACAO = "latin-1"
ARQUIVO = re.compile(r"/ncm/(EXP|IMP)_(\d{4})\.csv$")
FLUXOS = {"EXP": "exportacao", "IMP": "importacao"}
COLUNAS = (
    "fluxo", "competencia", "ncm", "urf", "vl_fob_usd", "kg_liquido", "preco_usd_por_kg",
    "disponivel_em",
)  # fmt: skip
CHAVE = ("fluxo", "competencia", "ncm", "urf")
CARIMBOS: tuple[str, ...] = ()
LEITURA = ["CO_ANO", "CO_MES", "CO_NCM", "CO_URF", "KG_LIQUIDO", "VL_FOB"]


def destino(url: str) -> str | None:
    """O nome do Parquet de cada arquivo (`exportacao_2026`); os `_MUN` e os totais ficam de fora."""
    if not (achado := ARQUIVO.search(url)):
        return None
    return f"{FLUXOS[achado.group(1)]}_{achado.group(2)}"


def ler(conteudo: bytes, url: str) -> pd.DataFrame:
    """Um CSV anual de exportação ou importação, somado por mês, NCM e URF, com o preço por quilo."""
    achado = ARQUIVO.search(url)
    if achado is None:
        raise ValueError(f"endereço que não é de um CSV de NCM do Comex: {url}")
    bruto = pd.read_csv(
        io.BytesIO(conteudo),
        sep=";",
        dtype=str,
        encoding=CODIFICACAO,
        usecols=LEITURA,
        keep_default_na=False,
    )
    tabela = pd.DataFrame(
        {
            "competencia": prazos.fim_do_mes(bruto["CO_ANO"], bruto["CO_MES"]),
            "ncm": bruto["CO_NCM"],
            "urf": bruto["CO_URF"],
            "vl_fob_usd": pd.to_numeric(bruto["VL_FOB"]).astype(float),
            "kg_liquido": pd.to_numeric(bruto["KG_LIQUIDO"]).astype(float),
        }
    )
    soma = tabela.groupby(["competencia", "ncm", "urf"], as_index=False).sum()
    soma.insert(0, "fluxo", FLUXOS[achado.group(1)])
    soma["preco_usd_por_kg"] = soma["vl_fob_usd"] / soma["kg_liquido"].where(
        soma["kg_liquido"] > 0
    )
    soma["disponivel_em"] = prazos.disponivel_mensal(soma["competencia"])
    return soma.reindex(columns=list(COLUNAS))
