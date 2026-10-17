"""As rotas da API de leitura (v1). Todas exigem a API ligada e uma conta logada (src/api_v1/acesso.py)."""

import json
import logging
import os
import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Annotated, Literal, TypeVar

import pandas as pd
import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from src import analises, catalogo, cobranca, conformidade, ficha, pulse, topicos
from src import compartilhamentos as comp
from src import juros_e_inflacao as ji
from src import linha_do_tempo as ldt
from src.api_v1 import contexto, esquemas
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
from src.banco import compartilhamentos as links
from src.banco import leituras as repo_leituras
from src.banco import pulse as repo_pulse
from src.banco import tentativas
from src.banco import teses as repo_teses
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.dados_do_usuario import (
    TAMANHO_MAXIMO_DO_NOME,
    DadosInvalidosError,
    apagar_simulacao,
    carregar_preferencias,
    contar_simulacoes,
    listar_favoritos,
    listar_simulacoes,
    salvar_preferencias,
    salvar_simulacao,
)
from src.banco.eventos import Evento, eventos_dos_tickers
from src.banco.usuarios import Usuario
from src.bcb import FUSO
from src.cdi import CDIIndisponivelError
from src.cobranca import Assinatura, buscar_assinatura
from src.comparacao import MAX_ATIVOS, interpretar_tickers
from src.dados import DadosIndisponiveisError, normalizar_ticker
from src.estrategias import ESTRATEGIAS, gerar_posicao
from src.eventos import FONTE_IPE
from src.formatos import formatar, formato_da_metrica
from src.indicadores import MOTIVO_SEM_ANUALIZAR
from src.metricas import resumir_desempenho
from src.moedas import TICKER_DO_DOLAR, converter_para_reais, moeda_do_ticker
from src.planos import (
    aviso_da_pagina_de_planos,
    frase_da_assinatura,
    limites_do,
    tabela_de_planos,
    texto_do_uso,
)
from src.simulacoes import (
    endereco_no_app_novo,
    restaurar_estado,
    retrato_do_app_novo,
)
from src.tentativas import TETO_POR_PESSOA, impressao
from src.validacao import parametros_numericos

# o que a tela aceita: letras, números e os símbolos de índices e moedas (^BVSP, BTC-USD, USDBRL=X)
FORMATO_DO_TICKER = r"^[A-Za-z0-9^][A-Za-z0-9.^=\-]{0,19}$"
CUSTO_MAXIMO = 0.05  # 5% por operação: acima disso é erro de digitação
Ticker = Annotated[str, Query(pattern=FORMATO_DO_TICKER, max_length=20)]
Periodo = Literal["6mo", "1y", "2y", "5y"]  # os PERIODOS_VALIDOS de src/dados.py
Taxa = Annotated[float | None, Query(ge=0, le=1)]  # sem taxa: o CDI do período
SEM_TAXA = 0.0  # para páginas que não usam taxa livre de risco (não baixa o CDI à toa)
# a ficha "Foi sorte?": o capital entra só no imposto da checagem 2 (o mesmo padrão do Streamlit)
CAPITAL_PADRAO = 10_000.0
CAPITAL_MINIMO = 100.0
MOTIVO_SEM_CONTAGEM = (
    "Não deu para contar as suas tentativas agora, e a ficha depende dessa conta. "
    "Tente de novo em instantes."
)

log = logging.getLogger(__name__)

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


class MeuPlanoV1(BaseModel):
    """A página de planos: o plano da conta, quanto já usou e a tabela (os textos do Streamlit)."""

    plano: str
    nome_do_plano: str
    simulacoes: str  # "1 de 5", "0 de ilimitadas" ou "—"
    favoritos: str
    frase_da_assinatura: (
        str | None
    )  # "Sua assinatura renova em dd/mm/aaaa."; nada do Stripe
    aviso: str
    tabela: list[dict[str, str]]  # uma linha por recurso, uma coluna por plano
    acao: (
        str | None
    )  # o botão: "assinar", "gerenciar" ou None (src/cobranca.acao_da_assinatura)
    texto_da_acao: str | None  # a frase que acompanha o botão (ou explica a falta dele)
    nota_do_cartao: str  # o cartão de teste do Stripe (só modo de teste, ADR 0003)


class EnderecoDoStripeV1(BaseModel):
    """A página de pagamento ou o portal do Stripe: a tela leva a pessoa até lá."""

    url: str


class LinkV1(BaseModel):
    """Um link compartilhado da conta (o código nunca volta: o banco só guarda a impressão)."""

    id: uuid.UUID
    titulo: str
    situacao: str  # "ativo", "vencido" ou "revogado"
    descricao: str  # "Ficha ... · ativo · criado em ... · vale até ... · 2 visita(s)"


class MeusLinksV1(BaseModel):
    explicacao: str
    sem_links: str  # a frase de quando a lista está vazia
    links: list[LinkV1]


class PedidoDeRevogarV1(BaseModel):
    id: uuid.UUID


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
    return eu_da_conta(conta)


@router.get("/meu-plano")
def meu_plano(conta: Conta) -> MeuPlanoV1:
    """Só leitura do banco: nenhuma chamada ao Stripe (assinar continua no app atual)."""
    limites = limites_do(conta.plano)
    with obter_engine().connect() as conexao:
        simulacoes = contar_simulacoes(conexao, conta.id)
        favoritos = len(listar_favoritos(conexao, conta.id))
        assinatura = buscar_assinatura(conexao, conta.id)
    acao = cobranca.acao_da_assinatura(
        conta.plano, conta.e_admin, assinatura, cobranca.cobranca_esta_configurada()
    )
    return MeuPlanoV1(
        plano=conta.plano,
        nome_do_plano=limites.nome,
        simulacoes=texto_do_uso(simulacoes, limites.simulacoes),
        favoritos=texto_do_uso(favoritos, limites.favoritos),
        frase_da_assinatura=None
        if assinatura is None
        else frase_da_assinatura(assinatura.periodo_fim, assinatura.cancela_no_fim),
        aviso=aviso_da_pagina_de_planos(),
        tabela=tabela_de_planos(),
        acao=acao.tipo,
        texto_da_acao=acao.texto,
        nota_do_cartao=cobranca.NOTA_DO_CARTAO_DE_TESTE,
    )


# o Stripe devolve a pessoa para a página de planos do app novo (o app atual volta para "/")
CAMINHO_DE_VOLTA_DO_APP_NOVO = "/novo/planos"
STRIPE_FORA_DO_AR = "O pagamento não está disponível agora. Tente de novo em instantes."


def _acao_da_conta(
    conta: Usuario,
) -> tuple[cobranca.AcaoDaAssinatura, Assinatura | None]:
    """O botão que a conta pode usar agora (a mesma regra da tela) e a assinatura dela."""
    if not cobranca.cobranca_esta_configurada():
        raise HTTPException(status_code=503, detail=cobranca.AVISO_SEM_COBRANCA)
    with obter_engine().connect() as conexao:
        assinatura = buscar_assinatura(conexao, conta.id)
    return cobranca.acao_da_assinatura(
        conta.plano, conta.e_admin, assinatura, True
    ), assinatura


@router.post("/pagamento-da-assinatura")
def pagamento_da_assinatura(conta: Conta) -> EnderecoDoStripeV1:
    """A página de pagamento do Stripe para assinar o Pro (só modo de teste; só admins, ADR 0029).

    A rota confere tudo de novo, mesmo com o botão escondido: chamar direto não fura a trava.
    """
    acao, _ = _acao_da_conta(conta)
    if acao.tipo != "assinar":
        raise HTTPException(
            status_code=409, detail=acao.texto or "Você já está no plano Pro."
        )
    try:
        url = cobranca.abrir_pagamento(
            obter_engine(),
            conta.id,
            conta.email,
            caminho_de_volta=CAMINHO_DE_VOLTA_DO_APP_NOVO,
        )
    except (
        cobranca.AssinaturaJaExisteError
    ) as erro:  # outra aba assinou nesse meio tempo
        raise HTTPException(
            status_code=409, detail="Esta conta já tem uma assinatura."
        ) from erro
    except Exception as erro:
        log.exception("Falha ao criar a página de pagamento do Stripe")
        raise HTTPException(status_code=503, detail=STRIPE_FORA_DO_AR) from erro
    return EnderecoDoStripeV1(url=url)


@router.post("/portal-da-assinatura")
def portal_da_assinatura(conta: Conta) -> EnderecoDoStripeV1:
    """O portal do Stripe para trocar o cartão, ver faturas ou cancelar a própria assinatura."""
    acao, assinatura = _acao_da_conta(conta)
    if acao.tipo != "gerenciar" or assinatura is None:
        raise HTTPException(status_code=404, detail="Não há assinatura para gerenciar.")
    try:
        url = cobranca.criar_portal_da_assinatura(
            assinatura.stripe_customer_id, caminho_de_volta=CAMINHO_DE_VOLTA_DO_APP_NOVO
        )
    except Exception as erro:
        log.exception("Falha ao criar o portal da assinatura")
        raise HTTPException(status_code=503, detail=STRIPE_FORA_DO_AR) from erro
    return EnderecoDoStripeV1(url=url)


def _meus_links(conexao: sa.Connection, usuario_id: uuid.UUID) -> MeusLinksV1:
    return MeusLinksV1(
        explicacao=comp.EXPLICACAO_DOS_LINKS,
        sem_links=comp.SEM_LINKS,
        links=[
            LinkV1(
                id=l.id,
                titulo=l.titulo,
                situacao=l.situacao,
                descricao=comp.descrever_link(
                    l.tipo, l.situacao, l.criado_em, l.expira_em, l.visitas
                ),
            )
            for l in links.listar_links(conexao, usuario_id)
        ],
    )


@router.get("/links-compartilhados")
def links_compartilhados(conta: Conta) -> MeusLinksV1:
    """Meus dados › Links compartilhados: só os da conta do token."""
    with obter_engine().connect() as conexao:
        return _meus_links(conexao, conta.id)


@router.post("/revogar-link")
def revogar_link(conta: Conta, pedido: PedidoDeRevogarV1) -> MeusLinksV1:
    """Revoga um link da própria conta; o de outra conta (ou já revogado) dá 404, sem dizer qual."""
    with obter_engine().begin() as conexao:
        if not links.revogar_link(conexao, conta.id, pedido.id):
            raise HTTPException(
                status_code=404, detail="Este link não existe ou já foi revogado."
            )
        return _meus_links(conexao, conta.id)


NOME_DA_EXPORTACAO = (
    "meus-dados-tickerlab.json"  # o mesmo arquivo do botão do Streamlit
)


@router.get("/meus-dados")
def meus_dados(conta: Conta) -> Response:
    """Tudo o que o TickerLab guarda sobre a conta (LGPD), a mesma exportação do Streamlit."""
    with obter_engine().begin() as conexao:
        dados = conformidade.exportar_meus_dados(conexao, conta.id)
    return Response(
        content=json.dumps(dados, ensure_ascii=False, indent=2, default=str),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{NOME_DA_EXPORTACAO}"',
            "Cache-Control": "no-store",
        },
    )


def eu_da_conta(conta: Usuario) -> EuV1:
    """O que a tela mostra da conta (o `/v1/eu` e a criação da conta respondem igual)."""
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
    # a ficha "Foi sorte?" (vazios: o capital padrão, a tolerância guardada na conta e os dois
    # primeiros parâmetros numéricos da estratégia, como no Streamlit)
    capital_inicial: float = Field(
        CAPITAL_PADRAO, ge=CAPITAL_MINIMO, le=ficha.CAPITAL_MAXIMO_GUARDADO
    )
    tolerancia_de_queda: float | None = Field(
        None, ge=ficha.TOLERANCIA_MINIMA, le=ficha.TOLERANCIA_MAXIMA
    )
    livres: list[Annotated[str, Field(max_length=40)]] | None = Field(
        None, max_length=2
    )


@router.post("/backtest")
def backtest(conta: Conta, pedido: PedidoDeBacktestV1) -> esquemas.BacktestDoAtivoV1:
    """O backtest simples (sem proteções, Monte Carlo nem grade) e, embaixo, a ficha "Foi sorte?".

    Como no Streamlit, todo backtest é uma tentativa: a configuração fica contada na conta (a mesma
    configuração não conta duas vezes) e entra na checagem do acaso.
    """
    if pedido.estrategia not in ESTRATEGIAS:
        raise HTTPException(status_code=422, detail="Estratégia desconhecida.")
    livres = _livres_do_pedido(pedido.estrategia, pedido.livres)
    c = _com_o_ativo(pedido.ticker, pedido.periodo, pedido.taxa)
    resposta = _ou_422(
        lambda: montar_backtest(
            c, pedido.estrategia, pedido.parametros, pedido.custo_por_operacao
        )
    )
    return resposta.model_copy(
        update=_ficha_da_conta(conta, c, pedido, resposta.parametros, livres)
    )


# --- Minhas simulações (ADR 0062, tela 3; Workspace, PR 1) ----------------------------------

SEM_SIMULACOES = (
    "Você ainda não guardou nenhuma simulação. Rode um backtest e clique em Salvar."
)


class PedidoDeSalvarSimulacaoV1(BaseModel):
    """O backtest que a tela mostrou (o mesmo pedido de /v1/backtest) e o veredito da ficha."""

    nome: str = Field(min_length=1, max_length=TAMANHO_MAXIMO_DO_NOME)
    backtest: PedidoDeBacktestV1
    veredito: str | None = Field(None, max_length=20)  # None: a tela ficou sem ficha


class PedidoDeSimulacaoV1(BaseModel):
    id: uuid.UUID


def _minhas_simulacoes(
    conexao: sa.Connection, conta: Usuario
) -> esquemas.MinhasSimulacoesV1:
    salvas = listar_simulacoes(conexao, conta.id)
    limite = limites_do(conta.plano).simulacoes
    return esquemas.MinhasSimulacoesV1(
        simulacoes=[esquemas.de_simulacao(s) for s in salvas],
        usadas=len(salvas),
        limite=limite,
        uso=texto_do_uso(len(salvas), limite),
        sem_simulacoes=SEM_SIMULACOES,
    )


@router.get("/simulacoes")
def minhas_simulacoes(conta: Conta) -> esquemas.MinhasSimulacoesV1:
    """Minhas simulações: as guardadas na conta do token (as do app atual também), a mais nova
    primeiro, com quantas o plano ainda deixa."""
    with obter_engine().connect() as conexao:
        return _minhas_simulacoes(conexao, conta)


@router.post("/salvar-simulacao")
def salvar_simulacao_da_tela(
    conta: Conta, pedido: PedidoDeSalvarSimulacaoV1
) -> esquemas.MinhasSimulacoesV1:
    """Guarda o backtest da tela como o Streamlit guarda (telas/dados_da_conta.py): o retrato
    das escolhas, os números formatados, até quando iam os dados e a ficha "Foi sorte?" (o
    pedido e o veredito), que o Pulse recalcula depois.

    O backtest roda de novo aqui (é barato) em vez de confiar nos números que a tela mandar; só
    o veredito vem da tela, porque a ficha custa caro e ele serve só de "antes" na comparação do
    Pulse. Além do limite do plano: 403 com o motivo "plano" (src/api.py).
    """
    b = pedido.backtest
    if b.estrategia not in ESTRATEGIAS:
        raise HTTPException(status_code=422, detail="Estratégia desconhecida.")
    if pedido.veredito is not None and pedido.veredito not in esquemas.VEREDITOS:
        raise HTTPException(status_code=422, detail="Veredito desconhecido.")
    livres = _livres_do_pedido(b.estrategia, b.livres)
    c = _com_o_ativo(b.ticker, b.periodo, b.taxa)
    resposta = _ou_422(
        lambda: montar_backtest(c, b.estrategia, b.parametros, b.custo_por_operacao)
    )
    numeros = {
        nome: formatar(valor, formato_da_metrica(nome))
        for nome, valor in resposta.backtest.metricas.items()
    }
    numeros["Operações"] = formatar(resposta.backtest.operacoes, "inteiro")
    with obter_engine().begin() as conexao:
        informada = b.tolerancia_de_queda
        if informada is None:  # a guardada na conta, como a ficha usou
            informada = carregar_preferencias(conexao, conta.id).get(
                ficha.PREFERENCIA_DA_TOLERANCIA
            )
        tolerancia = ficha.normalizar_tolerancia(informada)
        retrato = retrato_do_app_novo(
            ticker=c.ticker,
            periodo=c.periodo,
            estrategia=b.estrategia,
            parametros=resposta.parametros,
            custo_por_operacao=b.custo_por_operacao,
            capital_inicial=b.capital_inicial,
            tolerancia_de_queda=tolerancia,
            livres=livres,
            taxa=b.taxa,
        )
        resumo: dict = {
            "numeros": numeros,
            "dados_ate": f"{c.dados.index[-1]:%d/%m/%Y}",
        }
        if pedido.veredito is not None:
            da_pessoa = tentativas.contar_tentativas(conexao, conta.id, c.ticker)
            pedido_da_ficha = _pedido_da_ficha(
                c,
                b.estrategia,
                resposta.parametros,
                b.custo_por_operacao,
                b.capital_inicial,
                livres,
                tolerancia,
                max(da_pessoa, 1),  # a tela contou esta tentativa; ao menos ela
            )
            resumo["ficha"] = {
                "pedido": ficha.pedido_para_guardar(pedido_da_ficha),
                "veredito": pedido.veredito,
            }
        try:
            salvar_simulacao(
                conexao,
                conta.id,
                "backtest",
                pedido.nome,
                retrato,
                resumo,
                plano=conta.plano,
            )
        except DadosInvalidosError as erro:
            raise HTTPException(status_code=422, detail=str(erro)) from erro
        return _minhas_simulacoes(conexao, conta)


@router.post("/apagar-simulacao")
def apagar_simulacao_da_conta(
    conta: Conta, pedido: PedidoDeSimulacaoV1
) -> esquemas.MinhasSimulacoesV1:
    """Apaga uma simulação da própria conta; a de outra conta (ou já apagada) dá 404, sem dizer
    qual é o caso."""
    with obter_engine().begin() as conexao:
        if not apagar_simulacao(conexao, conta.id, pedido.id):
            raise HTTPException(
                status_code=404, detail="Esta simulação não existe ou já foi apagada."
            )
        return _minhas_simulacoes(conexao, conta)


def _livres_do_pedido(estrategia: str, livres: list[str] | None) -> tuple[str, ...]:
    """Os parâmetros que variam na ficha: só números da estratégia, sem repetir (senão 422)."""
    numericos = [p.nome for p in parametros_numericos(estrategia)]
    if livres is None:
        return tuple(numericos[:2])
    if len(set(livres)) != len(livres) or any(n not in numericos for n in livres):
        raise HTTPException(
            status_code=422,
            detail="Os parâmetros que variam precisam ser números da estratégia, sem repetir.",
        )
    return tuple(livres)


def _tolerancia_da_conta(
    conexao: sa.Connection, usuario_id: uuid.UUID, informada: float | None
) -> float:
    """A informada (e guardada nas preferências, como o campo do Streamlit) ou a já guardada."""
    guardadas = carregar_preferencias(conexao, usuario_id)
    if informada is None:
        return ficha.normalizar_tolerancia(
            guardadas.get(ficha.PREFERENCIA_DA_TOLERANCIA)
        )
    fracao = ficha.normalizar_tolerancia(informada)
    if guardadas.get(ficha.PREFERENCIA_DA_TOLERANCIA) != fracao:
        salvar_preferencias(
            conexao, usuario_id, {**guardadas, ficha.PREFERENCIA_DA_TOLERANCIA: fracao}
        )
    return fracao


def _cdi_da_ficha(c: ContextoDoAtivo) -> pd.Series | None:
    """O CDI do período, só quando ele é a taxa livre de risco (como no Streamlit)."""
    if not c.taxa_do_cdi:
        return None
    try:
        return cdi_entre(c.dados.index[0], c.dados.index[-1])
    except CDIIndisponivelError:
        return None


def _ficha_da_conta(
    conta: Usuario,
    c: ContextoDoAtivo,
    pedido: PedidoDeBacktestV1,
    parametros: dict[str, int | float | str],
    livres: tuple[str, ...],
) -> dict:
    """{"ficha": ...} ou {"motivo_sem_ficha": ...}: conta a tentativa e monta a ficha."""
    marca = impressao(
        c.ticker,
        pedido.estrategia,
        parametros,
        None,
        pedido.custo_por_operacao,
        c.periodo,
    )
    try:
        with obter_engine().begin() as conexao:
            tentativas.registrar_tentativa(conexao, conta.id, c.ticker, marca)
            da_pessoa = tentativas.contar_tentativas(conexao, conta.id, c.ticker)
            tolerancia = _tolerancia_da_conta(
                conexao, conta.id, pedido.tolerancia_de_queda
            )
    except Exception:
        # sem a conta das tentativas, contar "1" deixaria a checagem do acaso mais branda
        log.exception("Falha ao contar a tentativa do backtest na conta")
        return {"motivo_sem_ficha": MOTIVO_SEM_CONTAGEM}
    try:
        montada = montar_ficha_do_backtest(
            c,
            pedido.estrategia,
            parametros,
            pedido.custo_por_operacao,
            pedido.capital_inicial,
            livres,
            tolerancia,
            da_pessoa,
        )
    except ValueError as erro:
        return {"motivo_sem_ficha": str(erro)}
    return {"ficha": montada}


def montar_ficha_do_backtest(
    c: ContextoDoAtivo,
    estrategia: str,
    parametros: dict[str, int | float | str],
    custo_por_operacao: float,
    capital_inicial: float,
    livres: tuple[str, ...],
    tolerancia_de_queda: float,
    tentativas_da_pessoa: int,
) -> esquemas.FichaV1:
    """A ficha de um ativo já carregado, com as tentativas já contadas (a rota e os testes do React
    usam). `ValueError` se não der para montar (pouco histórico, por exemplo)."""
    pedido = _pedido_da_ficha(
        c,
        estrategia,
        parametros,
        custo_por_operacao,
        capital_inicial,
        livres,
        tolerancia_de_queda,
        tentativas_da_pessoa,
    )
    resultado = ficha.montar_ficha(pedido)
    texto = ficha.texto_das_tentativas(
        tentativas_da_pessoa, catalogo.codigo(c.ticker), TETO_POR_PESSOA
    )
    return esquemas.de_ficha(resultado, pedido, texto)


def _pedido_da_ficha(
    c: ContextoDoAtivo,
    estrategia: str,
    parametros: dict[str, int | float | str],
    custo_por_operacao: float,
    capital_inicial: float,
    livres: tuple[str, ...],
    tolerancia_de_queda: float,
    tentativas_da_pessoa: int,
) -> ficha.PedidoDaFicha:
    """Tudo o que a ficha precisa, com os preços (e o CDI) do ativo já carregado."""
    return ficha.PedidoDaFicha(
        dados=c.dados,
        estrategia=estrategia,
        parametros=dict(parametros),
        custo_por_operacao=custo_por_operacao,
        capital_inicial=capital_inicial,
        livres=livres,
        taxa_livre_de_risco=c.taxa_livre_de_risco,
        cdi_diario=_cdi_da_ficha(c),
        tolerancia_de_queda=tolerancia_de_queda,
        tentativas_da_pessoa=tentativas_da_pessoa,
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


def _eventos_do_ativo(
    ticker: str, desde: date
) -> tuple[list[Evento], dict[str, topicos.LeituraDoTopico]]:
    """Os acontecimentos do ativo desde `desde` e o assunto lido de cada fato relevante (leitor
    v2, só regras); vazios se o banco não tem o Research."""
    try:
        with obter_engine().connect() as conexao:
            eventos = eventos_dos_tickers(
                conexao, [ticker], desde, limite=ldt.LIMITE_DE_EVENTOS
            )
            fatos = [
                (e.protocolo, e.assunto)
                for e in eventos
                if e.fonte == FONTE_IPE and e.rotulo == topicos.ROTULO_DO_FATO_RELEVANTE
            ]
            return eventos, repo_leituras.topicos_dos_fatos(conexao, FONTE_IPE, fatos)
    except Exception as erro:
        if tabela_inexistente(erro):
            return [], {}
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
    eventos, assuntos = _eventos_do_ativo(c.ticker, c.fechamento.index[0].date())
    return montar_linha_do_tempo(c, eventos, materialidade_minima, assuntos)


def montar_linha_do_tempo(
    c: ContextoDoAtivo,
    eventos: list[Evento],
    materialidade_minima: int,
    assuntos: dict[str, topicos.LeituraDoTopico] | None = None,
) -> esquemas.LinhaDoTempoDoAtivoV1:
    """A resposta da linha do tempo de um ativo já carregado (a rota e os testes do React usam)."""
    linha = ldt.montar_linha_do_tempo(
        c.fechamento, eventos, materialidade_minima, assuntos=assuntos
    )
    return esquemas.LinhaDoTempoDoAtivoV1(
        ativo=esquemas.de_ativo(c), linha_do_tempo=esquemas.de_linha_do_tempo(linha)
    )


def openapi_v1() -> dict:
    """O esquema OpenAPI só da v1 (o contrato publicado em `docs/api/openapi-v1.json`)."""
    from fastapi import FastAPI

    from src.api_v1.conta import router as router_da_conta

    app = FastAPI(title="TickerLab API (leitura)", version="1")
    app.include_router(router)
    app.include_router(router_da_conta)
    return app.openapi()


# --- Pulse: estratégias acompanhadas (ADR 0062, Workspace, PR 2) ----------------------------

SEM_ESTRATEGIAS = (
    'Salve um backtest para acompanhar: o Pulse refaz a ficha "Foi sorte?" com os preços de '
    "hoje e mostra aqui quando o veredito muda."
)


def _precos_da_estrategia(ticker: str, periodo: str, em_reais: bool) -> pd.DataFrame:
    """Os preços como o app atual carrega os de uma simulação salva (telas/comum.py): em reais
    quando ela foi salva assim; sem o dólar, `cambio_falhou` (o veredito fica sem conferir)."""
    ticker = normalizar_ticker(ticker)
    dados = contexto.carregar_dados(ticker, periodo)
    if not (em_reais and moeda_do_ticker(ticker) == "USD"):
        return dados
    try:
        cambio = contexto.carregar_dados(TICKER_DO_DOLAR, periodo)
        return converter_para_reais(dados, cambio["Close"])
    except (DadosIndisponiveisError, ValueError) as erro:
        log.warning("Câmbio indisponível para converter %s: %s", ticker, erro)
        dados = dados.copy()
        dados.attrs = {**dados.attrs, "cambio_falhou": True}
        return dados


def _avisos_do_pulse(sem_conferir: list[str], sem_ficha: int, fora: int) -> list[str]:
    """Os mesmos avisos do Pulse no app atual (telas/research/pulse.py)."""
    avisos = []
    if sem_conferir:
        avisos.append(f"Não deu para conferir agora: {', '.join(sem_conferir)}.")
    if fora:
        avisos.append(
            f"O Pulse confere as {pulse.MAXIMO_DE_FICHAS} estratégias salvas mais "
            f"recentemente; {fora} ficaram para depois."
        )
    if sem_ficha:
        avisos.append(
            f"Backtests salvos antes de o Pulse acompanhar a ficha: {sem_ficha}. Para "
            "acompanhar, abra em Minhas simulações e salve de novo."
        )
    return avisos


def _estrategia_v1(
    a: pulse.EstrategiaAcompanhada, ligadas: dict
) -> esquemas.EstrategiaAcompanhadaV1:
    retrato = a.estrategia.retrato
    tese = ligadas.get(a.estrategia.id)
    return esquemas.EstrategiaAcompanhadaV1(
        id=a.estrategia.id,
        nome=a.estrategia.nome,
        ticker=restaurar_estado(retrato, "backtest").get("ticker"),
        antes=a.antes,
        agora=a.agora,
        mudou=a.mudou,
        conferido_em=a.conferido_em,
        tese_ligada=None if tese is None else pulse.texto_da_tese_ligada(tese),
        endereco=endereco_no_app_novo("backtest", retrato),
    )


@router.get("/pulse")
def pulse_da_conta(
    conta: Conta,
    desde: Annotated[
        datetime | None,
        Query(description="O início da janela que a aba já mostrava (ISO, com fuso)."),
    ] = None,
) -> esquemas.PulseV1:
    """O Pulse (parte 1): as estratégias salvas com o veredito da ficha "Foi sorte?" refeito
    com os preços de hoje, o que mudou primeiro. Abrir marca a visita, como no app atual.

    Sem sessão no servidor, o F5 da aba reenvia em `desde` o início que ela mostrava: a janela
    não encolhe para os minutos desde a visita que a própria aba marcou (até 30 dias atrás).
    Confere no máximo 10 fichas (as salvas mais recentemente); o resto aparece sem conferir.
    """
    agora = pulse.agora()
    with obter_engine().connect() as conexao:
        visita = repo_pulse.ultima_visita(conexao, conta.id)
        vistos = repo_pulse.vereditos_vistos(conexao, conta.id)
        guardadas = pulse.ler_mudancas(repo_pulse.mudancas_vistas(conexao, conta.id))
        simulacoes = listar_simulacoes(conexao, conta.id)
        ligadas = pulse.teses_por_estrategia(repo_teses.listar(conexao, conta.id))
    j = _ou_422(lambda: pulse.janela_da_aba(visita, agora, desde))
    salvas, sem_ficha, _ = pulse.estrategias_salvas(simulacoes, maximo=len(simulacoes))
    a_conferir = salvas[: pulse.MAXIMO_DE_FICHAS]
    fora = len(salvas) - len(a_conferir)
    conferidos = [
        pulse.comparar(
            e, vistos, pulse.veredito_de_hoje(e, _precos_da_estrategia, cdi_entre)
        )
        for e in a_conferir
    ] + [pulse.comparar(e, vistos, None) for e in salvas[pulse.MAXIMO_DE_FICHAS :]]
    acompanhadas, mudancas = pulse.acompanhar(conferidos, guardadas, j)
    with obter_engine().begin() as conexao:
        repo_pulse.marcar_visita(
            conexao,
            conta.id,
            agora,
            pulse.vereditos_para_guardar(
                vistos, conferidos, {str(s.id) for s in simulacoes}
            ),
            pulse.mudancas_para_guardar(mudancas),
        )
    sem_conferir = [
        v.estrategia.nome for v in conferidos[: len(a_conferir)] if v.agora is None
    ]
    return esquemas.PulseV1(
        janela=esquemas.JanelaV1(
            inicio=j.desde,
            fim=j.ate,
            primeira_vez=j.primeira_vez,
            texto=pulse.texto_da_janela(j),
        ),
        estrategias=[_estrategia_v1(a, ligadas) for a in acompanhadas],
        limites=esquemas.LimitesDoPulseV1(
            sem_ficha=sem_ficha, alem_do_maximo=fora, nao_conferidas=len(sem_conferir)
        ),
        avisos=_avisos_do_pulse(sem_conferir, sem_ficha, fora),
        sem_estrategias=SEM_ESTRATEGIAS,
        notas=[pulse.LIMITES[2], pulse.LIMITES[3]],
    )
