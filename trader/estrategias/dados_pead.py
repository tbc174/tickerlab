"""Dados da ficha P0-5 (IPE e PEAD): a mesma base da F-B3, sem a quantidade de ações, mais o IPE.

| Tabela | Fonte | Situação em 04/11/2026 |
|---|---|---|
| preços, volume, cadastro, balanços, CDI, BOVA11 | os de `dados_f_b3` (COTAHIST anual de 2009 a 2023 e preços ajustados) | pronto (COTAHIST baixado de novo em 03/11, com SHA-256) |
| documentos | `eventos/<ano>.parquet` do acervo (IPE da CVM: CNPJ, categoria, tipo, tema, referência, versão e `publicado_em`, a data de recebimento) | pronto (2003 em diante) |

A ficha não usa a quantidade de ações (não há valor de mercado na regra), então não exige
`acoes_em_circulacao.parquet`. Só os documentos recebidos até o fim do desenvolvimento entram.
Nada aqui baixa nada da internet.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from trader.estrategias import dados_f_b3
from trader.estrategias.pead import COLUNAS_DOS_DOCUMENTOS, Dados
from trader.holdout import FIM_DO_DESENVOLVIMENTO

PASTA_DA_FICHA = dados_f_b3.PASTA_DA_FICHA  # o COTAHIST anual é o mesmo da F-B3
PASTA_DO_ACERVO = dados_f_b3.PASTA_DO_ACERVO
PASTA_DO_IPE = "eventos"
PRIMEIRO_ANO_DO_IPE = (
    2009  # os resultados de 2009 (12 meses antes da 1ª decisão possível)
)
ULTIMO_ANO = dados_f_b3.ULTIMO_ANO


def conferir_base(
    pasta: Path = PASTA_DA_FICHA, pasta_do_acervo: Path = PASTA_DO_ACERVO
) -> list[str]:
    """Os arquivos que faltam para a ficha rodar; lista vazia quando dá para rodar."""
    faltas = dados_f_b3.conferir_base(pasta, com_acoes=False)
    ipe = pasta_do_acervo / PASTA_DO_IPE
    if not any(
        (ipe / f"{ano}.parquet").exists()
        for ano in range(PRIMEIRO_ANO_DO_IPE, ULTIMO_ANO + 1)
    ):
        faltas.append(f"{ipe} (IPE da CVM)")
    return faltas


def documentos_do_ipe(pasta_do_acervo: Path = PASTA_DO_ACERVO) -> pd.DataFrame:
    """Os documentos do IPE recebidos no desenvolvimento, em ordem de recebimento."""
    pasta = pasta_do_acervo / PASTA_DO_IPE
    arquivos = [
        pasta / f"{ano}.parquet" for ano in range(PRIMEIRO_ANO_DO_IPE, ULTIMO_ANO + 1)
    ]
    tabelas = [
        pd.read_parquet(arquivo, columns=list(COLUNAS_DOS_DOCUMENTOS))
        for arquivo in arquivos
        if arquivo.exists()
    ]
    if not tabelas:
        return pd.DataFrame(columns=list(COLUNAS_DOS_DOCUMENTOS))
    documentos = pd.concat(tabelas, ignore_index=True)
    documentos["publicado_em"] = pd.to_datetime(
        documentos["publicado_em"], errors="coerce"
    )
    documentos["referencia"] = pd.to_datetime(documentos["referencia"], errors="coerce")
    documentos = documentos.dropna(subset=["cnpj", "publicado_em"])
    documentos = documentos[documentos["publicado_em"] <= FIM_DO_DESENVOLVIMENTO]
    return documentos.sort_values(["publicado_em", "cnpj"], kind="stable").reset_index(
        drop=True
    )


def carregar_tabelas(
    pasta: Path = PASTA_DA_FICHA, pasta_do_acervo: Path = PASTA_DO_ACERVO
) -> Dados:
    """Monta `pead.Dados` só com o desenvolvimento; falha listando o que falta."""
    faltas = conferir_base(pasta, pasta_do_acervo)
    if faltas:
        raise FileNotFoundError(f"faltam na base da ficha P0-5: {', '.join(faltas)}")
    base = dados_f_b3.carregar_tabelas(pasta, pasta_do_acervo, com_acoes=False)
    return Dados(**base.__dict__, documentos=documentos_do_ipe(pasta_do_acervo))
