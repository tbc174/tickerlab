"""Quem está na amostra integrada em cada fim de mês, e com que tickers (bloco "universo").

Uma companhia entra num mês quando, naquele dia:
- tinha registro de companhia aberta na CVM (`registro` <= data e o cancelamento, se houve, depois);
- já tinha entregado ao menos uma DFP ou ITR (a primeira entrega já pública). Exigir "uma companhia que
  vai entregar" olharia o futuro: a que se registra e nunca entrega não entra.

As canceladas continuam nos meses em que existiam (sem viés de sobrevivência, ADR 0027, exigência 4).
Os tickers valem do dia da entrega do FCA que os trouxe até o dia em que um FCA passou a valer sem eles
(`base/cadastro.py::tickers_no_tempo`). O FCA só traz o código de 2018 em diante: antes da primeira
entrega com código, "sem ticker" é **desconhecido**, não falso (`com_ticker_na_data` vazio), e os poucos
códigos de antes vêm da tabela conferida. O nome e o setor do cadastro são os de hoje e **não entram**:
mudam com o tempo e a CVM não guarda o histórico.
"""

import pandas as pd

from base.amostra.como_era import DATA, INICIO, Entrada, fins_de_mes

REGISTRO_SEM_DATA = pd.Timestamp(
    "1900-01-01"
)  # cadastro antigo sem a data: registrada desde sempre
ENTRADAS = {
    "cadastro": Entrada(publico_em="registro", termina_em="cancelamento"),
    "entregas": Entrada(publico_em="primeira_entrega"),
    "tickers": Entrada(publico_em="primeiro_visto", termina_em="valido_ate"),
}
COLUNAS = (
    "cnpj", "data", "registrada_desde", "primeira_entrega", "tickers_na_data", "com_ticker_na_data",
)  # fmt: skip
SEPARADOR = ", "


def preparar(
    cadastro: pd.DataFrame, entregas: pd.DataFrame, tickers: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """As entradas do universo como o bloco e o corte as leem: datas como data e o registro sem data
    como `REGISTRO_SEM_DATA`."""
    cadastro = cadastro[["cnpj", "registro", "cancelamento"]].copy()
    cadastro["registro"] = pd.to_datetime(cadastro["registro"]).fillna(
        REGISTRO_SEM_DATA
    )
    cadastro["cancelamento"] = pd.to_datetime(cadastro["cancelamento"])
    entregas = entregas[["cnpj", "primeira_entrega"]].dropna().copy()
    entregas["primeira_entrega"] = pd.to_datetime(entregas["primeira_entrega"])
    colunas = ["codigo", "cnpj", "primeiro_visto", "valido_ate"]
    tickers = tickers.reindex(columns=[*colunas, "origem"]).dropna(
        subset=["primeiro_visto"]
    )
    tickers = tickers.assign(
        primeiro_visto=pd.to_datetime(tickers["primeiro_visto"]),
        valido_ate=pd.to_datetime(tickers["valido_ate"]),
    )
    return {"cadastro": cadastro, "entregas": entregas, "tickers": tickers}


def _registradas(cadastro: pd.DataFrame, meses: pd.DatetimeIndex) -> pd.DataFrame:
    """Cada companhia em cada mês em que tinha registro, com o início do registro daquele período."""
    grade = cadastro.merge(pd.DataFrame({"data": meses.astype(DATA)}), how="cross")
    ativa = (grade["registro"] <= grade["data"]) & (
        grade["cancelamento"].isna() | (grade["cancelamento"] > grade["data"])
    )
    registradas = grade[ativa].rename(columns={"registro": "registrada_desde"})
    return registradas.sort_values("registrada_desde").drop_duplicates(
        ["cnpj", "data"], keep="last"
    )[["cnpj", "data", "registrada_desde"]]


def _tickers_na_data(grade: pd.DataFrame, tickers: pd.DataFrame) -> pd.Series:
    pares = grade[["cnpj", "data"]].merge(tickers, on="cnpj")
    valem = (pares["primeiro_visto"] <= pares["data"]) & (
        pares["valido_ate"].isna() | (pares["valido_ate"] > pares["data"])
    )
    codigos = (
        pares[valem]
        .sort_values("codigo")
        .groupby(["cnpj", "data"])["codigo"]
        .agg(lambda serie: SEPARADOR.join(dict.fromkeys(serie)))
    )
    por_par = codigos.to_dict()
    valores = [
        por_par.get(par) for par in zip(grade["cnpj"], grade["data"], strict=True)
    ]
    return pd.Series(valores, index=grade.index, dtype=object)


def _com_ticker(grade: pd.DataFrame, tickers: pd.DataFrame) -> pd.Series:
    """Verdadeiro com um código válido; falso sem código depois que o FCA começou a trazer códigos
    (a primeira entrega de origem "fca"); vazio antes disso, quando não dá para saber."""
    do_fca = tickers[tickers["origem"].fillna("fca") == "fca"]["primeiro_visto"]
    inicio = do_fca.min() if len(do_fca) else pd.NaT
    tem = grade["tickers_na_data"].notna()
    sabido = tem | (grade["data"] >= inicio) if pd.notna(inicio) else tem
    return tem.astype("boolean").mask(~sabido, pd.NA)


def montar(entradas: dict[str, pd.DataFrame], fim: pd.Timestamp) -> pd.DataFrame:
    """O universo de `INICIO` a `fim`: uma linha por companhia e fim de mês."""
    meses = fins_de_mes(INICIO, fim)
    primeira = (
        entradas["entregas"]
        .groupby("cnpj")["primeira_entrega"]
        .min()
        .rename("primeira_entrega")
    )
    grade = _registradas(entradas["cadastro"], meses).merge(
        primeira.reset_index(), on="cnpj"
    )
    grade = grade[grade["primeira_entrega"] <= grade["data"]].reset_index(drop=True)
    grade["tickers_na_data"] = _tickers_na_data(grade, entradas["tickers"])
    grade["com_ticker_na_data"] = _com_ticker(grade, entradas["tickers"])
    return (
        grade.sort_values(["cnpj", "data"])
        .reindex(columns=list(COLUNAS))
        .reset_index(drop=True)
    )
