"""O formato das respostas da API de leitura (v1): o "contrato" que a interface nova lê.

Cada `de_...` converte um resumo de `src/analises.py` (ou do backtest) num modelo Pydantic, que vira
JSON. Duas regras valem para todos:
- número que não existe (NaN, infinito) vira `null`, porque JSON não tem NaN;
- **nada de preço bruto** (ADR 0048, item 6, e licença dos preços, ADR 0008): só números calculados,
  quedas, volatilidades e curvas em base 100. Há teste que percorre os esquemas e recusa campos de preço.
"""

import math
from dataclasses import asdict
from datetime import date

import pandas as pd
from pydantic import BaseModel

from src import analises, juros_e_inflacao, linha_do_tempo
from src.api_v1.contexto import ContextoDoAtivo
from src.backtest import ResultadoBacktest
from src.conteudo import descrever_pior_drawdown
from src.indicadores import calcular_media_por_mes
from src.links_das_fontes import link_da_fonte

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
    ticker: str
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


# --- As respostas das rotas: o ativo analisado e o resultado ---


class AtivoV1(BaseModel):
    """O ativo e o período analisados, de onde vieram os preços e a taxa livre de risco usada."""

    ticker: str
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


class BacktestDoAtivoV1(BaseModel):
    ativo: AtivoV1
    estrategia: str
    parametros: dict[str, int | float | str]
    custo_por_operacao: float
    backtest: BacktestV1


class LinhaDoTempoDoAtivoV1(BaseModel):
    ativo: AtivoV1  # a linha do tempo não usa taxa livre de risco: vem zerada
    linha_do_tempo: LinhaDoTempoV1
