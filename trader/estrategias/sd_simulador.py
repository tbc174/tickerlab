"""Simulador do Synthetic Dividend (SD) e do rebalanceamento: a ficha P0-7 do pré-registro quant v0.1.

É um estudo e não uma candidata a dinheiro (pré-registro, ficha P0-7, e escolha 7 da seção 13). Ele
responde à pergunta original do relatório de 29/10 (seção 4) e testa os custos do Brasil de ponta a
ponta, sem passar pelo critério da seção 5, e mostra onde cada regra perde para comprar e segurar.

As quatro regras, sobre um ativo e o caixa (o que não está no ativo rende o caixa do dia):
- **Comprar e segurar:** compra tudo no primeiro dia e não mexe mais.
- **Full (SD):** passo r = 2^(1/N) − 1 com N = 8 (≈ 9,05%) e partilha s = 50%. A cada alta de r
  desde a âncora vende a fração r·s da posição; a cada queda de r recompra a mesma fração; a
  âncora passa a ser o preço executado. Começa com tudo no ativo.
- **ATH-only:** só a venda do Full (a âncora só sobe); nunca recompra.
- **Constant-mix com banda adaptativa:** w = 50% no ativo. Quando o preço anda r_t desde o último
  rebalanceamento (para cima ou para baixo), volta a w. r_t = σ_t ÷ √F, com σ_t a volatilidade
  anualizada das 90 observações anteriores ao dia e F as execuções desejadas por ano (30 em
  cripto, 12 na B3), e piso de 10 × o custo de ida e volta (relatório, seção 4.5).

Duas execuções:
- **fechamento** (a do pré-registro, seção 4): o gatilho é visto no fechamento de D e a ordem sai
  no fechamento de D+1, ao preço de D+1. Como há uma ordem por dia, não existe day trade.
- **limitada:** a ordem fica parada no gatilho. O dia tem `passos_por_dia` preços (o último é o
  fechamento) e a ordem executa no primeiro passo que alcança o gatilho, ao preço desse passo.
  Venda e recompra no mesmo dia são day trade (20%, apuração à parte, com a taxa à vista, um
  pouco maior que a de day trade); `bloquear_day_trade` impede a ordem contrária no mesmo dia.

Custos e imposto (`trader/custos_br.py`):
- taxa por lado da classe: cripto na corretora; na B3, à vista ou, na execução "fechamento", no
  leilão de fechamento; corretagem por ordem; IOF e spread só com `com_cambio`;
- IR mensal por custo médio: 15% no swing e em cripto, 20% no day trade;
- isenção de R$ 20 mil em ações e de R$ 35 mil em cripto; ETF sem isenção;
- prejuízo compensado nos meses seguintes; DARF pago do caixa no último dia do mês seguinte;
- `teto_de_vendas` não vende no mês em que a venda passaria da isenção.

Convenções fixadas antes de qualquer número (o relatório as repete em "Limites e cuidados"):
- **Caixa:** sem caixa negativo, a recompra fica limitada ao caixa. O modo do relatório
  (`caixa_negativo`) empresta ao mesmo juro do caixa. O DARF sai do caixa mesmo que ele fique
  negativo.
- **Âncora:** só muda quando uma ordem executa; venda travada ou recompra sem caixa não a mudam.
- **Impacto de mercado:** fica de fora; as ordens são de alguns por cento de R$ 200 mil.
- **Custo de aquisição do IR:** é o preço pago, sem as taxas (erra contra as regras que vendem).
- **"Liquidado":** o patrimônio se tudo fosse vendido no último dia, com o IR dessa venda. É a
  medida principal, porque comprar e segurar adia o imposto e as outras regras não.

Tudo é vetorizado nos caminhos: um caminho é um sorteio do Monte Carlo ou uma janela do
histórico. Nada aqui envia ordem; é só simulação.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

from trader.custos_br import CLASSES, PADRAO, CustosBR

VERSAO = "0.1"
REGRAS = ("comprar_e_segurar", "full", "ath", "constant_mix")
EXECUCOES = ("fechamento", "limitada")
N_DO_SD = 8
PASSO_DO_SD = 2 ** (1 / N_DO_SD) - 1  # ≈ 9,05%
PARTILHA = 0.5  # s: fração do passo que vira venda
FRACAO_DO_CONSTANT_MIX = 0.5  # w
JANELA_DA_VOL = 90  # observações diárias antes do dia
MULTIPLO_DO_PISO = 10  # banda >= 10 × o custo de ida e volta
EXECUCOES_DESEJADAS = {"cripto": 30, "acoes": 12, "etf": 12, "futuros": 12}  # F
CAPITAL_INICIAL = 200_000.0  # o exemplo do relatório (seção 4.5)
ANOS = 3
CAMINHOS = 2_000
SEMENTE = 20261103
PRECO_INICIAL = 100.0
PASSOS_NO_DIA = 8  # execução limitada: preços por dia no Monte Carlo
INICIO_DO_SORTEIO = pd.Timestamp(
    "2030-01-01"
)  # calendário sintético (só os meses importam)
ZERO = 1e-12
ORDEM_MINIMA = (
    1.0  # reais: abaixo disso é resto de conta, não ordem (e não muda a âncora)
)


@dataclass(frozen=True)
class Parametros:
    """A regra e as fricções de uma simulação; as variações do estudo são cópias com uma mudança."""

    regra: str = "full"
    classe: str = "cripto"
    dias_por_ano: int = 365
    passo: float = PASSO_DO_SD
    partilha: float = PARTILHA
    fracao: float = FRACAO_DO_CONSTANT_MIX
    execucoes_desejadas: int = EXECUCOES_DESEJADAS["cripto"]
    janela_da_vol: int = JANELA_DA_VOL
    execucao: str = "fechamento"
    custos: CustosBR = PADRAO
    com_imposto: bool = True
    com_cambio: bool = False
    teto_de_vendas: bool = False
    bloquear_day_trade: bool = False
    caixa_negativo: bool = False

    def __post_init__(self) -> None:
        if self.regra not in REGRAS:
            raise ValueError(f"regra desconhecida: {self.regra!r}; use uma de {REGRAS}")
        if self.classe not in CLASSES or self.classe == "futuros":
            raise ValueError("a classe tem de ser cripto, acoes ou etf")
        if self.execucao not in EXECUCOES:
            raise ValueError(f"execução desconhecida: {self.execucao!r}")
        if not 0 < self.passo < 1 or not 0 < self.partilha <= 1:
            raise ValueError("passo e partilha precisam ficar entre 0 e 1")
        if not 0 < self.fracao < 1:
            raise ValueError("a fração do constant-mix precisa ficar entre 0 e 1")
        if self.execucoes_desejadas <= 0 or self.janela_da_vol < 2:
            raise ValueError("F precisa ser positivo e a janela da volatilidade >= 2")

    def especificacao(self) -> dict:
        """Tudo o que define a simulação, em tipos simples (vai para o registro)."""
        spec = asdict(self)
        spec["custos"] = {
            k: list(v) if isinstance(v, tuple) else v for k, v in spec["custos"].items()
        }
        return spec


def com(parametros: Parametros, **mudancas: object) -> Parametros:
    """Uma cópia dos parâmetros com algumas mudanças."""
    return replace(parametros, **mudancas)


@dataclass(frozen=True)
class Caminhos:
    """Os preços de vários caminhos com o mesmo número de dias.

    `precos` tem `passos_por_dia` linhas por dia (a última de cada dia é o fechamento) e uma coluna
    por caminho; `caixa` e `fim_do_mes` têm uma linha por dia. Os dias antes de `inicio` só servem
    para a volatilidade.
    """

    precos: np.ndarray
    passos_por_dia: int
    caixa: np.ndarray
    fim_do_mes: np.ndarray
    inicio: int

    def __post_init__(self) -> None:
        dias, n = self.caixa.shape
        if self.precos.shape != (dias * self.passos_por_dia, n):
            raise ValueError("preços, caixa e passos por dia não batem")
        if self.fim_do_mes.shape != (dias, n):
            raise ValueError("o fim do mês precisa de uma linha por dia")
        if not 0 <= self.inicio < dias - 1:
            raise ValueError(
                "o primeiro dia simulado precisa deixar pelo menos mais um dia"
            )
        if not np.all(self.precos > 0):
            raise ValueError("todo preço precisa ser positivo")

    @property
    def fechamentos(self) -> np.ndarray:
        return self.precos[self.passos_por_dia - 1 :: self.passos_por_dia]


@dataclass
class Resultado:
    """Uma linha por caminho (tudo em reais, salvo o que diz o contrário)."""

    final: (
        np.ndarray
    )  # patrimônio no último dia, sem vender (IR do que já foi vendido pago)
    liquidado: np.ndarray  # vendendo tudo no último dia, com custo e IR dessa venda
    patrimonio: np.ndarray  # (dias simulados, caminhos), no fechamento de cada dia
    imposto: np.ndarray  # DARFs pagos (sem o da liquidação)
    custos: np.ndarray  # corretagem, taxas e câmbio
    execucoes: np.ndarray  # ordens executadas, sem a compra inicial
    dias_de_day_trade: np.ndarray
    vendas_travadas: np.ndarray  # vendas que o teto não deixou sair
    caixa_minimo: np.ndarray  # menor caixa ÷ patrimônio
    anos: float
    capital: float
    parametros: Parametros

    def multiplo(self) -> np.ndarray:
        """Patrimônio liquidado ÷ capital inicial."""
        return self.liquidado / self.capital

    def maior_queda(self) -> np.ndarray:
        pico = np.maximum.accumulate(self.patrimonio, axis=0)
        return (1 - self.patrimonio / pico).max(axis=0)


# --- as contas que não dependem da regra -------------------------------------------------------------


def taxa_por_lado(parametros: Parametros) -> float:
    """Fração do valor paga em cada ordem (sem a corretagem fixa)."""
    custos = parametros.custos
    if parametros.classe == "cripto":
        taxa = custos.taxa_cripto_por_lado
    elif parametros.execucao == "fechamento":
        taxa = custos.emolumentos_no_leilao
    else:
        taxa = custos.emolumentos_a_vista
    if parametros.com_cambio:
        taxa += custos.iof_cambio + custos.spread_cambio
    return taxa


def piso_da_banda(parametros: Parametros) -> float:
    """10 × o custo de ida e volta: a banda abaixo disso dá ao custo mais de 10% do bruto."""
    return MULTIPLO_DO_PISO * 2 * taxa_por_lado(parametros)


def volatilidade_conhecida(
    fechamentos: np.ndarray, janela: int, dias_por_ano: int
) -> np.ndarray:
    """σ anualizada dos log-retornos das `janela` observações antes de cada dia (sem o dia)."""
    log = np.log(pd.DataFrame(fechamentos)).diff()
    sigma = log.rolling(janela).std().shift(1) * np.sqrt(dias_por_ano)
    return sigma.to_numpy(float)


def banda_adaptativa(sigma: np.ndarray, parametros: Parametros) -> np.ndarray:
    """r_t = σ_t ÷ √F, nunca abaixo do piso."""
    return np.maximum(
        sigma / np.sqrt(parametros.execucoes_desejadas), piso_da_banda(parametros)
    )


def ir_do_mes(
    vendas: np.ndarray,
    resultado: np.ndarray,
    prejuizo: np.ndarray,
    isencao: float,
    aliquota: float,
) -> tuple[np.ndarray, np.ndarray]:
    """O imposto do mês e o prejuízo que fica, caminho a caminho (a regra de `apurar_ir_mensal`)."""
    isento = (vendas <= isencao) if isencao > 0 else np.zeros_like(vendas, bool)
    perdeu = resultado < 0
    tributavel = ~perdeu & ~isento
    compensado = np.where(tributavel, np.minimum(prejuizo, resultado), 0.0)
    imposto = np.where(tributavel, resultado - compensado, 0.0) * aliquota
    restante = prejuizo + np.where(perdeu, -resultado, 0.0) - compensado
    return imposto, restante


# --- o livro de cada caminho ----------------------------------------------------------------------------


class _Livro:
    """Posição, caixa, âncora e as contas do dia e do mês de cada caminho (vetores)."""

    def __init__(self, n: int, capital: float, parametros: Parametros) -> None:
        self.p = parametros
        self.taxa = taxa_por_lado(parametros)
        self.corretagem = parametros.custos.corretagem_por_ordem
        self.caixa = np.full(n, float(capital))
        self.quantidade = np.zeros(n)
        self.custo_medio = np.zeros(n)
        self.ancora = np.full(n, np.nan)
        self.no_inicio_do_dia = np.zeros(n)
        self.comprado_qtd, self.comprado_valor = np.zeros(n), np.zeros(n)
        self.vendido_qtd, self.vendido_valor = np.zeros(n), np.zeros(n)
        self.vendas_swing, self.resultado_swing = np.zeros(n), np.zeros(n)
        self.vendas_dt, self.resultado_dt = np.zeros(n), np.zeros(n)
        self.prejuizo_swing, self.prejuizo_dt = np.zeros(n), np.zeros(n)
        self.darf_pendente = np.zeros(n)
        self.imposto, self.custos = np.zeros(n), np.zeros(n)
        self.execucoes = np.zeros(n, int)
        self.dias_de_day_trade = np.zeros(n, int)
        self.vendas_travadas = np.zeros(n, int)

    def patrimonio(self, preco: np.ndarray) -> np.ndarray:
        return self.caixa + self.quantidade * preco

    def _isencao(self) -> float:
        return self.p.custos.isencao_no_mes(self.p.classe, day_trade=False)

    def limitar(self, quantidade: np.ndarray, preco: np.ndarray) -> np.ndarray:
        """Tira da ordem o que o caixa, o teto de vendas e o bloqueio de day trade não deixam."""
        q = quantidade.copy()
        compra, venda = q > 0, q < 0
        if not self.p.caixa_negativo:
            cabe = np.maximum(self.caixa - self.corretagem, 0.0) / (
                preco * (1 + self.taxa)
            )
            q = np.where(compra, np.minimum(q, cabe), q)
        if self.p.teto_de_vendas and self._isencao() > 0:
            no_mes = self.vendas_swing + self.vendido_valor - q * preco
            travada = venda & (no_mes > self._isencao())
            self.vendas_travadas += travada
            q = np.where(travada, 0.0, q)
        if self.p.bloquear_day_trade:
            q = np.where((q > 0) & (self.vendido_qtd > 0), 0.0, q)
            q = np.where((q < 0) & (self.comprado_qtd > 0), 0.0, q)
        return np.where(np.abs(q) * preco >= ORDEM_MINIMA, q, 0.0)

    def executar(
        self, quantidade: np.ndarray, preco: np.ndarray, contar: bool = True
    ) -> None:
        """Compra (q > 0) ou vende (q < 0) ao preço; paga as taxas e muda a âncora de quem negociou."""
        houve = quantidade != 0
        valor = np.abs(quantidade) * preco
        custo = np.where(houve, self.corretagem + valor * self.taxa, 0.0)
        self.caixa -= quantidade * preco + custo
        self.quantidade += quantidade
        self.quantidade[np.abs(self.quantidade) < ZERO] = 0.0
        compra, venda = quantidade > 0, quantidade < 0
        self.comprado_qtd += np.where(compra, quantidade, 0.0)
        self.comprado_valor += np.where(compra, valor, 0.0)
        self.vendido_qtd += np.where(venda, -quantidade, 0.0)
        self.vendido_valor += np.where(venda, valor, 0.0)
        self.custos += custo
        if contar:
            self.execucoes += houve
        self.ancora = np.where(houve, preco, self.ancora)

    def fechar_o_dia(self) -> None:
        """Day trade (o que foi comprado e vendido no dia) à parte; o resto pelo custo médio."""
        qc, qv = self.comprado_qtd, self.vendido_qtd
        preco_c = np.divide(
            self.comprado_valor, qc, out=np.zeros_like(qc), where=qc > 0
        )
        preco_v = np.divide(self.vendido_valor, qv, out=np.zeros_like(qv), where=qv > 0)
        day_trade = np.minimum(qc, qv)
        self.vendas_dt += day_trade * preco_v
        self.resultado_dt += day_trade * (preco_v - preco_c)
        self.dias_de_day_trade += day_trade > 0
        compra, venda = qc - day_trade, qv - day_trade
        total = self.no_inicio_do_dia + compra
        medio = np.divide(
            self.no_inicio_do_dia * self.custo_medio + compra * preco_c,
            total,
            out=np.zeros_like(total),
            where=total > 0,
        )
        self.vendas_swing += venda * preco_v
        self.resultado_swing += venda * (preco_v - self.custo_medio)
        self.custo_medio = np.where(compra > 0, medio, self.custo_medio)
        self.custo_medio[self.quantidade <= 0] = 0.0
        self.no_inicio_do_dia = self.quantidade.copy()
        for conta in (qc, qv, self.comprado_valor, self.vendido_valor):
            conta[:] = 0.0

    def _imposto_do_mes(
        self, vendas: np.ndarray, resultado: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if not self.p.com_imposto:
            zero = np.zeros_like(vendas)
            return zero, self.prejuizo_swing, self.prejuizo_dt
        custos, classe = self.p.custos, self.p.classe
        swing, prejuizo_swing = ir_do_mes(
            vendas,
            resultado,
            self.prejuizo_swing,
            self._isencao(),
            custos.aliquota(classe, day_trade=False),
        )
        dt, prejuizo_dt = ir_do_mes(
            self.vendas_dt,
            self.resultado_dt,
            self.prejuizo_dt,
            0.0,
            custos.aliquota(classe, day_trade=True),
        )
        return swing + dt, prejuizo_swing, prejuizo_dt

    def fechar_o_mes(self, fim: np.ndarray) -> None:
        """Nos caminhos em que o mês acabou: paga o DARF do mês anterior e apura o deste."""
        devido, prejuizo_swing, prejuizo_dt = self._imposto_do_mes(
            self.vendas_swing, self.resultado_swing
        )
        pago = np.where(fim, self.darf_pendente, 0.0)
        self.caixa -= pago
        self.imposto += pago
        self.darf_pendente = np.where(fim, devido, self.darf_pendente)
        self.prejuizo_swing = np.where(fim, prejuizo_swing, self.prejuizo_swing)
        self.prejuizo_dt = np.where(fim, prejuizo_dt, self.prejuizo_dt)
        for conta in (
            self.vendas_swing,
            self.resultado_swing,
            self.vendas_dt,
            self.resultado_dt,
        ):
            conta[fim] = 0.0

    def encerrar(self, preco: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """No último dia: (patrimônio sem vender, patrimônio vendendo tudo), com os DARFs pagos."""
        devido, _, _ = self._imposto_do_mes(self.vendas_swing, self.resultado_swing)
        final = self.patrimonio(preco) - self.darf_pendente - devido
        valor = self.quantidade * preco
        custo = np.where(valor > 0, self.corretagem + valor * self.taxa, 0.0)
        ganho = valor - self.quantidade * self.custo_medio
        devido_vendendo, _, _ = self._imposto_do_mes(
            self.vendas_swing + valor, self.resultado_swing + ganho
        )
        liquidado = self.caixa + valor - custo - self.darf_pendente - devido_vendendo
        self.imposto += self.darf_pendente + devido
        self.caixa -= self.darf_pendente + devido
        self.darf_pendente[:] = 0.0
        return final, liquidado


# --- as regras -------------------------------------------------------------------------------------------


def _passos(preco: np.ndarray, ancora: np.ndarray, passo: float) -> np.ndarray:
    """Quantos passos inteiros o preço andou desde a âncora (+ para cima, − para baixo)."""
    with np.errstate(invalid="ignore"):
        andou = np.log(preco / ancora) / np.log1p(passo)
    andou = np.nan_to_num(andou, nan=0.0)
    return np.sign(andou) * np.floor(np.abs(andou) + ZERO)


def gatilho(
    preco: np.ndarray, livro: _Livro, banda: np.ndarray, parametros: Parametros
) -> np.ndarray:
    """O que a regra pede ao preço de agora: passos do SD (+ vende, − compra) ou ±1 no constant-mix."""
    regra = parametros.regra
    if regra == "comprar_e_segurar":
        return np.zeros_like(preco)
    if regra == "constant_mix":
        with np.errstate(invalid="ignore"):
            subiu = preco >= livro.ancora * (1 + banda)
            caiu = preco <= livro.ancora / (1 + banda)
        return np.where(subiu, 1.0, np.where(caiu, -1.0, 0.0))
    passos = _passos(preco, livro.ancora, parametros.passo)
    return np.maximum(passos, 0.0) if regra == "ath" else passos


def ordem(
    sinal: np.ndarray, preco: np.ndarray, livro: _Livro, parametros: Parametros
) -> np.ndarray:
    """A quantidade que o sinal pede ao preço de execução (+ compra, − venda), antes dos limites."""
    if parametros.regra == "constant_mix":
        valor = livro.quantidade * preco
        alvo = parametros.fracao * livro.patrimonio(preco)
        return np.where(sinal != 0, (alvo - valor) / preco, 0.0)
    fracao = parametros.passo * parametros.partilha
    vende = livro.quantidade * (1 - (1 - fracao) ** np.maximum(sinal, 0.0))
    compra = livro.quantidade * ((1 + fracao) ** np.maximum(-sinal, 0.0) - 1)
    return compra - vende


def _comprar_no_inicio(
    livro: _Livro, preco: np.ndarray, parametros: Parametros
) -> None:
    fracao = parametros.fracao if parametros.regra == "constant_mix" else 1.0
    disponivel = np.maximum(livro.caixa * fracao - livro.corretagem, 0.0)
    livro.executar(disponivel / (preco * (1 + livro.taxa)), preco, contar=False)


# --- a simulação -----------------------------------------------------------------------------------------


def simular(
    caminhos: Caminhos, parametros: Parametros, capital: float = CAPITAL_INICIAL
) -> Resultado:
    """Simula a regra em todos os caminhos de uma vez, dia a dia (e passo a passo na limitada)."""
    m = caminhos.passos_por_dia
    if parametros.execucao == "fechamento" and m != 1:
        raise ValueError("a execução no fechamento usa um preço por dia")
    if (
        caminhos.inicio < parametros.janela_da_vol + 1
        and parametros.regra == "constant_mix"
    ):
        raise ValueError("faltam observações antes do início para a volatilidade")
    dias, n = caminhos.caixa.shape
    bandas = banda_adaptativa(
        volatilidade_conhecida(
            caminhos.fechamentos, parametros.janela_da_vol, parametros.dias_por_ano
        ),
        parametros,
    )
    livro = _Livro(n, capital, parametros)
    patrimonio = np.full((dias - caminhos.inicio, n), np.nan)
    caixa_minimo = np.ones(n)
    pendente = np.zeros(n)
    final = liquidado = np.zeros(n)
    for d in range(caminhos.inicio, dias):
        livro.caixa *= 1 + caminhos.caixa[d]
        for k in range(m):
            preco = caminhos.precos[d * m + k]
            if d == caminhos.inicio:
                if k == m - 1:
                    _comprar_no_inicio(livro, preco, parametros)
                continue
            if parametros.execucao == "fechamento":
                livro.executar(
                    livro.limitar(ordem(pendente, preco, livro, parametros), preco),
                    preco,
                )
            else:
                sinal = gatilho(preco, livro, bandas[d], parametros)
                livro.executar(
                    livro.limitar(ordem(sinal, preco, livro, parametros), preco), preco
                )
        fechamento = caminhos.precos[d * m + m - 1]
        if parametros.execucao == "fechamento":
            pendente = gatilho(fechamento, livro, bandas[d], parametros)
        livro.fechar_o_dia()
        if d == dias - 1:
            final, liquidado = livro.encerrar(fechamento)
        else:
            livro.fechar_o_mes(caminhos.fim_do_mes[d])
        valor = livro.patrimonio(fechamento)
        patrimonio[d - caminhos.inicio] = valor
        caixa_minimo = np.minimum(caixa_minimo, livro.caixa / valor)
    return Resultado(
        final=final,
        liquidado=liquidado,
        patrimonio=patrimonio,
        imposto=livro.imposto,
        custos=livro.custos,
        execucoes=livro.execucoes,
        dias_de_day_trade=livro.dias_de_day_trade,
        vendas_travadas=livro.vendas_travadas,
        caixa_minimo=caixa_minimo,
        anos=(dias - caminhos.inicio - 1) / parametros.dias_por_ano,
        capital=capital,
        parametros=parametros,
    )


# --- os caminhos -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cenario:
    """Um cenário do Monte Carlo (tabela da seção 4.4 do relatório)."""

    nome: str
    mu: float  # deriva anual (aritmética) do GBM
    sigma: float  # volatilidade anual
    classe: str
    dias_por_ano: int


def _calendario(dias: int, dias_por_ano: int) -> pd.DatetimeIndex:
    if dias_por_ano == 365:
        return pd.date_range(INICIO_DO_SORTEIO, periods=dias, freq="D")
    return pd.bdate_range(INICIO_DO_SORTEIO, periods=dias)


def fim_do_mes(datas: pd.DatetimeIndex) -> np.ndarray:
    """Verdadeiro no último dia de cada mês dos dados (e no último dia da série)."""
    meses = datas.to_period("M")
    return np.append(meses[1:] != meses[:-1], True)


def caminhos_gbm(
    cenario: Cenario,
    caixa_anual: float,
    *,
    caminhos: int = CAMINHOS,
    anos: int = ANOS,
    passos_por_dia: int = 1,
    semente: int = SEMENTE,
    janela_da_vol: int = JANELA_DA_VOL,
) -> Caminhos:
    """Movimento browniano geométrico com `janela_da_vol` + 1 dias antes do início (só para σ)."""
    dias_por_ano = cenario.dias_por_ano
    inicio = janela_da_vol + 1
    dias = inicio + anos * dias_por_ano + 1
    dt = 1 / (dias_por_ano * passos_por_dia)
    sorteio = np.random.default_rng(semente)
    log = sorteio.standard_normal((dias * passos_por_dia, caminhos))
    log *= cenario.sigma * np.sqrt(dt)
    log += (cenario.mu - cenario.sigma**2 / 2) * dt
    log[0] = 0.0
    precos = PRECO_INICIAL * np.exp(np.cumsum(log, axis=0))
    datas = _calendario(dias, dias_por_ano)
    diario = (1 + caixa_anual) ** (1 / dias_por_ano) - 1
    return Caminhos(
        precos=precos,
        passos_por_dia=passos_por_dia,
        caixa=np.full((dias, caminhos), diario),
        fim_do_mes=np.repeat(fim_do_mes(datas)[:, None], caminhos, axis=1),
        inicio=inicio,
    )


def janelas_do_historico(
    fechamento: pd.Series,
    caixa: pd.Series,
    *,
    dias: int,
    aquecimento: int,
    janela_da_vol: int = JANELA_DA_VOL,
) -> tuple[Caminhos, list[pd.Timestamp]]:
    """Uma janela de `dias` observações a partir do primeiro dia de cada mês.

    A primeira janela começa depois de `aquecimento` observações da série (pré-registro, seção 2);
    as `janela_da_vol` + 1 observações antes de cada começo só servem para a volatilidade. As
    janelas se sobrepõem: os percentis delas não são independentes.
    """
    if not fechamento.index.equals(caixa.index):
        raise ValueError("preço e caixa precisam das mesmas datas")
    datas = pd.DatetimeIndex(fechamento.index)
    meses = datas.to_period("M")
    primeiros = np.flatnonzero(np.append(True, meses[1:] != meses[:-1]))
    antes = janela_da_vol + 1
    comecos = [
        i for i in primeiros if i >= max(aquecimento, antes) and i + dias <= len(datas)
    ]
    if not comecos:
        raise ValueError("a série é curta demais para uma janela inteira")
    fim = fim_do_mes(datas)
    precos = fechamento.to_numpy(float)
    retornos = caixa.to_numpy(float)
    fatias = [slice(i - antes, i + dias) for i in comecos]
    return (
        Caminhos(
            precos=np.column_stack([precos[f] for f in fatias]),
            passos_por_dia=1,
            caixa=np.column_stack([retornos[f] for f in fatias]),
            fim_do_mes=np.column_stack([fim[f] for f in fatias]),
            inicio=antes,
        ),
        [datas[i] for i in comecos],
    )


# --- o resumo --------------------------------------------------------------------------------------------


def resumir(resultado: Resultado, regua: Resultado | None = None) -> dict:
    """Mediana, p5, p95 e média do múltiplo liquidado, e quanto vence a régua no mesmo caminho."""
    multiplo = resultado.multiplo()
    resumo = {
        "mediana": float(np.median(multiplo)),
        "p5": float(np.percentile(multiplo, 5)),
        "p95": float(np.percentile(multiplo, 95)),
        "media": float(multiplo.mean()),
        "mediana_sem_vender": float(np.median(resultado.final / resultado.capital)),
        "execucoes_por_ano": float(np.median(resultado.execucoes) / resultado.anos),
        "imposto": float(np.median(resultado.imposto) / resultado.capital),
        "custos": float(np.median(resultado.custos) / resultado.capital),
        "maior_queda": float(np.median(resultado.maior_queda())),
        "dias_de_day_trade": float(resultado.dias_de_day_trade.mean()),
        "vendas_travadas": float(resultado.vendas_travadas.mean()),
        "caixa_minimo": float(resultado.caixa_minimo.min()),
        "caminhos": len(multiplo),
    }
    if regua is not None:
        resumo["vence_a_regua"] = float((multiplo > regua.multiplo()).mean())
    return resumo


def hash_do_resultado(resultado: Resultado) -> str:
    """Impressão digital do patrimônio de todos os caminhos (reexecução idêntica)."""
    return hashlib.sha256(
        np.ascontiguousarray(resultado.patrimonio.round(6)).tobytes()
        + resultado.liquidado.round(6).tobytes()
    ).hexdigest()
