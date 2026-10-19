"""Produção ferroviária da ANTT (SIADE; série T, PR T8): toneladas úteis (TU) e tonelada-quilômetro útil
(TKU) por mês, ferrovia, mercadoria e par de estações (origem e destino).

Um CSV por ano (`producao_origem_destino_AAAA.csv`, de 2006 a 2026), em latin-1, com `;` e o ponto como
separador de milhar ("28.774.620"). A linha do mês não traz a data em que foi publicada: o prazo é o
mensal da família (`prazos.disponivel_mensal`, 60 dias depois do fim do mês, com folga sobre o medido nas
outras agências; a única captura é de 14/10/2026 e ainda não deu para medir o atraso da ANTT, então a
regra pode atrasar um número, nunca adiantar). A ANTT revisa meses passados: a revisão vale desde o dia
da coleta (`base/setoriais/revisoes.py`).

A ferrovia vem como sigla (EFC, MRS, RMS...) e liga à empresa pela B13, na fonte `antt-siade` (a sigla
exata, sem casar nomes parecidos).
"""

import io
import re

import pandas as pd

from base.setoriais import prazos
from base.setoriais.comum import sem_espacos

FONTE = "antt-siade"
CODIFICACAO = "latin-1"
ARQUIVO = re.compile(r"producao_origem_destino_(\d{4})\.csv$")
COLUNAS = (
    "competencia", "ferrovia", "mercadoria", "estacao_de_origem", "uf_de_origem", "estacao_de_destino",
    "uf_de_destino", "toneladas_uteis", "tku", "disponivel_em",
)  # fmt: skip
CHAVE = (
    "competencia",
    "ferrovia",
    "mercadoria",
    "estacao_de_origem",
    "estacao_de_destino",
)
CARIMBOS: tuple[str, ...] = ()
TEXTOS = {
    "Ferrovia": "ferrovia", "Mercadoria_ANTT": "mercadoria", "Estacao_Origem": "estacao_de_origem",
    "UF_Origem": "uf_de_origem", "Estacao_Destino": "estacao_de_destino", "UF_Destino": "uf_de_destino",
}  # fmt: skip
NUMEROS = {"TU": "toneladas_uteis", "TKU": "tku"}


def destino(url: str) -> str | None:
    """O nome do Parquet de cada ano (`2026`); o PDF do dicionário fica de fora."""
    return achado.group(1) if (achado := ARQUIVO.search(url)) else None


def _numero(coluna: pd.Series) -> pd.Series:
    """O número com ponto de milhar ("28.774.620"); o vazio fica vazio."""
    return pd.to_numeric(
        coluna.str.strip().str.replace(".", "", regex=False), errors="coerce"
    ).astype(float)


def ler(conteudo: bytes) -> pd.DataFrame:
    """Um CSV anual do SIADE, com a competência (último dia do mês) e `disponivel_em`."""
    bruto = pd.read_csv(
        io.BytesIO(conteudo),
        sep=";",
        dtype=str,
        encoding=CODIFICACAO,
        keep_default_na=False,
    )
    bruto.columns = [c.strip() for c in bruto.columns]
    tabela = pd.DataFrame(
        {
            novo: sem_espacos(bruto[velho], vazio_vira_none=True)
            for velho, novo in TEXTOS.items()
        }
    )
    for velho, novo in NUMEROS.items():
        tabela[novo] = _numero(bruto[velho])
    mes_ano = bruto["Mes_Ano"].str.strip().str.split("/", expand=True)
    tabela["competencia"] = prazos.fim_do_mes(mes_ano[1], mes_ano[0])
    tabela["disponivel_em"] = prazos.disponivel_mensal(tabela["competencia"])
    return tabela.reindex(columns=list(COLUNAS))
