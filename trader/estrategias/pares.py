"""Pares por cointegração na B3 (ficha P0-4 do pré-registro quant v0.1).

Convenções fixadas AQUI, antes de qualquer número (seção 10 do pré-registro: mudar depois de
ver um resultado é tentativa nova):

- **Entradas** (`Dados`): as tabelas da F-B3 (`fatores_b3.Dados`: fechamento ajustado, volume,
  cadastro, balanços para o universo, CDI) mais `setores` (CNPJ, setor, `conhecido_em`), o setor
  do FCA da CVM ponto no tempo: em D vale o último setor com `conhecido_em` < D.
- **Janelas.** A primeira operação começa `MESES_DE_FORMACAO` (12) meses depois do primeiro
  pregão dos dados; cada operação dura 6 meses de calendário e a seguinte começa onde ela acaba,
  sem sobreposição. A formação são os `meses_de_formacao` meses antes do começo da operação; a
  janela cuja formação começaria antes dos dados fica em caixa (só acontece no vizinho de 14).
- **Formação**, no último pregão antes da operação: universo da seção 8 (`elegiveis_em` da F-B3:
  liquidez, 12 meses de pregão, balanço recente, sem recuperação judicial) e preço em todos os
  pregões da formação. Conjuntos de pares: `todos` (uma classe por empresa, a mais líquida, e
  todos os pares entre elas), `setor` (só pares do mesmo setor) e `on_pn` (as classes da mesma
  empresa, todas as que passam pela seção 8).
- **Engle-Granger.** Log dos preços ajustados; a perna dependente (y) é a mais líquida na
  formação; mínimos quadrados dão α e β; par com β ≤ 0 não é par (p = 1). ADF com constante e
  `DEFASAGENS_DO_ADF` (1) defasagem no resíduo; p-valor de MacKinnon para duas séries
  (`mackinnonp(t, "c", N=2)`). Benjamini-Hochberg a `q_do_bh` (5%) sobre todos os pares testados
  na janela; dos que passam, meia-vida do resíduo entre 5 e 30 pregões; os `max_pares` (10) de
  menor p ajustado (empate: menor meia-vida) operam. Um ticker pode estar em mais de um par.
- **Sinal** no fechamento de D: z = (log y − α − β·log x − média) ÷ desvio, média e desvio do
  resíduo da formação. Sem posição: 2 < |z| ≤ 4 entra (z > 2 vende o spread: vende y e compra x;
  z < −2 compra o spread); acima do stop não entra. Com posição: |z| > 4 ou ⌈3 × meia-vida⌉
  pregões na posição é stop e o par sai da janela; |z| < 0,5 é saída e o par pode voltar.
- **Execução** no fechamento do pregão seguinte (`executar_no_sinal=True` é a versão inflada
  do teste V (1): no próprio fechamento), tarifa de leilão. No último pregão da operação tudo é
  zerado e nada abre. Deslistagem (OPA, fechamento de capital): no primeiro pregão sem a perna,
  as duas pernas fecham, a deslistada pelo último preço, e o par sai da janela.
- **Tamanho.** Cada par recebe o patrimônio da véspera da operação ÷ `max_pares` (pares a
  menos deixam caixa): perna y = alocação ÷ (1 + β), perna x = β × alocação ÷ (1 + β), em ações
  inteiras (lote padrão mais o fracionário, como na F-B3); `fracionario=False` é o teste (b), só
  em lotes de 100. Se uma perna arredonda para zero, o par não entra naquele sinal.
- **Caixa e custos.** Patrimônio = caixa + Σ quantidade × preço (a perna vendida tem quantidade
  negativa); o caixa, com o dinheiro da venda a descoberto, rende o CDI (limitação declarada: na
  B3 a garantia rende, mas nem sempre o CDI inteiro). Cada ordem paga `custo_de_negociar` com
  tarifa de leilão mais o impacto Y·σ·√(Q/V)·Q (σ e V da formação, como na F-B3); a perna
  vendida paga, ao fechar, `custo_do_aluguel` sobre o valor da venda pelos dias corridos à taxa
  `taxa_do_aluguel` (5% a.a. no candidato; 2% e 10% no teste (a)), mínimo de R$ 10.
- **IR.** O resultado de cada perna sai no fechamento, líquido de custos e aluguel; a venda a
  descoberto conta como venda do mês em que fecha (para a isenção de R$ 20 mil) e o ganho é
  swing (`apurar_ir_mensal`, classe "acoes"); o DARF do mês M sai do caixa no último pregão de
  M+1. Pares abertos e fechados no mesmo pregão (por construção, zero) e dias em que o mesmo
  ticker é comprado e vendido (day trade; só acontece entre pares que dividem um ticker) são
  contados e vão ao relatório; o IR desses dias é apurado como swing (limitação declarada).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field, fields, replace
from itertools import combinations

import numpy as np
import pandas as pd
from statsmodels.tsa.adfvalues import mackinnonp

from src.pares import calcular_adf, calcular_meia_vida, estimar_relacao
from trader.custos_br import (
    PADRAO,
    CustosBR,
    arredondar_lote,
    custo_de_negociar,
    custo_do_aluguel,
)
from trader.estrategias import fatores_b3 as fb

VERSAO = "0.1"
CLASSE = "acoes"
MESES_DE_FORMACAO = 12
MESES_DE_OPERACAO = 6
Z_ENTRADA = 2.0
Z_SAIDA = 0.5
Z_STOP = 4.0
MULTIPLO_DA_MEIA_VIDA = 3.0
MEIA_VIDA_MINIMA = 5.0
MEIA_VIDA_MAXIMA = 30.0
MAX_PARES = 10
Q_DO_BH = 0.05
TAXA_DO_ALUGUEL = 0.05
DEFASAGENS_DO_ADF = 1
CAPITAL_INICIAL = 100_000.0
CONJUNTOS = ("todos", "setor", "on_pn")
COLUNAS_DOS_SETORES = ("cnpj", "setor", "conhecido_em")
COLUNAS_DAS_OPERACOES = (
    "y",
    "x",
    "lado",
    "sinal",
    "entrada",
    "saida",
    "motivo",
    "q_y",
    "q_x",
    "resultado",
)
COMPRAR_SPREAD, VENDER_SPREAD, SAIR, STOP = "comprar", "vender", "sair", "stop"
# O bruto da ficha: sem corretagem, tarifa do leilão, IR nem o mínimo do aluguel (a taxa do
# aluguel vai a zero pelos parâmetros, `taxa_do_aluguel=0`).
SEM_CUSTOS = replace(fb.SEM_CUSTOS, emolumentos_no_leilao=0.0, aluguel_minimo=0.0)


@dataclass
class Dados(fb.Dados):
    """As tabelas da F-B3 mais o setor de cada CNPJ, ponto no tempo (ver o topo do módulo)."""

    setores: pd.DataFrame | None = None


@dataclass(frozen=True)
class Parametros:
    meses_de_formacao: int = MESES_DE_FORMACAO
    z_entrada: float = Z_ENTRADA
    z_saida: float = Z_SAIDA
    z_stop: float = Z_STOP
    multiplo_da_meia_vida: float = MULTIPLO_DA_MEIA_VIDA
    max_pares: int = MAX_PARES
    q_do_bh: float = Q_DO_BH
    conjunto: str = "todos"
    taxa_do_aluguel: float = TAXA_DO_ALUGUEL
    fracionario: bool = True
    executar_no_sinal: bool = False
    capital_inicial: float = CAPITAL_INICIAL
    com_deslistadas: bool = True
    custos: CustosBR = PADRAO
    fator_de_impacto: float = 1.0

    def __post_init__(self) -> None:
        if self.conjunto not in CONJUNTOS:
            raise ValueError(f"conjunto precisa ser um de {CONJUNTOS}")
        if not 0 < self.z_saida < self.z_entrada < self.z_stop:
            raise ValueError("os limiares precisam ser 0 < saída < entrada < stop")
        if (
            self.max_pares < 1
            or self.meses_de_formacao < 1
            or self.capital_inicial <= 0
        ):
            raise ValueError(
                "max_pares, meses de formação e capital precisam ser positivos"
            )
        if self.taxa_do_aluguel < 0 or not 0 < self.q_do_bh < 1:
            raise ValueError("taxa do aluguel >= 0 e q do BH em (0, 1)")

    def especificacao(self) -> dict:
        """Tudo o que define a tentativa, em tipos simples (vai para o registro)."""
        spec = asdict(self)
        spec["custos"] = asdict(self.custos)
        spec["custos"]["a_confirmar"] = list(spec["custos"]["a_confirmar"])
        spec["versao"] = VERSAO
        spec["meses_de_operacao"] = MESES_DE_OPERACAO
        spec["meia_vida"] = [MEIA_VIDA_MINIMA, MEIA_VIDA_MAXIMA]
        spec["defasagens_do_adf"] = DEFASAGENS_DO_ADF
        return spec


@dataclass(frozen=True)
class Janela:
    """Posições (nos pregões dos dados) da formação e da operação, as duas inclusivas."""

    inicio_da_formacao: int
    fim_da_formacao: int
    inicio: int
    fim: int


@dataclass(frozen=True)
class Par:
    y: str
    x: str
    alfa: float
    beta: float
    media: float
    desvio: float
    meia_vida: float
    p_valor: float
    p_ajustado: float

    def z(self, log_y: float, log_x: float) -> float:
        return (log_y - self.alfa - self.beta * log_x - self.media) / self.desvio


@dataclass(frozen=True)
class Formacao:
    testados: int
    cointegrados: int  # passaram pelo Benjamini-Hochberg
    candidatos: tuple[Par, ...]  # e pela meia-vida, do menor p ajustado ao maior


@dataclass
class Resultado:
    retorno: pd.Series  # diário, líquido, da véspera da primeira operação em diante
    patrimonio: pd.Series
    pesos: pd.DataFrame  # com sinal: a perna vendida tem peso negativo
    negociado: pd.DataFrame  # reais por ticker e dia (+ compra, − venda)
    custos: pd.Series  # corretagem, bolsa e impacto, por dia
    aluguel: pd.Series
    imposto: pd.Series  # DARF pago, por dia
    giro: float
    janelas: list[dict]
    operacoes: pd.DataFrame
    dias_de_day_trade: int
    fechadas_no_dia_da_entrada: int
    quebrados_por_deslistagem: int
    parametros: Parametros = field(repr=False)


# --- janelas e formação ---------------------------------------------------------------------------


def janelas(
    datas: pd.DatetimeIndex, meses_de_formacao: int = MESES_DE_FORMACAO
) -> list[Janela]:
    """As janelas de formação e operação (ver o topo do módulo), só com formação inteira."""
    primeiro = datas[0]
    resultado = []
    for k in range(len(datas)):
        comeco = primeiro + pd.DateOffset(
            months=MESES_DE_FORMACAO + k * MESES_DE_OPERACAO
        )
        inicio = int(datas.searchsorted(comeco))
        if inicio >= len(datas):
            break
        fim = (
            int(datas.searchsorted(comeco + pd.DateOffset(months=MESES_DE_OPERACAO)))
            - 1
        )
        comeco_da_formacao = comeco - pd.DateOffset(months=meses_de_formacao)
        if comeco_da_formacao < primeiro:
            continue
        resultado.append(
            Janela(int(datas.searchsorted(comeco_da_formacao)), inicio - 1, inicio, fim)
        )
    return resultado


def benjamini_hochberg(p_valores: np.ndarray) -> np.ndarray:
    """P-valores ajustados de Benjamini-Hochberg (rejeita a q quem tem ajustado <= q)."""
    p = np.asarray(p_valores, dtype=float)
    m = len(p)
    if m == 0:
        return p
    ordem = np.argsort(p, kind="stable")
    escalado = p[ordem] * m / np.arange(1, m + 1)
    ajustado = np.minimum.accumulate(escalado[::-1])[::-1]
    resultado = np.empty(m)
    resultado[ordem] = np.minimum(ajustado, 1.0)
    return resultado


def _so_digitos(cnpj: object) -> str:
    return "".join(c for c in str(cnpj) if c.isdigit())


def setores_em(setores: pd.DataFrame | None, dia: pd.Timestamp) -> dict[str, str]:
    """O setor de cada CNPJ (só os dígitos) que podia ser lido em D."""
    if setores is None or setores.empty:
        return {}
    conhecidos = setores[pd.to_datetime(setores["conhecido_em"]) < dia]
    conhecidos = conhecidos.dropna(subset=["setor"]).sort_values(
        "conhecido_em", kind="stable"
    )
    return {
        _so_digitos(c): str(s)
        for c, s in zip(conhecidos["cnpj"], conhecidos["setor"], strict=True)
    }


def pares_do_conjunto(
    elegiveis: pd.DataFrame, conjunto: str, setores: dict[str, str]
) -> list[tuple[str, str]]:
    """Os pares a testar entre os elegíveis (índice = ticker; colunas cnpj e liquidez)."""
    if conjunto == "on_pn":
        pares: list[tuple[str, str]] = []
        for _, grupo in elegiveis.groupby("cnpj", sort=True):
            pares.extend(combinations(sorted(grupo.index.astype(str)), 2))
        return pares
    uma_por_empresa = elegiveis.sort_values(
        "liquidez", ascending=False, kind="stable"
    ).drop_duplicates("cnpj", keep="first")
    tickers = sorted(uma_por_empresa.index.astype(str))
    todos = list(combinations(tickers, 2))
    if conjunto == "todos":
        return todos
    setor = {
        t: setores.get(_so_digitos(uma_por_empresa.loc[t, "cnpj"])) for t in tickers
    }
    return [(a, b) for a, b in todos if setor[a] is not None and setor[a] == setor[b]]


def _testar(
    log_y: pd.Series, log_x: pd.Series
) -> tuple[float, float, pd.Series, float]:
    """Engle-Granger de um par: (α, β, resíduo, p-valor de MacKinnon)."""
    alfa, beta = estimar_relacao(log_y, log_x)
    residuo = log_y - alfa - beta * log_x
    if beta <= 0:
        return alfa, beta, residuo, 1.0
    t = calcular_adf(residuo, DEFASAGENS_DO_ADF)
    return (
        alfa,
        beta,
        residuo,
        float(mackinnonp(t, regression="c", N=2)) if np.isfinite(t) else 1.0,
    )


def formar(dados: Dados, janela: Janela, p: Parametros) -> Formacao:
    """Os pares que operam na janela, só com o que se sabia no último pregão da formação."""
    datas = pd.DatetimeIndex(dados.fechamento.index)
    dia = datas[janela.fim_da_formacao]
    trecho = dados.fechamento.iloc[
        janela.inicio_da_formacao : janela.fim_da_formacao + 1
    ]
    completos = trecho.columns[(trecho.notna() & (trecho > 0)).all()]
    elegiveis = fb.elegiveis_em(dia, dados, com_deslistadas=p.com_deslistadas)
    elegiveis = elegiveis[elegiveis.index.isin(completos)]
    pares = pares_do_conjunto(elegiveis, p.conjunto, setores_em(dados.setores, dia))
    if not pares:
        return Formacao(0, 0, ())
    liquidez = (
        dados.volume.iloc[janela.inicio_da_formacao : janela.fim_da_formacao + 1]
        .fillna(0.0)
        .mean()
    )
    log = np.log(trecho[completos])
    testes = []
    for a, b in pares:
        y, x = (a, b) if liquidez[a] >= liquidez[b] else (b, a)
        testes.append((y, x, *_testar(log[y], log[x])))
    ajustados = benjamini_hochberg(np.array([t[5] for t in testes]))
    candidatos = []
    for (y, x, alfa, beta, residuo, p_valor), ajustado in zip(
        testes, ajustados, strict=True
    ):
        if ajustado > p.q_do_bh:
            continue
        meia_vida = calcular_meia_vida(residuo)
        desvio = float(residuo.std())
        if MEIA_VIDA_MINIMA <= meia_vida <= MEIA_VIDA_MAXIMA and desvio > 0:
            candidatos.append(
                Par(
                    y,
                    x,
                    alfa,
                    beta,
                    float(residuo.mean()),
                    desvio,
                    meia_vida,
                    p_valor,
                    float(ajustado),
                )
            )
    candidatos.sort(key=lambda par: (par.p_ajustado, par.meia_vida, par.y, par.x))
    return Formacao(len(testes), int((ajustados <= p.q_do_bh).sum()), tuple(candidatos))


# --- sinal ------------------------------------------------------------------------------------------


def decidir(
    z: float, lado: int, pregoes_na_posicao: int, limite_de_pregoes: int, p: Parametros
) -> str:
    """O que fazer com o par no fechamento (vazio = nada): entrar, sair ou stop."""
    if not np.isfinite(z):
        return ""
    if lado == 0:
        if p.z_entrada < abs(z) <= p.z_stop:
            return VENDER_SPREAD if z > 0 else COMPRAR_SPREAD
        return ""
    if abs(z) > p.z_stop or pregoes_na_posicao >= limite_de_pregoes:
        return STOP
    if abs(z) < p.z_saida:
        return SAIR
    return ""


# --- motor ------------------------------------------------------------------------------------------


@dataclass
class _Posicao:
    par: Par
    lado: int  # +1 comprado no spread (compra y, vende x); −1 vendido
    q_y: float
    q_x: float
    preco_y: float
    preco_x: float
    custo_y: float
    custo_x: float
    sinal: int
    entrada: int


class _Motor:
    """Estado da simulação (caixa, posições, IR e as séries do resultado)."""

    def __init__(self, dados: Dados, p: Parametros) -> None:
        self.p = p
        self.datas = pd.DatetimeIndex(dados.fechamento.index)
        self.tickers = list(dados.fechamento.columns)
        self.coluna = {t: j for j, t in enumerate(self.tickers)}
        self.V = dados.fechamento.ffill().to_numpy(float)
        self.ultimo = fb._ultimo_pregao_de_cada_ticker(dados)
        n, k = self.V.shape
        self.carteira = fb._Carteira(p.capital_inicial, 0)  # caixa e IR do mês
        self.custos, self.aluguel = np.zeros(n), np.zeros(n)
        self.negociado = np.zeros((n, k))
        self.compras: set[tuple[int, int]] = set()
        self.vendas: set[tuple[int, int]] = set()
        self.operacoes: list[dict] = []
        self.fechadas_no_dia = 0
        self.sigma = np.zeros(k)
        self.volume = np.zeros(k)

    def _custo(self, valor: float, j: int, *, com_impacto: bool = True) -> float:
        custo = custo_de_negociar(
            abs(valor), CLASSE, no_leilao=True, custos=self.p.custos
        )
        if com_impacto and valor != 0:
            v = self.volume[j] if self.volume[j] > 0 else abs(valor)
            desvio = self.sigma[j] if np.isfinite(self.sigma[j]) else 0.0
            custo += (
                self.p.fator_de_impacto
                * desvio
                * math.sqrt(abs(valor) / v)
                * abs(valor)
            )
        return custo

    def _ordem(
        self, t: int, j: int, quantidade: float, preco: float, custo: float
    ) -> None:
        self.carteira.caixa -= quantidade * preco + custo
        self.negociado[t, j] += quantidade * preco
        self.custos[t] += custo
        (self.compras if quantidade > 0 else self.vendas).add((t, j))

    def abrir(
        self, par: Par, lado: int, alocacao: float, sinal: int, t: int
    ) -> _Posicao | None:
        y, x = self.coluna[par.y], self.coluna[par.x]
        preco_y, preco_x = self.V[t, y], self.V[t, x]
        q_y = arredondar_lote(
            alocacao / (1 + par.beta) / preco_y, fracionario=self.p.fracionario
        )
        q_x = arredondar_lote(
            alocacao * par.beta / (1 + par.beta) / preco_x,
            fracionario=self.p.fracionario,
        )
        if q_y == 0 or q_x == 0:
            return None
        q_y, q_x = float(lado * q_y), float(-lado * q_x)
        custo_y, custo_x = self._custo(q_y * preco_y, y), self._custo(q_x * preco_x, x)
        self._ordem(t, y, q_y, preco_y, custo_y)
        self._ordem(t, x, q_x, preco_x, custo_x)
        return _Posicao(
            par, lado, q_y, q_x, preco_y, preco_x, custo_y, custo_x, sinal, t
        )

    def _fechar_perna(
        self,
        t: int,
        j: int,
        q: float,
        preco_de_entrada: float,
        custo_de_entrada: float,
        dias: int,
        com_impacto: bool,
    ) -> float:
        preco = self.V[t, j]
        custo = self._custo(q * preco, j, com_impacto=com_impacto)
        self._ordem(t, j, -q, preco, custo)
        if q > 0:
            self.carteira.vendas_do_mes += q * preco
            return q * (preco - preco_de_entrada) - custo_de_entrada - custo
        aluguel = custo_do_aluguel(
            -q * preco_de_entrada,
            dias=dias,
            taxa_anual=self.p.taxa_do_aluguel,
            custos=self.p.custos,
        )
        self.carteira.caixa -= aluguel
        self.aluguel[t] += aluguel
        self.carteira.vendas_do_mes += -q * preco_de_entrada
        return -q * (preco_de_entrada - preco) - custo_de_entrada - custo - aluguel

    def fechar(self, posicao: _Posicao, t: int, motivo: str) -> None:
        par = posicao.par
        dias = max((self.datas[t] - self.datas[posicao.entrada]).days, 1)
        deslistagem = motivo == "deslistagem"
        resultado = 0.0
        for ticker, q, preco, custo in (
            (par.y, posicao.q_y, posicao.preco_y, posicao.custo_y),
            (par.x, posicao.q_x, posicao.preco_x, posicao.custo_x),
        ):
            j = self.coluna[ticker]
            sem_impacto = deslistagem and t > self.ultimo[j]
            resultado += self._fechar_perna(
                t, j, q, preco, custo, dias, not sem_impacto
            )
        self.carteira.resultado_do_mes += resultado
        self.fechadas_no_dia += int(t == posicao.entrada)
        self.operacoes.append(
            {
                "y": par.y,
                "x": par.x,
                "lado": posicao.lado,
                "sinal": self.datas[posicao.sinal],
                "entrada": self.datas[posicao.entrada],
                "saida": self.datas[t],
                "motivo": motivo,
                "q_y": posicao.q_y,
                "q_x": posicao.q_x,
                "resultado": resultado,
            }
        )

    def valor(self, posicoes: list[_Posicao], t: int) -> np.ndarray:
        valores = np.zeros(len(self.tickers))
        for posicao in posicoes:
            valores[self.coluna[posicao.par.y]] += (
                posicao.q_y * self.V[t, self.coluna[posicao.par.y]]
            )
            valores[self.coluna[posicao.par.x]] += (
                posicao.q_x * self.V[t, self.coluna[posicao.par.x]]
            )
        return valores


def _pernas_vivas(motor: _Motor, par: Par, t: int) -> bool:
    return (
        t <= motor.ultimo[motor.coluna[par.y]]
        and t <= motor.ultimo[motor.coluna[par.x]]
    )


def _chave_da_formacao(dados: Dados, janela: Janela, p: Parametros) -> tuple:
    return (id(dados.fechamento), janela, p.conjunto, p.com_deslistadas, p.q_do_bh)


class _Simulacao:
    """O estado do dia a dia de `simular`: pares da janela, posições, ordens pendentes e o DARF."""

    def __init__(
        self, dados: Dados, p: Parametros, cache: dict, lista: list[Janela]
    ) -> None:
        self.dados, self.p, self.cache = dados, p, cache
        self.motor = _Motor(dados, p)
        self.datas = self.motor.datas
        n = len(self.datas)
        self.cdi = dados.cdi.to_numpy(float)
        self.inicio, self.t_final = lista[0].inicio, lista[-1].fim
        self.janela_de = {
            t: janela for janela in lista for t in range(janela.inicio, janela.fim + 1)
        }
        lista_de_fins = sorted(fb._fins_de_mes(self.datas))
        self.fins = set(lista_de_fins)
        self.proximo_fim = dict(
            zip(lista_de_fins, [*lista_de_fins[1:], None], strict=True)
        )
        self.a_pagar: dict[int, float] = {}
        self.imposto = np.zeros(n)
        self.retorno, self.patrimonio = np.zeros(n), np.zeros(n)
        self.pesos = np.zeros((n, len(self.motor.tickers)))
        self.resumo_das_janelas: list[dict] = []
        self.quebrados = 0
        self.pat_ontem = p.capital_inicial
        self.posicoes: dict[Par, _Posicao] = {}
        self.pendentes: dict[Par, tuple[str, int]] = {}
        self.livres: list[Par] = []
        self.fora: set[Par] = set()
        self.alocacao = 0.0
        with np.errstate(divide="ignore", invalid="ignore"):
            self.log = np.log(self.motor.V)

    def dia(self, t: int) -> None:
        janela = self.janela_de.get(t)
        self.motor.carteira.caixa *= 1 + self.cdi[t]
        if janela is not None and t == janela.inicio:
            self.abrir_janela(janela)
        self.quebrar_deslistados(t)
        ultimo_da_janela = janela is not None and t == janela.fim
        self.executar_pendentes(t, ultimo_da_janela)
        if ultimo_da_janela:
            for par in list(self.posicoes):
                self.motor.fechar(self.posicoes.pop(par), t, "fim_da_janela")
        else:
            self.sinais(t)
        self.apurar_imposto(t)
        self.marcar(t)

    def abrir_janela(self, janela: Janela) -> None:
        chave = _chave_da_formacao(self.dados, janela, self.p)
        if chave not in self.cache:
            self.cache[chave] = formar(self.dados, janela, self.p)
        formacao = self.cache[chave]
        self.livres = list(formacao.candidatos[: self.p.max_pares])
        self.fora = set()
        self.alocacao = self.pat_ontem / self.p.max_pares
        fim_da_formacao = janela.fim_da_formacao
        self.motor.sigma = fb._volatilidade(
            self.dados.fechamento, fim_da_formacao
        ).to_numpy(float)
        self.motor.volume = fb._liquidez_media(
            self.dados.volume, fim_da_formacao
        ).to_numpy(float)
        self.resumo_das_janelas.append(
            {
                "inicio": self.datas[janela.inicio].date().isoformat(),
                "fim": self.datas[janela.fim].date().isoformat(),
                "testados": formacao.testados,
                "cointegrados": formacao.cointegrados,
                "candidatos": len(formacao.candidatos),
                "pares": [
                    {
                        "y": par.y,
                        "x": par.x,
                        "beta": par.beta,
                        "meia_vida": par.meia_vida,
                        "p_ajustado": par.p_ajustado,
                    }
                    for par in self.livres
                ],
            }
        )

    def quebrar_deslistados(self, t: int) -> None:
        """Par com uma perna sem preço (deslistada ou em OPA) fecha e sai da janela."""
        for par in self.livres:
            if par in self.fora or _pernas_vivas(self.motor, par, t):
                continue
            if par in self.posicoes:
                self.motor.fechar(self.posicoes.pop(par), t, "deslistagem")
            self.pendentes.pop(par, None)
            self.fora.add(par)
            self.quebrados += 1

    def executar(self, par: Par, acao: str, sinal: int, t: int) -> None:
        if acao in (COMPRAR_SPREAD, VENDER_SPREAD):
            lado = 1 if acao == COMPRAR_SPREAD else -1
            aberta = self.motor.abrir(par, lado, self.alocacao, sinal, t)
            if aberta is not None:
                self.posicoes[par] = aberta
            return
        self.motor.fechar(self.posicoes.pop(par), t, acao)
        if acao == STOP:
            self.fora.add(par)

    def executar_pendentes(self, t: int, ultimo_da_janela: bool) -> None:
        """As ordens do sinal de ontem; no último dia da janela não se abre par novo."""
        for par, (acao, sinal) in sorted(
            self.pendentes.items(), key=lambda item: (item[0].y, item[0].x)
        ):
            if acao in (COMPRAR_SPREAD, VENDER_SPREAD) and ultimo_da_janela:
                continue
            self.executar(par, acao, sinal, t)
        self.pendentes = {}

    def sinais(self, t: int) -> None:
        p, motor = self.p, self.motor
        for par in self.livres:
            if par in self.fora:
                continue
            aberta = self.posicoes.get(par)
            z = par.z(
                self.log[t, motor.coluna[par.y]], self.log[t, motor.coluna[par.x]]
            )
            acao = decidir(
                z,
                0 if aberta is None else aberta.lado,
                0 if aberta is None else t - aberta.entrada,
                math.ceil(p.multiplo_da_meia_vida * par.meia_vida),
                p,
            )
            if not acao:
                continue
            if p.executar_no_sinal:
                self.executar(par, acao, t, t)
            else:
                self.pendentes[par] = (acao, t)

    def apurar_imposto(self, t: int) -> None:
        """Paga o DARF que vence hoje e apura o mês no último pregão (vence no fim do mês seguinte)."""
        if t in self.a_pagar:
            devido = self.a_pagar.pop(t)
            self.motor.carteira.caixa -= devido
            self.imposto[t] = devido
        if t in self.fins or t == self.t_final:
            devido = self.motor.carteira.fechar_mes(self.datas[t], self.p.custos)
            vencimento = self.proximo_fim.get(t)
            if devido > 0 and vencimento is not None and vencimento <= self.t_final:
                self.a_pagar[vencimento] = self.a_pagar.get(vencimento, 0.0) + devido

    def marcar(self, t: int) -> None:
        valores = self.motor.valor(list(self.posicoes.values()), t)
        pat_fim = float(self.motor.carteira.caixa + valores.sum())
        self.retorno[t] = pat_fim / self.pat_ontem - 1
        self.patrimonio[t] = pat_fim
        self.pesos[t] = valores / pat_fim
        self.pat_ontem = pat_fim

    def resultado(self) -> Resultado:
        motor = self.motor
        periodo = slice(self.inicio, self.t_final + 1)
        indice = self.datas[periodo]
        anos = max(len(indice) / 252, 1e-9)
        return Resultado(
            retorno=pd.Series(self.retorno[periodo], index=indice, name="retorno"),
            patrimonio=pd.Series(
                self.patrimonio[periodo], index=indice, name="patrimonio"
            ),
            pesos=pd.DataFrame(
                self.pesos[periodo], index=indice, columns=motor.tickers
            ),
            negociado=pd.DataFrame(
                motor.negociado[periodo], index=indice, columns=motor.tickers
            ),
            custos=pd.Series(motor.custos[periodo], index=indice, name="custos"),
            aluguel=pd.Series(motor.aluguel[periodo], index=indice, name="aluguel"),
            imposto=pd.Series(self.imposto[periodo], index=indice, name="imposto"),
            giro=float(
                np.abs(motor.negociado[periodo]).sum()
                / anos
                / self.patrimonio[periodo].mean()
            ),
            janelas=self.resumo_das_janelas,
            operacoes=pd.DataFrame(
                motor.operacoes, columns=list(COLUNAS_DAS_OPERACOES)
            ),
            dias_de_day_trade=len({t for t, _ in motor.compras & motor.vendas}),
            fechadas_no_dia_da_entrada=motor.fechadas_no_dia,
            quebrados_por_deslistagem=self.quebrados,
            parametros=self.p,
        )


def simular(
    dados: Dados, parametros: Parametros, cache: dict | None = None
) -> Resultado:
    """Simula os pares dia a dia (ver as convenções no topo do módulo).

    `cache` guarda as formações entre rodadas com os mesmos `dados` (os vizinhos de z, tamanho e
    custos não mudam a formação).
    """
    fb._conferir_entradas(dados)
    lista = janelas(
        pd.DatetimeIndex(dados.fechamento.index), parametros.meses_de_formacao
    )
    if not lista:
        raise ValueError("dados curtos demais para uma janela de formação e operação")
    simulacao = _Simulacao(dados, parametros, {} if cache is None else cache, lista)
    for t in range(simulacao.inicio, simulacao.t_final + 1):
        simulacao.dia(t)
    return simulacao.resultado()


# --- verificações ------------------------------------------------------------------------------------


def hash_do_resultado(resultado: Resultado) -> str:
    """Impressão digital do retorno e do patrimônio (reexecução idêntica)."""
    bruto = (
        resultado.retorno.round(12).to_numpy().tobytes()
        + resultado.patrimonio.round(6).to_numpy().tobytes()
    )
    return hashlib.sha256(bruto).hexdigest()


def cortar(dados: Dados, corte: pd.Timestamp) -> Dados:
    """As mesmas tabelas como seriam vistas em `corte` (inclusive os setores)."""
    base = fb.cortar(dados, corte)
    setores = dados.setores
    if setores is not None:
        setores = setores[pd.to_datetime(setores["conhecido_em"]) <= corte]
    return Dados(
        **{f.name: getattr(base, f.name) for f in fields(fb.Dados)}, setores=setores
    )


def cortar_o_futuro_nao_muda_o_passado(
    dados: Dados, parametros: Parametros, corte: pd.Timestamp
) -> bool:
    """Rodar só com o que existia em `corte` dá, até a véspera, o mesmo retorno de rodar tudo.

    O próprio dia do corte fica de fora: na série cortada ele é o fim dos dados (zera os pares e
    apura o IR), o que não é olhar o futuro.
    """
    inteiro = simular(dados, parametros)
    cortado = simular(cortar(dados, corte), parametros)
    antes = inteiro.retorno.index < corte
    return bool(
        np.allclose(
            inteiro.retorno[antes].to_numpy(),
            cortado.retorno[cortado.retorno.index < corte].to_numpy(),
            rtol=0,
            atol=1e-12,
        )
    )


def com(parametros: Parametros, **mudancas: object) -> Parametros:
    """Uma cópia dos parâmetros com algumas mudanças (vizinhos do platô, estresse, testes)."""
    return replace(parametros, **mudancas)
