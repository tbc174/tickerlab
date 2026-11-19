"""Tabelas de apoio do Comex Stat (série T, PR T8): o nome de cada URF (porto, aeroporto ou posto da Receita)
e de cada via de transporte, para ler os códigos que `comex_preco_medio` guarda (`urf`) e que o MDIC usa
nos CSVs de via (`CO_VIA`).

São `URF.csv` e `VIA.csv`, do mesmo diretório `tabelas/` do MDIC que o arquivista já guarda (família
`comexstat`; dados abertos de uso livre, inclusive comercial, com atribuição Secex/MDIC, que vem de
`src/banco/coletas.py`). Em latin-1, com `;` e aspas. Os arquivos não trazem data: o primeiro valor vale
desde o dia da coleta que o trouxe (`foto`), e um nome que o MDIC mude depois vira linha nova, desde o dia
em que foi visto (`base/setoriais/revisoes.py`).

O `NO_URF` da fonte repete o código na frente ("0510353 - IRF ILHEUS"); o nome fica sem ele.
"""

import io
import re

import pandas as pd

from base.setoriais.comum import sem_espacos

FONTE_DOS_ORIGINAIS = "comexstat"
CODIFICACAO = "latin-1"
ARQUIVOS = {
    "URF": re.compile(r"/tabelas/URF\.csv$"),
    "VIA": re.compile(r"/tabelas/VIA\.csv$"),
}
COLUNAS_DA_URF = ("urf", "nome", "disponivel_em")
COLUNAS_DA_VIA = ("via", "nome", "disponivel_em")
CHAVE_DA_URF = ("urf",)
CHAVE_DA_VIA = ("via",)
CARIMBOS: tuple[str, ...] = ()
SEPARADOR_DO_CODIGO = " - "


def destino_da_urf(url: str) -> str | None:
    """O nome do Parquet da tabela de URF (`urf`); qualquer outro endereço fica de fora."""
    return "urf" if ARQUIVOS["URF"].search(url) else None


def destino_da_via(url: str) -> str | None:
    """O nome do Parquet da tabela de vias (`via`); qualquer outro endereço fica de fora."""
    return "via" if ARQUIVOS["VIA"].search(url) else None


def _ler_csv(conteudo: bytes, codigo: str, nome: str) -> pd.DataFrame:
    bruto = pd.read_csv(
        io.BytesIO(conteudo),
        sep=";",
        dtype=str,
        encoding=CODIFICACAO,
        usecols=[codigo, nome],
        keep_default_na=False,
    )
    return pd.DataFrame(
        {
            "codigo": sem_espacos(bruto[codigo]),
            "nome": sem_espacos(bruto[nome], vazio_vira_none=True),
        }
    )


def ler_urf(conteudo: bytes, url: str = "") -> pd.DataFrame:
    """`URF.csv`: o código e o nome da unidade, sem o código repetido na frente do nome."""
    tabela = _ler_csv(conteudo, "CO_URF", "NO_URF")
    tabela["nome"] = [
        _sem_o_codigo(c, n)
        for c, n in zip(tabela["codigo"], tabela["nome"], strict=True)
    ]
    return _com_data(tabela.rename(columns={"codigo": "urf"}), COLUNAS_DA_URF)


def ler_via(conteudo: bytes, url: str = "") -> pd.DataFrame:
    """`VIA.csv`: o código e o nome da via (marítima, aérea, rodoviária...)."""
    tabela = _ler_csv(conteudo, "CO_VIA", "NO_VIA")
    return _com_data(tabela.rename(columns={"codigo": "via"}), COLUNAS_DA_VIA)


def _sem_o_codigo(codigo: str, nome: str | None) -> str | None:
    prefixo = codigo + SEPARADOR_DO_CODIGO
    return nome.removeprefix(prefixo) if nome else nome


def _com_data(tabela: pd.DataFrame, colunas: tuple[str, ...]) -> pd.DataFrame:
    """`disponivel_em` fica vazio: a carga põe o dia da coleta."""
    tabela["disponivel_em"] = pd.to_datetime(pd.Series(pd.NaT, index=tabela.index))
    return tabela.reindex(columns=list(colunas))
