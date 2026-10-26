"""O que o relatório completo de empresa lê do banco (série 2 da base de ML, PR 7; ADR 0032).

Uma consulta por pedaço: demonstrações, achados abertos, acontecimentos recentes, FRE, padrões do
corte mais recente até `hoje` e os pares do mesmo grupo de setores com a receita do último ano. A
ficha do dossiê da base vem do arquivo da noite (`src/dossie.py`), não do banco. A montagem do relatório fica em `src/relatorio_empresa.py` (sem banco).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import sqlalchemy as sa

from src.banco.demonstracoes import dados_da_empresa
from src.banco.eventos import empresas_dos_tickers
from src.banco.fre import eventos_de, proventos_de
from src.banco.modelo import (
    demonstracoes,
    documentos_financeiros,
    eventos,
    setores_cvm,
    tickers_dos_emissores,
)
from src.banco.padroes import padroes_em
from src.banco.qualidade import achados_de
from src.configuracao import preco_no_relatorio_ligado
from src.cruzamentos import com_os_cruzamentos
from src.demonstracoes import EXERCICIO
from src.dossie import caixa_do_par, dossie_da_ficha, ficha_do, ficha_do_molde_a
from src.padroes import MULTIPLOS
from src.relatorio_empresa import QUANTOS_EVENTOS, Entradas
from src.setores import SEM_GRUPO, grupo_do_setor

FUSO = ZoneInfo("America/Sao_Paulo")  # "hoje" é o do Brasil, não o do servidor (UTC)


def _tabela(conexao: sa.Connection, consulta: sa.Select) -> pd.DataFrame:
    resultado = conexao.execute(consulta)
    return pd.DataFrame(resultado.fetchall(), columns=list(resultado.keys()))


def eventos_da_empresa(conexao: sa.Connection, cnpj: str) -> pd.DataFrame:
    """Os acontecimentos mais recentes da empresa (data, rótulo, assunto e link)."""
    e = eventos
    return _tabela(
        conexao,
        sa.select(e.c.publicado_em, e.c.rotulo, e.c.assunto, e.c.link)
        .where(e.c.cnpj == cnpj)
        .order_by(e.c.publicado_em.desc(), e.c.materialidade.desc())
        .limit(QUANTOS_EVENTOS),
    )


def tickers_da_empresa(conexao: sa.Connection, cnpj: str) -> pd.DataFrame:
    """Os códigos de negociação da empresa no cadastro (código, tipo da ação e data do cadastro)."""
    t = tickers_dos_emissores
    return _tabela(
        conexao,
        sa.select(t.c.codigo, t.c.valor_mobiliario, t.c.atualizado_em)
        .where(t.c.cnpj == cnpj)
        .order_by(t.c.codigo),
    )


def pares_do_grupo(conexao: sa.Connection, setor: str) -> pd.DataFrame:
    """cnpj, empresa e receita do último ano (DFP) das empresas do mesmo grupo de setores."""
    vazio = pd.DataFrame(columns=["cnpj", "empresa", "receita"])
    grupo = grupo_do_setor(setor)
    if grupo == SEM_GRUPO:
        return vazio
    do_grupo = [
        cnpj
        for cnpj, outro in conexao.execute(
            sa.select(setores_cvm.c.cnpj, setores_cvm.c.setor)
        )
        if grupo_do_setor(outro) == grupo
    ]
    d, f = demonstracoes, documentos_financeiros
    receitas = _tabela(
        conexao,
        sa.select(d.c.cnpj, d.c.referencia, d.c.valor.label("receita"), f.c.empresa)
        .join(f, (f.c.cnpj == d.c.cnpj) & (f.c.documento == d.c.documento)
              & (f.c.referencia == d.c.referencia))
        .where(d.c.cnpj.in_(do_grupo), d.c.documento == "DFP",
               d.c.periodo == EXERCICIO, d.c.conta == "receita", d.c.fim == d.c.referencia),
    )  # fmt: skip
    if receitas.empty:
        return vazio
    ultimas = receitas.sort_values("referencia").groupby("cnpj").tail(1)
    return ultimas[["cnpj", "empresa", "receita"]].reset_index(drop=True)


def _sem_os_multiplos(padroes: pd.DataFrame) -> pd.DataFrame | None:
    """Os padrões sem P/L e P/VP, que vêm do preço do Yahoo no corte (linha 413, Y1 a, "pode" do
    Tiago em 25/10/2026); None se não sobra nenhum."""
    restantes = padroes[~padroes["indicador"].isin(MULTIPLOS)].reset_index(drop=True)
    return None if restantes.empty else restantes


def entradas_do_relatorio(
    conexao: sa.Connection,
    ticker: str,
    *,
    preco: float | None = None,
    fechamentos: pd.Series | None = None,
    hoje: date | None = None,
) -> Entradas | None:
    """Tudo o que o relatório do ticker usa; None se o ticker não tem empresa cadastrada. Com a
    trava do preço desligada, o preço, os fechamentos e os múltiplos dos padrões ficam de fora
    (tela, PDF e API leem daqui)."""
    empresa = empresas_dos_tickers(conexao, [ticker]).get(ticker)
    if empresa is None:
        return None
    com_preco = preco_no_relatorio_ligado()
    if not com_preco:
        preco, fechamentos = None, None
    cnpj, nome = empresa
    dados = dados_da_empresa(conexao, cnpj)
    hoje = hoje or datetime.now(FUSO).date()
    corte, padroes = padroes_em(conexao, hoje)
    if padroes is not None and not com_preco:
        padroes = _sem_os_multiplos(padroes)
    ficha = ficha_do_molde_a(
        ficha_do(cnpj)
    )  # o plano tranca na montagem (`montar`), não aqui
    return Entradas(
        dados=dados,
        cnpj=cnpj,
        empresa=nome,
        ticker=ticker,
        preco=preco,
        fechamentos=fechamentos,
        padroes=None if corte is None or padroes is None else (corte, padroes),
        achados=achados_de(conexao, cnpj),
        eventos=eventos_da_empresa(conexao, cnpj),
        proventos=proventos_de(conexao, cnpj),
        eventos_de_capital=eventos_de(conexao, cnpj),
        pares=pares_do_grupo(conexao, dados.setor),
        caixa_do_par=caixa_do_par,
        tickers=tickers_da_empresa(conexao, cnpj),
        dossie=(
            None
            if ficha is None
            else com_os_cruzamentos(dossie_da_ficha(ficha, hoje), ficha, hoje)
        ),
    )
