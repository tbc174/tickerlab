"""O direito de resposta da ficha (ADR 0103, ponto 9): as contestações que as empresas mandaram.

Cada linha de `conferidas/contestacoes.csv` é uma contestação recebida e conferida por uma pessoa: o CNPJ,
o registro contestado (o rótulo da base, como `recuperacao_judicial`), o dia do fato (vazio: todos os fatos
daquele registro), o dia em que chegou e o texto da empresa. A ficha mostra o texto ao lado do fato e marca
`situacao: contestada`; só vale a partir do dia em que chegou (sem olhar o futuro).

O arquivo é conferido à mão, não carregado por migração: a contestação chega por e-mail ao contato do
TickerLab e vira uma linha aqui depois que o Tiago a lê (nota de nível 1). Texto com palavra vedada é
recusado na leitura.
"""

from pathlib import Path

import pandas as pd

from base.contrapartes.cafe import palavras_vedadas_em
from base.dossie import NOMES_DOS_REGISTROS
from base.fidc import documento_de_empresa

CAMINHO = Path(__file__).resolve().parent / "conferidas" / "contestacoes.csv"
COLUNAS = ("cnpj", "registro", "aconteceu_em", "recebida_em", "texto")
RAIZ_DO_CNPJ = 8


def vazia() -> pd.DataFrame:
    """Nenhuma contestação, com as colunas que a ficha lê."""
    return pd.DataFrame(
        {
            "cnpj": pd.Series(dtype=str),
            "registro": pd.Series(dtype=str),
            "aconteceu_em": pd.Series(dtype="datetime64[ns]"),
            "recebida_em": pd.Series(dtype="datetime64[ns]"),
            "texto": pd.Series(dtype=str),
        }
    )


def _data(valor: object, linha: int, coluna: str) -> pd.Timestamp:
    try:
        return pd.Timestamp(str(valor))
    except ValueError as erro:
        raise ValueError(f"linha {linha}: data inválida em `{coluna}`") from erro


def ler(caminho: Path = CAMINHO) -> pd.DataFrame:
    """As contestações do arquivo, com o CNPJ só em dígitos e as datas como datas.

    Levanta `ValueError` na primeira linha que a ficha não pode mostrar: CNPJ que não confere, registro
    que a ficha não conhece, data inválida, texto vazio ou com palavra vedada.
    """
    bruta = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    if list(bruta.columns) != list(COLUNAS):
        raise ValueError(f"colunas esperadas: {', '.join(COLUNAS)}")
    if bruta.empty:
        return vazia()
    linhas = []
    for posicao, linha in enumerate(bruta.to_dict("records"), start=2):
        formatado = documento_de_empresa(linha["cnpj"])
        if formatado is None:
            raise ValueError(f"linha {posicao}: CNPJ que não confere")
        if linha["registro"] not in NOMES_DOS_REGISTROS:
            raise ValueError(f"linha {posicao}: registro que a ficha não conhece")
        if not linha["texto"].strip():
            raise ValueError(f"linha {posicao}: texto vazio")
        if vedadas := palavras_vedadas_em(linha["texto"]):
            raise ValueError(f"linha {posicao}: palavra vedada {vedadas}")
        linhas.append(
            {
                "cnpj": "".join(c for c in formatado if c.isalnum()),
                "registro": linha["registro"],
                "aconteceu_em": (
                    _data(linha["aconteceu_em"], posicao, "aconteceu_em")
                    if linha["aconteceu_em"]
                    else pd.NaT
                ),
                "recebida_em": _data(linha["recebida_em"], posicao, "recebida_em"),
                "texto": linha["texto"].strip(),
            }
        )
    return pd.DataFrame(linhas, columns=list(COLUNAS))


def da_empresa(contestadas: pd.DataFrame, raiz: str) -> pd.DataFrame:
    """As contestações de qualquer estabelecimento da empresa (a raiz do CNPJ, 8 dígitos)."""
    if contestadas.empty:
        return contestadas
    return contestadas[contestadas["cnpj"].str[:RAIZ_DO_CNPJ] == raiz]
