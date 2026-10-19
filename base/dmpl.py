"""DMPL "como era na data" (série T1): a demonstração das mutações do patrimônio líquido.

A DMPL é uma matriz: cada conta (saldo inicial, lucro do período, dividendos...) tem um valor por
**coluna** do patrimônio (capital social, reservas de lucro, lucros acumulados...). Os dados abertos
da CVM trazem a coluna em `COLUNA_DF`, que as outras demonstrações não têm; por isso a DMPL é uma
tabela própria (`dmpl_como_era`), com a coluna no fato, e as mesmas regras de data de
`base/ponto_no_tempo.py`.

**Coluna canônica:** o mesmo conceito aparece com nomes diferentes nos dados abertos e no ENET
("Reservas de Capital, Opções Outorgadas e Ações em Tesouraria" e "Reservas de Capital, Outorgadas
em Ações em Tesouraria"; "Patrimônio Líquido" e "Total do Patrimônio Líquido"). `coluna_canonica`
os junta num nome curto, para a versão do ENET e a dos dados abertos serem o mesmo fato. Texto que
nenhuma regra reconhece vira o próprio nome sem acento (nunca se perde); coluna em branco (8.302
linhas nos dados abertos de 2010 a 2026, medido em 19/10/2026) vira `sem_coluna`.
"""

import io
import re
import unicodedata
import zipfile
from collections.abc import Iterable
from typing import TYPE_CHECKING

import pandas as pd

from base.contas_cvm import COLUNAS, COLUNAS_DO_CSV, ler_csv_da_cvm, normalizar_contas
from base.ponto_no_tempo import COLUNAS_DA_BASE, FATO, Formato, com_divulgacao

if TYPE_CHECKING:
    from base.enet import DocumentoEnet

DMPL = "DMPL"
COLUNAS_DA_DMPL = (*COLUNAS, "coluna")
ARQUIVO_DA_DMPL = re.compile(r"_DMPL_(con|ind)_\d{4}\.csv$")
SEM_COLUNA = "sem_coluna"
FORMATO_DMPL = Formato(
    fato=(*FATO[:4], "coluna", *FATO[4:]),
    colunas_lidas=COLUNAS_DA_DMPL,
    colunas_da_base=(*COLUNAS_DA_BASE[:5], "coluna", *COLUNAS_DA_BASE[5:]),
)
# (o que o texto sem acento precisa ter, a coluna canônica), na ordem: a primeira que casa vence.
# "Não controladores" antes de "consolidado", e os dois antes de "patrimônio líquido", porque
# "Patrimônio Líquido - Acionistas Não Controladores" tem as três expressões.
REGRAS_DA_COLUNA = (
    (("nao control",), "nao_controladores"),
    (("patrimonio liquido", "consolidado"), "patrimonio_liquido_consolidado"),
    (("patrimonio liquido",), "patrimonio_liquido"),
    (("capital social",), "capital_social"),
    (("reservas de capital",), "reservas_de_capital"),
    (("reservas de lucro",), "reservas_de_lucro"),
    (("reavaliacao",), "reservas_de_reavaliacao"),
    (("lucro", "prejuizo"), "lucros_acumulados"),
    (("outros resultados abrangentes",), "outros_resultados_abrangentes"),
    (("ajuste", "avaliacao patrimonial"), "ajustes_de_avaliacao_patrimonial"),
)


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower().strip()


def coluna_canonica(texto: str) -> str:
    """O nome curto da coluna da DMPL ("Reservas de Lucro" → "reservas_de_lucro")."""
    simples = _sem_acento(texto)
    if not simples:
        return SEM_COLUNA
    for expressoes, canonica in REGRAS_DA_COLUNA:
        if all(expressao in simples for expressao in expressoes):
            return canonica
    return re.sub(r"[^a-z0-9]+", "_", simples).strip("_")


def ler_dmpl(zip_bytes: bytes, documento: str) -> pd.DataFrame:
    """A DMPL (individual e consolidada) de um zip da CVM, com a coluna canônica.

    Mesma leitura de `base/contas_cvm.ler_contas` (valor em reais, escala desconhecida recusada);
    linhas repetidas idênticas saem.
    """
    partes = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as arquivo:
        for nome in sorted(arquivo.namelist()):
            achado = ARQUIVO_DA_DMPL.search(nome)
            if not achado:
                continue
            bruto = ler_csv_da_cvm(
                arquivo, nome, colunas={*COLUNAS_DO_CSV, "COLUNA_DF"}
            )
            parte = normalizar_contas(bruto, documento, DMPL, achado.group(1))
            parte["coluna"] = bruto["COLUNA_DF"].map(coluna_canonica)
            partes.append(parte.drop_duplicates(ignore_index=True))
    if not partes:
        return pd.DataFrame(columns=list(COLUNAS_DA_DMPL))
    return pd.concat(partes, ignore_index=True)


def publicadas_do_enet(
    documentos: Iterable["DocumentoEnet"],
    indice: pd.DataFrame,
    *,
    cadastro: pd.DataFrame,
) -> pd.DataFrame:
    """A DMPL de cada versão lida do ENET, com a data dela (ver `com_divulgacao`)."""
    partes = [d.dmpl for d in documentos if not d.dmpl.empty]
    dmpl = (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=list(COLUNAS_DA_DMPL))
    )
    return com_divulgacao(dmpl, indice, "enet", cadastro=cadastro, formato=FORMATO_DMPL)
