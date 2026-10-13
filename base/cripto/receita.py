"""Dados abertos de criptoativos da Receita Federal (base de cripto, série 1, PR 4).

Uma planilha `.xls` mensal com o que os brasileiros declararam de operações com criptoativos desde
agosto de 2019 (exchanges no Brasil, no exterior e sem exchange; e por criptoativo). Dados abertos do
governo federal: reuso livre citando a fonte (Decreto 8.777/2016, art. 2º, III, e art. 3º, IV).

A planilha é um relatório para ler, não uma tabela: títulos e notas no alto, células mescladas, o
mês por extenso ("Agosto de 2019"). Os leitores acham as linhas de dados pelo mês e usam as colunas
na posição da planilha conferida em 13/10/2026; se a Receita mudar o desenho, os testes do arquivo
real (na coleta) acusam.

**Quando passa a valer:** o nome do arquivo traz uma data (`..._20260826.xls`) e a página diz
"publicado em" no dia seguinte; vale à 0h de Brasília do dia seguinte ao do nome. Cada planilha
traz a série inteira de novo, e a Receita pode refazer meses antigos: o acervo guarda cada arquivo
(ADR 0024) e a base usa a versão que existia na data.
"""

import io
import re
import unicodedata
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

BRASILIA = ZoneInfo("America/Sao_Paulo")
MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
PADRAO_DO_MES = re.compile(r"^([a-z]+) de (\d{4})$")
PADRAO_DA_DATA_NO_NOME = re.compile(r"_(\d{8})\.")
# Relatório nº 1 (R$ milhões): coluna da planilha → nome na base
COLUNAS_DOS_TOTAIS = {
    1: "exterior_pf_milhoes",
    2: "exterior_pj_milhoes",
    3: "exterior_milhoes",
    4: "sem_exchange_pf_milhoes",
    5: "sem_exchange_pj_milhoes",
    6: "sem_exchange_milhoes",
    7: "exchanges_no_brasil_milhoes",
    8: "total_milhoes",
}
# Relatório nº 4 (reais): criptoativo, mês, operações, valor total
COLUNA_DO_CRIPTOATIVO, COLUNA_DO_MES, COLUNA_DAS_OPERACOES, COLUNA_DO_VALOR = 0, 1, 2, 3


def abrir_planilha(conteudo: bytes) -> dict[str, pd.DataFrame]:
    """Todas as abas da planilha, sem cabeçalho (o `.xls` antigo pede o `xlrd`)."""
    return pd.read_excel(
        io.BytesIO(conteudo), sheet_name=None, header=None, engine="xlrd"
    )


def data_do_arquivo(nome: str) -> date:
    """A data que a Receita põe no nome do arquivo (`criptoativos_dados_abertos_20260826.xls`)."""
    achado = PADRAO_DA_DATA_NO_NOME.search(nome)
    if achado is None:
        raise ValueError(f"Nome de arquivo sem data: {nome}")
    return date.fromisoformat(achado.group(1))


def divulgado_em(data_no_nome: date) -> datetime:
    """Desde quando a planilha pode ser usada: 0h de Brasília do dia seguinte ao do nome (UTC)."""
    dia_seguinte = data_no_nome + timedelta(days=1)
    return datetime.combine(dia_seguinte, time(0), tzinfo=BRASILIA).astimezone(UTC)


def ler_mes(texto: object) -> date | None:
    """O primeiro dia do mês escrito por extenso ("Março de 2026"), ou None se não for um mês."""
    normalizado = _sem_acento(str(texto)).strip().lower()
    achado = PADRAO_DO_MES.match(normalizado)
    if achado is None or achado.group(1) not in MESES:
        return None
    return date(int(achado.group(2)), MESES[achado.group(1)], 1)


def ler_totais(relatorio_1: pd.DataFrame, data_no_nome: date) -> pd.DataFrame:
    """Relatório nº 1: por mês, os valores declarados por tipo, em milhões de reais."""
    meses = relatorio_1[0].map(ler_mes)
    linhas = relatorio_1[meses.notna()]
    tabela = (
        linhas[list(COLUNAS_DOS_TOTAIS)]
        .rename(columns=COLUNAS_DOS_TOTAIS)
        .astype(float)
    )
    tabela.insert(0, "mes", meses[meses.notna()])
    tabela["divulgado_em"] = divulgado_em(data_no_nome)
    return tabela.reset_index(drop=True)


def ler_por_criptoativo(
    relatorio_4: pd.DataFrame, data_no_nome: date, criptoativo: str
) -> pd.DataFrame:
    """Relatório nº 4: por mês, número de operações e valor total (reais) de um criptoativo."""
    meses = relatorio_4[COLUNA_DO_MES].map(ler_mes)
    do_criptoativo = (
        relatorio_4[COLUNA_DO_CRIPTOATIVO].astype(str).str.strip() == criptoativo
    )
    linhas = relatorio_4[meses.notna() & do_criptoativo]
    return pd.DataFrame(
        {
            "mes": meses[linhas.index],
            "criptoativo": criptoativo,
            "operacoes": linhas[COLUNA_DAS_OPERACOES].astype(int),
            "valor_total_reais": linhas[COLUNA_DO_VALOR].astype(float),
            "divulgado_em": divulgado_em(data_no_nome),
        }
    ).reset_index(drop=True)


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(letra for letra in decomposto if not unicodedata.combining(letra))
