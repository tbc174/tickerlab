"""As rotas da API de leitura (v1). Todas exigem a API ligada e uma conta logada (src/api_v1/acesso.py)."""

from collections.abc import Callable
from typing import Annotated, Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src import analises
from src.api_v1 import esquemas
from src.api_v1.acesso import conta_logada, exigir_api_ligada
from src.api_v1.contexto import ContextoDoAtivo, PoucosDadosError, carregar_ativo
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest
from src.banco.usuarios import Usuario
from src.comparacao import MAX_ATIVOS, interpretar_tickers
from src.dados import DadosIndisponiveisError, normalizar_ticker
from src.estrategias import ESTRATEGIAS, gerar_posicao
from src.metricas import resumir_desempenho
from src.planos import limites_do

# o que a tela aceita: letras, números e os símbolos de índices e moedas (^BVSP, BTC-USD, USDBRL=X)
FORMATO_DO_TICKER = r"^[A-Za-z0-9^][A-Za-z0-9.^=\-]{0,19}$"
CUSTO_MAXIMO = 0.05  # 5% por operação: acima disso é erro de digitação
Ticker = Annotated[str, Query(pattern=FORMATO_DO_TICKER, max_length=20)]
Periodo = Literal["6mo", "1y", "2y", "5y"]  # os PERIODOS_VALIDOS de src/dados.py
Taxa = Annotated[float | None, Query(ge=0, le=1)]  # sem taxa: o CDI do período

router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])

Conta = Annotated[Usuario, Depends(conta_logada)]


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
    c = _com_o_ativo(ticker, periodo, taxa)
    painel = analises.painel_de_numeros(
        c.fechamento, c.retorno, c.taxa_livre_de_risco, confianca_do_var
    )
    return esquemas.VisaoGeralV1(
        ativo=esquemas.de_ativo(c), painel=esquemas.de_painel(painel)
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
    posicao = _ou_422(
        lambda: gerar_posicao(pedido.estrategia, c.dados, **pedido.parametros)
    )
    resultado = executar_backtest(c.fechamento, posicao, pedido.custo_por_operacao)
    metricas = resumir_desempenho(
        resultado.retorno, resultado.posicao, None, c.taxa_livre_de_risco
    )
    usados = {
        **ESTRATEGIAS[pedido.estrategia].parametros_padrao(),
        **pedido.parametros,
    }
    return esquemas.BacktestDoAtivoV1(
        ativo=esquemas.de_ativo(c),
        estrategia=pedido.estrategia,
        parametros=usados,
        custo_por_operacao=pedido.custo_por_operacao,
        backtest=esquemas.de_backtest(resultado, metricas),
    )
