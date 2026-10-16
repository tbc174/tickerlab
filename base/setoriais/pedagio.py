"""Tráfego nas praças de pedágio (série 5 da base de ML, PR 1; ADR 0081), no formato de cada fonte.

**ANTT** (rodovias federais concedidas), um CSV por ano em latin-1, três esquemas (lidos em 16/10/2026):

- 2010 a 2023: o anual, por mês (`mes_ano` = "01/MM/AAAA"), com `categoria` ("Categoria 1"...);
- 2024 em diante: o `_mensal_consolidado`, por mês (`mes_ano` = "MM/AAAA"), com `categoria_eixo` (o
  número de eixos: "2"..."12"). O `2024.csv` sem sufixo e os `_diario` são por dia: o mesmo tráfego
  outra vez, e ficam fora (somar os dois contaria em dobro). Os JSON repetem os CSV.

Nada é convertido de um esquema para o outro: a coluna `esquema` diz qual vale na linha. A chave da
empresa é o nome da concessionária como a ANTT escreve (`concessionaria`), ligado ao CNPJ só pela tabela
conferida (`base/empresa_serie.py`). Os anuais foram recarregados em 03/12/2024: a data do arquivo não
diz quando o mês saiu, e `disponivel_em` vem do prazo medido (`prazos.disponivel_pedagio`).
"""

import io
import re

import pandas as pd

from base.setoriais import prazos
from base.setoriais.comum import sem_espacos

FONTE_DA_ANTT = "antt-pedagio"
CODIFICACAO_DA_ANTT = "latin-1"
# o último ano em que o arquivo anual (sem sufixo) é por mês; de 2024 em diante ele é por dia
ULTIMO_ANUAL_POR_MES = 2023
ANUAL = re.compile(r"-(\d{4})\.csv$")
CONSOLIDADO = re.compile(r"-(\d{4})_mensal_consolidado\.csv$")
TEXTOS_DA_ANTT = (
    "concessionaria", "praca", "sentido", "tipo_cobranca", "categoria", "categoria_eixo",
    "tipo_de_veiculo",
)  # fmt: skip
COLUNAS_DA_ANTT = (
    "competencia", *TEXTOS_DA_ANTT, "volume_total", "esquema", "arquivo", "disponivel_em",
)  # fmt: skip


def arquivo_da_antt(url: str) -> str | None:
    """O ano que o arquivo traz por mês (o nome do Parquet), ou None se ele fica fora."""
    nome = url.rsplit("/", 1)[-1]
    if achado := CONSOLIDADO.search(nome):
        return achado.group(1)
    if (achado := ANUAL.search(nome)) and int(achado.group(1)) <= ULTIMO_ANUAL_POR_MES:
        return achado.group(1)
    return None


def _numero(serie: pd.Series) -> pd.Series:
    """ "277638,00" → 277638.0 (vírgula decimal, sem separador de milhar)."""
    return pd.to_numeric(
        serie.str.strip().str.replace(",", ".", regex=False), errors="coerce"
    )


def _competencia(mes_ano: pd.Series) -> pd.Series:
    """ "01/03/2010" ou "03/2010" → 2010-03-31 (o dia do anual é sempre 01, salvo erro de digitação)."""
    mes = pd.to_datetime(mes_ano.str.strip().str[-7:], format="%m/%Y")
    return mes + pd.offsets.MonthEnd(0)


def ler_antt(conteudo: bytes, url: str) -> pd.DataFrame:
    """Um CSV mensal da ANTT (anual até 2023 ou consolidado), com a competência e `disponivel_em`."""
    bruto = pd.read_csv(
        io.BytesIO(conteudo), sep=";", dtype=str, keep_default_na=False,
        encoding=CODIFICACAO_DA_ANTT,
    )  # fmt: skip
    bruto.columns = [c.strip().lower() for c in bruto.columns]
    tabela = pd.DataFrame(
        {
            c: sem_espacos(bruto[c], vazio_vira_none=True)
            if c in bruto
            else pd.Series(None, index=bruto.index, dtype=object)
            for c in TEXTOS_DA_ANTT
        }
    )
    tabela["competencia"] = _competencia(bruto["mes_ano"])
    tabela["volume_total"] = _numero(bruto["volume_total"]).astype(float)
    tabela["esquema"] = "eixos" if "categoria_eixo" in bruto else "categoria"
    tabela["arquivo"] = url.rsplit("/", 1)[-1]
    tabela["disponivel_em"] = prazos.disponivel_pedagio(tabela["competencia"])
    return tabela.reindex(columns=list(COLUNAS_DA_ANTT))
