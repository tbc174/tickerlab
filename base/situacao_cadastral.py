"""B-30c: situação cadastral do CNPJ (ativa, baixada, inapta, suspensa, nula) mês a mês, com histórico.

A Receita só publica o retrato do mês; a situação "como era no dia D" nasce da sequência dos retratos
guardados, como na `cnpj_situacao_especial` (a irmã, `base/rotulos.py`): um Parquet por mês em
`<pasta>/cnpj_situacao_cadastral/<AAAA-MM>.parquet`, cada retrato valendo desde `disponivel_em` (nunca
desde o mês do arquivo, que olharia o futuro).

Só CNPJ e códigos entram (ADR 0106): nome fantasia, razão social, endereço e contatos nem são lidos; o
nome fantasia do MEI costuma ser o nome da pessoa. O código vira texto pela `base/receita_codigos.py`.
"""

import io
from datetime import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base.parquet import LINHAGEM, gravar_se_mudou
from base.receita_retrato import CAMPOS_DO_ESTABELECIMENTO, MATRIZ, _datas, _partes
from base.rotulos import MES_NA_PASTA, disponivel_em
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.versao_do_codigo import versao_do_codigo

TABELA = "cnpj_situacao_cadastral"
# posição de cada campo no arquivo de estabelecimentos (layout conferido em 15/10/2026)
POSICOES = {
    0: "cnpj_basico", 1: "ordem", 2: "dv", 3: "matriz", 5: "situacao_cadastral",
    6: "data_situacao_cadastral", 7: "motivo_situacao",
}  # fmt: skip
COLUNAS = (
    "cnpj", "cnpj_basico", "matriz", "situacao_cadastral", "data_situacao_cadastral",
    "motivo_situacao",
)  # fmt: skip
TAMANHO_DO_CODIGO = 2  # a base guarda sem o zero à esquerda em alguns meses


def _codigo(serie: pd.Series) -> pd.Series:
    """O código de dois dígitos; vazio fica vazio."""
    texto = serie.str.strip()
    return texto.where(texto == "", texto.str.zfill(TAMANHO_DO_CODIGO))


def ler_situacao_cadastral_do_cnpj(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Um registro por estabelecimento num `Estabelecimentos*.zip`: CNPJ e os três campos da situação.

    Lê por partes (o mês inteiro tem 70 milhões de linhas) e só as posições pedidas: o resto do arquivo
    nunca vira coluna.
    """
    partes = []
    for parte in _partes(
        io.BytesIO(conteudo_do_zip), CAMPOS_DO_ESTABELECIMENTO, POSICOES
    ):
        parte = parte.rename(columns=POSICOES)
        basico, ordem, dv = (
            parte[c].str.strip() for c in ("cnpj_basico", "ordem", "dv")
        )
        partes.append(
            pd.DataFrame(
                {
                    "cnpj": (
                        basico.str[:2]
                        + "."
                        + basico.str[2:5]
                        + "."
                        + basico.str[5:8]
                        + "/"
                        + ordem
                        + "-"
                        + dv
                    ),
                    "cnpj_basico": basico,
                    "matriz": parte["matriz"].str.strip() == MATRIZ,
                    "situacao_cadastral": _codigo(parte["situacao_cadastral"]),
                    "data_situacao_cadastral": _datas(
                        parte["data_situacao_cadastral"]
                    ).dt.date,
                    "motivo_situacao": _codigo(parte["motivo_situacao"]),
                }
            )
        )
    if not partes:
        return pd.DataFrame({coluna: [] for coluna in COLUNAS})
    return pd.concat(partes, ignore_index=True)[list(COLUNAS)]


def montar(conexao: sa.Connection, pasta: Path, agora: datetime) -> dict[str, int]:
    """`<pasta>/cnpj_situacao_cadastral/<AAAA-MM>.parquet` para cada mês do CNPJ guardado.

    Devolve as linhas por mês. Reprocessar os meses guardados não regrava o que não mudou.
    """
    por_mes: dict[str, list[pd.DataFrame]] = {}
    origens: dict[str, list[dict[str, str]]] = {}
    for original in originais_mais_recentes(conexao, "rfb-cnpj"):
        achado = MES_NA_PASTA.search(original.url)
        conteudo = acervo.ler_original(original.caminho_do_original)
        if achado is None or conteudo is None:
            continue
        mes = achado.group(1)
        tabela = ler_situacao_cadastral_do_cnpj(conteudo).assign(
            mes_do_retrato=mes,
            disponivel_em=disponivel_em(conexao, original, mes),
            origem_sha256=original.sha256,
            origem_coletada_em=pd.Timestamp(original.baixado_em).isoformat(),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )
        por_mes.setdefault(mes, []).append(tabela)
        origens.setdefault(mes, []).append(
            {"url": original.url, "sha256": original.sha256}
        )
    linhas: dict[str, int] = {}
    for mes, partes in por_mes.items():
        tabela = pd.concat(partes, ignore_index=True)
        gravar_se_mudou(
            tabela,
            pasta / TABELA / f"{mes}.parquet",
            origens[mes],
            ["cnpj"],
            carimbos=LINHAGEM,
        )
        linhas[mes] = len(tabela)
    return linhas
