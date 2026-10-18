"""Coleta as séries macro e guarda cada valor com a safra (Radar, PR 5; ADR 0024 do autor).

    python -m scripts.atualizar_series_macro

Banco Central (SGS, PTAX e Focus), curva de juros do Tesouro dos EUA e dois índices do Yahoo
(Ibovespa e S&P 500, só para uso interno: nunca exportados). Na primeira vez busca desde 2010;
depois, só uma janela recente, longa o bastante para pegar as revisões (o IBC-Br é revisto meses
depois). Valor igual ao guardado não grava nada; valor revisto vira uma safra nova, sem apagar a
anterior. Cada arquivo baixado do BC e do Tesouro fica no registro de coletas e no acervo.

Roda fora do app (no servidor, uma vez por dia). Uma fonte fora do ar não impede as outras; a
tarefa sai com erro para o alarme avisar, e o dia seguinte tenta de novo.
"""

import logging
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta

import pandas as pd
import requests
import sqlalchemy as sa

from src import bcb, dados, precos_de_referencia, tesouro_eua
from src.banco import series as acervo_de_series
from src.banco.coletas import buscar_com_registro
from src.banco.conexao import criar_engine, migrar_para
from src.banco.series import SerieDoAcervo
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.series_macro")

INICIO_DO_ACERVO = date(2010, 1, 1)
DIAS_DE_REVISAO = 400  # IBC-Br e IGP-M são revistos meses depois da primeira divulgação
DIAS_DO_FOCUS = 14  # a pesquisa é semanal; duas semanas cobrem um dia perdido
DIAS_DO_YAHOO = 30
FIM_DO_ANO = (12, 31)  # o Focus anual se refere ao ano inteiro: guardado em 31/12

FOCUS = {"ipca": "IPCA", "selic": "Selic", "cambio": "Câmbio", "pib": "PIB Total"}
YAHOO = {
    "bvsp": ("^BVSP", "Ibovespa", "pontos"),
    "gspc": ("^GSPC", "S&P 500", "pontos"),
}

BuscarYahoo = Callable[[str, date], pd.Series | None]


# séries de terceiros que o SGS só repassa: a licença continua a do dono (o IGP-M é da FGV IBRE,
# cujos termos pedem autorização para uso comercial; licencas-por-fonte.md, 14/10/2026)
SGS_DE_TERCEIROS = {"igpm"}
SGS_MENSAIS_EM_INDICE = {
    "ibc_br",
    "icbr",
    "icbr_agro",
}  # mensais que não são "% no mês"


def serie_sgs(chave: str) -> SerieDoAcervo:
    s = bcb.SERIES[chave]
    mensal = s.unidade == "% no mês" or chave in SGS_MENSAIS_EM_INDICE
    frequencia = "mensal" if mensal else "diária"
    return SerieDoAcervo(
        f"bcb-sgs-{s.codigo}",
        s.nome,
        s.unidade,
        frequencia,
        uso_interno=chave in SGS_DE_TERCEIROS,
    )


def serie_ptax(lado: str) -> SerieDoAcervo:
    return SerieDoAcervo(f"bcb-ptax-{lado}", f"PTAX ({lado})", "R$ por US$", "diária")


def serie_focus(chave: str) -> SerieDoAcervo:
    return SerieDoAcervo(
        f"bcb-focus-{chave}",
        f"Focus: mediana para {FOCUS[chave]} no ano",
        "como no boletim Focus",
        "anual",
    )


def rotulo_do_prazo(anos: float) -> str:
    """0,5 → "6m"; 10 → "10a" (o código da série do prazo)."""
    return f"{anos * 12:g}m" if anos < 1 else f"{anos:g}a"


def serie_tesouro(anos: float) -> SerieDoAcervo:
    rotulo = rotulo_do_prazo(anos)
    return SerieDoAcervo(
        f"tesouro-eua-{rotulo}",
        f"Título do Tesouro dos EUA de {rotulo} (par yield)",
        "fração ao ano",
        "diária",
    )


def serie_yahoo(chave: str) -> SerieDoAcervo:
    _, nome, unidade = YAHOO[chave]
    return SerieDoAcervo(
        f"yahoo-{chave}", f"{nome} (fechamento)", unidade, "diária", uso_interno=True
    )


def _inicio(conexao: sa.Connection, codigo: str, hoje: date, dias: int) -> date:
    if not acervo_de_series.tem_dados(conexao, codigo):
        return INICIO_DO_ACERVO
    return max(INICIO_DO_ACERVO, hoje - timedelta(days=dias))


def _gravar(
    motor: sa.Engine, serie: SerieDoAcervo, valores: pd.Series, safra: date
) -> int:
    with motor.begin() as conexao:
        acervo_de_series.garantir_serie(conexao, serie)
        return acervo_de_series.gravar(conexao, serie.codigo, valores, safra)


def coletar_sgs(motor: sa.Engine, hoje: date, buscar: bcb.Buscar) -> int:
    novas = 0
    for chave in bcb.SERIES:
        serie = serie_sgs(chave)
        with motor.connect() as conexao:
            inicio = _inicio(conexao, serie.codigo, hoje, DIAS_DE_REVISAO)
        valores = bcb.baixar_serie_sgs(chave, inicio, hoje, hoje, buscar)
        novas += _gravar(motor, serie, valores, hoje)
    return novas


def coletar_ptax(motor: sa.Engine, hoje: date, buscar: bcb.Buscar) -> int:
    with motor.connect() as conexao:
        inicio = _inicio(conexao, serie_ptax("venda").codigo, hoje, DIAS_DE_REVISAO)
    ptax = bcb.baixar_ptax(inicio, hoje, hoje, buscar)
    return sum(_gravar(motor, serie_ptax(lado), ptax[lado], hoje) for lado in ptax)


def coletar_focus(motor: sa.Engine, hoje: date, buscar: bcb.Buscar) -> int:
    novas = 0
    for chave, indicador in FOCUS.items():
        serie = serie_focus(chave)
        with motor.connect() as conexao:
            inicio = _inicio(conexao, serie.codigo, hoje, DIAS_DO_FOCUS)
        tabela = bcb.baixar_focus(indicador, inicio, buscar, base_de_calculo=0)
        # cada pesquisa é uma safra; da mais antiga para a mais nova
        for pesquisa, linhas in tabela.groupby("data", sort=True):
            valores = pd.Series(
                linhas["mediana"].to_numpy(),
                index=[date(int(ano), *FIM_DO_ANO) for ano in linhas["ano"]],
            )
            novas += _gravar(motor, serie, valores, pd.Timestamp(pesquisa).date())
    return novas


def coletar_tesouro(motor: sa.Engine, hoje: date, buscar: bcb.Buscar) -> int:
    with motor.connect() as conexao:
        inicio = _inicio(conexao, serie_tesouro(10).codigo, hoje, DIAS_DE_REVISAO)
    novas = 0
    for ano in range(inicio.year, hoje.year + 1):
        curva = tesouro_eua.baixar_curva(ano, buscar)
        for anos in curva.columns:
            novas += _gravar(motor, serie_tesouro(float(anos)), curva[anos], hoje)
    return novas


def _tem_precos(motor: sa.Engine, familia: str) -> bool:
    with motor.connect() as conexao:
        return acervo_de_series.tem_dados(
            conexao, precos_de_referencia.SERIE_TESTEMUNHA[familia]
        )


def _gravar_precos(
    motor: sa.Engine, valores: list[precos_de_referencia.ValorMensal], hoje: date
) -> int:
    with motor.begin() as conexao:
        return precos_de_referencia.gravar_precos(conexao, valores, hoje)


def coletar_pink_sheet(motor: sa.Engine, hoje: date, buscar: bcb.Buscar) -> int:
    """Pink Sheet do Banco Mundial (mensal, sai nos primeiros dias úteis do mês)."""
    tem = _tem_precos(motor, precos_de_referencia.FAMILIA_BM)
    if not precos_de_referencia.deve_coletar(
        precos_de_referencia.FAMILIA_BM, hoje, tem
    ):
        return 0
    conteudo = precos_de_referencia.baixar_pink_sheet(buscar)
    return _gravar_precos(motor, precos_de_referencia.ler_pink_sheet(conteudo), hoje)


def coletar_fmi(motor: sa.Engine, hoje: date, buscar: bcb.Buscar) -> int:
    """Preços de commodities do FMI (mensal, perto do dia 10): os últimos 14 meses; a primeira
    vez, desde 2010, como o resto do acervo."""
    tem = _tem_precos(motor, precos_de_referencia.FAMILIA_FMI)
    if not precos_de_referencia.deve_coletar(
        precos_de_referencia.FAMILIA_FMI, hoje, tem
    ):
        return 0
    desde = hoje - timedelta(days=DIAS_DE_REVISAO) if tem else INICIO_DO_ACERVO
    conteudo = precos_de_referencia.baixar_fmi(desde, buscar)
    return _gravar_precos(motor, precos_de_referencia.ler_fmi(conteudo), hoje)


def _fechamento_do_yahoo(ticker: str, inicio: date) -> pd.Series | None:
    # a mesma consulta ao Yahoo que o app usa (colunas simples, só dias úteis)
    tabela = dados._baixar_do_yahoo(ticker, start=inicio.isoformat())
    return None if tabela is None else tabela["Close"]


def coletar_yahoo(motor: sa.Engine, hoje: date, buscar: BuscarYahoo) -> int:
    novas = 0
    for chave, (ticker, _, _) in YAHOO.items():
        serie = serie_yahoo(chave)
        with motor.connect() as conexao:
            inicio = _inicio(conexao, serie.codigo, hoje, DIAS_DO_YAHOO)
        fechamentos = buscar(ticker, inicio)
        if fechamentos is None:
            raise RuntimeError(f"O Yahoo não devolveu {ticker}.")
        novas += _gravar(motor, serie, fechamentos, hoje)
    return novas


def coletar_tudo(
    motor: sa.Engine,
    hoje: date,
    buscar: Callable[..., requests.Response] = requests.get,
    buscar_yahoo: BuscarYahoo = _fechamento_do_yahoo,
) -> bool:
    """Roda cada fonte; devolve False se alguma falhou (as outras seguem)."""
    etapas: list[tuple[str, Callable[[], int]]] = [
        ("bcb-sgs", lambda: coletar_sgs(motor, hoje, buscar_com_registro("bcb-sgs", buscar))),
        ("bcb-ptax", lambda: coletar_ptax(motor, hoje, buscar_com_registro("bcb-ptax", buscar))),
        ("bcb-focus", lambda: coletar_focus(motor, hoje, buscar_com_registro("bcb-focus", buscar))),
        ("tesouro-eua", lambda: coletar_tesouro(motor, hoje, buscar_com_registro("tesouro-eua", buscar))),
        ("bm-pink", lambda: coletar_pink_sheet(motor, hoje, buscar_com_registro("bm-pink", buscar))),
        ("fmi-pcps", lambda: coletar_fmi(motor, hoje, buscar_com_registro("fmi-pcps", buscar))),
        ("yahoo", lambda: coletar_yahoo(motor, hoje, buscar_yahoo)),
    ]  # fmt: skip
    tudo_certo = True
    for nome, etapa in etapas:
        try:
            log.info("%s: %s valores novos ou revistos", nome, etapa())
        except (
            bcb.BcbIndisponivelError,
            precos_de_referencia.PrecosIndisponiveisError,
            tesouro_eua.TesouroIndisponivelError,
            requests.RequestException,
            RuntimeError,
            sa.exc.SQLAlchemyError,
        ) as erro:
            log.error("%s: falhou (%s: %s)", nome, type(erro).__name__, erro)
            tudo_certo = False
    return tudo_certo


def main(argv: list[str] | None = None) -> int:
    del argv  # sem opções por enquanto
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        return 0 if coletar_tudo(motor, datetime.now(bcb.FUSO).date()) else 1
    finally:
        motor.dispose()


if __name__ == "__main__":
    sys.exit(main())
