"""Padrões por setor no banco (série 2 da base de ML, PR 4): gravar um corte e ler o mais recente.

Também junta, do banco, o que o cálculo dos padrões precisa (`entradas_para_padroes`): todas as
versões guardadas das demonstrações da CVM e a data de entrega de cada versão, o setor de cada
empresa e os achados de qualidade que tiram uma empresa do padrão.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import sqlalchemy as sa

from src.banco.modelo import (
    achados_de_qualidade,
    demonstracoes_versoes,
    documentos_financeiros_versoes,
    padroes_setoriais,
    setores_cvm,
)
from src.padroes import (
    REGRAS_QUE_TIRAM_DO_PADRAO,
    VERSAO_DOS_PADROES,
    calcular_padroes,
    contas_como_estavam,
    indicadores_da_empresa,
)
from src.setores import SEM_GRUPO, grupo_do_setor

FUSO = ZoneInfo("America/Sao_Paulo")
PREFIXO_DA_SEC = "CIK"  # empresas dos EUA: fora dos padrões (Brasil primeiro, ADR 0028)


@dataclass(frozen=True)
class Entradas:
    contas: (
        pd.DataFrame
    )  # cnpj, documento, referencia, versao, periodo, inicio, fim, conta, valor
    documentos: pd.DataFrame  # cnpj, documento, referencia, versao, recebido_em
    setores: dict[str, str]  # cnpj → setor da CVM
    achados: (
        pd.DataFrame
    )  # cnpj, valido_desde, fechado_em (só as regras que tiram do padrão)

    def em_conferencia(self, data: datetime) -> set[str]:
        """Empresas com achado aberto em `data` (ficam fora do padrão daquele corte)."""
        a = self.achados
        if a.empty:
            return set()
        aberto = (pd.to_datetime(a["valido_desde"], utc=True) <= data) & (
            a["fechado_em"].isna() | (pd.to_datetime(a["fechado_em"], utc=True) > data)
        )
        return set(a.loc[aberto, "cnpj"])


def _tabela(conexao: sa.Connection, consulta: sa.Select) -> pd.DataFrame:
    resultado = conexao.execute(consulta)
    return pd.DataFrame(resultado.fetchall(), columns=list(resultado.keys()))


def entradas_para_padroes(conexao: sa.Connection) -> Entradas:
    v, d = demonstracoes_versoes, documentos_financeiros_versoes
    so_cvm_v = ~v.c.cnpj.startswith(PREFIXO_DA_SEC)
    contas = _tabela(
        conexao,
        sa.select(
            v.c.cnpj, v.c.documento, v.c.referencia, v.c.versao, v.c.periodo,
            v.c.inicio, v.c.fim, v.c.conta, v.c.valor,
        ).where(so_cvm_v),
    )  # fmt: skip
    documentos = _tabela(
        conexao,
        sa.select(d.c.cnpj, d.c.documento, d.c.referencia, d.c.versao, d.c.recebido_em)
        .where(~d.c.cnpj.startswith(PREFIXO_DA_SEC), d.c.recebido_em.is_not(None))
        .distinct(),
    )
    setores = {
        cnpj: setor
        for cnpj, setor in conexao.execute(
            sa.select(setores_cvm.c.cnpj, setores_cvm.c.setor)
        )
    }
    q = achados_de_qualidade
    achados = _tabela(
        conexao,
        sa.select(q.c.cnpj, q.c.valido_desde, q.c.fechado_em).where(
            q.c.regra.in_(REGRAS_QUE_TIRAM_DO_PADRAO)
        ),
    )
    return Entradas(contas, documentos, setores, achados)


def gravar_padroes(
    conexao: sa.Connection,
    padroes: pd.DataFrame,
    data_de_corte: date,
    agora: datetime,
    versao: str = VERSAO_DOS_PADROES,
) -> int:
    """Grava os padrões de um corte (substitui o que havia nesse corte e versão)."""
    t = padroes_setoriais
    conexao.execute(
        sa.delete(t).where(t.c.data_de_corte == data_de_corte, t.c.versao == versao)
    )
    linhas = [
        {
            "data_de_corte": data_de_corte,
            "grupo": linha.grupo,
            "indicador": linha.indicador,
            "versao": versao,
            "empresas": int(linha.empresas),
            "percentis": dict(linha.percentis),
            "calculado_em": agora,
        }
        for linha in padroes.itertuples(index=False)
    ]
    if linhas:
        conexao.execute(sa.insert(t), linhas)
    return len(linhas)


def padroes_em(
    conexao: sa.Connection, data: date, versao: str = VERSAO_DOS_PADROES
) -> tuple[date | None, pd.DataFrame | None]:
    """(corte, padrões) do corte mais recente até `data`; (None, None) se não há."""
    t = padroes_setoriais
    corte = conexao.execute(
        sa.select(sa.func.max(t.c.data_de_corte)).where(
            t.c.data_de_corte <= data, t.c.versao == versao
        )
    ).scalar()
    if corte is None:
        return None, None
    tabela = _tabela(
        conexao,
        sa.select(t.c.grupo, t.c.indicador, t.c.empresas, t.c.percentis).where(
            t.c.data_de_corte == corte, t.c.versao == versao
        ),
    )
    return corte, tabela


def calcular_corte(entradas: Entradas, data_de_corte: date) -> pd.DataFrame:
    """Os padrões de um corte: indicadores de cada empresa como estavam no fim de `data_de_corte`."""
    fim_do_dia = datetime.combine(
        data_de_corte + timedelta(days=1), datetime.min.time(), FUSO
    )
    contas = contas_como_estavam(
        entradas.contas, entradas.documentos, pd.Timestamp(data_de_corte)
    )
    linhas = []
    for cnpj, parte in contas.groupby("cnpj"):
        setor = entradas.setores.get(str(cnpj), "")
        grupo = grupo_do_setor(setor)
        if grupo == SEM_GRUPO:
            continue
        valores = indicadores_da_empresa(parte.drop(columns="cnpj"), setor)
        linhas += [
            {"cnpj": cnpj, "grupo": grupo, "indicador": indicador, "valor": valor}
            for indicador, valor in valores.items()
        ]
    if not linhas:
        return pd.DataFrame(columns=["grupo", "indicador", "empresas", "percentis"])
    return calcular_padroes(pd.DataFrame(linhas), entradas.em_conferencia(fim_do_dia))
