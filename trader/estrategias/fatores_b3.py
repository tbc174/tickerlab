"""Fatores na B3 (ficha F-B3 do pré-registro quant v0.1): valor, qualidade, momento e baixa vol.

Convenções fixadas AQUI, antes de qualquer número (seção 10 do pré-registro: mudar depois de
ver um resultado é tentativa nova):

- **Entradas** (`Dados`), em tabelas simples: `fechamento` e `abertura` ajustados por
  desdobramentos e proventos (uma coluna por ticker, NaN fora do período em que a ação existiu),
  `volume` financeiro diário em reais, `cadastro` por ticker (CNPJ, classe ON/PN/UNT, primeiro e
  último pregão), `fundamentos` em formato longo e ponto no tempo (CNPJ, demonstração, conta,
  início e fim do período, valor, `divulgado_em`, `ate`), `acoes` em circulação por CNPJ com a
  data em que a quantidade ficou pública, o `cdi` diário e, se houver, as recuperações judiciais.
- **Ponto no tempo.** Em D só entra balanço com `divulgado_em` < D (o que saiu em D entra em
  D+1) e ainda vigente (`ate` vazio ou > D). Os 12 meses são DFP do ano anterior + acumulado do
  ano − acumulado do ano anterior até o mesmo mês; sem as três peças, o fator fica vazio.
- **Universo** (seção 8): ação ON, PN ou UNT listada em D com 12 meses de pregão, volume
  financeiro médio dos 60 pregões anteriores (sem o próprio D; dia sem negócio conta zero) de pelo
  menos R$ 5 milhões, balanço divulgado nos 12 meses anteriores e sem recuperação judicial em
  curso; uma classe por empresa (a mais líquida). Deslistadas entram enquanto existiram.
- **Fatores em D** (fechamento): valor = EBIT 12m ÷ valor da firma (ações × preço + empréstimos
  − caixa e aplicações); qualidade = lucro 12m ÷ patrimônio líquido; momento = preço 21 pregões
  atrás ÷ preço 252 pregões atrás − 1; baixa vol = −desvio dos retornos dos 252 pregões até D.
  Bancos não têm EBIT nem empréstimos no plano industrial, então ficam sem valor (limitação
  declarada). Nota = média simples dos escores z dos fatores disponíveis, com pelo menos 3 dos 4.
- **Carteira.** Decisão no fechamento do primeiro pregão do mês; as 20% melhores notas em pesos
  iguais, só comprado; ordens no leilão de abertura do pregão seguinte, em ações inteiras (lote
  padrão mais o fracionário). Banda: se alguma posição está mais de `banda` × alvo longe do
  alvo, a carteira inteira vai ao alvo; senão nada é negociado. Sem alvo (universo vazio ou sem
  notas) a carteira fica como está. Ação deslistada é vendida no primeiro dia sem preço, pelo
  último preço conhecido, só com corretagem e bolsa (limitação: a liquidação real é a da OPA).
- **Custos.** Corretagem e emolumentos de `custo_de_negociar(valor, "acoes")` mais o impacto
  Y·σ·√(Q/V)·Q (σ = desvio diário dos 252 pregões, V = volume médio dos 60 pregões). IR de 15%
  sobre o ganho líquido do mês com isenção de R$ 20 mil de vendas (`apurar_ir_mensal`, classe
  "acoes"); o DARF do mês M é pago no último pregão de M+1, vendendo proporcionalmente se o
  caixa não cobre. O caixa rende o CDI do dia.
- **Olhar o futuro** (`olhar_o_futuro=True`): o balanço vale desde a data do próprio balanço, não
  da divulgação. Serve para o teste (c) do Brasil: o motor rende mais quando vê o futuro, logo
  não o vê no modo normal. `com_deslistadas=False` é o teste (a): só quem existe no fim dos
  dados, o viés de sobrevivência medido de propósito.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field, replace

import numpy as np
import pandas as pd

from trader import criterio_quant
from trader.custos_br import (
    PADRAO,
    CustosBR,
    apurar_ir_mensal,
    arredondar_lote,
    custo_de_negociar,
)
from trader.estrategias.carteira_rp import fora_da_banda, p_valor_do_acaso

__all__ = ["p_valor_do_acaso"]

VERSAO = "0.1"
CLASSE = "acoes"
CLASSES_DE_ACAO = ("ON", "PN", "UNT")
FATORES = ("valor", "qualidade", "momento", "baixa_vol")
FATORES_MINIMOS = 3
QUINTIL = 0.20
BANDA = 0.20
CAPITAL_INICIAL = 100_000.0
JANELA_DO_MOMENTO = 252
PULAR_NO_MOMENTO = 21
JANELA_DA_VOL = 252
PISO_DE_LIQUIDEZ = criterio_quant.PISO_DE_LIQUIDEZ_EM_REAIS
PREGOES_DA_LIQUIDEZ = criterio_quant.PREGOES_DA_LIQUIDEZ
MESES_MINIMOS_DE_PREGAO = criterio_quant.MESES_MINIMOS_DE_PREGAO
MESES_DO_BALANCO = 12
CONTA_EBIT = "3.05"
CONTA_LUCRO = "3.11"
CONTA_PL = "2.03"
CONTAS_DA_DIVIDA = ("2.01.04", "2.02.01")
CONTAS_DO_CAIXA = ("1.01.01", "1.01.02")
CONTAS_USADAS = (CONTA_EBIT, CONTA_LUCRO, CONTA_PL, *CONTAS_DA_DIVIDA, *CONTAS_DO_CAIXA)
COLUNAS_DOS_FUNDAMENTOS = (
    "cnpj",
    "demonstracao",
    "conta",
    "inicio",
    "fim",
    "valor",
    "divulgado_em",
    "ate",
)
COLUNAS_DAS_ACOES = ("cnpj", "quantidade", "disponivel_em")
COLUNAS_DO_CADASTRO = ("cnpj", "classe", "inicio_negociacao", "fim_negociacao")
SEM_CUSTOS = CustosBR(corretagem_por_ordem=0.0, emolumentos_a_vista=0.0, ir_swing=0.0)
AVISO_DE_SOBREVIVENCIA = (
    "Viés de sobrevivência: a base não tem nenhuma ação deslistada no período, então o resultado "
    "vale só como ilustração e a estratégia não pode receber dinheiro (pré-registro v0.1, seção 2)."
)


@dataclass
class Dados:
    """As tabelas da ficha (ver o topo do módulo)."""

    fechamento: pd.DataFrame
    abertura: pd.DataFrame
    volume: pd.DataFrame
    cadastro: pd.DataFrame
    fundamentos: pd.DataFrame
    acoes: pd.DataFrame
    cdi: pd.Series
    recuperacao_judicial: pd.DataFrame | None = None
    ibovespa: pd.Series | None = (
        None  # retorno diário da régua (total líquido), se houver
    )


@dataclass(frozen=True)
class Parametros:
    quintil: float = QUINTIL
    banda: float = BANDA
    capital_inicial: float = CAPITAL_INICIAL
    com_deslistadas: bool = True
    custos: CustosBR = PADRAO
    fator_de_impacto: float = 1.0
    olhar_o_futuro: bool = False

    def __post_init__(self) -> None:
        if not 0 < self.quintil <= 1 or self.banda < 0 or self.capital_inicial <= 0:
            raise ValueError("quintil em (0, 1], banda >= 0 e capital inicial > 0")

    def especificacao(self) -> dict:
        """Tudo o que define a tentativa, em tipos simples (vai para o registro)."""
        spec = asdict(self)
        spec["custos"] = asdict(self.custos)
        spec["custos"]["a_confirmar"] = list(spec["custos"]["a_confirmar"])
        spec["versao"] = VERSAO
        return spec


@dataclass
class Resultado:
    retorno: pd.Series  # diário, líquido
    patrimonio: pd.Series
    pesos: pd.DataFrame  # no fechamento de cada dia (com a deriva)
    alvos: dict[pd.Timestamp, pd.Series]  # nos dias de decisão com alvo
    negociado: pd.DataFrame  # reais por ticker e dia (+ compra, − venda)
    custos: pd.Series  # corretagem, bolsa e impacto, por dia
    imposto: pd.Series  # DARF pago, por dia
    giro: float  # valor negociado por ano ÷ patrimônio médio
    parametros: Parametros = field(repr=False)


@dataclass(frozen=True)
class Conformidade:
    """O que a conferência de sobrevivência achou (vai escrito no relatório)."""

    deslistadas: int
    total: int
    vies: bool
    aviso: str


# --- ponto no tempo -----------------------------------------------------------------------------------


def vigentes_em(
    base: pd.DataFrame, dia: pd.Timestamp, *, pela_data_do_balanco: bool = False
) -> pd.DataFrame:
    """As linhas que podiam ser lidas em D: divulgadas antes de D e ainda não substituídas."""
    disponivel = pd.to_datetime(base["fim" if pela_data_do_balanco else "divulgado_em"])
    ate = (
        pd.to_datetime(base["ate"])
        if "ate" in base
        else pd.Series(pd.NaT, index=base.index)
    )
    return base[(disponivel < dia) & (ate.isna() | (ate > dia))]


def ultimos_12_meses(base: pd.DataFrame, conta: str) -> pd.Series:
    """Valor da conta de resultado nos últimos 12 meses, por CNPJ (NaN sem as três peças).

    Só os períodos acumulados desde 1º de janeiro contam: DFP (o ano inteiro) ou o acumulado do
    ITR; trimestre isolado é ignorado.
    """
    inicio = pd.to_datetime(base["inicio"])
    acumulados = base[(base["conta"] == conta) & inicio.dt.is_year_start.fillna(False)]
    acumulados = acumulados.sort_values(["cnpj", "fim"], kind="stable").drop_duplicates(
        ["cnpj", "inicio", "fim"], keep="last"
    )
    resultado: dict[str, float] = {}
    for cnpj, grupo in acumulados.groupby("cnpj", sort=True):
        por_fim = grupo.set_index(pd.to_datetime(grupo["fim"]))["valor"].astype(float)
        ultimo = pd.Timestamp(por_fim.index.max())
        if ultimo.is_year_end:
            resultado[str(cnpj)] = float(por_fim[ultimo])
            continue
        dfp = pd.Timestamp(year=ultimo.year - 1, month=12, day=31)
        mesmo_mes = ultimo - pd.DateOffset(years=1)
        if dfp in por_fim.index and mesmo_mes in por_fim.index:
            resultado[str(cnpj)] = float(
                por_fim[ultimo] + por_fim[dfp] - por_fim[mesmo_mes]
            )
        else:
            resultado[str(cnpj)] = math.nan
    return pd.Series(resultado, dtype=float)


def valor_pontual(base: pd.DataFrame, conta: str) -> pd.Series:
    """Saldo mais recente de uma conta de balanço, por CNPJ."""
    linhas = base[base["conta"] == conta].sort_values(["cnpj", "fim"], kind="stable")
    return linhas.groupby("cnpj", sort=True)["valor"].last().astype(float)


def _quantidade_de_acoes(acoes: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    publicas = acoes[pd.to_datetime(acoes["disponivel_em"]) < dia]
    publicas = publicas.sort_values(["cnpj", "disponivel_em"], kind="stable")
    return publicas.groupby("cnpj", sort=True)["quantidade"].last().astype(float)


# --- universo e fatores ------------------------------------------------------------------------------


def _posicao(datas: pd.DatetimeIndex, dia: pd.Timestamp) -> int:
    posicao = datas.get_loc(dia)
    if not isinstance(posicao, int):
        raise TypeError(f"{dia.date()} não é um pregão único dos dados")
    return posicao


def _liquidez_media(volume: pd.DataFrame, posicao: int) -> pd.Series:
    """Volume financeiro médio dos `PREGOES_DA_LIQUIDEZ` pregões anteriores (sem o próprio dia)."""
    janela = volume.iloc[max(posicao - PREGOES_DA_LIQUIDEZ, 0) : posicao]
    return janela.fillna(0.0).sum() / PREGOES_DA_LIQUIDEZ


def _volatilidade(fechamento: pd.DataFrame, posicao: int) -> pd.Series:
    if posicao < JANELA_DA_VOL:
        return pd.Series(math.nan, index=fechamento.columns, dtype=float)
    janela = fechamento.iloc[posicao - JANELA_DA_VOL : posicao + 1]
    return janela.pct_change(fill_method=None).iloc[1:].std()


def _em_recuperacao_judicial(dados: Dados, dia: pd.Timestamp) -> set[str]:
    tabela = dados.recuperacao_judicial
    if tabela is None or tabela.empty:
        return set()
    inicio = pd.to_datetime(tabela["inicio"])
    fim = pd.to_datetime(tabela["fim"])
    em_curso = tabela[(inicio <= dia) & (fim.isna() | (fim > dia))]
    return set(em_curso["cnpj"].astype(str))


def _com_balanco_recente(fundamentos: pd.DataFrame, dia: pd.Timestamp) -> set[str]:
    divulgado = pd.to_datetime(fundamentos["divulgado_em"])
    recente = fundamentos[
        (divulgado < dia) & (divulgado >= dia - pd.DateOffset(months=MESES_DO_BALANCO))
    ]
    return set(recente["cnpj"].astype(str))


def _sobreviventes(dados: Dados) -> pd.Series:
    """Quem ainda existe no último dia dos dados (olha o futuro de propósito: teste (a))."""
    fim = pd.to_datetime(dados.cadastro["fim_negociacao"]).reindex(
        dados.fechamento.columns
    )
    ultimo_dia = dados.fechamento.index[-1]
    ultimo_preco = pd.Series(
        {t: dados.fechamento[t].last_valid_index() for t in dados.fechamento.columns}
    )
    return fim.isna() & (pd.to_datetime(ultimo_preco) == ultimo_dia)


def universo_em(dia: pd.Timestamp, dados: Dados, parametros: Parametros) -> list[str]:
    """Os tickers elegíveis em D pela seção 8 do pré-registro (uma classe por empresa)."""
    tickers = dados.fechamento.columns
    cadastro = dados.cadastro.reindex(tickers)
    posicao = _posicao(pd.DatetimeIndex(dados.fechamento.index), dia)
    inicio = pd.to_datetime(cadastro["inicio_negociacao"])
    fim = pd.to_datetime(cadastro["fim_negociacao"])
    cnpj = cadastro["cnpj"].astype(str)
    liquidez = _liquidez_media(dados.volume, posicao)
    elegivel = (
        dados.fechamento.loc[dia].notna()
        & (inicio <= dia)
        & (fim.isna() | (fim >= dia))
        & cadastro["classe"].isin(CLASSES_DE_ACAO)
        & (inicio <= dia - pd.DateOffset(months=MESES_MINIMOS_DE_PREGAO))
        & (liquidez >= PISO_DE_LIQUIDEZ)
        & ~cnpj.isin(_em_recuperacao_judicial(dados, dia))
        & cnpj.isin(_com_balanco_recente(dados.fundamentos, dia))
    )
    if not parametros.com_deslistadas:
        elegivel &= _sobreviventes(dados)
    candidatas = pd.DataFrame({"cnpj": cnpj, "liquidez": liquidez})[elegivel.to_numpy()]
    candidatas = candidatas.sort_values("liquidez", ascending=False, kind="stable")
    return sorted(candidatas.drop_duplicates("cnpj", keep="first").index.astype(str))


def fatores_em(
    dia: pd.Timestamp, dados: Dados, tickers: list[str], *, olhar_o_futuro: bool = False
) -> pd.DataFrame:
    """Os quatro fatores de cada ticker no fechamento de D (ver o topo do módulo)."""
    vigentes = vigentes_em(dados.fundamentos, dia, pela_data_do_balanco=olhar_o_futuro)
    cnpjs = dados.cadastro["cnpj"].reindex(tickers).astype(str)
    por_cnpj = pd.Index(cnpjs.to_numpy())

    def da_empresa(serie: pd.Series) -> np.ndarray:
        return serie.reindex(por_cnpj).to_numpy(float)

    def soma(contas: tuple[str, ...]) -> np.ndarray:
        return np.nansum(
            [
                da_empresa(valor_pontual(vigentes, c).reindex(por_cnpj).fillna(0.0))
                for c in contas
            ],
            axis=0,
        )

    preco = dados.fechamento.loc[dia, tickers].to_numpy(float)
    quantidade = da_empresa(_quantidade_de_acoes(dados.acoes, dia))
    valor_da_firma = quantidade * preco + soma(CONTAS_DA_DIVIDA) - soma(CONTAS_DO_CAIXA)
    patrimonio = da_empresa(valor_pontual(vigentes, CONTA_PL))
    with np.errstate(divide="ignore", invalid="ignore"):
        valor = np.where(
            valor_da_firma > 0,
            da_empresa(ultimos_12_meses(vigentes, CONTA_EBIT)) / valor_da_firma,
            np.nan,
        )
        qualidade = np.where(
            patrimonio > 0,
            da_empresa(ultimos_12_meses(vigentes, CONTA_LUCRO)) / patrimonio,
            np.nan,
        )
    posicao = _posicao(pd.DatetimeIndex(dados.fechamento.index), dia)
    if posicao >= JANELA_DO_MOMENTO:
        recente = dados.fechamento.iloc[posicao - PULAR_NO_MOMENTO][tickers].to_numpy(
            float
        )
        antigo = dados.fechamento.iloc[posicao - JANELA_DO_MOMENTO][tickers].to_numpy(
            float
        )
        momento = recente / antigo - 1
    else:
        momento = np.full(len(tickers), np.nan)
    baixa_vol = -_volatilidade(dados.fechamento[tickers], posicao).to_numpy(float)
    return pd.DataFrame(
        {
            "valor": valor,
            "qualidade": qualidade,
            "momento": momento,
            "baixa_vol": baixa_vol,
        },
        index=pd.Index(tickers),
    )


def notas(fatores: pd.DataFrame) -> pd.Series:
    """Média simples dos escores z dos fatores disponíveis; vazia com menos de 3 dos 4."""
    z = (fatores - fatores.mean()) / fatores.std()
    suficientes = z.notna().sum(axis=1) >= FATORES_MINIMOS
    return z.mean(axis=1).where(suficientes)


def carteira_alvo(notas: pd.Series, quintil: float = QUINTIL) -> pd.Series:
    """As `quintil` melhores notas (arredondando para cima) em pesos iguais."""
    validas = notas.dropna()
    validas = validas.loc[sorted(validas.index)].sort_values(
        ascending=False, kind="stable"
    )
    quantas = math.ceil(len(validas) * quintil)
    if quantas == 0:
        return pd.Series(dtype=float)
    return pd.Series(1.0 / quantas, index=validas.index[:quantas])


def primeiros_pregoes_do_mes(datas: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return datas[~datas.to_period("M").duplicated()]


# --- motor ------------------------------------------------------------------------------------------


def _conferir_entradas(dados: Dados) -> None:
    datas = dados.fechamento.index
    if not datas.is_monotonic_increasing or datas.has_duplicates:
        raise ValueError("as datas dos preços precisam ser crescentes e sem repetição")
    for nome in ("abertura", "volume"):
        tabela = getattr(dados, nome)
        if not tabela.index.equals(datas) or not tabela.columns.equals(
            dados.fechamento.columns
        ):
            raise ValueError(f"{nome}: precisa ter as datas e os tickers do fechamento")
    if not dados.cdi.index.equals(datas) or dados.cdi.isna().any():
        raise ValueError("o CDI precisa ter exatamente as datas dos preços, sem vazios")
    sem_cadastro = set(dados.fechamento.columns) - set(dados.cadastro.index)
    if sem_cadastro:
        raise ValueError(f"tickers sem cadastro: {sorted(sem_cadastro)[:5]}")
    for nome, colunas in (
        ("cadastro", COLUNAS_DO_CADASTRO),
        ("fundamentos", COLUNAS_DOS_FUNDAMENTOS),
        ("acoes", COLUNAS_DAS_ACOES),
    ):
        faltam = set(colunas) - set(getattr(dados, nome).columns)
        if faltam:
            raise ValueError(f"{nome}: faltam as colunas {sorted(faltam)}")


def _custo_das_ordens(
    delta: np.ndarray, sigma: np.ndarray, volumes: np.ndarray, p: Parametros
) -> np.ndarray:
    """Corretagem e bolsa de cada ordem mais o impacto de raiz quadrada; zero onde não há ordem.

    Sem volume conhecido, Q/V vale 1 (o pior caso da fórmula).
    """
    custos = np.zeros_like(delta)
    for i, valor in enumerate(np.abs(delta)):
        if valor > 0:
            v = volumes[i] if volumes[i] > 0 else valor
            desvio = sigma[i] if np.isfinite(sigma[i]) else 0.0
            impacto = p.fator_de_impacto * desvio * np.sqrt(valor / v) * valor
            custos[i] = (
                custo_de_negociar(float(valor), CLASSE, custos=p.custos) + impacto
            )
    return custos


def _ordens_para_o_alvo(
    alvo: np.ndarray,
    q: np.ndarray,
    caixa: float,
    precos: np.ndarray,
    sigma: np.ndarray,
    volumes: np.ndarray,
    p: Parametros,
) -> tuple[np.ndarray, np.ndarray]:
    """Compras e vendas (ações inteiras) que levam ao alvo pagando os custos com o patrimônio."""
    valores = np.nan_to_num(q * precos)
    total = caixa + valores.sum()
    custos = np.zeros_like(q)
    delta_q = np.zeros_like(q)
    for _ in range(3):  # o custo sai do que é alocado; três passadas fecham a conta
        orcamento = total - custos.sum()
        q_alvo = np.array(
            [
                arredondar_lote(alvo[i] * orcamento / precos[i], fracionario=True)
                if alvo[i] > 0 and precos[i] > 0
                else 0
                for i in range(len(q))
            ],
            dtype=float,
        )
        delta_q = q_alvo - q
        custos = _custo_das_ordens(delta_q * precos, sigma, volumes, p)
    while (
        caixa - np.nansum(delta_q * precos) - custos.sum() < 0 and (delta_q > 0).any()
    ):
        delta_q[int(np.argmax(delta_q * np.nan_to_num(precos)))] -= (
            1  # uma ação a menos na maior compra
        )
        custos = _custo_das_ordens(delta_q * precos, sigma, volumes, p)
    return delta_q, custos


def _vender_para_pagar(
    carteira: _Carteira, devido: float, precos: np.ndarray, p: Parametros
) -> tuple[np.ndarray, np.ndarray]:
    """Vende proporcionalmente (ações inteiras) o que falta no caixa para o DARF."""
    k = len(carteira.q)
    falta = devido - carteira.caixa
    valores = np.nan_to_num(carteira.valores(precos))
    if falta <= 0 or valores.sum() <= 0:
        return np.zeros(k), np.zeros(k)
    sem_impacto = np.zeros(k)  # a venda do DARF é pequena: só corretagem e bolsa
    proporcao = valores / valores.sum()
    precos_validos = np.where(np.nan_to_num(precos) > 0, precos, np.inf)

    def ordens(a_levantar: float) -> np.ndarray:
        return -np.minimum(np.ceil(a_levantar * proporcao / precos_validos), carteira.q)

    delta_q = ordens(falta)
    custos = _custo_das_ordens(delta_q * precos, sem_impacto, sem_impacto, p)
    for _ in range(2):
        delta_q = ordens(falta + custos.sum())
        custos = _custo_das_ordens(delta_q * precos, sem_impacto, sem_impacto, p)
    return delta_q, custos


class _Carteira:
    """Estado da carteira ao longo da simulação (ações inteiras, caixa, custo médio e IR)."""

    def __init__(self, capital: float, n_ativos: int) -> None:
        self.q = np.zeros(n_ativos)
        self.caixa = capital
        self.base = np.zeros(n_ativos)  # custo de aquisição que ainda está na carteira
        self.vendas_do_mes = 0.0
        self.resultado_do_mes = 0.0
        self.meses: list[tuple[pd.Timestamp, float, float]] = []

    def valores(self, precos: np.ndarray) -> np.ndarray:
        return self.q * precos

    def patrimonio(self, precos: np.ndarray) -> float:
        return float(self.caixa + np.nansum(self.valores(precos)))

    def executar(
        self, delta_q: np.ndarray, precos: np.ndarray, custos: np.ndarray
    ) -> None:
        for i, dq in enumerate(delta_q):
            if dq > 0:
                self.q[i] += dq
                self.base[i] += dq * precos[i] + custos[i]
            elif dq < 0:
                vendidas = min(-dq, self.q[i])
                fracao = vendidas / self.q[i]
                vendido = vendidas * precos[i]
                self.resultado_do_mes += vendido - custos[i] - fracao * self.base[i]
                self.vendas_do_mes += vendido
                self.base[i] -= fracao * self.base[i]
                self.q[i] -= vendidas
        self.caixa -= float(np.nansum(delta_q * precos)) + custos.sum()

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


def _decidir(
    dia: pd.Timestamp, dados: Dados, p: Parametros
) -> tuple[pd.Series, np.ndarray, np.ndarray] | None:
    """O alvo de D (ou nada), com o σ e o volume médio de todos os tickers para os custos."""
    universo = universo_em(dia, dados, p)
    if not universo:
        return None
    alvo = carteira_alvo(
        notas(fatores_em(dia, dados, universo, olhar_o_futuro=p.olhar_o_futuro)),
        p.quintil,
    )
    if alvo.empty:
        return None
    posicao = _posicao(pd.DatetimeIndex(dados.fechamento.index), dia)
    sigma = _volatilidade(dados.fechamento, posicao).to_numpy(float)
    volumes = _liquidez_media(dados.volume, posicao).to_numpy(float)
    return alvo, sigma, volumes


def _fins_de_mes(datas: pd.DatetimeIndex) -> list[int]:
    periodos = datas.to_period("M")
    return [
        t
        for t in range(len(datas))
        if t + 1 == len(datas) or periodos[t + 1] != periodos[t]
    ]


def _ultimo_pregao_de_cada_ticker(dados: Dados) -> np.ndarray:
    """Posição do último preço de cada ticker (ou do último pregão permitido pelo cadastro)."""
    datas = pd.DatetimeIndex(dados.fechamento.index)
    fim = pd.to_datetime(dados.cadastro["fim_negociacao"]).reindex(
        dados.fechamento.columns
    )
    ultimos = []
    for ticker in dados.fechamento.columns:
        ultimo = dados.fechamento[ticker].last_valid_index()
        posicao = -1 if ultimo is None else _posicao(datas, pd.Timestamp(ultimo))
        if pd.notna(fim[ticker]):
            posicao = min(
                posicao, int(datas.searchsorted(fim[ticker], side="right")) - 1
            )
        ultimos.append(posicao)
    return np.array(ultimos)


def simular(dados: Dados, parametros: Parametros) -> Resultado:
    """Simula a carteira dia a dia (ver as convenções no topo do módulo)."""
    _conferir_entradas(dados)
    p = parametros
    dados = replace(
        dados,
        fundamentos=dados.fundamentos[dados.fundamentos["conta"].isin(CONTAS_USADAS)],
    )
    datas = pd.DatetimeIndex(dados.fechamento.index)
    tickers = list(dados.fechamento.columns)
    n, k = dados.fechamento.shape
    V = dados.fechamento.ffill().to_numpy(
        float
    )  # avaliação: último fechamento conhecido
    A = dados.abertura.to_numpy(float)
    A = np.where(np.isnan(A), V, A)
    cdi_v = dados.cdi.to_numpy(float)
    ultimo = _ultimo_pregao_de_cada_ticker(dados)
    decisoes = set(datas.get_indexer(primeiros_pregoes_do_mes(datas)).tolist())
    fins = _fins_de_mes(datas)
    proximo_fim = {
        t: (fins[j + 1] if j + 1 < len(fins) else None) for j, t in enumerate(fins)
    }

    carteira = _Carteira(p.capital_inicial, k)
    retorno, patrimonio = np.zeros(n), np.zeros(n)
    custos, imposto = np.zeros(n), np.zeros(n)
    pesos, negociado = np.zeros((n, k)), np.zeros((n, k))
    alvos: dict[pd.Timestamp, pd.Series] = {}
    pendente: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
    a_pagar: dict[int, float] = {}
    pat_ontem = p.capital_inicial

    def executar(
        delta_q: np.ndarray, precos: np.ndarray, custo: np.ndarray, t: int
    ) -> None:
        carteira.executar(delta_q, precos, custo)
        negociado[t] += np.nan_to_num(delta_q * precos)
        custos[t] += custo.sum()

    for t in range(n):
        if t > 0:
            carteira.caixa *= 1 + cdi_v[t]
        for j in np.flatnonzero(
            (carteira.q > 0) & (t > ultimo)
        ):  # deslistada: vende tudo
            delta_q = np.zeros(k)
            delta_q[j] = -carteira.q[j]
            executar(
                delta_q,
                V[t],
                _custo_das_ordens(delta_q * V[t], np.zeros(k), np.zeros(k), p),
                t,
            )
        if pendente is not None:
            alvo, sigma, volumes = pendente
            pendente = None
            valores = np.nan_to_num(carteira.q * A[t])
            atual = pd.Series(valores / (carteira.caixa + valores.sum()), index=tickers)
            primeira = not carteira.q.any()
            if primeira or fora_da_banda(
                atual, pd.Series(alvo, index=tickers), p.banda
            ):
                delta_q, custo = _ordens_para_o_alvo(
                    alvo, carteira.q, carteira.caixa, A[t], sigma, volumes, p
                )
                executar(delta_q, A[t], custo, t)
        if t in a_pagar:
            devido = a_pagar.pop(t)
            delta_q, custo = _vender_para_pagar(carteira, devido, V[t], p)
            executar(delta_q, V[t], custo, t)
            carteira.caixa -= devido
            imposto[t] = devido
        if t in decisoes and t + 1 < n:
            decisao = _decidir(datas[t], dados, p)
            if decisao is not None:
                alvo_serie, sigma, volumes = decisao
                alvos[datas[t]] = alvo_serie
                pendente = (
                    alvo_serie.reindex(tickers).fillna(0.0).to_numpy(float),
                    sigma,
                    volumes,
                )
        if t in proximo_fim:
            devido = carteira.fechar_mes(datas[t], p.custos)
            if devido > 0 and proximo_fim[t] is not None:
                vencimento = proximo_fim[t]
                a_pagar[vencimento] = a_pagar.get(vencimento, 0.0) + devido
        pat_fim = carteira.patrimonio(V[t])
        retorno[t] = pat_fim / pat_ontem - 1 if t > 0 else 0.0
        patrimonio[t] = pat_fim
        pesos[t] = np.nan_to_num(carteira.valores(V[t])) / pat_fim
        pat_ontem = pat_fim

    anos = max(n / 252, 1e-9)
    giro = float(np.abs(negociado).sum() / anos / patrimonio.mean())
    return Resultado(
        retorno=pd.Series(retorno, index=datas, name="retorno"),
        patrimonio=pd.Series(patrimonio, index=datas, name="patrimonio"),
        pesos=pd.DataFrame(pesos, index=datas, columns=tickers),
        alvos=alvos,
        negociado=pd.DataFrame(negociado, index=datas, columns=tickers),
        custos=pd.Series(custos, index=datas, name="custos"),
        imposto=pd.Series(imposto, index=datas, name="imposto"),
        giro=giro,
        parametros=p,
    )


# --- verificações ------------------------------------------------------------------------------------


def conferir_sobrevivencia(dados: Dados) -> Conformidade:
    """Conta as deslistadas; sem nenhuma, o relatório sai com o aviso de viés de sobrevivência."""
    sobreviventes = _sobreviventes(dados)
    deslistadas = int((~sobreviventes).sum())
    vies = deslistadas == 0
    return Conformidade(
        deslistadas=deslistadas,
        total=len(sobreviventes),
        vies=vies,
        aviso=AVISO_DE_SOBREVIVENCIA
        if vies
        else f"{deslistadas} de {len(sobreviventes)} tickers deslistados no período.",
    )


def hash_do_resultado(resultado: Resultado) -> str:
    """Impressão digital do retorno e do patrimônio (reexecução idêntica)."""
    bruto = (
        resultado.retorno.round(12).to_numpy().tobytes()
        + resultado.patrimonio.round(6).to_numpy().tobytes()
    )
    return hashlib.sha256(bruto).hexdigest()


def cortar(dados: Dados, corte: pd.Timestamp) -> Dados:
    """As mesmas tabelas como seriam vistas em `corte`: nada divulgado nem acontecido depois."""
    ate = dados.fechamento.index <= corte
    cadastro = dados.cadastro.copy()
    fim = pd.to_datetime(cadastro["fim_negociacao"])
    cadastro["fim_negociacao"] = fim.where(fim <= corte)
    rj = dados.recuperacao_judicial
    if rj is not None:
        rj = rj[pd.to_datetime(rj["inicio"]) <= corte].copy()
        fim_rj = pd.to_datetime(rj["fim"])
        rj["fim"] = fim_rj.where(fim_rj <= corte)
    return Dados(
        fechamento=dados.fechamento[ate],
        abertura=dados.abertura[ate],
        volume=dados.volume[ate],
        cadastro=cadastro,
        fundamentos=dados.fundamentos[
            pd.to_datetime(dados.fundamentos["divulgado_em"]) <= corte
        ],
        acoes=dados.acoes[pd.to_datetime(dados.acoes["disponivel_em"]) <= corte],
        cdi=dados.cdi[ate],
        recuperacao_judicial=rj,
        ibovespa=None
        if dados.ibovespa is None
        else dados.ibovespa[dados.ibovespa.index <= corte],
    )


def cortar_o_futuro_nao_muda_o_passado(
    dados: Dados, parametros: Parametros, corte: pd.Timestamp
) -> bool:
    """Rodar só com o que existia em `corte` dá, até a véspera, o mesmo retorno de rodar tudo.

    O próprio dia do corte fica de fora: na série cortada ele é o último dia do mês (apura o IR),
    o que não é olhar o futuro, é o fim dos dados.
    """
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
    """Uma cópia dos parâmetros com algumas mudanças (vizinhos do platô, estresse, bruto)."""
    return replace(parametros, **mudancas)
