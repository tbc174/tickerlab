"""Coleta as séries do IBGE pelo SIDRA e guarda cada valor com a safra (ADR 0024 do autor).

    python -m scripts.atualizar_series_ibge

LSPA, PAM (por município e por UF), PMC e PMS, PIM-PF, IPP, SINAPI, IPCA, IPCA-15 e INPC por item, silvicultura, rebanhos e população (`src/ibge_sidra.py`). Na primeira vez de
cada tabela busca desde 2010; depois, só uma janela recente, longa o bastante para pegar as
revisões (a LSPA revisa a safra todo mês). Valor igual ao guardado não grava nada; valor revisto
vira uma safra nova, sem apagar a anterior ("como estava em D" nunca traz revisão posterior a D).
Cada resposta do SIDRA fica no registro de coletas e no acervo.

Roda fora do app (no servidor de casa, uma vez por dia). Uma tabela fora do ar não impede as
outras; a tarefa sai com erro para o alarme avisar, e o dia seguinte tenta de novo.
"""

import argparse
import logging
import sys
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime

import pandas as pd
import requests
import sqlalchemy as sa

from src import bcb, ibge_sidra, rede
from src.banco import series as acervo_de_series
from src.banco.coletas import buscar_com_registro
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import observacoes
from src.configuracao import url_do_banco
from src.ibge_sidra import COLETAS, Coleta, Valor

log = logging.getLogger("tickerlab.series_ibge")

PRIMEIRO_ANO = 2010
MESES_DE_REVISAO = 24  # a LSPA revisa o ano em curso; o IPCA e a PMC revisam menos
ANOS_DE_REVISAO = 2  # PAM: a divulgação do ano seguinte pode corrigir o anterior
TEMPO_LIMITE = 120  # segundos: o SIDRA demora em pedidos grandes
FONTE = "ibge-sidra"


def _ja_coletada(conexao: sa.Connection, tabela: int) -> bool:
    return (
        conexao.execute(
            sa.select(observacoes.c.id)
            .where(observacoes.c.serie.like(f"{FONTE}-{tabela}-%"))
            .limit(1)
        ).first()
        is not None
    )


def _mes_atras(hoje: date, meses: int) -> tuple[int, int]:
    indice = hoje.year * 12 + hoje.month - 1 - meses
    return indice // 12, indice % 12 + 1


def periodo_da_coleta(coleta: Coleta, hoje: date, primeira_vez: bool) -> str:
    """O período pedido: tudo desde 2010 na primeira vez, a janela de revisão nas seguintes."""
    if coleta.frequencia == "anual":
        inicio = PRIMEIRO_ANO if primeira_vez else hoje.year - ANOS_DE_REVISAO
        return f"{inicio}-{hoje.year}"
    ano, mes = (PRIMEIRO_ANO, 1) if primeira_vez else _mes_atras(hoje, MESES_DE_REVISAO)
    return f"{ano}{mes:02d}-{hoje.year}{hoje.month:02d}"


def _ler_pedido(url: str, buscar: Callable[..., requests.Response]) -> list[Valor]:
    resposta = buscar(url, timeout=TEMPO_LIMITE)
    resposta.raise_for_status()
    return ibge_sidra.ler_resposta(resposta.json())


def _gravar(motor: sa.Engine, coleta: Coleta, valores: list[Valor], safra: date) -> int:
    por_serie: dict[str, list[Valor]] = defaultdict(list)
    for v in valores:
        if v.valor is not None:
            por_serie[ibge_sidra.codigo_da_serie(coleta.tabela, v)].append(v)
    novas = 0
    with motor.begin() as conexao:
        for codigo, da_serie in por_serie.items():
            acervo_de_series.garantir_serie(
                conexao,
                ibge_sidra.serie_do_acervo(
                    coleta.tabela, da_serie[0], coleta.frequencia
                ),
            )
            serie = pd.Series(
                [v.valor for v in da_serie],
                index=pd.to_datetime([v.referencia for v in da_serie]),
            )
            novas += acervo_de_series.gravar(conexao, codigo, serie, safra)
    return novas


def coletar_tabela(
    motor: sa.Engine,
    coleta: Coleta,
    hoje: date,
    buscar: Callable[..., requests.Response],
) -> int:
    """Busca uma tabela do SIDRA e grava as datas novas e as revistas. Devolve quantas linhas."""
    with motor.connect() as conexao:
        primeira_vez = not _ja_coletada(conexao, coleta.tabela)
    novas = 0
    for url in coleta.urls(periodo_da_coleta(coleta, hoje, primeira_vez)):
        valores = ibge_sidra.cortar_futuro(_ler_pedido(url, buscar), hoje)
        if coleta.soma_o_total_do_cafe:
            valores = ibge_sidra.somar_total_do_cafe(valores)
        if coleta.descarta_series_vazias:
            valores = ibge_sidra.descartar_series_vazias(valores)
        novas += _gravar(motor, coleta, valores, hoje)
    return novas


def coletar_tudo(
    motor: sa.Engine,
    hoje: date,
    buscar: Callable[..., requests.Response] = rede.get_com_agente,
    so: str | None = None,
) -> bool:
    """Roda cada tabela (ou só a de nome `so`); devolve False se alguma falhou (as outras seguem)."""
    buscar = buscar_com_registro(FONTE, buscar)
    tudo_certo = True
    for coleta in COLETAS:
        if so is not None and coleta.nome != so:
            continue
        try:
            log.info(
                "%s: %s valores novos ou revistos",
                coleta.nome,
                coletar_tabela(motor, coleta, hoje, buscar),
            )
        except (
            ibge_sidra.RespostaInesperada,
            requests.RequestException,
            sa.exc.SQLAlchemyError,
        ) as erro:
            log.error("%s: falhou (%s: %s)", coleta.nome, type(erro).__name__, erro)
            tudo_certo = False
    return tudo_certo


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "--so",
        choices=[coleta.nome for coleta in COLETAS],
        help="coleta só esta tabela (o café usa pam-municipal)",
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        return (
            0 if coletar_tudo(motor, datetime.now(bcb.FUSO).date(), so=opcoes.so) else 1
        )
    finally:
        motor.dispose()


if __name__ == "__main__":
    sys.exit(main())
