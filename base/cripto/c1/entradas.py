"""Entradas do modelo C-1 (pré-registro v2, seção 3): a lista fechada, cada uma só com o que
existia às 00:00 UTC do dia D.

Cada fonte é transformada na própria linha do tempo (pela data dela, usando só linhas anteriores) e
depois alinhada ao dia D pela última linha com `divulgado_em` até 00:00 UTC de D.

- **Preço** (Kraken, BTC/USD): volatilidade de 1, 7, 30 e 90 dias, amplitude do dia (log da máxima
  sobre a mínima) e retorno de 30 dias, todos até o último dia fechado.
- **Rede, atenção e posições:** variação em relação à média dos 90 dias anteriores. Em log
  (`variacao_log`) para o que é sempre positivo. **Esclarecimento de implementação (13/10/2026,
  antes de qualquer resultado):** a posição líquida e o tom das notícias podem ser negativos, e log
  de negativo não existe; para eles, a variação é a diferença para a média dos 90 dias dividida pela
  média dos valores absolutos (`variacao_relativa`), a mesma ideia sem o log.
- **Macro:** volatilidade de 30 observações da PTAX, juro de 2 anos dos EUA e Selic, em nível.
"""

from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd

JANELA_DA_VARIACAO = "90D"
JANELAS_DE_VOLATILIDADE = (7, 30, 90)
DIAS_DO_RETORNO = 30
# BTC por contrato na CME
BTC_POR_CONTRATO = {"bitcoin": 5.0, "micro_bitcoin": 0.1}
METRICAS_DA_REDE = [
    "taxas_total",
    "taxa_mediana_por_vbyte",
    "n_transacoes",
    "valor_movimentado",
    "dias_moeda_destruidos",
    "fracao_parada_1_ano",
    "dificuldade",
]
COLUNAS_DE_PRECO = ["vol_1", "vol_7", "vol_30", "vol_90", "amplitude", "retorno_30"]
COLUNAS_DE_POSICAO = ["gestores_liquido", "alavancados_liquido", "contratos_em_aberto"]
COLUNAS_DE_ATENCAO = ["wikipedia", "noticias", "tom"]
COLUNAS_MACRO = ["vol_ptax_30", "juro_2_anos_eua", "selic"]
COLUNAS = (
    COLUNAS_DE_PRECO
    + METRICAS_DA_REDE
    + COLUNAS_DE_POSICAO
    + COLUNAS_DE_ATENCAO
    + COLUNAS_MACRO
)
PROJETO_DA_WIKIPEDIA = "en.wikipedia"
# uma resolução só para as datas dos dois lados do alinhamento (o merge_asof exige)
TIPO_DO_MOMENTO = "datetime64[ns, UTC]"


def montar_entradas(
    tabelas: dict[str, pd.DataFrame], dias: Sequence[date]
) -> pd.DataFrame:
    """As entradas de cada dia D (índice), nas colunas de `COLUNAS`.

    `tabelas`: `precos`, `rede`, `cot`, `wikipedia`, `gdelt`, `ptax`, `juro_2_anos_eua` e `selic`,
    cada uma com `divulgado_em` (UTC).
    """
    momentos = pd.Series(pd.to_datetime(pd.Series(list(dias))).dt.tz_localize("UTC"))
    partes = [
        _alinhar(_entradas_de_preco(tabelas["precos"]), momentos),
        _alinhar(_entradas_da_rede(tabelas["rede"]), momentos),
        _alinhar(_entradas_de_posicao(tabelas["cot"]), momentos),
        _alinhar(_entradas_da_wikipedia(tabelas["wikipedia"]), momentos),
        _alinhar(_entradas_do_gdelt(tabelas["gdelt"]), momentos),
        *[_alinhar(serie, momentos) for serie in _entradas_macro(tabelas)],
    ]
    entradas = pd.concat(partes, axis=1)
    entradas.index = list(dias)
    return entradas[COLUNAS]


def variacao_log(serie: pd.Series) -> pd.Series:
    """log(valor / média dos 90 dias anteriores, sem o próprio dia); índice de datas."""
    media = serie.rolling(JANELA_DA_VARIACAO, closed="left").mean()
    return np.log(serie / media)


def variacao_relativa(serie: pd.Series) -> pd.Series:
    """(valor − média dos 90 dias anteriores) / média dos valores absolutos nesses 90 dias."""
    media = serie.rolling(JANELA_DA_VARIACAO, closed="left").mean()
    escala = serie.abs().rolling(JANELA_DA_VARIACAO, closed="left").mean()
    return (serie - media) / escala.replace(0, np.nan)


def posicoes_em_btc(cot: pd.DataFrame) -> pd.DataFrame:
    """Por relatório: posição líquida de gestores e de alavancados e contratos em aberto, em BTC
    (Bitcoin + Micro Bitcoin), com o `divulgado_em` mais tardio dos contratos."""
    tamanho = cot["contrato"].map(BTC_POR_CONTRATO)
    em_btc = pd.DataFrame(
        {
            "relatorio": cot["relatorio"],
            "gestores_liquido": (cot["gestores_comprados"] - cot["gestores_vendidos"])
            * tamanho,
            "alavancados_liquido": (
                cot["alavancados_comprados"] - cot["alavancados_vendidos"]
            )
            * tamanho,
            "contratos_em_aberto": cot["contratos_em_aberto"] * tamanho,
            "divulgado_em": cot["divulgado_em"],
        }
    )
    return (
        em_btc.groupby("relatorio")
        .agg({c: "sum" for c in COLUNAS_DE_POSICAO} | {"divulgado_em": "max"})
        .reset_index()
    )


def _por_data(tabela: pd.DataFrame, coluna_da_data: str) -> pd.DataFrame:
    ordenada = tabela.sort_values(coluna_da_data)
    return ordenada.set_index(pd.to_datetime(ordenada[coluna_da_data]))


def _entradas_de_preco(precos: pd.DataFrame) -> pd.DataFrame:
    tabela = _por_data(precos, "dia")
    retornos = np.log(tabela["fechamento"] / tabela["fechamento"].shift(1))
    # dia faltando: o retorno não pode juntar dois dias
    retornos[tabela.index.to_series().diff() != pd.Timedelta(days=1)] = np.nan
    saida = pd.DataFrame({"vol_1": retornos.abs()}, index=tabela.index)
    for janela in JANELAS_DE_VOLATILIDADE:
        saida[f"vol_{janela}"] = retornos.rolling(janela, min_periods=janela).std()
    saida["amplitude"] = np.log(tabela["maxima"] / tabela["minima"])
    saida["retorno_30"] = retornos.rolling(
        DIAS_DO_RETORNO, min_periods=DIAS_DO_RETORNO
    ).sum()
    saida["divulgado_em"] = tabela["divulgado_em"]
    return saida


def _entradas_da_rede(rede: pd.DataFrame) -> pd.DataFrame:
    tabela = _por_data(rede, "dia")
    saida = pd.DataFrame(
        {m: variacao_log(tabela[m].astype(float)) for m in METRICAS_DA_REDE}
    )
    saida["divulgado_em"] = tabela["divulgado_em"]
    return saida


def _entradas_de_posicao(cot: pd.DataFrame) -> pd.DataFrame:
    tabela = _por_data(posicoes_em_btc(cot), "relatorio")
    return pd.DataFrame(
        {
            "gestores_liquido": variacao_relativa(tabela["gestores_liquido"]),
            "alavancados_liquido": variacao_relativa(tabela["alavancados_liquido"]),
            "contratos_em_aberto": variacao_log(tabela["contratos_em_aberto"]),
            "divulgado_em": tabela["divulgado_em"],
        }
    )


def _entradas_da_wikipedia(wikipedia: pd.DataFrame) -> pd.DataFrame:
    tabela = _por_data(wikipedia[wikipedia["projeto"] == PROJETO_DA_WIKIPEDIA], "dia")
    return pd.DataFrame(
        {
            "wikipedia": variacao_log(tabela["acessos"].astype(float)),
            "divulgado_em": tabela["divulgado_em"],
        }
    )


def _entradas_do_gdelt(gdelt: pd.DataFrame) -> pd.DataFrame:
    tabela = _por_data(gdelt, "dia")
    return pd.DataFrame(
        {
            "noticias": variacao_log(tabela["fracao_das_noticias"]),
            "tom": variacao_relativa(tabela["tom"]),
            "divulgado_em": tabela["divulgado_em"],
        }
    )


def _entradas_macro(tabelas: dict[str, pd.DataFrame]) -> list[pd.DataFrame]:
    """Uma tabela por série macro: cada uma tem a própria data de divulgação."""
    ptax = _por_data(tabelas["ptax"], "dia")
    retornos = np.log(ptax["valor"] / ptax["valor"].shift(1))
    partes = [
        pd.DataFrame(
            {
                "vol_ptax_30": retornos.rolling(30, min_periods=30).std(),
                "divulgado_em": ptax["divulgado_em"],
            }
        )
    ]
    for nome in ("juro_2_anos_eua", "selic"):
        serie = _por_data(tabelas[nome], "dia")
        partes.append(
            pd.DataFrame({nome: serie["valor"], "divulgado_em": serie["divulgado_em"]})
        )
    return partes


def _alinhar(fonte: pd.DataFrame, momentos: pd.Series) -> pd.DataFrame:
    """Para cada momento (00:00 UTC de D), a última linha com `divulgado_em` até ele."""
    esquerda = pd.DataFrame(
        {"momento": momentos.astype(TIPO_DO_MOMENTO), "ordem": range(len(momentos))}
    ).sort_values("momento")
    direita = fonte.assign(divulgado_em=fonte["divulgado_em"].astype(TIPO_DO_MOMENTO))
    direita = direita.sort_values("divulgado_em").reset_index(drop=True)
    juntas = pd.merge_asof(
        esquerda,
        direita,
        left_on="momento",
        right_on="divulgado_em",
        direction="backward",
    )
    juntas = juntas.sort_values("ordem")
    return juntas.drop(columns=["momento", "ordem", "divulgado_em"]).reset_index(
        drop=True
    )
