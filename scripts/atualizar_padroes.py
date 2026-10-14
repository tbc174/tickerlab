"""Recalcula os padrões por setor das notas (série 2 da base de ML, PR 4; ADR 0033).

    python -m scripts.atualizar_padroes                       (o fim do mês passado)
    python -m scripts.atualizar_padroes --desde 2021-01       (todo fim de mês desde jan/2021)
    python -m scripts.atualizar_padroes --datas 2025-12-31    (cortes escolhidos)
    python -m scripts.atualizar_padroes --com-precos          (também P/L e P/VP dos pares)
    python -m scripts.atualizar_padroes --so-o-que-falta      (o cron diário: só o corte novo)

Roda no VPS uma vez por mês, num contêiner próprio (carrega as versões de todas as empresas). Para
cada corte, usa só o que era público até ele (`src/padroes.py`). Os padrões publicados na página de
metodologia são os de 31/12 de cada ano.

Com `--com-precos`, busca o preço de cada empresa no corte (último pregão até a data, no máximo
`DIAS_DE_TOLERANCIA` antes) pelo histórico do app (Yahoo, com o cache no banco), e os múltiplos
entram nos padrões: são a régua do setor do barato, justo ou caro. Preço de exemplo nunca entra.
"""

import argparse
import logging
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import sqlalchemy as sa

from src.banco.conexao import criar_engine, migrar_para
from src.banco.padroes import (
    calcular_corte,
    cortes_gravados,
    entradas_para_padroes,
    gravar_padroes,
    tickers_por_empresa,
)
from src.configuracao import url_do_banco
from src.dados import DadosIndisponiveisError, baixar_dados

log = logging.getLogger("tickerlab.padroes")
FUSO = ZoneInfo("America/Sao_Paulo")
DIAS_DE_TOLERANCIA = (
    10  # sem pregão nos 10 dias antes do corte: sem preço (ação parada ou fora)
)
PERIODO_DOS_PRECOS = "5y"  # o maior que o app guarda
ORIGEM_PROIBIDA = "exemplo"  # dado de exemplo do app: nunca num padrão


def _historico(ticker: str) -> pd.DataFrame:
    return baixar_dados(ticker, periodo=PERIODO_DOS_PRECOS)


def _preco_ate(historico: pd.DataFrame, corte: date) -> float | None:
    ate = historico[historico.index <= pd.Timestamp(corte)]
    if ate.empty or (pd.Timestamp(corte) - ate.index[-1]).days > DIAS_DE_TOLERANCIA:
        return None
    return float(ate["Close"].iloc[-1])


def precos_nos_cortes(
    tickers: dict[str, list[str]],
    cortes: list[date],
    buscar: Callable[[str], pd.DataFrame] = _historico,
) -> dict[date, dict[str, float]]:
    """corte → (cnpj → preço): o primeiro ticker da empresa com pregão perto do corte."""
    historicos: dict[str, pd.DataFrame | None] = {}

    def historico(ticker: str) -> pd.DataFrame | None:
        if ticker not in historicos:
            try:
                dados = buscar(ticker)
            except (DadosIndisponiveisError, ValueError, OSError) as erro:
                log.warning("Sem preço de %s: %s", ticker, erro)
                dados = None
            proibido = (
                dados is not None and dados.attrs.get("origem") == ORIGEM_PROIBIDA
            )
            historicos[ticker] = None if proibido else dados
        return historicos[ticker]

    precos: dict[date, dict[str, float]] = {corte: {} for corte in cortes}
    for cnpj, lista in tickers.items():
        for corte in cortes:
            for ticker in lista:
                dados = historico(ticker)
                preco = (
                    None if dados is None or dados.empty else _preco_ate(dados, corte)
                )
                if preco is not None:
                    precos[corte][cnpj] = preco
                    break
    return precos


def fim_do_mes_passado(hoje: date) -> date:
    return hoje.replace(day=1) - timedelta(days=1)


def fins_de_mes(desde: str, ate: date) -> list[date]:
    """Todo último dia de mês de `desde` (AAAA-MM) até `ate`."""
    inicio = pd.Period(desde, freq="M")
    return [
        p.end_time.date()
        for p in pd.period_range(inicio, ate, freq="M")
        if p.end_time.date() <= ate
    ]


def _cortes(opcoes: argparse.Namespace, hoje: date) -> list[date]:
    if opcoes.datas:
        return sorted(date.fromisoformat(d) for d in opcoes.datas)
    ultimo = fim_do_mes_passado(hoje)
    return fins_de_mes(opcoes.desde, ultimo) if opcoes.desde else [ultimo]


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--datas", nargs="+", help="cortes AAAA-MM-DD")
    argumentos.add_argument("--desde", help="todo fim de mês desde AAAA-MM")
    argumentos.add_argument(
        "--com-precos", action="store_true", help="também P/L e P/VP (busca os preços)"
    )
    argumentos.add_argument(
        "--so-o-que-falta",
        action="store_true",
        help="pula os cortes que já estão gravados",
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cortes = _cortes(opcoes, datetime.now(FUSO).date())
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        if opcoes.so_o_que_falta:
            with motor.connect() as conexao:
                feitos = cortes_gravados(conexao)
            cortes = [c for c in cortes if c not in feitos]
            if not cortes:
                log.info("Padrões em dia: nada a calcular")
                return 0
        with motor.connect() as conexao:
            entradas = entradas_para_padroes(conexao)
        log.info(
            "%s versões de contas, %s empresas com setor",
            len(entradas.contas), len(entradas.setores),
        )  # fmt: skip
        precos: dict[date, dict[str, float]] = {}
        if opcoes.com_precos:
            with motor.connect() as conexao:
                tickers = tickers_por_empresa(conexao)
            precos = precos_nos_cortes(tickers, cortes)
        for corte in cortes:
            padroes = calcular_corte(entradas, corte, precos.get(corte))
            with motor.begin() as conexao:
                gravados = gravar_padroes(conexao, padroes, corte, datetime.now(UTC))
            log.info("Corte %s: %s padrões (grupo e indicador)", corte, gravados)
    except (sa.exc.SQLAlchemyError, ValueError) as erro:
        log.error("Padrões interrompidos: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
