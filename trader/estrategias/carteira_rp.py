"""Carteira multiativo da ficha P0-3 (pré-registro quant v0.1): CDI, NTN-B, BOVA11, ouro e S&P 500.

Convenções fixadas AQUI, antes de qualquer número (seção 10 do pré-registro: mudar depois de ver
um resultado é tentativa nova):

- **Ativos.** Os quatro de risco (`ATIVOS_DE_RISCO`) entram como índices de retorno total em
  reais; o CDI é o caixa e rende o CDI bruto do dia. Os esquemas pesam só os quatro de risco (um
  esquema de risco daria quase tudo ao CDI, que não tem volatilidade); o que não está alocado fica
  em caixa.
- **Decisão e execução.** Sinal no fechamento do último pregão do mês (D), com os `janela` últimos
  retornos até D; ordens executadas no fechamento de D+1 (o pregão seguinte presente nos dados);
  os pesos novos rendem de D+2 em diante. Decisão sem pregão seguinte não gera alvo.
- **Banda.** Em D, se algum ativo está mais de `banda` × alvo longe do alvo, a carteira inteira
  vai ao alvo em D+1; senão nada é negociado. A primeira alocação sempre acontece. Sem dados para
  a janela inteira, tudo fica em caixa.
- **Custos.** Cada ativo negociado paga `custo_de_negociar(valor, "etf")` (B5P211, BOVA11,
  GOLD11, IVVB11) mais o impacto de raiz quadrada Y·σ·√(Q/V)·Q (σ = desvio diário na janela da
  decisão, Q = valor negociado, V = volume financeiro médio diário). Quantidades fracionárias:
  os índices sintéticos não têm cota, então o lote de 100 não se aplica (limitação declarada).
- **Imposto.** IR de 15% sobre o ganho de capital líquido do mês, custo médio por ativo, prejuízo
  compensado (`apurar_ir_mensal`, classe "etf", sem isenção). O DARF do mês M é pago no último
  pregão de M+1, vendendo proporcionalmente se o caixa não cobre; essa venda realiza resultado
  no mês do pagamento. Imposto apurado sem pregão de vencimento nos dados não é pago.
- **Modo "aporte"** (teste do Brasil da ficha): em cada execução entra `aporte_mensal` ×
  patrimônio do dia anterior, usado só para comprar o que mais falta ao alvo (nunca vende); o
  retorno diário é ponderado no tempo, tirando o aporte do dia.
- **Olhar o futuro** (`olhar_o_futuro=True`): a decisão em D usa os retornos de D+1 até a próxima
  decisão, o próprio mês em que os pesos vão valer. Serve só para provar que o motor rende mais
  quando vê o futuro, logo não o vê no modo normal.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, replace

import numpy as np
import pandas as pd

from src.carteiras import dias_de_decisao
from trader.avaliacao import sharpe
from trader.custos_br import PADRAO, CustosBR, apurar_ir_mensal, custo_de_negociar

VERSAO = "0.2"  # 0.2: janela sem variação é erro, não NaN (tentativa 1 real)
ATIVOS_DE_RISCO = ("NTNB", "BOVA11", "OURO", "SP500")
ETF_DE_CADA_ATIVO = {
    "NTNB": "B5P211",
    "BOVA11": "BOVA11",
    "OURO": "GOLD11",
    "SP500": "IVVB11",
}
CLASSE = "etf"
ESQUEMAS = ("risk_parity", "inverso_vol", "min_var", "fixo")
MODOS = ("vender", "aporte")
CANDIDATO = "risk_parity"
JANELA = 252
BANDA = 0.20
TETO = 0.40
APORTE_MENSAL = 0.01
CAPITAL_INICIAL = 100_000.0
SEM_CUSTOS = CustosBR(corretagem_por_ordem=0.0, emolumentos_a_vista=0.0, ir_swing=0.0)
TOLERANCIA = 1e-13
ITERACOES_MAXIMAS = 20_000

__all__ = ["sharpe"]


@dataclass(frozen=True)
class Parametros:
    esquema: str = CANDIDATO
    janela: int = JANELA
    banda: float = BANDA
    teto: float = TETO
    pesos_fixos: dict[str, float] | None = None
    modo: str = "vender"
    aporte_mensal: float = APORTE_MENSAL
    capital_inicial: float = CAPITAL_INICIAL
    custos: CustosBR = PADRAO
    fator_de_impacto: float = 1.0
    olhar_o_futuro: bool = False

    def __post_init__(self) -> None:
        if self.esquema not in ESQUEMAS:
            raise ValueError(
                f"esquema desconhecido: {self.esquema!r}; use um de {ESQUEMAS}"
            )
        if self.modo not in MODOS:
            raise ValueError(f"modo desconhecido: {self.modo!r}; use um de {MODOS}")
        if self.esquema == "fixo":
            _conferir_pesos_fixos(self.pesos_fixos)
        if self.janela < 2 or self.banda < 0 or self.capital_inicial <= 0:
            raise ValueError("janela >= 2, banda >= 0 e capital inicial > 0")

    def especificacao(self) -> dict:
        """Tudo o que define a tentativa, em tipos simples (vai para o registro)."""
        spec = asdict(self)
        spec["custos"] = asdict(self.custos)
        spec["custos"]["a_confirmar"] = list(spec["custos"]["a_confirmar"])
        spec["versao"] = VERSAO
        return spec


@dataclass
class Resultado:
    retorno: pd.Series  # diário, líquido, ponderado no tempo
    patrimonio: pd.Series
    pesos: pd.DataFrame  # no fechamento de cada dia (com a deriva)
    alvos: pd.DataFrame  # nos dias de decisão com execução
    negociado: pd.DataFrame  # reais por ativo e dia (+ compra, - venda)
    custos: pd.Series  # corretagem, bolsa e impacto, por dia
    imposto: pd.Series  # DARF pago, por dia
    aportes: pd.Series
    giro: float  # valor negociado por ano ÷ patrimônio médio
    parametros: Parametros = field(repr=False)


# --- esquemas de peso -------------------------------------------------------------------------------


def _conferir_pesos_fixos(pesos: dict[str, float] | None) -> None:
    if not pesos:
        raise ValueError("o esquema fixo precisa de pesos_fixos")
    estranhos = set(pesos) - set(ATIVOS_DE_RISCO)
    if estranhos or min(pesos.values()) < 0 or sum(pesos.values()) > 1 + 1e-12:
        raise ValueError(
            "pesos_fixos: só ativos de risco, não negativos, somando no máximo 1"
        )


REGUA_60_40 = Parametros(esquema="fixo", pesos_fixos={"BOVA11": 0.6}, banda=0.0)


def pesos_inverso_da_volatilidade(retornos: pd.DataFrame) -> pd.Series:
    """Peso proporcional a 1/desvio-padrão; soma 1."""
    inverso = 1 / retornos.std()
    return inverso / inverso.sum()


def contribuicoes_ao_risco(pesos: pd.Series, cov: pd.DataFrame) -> pd.Series:
    """Fração da variância da carteira que vem de cada ativo (soma 1)."""
    w = pesos.reindex(cov.index).to_numpy(float)
    marginal = cov.to_numpy(float) @ w
    return pd.Series(w * marginal / float(w @ marginal), index=cov.index)


def pesos_risk_parity(retornos: pd.DataFrame) -> pd.Series:
    """Cada ativo contribui com a mesma fração do risco (descida por coordenadas cíclica).

    Resolve min ½xᵀΣx − Σ b·ln x com b = 1/n: a solução satisfaz x_i(Σx)_i = b, e normalizada dá
    contribuições iguais.
    """
    cov = retornos.cov().to_numpy(float)
    n = cov.shape[0]
    orcamento = 1.0 / n
    x = np.full(n, 1.0 / np.sqrt(np.trace(cov) / n))
    for _ in range(ITERACOES_MAXIMAS):
        anterior = x.copy()
        for i in range(n):
            alfa = cov[i, i]
            beta = cov[i] @ x - alfa * x[i]
            x[i] = (-beta + np.sqrt(beta * beta + 4 * alfa * orcamento)) / (2 * alfa)
        if np.max(np.abs(x - anterior)) < TOLERANCIA * np.max(np.abs(x)):
            break
    return pd.Series(x / x.sum(), index=retornos.columns)


def _projetar_no_simplex_com_teto(v: np.ndarray, teto: float) -> np.ndarray:
    """O ponto mais perto de v com soma 1 e 0 <= w <= teto (bissecção no deslocamento)."""
    baixo, alto = float(v.min()) - 1.0, float(v.max())
    for _ in range(200):
        tau = (baixo + alto) / 2
        soma = np.clip(v - tau, 0.0, teto).sum()
        if soma > 1.0:
            baixo = tau
        else:
            alto = tau
    return np.clip(v - (baixo + alto) / 2, 0.0, teto)


def pesos_minima_variancia(retornos: pd.DataFrame, teto: float = TETO) -> pd.Series:
    """Menor variância com soma 1, sem venda a descoberto e com teto por ativo (gradiente projetado)."""
    cov = retornos.cov().to_numpy(float)
    n = cov.shape[0]
    if teto * n < 1 - 1e-12:
        raise ValueError(
            f"teto {teto} impossível para {n} ativos (precisa de teto × n >= 1)"
        )
    passo = 1.0 / float(np.linalg.eigvalsh(cov).max())
    w = _projetar_no_simplex_com_teto(np.full(n, 1.0 / n), teto)
    for _ in range(ITERACOES_MAXIMAS):
        novo = _projetar_no_simplex_com_teto(w - passo * (cov @ w), teto)
        if np.max(np.abs(novo - w)) < TOLERANCIA:
            w = novo
            break
        w = novo
    return pd.Series(w, index=retornos.columns)


def calcular_pesos(
    esquema: str,
    retornos: pd.DataFrame,
    *,
    teto: float = TETO,
    pesos_fixos: dict[str, float] | None = None,
) -> pd.Series:
    """Os pesos-alvo dos ativos de risco para uma janela de retornos (soma <= 1; o resto é caixa)."""
    if esquema in ("risk_parity", "inverso_vol", "min_var"):
        _conferir_janela(retornos)
    if esquema == "risk_parity":
        return pesos_risk_parity(retornos)
    if esquema == "inverso_vol":
        return pesos_inverso_da_volatilidade(retornos)
    if esquema == "min_var":
        return pesos_minima_variancia(retornos, teto)
    if esquema == "fixo":
        _conferir_pesos_fixos(pesos_fixos)
        return (
            pd.Series(pesos_fixos)
            .reindex(retornos.columns, fill_value=0.0)
            .astype(float)
        )
    raise ValueError(f"esquema desconhecido: {esquema!r}; use um de {ESQUEMAS}")


def _conferir_janela(retornos: pd.DataFrame) -> None:
    """Coluna sem variação (preço repetido: dado inconforme) viraria 0/0 nos pesos, em silêncio."""
    desvio = retornos.std()
    paradas = desvio.index[(desvio == 0) | desvio.isna()]
    if len(paradas):
        raise ValueError(
            f"janela sem variação em {paradas[0]}: preço repetido (dado inconforme)"
        )


def fora_da_banda(atual: pd.Series, alvo: pd.Series, banda: float) -> bool:
    """Algum ativo está mais de `banda` × alvo longe do alvo (alvo zero: qualquer posição)."""
    alvo = alvo.reindex(atual.index).fillna(0.0)
    return bool(((atual - alvo).abs() > banda * alvo).any())


# --- motor ------------------------------------------------------------------------------------------


def _conferir_entradas(
    precos: pd.DataFrame, cdi: pd.Series, volumes: pd.Series
) -> None:
    faltando = set(ATIVOS_DE_RISCO) - set(precos.columns)
    if faltando:
        raise ValueError(f"faltam ativos nos preços: {sorted(faltando)}")
    if precos.isna().any().any():
        vazio = precos.index[precos.isna().any(axis=1)][0]
        raise ValueError(f"preço vazio (NaN) em {vazio.date()}")
    if not precos.index.is_monotonic_increasing or precos.index.has_duplicates:
        raise ValueError("as datas dos preços precisam ser crescentes e sem repetição")
    if not cdi.index.equals(precos.index) or cdi.isna().any():
        raise ValueError("o CDI precisa ter exatamente as datas dos preços, sem vazios")
    if volumes.reindex(ATIVOS_DE_RISCO).isna().any() or (volumes <= 0).any():
        raise ValueError("volumes: um valor positivo por ativo de risco")


def _custo_das_ordens(
    delta: np.ndarray, sigma: np.ndarray, volumes: np.ndarray, p: Parametros
) -> np.ndarray:
    """Corretagem e bolsa de cada ordem mais o impacto de raiz quadrada; zero onde não há ordem."""
    custos = np.zeros_like(delta)
    for i, valor in enumerate(np.abs(delta)):
        if valor > 0:
            impacto = (
                p.fator_de_impacto * sigma[i] * np.sqrt(valor / volumes[i]) * valor
            )
            custos[i] = (
                custo_de_negociar(float(valor), CLASSE, custos=p.custos) + impacto
            )
    return custos


def _ordens_para_o_alvo(
    alvo: np.ndarray,
    valores: np.ndarray,
    caixa: float,
    sigma: np.ndarray,
    volumes: np.ndarray,
    p: Parametros,
) -> tuple[np.ndarray, np.ndarray]:
    """Compras e vendas (reais) que levam ao alvo pagando os custos com o próprio patrimônio."""
    total = caixa + valores.sum()
    delta = alvo * total - valores
    custos = _custo_das_ordens(delta, sigma, volumes, p)
    for _ in range(
        2
    ):  # o custo sai do que é alocado; duas passadas bastam para fechar a conta
        delta = alvo * (total - custos.sum()) - valores
        custos = _custo_das_ordens(delta, sigma, volumes, p)
    return _sem_caixa_negativo(delta, custos, caixa, sigma, volumes, p)


def _ordens_so_de_compra(
    alvo: np.ndarray,
    valores: np.ndarray,
    caixa: float,
    sigma: np.ndarray,
    volumes: np.ndarray,
    p: Parametros,
) -> tuple[np.ndarray, np.ndarray]:
    """Modo aporte: todo o caixa compra o que mais falta ao alvo (nunca vende)."""
    if caixa <= 0:
        return np.zeros_like(valores), np.zeros_like(valores)
    falta = np.maximum(alvo * (caixa + valores.sum()) - valores, 0.0)
    proporcao = falta / falta.sum() if falta.sum() > 0 else alvo / alvo.sum()
    delta = caixa * proporcao
    custos = _custo_das_ordens(delta, sigma, volumes, p)
    for _ in range(2):
        delta = max(caixa - custos.sum(), 0.0) * proporcao
        custos = _custo_das_ordens(delta, sigma, volumes, p)
    return _sem_caixa_negativo(delta, custos, caixa, sigma, volumes, p)


def _sem_caixa_negativo(
    delta: np.ndarray,
    custos: np.ndarray,
    caixa: float,
    sigma: np.ndarray,
    volumes: np.ndarray,
    p: Parametros,
) -> tuple[np.ndarray, np.ndarray]:
    """Se as passadas deixaram o caixa negativo por centavos, a maior compra encolhe esse tanto."""
    sobra = caixa - delta.sum() - custos.sum()
    if sobra < 0 and (delta > 0).any():
        delta[int(np.argmax(delta))] += sobra  # sobra é negativa
        custos = _custo_das_ordens(delta, sigma, volumes, p)
    return delta, custos


class _Carteira:
    """Estado da carteira ao longo da simulação (quantidades, caixa, custo médio e IR)."""

    def __init__(self, capital: float, n_ativos: int) -> None:
        self.q = np.zeros(n_ativos)
        self.caixa = capital
        self.base = np.zeros(n_ativos)  # custo de aquisição que ainda está na carteira
        self.vendas_do_mes = 0.0
        self.resultado_do_mes = 0.0
        self.meses: list[tuple[pd.Timestamp, float, float]] = []

    def valores(self, precos_do_dia: np.ndarray) -> np.ndarray:
        return self.q * precos_do_dia

    def patrimonio(self, precos_do_dia: np.ndarray) -> float:
        return float(self.caixa + self.valores(precos_do_dia).sum())

    def executar(
        self, delta: np.ndarray, custos: np.ndarray, precos_do_dia: np.ndarray
    ) -> None:
        for i, valor in enumerate(delta):
            if valor > 0:
                self.q[i] += valor / precos_do_dia[i]
                self.base[i] += valor + custos[i]
            elif valor < 0:
                vendido = -valor
                fracao = min(1.0, vendido / (self.q[i] * precos_do_dia[i]))
                self.resultado_do_mes += vendido - custos[i] - fracao * self.base[i]
                self.vendas_do_mes += vendido
                self.base[i] -= fracao * self.base[i]
                self.q[i] -= vendido / precos_do_dia[i]
        self.caixa -= delta.sum() + custos.sum()

    def fechar_mes(self, dia: pd.Timestamp, custos: CustosBR) -> float:
        """Apura o IR do mês que termina em `dia` (só com o passado) e zera o mês."""
        self.meses.append(
            (
                dia.to_period("M").to_timestamp(),
                self.vendas_do_mes,
                self.resultado_do_mes,
            )
        )
        self.vendas_do_mes = self.resultado_do_mes = 0.0
        if not any(v > 0 for _, v, _ in self.meses):
            return 0.0
        datas = pd.DatetimeIndex([m for m, _, _ in self.meses])
        vendas = pd.Series([v for _, v, _ in self.meses], index=datas)
        resultado = pd.Series([r for _, _, r in self.meses], index=datas)
        tabela = apurar_ir_mensal(vendas, resultado, CLASSE, custos=custos)
        return float(tabela["imposto"].iloc[-1])


def _janela_da_decisao(
    retornos: np.ndarray, t: int, proxima_decisao: int | None, p: Parametros
) -> np.ndarray | None:
    if p.olhar_o_futuro and proxima_decisao is not None and proxima_decisao - t >= 2:
        return retornos[t + 1 : proxima_decisao + 1]
    if t < p.janela:
        return None
    return retornos[t - p.janela + 1 : t + 1]


def simular(
    precos: pd.DataFrame, cdi: pd.Series, volumes: pd.Series, parametros: Parametros
) -> Resultado:
    """Simula a carteira dia a dia (ver as convenções no topo do módulo)."""
    _conferir_entradas(precos, cdi, volumes)
    p = parametros
    ativos = list(ATIVOS_DE_RISCO)
    datas = precos.index
    P = precos[ativos].to_numpy(float)
    n, k = P.shape
    R = np.vstack([np.zeros((1, k)), P[1:] / P[:-1] - 1])
    cdi_v = cdi.to_numpy(float)
    vol_v = volumes.reindex(ativos).to_numpy(float)
    decisoes = [int(i) for i in datas.get_indexer(dias_de_decisao(datas))]
    proxima = {
        d: (decisoes[j + 1] if j + 1 < len(decisoes) else None)
        for j, d in enumerate(decisoes)
    }
    e_decisao = set(decisoes)

    carteira = _Carteira(p.capital_inicial, k)
    retorno, patrimonio = np.zeros(n), np.zeros(n)
    custos, imposto, aportes = np.zeros(n), np.zeros(n), np.zeros(n)
    pesos, negociado = np.zeros((n, k)), np.zeros((n, k))
    alvos: dict[pd.Timestamp, np.ndarray] = {}
    pendente: tuple[np.ndarray, np.ndarray] | None = None
    a_pagar: dict[int, float] = {}
    pat_ontem = p.capital_inicial

    for t in range(n):
        if t > 0:
            carteira.caixa *= 1 + cdi_v[t]
        if pendente is not None:
            alvo, sigma = pendente
            pendente = None
            valores = carteira.valores(P[t])
            if p.modo == "aporte":
                aportes[t] = p.aporte_mensal * pat_ontem
                carteira.caixa += aportes[t]
                delta, custo = _ordens_so_de_compra(
                    alvo, valores, carteira.caixa, sigma, vol_v, p
                )
            else:
                primeira = not carteira.q.any()
                atual = pd.Series(valores / carteira.patrimonio(P[t]), index=ativos)
                if primeira or fora_da_banda(
                    atual, pd.Series(alvo, index=ativos), p.banda
                ):
                    delta, custo = _ordens_para_o_alvo(
                        alvo, valores, carteira.caixa, sigma, vol_v, p
                    )
                else:
                    delta, custo = np.zeros(k), np.zeros(k)
            carteira.executar(delta, custo, P[t])
            negociado[t] += delta
            custos[t] += custo.sum()
        if t in a_pagar:
            devido = a_pagar.pop(t)
            delta, custo = _vender_para_pagar(carteira, devido, P[t], vol_v, p)
            carteira.executar(delta, custo, P[t])
            negociado[t] += delta
            custos[t] += custo.sum()
            carteira.caixa -= devido
            imposto[t] = devido
        if t in e_decisao:
            if t + 1 < n:
                janela = _janela_da_decisao(R, t, proxima[t], p)
                if janela is not None:
                    w = calcular_pesos(
                        p.esquema,
                        pd.DataFrame(janela, columns=ativos),
                        teto=p.teto,
                        pesos_fixos=p.pesos_fixos,
                    )
                    alvo = w.reindex(ativos).to_numpy(float)
                    if not np.isfinite(alvo).all():
                        raise ValueError(f"pesos-alvo inválidos em {datas[t].date()}")
                    alvos[datas[t]] = alvo
                    pendente = (alvo, janela.std(axis=0, ddof=1))
            devido = carteira.fechar_mes(datas[t], p.custos)
            if devido > 0 and proxima[t] is not None:
                a_pagar[proxima[t]] = a_pagar.get(proxima[t], 0.0) + devido
        pat_fim = carteira.patrimonio(P[t])
        retorno[t] = (pat_fim - aportes[t]) / pat_ontem - 1 if t > 0 else 0.0
        patrimonio[t] = pat_fim
        pesos[t] = carteira.valores(P[t]) / pat_fim
        pat_ontem = pat_fim

    anos = max(n / 252, 1e-9)
    giro = float(np.abs(negociado).sum() / anos / patrimonio.mean())
    return Resultado(
        retorno=pd.Series(retorno, index=datas, name="retorno"),
        patrimonio=pd.Series(patrimonio, index=datas, name="patrimonio"),
        pesos=pd.DataFrame(pesos, index=datas, columns=ativos),
        alvos=pd.DataFrame.from_dict(alvos, orient="index", columns=ativos),
        negociado=pd.DataFrame(negociado, index=datas, columns=ativos),
        custos=pd.Series(custos, index=datas, name="custos"),
        imposto=pd.Series(imposto, index=datas, name="imposto"),
        aportes=pd.Series(aportes, index=datas, name="aportes"),
        giro=giro,
        parametros=p,
    )


def _vender_para_pagar(
    carteira: _Carteira,
    devido: float,
    precos_do_dia: np.ndarray,
    volumes: np.ndarray,
    p: Parametros,
) -> tuple[np.ndarray, np.ndarray]:
    """Vende proporcionalmente o que falta no caixa para o DARF (duas passadas pelos custos)."""
    k = len(carteira.q)
    falta = devido - carteira.caixa
    valores = carteira.valores(precos_do_dia)
    if falta <= 0 or valores.sum() <= 0:
        return np.zeros(k), np.zeros(k)
    sigma = np.zeros(k)  # a venda do DARF é pequena: só corretagem e bolsa, sem impacto
    proporcao = valores / valores.sum()
    delta = -np.minimum(falta * proporcao, valores)
    custos = _custo_das_ordens(delta, sigma, volumes, p)
    for _ in range(2):
        delta = -np.minimum((falta + custos.sum()) * proporcao, valores)
        custos = _custo_das_ordens(delta, sigma, volumes, p)
    return delta, custos


# --- verificações ------------------------------------------------------------------------------------


def hash_do_resultado(resultado: Resultado) -> str:
    """Impressão digital do retorno e do patrimônio (reexecução idêntica)."""
    bruto = (
        resultado.retorno.round(12).to_numpy().tobytes()
        + resultado.patrimonio.round(6).to_numpy().tobytes()
    )
    return hashlib.sha256(bruto).hexdigest()


def cortar_o_futuro_nao_muda_o_passado(
    precos: pd.DataFrame,
    cdi: pd.Series,
    volumes: pd.Series,
    parametros: Parametros,
    corte: pd.Timestamp,
) -> bool:
    """Rodar só até `corte` dá, até a véspera do corte, o mesmo retorno de rodar tudo.

    O próprio dia do corte fica de fora da comparação: na série cortada ele é o último dia do
    mês (apura o IR e paga o DARF vencido), o que não é olhar o futuro, é o fim dos dados.
    """
    inteiro = simular(precos, cdi, volumes, parametros)
    cortado = simular(precos.loc[:corte], cdi.loc[:corte], volumes, parametros)
    ate_a_vespera = inteiro.retorno.index < corte
    return bool(
        np.allclose(
            inteiro.retorno.loc[ate_a_vespera].to_numpy(),
            cortado.retorno.loc[cortado.retorno.index < corte].to_numpy(),
            rtol=0,
            atol=1e-12,
        )
    )


def p_valor_do_acaso(
    pesos: pd.DataFrame,
    retornos: pd.DataFrame,
    cdi: pd.Series,
    custo_por_lado: float,
    sorteios: int = 1000,
    semente: int = 42,
) -> dict:
    """A6: desloca os pesos diários no tempo (todos juntos) e refaz a carteira com os mesmos custos.

    Conta simples: o peso do fechamento de ontem rende o retorno de hoje, o que não está alocado
    rende o CDI e cada real negociado paga `custo_por_lado`. Sharpe do excesso sobre o CDI.
    """
    ativos = list(pesos.columns)
    w = pesos.fillna(0.0).to_numpy(float)
    r = retornos[ativos].reindex(pesos.index).fillna(0.0).to_numpy(float)
    c = cdi.reindex(pesos.index).fillna(0.0).to_numpy(float)

    def sharpe_de(pesos_diarios: np.ndarray) -> float:
        ontem = np.vstack([np.zeros((1, len(ativos))), pesos_diarios[:-1]])
        giro = np.abs(np.diff(pesos_diarios, axis=0, prepend=0.0)).sum(axis=1)
        diario = (
            (ontem * r).sum(axis=1)
            + (1 - ontem.sum(axis=1)) * c
            - giro * custo_por_lado
        )
        excesso = diario - c
        desvio = excesso.std(ddof=1)
        return float(excesso.mean() / desvio * np.sqrt(252)) if desvio > 0 else np.nan

    real = sharpe_de(w)
    n = len(w)
    folga = max(21, n // 10)
    deslocamentos = np.random.default_rng(semente).integers(
        folga, n - folga, size=sorteios
    )
    sorteados = np.array([sharpe_de(np.roll(w, int(d), axis=0)) for d in deslocamentos])
    sorteados = sorteados[~np.isnan(sorteados)]
    return {
        "sharpe_real": real,
        "percentil_95": float(np.percentile(sorteados, 95)),
        "p_valor": float((1 + (sorteados >= real).sum()) / (1 + len(sorteados))),
    }


def com(parametros: Parametros, **mudancas: object) -> Parametros:
    """Uma cópia dos parâmetros com algumas mudanças (vizinhos do platô, estresse, bruto)."""
    return replace(parametros, **mudancas)
