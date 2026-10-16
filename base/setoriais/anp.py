"""Vendas de combustíveis por distribuidora da ANP (série 4, PR 4): líquidos, GLP e aviação, por mês,
agente regulado, produto, origem e destino, no formato da fonte.

Cada zip tem o arquivo "Vendas_Atual" (2017 em diante, com cabeçalho) e o "Vendas_Historico" (2007 a
2017; o dos líquidos vem sem cabeçalho e sem a descrição do produto). Os meses que o atual traz ficam
só com ele. A ANP escreve o nome atual da distribuidora também no passado ("VIBRA ENERGIA S.A" em
2010, quando era BR Distribuidora): o CNPJ é o mesmo, e a ligação pela B13 usa esse nome.
"""

import io
import re
import unicodedata
import zipfile

import pandas as pd

from base.setoriais import prazos

FONTE = "anp-vendas-distribuidora"
CODIFICACAO = "latin-1"
COLUNAS = (
    "competencia", "grupo", "agente", "codigo_do_produto", "nome_do_produto", "descricao_do_produto",
    "codigo_da_embalagem", "regiao_origem", "uf_origem", "regiao_destino", "uf_destino",
    "mercado_destino", "quantidade", "unidade", "arquivo", "disponivel_em",
)  # fmt: skip
# nome da coluna na fonte (sem acento, em minúsculas) → coluna da base
NOMES = {
    "ano": "ano", "mes": "mes", "agente regulado": "agente", "codigo do produto": "codigo_do_produto",
    "nome do produto": "nome_do_produto", "descricao do produto": "descricao_do_produto",
    "codigo de embalagem glp": "codigo_da_embalagem", "codigo da embalagem": "codigo_da_embalagem",
    "regiao origem": "regiao_origem", "uf origem": "uf_origem", "uf de origem": "uf_origem",
    "regiao destinatario": "regiao_destino", "uf destino": "uf_destino",
    "uf de destino": "uf_destino", "mercado destinatario": "mercado_destino",
}  # fmt: skip
# o histórico dos líquidos vem sem cabeçalho: as colunas, na ordem do arquivo
SEM_CABECALHO = (
    "ano", "mes", "agente", "codigo_do_produto", "nome_do_produto", "regiao_origem", "uf_origem",
    "regiao_destino", "uf_destino", "mercado_destino", "quantidade",
)  # fmt: skip
UNIDADE = re.compile(r"\((mil [^)]+)\)")
VENDAS = re.compile(r"_Vendas_(Atual|Historico)")


def _simples(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.replace("﻿", "").strip().strip('"').lower().split())


def _nome_da_coluna(coluna: str) -> str:
    simples = _simples(coluna)
    return (
        "quantidade"
        if simples.startswith("quantidade")
        else NOMES.get(simples, simples)
    )


def _ler_membro(arquivo: zipfile.ZipFile, nome: str) -> tuple[pd.DataFrame, str | None]:
    """O CSV de vendas, com as colunas da base, e a unidade escrita no cabeçalho (se houver)."""
    primeira = arquivo.open(nome).readline().decode(CODIFICACAO, errors="replace")
    com_cabecalho = _simples(primeira.split(";")[0]) == "ano"
    bruto = pd.read_csv(
        arquivo.open(nome), sep=";", encoding=CODIFICACAO, encoding_errors="replace",
        dtype=str, keep_default_na=False, header=0 if com_cabecalho else None,
    )  # fmt: skip
    if not com_cabecalho:
        bruto.columns = list(SEM_CABECALHO)[: len(bruto.columns)]
        return bruto, None
    unidade = next(
        (achado.group(1) for c in bruto.columns if (achado := UNIDADE.search(c))), None
    )
    return bruto.rename(columns={c: _nome_da_coluna(c) for c in bruto.columns}), unidade


def _meses(bruto: pd.DataFrame) -> list[tuple[str, str]]:
    return list(
        zip(
            bruto["ano"].str.strip(),
            bruto["mes"].str.strip().str.lstrip("0"),
            strict=True,
        )
    )


def _numero(serie: pd.Series) -> pd.Series:
    """ "1.234,5" → 1234.5 (o formato da ANP)."""
    limpo = serie.str.strip().str.replace(".", "", regex=False).str.replace(",", ".")
    return pd.to_numeric(limpo, errors="coerce")


def ler(conteudo_do_zip: bytes, grupo: str) -> pd.DataFrame:
    """As vendas de um zip da ANP (`grupo`: liquidos, glp ou aviacao), atual e histórico juntos."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nomes = sorted(
            (n for n in arquivo.namelist() if VENDAS.search(n)),
            key=lambda n: "Historico" in n,  # o atual primeiro
        )
        lidos = [(nome, *_ler_membro(arquivo, nome)) for nome in nomes]
    unidade_do_grupo = next((u for _, _, u in lidos if u), None)
    meses_do_atual: set[tuple[str, str]] = set()
    tabelas = []
    for nome, bruto, _ in lidos:
        if "Historico" in nome:
            bruto = bruto[[m not in meses_do_atual for m in _meses(bruto)]]
        else:
            meses_do_atual |= set(_meses(bruto))
        tabela = pd.DataFrame(
            {c: bruto[c].str.strip().replace("", None) for c in COLUNAS if c in bruto}
        )
        tabela["quantidade"] = _numero(bruto["quantidade"])
        tabela["competencia"] = prazos.fim_do_mes(bruto["ano"], bruto["mes"])
        tabelas.append(tabela.assign(arquivo=nome))
    juntas = pd.concat(tabelas, ignore_index=True)
    juntas["grupo"] = grupo
    juntas["unidade"] = unidade_do_grupo
    juntas["disponivel_em"] = prazos.disponivel_mensal(juntas["competencia"])
    return juntas.reindex(columns=list(COLUNAS))
