"""A edição da Newsletter lida do banco: a mesma para a página, o PDF e o envio por e-mail.

`src.newsletter` monta a edição a partir de uma `Entrada` (função pura). Aqui ficam as leituras
do banco que preenchem essa entrada: eventos, cobertura, frases de fundos e gestores, datas das
coletas e os resumos da R5. Antes isso morava no `app.py`; o envio por e-mail (etapa 5c), que
roda fora do Streamlit, precisa da mesma montagem.
"""

from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple

import pandas as pd
import sqlalchemy as sa

from src import detentores, fundos_cvm, fundos_sec, newsletter, research
from src.banco import detentores as repo_detentores
from src.banco import leituras as repo_leituras
from src.banco import negociacoes as repo_negociacoes
from src.banco.eventos import empresas_dos_tickers, eventos_dos_tickers, ultima_coleta
from src.carteira_research import Fotografia
from src.eventos import FONTE_IPE
from src.moedas import moeda_do_ticker
from src.presets import Resolucao
from src.relatorios import FUSO


class FonteDosDetentores(NamedTuple):
    fonte: str
    quem: str  # "fundos" ou "gestores"
    periodo: str  # "mês" ou "trimestre"
    simbolo: str  # "R$" ou "US$"


FONTES_DOS_DETENTORES = {
    "BRL": FonteDosDetentores(fundos_cvm.FONTE_CDA, "fundos", "mês", "R$"),
    "USD": FonteDosDetentores(fundos_sec.FONTE_13F, "gestores", "trimestre", "US$"),
}


def quando_foi_coletado(momento: datetime | None) -> str:
    if momento is None:
        return "ainda não coletado"
    if momento.tzinfo is None:  # o SQLite devolve sem fuso: foi gravado em UTC
        momento = momento.replace(tzinfo=UTC)
    return f"coletado em {momento.astimezone(FUSO):%d/%m/%Y às %H:%M}"


def _frase_do_detentor(
    codigo: str,
    linha: pd.Series,
    quem: str,
    par: tuple[date, date],
    da_cvm: bool,
    informantes: int,
) -> str:
    variacao = (
        ""
        if pd.isna(linha["variacao"])
        else f" ({linha['variacao']:+.0f} desde {par[1]:%m/%Y})"
    )
    vendidos = (
        f"; {int(linha['vendidos'])} vendidos" if da_cvm and linha["vendidos"] else ""
    )
    return (
        f"{codigo}: {int(linha['detentores'])} {quem} com a ação em {par[0]:%m/%Y}, de "
        f"{informantes} que informaram{variacao}{vendidos}."
    )


def frases_dos_detentores(
    conexao: sa.Connection, tickers: list[str]
) -> tuple[str, ...]:
    """Uma frase por ativo da lista, com a última comparação válida (fundos ou 13F)."""
    frases = []
    for moeda, escolha in FONTES_DOS_DETENTORES.items():
        do_mercado = [t for t in tickers if moeda_do_ticker(t) == moeda]
        cobertura = repo_detentores.cobertura(conexao, escolha.fonte)
        par = detentores.par_comparavel(cobertura)
        if not do_mercado or par is None:
            continue
        resumo = repo_detentores.resumo_do_mercado(conexao, escolha.fonte, par)
        tabela = detentores.comparar(resumo, *par).set_index("codigo")
        for ticker in do_mercado:
            codigo = ticker.removesuffix(".SA")
            if codigo in tabela.index:
                frases.append(
                    _frase_do_detentor(
                        codigo,
                        tabela.loc[codigo],
                        escolha.quem,
                        par,
                        escolha.fonte == fundos_cvm.FONTE_CDA,
                        cobertura[par[0]],
                    )
                )
    return tuple(frases)


def fontes_da_edicao(conexao: sa.Connection) -> tuple[tuple[str, str], ...]:
    fontes = [
        ("Eventos (CVM e SEC)", quando_foi_coletado(ultima_coleta(conexao))),
        (
            "Pessoas de dentro (CVM e SEC)",
            quando_foi_coletado(repo_negociacoes.ultima_coleta(conexao)),
        ),
    ]
    for fonte, nome in ((fundos_cvm.FONTE_CDA, "Carteiras dos fundos (CVM)"),
                        (fundos_sec.FONTE_13F, "Gestores, 13F (SEC)")):  # fmt: skip
        datas = detentores.competencias_utilizaveis(
            repo_detentores.cobertura(conexao, fonte)
        )
        fontes.append(
            (nome, f"posição de {datas[0]:%m/%Y}" if datas else "ainda não coletado")
        )
    return tuple(fontes)


def montar_edicao(
    conexao: sa.Connection,
    lista: str,
    tickers: list[str],
    janela: int,
    resolucao: Resolucao,
    gerada_em: datetime,
    carteira: Fotografia | None = None,
) -> newsletter.Edicao:
    """A edição da lista com os parâmetros da pessoa (`resolucao`), lida do banco."""
    hoje = gerada_em.astimezone(FUSO).date()
    eventos_da_lista = eventos_dos_tickers(
        conexao, tickers, hoje - timedelta(days=janela)
    )
    empresas = empresas_dos_tickers(conexao, tickers)
    protocolos = [e.protocolo for e in eventos_da_lista if e.fonte == FONTE_IPE]
    return newsletter.montar(
        newsletter.Entrada(
            lista=lista,
            tickers=tuple(tickers),
            eventos=tuple(eventos_da_lista),
            pesos=research.pesos_da_resolucao(resolucao.valores("relevancia")),
            temas=tuple(resolucao["newsletter.temas"]),
            hoje=hoje,
            janela=janela,
            max_itens=int(resolucao["newsletter.max_itens"]),
            gerada_em=gerada_em,
            detentores=frases_dos_detentores(conexao, tickers),
            fontes=fontes_da_edicao(conexao),
            cobertos=tuple(t for t in tickers if t in empresas),
            resumos=repo_leituras.resumos(conexao, FONTE_IPE, protocolos),
            carteira=carteira,
        )
    )
