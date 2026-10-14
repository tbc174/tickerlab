"""As rotas da API de leitura (v1). Todas exigem a API ligada e uma conta logada (src/api_v1/acesso.py)."""

import os
from collections.abc import Callable
from datetime import date, timedelta
from typing import Annotated, Literal, TypeVar

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src import analises
from src import juros_e_inflacao as ji
from src import linha_do_tempo as ldt
from src.api_v1 import esquemas
from src.api_v1.acesso import (
    VARIAVEL_DO_CLIENT_ID,
    conta_com_acesso,
    exigir_api_ligada,
)
from src.api_v1.contexto import (
    ContextoDoAtivo,
    PoucosDadosError,
    carregar_ativo,
    cdi_entre,
)
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.eventos import Evento, eventos_dos_tickers
from src.banco.usuarios import Usuario
from src.bcb import FUSO
from src.cdi import CDIIndisponivelError
from src.comparacao import MAX_ATIVOS, interpretar_tickers
from src.dados import DadosIndisponiveisError, normalizar_ticker
from src.estrategias import ESTRATEGIAS, gerar_posicao
from src.indicadores import MOTIVO_SEM_ANUALIZAR
from src.metricas import resumir_desempenho
from src.planos import limites_do

# o que a tela aceita: letras, números e os símbolos de índices e moedas (^BVSP, BTC-USD, USDBRL=X)
FORMATO_DO_TICKER = r"^[A-Za-z0-9^][A-Za-z0-9.^=\-]{0,19}$"
CUSTO_MAXIMO = 0.05  # 5% por operação: acima disso é erro de digitação
Ticker = Annotated[str, Query(pattern=FORMATO_DO_TICKER, max_length=20)]
Periodo = Literal["6mo", "1y", "2y", "5y"]  # os PERIODOS_VALIDOS de src/dados.py
Taxa = Annotated[float | None, Query(ge=0, le=1)]  # sem taxa: o CDI do período
SEM_TAXA = 0.0  # para páginas que não usam taxa livre de risco (não baixa o CDI à toa)

router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])

# a conta logada cujo plano abre a página da rota (403 com o motivo, se não abre)
Conta = Annotated[Usuario, Depends(conta_com_acesso)]


class LimitesV1(BaseModel):
    simulacoes: int | None  # null = sem limite
    favoritos: int
    ativos_na_carteira: int
    relatorios_por_dia: int | None
    recursos: list[str]


class EuV1(BaseModel):
    """Quem está logado: só o necessário para a tela (sem e-mail)."""

    nome: str | None
    plano: str
    administrador: bool
    limites: LimitesV1


class ConfiguracaoV1(BaseModel):
    """O que a tela nova precisa antes do login (sem segredo: o client ID vai no endereço do Google)."""

    google_client_id: str | None  # null: login da API não configurado neste servidor


@router.get("/configuracao")
def configuracao() -> ConfiguracaoV1:
    """Pública (sem token), mas só com a API ligada, como as outras."""
    return ConfiguracaoV1(
        google_client_id=os.environ.get(VARIAVEL_DO_CLIENT_ID, "").strip() or None
    )


@router.get("/eu")
def eu(conta: Conta) -> EuV1:
    limites = limites_do(conta.plano)
    return EuV1(
        nome=conta.nome,
        plano=conta.plano,
        administrador=conta.e_admin,
        limites=LimitesV1(
            simulacoes=limites.simulacoes,
            favoritos=limites.favoritos,
            ativos_na_carteira=limites.ativos_na_carteira,
            relatorios_por_dia=limites.relatorios_por_dia,
            recursos=sorted(limites.recursos),
        ),
    )


T = TypeVar("T")


def _com_o_ativo(ticker: str, periodo: str, taxa: float | None) -> ContextoDoAtivo:
    """Carrega o ativo ou responde 404 (sem dados) ou 422 (período curto demais)."""
    try:
        return carregar_ativo(ticker, periodo, taxa)
    except DadosIndisponiveisError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except PoucosDadosError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro


def _ou_422(conta: Callable[[], T]) -> T:
    try:
        return conta()
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro


@router.get("/visao-geral")
def visao_geral(
    _conta: Conta,
    ticker: Ticker,
    periodo: Periodo = "2y",
    taxa: Taxa = None,
    confianca_do_var: Annotated[int, Query(ge=90, le=99)] = 95,
) -> esquemas.VisaoGeralV1:
    return montar_visao_geral(_com_o_ativo(ticker, periodo, taxa), confianca_do_var)


def montar_visao_geral(
    c: ContextoDoAtivo, confianca_do_var: int
) -> esquemas.VisaoGeralV1:
    """A resposta da visão geral de um ativo já carregado (a rota e os testes do React usam)."""
    painel = analises.painel_de_numeros(
        c.fechamento, c.retorno, c.taxa_livre_de_risco, confianca_do_var
    )
    return esquemas.VisaoGeralV1(
        ativo=esquemas.de_ativo(c),
        painel=esquemas.de_painel(painel),
        curva=esquemas.em_base_100(c.fechamento),
        motivo_sem_anualizar=(
            MOTIVO_SEM_ANUALIZAR if pd.isna(painel.retorno_anualizado) else None
        ),
    )


@router.get("/risco")
def risco(
    _conta: Conta,
    ticker: Ticker,
    periodo: Periodo = "2y",
    taxa: Taxa = None,
    janela: Annotated[int, Query(ge=5, le=252)] = 20,
) -> esquemas.RiscoDoAtivoV1:
    c = _com_o_ativo(ticker, periodo, taxa)
    resumo = analises.risco_ao_longo_do_tempo(c.fechamento, c.retorno, janela)
    return esquemas.RiscoDoAtivoV1(
        ativo=esquemas.de_ativo(c), risco=esquemas.de_risco(resumo)
    )


@router.get("/retorno-mensal")
def retorno_mensal(
    _conta: Conta, ticker: Ticker, periodo: Periodo = "2y", taxa: Taxa = None
) -> esquemas.RetornoMensalDoAtivoV1:
    c = _com_o_ativo(ticker, periodo, taxa)
    return esquemas.RetornoMensalDoAtivoV1(
        ativo=esquemas.de_ativo(c),
        retorno_mensal=esquemas.de_retorno_mensal(analises.retorno_mensal(c.retorno)),
    )


@router.get("/comparacao")
def comparacao(
    _conta: Conta,
    ticker: Ticker,
    com: Annotated[list[str], Query(max_length=MAX_ATIVOS - 1)],
    periodo: Periodo = "2y",
    taxa: Taxa = None,
) -> esquemas.ComparacaoDoAtivoV1:
    """O ativo contra até MAX_ATIVOS - 1 outros, nos dias em que todos têm preço."""
    outros = [normalizar_ticker(t) for t in interpretar_tickers(",".join(com))]
    c = _com_o_ativo(ticker, periodo, taxa)
    fechamentos, sem_dados = {c.ticker: c.fechamento}, []
    for outro in dict.fromkeys(t for t in outros if t != c.ticker):
        try:
            fechamentos[outro] = carregar_ativo(outro, periodo, 0.0).fechamento
        except (DadosIndisponiveisError, PoucosDadosError):
            sem_dados.append(outro)
    resumo = analises.comparacao_de_ativos(fechamentos, c.taxa_livre_de_risco)
    return esquemas.ComparacaoDoAtivoV1(
        ativo=esquemas.de_ativo(c),
        comparacao=esquemas.de_comparacao(resumo),
        sem_dados=sem_dados,
    )


class PedidoDeBacktestV1(BaseModel):
    ticker: str = Field(pattern=FORMATO_DO_TICKER, max_length=20)
    periodo: Periodo = "2y"
    estrategia: str
    parametros: dict[str, int | float | str] = Field(
        default_factory=dict, max_length=10
    )
    custo_por_operacao: float = Field(CUSTO_PADRAO_POR_OPERACAO, ge=0, le=CUSTO_MAXIMO)
    taxa: float | None = Field(None, ge=0, le=1)


@router.post("/backtest")
def backtest(_conta: Conta, pedido: PedidoDeBacktestV1) -> esquemas.BacktestDoAtivoV1:
    """O backtest simples (sem proteções, Monte Carlo nem grade): a estratégia com os custos."""
    if pedido.estrategia not in ESTRATEGIAS:
        raise HTTPException(status_code=422, detail="Estratégia desconhecida.")
    c = _com_o_ativo(pedido.ticker, pedido.periodo, pedido.taxa)
    return _ou_422(
        lambda: montar_backtest(
            c, pedido.estrategia, pedido.parametros, pedido.custo_por_operacao
        )
    )


def montar_backtest(
    c: ContextoDoAtivo,
    estrategia: str,
    parametros: dict[str, int | float | str],
    custo_por_operacao: float,
) -> esquemas.BacktestDoAtivoV1:
    """O backtest de um ativo já carregado (a rota e os testes do React usam). `ValueError` se um
    parâmetro não servir à estratégia."""
    posicao = gerar_posicao(estrategia, c.dados, **parametros)
    resultado = executar_backtest(c.fechamento, posicao, custo_por_operacao)
    metricas = resumir_desempenho(
        resultado.retorno, resultado.posicao, None, c.taxa_livre_de_risco
    )
    usados = {**ESTRATEGIAS[estrategia].parametros_padrao(), **parametros}
    return esquemas.BacktestDoAtivoV1(
        ativo=esquemas.de_ativo(c),
        estrategia=estrategia,
        parametros=usados,
        custo_por_operacao=custo_por_operacao,
        backtest=esquemas.de_backtest(resultado, metricas),
    )


def hoje_no_brasil() -> date:
    """O dia de hoje em Brasília (o servidor roda em UTC); os testes fixam o dia."""
    return pd.Timestamp.now(tz=FUSO).date()


def _series_de_juros(dia: date) -> dict[str, ji.SerieLida]:
    """As séries do Banco Central no acervo; vazio se o banco ainda não tem a tabela."""
    try:
        with obter_engine().connect() as conexao:
            return ji.ler_series(conexao, dia)
    except Exception as erro:
        if tabela_inexistente(erro):
            return {}
        raise


@router.get("/juros-e-inflacao")
def juros_e_inflacao(_conta: Conta) -> esquemas.JurosEInflacaoV1:
    """Selic, CDI, IPCA, juro real e o Focus de hoje; 503 se as séries não foram coletadas."""
    hoje = hoje_no_brasil()
    lidas = _series_de_juros(hoje)
    if not lidas:
        raise HTTPException(
            status_code=503,
            detail="As séries do Banco Central ainda não foram coletadas neste servidor.",
        )
    try:
        inicio = pd.Timestamp(hoje - timedelta(days=ji.DIAS_DE_CDI))
        cdi = cdi_entre(inicio, pd.Timestamp(hoje))
    except CDIIndisponivelError:
        cdi = None  # o painel deixa o CDI e o juro real em branco e avisa
    return esquemas.de_juros_e_inflacao(ji.montar_painel(lidas, cdi, hoje), hoje)


def _eventos_do_ativo(ticker: str, desde: date) -> list[Evento]:
    """Os acontecimentos do ativo desde `desde`; vazio se o banco não tem o Research."""
    try:
        with obter_engine().connect() as conexao:
            return eventos_dos_tickers(
                conexao, [ticker], desde, limite=ldt.LIMITE_DE_EVENTOS
            )
    except Exception as erro:
        if tabela_inexistente(erro):
            return []
        raise


@router.get("/linha-do-tempo")
def linha_do_tempo(
    _conta: Conta,
    ticker: Ticker,
    periodo: Periodo = "2y",
    materialidade_minima: Annotated[
        int, Query(ge=0, le=100)
    ] = ldt.MATERIALIDADE_PADRAO,
) -> esquemas.LinhaDoTempoDoAtivoV1:
    """A curva em base 100 (nunca o preço bruto) e os documentos da CVM ou da SEC do período."""
    c = _com_o_ativo(ticker, periodo, SEM_TAXA)
    eventos = _eventos_do_ativo(c.ticker, c.fechamento.index[0].date())
    return montar_linha_do_tempo(c, eventos, materialidade_minima)


def montar_linha_do_tempo(
    c: ContextoDoAtivo, eventos: list[Evento], materialidade_minima: int
) -> esquemas.LinhaDoTempoDoAtivoV1:
    """A resposta da linha do tempo de um ativo já carregado (a rota e os testes do React usam)."""
    linha = ldt.montar_linha_do_tempo(c.fechamento, eventos, materialidade_minima)
    return esquemas.LinhaDoTempoDoAtivoV1(
        ativo=esquemas.de_ativo(c), linha_do_tempo=esquemas.de_linha_do_tempo(linha)
    )


def openapi_v1() -> dict:
    """O esquema OpenAPI só da v1 (o contrato publicado em `docs/api/openapi-v1.json`)."""
    from fastapi import FastAPI

    app = FastAPI(title="TickerLab API (leitura)", version="1")
    app.include_router(router)
    return app.openapi()
