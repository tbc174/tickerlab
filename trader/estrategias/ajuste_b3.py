"""Preços ajustados das fichas F-B3 e P0-4: o fechamento do COTAHIST corrigido pelos eventos de capital.

Convenções (escritas antes de qualquer número das fichas):

- **Eventos que ajustam:** desdobramento, grupamento e bonificação da tabela `eventos_de_capital` do
  acervo (formulário de referência da CVM, por CNPJ), com `fator = ações depois ÷ ações antes`. Aumento
  de capital por subscrição não ajusta (o direito de subscrição vale pouco perto do preço). O mesmo
  evento repetido em versões e anos do formulário conta uma vez; eventos da mesma empresa na mesma data
  se multiplicam (o grupamento de 1:100 com desdobramento de 100 do mesmo dia dá 1 e some).
- **Data ex pelo preço:** a data do formulário é a da deliberação, não a data ex. Para cada papel da
  empresa, a data ex é o pregão, de `DIAS_ANTES` dias corridos antes até `DIAS_DEPOIS` depois da data do
  evento, cujo retorno de um pregão mais se aproxima de 1 ÷ fator; vale se a distância em log ficar
  dentro de `TOLERANCIA` × |log fator|. Sem pregão que bata, o evento não ajusta aquele papel e entra na
  conferência como "sem data ex". Um pregão serve a um evento só.
- **Ajuste para trás:** todo preço antes da data ex é multiplicado por 1 ÷ fator (o último preço fica o do
  arquivo). O fator de um evento é o mesmo para todo o passado, então o retorno de um dia e o z de uma
  janela sem evento não mudam com eventos posteriores: o ajuste não olha o futuro.
- **Proventos não ajustam:** o acervo tem dividendos e JCP por exercício, sem valor por ação nem data ex.
  Os retornos ficam sem os proventos nas duas pernas (a comprada deixa de receber, a vendida deixa de
  pagar); limitação declarada no relatório de cada ficha.
- **Desdobramento pelo preço (o que o formulário não tem):** depois dos eventos do formulário, um
  retorno de um pregão de `SALTO` vezes ou mais no dia em que o número de distribuição do COTAHIST
  (DISMES) mudou é desdobramento ou grupamento se a razão fechamento anterior ÷ fechamento do dia
  ficar a até `TOLERANCIA_DO_PRECO` (em log) de um fator usual (`FATORES_USUAIS` e os inversos); o
  fator é essa razão arredondada. A B3 muda o DISMES no dia ex de todo evento, com ou sem
  desdobramento; uma quebra sem evento (Americanas em 01/2023) não muda. Dividendo grande e cisão
  mudam o DISMES, mas a razão fica longe de um fator usual (Bradespar 2,41, Assaí 3,56) e não
  ajustam. A tolerância foi escolhida na conferência dos casos conhecidos, antes de qualquer número
  de ficha; o ajuste continua para trás e sem olhar o futuro.
- **Saltos sem evento:** retorno de um pregão de `SALTO` vezes para cima ou para baixo que nenhum evento
  explica fica na conferência, para o relatório dizer quantos são. Não é corrigido.

`python -m trader.estrategias.ajuste_b3` lê os COTAHIST anuais da pasta da ficha e o acervo e grava
`precos_ajustados.parquet` e `conferencia_do_ajuste.json` na pasta da ficha. Nada baixa da internet.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from trader.estrategias import dados_f_b3

TIPOS_QUE_AJUSTAM = ("desdobramento", "grupamento", "bonificação")
DIAS_ANTES = 10
DIAS_DEPOIS = 120
TOLERANCIA = 0.5
FATOR_MINIMO = 1.01  # abaixo de 1% o evento não muda o preço de forma que se veja
SALTO = 2.0
FATORES_USUAIS = (
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    12,
    15,
    16,
    20,
    25,
    30,
    40,
    50,
    60,
    80,
    100,
)
FATORES_USUAIS += (200, 250, 500, 1000)
TOLERANCIA_DO_PRECO = math.log(
    1.05
)  # o movimento do mercado no dia ex fica abaixo de 5%
CASAS_DO_FATOR = (
    4  # o mesmo evento em versões diferentes do formulário difere na 5ª casa
)
ARQUIVO_DA_CONFERENCIA = "conferencia_do_ajuste.json"
PRIMEIRO_DIA = pd.Timestamp(f"{dados_f_b3.PRIMEIRO_ANO}-01-01")


@dataclass(frozen=True)
class Ajuste:
    """O fechamento ajustado e o que a conferência precisa contar."""

    ajustado: pd.DataFrame
    aplicados: (
        pd.DataFrame
    )  # ticker, cnpj, data do evento, data ex, fator, retorno do dia
    sem_data_ex: pd.DataFrame  # ticker, cnpj, data do evento, fator
    saltos: pd.DataFrame  # ticker, data, retorno do dia (sem evento que explique)
    pelo_preco: pd.DataFrame  # ticker, data ex, fator, retorno do dia


def eventos_que_ajustam(eventos: pd.DataFrame) -> pd.DataFrame:
    """Um fator por empresa e data (cnpj, data, fator), só os que mudam o preço."""
    linhas = eventos[
        eventos["tipo"].isin(TIPOS_QUE_AJUSTAM)
        & (eventos["fator"] > 0)
        & eventos["data"].notna()
    ].assign(fator_curto=lambda t: t["fator"].round(CASAS_DO_FATOR))
    linhas = linhas.drop_duplicates(["cnpj", "tipo", "data", "fator_curto"])
    por_data = linhas.groupby(["cnpj", "data"], as_index=False)["fator"].prod()
    visivel = np.abs(np.log(por_data["fator"])) >= math.log(FATOR_MINIMO)
    return por_data[visivel].sort_values(["cnpj", "data"]).reset_index(drop=True)


def _data_ex(
    retorno: pd.Series, data_do_evento: pd.Timestamp, fator: float, usados: set
) -> pd.Timestamp | None:
    """O pregão da janela do evento cujo retorno mais se aproxima de 1 ÷ fator, se bater."""
    janela = retorno.loc[
        data_do_evento - pd.Timedelta(days=DIAS_ANTES) : data_do_evento
        + pd.Timedelta(days=DIAS_DEPOIS)
    ].dropna()
    janela = janela[~janela.index.isin(list(usados))]
    if janela.empty:
        return None
    esperado = -math.log(fator)
    distancia = (np.log1p(janela) - esperado).abs()
    melhor = distancia.idxmin()
    if distancia[melhor] > TOLERANCIA * abs(esperado):
        return None
    return pd.Timestamp(melhor)


def ajustar_um(
    fechamento: pd.Series, eventos: pd.DataFrame
) -> tuple[pd.Series, list[tuple]]:
    """O fechamento de um papel ajustado para trás; devolve também (data do evento, data ex, fator)."""
    precos = fechamento.dropna()
    retorno = precos.pct_change(fill_method=None)
    multiplicador = pd.Series(1.0, index=precos.index)
    usados: set = set()
    achados = []
    for data_do_evento, fator in zip(eventos["data"], eventos["fator"], strict=True):
        data_ex = _data_ex(retorno, pd.Timestamp(data_do_evento), float(fator), usados)
        achados.append((pd.Timestamp(data_do_evento), data_ex, float(fator)))
        if data_ex is None:
            continue
        usados.add(data_ex)
        multiplicador[multiplicador.index < data_ex] /= fator
    return (precos * multiplicador).reindex(fechamento.index), achados


def fator_usual(razao: float) -> float | None:
    """O fator usual (ou o inverso) a até `TOLERANCIA_DO_PRECO` da razão de preços; senão nada."""
    if not math.isfinite(razao) or razao <= 0:
        return None
    candidatos = [float(f) for f in FATORES_USUAIS] + [1 / f for f in FATORES_USUAIS]
    melhor = min(candidatos, key=lambda f: abs(math.log(razao / f)))
    return melhor if abs(math.log(razao / melhor)) <= TOLERANCIA_DO_PRECO else None


def ajustar_pelo_preco(
    fechamento: pd.Series, trocas: pd.Series
) -> tuple[pd.Series, list[tuple]]:
    """Desdobramentos sem formulário: salto no dia da troca de distribuição perto de um fator usual.

    Devolve o fechamento ajustado para trás e (data ex, fator, retorno do dia) de cada um.
    """
    precos = fechamento.dropna()
    retorno = precos.pct_change(fill_method=None)
    no_dia_da_troca = trocas.reindex(retorno.index).eq(True)
    with np.errstate(divide="ignore"):  # preço zero no arquivo: não é desdobramento
        grande = np.log1p(retorno).abs() >= math.log(SALTO)
    multiplicador = pd.Series(1.0, index=precos.index)
    achados = []
    for dia in retorno.index[grande & no_dia_da_troca]:
        fator = fator_usual(1 / (1 + float(retorno[dia])))
        if fator is None:
            continue
        multiplicador[multiplicador.index < dia] /= fator
        achados.append((pd.Timestamp(dia), fator, float(retorno[dia])))
    return (precos * multiplicador).reindex(fechamento.index), achados


def ajustar(
    fechamento: pd.DataFrame,
    cnpj_por_ticker: pd.Series,
    eventos: pd.DataFrame,
    trocas: pd.DataFrame | None = None,
) -> Ajuste:
    """Ajusta cada papel pelos eventos da sua empresa e, com `trocas`, pelo preço (ver o topo)."""
    por_cnpj = {
        cnpj: grupo for cnpj, grupo in eventos_que_ajustam(eventos).groupby("cnpj")
    }
    colunas, aplicados, sem_data_ex = {}, [], []
    for ticker in fechamento.columns:
        cnpj = cnpj_por_ticker.get(ticker)
        do_papel = por_cnpj.get(cnpj) if isinstance(cnpj, str) else None
        if do_papel is None:
            colunas[ticker] = fechamento[ticker]
            continue
        precos = fechamento[ticker].dropna()
        no_periodo = (
            do_papel[
                (
                    do_papel["data"]
                    >= precos.index.min() - pd.Timedelta(days=DIAS_DEPOIS)
                )
                & (
                    do_papel["data"]
                    <= precos.index.max() + pd.Timedelta(days=DIAS_ANTES)
                )
            ]
            if not precos.empty
            else do_papel.iloc[:0]
        )
        colunas[ticker], achados = ajustar_um(fechamento[ticker], no_periodo)
        retorno = precos.pct_change(fill_method=None)
        for data_do_evento, data_ex, fator in achados:
            if data_ex is None:
                sem_data_ex.append((ticker, cnpj, data_do_evento, fator))
            else:
                aplicados.append(
                    (
                        ticker,
                        cnpj,
                        data_do_evento,
                        data_ex,
                        fator,
                        float(retorno[data_ex]),
                    )
                )
    pelo_preco = []
    if trocas is not None:
        for ticker in fechamento.columns:
            if ticker not in trocas.columns:
                continue
            colunas[ticker], achados = ajustar_pelo_preco(
                colunas[ticker], trocas[ticker]
            )
            pelo_preco.extend((ticker, *achado) for achado in achados)
    ajustado = pd.DataFrame(colunas, index=fechamento.index)[fechamento.columns]
    return Ajuste(
        ajustado=ajustado,
        aplicados=pd.DataFrame(
            aplicados,
            columns=[
                "ticker",
                "cnpj",
                "data_do_evento",
                "data_ex",
                "fator",
                "retorno_do_dia",
            ],
        ),
        sem_data_ex=pd.DataFrame(
            sem_data_ex, columns=["ticker", "cnpj", "data_do_evento", "fator"]
        ),
        saltos=saltos_sem_evento(ajustado),
        pelo_preco=pd.DataFrame(
            pelo_preco, columns=["ticker", "data", "fator", "retorno_do_dia"]
        ),
    )


def saltos_sem_evento(ajustado: pd.DataFrame) -> pd.DataFrame:
    """Retornos de um pregão de `SALTO` vezes ou mais que sobraram depois do ajuste."""
    linhas = []
    for ticker in ajustado.columns:
        retorno = ajustado[ticker].dropna().pct_change(fill_method=None).dropna()
        with np.errstate(
            divide="ignore"
        ):  # preço zero no arquivo dá −100%: conta como salto
            grandes = retorno[(np.log1p(retorno)).abs() >= math.log(SALTO)]
        linhas.extend((ticker, data, float(valor)) for data, valor in grandes.items())
    return pd.DataFrame(linhas, columns=["ticker", "data", "retorno_do_dia"])


def conferencia(ajuste: Ajuste, negociados: pd.DataFrame) -> dict:
    """Resumo para o relatório: quantos eventos ajustaram, quantos não acharam data ex, saltos."""
    com_volume = set(negociados.columns)
    return {
        "papeis": len(ajuste.ajustado.columns),
        "papeis_com_negocio": len(com_volume),
        "eventos_aplicados": len(ajuste.aplicados),
        "eventos_sem_data_ex": len(ajuste.sem_data_ex),
        "desdobramentos_pelo_preco": len(ajuste.pelo_preco),
        "saltos_sem_evento": len(ajuste.saltos),
        "papeis_com_salto_sem_evento": int(ajuste.saltos["ticker"].nunique()),
        "regras": {
            "tipos": list(TIPOS_QUE_AJUSTAM),
            "dias_antes": DIAS_ANTES,
            "dias_depois": DIAS_DEPOIS,
            "tolerancia": TOLERANCIA,
            "fator_minimo": FATOR_MINIMO,
            "salto": SALTO,
            "fatores_usuais": list(FATORES_USUAIS),
            "tolerancia_do_preco": TOLERANCIA_DO_PRECO,
        },
    }


def main(
    pasta: Path = dados_f_b3.PASTA_DA_FICHA,
    pasta_do_acervo: Path = dados_f_b3.PASTA_DO_ACERVO,
) -> int:
    """Grava os preços ajustados e a conferência na pasta da ficha."""
    faltam = [
        dados_f_b3.nome_do_cotahist(ano)
        for ano in range(dados_f_b3.PRIMEIRO_ANO, dados_f_b3.ULTIMO_ANO + 1)
        if not (pasta / dados_f_b3.nome_do_cotahist(ano)).exists()
    ]
    if faltam:
        print(f"faltam os COTAHIST anuais: {', '.join(faltam)}")
        return 2
    longo = pd.concat(
        [
            dados_f_b3.ler_cotahist_anual(pasta / dados_f_b3.nome_do_cotahist(ano))
            for ano in range(dados_f_b3.PRIMEIRO_ANO, dados_f_b3.ULTIMO_ANO + 1)
        ],
        ignore_index=True,
    )
    fechamento, _, volume = dados_f_b3.paineis(longo)
    cadastro = dados_f_b3.cadastro_dos_tickers(
        longo, dados_f_b3.ler_emissores(pasta_do_acervo)
    )
    eventos = pd.concat(
        [
            pd.read_parquet(arquivo)
            for arquivo in sorted(
                (pasta_do_acervo / "eventos_de_capital").glob("*.parquet")
            )
        ],
        ignore_index=True,
    )
    ajuste = ajustar(
        fechamento,
        cadastro["cnpj"],
        eventos[eventos["data"] >= PRIMEIRO_DIA - pd.Timedelta(days=DIAS_DEPOIS)],
        trocas=dados_f_b3.trocas_de_distribuicao(longo),
    )
    ajuste.ajustado.to_parquet(pasta / dados_f_b3.ARQUIVO_DE_PRECOS_AJUSTADOS)
    resumo = conferencia(ajuste, volume.loc[:, volume.sum() > 0])
    (pasta / ARQUIVO_DA_CONFERENCIA).write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for nome, tabela in (
        ("aplicados", ajuste.aplicados),
        ("sem_data_ex", ajuste.sem_data_ex),
        ("saltos", ajuste.saltos),
        ("pelo_preco", ajuste.pelo_preco),
    ):
        tabela.to_csv(pasta / f"ajuste_{nome}.csv", index=False)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
