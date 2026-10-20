"""O formato das respostas da API de leitura (v1): o "contrato" que a interface nova lê.

Cada `de_...` converte um resumo de `src/analises.py` (ou do backtest) num modelo Pydantic, que vira
JSON. Duas regras valem para todos:
- número que não existe (NaN, infinito) vira `null`, porque JSON não tem NaN;
- **nada de preço bruto** (ADR 0048, item 6, e licença dos preços, ADR 0008): só números calculados,
  quedas, volatilidades e curvas em base 100. Há teste que percorre os esquemas e recusa campos de preço.
"""

import math
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, datetime

import pandas as pd
from pydantic import BaseModel

from src import (
    analises,
    busca_por_cnpj,
    catalogo,
    dossie,
    juros_e_inflacao,
    linha_do_tempo,
    relatorio_empresa,
    relatorio_setor,
    topicos,
)
from src.api_v1.contexto import ContextoDoAtivo
from src.backtest import ResultadoBacktest
from src.banco.dados_do_usuario import Simulacao
from src.commodities import painel_de_precos
from src.commodities.cafe import painel as painel_do_cafe
from src.conteudo import descrever_pior_drawdown
from src.ficha import Ficha, PedidoDaFicha, Resultado, nota_das_tentativas
from src.indicadores import calcular_media_por_mes
from src.links_das_fontes import link_da_fonte
from src.rastro import como_foi_calculado
from src.simulacoes import endereco_no_app_novo

BASE = 100.0  # as curvas de valor começam aqui


def numero(valor: float | None) -> float | None:
    """O número como `float`, ou `None` se não existir (NaN, infinito ou vazio)."""
    if valor is None or pd.isna(valor) or math.isinf(valor):
        return None
    return float(valor)


def _data(valor: pd.Timestamp | None) -> date | None:
    return None if valor is None or pd.isna(valor) else valor.date()


def _mes(periodo: pd.Period) -> str:
    return f"{periodo.year:04d}-{periodo.month:02d}"


class CurvaV1(BaseModel):
    """Uma série ao longo do tempo: as datas e o valor em cada uma (`null` onde não há)."""

    datas: list[date]
    valores: list[float | None]


def em_base_100(fechamento: pd.Series) -> CurvaV1:
    """O fechamento dividido pelo primeiro dia, vezes 100: a forma da curva sem o preço."""
    precos = fechamento.dropna()
    return curva(precos / precos.iloc[0] * BASE)


def curva(serie: pd.Series) -> CurvaV1:
    return CurvaV1(
        datas=[d.date() for d in pd.DatetimeIndex(serie.index)],
        valores=[numero(v) for v in serie.to_numpy()],
    )


class PainelDeNumerosV1(BaseModel):
    """Os números da visão geral (frações: 0.12 = 12%)."""

    retorno_total: float | None
    retorno_anualizado: float | None
    volatilidade_anual: float | None
    maior_queda: float | None
    sharpe: float | None
    data_do_melhor_dia: date
    melhor_dia: float | None
    data_do_pior_dia: date
    pior_dia: float | None
    dias_de_alta: float | None
    confianca_do_var: int
    var: float | None
    cvar: float | None


def de_painel(painel: analises.PainelDeNumeros) -> PainelDeNumerosV1:
    return PainelDeNumerosV1(
        retorno_total=numero(painel.retorno_total),
        retorno_anualizado=numero(painel.retorno_anualizado),
        volatilidade_anual=numero(painel.volatilidade_anual),
        maior_queda=numero(painel.maior_queda),
        sharpe=numero(painel.sharpe),
        data_do_melhor_dia=painel.data_do_melhor_dia.date(),
        melhor_dia=numero(painel.melhor_dia),
        data_do_pior_dia=painel.data_do_pior_dia.date(),
        pior_dia=numero(painel.pior_dia),
        dias_de_alta=numero(painel.dias_de_alta),
        confianca_do_var=painel.confianca_do_var,
        var=numero(painel.var),
        cvar=numero(painel.cvar),
    )


class PiorQuedaV1(BaseModel):
    queda: float | None
    data_topo: date | None
    data_fundo: date | None
    data_recuperacao: date | None  # null se ainda não voltou ao topo


class RiscoV1(BaseModel):
    """A queda desde o topo dia a dia (frações, nunca positivas), a pior queda e a volatilidade móvel."""

    drawdown: CurvaV1
    pior_queda: PiorQuedaV1
    janela: int
    volatilidade_movel: CurvaV1
    frase_da_pior_queda: str  # a mesma frase da tela, sem Markdown
    aviso_da_janela: str | None  # o período não tem dias para a janela escolhida


def de_risco(risco: analises.RiscoAoLongoDoTempo) -> RiscoV1:
    pior = risco.pior_drawdown
    return RiscoV1(
        drawdown=curva(risco.drawdown),
        pior_queda=PiorQuedaV1(
            queda=numero(pior.queda),
            data_topo=_data(pior.data_topo),
            data_fundo=_data(pior.data_fundo),
            data_recuperacao=_data(pior.data_recuperacao),
        ),
        janela=risco.janela,
        volatilidade_movel=curva(risco.volatilidade_movel),
        frase_da_pior_queda=descrever_pior_drawdown(pior, negrito=False),
        aviso_da_janela=(
            analises.aviso_janela_curta(risco.janela)
            if risco.volatilidade_movel.dropna().empty
            else None
        ),
    )


class MesV1(BaseModel):
    mes: str  # "2024-03"
    retorno: float | None


class AnoV1(BaseModel):
    ano: int
    meses: list[float | None]  # janeiro a dezembro (null: mês sem dados)
    total: float | None  # o ano inteiro


class RetornoMensalV1(BaseModel):
    meses: list[MesV1]
    tabela: list[AnoV1]
    melhor: MesV1
    pior: MesV1
    meses_de_alta: float | None
    media_por_mes: list[
        float | None
    ]  # janeiro a dezembro: a média de cada mês ao longo dos anos


def de_retorno_mensal(mensal: analises.RetornoMensal) -> RetornoMensalV1:
    tabela = mensal.tabela
    meses_do_ano = [c for c in tabela.columns if c != "Ano"]
    return RetornoMensalV1(
        meses=[
            MesV1(mes=_mes(p), retorno=numero(v)) for p, v in mensal.retornos.items()
        ],
        tabela=[
            AnoV1(
                ano=int(ano),
                meses=[numero(v) for v in tabela.loc[ano, meses_do_ano]],
                total=numero(tabela.loc[ano, "Ano"]),
            )
            for ano in tabela.index
        ],
        melhor=MesV1(mes=_mes(mensal.mes_melhor), retorno=numero(mensal.melhor)),
        pior=MesV1(mes=_mes(mensal.mes_pior), retorno=numero(mensal.pior)),
        meses_de_alta=numero(mensal.meses_de_alta),
        media_por_mes=[numero(v) for v in calcular_media_por_mes(tabela).to_numpy()],
    )


class LinhaDaComparacaoV1(BaseModel):
    ticker: str  # o símbolo dos dados (^BVSP)
    codigo: str  # o que a tela mostra (IBOV)
    retorno_total: float | None
    retorno_anualizado: float | None
    volatilidade_anual: float | None
    maior_queda: float | None
    sharpe: float | None


class ComparacaoV1(BaseModel):
    """Ativos nos dias em que todos têm preço; curvas e tabela vêm `null` se o período for curto."""

    dias_em_comum: int
    dias_descartados: int
    curvas: dict[str, CurvaV1] | None  # cada ativo começando em 100
    tabela: list[LinhaDaComparacaoV1] | None
    nota: str | None  # como a comparação foi feita (com dados)
    aviso: str | None  # poucos dias em comum (sem curvas nem tabela)


def de_comparacao(comparacao: analises.Comparacao) -> ComparacaoV1:
    curvas = tabela = None
    if comparacao.base_100 is not None and comparacao.tabela is not None:
        curvas = {str(t): curva(comparacao.base_100[t]) for t in comparacao.base_100}
        tabela = [
            LinhaDaComparacaoV1(
                ticker=str(ticker),
                codigo=catalogo.codigo(str(ticker)),
                retorno_total=numero(linha["Retorno total"]),
                retorno_anualizado=numero(linha["Retorno anualizado"]),
                volatilidade_anual=numero(linha["Volatilidade anual"]),
                maior_queda=numero(linha["Maior queda"]),
                sharpe=numero(linha["Índice de Sharpe"]),
            )
            for ticker, linha in comparacao.tabela.iterrows()
        ]
    return ComparacaoV1(
        dias_em_comum=comparacao.dias_em_comum,
        dias_descartados=comparacao.dias_descartados,
        curvas=curvas,
        tabela=tabela,
        nota=(
            analises.nota_da_comparacao(
                comparacao.dias_em_comum, comparacao.dias_descartados
            )
            if tabela is not None
            else None
        ),
        aviso=(
            None
            if tabela is not None
            else analises.aviso_poucos_dias_em_comum(comparacao.dias_em_comum)
        ),
    )


class BacktestV1(BaseModel):
    """As métricas (na ordem da tela), a curva de capital em base 100 e quantas operações houve."""

    metricas: dict[str, float | None]
    curva_de_capital: CurvaV1
    operacoes: int


def de_backtest(resultado: ResultadoBacktest, metricas: dict[str, float]) -> BacktestV1:
    return BacktestV1(
        metricas={nome: numero(valor) for nome, valor in metricas.items()},
        curva_de_capital=curva(resultado.curva_de_capital * BASE),
        operacoes=len(resultado.operacoes),
    )


class MarcoV1(BaseModel):
    """Um acontecimento na linha do tempo: o documento e o ponto da curva (base 100) onde ele fica."""

    data: date  # quando o documento foi publicado
    dia_no_grafico: date  # o pregão em que o ponto fica (o mesmo dia ou o seguinte)
    valor_no_grafico: float  # a curva em base 100 nesse pregão
    rotulo: str
    tema: str
    materialidade: int
    assunto: str
    descricao: str  # "dd/mm/aaaa · tipo: assunto", como na tela
    link: str  # vazio: sem link seguro
    topico: str  # o assunto do fato relevante (leitor v2): código; vazio se não há
    topico_nome: str  # o mesmo, em português ("Aquisição"); vazio se não há


class LinhaDoTempoV1(BaseModel):
    """A curva do ativo em base 100 e os acontecimentos do período, com os textos da tela."""

    curva: CurvaV1
    marcos: list[MarcoV1]
    fora_do_grafico: (
        int  # acontecimentos do período que ficaram de fora (rotina ou excesso)
    )
    aviso: str  # a linha do tempo não diz que um fato causou o preço
    sem_acontecimentos: str | None  # texto para quando não há marcos
    texto_fora_do_grafico: str | None


def de_linha_do_tempo(linha: linha_do_tempo.LinhaDoTempo) -> LinhaDoTempoV1:
    return LinhaDoTempoV1(
        curva=CurvaV1(
            datas=[p.dia for p in linha.curva],
            valores=[numero(p.valor) for p in linha.curva],
        ),
        marcos=[
            MarcoV1(
                # só https da CVM ou da SEC (a coleta já filtra; aqui é a segunda trava)
                **{**asdict(m), "link": link_da_fonte(m.link) or ""},
                descricao=linha_do_tempo.descricao_do_marco(m),
                topico_nome=topicos.TOPICOS.get(m.topico, ""),
            )
            for m in linha.marcos
        ],
        fora_do_grafico=linha.fora_do_grafico,
        aviso=linha_do_tempo.AVISO_DA_LINHA,
        sem_acontecimentos=None if linha.marcos else linha_do_tempo.SEM_ACONTECIMENTOS,
        texto_fora_do_grafico=(
            linha_do_tempo.texto_fora_do_grafico(linha.fora_do_grafico)
            if linha.fora_do_grafico
            else None
        ),
    )


class NumeroDeJurosV1(BaseModel):
    """Um número do painel (em %, como o Banco Central publica), com a data e a fonte."""

    nome: str
    valor: float | None  # null: faltou dado (o motivo está nos avisos)
    texto: str  # o valor como a tela mostra ("15,00% ao ano", "—")
    unidade: str
    referencia: date | None
    referencia_mensal: bool  # true: vale para o mês inteiro (IPCA)
    divulgado_em: date | None
    fonte: str
    legenda: str  # referência, divulgação e fonte numa linha, como na tela


class ExpectativaV1(BaseModel):
    indicador: str  # "IPCA" ou "Selic"
    ano: int
    mediana: float  # % (como no boletim Focus)
    pesquisa: date | None


class PontoMensalV1(BaseModel):
    mes: date  # o primeiro dia do mês
    selic_meta: float | None  # % ao ano no fim do mês
    ipca_12_meses: float | None  # %


class JurosEInflacaoV1(BaseModel):
    """O painel de juros e inflação como era conhecido em `dia` (fonte: Banco Central)."""

    dia: date
    numeros: list[NumeroDeJurosV1]
    expectativas: list[ExpectativaV1]
    historico: list[PontoMensalV1]
    avisos: list[str]


def de_juros_e_inflacao(
    painel: juros_e_inflacao.PainelDeJuros, dia: date
) -> JurosEInflacaoV1:
    return JurosEInflacaoV1(
        dia=dia,
        numeros=[
            NumeroDeJurosV1(
                **{**asdict(n), "valor": numero(n.valor)},
                texto=juros_e_inflacao.formatar_valor(n),
                legenda=juros_e_inflacao.legenda(n),
            )
            for n in painel.numeros
        ],
        expectativas=[ExpectativaV1(**asdict(e)) for e in painel.expectativas],
        historico=[
            PontoMensalV1(
                mes=p.mes,
                selic_meta=numero(p.selic_meta),
                ipca_12_meses=numero(p.ipca_12_meses),
            )
            for p in painel.historico
        ],
        avisos=list(painel.avisos),
    )


# --- Preços de referência (café, algodão e fertilizantes; src/commodities/painel_de_precos.py) ---


class PontoDoPrecoV1(BaseModel):
    mes: date  # o primeiro dia do mês
    bm: float | None  # Pink Sheet do Banco Mundial
    fmi: float | None  # FMI (PCPS); null também quando o item não tem o FMI ao lado


class PontoDoSpreadV1(BaseModel):
    mes: date
    valor: float  # arábica menos robusta, em US$/kg


class PrecoDeReferenciaV1(BaseModel):
    """Um item do painel, com os textos prontos (os mesmos do Streamlit)."""

    chave: str
    nome: str
    unidade: str
    ultimo_mes: date
    ultimo_valor: float
    texto: str  # o último valor como a tela mostra ("1.234,50")
    variacao_12_meses: float | None  # %, contra o mesmo mês do ano anterior
    texto_da_variacao: str | None  # "+3,2% em 12 meses"
    legenda: str  # o mês e a fonte
    com_fmi: bool  # true: o histórico traz o FMI ao lado do Pink Sheet
    nota_das_fontes: str | None
    historico: list[PontoDoPrecoV1]


class PrecosDeReferenciaV1(BaseModel):
    """O painel de preços de referência mensais como era em `dia`."""

    dia: date
    itens: list[PrecoDeReferenciaV1]
    spread: list[PontoDoSpreadV1]
    titulo_do_spread: str
    nota_do_spread: str
    aviso_diario: str
    atribuicao: str


def de_precos_de_referencia(
    lido: painel_de_precos.PainelDePrecos, dia: date
) -> PrecosDeReferenciaV1:
    return PrecosDeReferenciaV1(
        dia=dia,
        itens=[
            PrecoDeReferenciaV1(
                chave=i.chave,
                nome=i.nome,
                unidade=i.unidade,
                ultimo_mes=i.ultimo_mes,
                ultimo_valor=i.ultimo_valor,
                texto=painel_de_precos.formatar_valor(i.ultimo_valor),
                variacao_12_meses=numero(i.variacao_12_meses),
                texto_da_variacao=painel_de_precos.texto_da_variacao(
                    i.variacao_12_meses
                ),
                legenda=painel_de_precos.legenda_do_item(i),
                com_fmi=i.com_fmi,
                nota_das_fontes=i.nota_das_fontes,
                historico=[
                    PontoDoPrecoV1(mes=p.mes, bm=numero(p.bm), fmi=numero(p.fmi))
                    for p in i.historico
                ],
            )
            for i in lido.itens
        ],
        spread=[PontoDoSpreadV1(mes=s.mes, valor=s.valor) for s in lido.spread],
        titulo_do_spread=painel_de_precos.TITULO_DO_SPREAD,
        nota_do_spread=painel_de_precos.NOTA_DO_SPREAD,
        aviso_diario=lido.aviso_diario,
        atribuicao=lido.atribuicao,
    )


# --- As respostas das rotas: o ativo analisado e o resultado ---


class AtivoV1(BaseModel):
    """O ativo e o período analisados, de onde vieram os preços e a taxa livre de risco usada."""

    ticker: str  # o símbolo dos dados (^BVSP); é o que se manda de volta à API
    codigo: str  # o que a tela mostra (IBOV, PETR4)
    periodo: str
    inicio: date
    fim: date
    origem: str  # "atual", "cache_antigo" (o Yahoo falhou) ou "exemplo"
    taxa_livre_de_risco: float
    taxa_do_cdi: bool  # true: a taxa é o CDI do período
    aviso_da_origem: (
        str | None
    )  # o aviso da tela quando os preços não são os mais recentes


def de_ativo(contexto: ContextoDoAtivo) -> AtivoV1:
    indice = pd.DatetimeIndex(contexto.dados.index)
    return AtivoV1(
        ticker=contexto.ticker,
        codigo=catalogo.codigo(contexto.ticker),
        periodo=contexto.periodo,
        inicio=indice[0].date(),
        fim=indice[-1].date(),
        origem=contexto.origem,
        taxa_livre_de_risco=contexto.taxa_livre_de_risco,
        taxa_do_cdi=contexto.taxa_do_cdi,
        aviso_da_origem=analises.aviso_da_origem(
            contexto.origem, contexto.dados.attrs.get("ate")
        ),
    )


class VisaoGeralV1(BaseModel):
    ativo: AtivoV1
    painel: PainelDeNumerosV1
    curva: CurvaV1  # o fechamento em base 100 (nunca o preço bruto)
    motivo_sem_anualizar: str | None  # por que o retorno anualizado veio vazio


class RiscoDoAtivoV1(BaseModel):
    ativo: AtivoV1
    risco: RiscoV1


class RetornoMensalDoAtivoV1(BaseModel):
    ativo: AtivoV1
    retorno_mensal: RetornoMensalV1


class ComparacaoDoAtivoV1(BaseModel):
    ativo: AtivoV1  # o ativo principal
    comparacao: ComparacaoV1
    sem_dados: list[str]  # pedidos que ficaram de fora por falta de dados


class ChecagemV1(BaseModel):
    pergunta: str
    situacao: str  # "passou", "não passou", "não se aplica" ou "não deu para medir"
    explicacao: str  # a frase com os números que decidiram


class VereditoV1(BaseModel):
    resultado: str  # "passou", "não passou" ou "inconclusivo"
    titulo: str
    texto: str  # sempre termina com o aviso de src/ficha.py


class FichaV1(BaseModel):
    """A ficha "Foi sorte?" do backtest (ADR 0037, D1 e D2), com os textos de `src/ficha.py`."""

    veredito: VereditoV1
    checagens: list[ChecagemV1]  # sempre as cinco, na ordem da ficha
    tentativas: int  # variações na conta do acaso (as da grade e as da pessoa)
    tentativas_da_pessoa: int  # configurações que a pessoa já rodou neste ativo
    texto_das_tentativas: str
    tolerancia_de_queda: float  # fração (0,30 = 30%) usada na checagem das quedas
    livres: list[str]  # os parâmetros que variaram na grade
    capital_inicial: float  # R$, para a isenção do imposto
    nota: str  # quantas variações entraram na conta e o custo usado (embaixo da ficha)


def de_ficha(
    resultado: Ficha, pedido: PedidoDaFicha, texto_das_tentativas: str
) -> FichaV1:
    veredito = resultado.veredito
    return FichaV1(
        veredito=VereditoV1(
            resultado=veredito.resultado.value,
            titulo=veredito.titulo,
            texto=veredito.texto,
        ),
        checagens=[
            ChecagemV1(
                pergunta=c.pergunta, situacao=c.situacao.value, explicacao=c.explicacao
            )
            for c in resultado.checagens
        ],
        tentativas=resultado.tentativas,
        tentativas_da_pessoa=pedido.tentativas_da_pessoa,
        texto_das_tentativas=texto_das_tentativas,
        tolerancia_de_queda=pedido.tolerancia_de_queda,
        livres=list(pedido.livres),
        capital_inicial=pedido.capital_inicial,
        nota=nota_das_tentativas(resultado.tentativas),
    )


class BacktestDoAtivoV1(BaseModel):
    ativo: AtivoV1
    estrategia: str
    parametros: dict[str, int | float | str]
    custo_por_operacao: float
    backtest: BacktestV1
    ficha: FichaV1 | None = None  # null: não deu para montar (o motivo diz por quê)
    motivo_sem_ficha: str | None = None


class LinhaDoTempoDoAtivoV1(BaseModel):
    ativo: AtivoV1  # a linha do tempo não usa taxa livre de risco: vem zerada
    linha_do_tempo: LinhaDoTempoV1


# --- Minhas simulações (ADR 0062, tela 3; Workspace, PR 1) ----------------------------------

VEREDITOS = frozenset(r.value for r in Resultado)


class SimulacaoV1(BaseModel):
    """Uma simulação guardada na conta: o que a lista mostra e o endereço que a reabre."""

    id: uuid.UUID
    tipo: str  # "backtest", "carteira" ou "pares"
    nome: str
    criada_em: datetime
    dados_ate: str | None  # "dd/mm/aaaa": até quando iam os dados na hora de salvar
    numeros: dict[str, str]  # o resumo dos números, formatado como a tela mostrou
    veredito: str | None  # o da ficha "Foi sorte?" ao salvar (só backtests com ficha)
    endereco: (
        str | None
    )  # a tela do app novo que a reabre; null: só reabre no app atual


class MinhasSimulacoesV1(BaseModel):
    simulacoes: list[SimulacaoV1]  # a mais nova primeiro
    usadas: int
    limite: int | None  # null = sem limite
    uso: str  # "2 de 5"
    sem_simulacoes: str  # a frase de quando a lista está vazia


def de_simulacao(simulacao: Simulacao) -> SimulacaoV1:
    """O `resultado` vem do banco e pode ter sido salvo por versões antigas do app: só o que
    estiver no formato esperado aparece (números como texto, veredito conhecido)."""
    resumo = simulacao.resultado if isinstance(simulacao.resultado, Mapping) else {}
    numeros = resumo.get("numeros")
    guardada = resumo.get("ficha")
    veredito = guardada.get("veredito") if isinstance(guardada, Mapping) else None
    dados_ate = resumo.get("dados_ate")
    return SimulacaoV1(
        id=simulacao.id,
        tipo=simulacao.tipo,
        nome=simulacao.nome,
        criada_em=simulacao.criada_em,
        dados_ate=dados_ate if isinstance(dados_ate, str) else None,
        numeros=(
            {str(k): str(v) for k, v in numeros.items()}
            if isinstance(numeros, Mapping)
            else {}
        ),
        veredito=veredito if veredito in VEREDITOS else None,
        endereco=endereco_no_app_novo(simulacao.tipo, simulacao.parametros),
    )


# --- Pulse: estratégias acompanhadas (ADR 0062, Workspace, PR 2) ----------------------------


class JanelaV1(BaseModel):
    """De quando a quando o Pulse olha: da última visita (na 1ª, 7 dias atrás) até agora."""

    inicio: datetime
    fim: datetime
    primeira_vez: bool
    texto: str  # "Desde a sua última visita, em 16/10/2026 às 09h30."


class EstrategiaAcompanhadaV1(BaseModel):
    """Um backtest salvo com a ficha "Foi sorte?" e o veredito dela refeito com os preços de
    hoje."""

    id: str
    nome: str
    ticker: str | None
    antes: str | None  # o veredito visto na última visita (ou o da hora de salvar)
    agora: str | None  # null: não deu para conferir agora
    mudou: bool
    conferido_em: datetime | None  # a visita em que o veredito de agora foi visto
    tese_ligada: str | None  # texto da pessoa: mostrar como texto puro
    endereco: str | None  # o backtest no app novo; null: só reabre no app atual


class LimitesDoPulseV1(BaseModel):
    sem_ficha: int  # backtests salvos antes de o Pulse guardar a ficha
    alem_do_maximo: int  # além das 10 conferidas a cada visita
    nao_conferidas: int  # das conferidas, as que não deu para conferir agora
    alem_dos_ativos: int  # ativos guardados além dos 30 que o Pulse acompanha


# --- Pulse, parte 2: acontecimentos novos e variação do preço (Workspace, PR 3) -------------


class AcontecimentoV1(BaseModel):
    """Um documento novo (CVM ou SEC) de uma empresa que a pessoa acompanha."""

    id: str  # "<fonte>:<protocolo>"
    ticker: str  # sem o ".SA"
    empresa: str  # texto da fonte: mostrar como texto puro
    tipo: str  # "Fato Relevante", "Comunicado ao Mercado", "8-K"...
    titulo: str  # o assunto do cadastro (texto da fonte)
    publicado_em: date
    fonte: str  # "CVM" ou "SEC"
    link_do_original: str | None  # só https da CVM ou da SEC; null: não mostrar o link
    relevancia: float  # 0 a 1, pelos parâmetros do Research da pessoa
    por_que_aparece: list[
        str
    ]  # o ativo acompanhado primeiro, depois as razões da relevância


class VariacaoV1(BaseModel):
    """Do último fechamento conhecido na hora da visita ao último de hoje, sem os proventos."""

    ticker: str  # sem o ".SA"
    variacao: float  # fração: 0.012 é +1,2%
    de: date
    ate: date
    por_que_aparece: list[
        str
    ]  # "favoritos", "Minha carteira", "lista X", "estratégias salvas"


class PulseV1(BaseModel):
    janela: JanelaV1
    estrategias: list[
        EstrategiaAcompanhadaV1
    ]  # as que mudaram, as iguais, as não conferidas
    limites: LimitesDoPulseV1
    avisos: list[str]  # o que ficou de fora e por quê, como o app atual mostra
    sem_estrategias: str  # a frase de quando não há backtest salvo
    notas: list[str]  # os limites do Pulse que valem para esta parte
    # null: a leitura falhou agora e a visita não foi marcada (nada se perde)
    acontecimentos: list[AcontecimentoV1] | None
    variacoes: list[VariacaoV1]  # a maior mudança (para cima ou para baixo) primeiro
    avisos_dos_ativos: list[str]  # os ativos que ficaram de fora do Pulse
    sem_variacao: list[str]  # sem pregão novo ou sem preço desde a visita
    sem_ativos: str  # a frase de quando não há nenhum ativo guardado
    nota_da_variacao: str  # de onde a onde a variação é medida


# --- Relatório da empresa (dossiê da base, PR 4) -----------------------------------------------


class ComparacaoDoNumeroV1(BaseModel):
    """Contra o quê o número é comparado (o setor, uma faixa, o artigo, o balanço anterior)."""

    contra: str
    texto: str
    valor: float | None = None  # o número comparado, quando é um só


class DocumentoUsadoV1(BaseModel):
    """Um documento que entrou na conta: a demonstração da CVM ou o fechamento do preço."""

    nome: str  # "DFP de 31/12/2025, versão 1"
    publicado_em: date | None  # quando ficou público (null: o dia não é conhecido)
    url: str  # o documento original ("" quando não há link)


class LinhaDoRastroV1(BaseModel):
    """Uma linha do "como foi calculado" (`src/rastro.py`, `como_foi_calculado`)."""

    rotulo: str  # "Fórmula", "Versão do cálculo", "Fonte", "Publicado em", "Documento"
    texto: str
    url: str  # o documento original ("" quando não há link)


class RastroDoNumeroV1(BaseModel):
    """Como o número foi calculado e de onde veio (`src/rastro.py`): a conta, a versão dela, a
    fonte (o id da coleta, com a licença) e quando o insumo mais novo ficou público."""

    formula: str
    versao_do_calculo: str  # "fundamentos 2": muda quando a fórmula muda
    fonte_id: str  # "cvm"
    publicado_em: date | None
    documentos: list[DocumentoUsadoV1]
    outras_fontes: list[str]  # ["yahoo"] nos números que usam o preço
    linhas: list[
        LinhaDoRastroV1
    ] = []  # o "como foi calculado" já escrito, como na página


def _rastro_com_linhas(dados: dict, secoes: list) -> None:
    """Põe em cada número, dentro do dicionário já montado, as linhas do "como foi calculado" de
    `src/rastro.py` (o mesmo texto da página e do PDF)."""
    for secao, original in zip(dados["secoes"], secoes, strict=True):
        for item, item_original in zip(secao["itens"], original.itens, strict=True):
            if item_original.rastro is not None:
                item["rastro"]["linhas"] = [
                    asdict(linha) for linha in como_foi_calculado(item_original.rastro)
                ]


class ItemDoRelatorioV1(BaseModel):
    """Um número com o contrato inteiro: de quando é (`base`), de onde veio (`fonte`) e a
    comparação (ou, em `sem_comparacao`, por que não há com o quê comparar)."""

    chave: str
    nome: str
    texto: str  # o número já escrito ("R$ 12,3 bi", "18,5%")
    valor: float | None
    unidade: str
    base: str
    motivo: str
    nota: str | None
    nota_texto: str
    fonte: str
    comparacao: ComparacaoDoNumeroV1 | None
    sem_comparacao: str
    rastro: RastroDoNumeroV1 | None = (
        None  # null: frase (nome, auditor) ou número da base
    )


class TabelaDoRelatorioV1(BaseModel):
    """Uma tabela de uma seção, com o título e as células já escritas (como na página e no PDF)."""

    chave: str
    titulo: str
    colunas: list[str]
    linhas: list[list[str]]


class PontoDoRelatorioV1(BaseModel):
    """Um ponto de "O que os dados mostram": saiu de uma regra fixa e leva o número, de quando
    ele é e a tabela de origem."""

    lado: str  # "forte" ou "atenção"
    texto: str
    numero: str
    medido_em: str
    tabela: str
    indicador: str


class SecaoDoRelatorioV1(BaseModel):
    chave: str
    titulo: str
    itens: list[ItemDoRelatorioV1]
    paragrafos: list[str]
    tabelas: list[TabelaDoRelatorioV1]
    pontos: list[PontoDoRelatorioV1] = []
    trancada: bool  # o plano não inclui a seção: só o título e o convite (sem números)
    recolhida: bool = False  # explicação: a tela mostra fechada até a pessoa abrir


class NotaDaAnaliseV1(BaseModel):
    """A nota numerada de uma frase da análise: abre o número de onde a frase saiu."""

    numero: int
    id: str
    nome: str
    texto: str  # o valor já escrito, ou a linha da tabela
    medido_em: str
    fonte: str
    comparacao: str  # "Contra X: texto"; vazio quando não compara


class FraseDaAnaliseV1(BaseModel):
    texto: str
    notas: list[int]  # os números das notas (`AnaliseDaEmpresaV1.notas`)


class ParagrafoDaAnaliseV1(BaseModel):
    tipo: str  # "fato" ou "leitura"
    rotulo: str  # "Leitura" no parágrafo de leitura; vazio no de fato
    frases: list[FraseDaAnaliseV1]


class ParteDaAnaliseV1(BaseModel):
    chave: str
    titulo: str
    origem: str  # "modelo" ou "molde" (texto de reserva por regras)
    paragrafos: list[ParagrafoDaAnaliseV1]


class AnaliseDaEmpresaV1(BaseModel):
    """A análise escrita pelo modelo, frase por frase, com fonte em cada uma (ADR 0100)."""

    partes: list[ParteDaAnaliseV1]
    notas: list[NotaDaAnaliseV1]
    aviso: str
    motivo: str | None = (
        None  # por que saiu o molde no lugar do texto do modelo, se saiu
    )


class RelatorioDaEmpresaV1(BaseModel):
    empresa: str
    cnpj: str
    ticker: str
    setor: str
    grupo: str
    secoes: list[SecaoDoRelatorioV1]
    fontes: list[str]
    aviso_das_notas: str
    em_conferencia: bool
    analise: AnaliseDaEmpresaV1 | None = (
        None  # null: sem análise aprovada para a empresa
    )


def _titulo_da_tabela(chave: str) -> str:
    if chave in dossie.TITULOS_DAS_TABELAS:
        return dossie.titulo_da_tabela(chave)
    return relatorio_empresa.nome_da_tabela(chave)


def _tabela_do_relatorio(chave: str, linhas: list[dict]) -> TabelaDoRelatorioV1:
    colunas = list(linhas[0])
    return TabelaDoRelatorioV1(
        chave=chave,
        titulo=_titulo_da_tabela(chave),
        colunas=[relatorio_empresa.rotulo_da_coluna(c) for c in colunas],
        linhas=[
            [relatorio_empresa.escrever_celula(linha.get(c)) for c in colunas]
            for linha in linhas
        ],
    )


def de_relatorio_da_empresa(
    relatorio: relatorio_empresa.Relatorio,
) -> RelatorioDaEmpresaV1:
    """O relatório montado (já trancado para o plano de quem vê) no formato da API."""
    dados = relatorio.como_dict()
    _rastro_com_linhas(dados, relatorio.secoes)
    for secao, original in zip(dados["secoes"], relatorio.secoes, strict=True):
        secao["tabelas"] = [
            _tabela_do_relatorio(chave, linhas).model_dump()
            for chave, linhas in original.tabelas.items()
            if linhas
        ]
    return RelatorioDaEmpresaV1.model_validate(dados)


class BuscaPorCnpjV1(BaseModel):
    """O relatório do CNPJ (molde B): as seções no formato do relatório da empresa."""

    situacao: str  # "encontrada" ou "fora_da_base_aberta"
    cnpj: str
    empresa: str
    tickers: list[str]
    como_era_em: date | None  # o dia da ficha da noite
    secoes: list[SecaoDoRelatorioV1]
    fontes: list[str]
    limites: list[str]
    desligado: list[str]  # o que ainda não aparece e por quê
    avisos: list[str]


def de_busca_por_cnpj(relatorio: busca_por_cnpj.RelatorioDoCnpj) -> BuscaPorCnpjV1:
    """O relatório do CNPJ (já trancado para o plano de quem vê) no formato da API."""
    dados = relatorio.como_dict()
    _rastro_com_linhas(dados, relatorio.secoes)
    for secao, original in zip(dados["secoes"], relatorio.secoes, strict=True):
        secao["tabelas"] = [
            _tabela_do_relatorio(chave, linhas).model_dump()
            for chave, linhas in original.tabelas.items()
            if linhas
        ]
    return BuscaPorCnpjV1.model_validate(dados)


# --- Relatório do setor (molde D, plano de 19/10/2026, PR 3) ---------------------------------------


class SetorV1(BaseModel):
    """Um setor do relatório: a chave que vai em `/v1/relatorio-setor?setor=` e quantas companhias."""

    chave: str
    nome: str
    empresas: int  # companhias abertas com ticker no setor
    como_era_em: (
        date | None
    )  # o dia da ficha da noite (null: a noite ainda não trouxe o setor)


class SetoresV1(BaseModel):
    setores: list[SetorV1]  # na ordem da lista do lançamento


def de_setores(disponiveis: list[relatorio_setor.SetorDisponivel]) -> SetoresV1:
    return SetoresV1(setores=[SetorV1.model_validate(asdict(s)) for s in disponiveis])


class MembroDoSetorV1(BaseModel):
    cnpj: str  # só os 14 caracteres
    empresa: str
    tickers: list[str]
    motivo: str  # por que está no setor (a ligação com a agência, o setor da CVM ou os dois)


class FraseDoSetorV1(BaseModel):
    """Uma frase de "O que os dados mostram": saiu de uma regra fixa e leva o id de cada número."""

    texto: str
    ids: list[
        str
    ]  # "hhi_<série>", "concentracao_<série>/<ano>", "participacao_dos_membros/..."


class FaltaNoSetorV1(BaseModel):
    kpi: str
    motivo: str
    fonte: str  # de onde viria (ou a tabela da base que já o tem)


class RelatorioDoSetorV1(BaseModel):
    """O relatório do setor (molde D): as seções no formato do relatório da empresa."""

    setor: str
    nome: str
    como_era_em: (
        date | None
    )  # o dia da ficha da noite (null: a noite ainda não trouxe o setor)
    membros: list[MembroDoSetorV1]
    secoes: list[SecaoDoRelatorioV1]
    frases: list[FraseDoSetorV1]  # vazia quando a seção vem trancada
    nao_temos: list[
        FaltaNoSetorV1
    ]  # sempre: o que um analista procuraria e não está aqui
    fontes: list[str]
    limites: list[str]
    avisos: list[str]


def _tabela_ja_escrita(chave: str, linhas: list[dict[str, str]]) -> TabelaDoRelatorioV1:
    """As tabelas do setor já saem com os rótulos e as células escritas (siglas como HHI e CR4
    ficam como estão, sem a regra geral de rótulo)."""
    colunas = list(linhas[0])
    return TabelaDoRelatorioV1(
        chave=chave,
        titulo=relatorio_setor.titulo_da_tabela(chave),
        colunas=colunas,
        linhas=[[str(linha.get(c, "—")) for c in colunas] for linha in linhas],
    )


def de_relatorio_do_setor(
    relatorio: relatorio_setor.RelatorioDoSetor,
) -> RelatorioDoSetorV1:
    """O relatório do setor (já trancado para o plano de quem vê) no formato da API."""
    dados = relatorio.como_dict()
    for secao, original in zip(dados["secoes"], relatorio.secoes, strict=True):
        secao["tabelas"] = [
            _tabela_ja_escrita(chave, linhas).model_dump()
            for chave, linhas in original.tabelas.items()
            if linhas
        ]
    return RelatorioDoSetorV1.model_validate(dados)


# --- Mapa do café (plano do café, PR 10) -----------------------------------------------------------
class CamadaDoMapaV1(BaseModel):
    """Uma camada do mapa: o que pinta os municípios, com o "o que é isto" e a fonte."""

    chave: str  # "producao", "area", "chuva" ou "geada"
    titulo: str
    unidade: str
    o_que_e: str
    fonte: str
    escala: str  # "sequencial" (mais é mais) ou "divergente" (em torno de `referencia`)
    referencia: float | None


class MunicipioDoMapaV1(BaseModel):
    codigo: (
        str  # o código do IBGE (7 dígitos), o mesmo da propriedade `codarea` da malha
    )
    nome: str
    uf: str
    regiao: str | None  # a região produtora do cadastro; null: fora das regiões
    valores: dict[
        str, float | None
    ]  # por camada; null: sem dado (o motivo em `sem_dado`)
    sem_dado: dict[str, str]  # por camada sem valor: por que o município fica cinza
    area_mapbiomas_ha: (
        float | None
    )  # a área de café vista por satélite, para conferir a PAM


class IndiceDoMapaV1(BaseModel):
    valor: float | None
    normal: float | None  # a média de 1991–2020; null: sem anos bastantes
    n_estacoes: int  # 0 no CHIRPS (satélite)
    inicio: date
    fim: date
    texto: str  # a frase pronta, com o período e de onde veio


class ItemDoMesV1(BaseModel):
    titulo: str
    texto: str


class RegiaoDoMapaV1(BaseModel):
    id: str
    nome: str
    tipo_predominante: str  # "arabica" ou "conilon"
    chuva: IndiceDoMapaV1
    geada: IndiceDoMapaV1
    fase: str  # a fase do calendário do café no mês
    o_que_o_mercado_olha: list[ItemDoMesV1]


class MapaDoCafeV1(BaseModel):
    """O mapa de um tipo de café como o pacote de `gerado_em` o deixou (nada publicado depois)."""

    tipo: str  # "arabica" ou "conilon"
    ano: int  # o ano da PAM
    gerado_em: date
    mes: int  # o mês do calendário da fase (1 a 12)
    camadas: list[CamadaDoMapaV1]
    municipios: list[MunicipioDoMapaV1]
    regioes: list[RegiaoDoMapaV1]
    malha: dict[
        str, object
    ]  # GeoJSON (FeatureCollection) simplificado, propriedade `codarea`
    fontes: list[str]
    aviso: str


# --- Painel do café (plano do café, PR 11): os tipos de `src/commodities/cafe/painel.py` ------------
class PontoDoPrecoDoCafeV1(BaseModel):
    mes: date
    bm: float | None  # Pink Sheet do Banco Mundial
    fmi: float | None


class PrecoDeReferenciaDoCafeV1(BaseModel):
    chave: str
    nome: str
    unidade: str
    ultimo_mes: date
    ultimo_valor: float
    variacao_12_meses: float | None  # em %
    historico: list[PontoDoPrecoDoCafeV1]
    com_fmi: bool
    nota_das_fontes: str | None


class PontoDoSpreadDoCafeV1(BaseModel):
    mes: date
    arabica: float  # centavos de dólar por libra-peso
    robusta: float
    spread: float
    razao: float


class MarcoDoCafeV1(BaseModel):
    data: date
    texto: str
    fonte: str


class PrecoDoCafeV1(BaseModel):
    item: PrecoDeReferenciaDoCafeV1
    spread: list[PontoDoSpreadDoCafeV1]
    marcos: list[MarcoDoCafeV1]


class PontoDoCambioV1(BaseModel):
    mes: date
    valor: float  # média do mês, R$ por US$


class CambioDoCafeV1(BaseModel):
    ultimo_dia: date
    ultimo_valor: float
    variacao_12_meses: float | None
    historico: list[PontoDoCambioV1]


class PontoDosFundosV1(BaseModel):
    relatorio: date
    liquido_lotes: float
    fracao_do_interesse_aberto: float


class FundosDoCafeV1(BaseModel):
    relatorio: date
    comprados_lotes: float
    vendidos_lotes: float
    liquido_lotes: float
    liquido_sacas: float
    interesse_aberto_lotes: float
    fracao_do_interesse_aberto: float
    historico: list[PontoDosFundosV1]
    legenda: str


class DestinoDoCafeV1(BaseModel):
    pais: str
    sacas: float
    fob_usd: float
    fracao: float


class ExportacoesDoCafeV1(BaseModel):
    primeiro_mes: date
    ultimo_mes: date
    sacas: float
    fob_usd: float
    destinos: list[DestinoDoCafeV1]
    fracao_do_espirito_santo: float | None
    nota: str


class PontoAnualDoCafeV1(BaseModel):
    ano_safra: int
    valor: float
    rotulo: str


class BalancoDoPaisV1(BaseModel):
    codigo_do_pais: str
    ano_safra: int
    tipo: str
    producao: float
    participacao_na_producao: float
    relacao_estoque_consumo: float | None


class BalancoDoCafeV1(BaseModel):
    ultima_safra: int
    estoque_consumo_mundo: list[PontoAnualDoCafeV1]
    estoque_consumo_brasil: list[PontoAnualDoCafeV1]
    participacao_do_brasil: list[PontoAnualDoCafeV1]
    paises: list[BalancoDoPaisV1]


class LinhaDaSafraV1(BaseModel):
    uf: str
    area_producao_ha: float | None
    produtividade_sc_ha: float | None
    producao_mil_sacas: float | None


class SafraDoCafeV1(BaseModel):
    safra: int
    levantamento: int
    divulgado_em: date
    linhas: list[LinhaDaSafraV1]


class ErroDaSafraV1(BaseModel):
    safra: int
    erro_pct: float
    erro_mil_sacas: float


class TermometroDaConabV1(BaseModel):
    erros: list[ErroDaSafraV1]
    vies_medio_pct: float | None
    menor_erro_pct: float
    maior_erro_pct: float
    nota: str


class PontoDaSafraV1(BaseModel):
    safra: int
    tipo: str
    uf: str
    serie: str
    valor: float
    unidade: str
    rotulo: str | None
    levantamento: int | None


class BienalidadeDoCafeV1(BaseModel):
    marcas: list[PontoDaSafraV1]


class IndiceDeChuvaV1(BaseModel):
    valor: float | None  # mm somados nos três meses
    normal: float | None
    anomalia: float | None
    razao_da_normal: float | None
    n_estacoes: int
    inicio: date
    fim: date


class TemperaturaDoMesV1(BaseModel):
    competencia: date
    tmin_media_c: float | None
    tmin_normal_c: float | None
    tmin_anomalia_c: float | None
    dias_tmin_abaixo_de_2c: float | None


class ClimaDaRegiaoV1(BaseModel):
    regiao: str
    nome_da_regiao: str
    fonte_dos_dados: str
    chuva: IndiceDeChuvaV1
    temperatura: TemperaturaDoMesV1


class FaseDoCafeV1(BaseModel):
    mes: int
    regiao_id: str
    safra_em_curso: str
    safra_seguinte: str
    em_colheita: bool
    na_janela_de_geada: bool


class ItemDoCalendarioV1(BaseModel):
    tema: str
    texto: str
    indices: list[str]


class CalendarioDoCafeV1(BaseModel):
    fase: FaseDoCafeV1
    itens: list[ItemDoCalendarioV1]


class FatoDaContraparteV1(BaseModel):
    fato: str
    descricao: str
    valor: float | None
    unidade: str | None
    data: date
    divulgado_em: date
    fonte: str
    veiculo: str
    tipo_de_fonte: str


class FichaDaContraparteV1(BaseModel):
    id: str
    cnpj: str | None
    nome: str
    tipo: str
    uf: str | None
    fatos: list[FatoDaContraparteV1]
    o_que_nao_sabemos: list[str]


class ContrapartesDoCafeV1(BaseModel):
    fichas: list[FichaDaContraparteV1]


class BlocoDoCafeV1(BaseModel):
    """O que toda caixa do painel tem: o que é, a fonte, a data do número mais novo e, sem dado, o
    motivo (`conteudo` vazio)."""

    chave: str
    titulo: str
    o_que_e: str
    fonte: str
    data: date | None
    motivo_sem_dado: str | None


class BlocoDoPrecoDoCafeV1(BlocoDoCafeV1):
    conteudo: PrecoDoCafeV1 | None


class BlocoDoCambioV1(BlocoDoCafeV1):
    conteudo: CambioDoCafeV1 | None


class BlocoDosFundosV1(BlocoDoCafeV1):
    conteudo: FundosDoCafeV1 | None


class BlocoDasExportacoesV1(BlocoDoCafeV1):
    conteudo: ExportacoesDoCafeV1 | None


class BlocoDoBalancoV1(BlocoDoCafeV1):
    conteudo: BalancoDoCafeV1 | None


class BlocoDaSafraV1(BlocoDoCafeV1):
    conteudo: SafraDoCafeV1 | None


class BlocoDoTermometroV1(BlocoDoCafeV1):
    conteudo: TermometroDaConabV1 | None


class BlocoDaBienalidadeV1(BlocoDoCafeV1):
    conteudo: BienalidadeDoCafeV1 | None


class BlocoDoClimaV1(BlocoDoCafeV1):
    conteudo: ClimaDaRegiaoV1 | None


class BlocoDoCalendarioV1(BlocoDoCafeV1):
    conteudo: CalendarioDoCafeV1 | None


class BlocoDasContrapartesV1(BlocoDoCafeV1):
    conteudo: ContrapartesDoCafeV1 | None


class OpcaoDeRegiaoV1(BaseModel):
    id: str
    nome: str
    tipo_predominante: str


class PainelDoCafeV1(BaseModel):
    """O painel do café de um tipo como estava em `dia`: cada bloco com o que é, a fonte e a data."""

    dia: date
    tipo: str
    nome_do_tipo: str
    regiao: str
    regioes: list[OpcaoDeRegiaoV1]
    aviso_diario: str
    preco_de_referencia: BlocoDoPrecoDoCafeV1
    cambio: BlocoDoCambioV1
    fundos: BlocoDosFundosV1
    exportacoes: BlocoDasExportacoesV1
    balanco: BlocoDoBalancoV1
    safra: BlocoDaSafraV1
    termometro: BlocoDoTermometroV1
    bienalidade: BlocoDaBienalidadeV1
    clima: BlocoDoClimaV1
    calendario: BlocoDoCalendarioV1
    contrapartes: BlocoDasContrapartesV1


def de_painel_do_cafe(painel: painel_do_cafe.PainelDoCafe) -> PainelDoCafeV1:
    """O painel montado no formato da API (os campos têm os mesmos nomes das dataclasses)."""
    return PainelDoCafeV1.model_validate(painel_do_cafe.em_dicionario(painel))
