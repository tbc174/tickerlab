"""A ficha "Foi sorte?": cinco checagens "passou / não passou" e um veredito (ADR 0037, D1 e D2).

A ficha junta, em linguagem simples, a validação que o backtest já faz (`validacao.py` e
`acaso.py`). A única escolha nova está na checagem 3: a dispersão dos Sharpes "sem habilidade",
que o Sharpe deflacionado usa, vem das versões ao acaso da própria regra, e não da grade de
parâmetros (ver `medir_acaso`). Cada checagem responde uma pergunta:

1. Funcionou fora do período usado para escolher os parâmetros?
2. Sobrevive aos custos e ao imposto (rende mais que o CDI)?
3. Bate o acaso, contando as tentativas da pessoa?
4. Funciona com parâmetros vizinhos?
5. As quedas cabem no que a pessoa aguenta?

Os limites de cada checagem são constantes deste módulo, escritos antes de qualquer resultado
(o espírito da ADR 0006) e publicados na metodologia.
"""

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from src.acaso import (
    MIN_OPERACOES_PARA_MONTE_CARLO,
    calcular_sharpe_maximo_esperado,
    calcular_sharpe_probabilistico,
    resumir_monte_carlo,
    simular_monte_carlo,
    testar_contra_o_acaso,
)
from src.backtest import (
    CUSTO_PADRAO_POR_OPERACAO,
    ResultadoBacktest,
    executar_backtest,
)
from src.cdi import curva_do_cdi
from src.estrategias import gerar_posicao
from src.imposto import aplicar_imposto
from src.indicadores import DIAS_POR_ANO, calcular_indice_sharpe
from src.protecoes import Protecoes, aplicar_protecoes
from src.validacao import (
    FRACAO_DE_TREINO_PADRAO,
    avaliar_treino_e_teste,
    calcular_retornos_dos_candidatos,
    data_de_corte,
    executar_walk_forward,
    montar_candidatos,
    montar_mapa_de_sharpe,
    parametros_numericos,
)

AVISO = "Vale para os dados do passado. Não é promessa de resultado nem recomendação."

PERGUNTA_FORA_DO_PERIODO = "Funcionou fora do período usado para escolher?"
PERGUNTA_VIZINHOS = "Funciona com parâmetros vizinhos?"
PERGUNTA_CUSTOS = "Sobrevive aos custos e ao imposto?"
PERGUNTA_QUEDAS = "As quedas cabem no que você aguenta?"
PERGUNTA_ACASO = "Bate o acaso, contando as suas tentativas?"

# Checagem 1: as janelas do walk-forward (dias úteis), as mesmas que a tela abre por padrão;
# com menos histórico que treino + teste, vale um corte só (treino e teste)
DIAS_DE_TREINO = 504
DIAS_DE_TESTE = 126
# Checagem 1: o Sharpe de fora precisa guardar pelo menos metade do de dentro
EFICIENCIA_MINIMA = 0.5
# Checagem 3: poucas versões ao acaso fazem igual (p-valor) e, descontadas as tentativas, o
# Sharpe deflacionado convence (chance de não ser sorte)
P_VALOR_MAXIMO = 0.05
CHANCE_MINIMA_DE_NAO_SER_SORTE = 0.95
# Checagem 4: 2 de cada 3 vizinhos com Sharpe positivo, e a mediana deles com pelo menos metade
# do Sharpe da configuração escolhida (um pico isolado cercado de resultados fracos é sorte)
FRACAO_MINIMA_DE_VIZINHOS_POSITIVOS = 2 / 3
FRACAO_MINIMA_DA_MEDIANA = 0.5
# Checagem 5: a maior queda que a pessoa aguentaria, se ela não disser outra (fração), e a faixa
# aceita; a escolha fica nas preferências da conta com esta chave
TOLERANCIA_PADRAO_DE_QUEDA = 0.30
TOLERANCIA_MINIMA = 0.05
TOLERANCIA_MAXIMA = 0.90
PREFERENCIA_DA_TOLERANCIA = "tolerancia_de_queda"


class Situacao(Enum):
    PASSOU = "passou"
    NAO_PASSOU = "não passou"
    NAO_SE_APLICA = "não se aplica"  # não havia o que conferir (ex.: nada foi ajustado)
    SEM_MEDIDA = "não deu para medir"  # faltaram dados ou operações


class Resultado(Enum):
    PASSOU = "passou"
    NAO_PASSOU = "não passou"
    INCONCLUSIVO = "inconclusivo"


@dataclass(frozen=True)
class Checagem:
    pergunta: str
    situacao: Situacao
    explicacao: str  # uma frase em português, com os números que decidiram


@dataclass(frozen=True)
class Veredito:
    resultado: Resultado
    titulo: str
    texto: str  # sempre termina com o AVISO


@dataclass(frozen=True)
class Ficha:
    checagens: tuple[Checagem, ...]
    tentativas: int  # quantas variações entraram na conta da checagem 3

    @property
    def veredito(self) -> Veredito:
        """Passou só se nenhuma checagem falhou nem ficou sem medida ("não se aplica" não pesa)."""
        return montar_veredito(self.checagens)


def _perguntas(checagens: tuple[Checagem, ...], situacao: Situacao) -> str:
    return "; ".join(c.pergunta for c in checagens if c.situacao is situacao)


def montar_veredito(checagens: tuple[Checagem, ...]) -> Veredito:
    """O veredito da ficha a partir das checagens, com o texto que explica o porquê."""
    falhas = _perguntas(checagens, Situacao.NAO_PASSOU)
    if falhas:
        return Veredito(
            Resultado.NAO_PASSOU,
            "Não passou no teste contra a sorte",
            f"Não passou em: {falhas} Uma regra assim pode ter funcionado só no passado: "
            f"não coloque dinheiro nela por causa deste resultado. {AVISO}",
        )
    sem_medida = _perguntas(checagens, Situacao.SEM_MEDIDA)
    if sem_medida or not any(c.situacao is Situacao.PASSOU for c in checagens):
        return Veredito(
            Resultado.INCONCLUSIVO,
            "Inconclusivo",
            "Nenhuma checagem falhou, mas não deu para medir: "
            f"{sem_medida or 'nenhuma checagem se aplica'}. Com mais histórico ou mais "
            f"operações a ficha pode responder. {AVISO}",
        )
    return Veredito(
        Resultado.PASSOU,
        "Passou no teste contra a sorte",
        "Todas as checagens que se aplicam passaram: o resultado não parece ser só sorte. "
        f"{AVISO}",
    )


# --- Construtores das situações sem conta ------------------------------------------------


def nao_se_aplica(pergunta: str, motivo: str) -> Checagem:
    """Checagem que não tinha o que conferir (por exemplo, a regra não tem números para ajustar)."""
    return Checagem(pergunta, Situacao.NAO_SE_APLICA, motivo)


def sem_medida(pergunta: str, motivo: str) -> Checagem:
    """Checagem que não pôde ser feita (poucos dados, poucas operações)."""
    return Checagem(pergunta, Situacao.SEM_MEDIDA, motivo)


def _numero(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


def _porcentagem(valor: float) -> str:
    return f"{valor * 100:+.1f}%".replace(".", ",")


def _percentual(valor: float) -> str:
    return f"{valor * 100:.1f}%".replace(".", ",")


def _queda(valor: float) -> str:
    return f"{abs(valor) * 100:.0f}%"


def _situacao(passou: bool) -> Situacao:
    return Situacao.PASSOU if passou else Situacao.NAO_PASSOU


# --- Checagem 1: fora do período ---------------------------------------------------------


def checar_fora_do_periodo(
    sharpe_fora: float, sharpe_dentro: float, como: str
) -> Checagem:
    """Passa se o Sharpe fora do período de escolha é positivo e guarda pelo menos
    `EFICIENCIA_MINIMA` do Sharpe de dentro. `como`: "walk-forward" ou "treino e teste"."""
    if np.isnan(sharpe_fora):
        return Checagem(
            PERGUNTA_FORA_DO_PERIODO,
            Situacao.NAO_PASSOU,
            f"No {como}, a regra não operou fora do período de escolha.",
        )
    passou = (
        sharpe_fora > 0
        and sharpe_dentro > 0
        and sharpe_fora >= EFICIENCIA_MINIMA * sharpe_dentro
    )
    return Checagem(
        PERGUNTA_FORA_DO_PERIODO,
        _situacao(passou),
        f"No {como}, o Sharpe foi {_numero(sharpe_dentro)} no período usado para escolher "
        f"e {_numero(sharpe_fora)} fora dele.",
    )


# --- Checagem 4: parâmetros vizinhos -----------------------------------------------------


Valor = float | str  # valor de um parâmetro no mapa ("" quando só um parâmetro varia)


def _posicao_mais_proxima(rotulos: pd.Index, valor: Valor) -> int:
    exata = int(rotulos.get_indexer([valor])[0])  # -1 quando o valor não está na grade
    if exata >= 0:
        return exata
    distancias = np.abs(np.asarray(rotulos, dtype=float) - float(valor))
    return int(distancias.argmin())


def vizinhos(mapa: pd.DataFrame, escolhido: tuple[Valor, Valor]) -> list[float]:
    """Sharpes das casas em volta da escolhida no mapa de parâmetros (até 8; as inválidas saem).

    `mapa` vem de `validacao.montar_mapa_de_sharpe` (colunas = 1º parâmetro, linhas = 2º);
    `escolhido` = (valor do 1º, valor do 2º ou ""). Fora da grade, vale a casa mais próxima.
    """
    coluna = _posicao_mais_proxima(mapa.columns, escolhido[0])
    linha = _posicao_mais_proxima(mapa.index, escolhido[1])
    valores = mapa.to_numpy(dtype=float).copy()
    valores[linha, coluna] = np.nan  # a própria escolha não é vizinha dela
    bloco = valores[max(linha - 1, 0) : linha + 2, max(coluna - 1, 0) : coluna + 2]
    return [float(v) for v in bloco.ravel() if not np.isnan(v)]


def checar_vizinhos(
    mapa: pd.DataFrame, escolhido: tuple[Valor, Valor], sharpe_da_pessoa: float
) -> Checagem:
    """Passa se a configuração está numa região boa do mapa, não num pico isolado."""
    if np.isnan(sharpe_da_pessoa):
        return sem_medida(
            PERGUNTA_VIZINHOS,
            "A sua configuração não operou: não há Sharpe para comparar.",
        )
    em_volta = vizinhos(mapa, escolhido)
    if not em_volta:
        return sem_medida(
            PERGUNTA_VIZINHOS, "Não há combinações vizinhas válidas para comparar."
        )
    positivos = sum(v > 0 for v in em_volta)
    mediana = float(np.median(em_volta))
    passou = (
        positivos >= FRACAO_MINIMA_DE_VIZINHOS_POSITIVOS * len(em_volta)
        and mediana >= FRACAO_MINIMA_DA_MEDIANA * sharpe_da_pessoa
    )
    return Checagem(
        PERGUNTA_VIZINHOS,
        _situacao(passou),
        f"{positivos} de {len(em_volta)} combinações vizinhas têm Sharpe "
        f"positivo; a mediana delas é {_numero(mediana)}, contra {_numero(sharpe_da_pessoa)} "
        "da sua configuração.",
    )


# --- Checagem 2: custos e imposto --------------------------------------------------------


IMPOSTO = "regras simplificadas da B3"  # `src/imposto.py`, usado em qualquer ativo


def custo_da_checagem(custo_por_operacao: float) -> float:
    """O custo usado pela ficha: o da pessoa, mas nunca abaixo do padrão do app (fração)."""
    return max(custo_por_operacao, CUSTO_PADRAO_POR_OPERACAO)


def retorno_liquido(
    fechamento: pd.Series,
    posicao_desejada: pd.Series,
    custo_por_operacao: float,
    capital_inicial: float,
) -> float:
    """Retorno total da regra depois dos custos e do imposto simplificado da B3 (fração)."""
    bruto = executar_backtest(fechamento, posicao_desejada, custo_por_operacao)
    liquido = aplicar_imposto(bruto, capital_inicial).resultado
    return float(liquido.curva_de_capital.iloc[-1] - 1)


def checar_custos_e_imposto(
    retorno_liquido_total: float, retorno_do_cdi: float | None
) -> Checagem:
    """Passa se, depois dos custos e do imposto, a regra rende mais que o CDI do mesmo período
    (sem o CDI, mais que zero). Os dois retornos são totais do período, em fração."""
    if retorno_do_cdi is None:
        return Checagem(
            PERGUNTA_CUSTOS,
            _situacao(retorno_liquido_total > 0),
            f"Depois dos custos e do imposto ({IMPOSTO}), a regra rendeu "
            f"{_porcentagem(retorno_liquido_total)}. Ficou sem o CDI para comparar, então a "
            "conta foi contra zero.",
        )
    return Checagem(
        PERGUNTA_CUSTOS,
        _situacao(retorno_liquido_total > retorno_do_cdi),
        f"Depois dos custos e do imposto ({IMPOSTO}), a regra rendeu "
        f"{_porcentagem(retorno_liquido_total)}; "
        f"o CDI rendeu {_porcentagem(retorno_do_cdi)} no mesmo período.",
    )


# --- Checagem 5: quedas ------------------------------------------------------------------


def queda_no_pior_caso_comum(
    retornos_das_operacoes: pd.Series, curva_de_capital: pd.Series
) -> tuple[float, str]:
    """A maior queda (negativa) que se deve esperar e de onde ela veio.

    Com operações suficientes, o pior caso comum do Monte Carlo (as operações em outra ordem);
    com poucas, a maior queda que de fato aconteceu.
    """
    if len(retornos_das_operacoes.dropna()) >= MIN_OPERACOES_PARA_MONTE_CARLO:
        resumo = resumir_monte_carlo(simular_monte_carlo(retornos_das_operacoes))
        return resumo.queda_p5, "no pior caso comum do Monte Carlo"
    real = float((curva_de_capital / curva_de_capital.cummax() - 1).min())
    return real, "na maior queda real (poucas operações para o Monte Carlo)"


def normalizar_tolerancia(guardada: object) -> float:
    """A tolerância de queda guardada na conta, ou o padrão se ela não for um número da faixa."""
    if isinstance(guardada, bool) or not isinstance(guardada, int | float):
        return TOLERANCIA_PADRAO_DE_QUEDA
    if not TOLERANCIA_MINIMA <= guardada <= TOLERANCIA_MAXIMA:
        return TOLERANCIA_PADRAO_DE_QUEDA
    return float(guardada)


def checar_quedas(queda: float, tolerancia: float, fonte: str) -> Checagem:
    """Passa se a queda (negativa) não passa da tolerância da pessoa (fração positiva)."""
    return Checagem(
        PERGUNTA_QUEDAS,
        _situacao(abs(queda) <= tolerancia),
        f"A queda chegou a {_queda(queda)} {fonte}; você disse aguentar até "
        f"{_queda(tolerancia)}.",
    )


# --- Checagem 3: acaso com as tentativas -------------------------------------------------


def total_de_tentativas(combinacoes_da_grade: int, tentativas_da_pessoa: int) -> int:
    """Variações que entram no desconto: as da grade da validação mais as que a pessoa testou.

    A configuração de agora já está entre as da pessoa e (na grade ou perto dela) entre as da
    grade; por isso conta uma vez só.
    """
    return max(combinacoes_da_grade, 1) + max(tentativas_da_pessoa - 1, 0)


def chance_de_nao_ser_sorte(
    retorno: pd.Series,
    variancia_dos_sharpes_diarios: float,
    tentativas: int,
    taxa_livre_de_risco: float = 0.0,
) -> float:
    """Chance de o Sharpe verdadeiro passar do melhor que `tentativas` regras sem valor dariam
    (o Sharpe deflacionado de Bailey e López de Prado, com a variância dada)."""
    referencia = calcular_sharpe_maximo_esperado(
        variancia_dos_sharpes_diarios, tentativas
    )
    return calcular_sharpe_probabilistico(retorno, referencia, taxa_livre_de_risco)


def checar_acaso(p_valor: float, chance: float, tentativas: int) -> Checagem:
    """Passa se o p-valor do teste contra o acaso é baixo e a chance de não ser sorte, com as
    tentativas descontadas, é alta (as duas em fração)."""
    passou = p_valor < P_VALOR_MAXIMO and chance >= CHANCE_MINIMA_DE_NAO_SER_SORTE
    return Checagem(
        PERGUNTA_ACASO,
        _situacao(passou),
        f"{_percentual(p_valor)} das versões ao acaso fizeram igual ou melhor. Contando "
        f"{tentativas} {'tentativa' if tentativas == 1 else 'tentativas'}, a chance de não "
        f"ser sorte é {_percentual(chance)}.",
    )


SEM_MOMENTO = (
    "A regra fica sempre na mesma posição (entra uma vez e não sai): não há momento de "
    "entrar e sair para comparar com o acaso."
)


def medir_acaso(
    fechamento: pd.Series,
    posicao_desejada: pd.Series,
    custo_por_operacao: float,
    taxa_livre_de_risco: float,
    combinacoes_da_grade: int,
    tentativas_da_pessoa: int,
) -> Checagem:
    """Roda o teste contra o acaso e o Sharpe deflacionado e devolve a checagem 3.

    A dispersão dos Sharpes "sem habilidade" vem das versões ao acaso da própria regra (a
    posição deslocada no tempo). Não vem da grade de parâmetros: quando várias combinações
    são boas de verdade, a dispersão entre elas não é sorte e puniria a regra boa.
    """
    if posicao_desejada.diff().abs().gt(0).sum() <= 1:
        return sem_medida(PERGUNTA_ACASO, SEM_MOMENTO)
    try:
        acaso = testar_contra_o_acaso(
            fechamento, posicao_desejada, custo_por_operacao, taxa_livre_de_risco
        )
    except ValueError as erro:
        return sem_medida(PERGUNTA_ACASO, str(erro))
    retorno = executar_backtest(
        fechamento, posicao_desejada, custo_por_operacao
    ).retorno
    tentativas = total_de_tentativas(combinacoes_da_grade, tentativas_da_pessoa)
    # os Sharpes do acaso são anuais: Sharpe anual ≈ diário × √252, variância ÷ 252
    variancia = float(np.var(acaso.sharpes_ao_acaso, ddof=1)) / DIAS_POR_ANO
    chance = chance_de_nao_ser_sorte(
        retorno, variancia, tentativas, taxa_livre_de_risco
    )
    if np.isnan(chance):
        return sem_medida(
            PERGUNTA_ACASO, "Os retornos não deixaram calcular o Sharpe deflacionado."
        )
    return checar_acaso(acaso.p_valor, chance, tentativas)


# --- A ficha inteira ---------------------------------------------------------------------


@dataclass(frozen=True)
class PedidoDaFicha:
    """Tudo o que a ficha precisa saber sobre o teste da pessoa."""

    dados: pd.DataFrame  # preços do ativo (Open, High, Low, Close, Volume)
    estrategia: str  # nome em `estrategias.ESTRATEGIAS`
    parametros: dict  # os valores escolhidos pela pessoa
    custo_por_operacao: float  # fração; a ficha nunca usa menos que o padrão
    capital_inicial: float  # R$, para a isenção do imposto
    protecoes: Protecoes | None = None
    # parâmetros que variam na grade; vazio = os 2 primeiros numéricos, como na tela
    livres: tuple[str, ...] = ()
    taxa_livre_de_risco: float = 0.0
    cdi_diario: pd.Series | None = None
    tolerancia_de_queda: float = TOLERANCIA_PADRAO_DE_QUEDA
    tentativas_da_pessoa: int = 1  # configurações diferentes já testadas neste ativo


@dataclass(frozen=True)
class _Grade:
    retornos: pd.DataFrame  # retorno diário de cada combinação (uma coluna cada)
    combinacoes: list[dict]
    livres: tuple[str, ...]


SEM_NUMEROS = "Esta regra não tem números para ajustar: não houve escolha a conferir."


def _montar_grade(pedido: PedidoDaFicha, custo: float) -> _Grade:
    """As combinações dos parâmetros livres, como na validação da tela (pode dar ValueError)."""
    livres = pedido.livres or tuple(
        p.nome for p in parametros_numericos(pedido.estrategia)[:2]
    )
    candidatos = montar_candidatos(pedido.estrategia, pedido.parametros, list(livres))
    retornos, validos = calcular_retornos_dos_candidatos(
        pedido.dados, pedido.estrategia, candidatos, custo, pedido.protecoes
    )
    return _Grade(retornos, validos, livres)


def _checar_fora(grade: _Grade, taxa: float) -> Checagem:
    try:
        wf = executar_walk_forward(
            grade.retornos, grade.combinacoes, DIAS_DE_TREINO, DIAS_DE_TESTE, taxa
        )
        return checar_fora_do_periodo(
            wf.sharpe_fora_da_amostra, wf.sharpe_medio_no_treino, "walk-forward"
        )
    except ValueError:
        pass  # pouco histórico para as janelas: tenta um corte só
    try:
        corte = data_de_corte(grade.retornos.index, FRACAO_DE_TREINO_PADRAO)
        tt = avaliar_treino_e_teste(grade.retornos, grade.combinacoes, corte, taxa)
    except ValueError as erro:
        return sem_medida(PERGUNTA_FORA_DO_PERIODO, str(erro))
    return checar_fora_do_periodo(
        tt.sharpe_no_teste, tt.sharpe_no_treino, "treino e teste"
    )


def _checar_vizinhos_da_grade(
    grade: _Grade, pedido: PedidoDaFicha, sharpe_da_pessoa: float
) -> Checagem:
    eixo_x = grade.livres[0]
    eixo_y = grade.livres[1] if len(grade.livres) > 1 else None
    mapa = montar_mapa_de_sharpe(
        grade.retornos,
        grade.combinacoes,
        eixo_x,
        eixo_y,
        pedido.taxa_livre_de_risco,
    )
    escolhido = (
        pedido.parametros[eixo_x],
        pedido.parametros[eixo_y] if eixo_y else "",
    )
    return checar_vizinhos(mapa, escolhido, sharpe_da_pessoa)


def _checar_custos(pedido: PedidoDaFicha, posicao: pd.Series, custo: float) -> Checagem:
    fechamento = pedido.dados["Close"]
    liquido = retorno_liquido(fechamento, posicao, custo, pedido.capital_inicial)
    cdi = None
    if pedido.cdi_diario is not None:
        cdi = float(curva_do_cdi(pedido.cdi_diario, fechamento.index).iloc[-1] - 1)
    return checar_custos_e_imposto(liquido, cdi)


def _checar_quedas_do(resultado: ResultadoBacktest, tolerancia: float) -> Checagem:
    if resultado.operacoes.empty:
        return sem_medida(PERGUNTA_QUEDAS, "A regra não fez nenhuma operação.")
    queda, fonte = queda_no_pior_caso_comum(
        resultado.operacoes["retorno"], resultado.curva_de_capital
    )
    return checar_quedas(queda, tolerancia, fonte)


def montar_ficha(pedido: PedidoDaFicha) -> Ficha:
    """As cinco checagens do teste da pessoa, com o custo nunca abaixo do padrão do app."""
    custo = custo_da_checagem(pedido.custo_por_operacao)
    fechamento = pedido.dados["Close"]
    posicao = gerar_posicao(pedido.estrategia, pedido.dados, **pedido.parametros)
    if pedido.protecoes is not None:
        posicao = aplicar_protecoes(pedido.dados, posicao, pedido.protecoes)
    resultado = executar_backtest(fechamento, posicao, custo)
    sharpe = calcular_indice_sharpe(resultado.retorno, pedido.taxa_livre_de_risco)

    grade: _Grade | None = None
    if not parametros_numericos(pedido.estrategia):
        fora = nao_se_aplica(PERGUNTA_FORA_DO_PERIODO, SEM_NUMEROS)
        vizinhanca = nao_se_aplica(PERGUNTA_VIZINHOS, SEM_NUMEROS)
    else:
        try:
            grade = _montar_grade(pedido, custo)
        except ValueError as erro:
            fora = sem_medida(PERGUNTA_FORA_DO_PERIODO, str(erro))
            vizinhanca = sem_medida(PERGUNTA_VIZINHOS, str(erro))
        else:
            fora = _checar_fora(grade, pedido.taxa_livre_de_risco)
            vizinhanca = _checar_vizinhos_da_grade(grade, pedido, sharpe)

    combinacoes = 0 if grade is None else len(grade.combinacoes)
    acaso = medir_acaso(
        fechamento,
        posicao,
        custo,
        pedido.taxa_livre_de_risco,
        combinacoes,
        pedido.tentativas_da_pessoa,
    )
    return Ficha(
        (
            fora,
            _checar_custos(pedido, posicao, custo),
            acaso,
            vizinhanca,
            _checar_quedas_do(resultado, pedido.tolerancia_de_queda),
        ),
        tentativas=total_de_tentativas(combinacoes, pedido.tentativas_da_pessoa),
    )
