"""Eventos do IPE da CVM e PEAD (ficha P0-5 do pré-registro quant v0.1).

Convenções fixadas AQUI, antes de qualquer número (seção 10 do pré-registro: mudar depois de ver um
resultado é tentativa nova). Tudo o que não está na ficha e o código precisa decidir está nesta lista.

- **Entradas** (`Dados`): as tabelas da F-B3 (preços ajustados, abertura, volume, cadastro, balanços
  ponto no tempo, CDI e o BOVA11 como mercado) mais os `documentos` do IPE (CNPJ, categoria, tipo,
  tema, data de referência e `publicado_em`, que é a data de recebimento na CVM).
- **O lucro do trimestre:** conta 3.11 do consolidado (lucro ou prejuízo do período). O 1º trimestre
  é o acumulado de março; os outros são o acumulado do trimestre menos o do anterior no mesmo ano
  (o 4º sai da DFP menos o acumulado de setembro). Cada acumulado é a versão mais recente divulgada
  antes do dia da entrada (as reapresentações e os comparativos das entregas seguintes entram só a
  partir da própria data).
- **O dia do resultado (D):** a primeira data de recebimento entre os documentos de resultado do IPE
  (tema "resultados": press-release e demonstrações) com a referência do trimestre e a entrega do
  ITR ou da DFP (documento do IPE recebido até o fim do trimestre não conta). Trimestre com D mais de 6 meses depois do fim fica de fora (não é anúncio). Se a
  linha do balanço que dá o lucro do trimestre só foi divulgada no dia da entrada ou depois, o evento
  fica de fora: o número que a base tem pode ser uma reapresentação.
- **Dia zero e entrada:** dia zero = D+1 (o IPE não tem hora): o primeiro pregão a partir do dia
  seguinte a D. A entrada é no leilão de abertura do pregão seguinte ao dia zero (D+2). Teste do
  Brasil: dia zero = D (o primeiro pregão a partir de D; entrada um pregão antes), otimista e
  **proibido** no resultado final. Os dois usam os mesmos eventos e as mesmas surpresas; só a data
  muda. V (1), `executar_no_sinal`: entrada na abertura do próprio dia D (antes do documento).
- **Surpresa padronizada (SUE):** (lucro do trimestre − lucro do mesmo trimestre do ano anterior) ÷
  desvio-padrão amostral dessas diferenças sazonais nos 8 trimestres anteriores (sem tendência).
  Precisa das 8; desvio zero fica de fora.
- **Tercil de cima:** SUE acima do quantil 2/3 das SUEs dos eventos do universo com dia zero nos 365
  dias anteriores (só o passado; pelo menos 30 eventos, senão não entra).
- **Universo** (seção 8): a ação do CNPJ precisa ser a classe escolhida pelo universo no dia zero
  (`fatores_b3.elegiveis_em`, uma classe por empresa, a mais líquida).
- **Carteira:** só comprada, pesos iguais por posição: cada entrada compra 1/30 do patrimônio (na
  abertura); sem caixa para todas as do dia, o caixa é dividido igualmente entre elas. Não há
  rebalanceamento. A saída é no leilão de abertura do 60º pregão depois da entrada. Um novo evento da
  empresa enquanto a posição está aberta não muda nada. O caixa rende o CDI.
- **Custos e IR:** os da F-B3 (`custo_de_negociar` mais o impacto Y·σ·√(Q/V)·Q, σ dos 252 e V dos 60
  pregões anteriores; IR de 15% no mês com a isenção de R$ 20 mil; DARF no último pregão do mês
  seguinte). Ação deslistada é vendida no primeiro dia sem preço, pelo último preço conhecido.
- **Estudo dos eventos (CAR):** para cada documento do IPE de uma empresa do universo no dia zero,
  o retorno anormal acumulado de +1 a +60 pelo modelo de mercado (α e β por mínimos quadrados nos
  252 pregões que terminam dois antes do dia zero, mercado = BOVA11; pelo menos 200 retornos). Só
  a 1ª versão de cada documento; um evento por empresa, tipo e dia zero. Depois de uma deslistagem o retorno anormal vale zero. É
  estudo: não escolhe nada e não vira carteira.

Nada aqui é recomendação de investimento.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field, fields, replace

import numpy as np
import pandas as pd

from trader.custos_br import PADRAO, CustosBR, arredondar_lote
from trader.estrategias import fatores_b3 as fb

VERSAO = "0.1"
CONTA_DO_LUCRO = fb.CONTA_LUCRO
TEMA_DOS_RESULTADOS = "resultados"
TRIMESTRES_DO_DESVIO = 8
DEFASAGEM_SAZONAL = 4  # trimestres
FRACAO_DE_CIMA = 1 / 3
PREGOES_NA_POSICAO = 60
POSICOES = 30  # cada entrada recebe 1/30 do patrimônio
DIAS_DO_CORTE_DO_TERCIL = 365
EVENTOS_MINIMOS_DO_TERCIL = 30
MESES_MAXIMOS_ATE_O_RESULTADO = 6
CAPITAL_INICIAL = 100_000.0
PREGOES_DA_ESTIMACAO = 252
RETORNOS_MINIMOS_DA_ESTIMACAO = 200
INICIO_DA_JANELA_DO_CAR, FIM_DA_JANELA_DO_CAR = 1, 60
SEM_CUSTOS = replace(fb.SEM_CUSTOS, emolumentos_no_leilao=0.0)
COLUNAS_DOS_DOCUMENTOS = (
    "cnpj",
    "categoria",
    "tipo",
    "tema",
    "referencia",
    "publicado_em",
    "versao",  # opcional; o estudo dos eventos usa só a 1ª
)
COLUNAS_DOS_EVENTOS = (
    "cnpj",
    "trimestre",
    "dia_do_resultado",
    "sue",
    "variacao",
    "desvio",
)


@dataclass
class Dados(fb.Dados):
    """As tabelas da F-B3 mais os documentos do IPE (ver o topo do módulo)."""

    documentos: pd.DataFrame | None = None


@dataclass(frozen=True)
class Parametros:
    trimestres_do_desvio: int = TRIMESTRES_DO_DESVIO
    fracao_de_cima: float = FRACAO_DE_CIMA
    pregoes_na_posicao: int = PREGOES_NA_POSICAO
    posicoes: int = POSICOES
    dia_zero_em_d: bool = (
        False  # teste do Brasil: otimista e proibido no resultado final
    )
    executar_no_sinal: bool = False  # V (1)
    com_deslistadas: bool = True
    capital_inicial: float = CAPITAL_INICIAL
    custos: CustosBR = PADRAO
    fator_de_impacto: float = 1.0

    def __post_init__(self) -> None:
        if (
            self.trimestres_do_desvio < 2
            or not 0 < self.fracao_de_cima < 1
            or self.pregoes_na_posicao < 1
            or self.posicoes < 1
            or self.capital_inicial <= 0
        ):
            raise ValueError(
                "trimestres >= 2, fração em (0, 1), pregões >= 1, posições >= 1 e capital > 0"
            )

    def especificacao(self) -> dict:
        """Tudo o que define a tentativa, em tipos simples (vai para o registro)."""
        spec = asdict(self)
        spec["custos"] = asdict(self.custos)
        spec["custos"]["a_confirmar"] = list(spec["custos"]["a_confirmar"])
        spec["versao"] = VERSAO
        return spec


@dataclass
class Sinal:
    """Um evento do tercil de cima, pronto para a carteira."""

    ticker: str
    cnpj: str
    trimestre: str
    sue: float
    dia_zero: int  # posição nos pregões
    entrada: int


@dataclass
class Resultado:
    retorno: pd.Series  # diário, líquido
    patrimonio: pd.Series
    pesos: pd.DataFrame  # no fechamento de cada dia, só os tickers com sinal
    custos: pd.Series
    imposto: pd.Series
    giro: float
    posicoes: pd.DataFrame  # uma linha por posição aberta
    contagem: dict  # quantos eventos passaram por cada etapa
    parametros: Parametros = field(repr=False)


# --- o lucro do trimestre, ponto no tempo -------------------------------------------------------------


def acumulados_do_lucro(fundamentos: pd.DataFrame) -> pd.DataFrame:
    """As linhas do lucro acumulado no ano (início em 1º de janeiro), uma por versão divulgada."""
    inicio = pd.to_datetime(fundamentos["inicio"])
    linhas = fundamentos[
        (fundamentos["conta"] == CONTA_DO_LUCRO)
        & inicio.dt.is_year_start.fillna(False)
        & pd.to_datetime(fundamentos["fim"]).dt.is_quarter_end.fillna(False)
    ]
    tabela = pd.DataFrame(
        {
            "cnpj": linhas["cnpj"].astype(str),
            "trimestre": pd.to_datetime(linhas["fim"]).dt.to_period("Q"),
            "divulgado_em": pd.to_datetime(linhas["divulgado_em"]),
            "valor": linhas["valor"].astype(float),
        }
    ).dropna(subset=["divulgado_em", "valor"])
    return tabela.sort_values(
        ["cnpj", "trimestre", "divulgado_em"], kind="stable"
    ).reset_index(drop=True)


def acumulados_vigentes(
    linhas: pd.DataFrame, antes_de: pd.Timestamp
) -> dict[pd.Period, float]:
    """O acumulado de cada trimestre de um CNPJ na versão mais recente divulgada antes de `antes_de`."""
    vistas = linhas[linhas["divulgado_em"] < antes_de]
    return dict(
        zip(
            vistas["trimestre"],
            vistas["valor"],
            strict=True,
        )
    )  # a ordem por data de divulgação faz a última versão vencer


def lucro_do_trimestre(
    acumulados: dict[pd.Period, float], trimestre: pd.Period
) -> float:
    """O lucro só do trimestre: o acumulado menos o do trimestre anterior no mesmo ano."""
    atual = acumulados.get(trimestre, math.nan)
    if trimestre.quarter == 1:
        return atual
    return atual - acumulados.get(trimestre - 1, math.nan)


def surpresa(
    acumulados: dict[pd.Period, float], trimestre: pd.Period, trimestres_do_desvio: int
) -> tuple[float, float, float]:
    """SUE, variação sazonal e desvio (NaN quando falta algum trimestre ou o desvio é zero)."""

    def variacao(t: pd.Period) -> float:
        return lucro_do_trimestre(acumulados, t) - lucro_do_trimestre(
            acumulados, t - DEFASAGEM_SAZONAL
        )

    atual = variacao(trimestre)
    anteriores = np.array(
        [variacao(trimestre - j) for j in range(1, trimestres_do_desvio + 1)]
    )
    if math.isnan(atual) or np.isnan(anteriores).any():
        return math.nan, atual, math.nan
    desvio = float(np.std(anteriores, ddof=1))
    if desvio == 0:
        return math.nan, atual, desvio
    return atual / desvio, atual, desvio


def dias_dos_resultados(
    acumulados: pd.DataFrame, documentos: pd.DataFrame | None
) -> pd.Series:
    """D de cada (CNPJ, trimestre): a primeira entrega entre o IPE de resultados e o ITR ou a DFP."""
    do_balanco = acumulados.groupby(["cnpj", "trimestre"])["divulgado_em"].min()
    if documentos is None or documentos.empty:
        return do_balanco
    resultados = documentos[documentos["tema"] == TEMA_DOS_RESULTADOS]
    referencia = pd.to_datetime(resultados["referencia"])
    resultados = pd.DataFrame(
        {
            "cnpj": resultados["cnpj"].astype(str),
            "trimestre": referencia.dt.to_period("Q"),
            "publicado_em": pd.to_datetime(resultados["publicado_em"]),
        }
    )
    depois_do_fim = (
        resultados["publicado_em"] > referencia
    )  # documento antes do fim não é anúncio
    resultados = resultados[
        (referencia.dt.is_quarter_end.fillna(False) & depois_do_fim).to_numpy()
    ]
    do_ipe = resultados.groupby(["cnpj", "trimestre"])["publicado_em"].min()
    juntos = pd.concat([do_balanco, do_ipe.reindex(do_balanco.index)], axis=1)
    return juntos.min(axis=1)


# --- pregões, universo e sinais -----------------------------------------------------------------------


def _primeiro_pregao_a_partir(datas: pd.DatetimeIndex, dia: pd.Timestamp) -> int:
    return int(datas.searchsorted(dia, side="left"))


def posicoes_do_evento(
    datas: pd.DatetimeIndex, dia_do_resultado: pd.Timestamp, p: Parametros
) -> tuple[int, int]:
    """Dia zero e entrada (posições nos pregões) do evento, pela convenção de `p`."""
    no_dia = _primeiro_pregao_a_partir(datas, dia_do_resultado)
    dia_zero = _primeiro_pregao_a_partir(datas, dia_do_resultado + pd.Timedelta(days=1))
    if p.dia_zero_em_d:
        dia_zero = no_dia
    entrada = no_dia if p.executar_no_sinal else dia_zero + 1
    return dia_zero, entrada


def _escolhida_do_universo(
    dia: pd.Timestamp, dados: Dados, com_deslistadas: bool
) -> dict[str, str]:
    """CNPJ → ticker da classe escolhida pela seção 8 em D (uma por empresa, a mais líquida)."""
    candidatas = fb.elegiveis_em(dia, dados, com_deslistadas=com_deslistadas)
    candidatas = candidatas.sort_values("liquidez", ascending=False, kind="stable")
    unicas = candidatas.drop_duplicates("cnpj", keep="first")
    return dict(zip(unicas["cnpj"].astype(str), unicas.index.astype(str), strict=True))


class _Universos:
    """O universo de cada dia, calculado uma vez (muitos eventos caem no mesmo dia)."""

    def __init__(self, dados: Dados, com_deslistadas: bool) -> None:
        self.dados = dados
        self.com_deslistadas = com_deslistadas
        self._dias: dict[pd.Timestamp, dict[str, str]] = {}

    def em(self, dia: pd.Timestamp) -> dict[str, str]:
        if dia not in self._dias:
            self._dias[dia] = _escolhida_do_universo(
                dia, self.dados, self.com_deslistadas
            )
        return self._dias[dia]


def eventos_de_lucro(
    dados: Dados, p: Parametros, universos: _Universos | None = None
) -> tuple[pd.DataFrame, dict]:
    """Os anúncios de lucro do universo com a SUE de cada um e a contagem de cada etapa.

    A informação é a do candidato (tudo divulgado antes da entrada em D+2), também nas variantes
    de data (otimista e V (1)): só a data da entrada muda.
    """
    datas = pd.DatetimeIndex(dados.fechamento.index)
    universos = universos or _Universos(_so_o_lucro(dados), p.com_deslistadas)
    acumulados = acumulados_do_lucro(dados.fundamentos)
    dias = dias_dos_resultados(acumulados, dados.documentos)
    por_cnpj = dict(tuple(acumulados.groupby("cnpj", sort=False)))
    referencia = replace(p, dia_zero_em_d=False, executar_no_sinal=False)
    contagem = dict.fromkeys(
        (
            "trimestres",
            "atrasados",
            "fora_dos_pregoes",
            "fora_do_universo",
            "sem_linha",
            "sem_sue",
        ),
        0,
    )
    linhas = []
    for (cnpj, trimestre), dia in dias.items():
        contagem["trimestres"] += 1
        fim = trimestre.end_time.normalize()
        if dia > fim + pd.DateOffset(months=MESES_MAXIMOS_ATE_O_RESULTADO):
            contagem["atrasados"] += 1
            continue
        dia_zero, entrada = posicoes_do_evento(datas, dia, referencia)
        if entrada >= len(datas):
            contagem["fora_dos_pregoes"] += 1
            continue
        ticker = universos.em(datas[dia_zero]).get(str(cnpj))
        if ticker is None:
            contagem["fora_do_universo"] += 1
            continue
        vigentes = acumulados_vigentes(por_cnpj[cnpj], datas[entrada])
        if trimestre not in vigentes:
            contagem["sem_linha"] += 1
            continue
        sue, variacao, desvio = surpresa(vigentes, trimestre, p.trimestres_do_desvio)
        if math.isnan(sue):
            contagem["sem_sue"] += 1
            continue
        linhas.append(
            {
                "cnpj": str(cnpj),
                "trimestre": str(trimestre),
                "dia_do_resultado": dia,
                "sue": sue,
                "variacao": variacao,
                "desvio": desvio,
                "ticker": ticker,
                "dia_zero": datas[dia_zero],
            }
        )
    eventos = pd.DataFrame(linhas, columns=[*COLUNAS_DOS_EVENTOS, "ticker", "dia_zero"])
    eventos = eventos.sort_values(["dia_zero", "cnpj"], kind="stable").reset_index(
        drop=True
    )
    contagem["com_sue"] = len(eventos)
    return eventos, contagem


def corte_do_tercil(
    eventos: pd.DataFrame, dia_zero: pd.Timestamp, fracao_de_cima: float
) -> float:
    """O quantil que separa a fração de cima, com as SUEs dos 365 dias anteriores (NaN sem 30)."""
    anteriores = eventos[
        (eventos["dia_zero"] < dia_zero)
        & (eventos["dia_zero"] >= dia_zero - pd.Timedelta(days=DIAS_DO_CORTE_DO_TERCIL))
    ]["sue"]
    if len(anteriores) < EVENTOS_MINIMOS_DO_TERCIL:
        return math.nan
    return float(anteriores.quantile(1 - fracao_de_cima))


def sinais(dados: Dados, p: Parametros, eventos: pd.DataFrame) -> list[Sinal]:
    """Os eventos do tercil de cima, com a entrada pela convenção de data de `p`."""
    datas = pd.DatetimeIndex(dados.fechamento.index)
    escolhidos = []
    cortes: dict[pd.Timestamp, float] = {}
    for evento in eventos.itertuples(index=False):
        dia_zero = pd.Timestamp(evento.dia_zero)
        if dia_zero not in cortes:
            cortes[dia_zero] = corte_do_tercil(eventos, dia_zero, p.fracao_de_cima)
        corte = cortes[dia_zero]
        if math.isnan(corte) or not evento.sue > corte:
            continue
        posicao_zero, entrada = posicoes_do_evento(
            datas, pd.Timestamp(evento.dia_do_resultado), p
        )
        escolhidos.append(
            Sinal(
                ticker=str(evento.ticker),
                cnpj=str(evento.cnpj),
                trimestre=str(evento.trimestre),
                sue=float(evento.sue),
                dia_zero=posicao_zero,
                entrada=entrada,
            )
        )
    return escolhidos


# --- a carteira ---------------------------------------------------------------------------------------


def _so_o_lucro(dados: Dados) -> Dados:
    return replace(
        dados,
        fundamentos=dados.fundamentos[dados.fundamentos["conta"] == CONTA_DO_LUCRO],
    )


def _para_os_custos(p: Parametros) -> fb.Parametros:
    """Os parâmetros da F-B3 que o cálculo de custos dela lê (custos e Y)."""
    return fb.Parametros(custos=p.custos, fator_de_impacto=p.fator_de_impacto)


def _sigma_e_volume(dados: Dados, tickers: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """σ diário dos 252 pregões e volume médio dos 60, os dois até a véspera de cada dia."""
    fechamento = dados.fechamento[tickers]
    sigma = (
        fechamento.pct_change(fill_method=None)
        .rolling(fb.JANELA_DA_VOL, min_periods=fb.JANELA_DA_VOL)
        .std()
        .shift(1)
    )
    volume = (
        dados.volume[tickers]
        .fillna(0.0)
        .rolling(fb.PREGOES_DA_LIQUIDEZ, min_periods=1)
        .sum()
        / fb.PREGOES_DA_LIQUIDEZ
    ).shift(1)
    return sigma.to_numpy(float), volume.fillna(0.0).to_numpy(float)


def _quantidades_das_entradas(
    entradas: list[int],
    patrimonio: float,
    caixa: float,
    precos: np.ndarray,
    posicoes: int,
) -> dict[int, float]:
    """Ações a comprar em cada entrada do dia: 1/`posicoes` do patrimônio, dividindo o caixa se faltar."""
    validas = [j for j in entradas if precos[j] > 0]
    if not validas or caixa <= 0:
        return {}
    alvo = patrimonio / posicoes
    cada = min(alvo, caixa / len(validas))
    return {
        j: float(arredondar_lote(cada / precos[j], fracionario=True)) for j in validas
    }


class _Simulacao:
    """O estado da carteira durante `simular`, com uma etapa do dia por método."""

    def __init__(self, dados: Dados, p: Parametros, lista: list[Sinal]) -> None:
        self.p = p
        self.tickers = sorted({s.ticker for s in lista})
        self.datas = pd.DatetimeIndex(dados.fechamento.index)
        n, k = len(self.datas), len(self.tickers)
        self.n, self.k = n, k
        self.coluna = {t: j for j, t in enumerate(self.tickers)}
        self.V = dados.fechamento[self.tickers].ffill().to_numpy(float)
        A = dados.abertura[self.tickers].to_numpy(float)
        self.A = np.where(np.isnan(A), self.V, A)
        self.cdi = dados.cdi.to_numpy(float)
        self.sigma, self.volumes = _sigma_e_volume(dados, self.tickers)
        self.ultimo = fb._ultimo_pregao_de_cada_ticker(
            replace(dados, fechamento=dados.fechamento[self.tickers])
        )
        self.custos_p = _para_os_custos(p)
        fins = fb._fins_de_mes(self.datas)
        self.proximo_fim = {
            t: (fins[j + 1] if j + 1 < len(fins) else None) for j, t in enumerate(fins)
        }
        self.por_dia: dict[int, list[Sinal]] = {}
        for s in lista:
            self.por_dia.setdefault(s.entrada, []).append(s)
        self.carteira = fb._Carteira(p.capital_inicial, k)
        self.saidas: dict[
            int, list[tuple[int, int]]
        ] = {}  # dia → (coluna, dia da entrada)
        self.abertas: dict[int, dict] = {}  # coluna → a posição aberta
        self.fechadas: list[dict] = []
        self.retorno, self.patrimonio = np.zeros(n), np.zeros(n)
        self.custos, self.imposto = np.zeros(n), np.zeros(n)
        self.pesos, self.negociado = np.zeros((n, k)), np.zeros(n)
        self.a_pagar: dict[int, float] = {}
        self.ignorados = 0
        self.pat_ontem = p.capital_inicial

    def negociar(
        self, delta_q: np.ndarray, precos: np.ndarray, t: int, com_impacto: bool
    ) -> None:
        sem = np.zeros(self.k)
        custo = fb._custo_das_ordens(
            delta_q * np.nan_to_num(precos),
            self.sigma[t] if com_impacto else sem,
            self.volumes[t] if com_impacto else sem,
            self.custos_p,
        )
        self.carteira.executar(delta_q, precos, custo)
        self.negociado[t] += float(np.abs(np.nan_to_num(delta_q * precos)).sum())
        self.custos[t] += custo.sum()

    def zerar(self, j: int, precos: np.ndarray, t: int, com_impacto: bool) -> None:
        delta_q = np.zeros(self.k)
        delta_q[j] = -self.carteira.q[j]
        self.negociar(delta_q, precos, t, com_impacto)

    def fechar(self, j: int, t: int, preco: float, motivo: str) -> None:
        posicao = self.abertas.pop(j)
        posicao.pop("t")
        self.fechadas.append(
            {
                **posicao,
                "saida": self.datas[t].date().isoformat(),
                "preco_de_saida": preco,
                "motivo": motivo,
            }
        )

    def vender_as_deslistadas(self, t: int) -> None:
        for j in [j for j in self.abertas if t > self.ultimo[j]]:
            self.zerar(j, self.V[t], t, com_impacto=False)
            self.fechar(j, t, float(self.V[t, j]), "deslistada")

    def sair_das_vencidas(self, t: int) -> None:
        for j, desde in self.saidas.pop(t, []):
            if self.abertas.get(j, {}).get("t") == desde:  # a mesma (não uma reaberta)
                self.zerar(j, self.A[t], t, com_impacto=True)
                self.fechar(j, t, float(self.A[t, j]), "60 pregões")

    def entrar(self, t: int) -> None:
        hoje = []
        for s in self.por_dia.get(t, []):
            j = self.coluna[s.ticker]
            if j in self.abertas or j in hoje or t > self.ultimo[j]:
                self.ignorados += 1
                continue
            hoje.append(j)
        if not hoje:
            return
        A, carteira = self.A[t], self.carteira
        quantidades = _quantidades_das_entradas(
            hoje, carteira.patrimonio(A), carteira.caixa, A, self.p.posicoes
        )
        delta_q = np.zeros(self.k)
        for j, q in quantidades.items():
            delta_q[j] = q
        delta_q = _cabe_no_caixa(
            delta_q, carteira.caixa, A, self.sigma[t], self.volumes[t], self.custos_p
        )
        self.negociar(delta_q, A, t, com_impacto=True)
        sinal_de = {self.coluna[s.ticker]: s for s in self.por_dia[t]}
        for j in np.flatnonzero(delta_q > 0):
            s = sinal_de[int(j)]
            self.abertas[int(j)] = {
                "ticker": s.ticker,
                "cnpj": s.cnpj,
                "trimestre": s.trimestre,
                "sue": s.sue,
                "entrada": self.datas[t].date().isoformat(),
                "preco_de_entrada": float(A[j]),
                "t": t,
            }
            self.saidas.setdefault(t + self.p.pregoes_na_posicao, []).append(
                (int(j), t)
            )

    def pagar_o_imposto(self, t: int) -> None:
        if t in self.a_pagar:
            devido = self.a_pagar.pop(t)
            delta_q, custo = fb._vender_para_pagar(
                self.carteira, devido, self.V[t], self.custos_p
            )
            self.carteira.executar(delta_q, self.V[t], custo)
            self.custos[t] += custo.sum()
            self.carteira.caixa -= devido
            self.imposto[t] = devido
            for j in [j for j in self.abertas if self.carteira.q[j] <= 0]:
                self.fechar(j, t, float(self.V[t, j]), "DARF")
        if t in self.proximo_fim:
            devido = self.carteira.fechar_mes(self.datas[t], self.p.custos)
            vencimento = self.proximo_fim[t]
            if devido > 0 and vencimento is not None:
                self.a_pagar[vencimento] = self.a_pagar.get(vencimento, 0.0) + devido

    def marcar(self, t: int) -> None:
        pat_fim = self.carteira.patrimonio(self.V[t])
        self.retorno[t] = pat_fim / self.pat_ontem - 1 if t > 0 else 0.0
        self.patrimonio[t] = pat_fim
        if self.k:
            self.pesos[t] = np.nan_to_num(self.carteira.valores(self.V[t])) / pat_fim
        self.pat_ontem = pat_fim

    def rodar(self) -> None:
        for t in range(self.n):
            if t > 0:
                self.carteira.caixa *= 1 + self.cdi[t]
            self.vender_as_deslistadas(t)
            self.sair_das_vencidas(t)
            self.entrar(t)
            self.pagar_o_imposto(t)
            self.marcar(t)
        for j in list(self.abertas):
            self.fechar(j, self.n - 1, float(self.V[self.n - 1, j]), "fim dos dados")


def simular(
    dados: Dados,
    parametros: Parametros,
    eventos: pd.DataFrame | None = None,
    contagem: dict | None = None,
) -> Resultado:
    """Simula a carteira dia a dia (ver as convenções no topo do módulo).

    `eventos` e `contagem` vêm de `eventos_de_lucro`; quem roda várias leituras com os mesmos
    trimestres pode passá-los para não refazer a conta.
    """
    fb._conferir_entradas(dados)
    p = parametros
    dados = _so_o_lucro(dados)
    if eventos is None or contagem is None:
        eventos, contagem = eventos_de_lucro(dados, p)
    lista = [s for s in sinais(dados, p, eventos) if s.entrada < len(dados.fechamento)]
    sim = _Simulacao(dados, p, lista)
    sim.rodar()
    anos = max(sim.n / 252, 1e-9)
    tabela = pd.DataFrame(sim.fechadas)
    if len(tabela):
        tabela["retorno"] = tabela["preco_de_saida"] / tabela["preco_de_entrada"] - 1
    return Resultado(
        retorno=pd.Series(sim.retorno, index=sim.datas, name="retorno"),
        patrimonio=pd.Series(sim.patrimonio, index=sim.datas, name="patrimonio"),
        pesos=pd.DataFrame(sim.pesos, index=sim.datas, columns=sim.tickers),
        custos=pd.Series(sim.custos, index=sim.datas, name="custos"),
        imposto=pd.Series(sim.imposto, index=sim.datas, name="imposto"),
        giro=float(sim.negociado.sum() / anos / sim.patrimonio.mean()),
        posicoes=tabela,
        contagem={**contagem, "sinais": len(lista), "sinais_ignorados": sim.ignorados},
        parametros=p,
    )


def _cabe_no_caixa(
    delta_q: np.ndarray,
    caixa: float,
    precos: np.ndarray,
    sigma: np.ndarray,
    volumes: np.ndarray,
    custos_p: fb.Parametros,
) -> np.ndarray:
    """Tira uma ação da maior compra até o caixa pagar as compras e os custos."""
    delta_q = delta_q.copy()

    def falta() -> float:
        custo = fb._custo_das_ordens(
            delta_q * np.nan_to_num(precos), sigma, volumes, custos_p
        )
        return float(np.nansum(delta_q * precos) + custo.sum() - caixa)

    while falta() > 0 and (delta_q > 0).any():
        maior = int(np.argmax(delta_q * np.nan_to_num(precos)))
        delta_q[maior] = max(
            delta_q[maior] - max(1.0, np.ceil(0.01 * delta_q[maior])), 0.0
        )
    return delta_q


# --- o estudo dos eventos (CAR) -----------------------------------------------------------------------


def chave_do_documento(categoria: str, tipo: str) -> str:
    tipo = (tipo or "").strip()
    return f"{categoria} · {tipo}" if tipo else str(categoria)


def retornos_anormais(
    retornos: np.ndarray,
    mercado: np.ndarray,
    coluna: int,
    dia_zero: int,
) -> float:
    """CAR (+1, +60) de um evento pelo modelo de mercado (NaN sem 200 retornos ou sem a janela)."""
    inicio = dia_zero - 1 - PREGOES_DA_ESTIMACAO
    fim_da_janela = dia_zero + FIM_DA_JANELA_DO_CAR
    if inicio < 1 or fim_da_janela >= len(mercado):
        return math.nan
    r_i = retornos[inicio : dia_zero - 1, coluna]
    r_m = mercado[inicio : dia_zero - 1]
    validos = ~np.isnan(r_i) & ~np.isnan(r_m)
    if validos.sum() < RETORNOS_MINIMOS_DA_ESTIMACAO:
        return math.nan
    beta, alfa = np.polyfit(r_m[validos], r_i[validos], 1)
    janela = slice(dia_zero + INICIO_DA_JANELA_DO_CAR, fim_da_janela + 1)
    anormal = retornos[janela, coluna] - alfa - beta * mercado[janela]
    return float(np.nansum(anormal))


def estudo_dos_eventos(
    dados: Dados, p: Parametros, eventos_de_lucro_: pd.DataFrame | None = None
) -> dict:
    """CAR (+1, +60) por tipo de documento do IPE e por tercil da SUE (estudo, sem carteira)."""
    ibovespa = dados.ibovespa
    if ibovespa is None:
        raise ValueError("o estudo dos eventos precisa do mercado (BOVA11)")
    dados = _so_o_lucro(dados)
    datas = pd.DatetimeIndex(dados.fechamento.index)
    tickers = list(dados.fechamento.columns)
    coluna = {t: j for j, t in enumerate(tickers)}
    precos = dados.fechamento.ffill(limit_area="inside")
    retornos = precos.pct_change(fill_method=None).to_numpy(float)
    mercado = ibovespa.reindex(datas).to_numpy(float)
    universos = _Universos(dados, p.com_deslistadas)
    linhas = []
    documentos = dados.documentos if dados.documentos is not None else pd.DataFrame()
    if "versao" in documentos:  # a reapresentação de um documento não é notícia nova
        documentos = documentos[documentos["versao"] == 1]
    vistos: set[tuple[str, str, int]] = set()
    for doc in documentos.itertuples(index=False):
        dia_zero, _ = posicoes_do_evento(datas, pd.Timestamp(doc.publicado_em), p)
        if dia_zero >= len(datas):
            continue
        ticker = universos.em(datas[dia_zero]).get(str(doc.cnpj))
        chave = chave_do_documento(str(doc.categoria), str(doc.tipo))
        if ticker is None or (str(doc.cnpj), chave, dia_zero) in vistos:
            continue
        vistos.add((str(doc.cnpj), chave, dia_zero))
        car = retornos_anormais(retornos, mercado, coluna[ticker], dia_zero)
        if not math.isnan(car):
            linhas.append({"chave": chave, "car": car})
    por_tipo = _resumir_car(pd.DataFrame(linhas, columns=["chave", "car"]), "chave")
    por_tercil: dict = {}
    if eventos_de_lucro_ is not None and len(eventos_de_lucro_):
        cars = []
        for evento in eventos_de_lucro_.itertuples(index=False):
            dia_zero = int(datas.get_loc(pd.Timestamp(evento.dia_zero)))
            corte_de_cima = corte_do_tercil(
                eventos_de_lucro_, pd.Timestamp(evento.dia_zero), p.fracao_de_cima
            )
            corte_de_baixo = corte_do_tercil(
                eventos_de_lucro_, pd.Timestamp(evento.dia_zero), 1 - p.fracao_de_cima
            )
            if math.isnan(corte_de_cima):
                continue
            tercil = (
                "de cima"
                if evento.sue > corte_de_cima
                else ("de baixo" if evento.sue <= corte_de_baixo else "do meio")
            )
            car = retornos_anormais(
                retornos, mercado, coluna[str(evento.ticker)], dia_zero
            )
            if not math.isnan(car):
                cars.append({"chave": tercil, "car": car})
        por_tercil = _resumir_car(pd.DataFrame(cars, columns=["chave", "car"]), "chave")
    return {
        "por_tipo": por_tipo,
        "por_tercil_da_sue": por_tercil,
        "documentos": len(linhas),
    }


def _resumir_car(tabela: pd.DataFrame, chave: str) -> dict:
    resumo = {}
    for nome, grupo in tabela.groupby(chave, sort=True):
        car = grupo["car"]
        desvio = float(car.std(ddof=1)) if len(car) > 1 else math.nan
        resumo[str(nome)] = {
            "n": len(car),
            "media": float(car.mean()),
            "mediana": float(car.median()),
            "t": float(car.mean() / desvio * math.sqrt(len(car)))
            if desvio and desvio > 0
            else math.nan,
            "positivos": float((car > 0).mean()),
        }
    return resumo


# --- verificações -------------------------------------------------------------------------------------


def hash_do_resultado(resultado: Resultado) -> str:
    """Impressão digital do retorno e do patrimônio (reexecução idêntica)."""
    bruto = (
        resultado.retorno.round(12).to_numpy().tobytes()
        + resultado.patrimonio.round(6).to_numpy().tobytes()
    )
    return hashlib.sha256(bruto).hexdigest()


def cortar(dados: Dados, corte: pd.Timestamp) -> Dados:
    """As mesmas tabelas como seriam vistas em `corte` (inclusive os documentos do IPE)."""
    base = fb.cortar(dados, corte)
    documentos = dados.documentos
    if documentos is not None:
        documentos = documentos[pd.to_datetime(documentos["publicado_em"]) <= corte]
    return Dados(
        **{f.name: getattr(base, f.name) for f in fields(fb.Dados)},
        documentos=documentos,
    )


def cortar_o_futuro_nao_muda_o_passado(
    dados: Dados, parametros: Parametros, corte: pd.Timestamp
) -> bool:
    """Rodar só com o que existia em `corte` dá, até a véspera, o mesmo retorno de rodar tudo."""
    inteiro = simular(dados, parametros)
    cortado = simular(cortar(dados, corte), parametros)
    return bool(
        np.allclose(
            inteiro.retorno[inteiro.retorno.index < corte].to_numpy(),
            cortado.retorno[cortado.retorno.index < corte].to_numpy(),
            rtol=0,
            atol=1e-12,
        )
    )


def com(parametros: Parametros, **mudancas: object) -> Parametros:
    """Uma cópia dos parâmetros com algumas mudanças (vizinhos do platô, estresse, testes)."""
    return replace(parametros, **mudancas)
