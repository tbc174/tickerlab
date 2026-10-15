"""Curva de juros própria (série B12): nominal, real e inflação implícita, sem B3 nem ANBIMA.

Fonte: as taxas diárias do Tesouro Direto desde 2004 (Tesouro Transparente, ODbL), guardadas pelo
arquivista como `tesouro-br-direto`. Versão 1, de propósito simples e auditável:

- só os títulos **sem cupom**, cuja taxa já é a taxa "zero" do prazo: Tesouro Prefixado (LTN) para a
  curva nominal e Tesouro IPCA+ (NTN-B Principal) para a real;
- prazo em dias úteis (base 252) da **liquidação** (dia útil seguinte à cotação) até o vencimento, com
  o calendário que se conhecia na data (`base/dias_uteis.py`): é a conta que reproduz o preço publicado
  pelo Tesouro em 99% das linhas;
- entre dois títulos, interpolação **flat-forward** (padrão do mercado brasileiro); **sem extrapolar**:
  se o título mais longo do dia vence em 7 anos, o vértice de 10 anos não sai;
- inflação implícita = (1 + nominal) / (1 + real) − 1 no mesmo prazo.

Cuidados: a taxa do Tesouro Direto tem um spread do Tesouro sobre o mercado secundário (medir contra
os leilões, `tesouro-br-leiloes`). Usa a taxa de compra; quando o título só está à venda para resgate,
a de venda (`lado`). Nada de olhar o futuro: a curva de um dia só usa as taxas daquele dia, e
`disponivel_em` é o dia útil seguinte (o arquivo do Tesouro sai na manhã seguinte).
Versão 2 (depois): Nelson-Siegel-Svensson e os títulos com cupom (NTN-F e NTN-B).
"""

import io
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base.dias_uteis import DIAS_POR_ANO, dias_uteis, proximo_dia_util
from base.parquet import LINHAGEM, gravar_se_mudou
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.versao_do_codigo import versao_do_codigo

FONTE = "tesouro-br-direto"
TITULOS_DAS_CURVAS = {"nominal": "Tesouro Prefixado", "real": "Tesouro IPCA+"}
VERTICES_ANOS = (0.5, 1, 2, 3, 5, 10, 20)
TABELA = "curva_juros"
COLUNAS_DO_CSV = {
    "Tipo Titulo": "titulo",
    "Data Vencimento": "vencimento",
    "Data Base": "data_base",
    "Taxa Compra Manha": "taxa_compra",
    "Taxa Venda Manha": "taxa_venda",
}


def ler_tesouro_direto(conteudo: bytes) -> pd.DataFrame:
    """Uma linha por título e dia: taxa (decimal), lado da taxa e prazo em dias úteis e em anos."""
    bruto = pd.read_csv(io.BytesIO(conteudo), sep=";", decimal=",", encoding="latin-1")
    tabela = pd.DataFrame(
        bruto.rename(columns=COLUNAS_DO_CSV).loc[:, list(COLUNAS_DO_CSV.values())]
    )
    for coluna in ("data_base", "vencimento"):
        tabela[coluna] = pd.to_datetime(tabela[coluna], dayfirst=True)
    compra = pd.Series(tabela["taxa_compra"]).fillna(0) > 0
    venda = pd.Series(tabela["taxa_venda"]).fillna(0) > 0
    tabela = tabela.loc[compra | venda].copy()
    compra = compra.loc[tabela.index]
    tabela["taxa"] = (
        pd.Series(tabela["taxa_compra"]).where(compra, tabela["taxa_venda"]) / 100
    )
    tabela["lado"] = np.where(compra, "compra", "venda")
    tabela["liquidacao"] = proximo_dia_util(pd.Series(tabela["data_base"]))
    tabela["dias_uteis"] = dias_uteis(
        pd.Series(tabela["liquidacao"]), pd.Series(tabela["vencimento"])
    )
    tabela = tabela.loc[tabela["dias_uteis"] > 0].copy()
    tabela["prazo_anos"] = tabela["dias_uteis"] / DIAS_POR_ANO
    colunas = [
        "data_base",
        "titulo",
        "vencimento",
        "taxa",
        "lado",
        "dias_uteis",
        "prazo_anos",
    ]
    ordenada = tabela.loc[:, colunas].sort_values(["data_base", "titulo", "vencimento"])
    return ordenada.reset_index(drop=True)


def flat_forward(prazos: np.ndarray, taxas: np.ndarray, alvo: float) -> float:
    """Taxa no prazo `alvo` (anos) entre os títulos do dia; NaN fora do intervalo (sem extrapolar).

    Flat-forward: o logaritmo do fator (1 + taxa) ^ prazo varia em linha reta entre dois vencimentos,
    ou seja, a taxa a termo entre eles é constante.
    """
    if len(prazos) == 0 or alvo < prazos[0] or alvo > prazos[-1]:
        return math.nan
    fatores = prazos * np.log1p(taxas)
    return math.expm1(float(np.interp(alvo, prazos, fatores)) / alvo)


def _vertices(dia: pd.DataFrame) -> list[tuple[float, float]]:
    pontos = dia.groupby("prazo_anos")["taxa"].mean().sort_index()
    prazos, taxas = pontos.index.to_numpy(dtype=float), pontos.to_numpy(dtype=float)
    return [(v, flat_forward(prazos, taxas, v)) for v in VERTICES_ANOS]


def montar_curvas(taxas: pd.DataFrame) -> pd.DataFrame:
    """Vértices de cada dia (nominal, real e implícita), só onde há títulos dos dois lados do prazo."""
    linhas = []
    for curva, titulo in TITULOS_DAS_CURVAS.items():
        do_titulo = taxas[taxas["titulo"] == titulo]
        for data_base, dia in do_titulo.groupby("data_base"):
            maior = float(dia["prazo_anos"].max())
            for prazo, taxa in _vertices(dia):
                if not math.isnan(taxa):
                    linhas.append((data_base, curva, prazo, taxa, len(dia), maior))
    curvas = pd.DataFrame(
        linhas,
        columns=[
            "data_base",
            "curva",
            "prazo_anos",
            "taxa",
            "titulos",
            "maior_prazo_anos",
        ],
    )
    chave = ["data_base", "prazo_anos"]
    nominal = curvas[curvas["curva"] == "nominal"].set_index(chave)
    real = curvas[curvas["curva"] == "real"].set_index(chave)
    juntos = nominal.join(real, how="inner", lsuffix="_n", rsuffix="_r")
    implicita = pd.DataFrame(
        {
            "curva": "implicita",
            "taxa": (1 + juntos["taxa_n"]) / (1 + juntos["taxa_r"]) - 1,
            "titulos": juntos["titulos_n"] + juntos["titulos_r"],
            "maior_prazo_anos": juntos[
                ["maior_prazo_anos_n", "maior_prazo_anos_r"]
            ].min(axis=1),
        }
    ).reset_index()
    curvas = pd.concat([curvas, implicita], ignore_index=True)
    curvas["disponivel_em"] = proximo_dia_util(curvas["data_base"])
    return curvas.sort_values(["data_base", "curva", "prazo_anos"]).reset_index(
        drop=True
    )


def montar(conexao: sa.Connection, pasta: Path, agora: datetime) -> dict[int, int]:
    """`<pasta>/curva_juros/<ano>.parquet` a partir do CSV do Tesouro Direto mais recente."""
    for original in originais_mais_recentes(conexao, FONTE):
        if not original.url.lower().endswith(".csv"):
            continue  # o pacote também tem o PDF de metadados
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo is None:
            continue
        curvas = montar_curvas(ler_tesouro_direto(conteudo)).assign(
            origem_sha256=original.sha256,
            origem_coletada_em=pd.Timestamp(original.baixado_em).isoformat(),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )
        linhas: dict[int, int] = {}
        for ano, do_ano in curvas.groupby(curvas["data_base"].dt.year):
            gravar_se_mudou(
                do_ano,
                pasta / TABELA / f"{ano}.parquet",
                [{"url": original.url, "sha256": original.sha256}],
                ["data_base", "curva", "prazo_anos"],
                carimbos=LINHAGEM,
            )
            linhas[int(ano)] = len(do_ano)
        return linhas
    return {}
