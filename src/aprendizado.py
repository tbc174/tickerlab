"""Aprendizado de máquina honesto: o modelo precisa vencer uma previsão ingênua, sem olhar o futuro.

Peças (tudo em numpy e pandas, sem biblioteca de ML, para dar para ler):
- variáveis simples calculadas só com dados até o fechamento do dia;
- rótulos: "o próximo dia sobe?" e a barreira tripla (alvo, stop ou prazo, o que vier primeiro);
- regressão logística escrita à mão (Newton com penalidade L2); a padronização usa só o treino;
- treino com janela que expande, descartando do treino os exemplos cujo rótulo só se resolve
  depois do dia da previsão (expurgo);
- validação cruzada com expurgo e embargo, para quando os rótulos se sobrepõem no tempo;
- meta-rotulagem: uma regra simples decide a direção e o modelo decide se vale agir;
- previsão de volatilidade (modelo linear tipo HAR) contra a previsão "amanhã igual a hoje".

A lição mais comum: prever o sinal do dia seguinte fica perto do acaso; prever a volatilidade
funciona bem melhor, porque ela é persistente.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import indicadores as ind

NOMES_DAS_VARIAVEIS = (
    "Retorno de 1 dia",
    "Retorno de 5 dias",
    "Retorno de 21 dias",
    "Volatilidade de 5 dias",
    "Volatilidade de 20 dias",
    "Amplitude média (5 dias)",
    "Volume relativo",
    "Distância da média de 50 dias",
)


@dataclass(frozen=True)
class ConjuntoDeDados:
    """Variáveis e rótulos alinhados. `posicao` e `fim` são posições no índice de preços."""

    X: pd.DataFrame
    y: pd.Series
    posicao: np.ndarray  # posição do dia de cada exemplo
    fim: np.ndarray  # posição do dia em que o rótulo de cada exemplo se resolve


# --- variáveis ----------------------------------------------------------------------------


def montar_variaveis(dados: pd.DataFrame) -> pd.DataFrame:
    """Variáveis conhecidas no fechamento de cada dia (nada olha o futuro)."""
    fechamento = dados["Close"]
    retorno = fechamento.pct_change()
    variaveis = pd.DataFrame(index=dados.index)
    variaveis["Retorno de 1 dia"] = retorno
    variaveis["Retorno de 5 dias"] = fechamento.pct_change(5)
    variaveis["Retorno de 21 dias"] = fechamento.pct_change(21)
    variaveis["Volatilidade de 5 dias"] = retorno.rolling(5).std()
    variaveis["Volatilidade de 20 dias"] = retorno.rolling(20).std()
    if {"High", "Low"} <= set(dados.columns):
        amplitude = (dados["High"] - dados["Low"]) / fechamento
    else:
        amplitude = retorno.abs()
    variaveis["Amplitude média (5 dias)"] = amplitude.rolling(5).mean()
    if "Volume" in dados.columns and (dados["Volume"] > 0).mean() > 0.5:
        volume = dados["Volume"].replace(0, np.nan)
        variaveis["Volume relativo"] = volume / volume.rolling(20).mean() - 1
    else:
        variaveis["Volume relativo"] = 0.0  # sem volume (ex.: índices): coluna neutra
    variaveis["Distância da média de 50 dias"] = (
        fechamento / ind.calcular_media_movel(fechamento, 50) - 1
    )
    return variaveis[list(NOMES_DAS_VARIAVEIS)]


# --- rótulos ------------------------------------------------------------------------------


def _conjunto(
    variaveis: pd.DataFrame, rotulo: np.ndarray, fim: np.ndarray
) -> ConjuntoDeDados:
    valido = variaveis.notna().all(axis=1).to_numpy() & ~np.isnan(rotulo)
    posicoes = np.flatnonzero(valido)
    if len(posicoes) < 100:
        raise ValueError(
            "Poucos dias com histórico para treinar um modelo. Use um período maior."
        )
    return ConjuntoDeDados(
        X=variaveis.iloc[posicoes],
        y=pd.Series(rotulo[posicoes], index=variaveis.index[posicoes]),
        posicao=posicoes,
        fim=fim[posicoes].astype(int),
    )


def rotular_proximo_dia(dados: pd.DataFrame) -> ConjuntoDeDados:
    """Exemplo do dia t: 1 se o retorno do dia t+1 for positivo, 0 se não for."""
    fechamento = dados["Close"]
    proximo = fechamento.pct_change().shift(-1)
    rotulo = np.where(proximo.isna(), np.nan, (proximo > 0).astype(float))
    fim = np.arange(len(fechamento)) + 1
    return _conjunto(montar_variaveis(dados), rotulo, fim)


def calcular_barreira_tripla(
    fechamento: pd.Series, alvo: float, stop: float, prazo: int
) -> tuple[np.ndarray, np.ndarray]:
    """Para cada dia: 1 se o preço sobe `alvo` antes de cair `stop`; 0 se cai `stop` ou se o
    prazo acaba antes. Devolve também o dia em que cada rótulo se resolve.

    Conferido no fechamento. Dias cujo prazo ainda não terminou no fim dos dados ficam sem
    rótulo (NaN), porque o resultado ainda não é conhecido.
    """
    if not 0 < alvo < 1 or not 0 < stop < 1:
        raise ValueError(
            "Alvo e stop devem ficar entre 0 e 1 (por exemplo, 0,03 para 3%)."
        )
    if prazo < 1:
        raise ValueError("O prazo precisa ser de pelo menos 1 dia.")
    precos = fechamento.to_numpy(dtype=float)
    n = len(precos)
    rotulo = np.full(n, np.nan)
    fim = np.arange(n) + prazo
    for t in range(n - 1):
        janela = precos[t + 1 : t + 1 + prazo] / precos[t] - 1
        bateu_alvo = np.flatnonzero(janela >= alvo)
        bateu_stop = np.flatnonzero(janela <= -stop)
        primeiro_alvo = bateu_alvo[0] if len(bateu_alvo) else None
        primeiro_stop = bateu_stop[0] if len(bateu_stop) else None
        if primeiro_alvo is not None and (
            primeiro_stop is None or primeiro_alvo < primeiro_stop
        ):
            rotulo[t], fim[t] = 1.0, t + 1 + primeiro_alvo
        elif primeiro_stop is not None:
            rotulo[t], fim[t] = 0.0, t + 1 + primeiro_stop
        elif len(janela) == prazo:  # prazo completo sem tocar nenhuma barreira
            rotulo[t], fim[t] = 0.0, t + prazo
    return rotulo, fim


def rotular_barreira_tripla(
    dados: pd.DataFrame, alvo: float = 0.03, stop: float = 0.03, prazo: int = 10
) -> ConjuntoDeDados:
    rotulo, fim = calcular_barreira_tripla(dados["Close"], alvo, stop, prazo)
    return _conjunto(montar_variaveis(dados), rotulo, fim)


# --- modelo -------------------------------------------------------------------------------


def _sigmoide(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


class RegressaoLogistica:
    """Regressão logística com penalidade L2, ajustada pelo método de Newton."""

    def __init__(self, l2: float = 1.0, iteracoes: int = 30) -> None:
        if l2 <= 0:
            raise ValueError("A penalidade L2 precisa ser maior que zero.")
        self.l2 = l2
        self.iteracoes = iteracoes
        self.media = None
        self.desvio = None
        self.pesos = None

    def _padronizar(self, X: np.ndarray) -> np.ndarray:
        # a média e o desvio vêm só do treino
        Z = (X - self.media) / self.desvio
        return np.column_stack([np.ones(len(Z)), Z])

    def ajustar(self, X: np.ndarray, y: np.ndarray) -> "RegressaoLogistica":
        if len(X) != len(y) or len(X) < 2:
            raise ValueError("São necessários pelo menos 2 exemplos para ajustar.")
        self.media = X.mean(axis=0)
        self.desvio = np.where(X.std(axis=0) > 0, X.std(axis=0), 1.0)
        A = self._padronizar(X)
        penalidade = self.l2 * np.eye(A.shape[1])
        penalidade[0, 0] = 0.0  # o intercepto não é penalizado
        w = np.zeros(A.shape[1])
        for _ in range(self.iteracoes):
            p = _sigmoide(A @ w)
            gradiente = A.T @ (y - p) - penalidade @ w
            hessiana = (A * (p * (1 - p))[:, None]).T @ A + penalidade
            passo = np.linalg.solve(hessiana + 1e-9 * np.eye(len(w)), gradiente)
            w = w + passo
            if np.max(np.abs(passo)) < 1e-8:
                break
        self.pesos = w
        return self

    def prever_probabilidade(self, X: np.ndarray) -> np.ndarray:
        if self.pesos is None:
            raise ValueError("Ajuste o modelo antes de prever.")
        return _sigmoide(self._padronizar(X) @ self.pesos)


# --- treino com janela que expande --------------------------------------------------------


def prever_fora_da_amostra(
    conjunto: ConjuntoDeDados,
    minimo_de_treino: int = 504,
    passo: int = 63,
    l2: float = 1.0,
    mascara: np.ndarray | None = None,
) -> pd.DataFrame:
    """Probabilidades previstas só com o passado, em blocos de `passo` dias.

    Para prever o bloco que começa no dia s, o modelo treina com os exemplos anteriores cujo
    rótulo já estava resolvido antes de s (o resto é expurgado: seu rótulo ainda dependia do
    futuro). Com `mascara`, treina e prevê só nos exemplos marcados (meta-rotulagem).
    Colunas: `p` (modelo) e `p_ingenua` (fração de 1 no treino). NaN onde não houve previsão.
    """
    n = len(conjunto.y)
    if minimo_de_treino < 50 or passo < 1:
        raise ValueError("O treino mínimo é de 50 exemplos e o passo, de 1 dia.")
    if n <= minimo_de_treino:
        raise ValueError(
            "O histórico é curto demais para treinar e testar. Use um período maior."
        )
    usar = (
        np.ones(n, dtype=bool) if mascara is None else np.asarray(mascara, dtype=bool)
    )
    X = conjunto.X.to_numpy(dtype=float)
    y = conjunto.y.to_numpy(dtype=float)
    saida = pd.DataFrame(np.nan, index=conjunto.y.index, columns=["p", "p_ingenua"])
    for inicio in range(minimo_de_treino, n, passo):
        fim_do_bloco = min(inicio + passo, n)
        dia_da_previsao = conjunto.posicao[inicio]
        treino = np.flatnonzero(
            (np.arange(n) < inicio) & (conjunto.fim < dia_da_previsao) & usar
        )
        alvo = np.arange(inicio, fim_do_bloco)
        alvo = alvo[usar[alvo]]
        if len(treino) < 30 or len(alvo) == 0:
            continue
        taxa = y[treino].mean()
        saida.iloc[alvo, 1] = taxa
        if len(np.unique(y[treino])) < 2:
            saida.iloc[alvo, 0] = taxa
            continue
        modelo = RegressaoLogistica(l2).ajustar(X[treino], y[treino])
        saida.iloc[alvo, 0] = modelo.prever_probabilidade(X[alvo])
    return saida


def calcular_auc(y: np.ndarray, p: np.ndarray) -> float:
    """Área sob a curva ROC: chance de um exemplo positivo receber nota maior que um negativo."""
    y = np.asarray(y, dtype=float)
    positivos = y == 1
    n_pos, n_neg = positivos.sum(), (~positivos).sum()
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    postos = pd.Series(p).rank().to_numpy()
    return float((postos[positivos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def avaliar_previsoes(
    y: pd.Series, previsoes: pd.DataFrame, limiar: float = 0.5
) -> dict[str, float]:
    """Compara o modelo com a previsão ingênua (sempre a classe mais comum do treino)."""
    valido = previsoes["p"].notna()
    if valido.sum() < 30:
        raise ValueError("Há poucas previsões para avaliar.")
    rotulo = y[valido].to_numpy(dtype=float)
    p = previsoes.loc[valido, "p"].to_numpy()
    p0 = previsoes.loc[valido, "p_ingenua"].to_numpy()
    n = len(rotulo)
    acuracia = float(((p > limiar) == (rotulo == 1)).mean())
    acuracia_ingenua = float(((p0 > 0.5) == (rotulo == 1)).mean())
    erro_padrao = float(np.sqrt(0.25 / n))
    return {
        "Previsões": n,
        "Acurácia do modelo": acuracia,
        "Acurácia ingênua": acuracia_ingenua,
        "Diferença em erros-padrão": (acuracia - acuracia_ingenua) / erro_padrao,
        "AUC": calcular_auc(rotulo, p),
        "Brier do modelo": float(np.mean((p - rotulo) ** 2)),
        "Brier ingênuo": float(np.mean((p0 - rotulo) ** 2)),
        "Fração de 1": float(rotulo.mean()),
    }


def posicao_a_partir_das_probabilidades(
    probabilidade: pd.Series, indice: pd.Index, limiar: float = 0.5
) -> pd.Series:
    """Compra no fechamento do dia se a probabilidade passa do limiar; senão, caixa."""
    if not 0 < limiar < 1:
        raise ValueError("O limiar deve ficar entre 0 e 1.")
    posicao = (probabilidade > limiar).astype(float).reindex(indice).fillna(0.0)
    return posicao


# --- validação cruzada com expurgo e embargo ----------------------------------------------


def dividir_com_expurgo(
    conjunto: ConjuntoDeDados, k: int = 5, embargo: int = 5, expurgar: bool = True
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Gera (treino, teste) em `k` blocos contínuos.

    Com `expurgar`, sai do treino todo exemplo cujo intervalo (do dia até a resolução do
    rótulo) encosta no bloco de teste, e também os `embargo` dias logo depois do teste.
    Sem ele, é o k-fold comum, que deixa o futuro vazar para o treino.
    """
    n = len(conjunto.y)
    if k < 2 or k > n // 20:
        raise ValueError("Use pelo menos 2 blocos, com ao menos 20 exemplos em cada.")
    if embargo < 0:
        raise ValueError("O embargo não pode ser negativo.")
    blocos = np.array_split(np.arange(n), k)
    for teste in blocos:
        primeiro, ultimo = conjunto.posicao[teste[0]], conjunto.posicao[teste[-1]]
        treino = np.setdiff1d(np.arange(n), teste)
        if expurgar:
            sobrepoe = (conjunto.posicao[treino] <= ultimo) & (
                conjunto.fim[treino] >= primeiro
            )
            no_embargo = (conjunto.posicao[treino] > ultimo) & (
                conjunto.posicao[treino] <= ultimo + embargo
            )
            treino = treino[~sobrepoe & ~no_embargo]
        yield treino, teste


def validar_com_expurgo(
    conjunto: ConjuntoDeDados,
    k: int = 5,
    embargo: int = 5,
    expurgar: bool = True,
    l2: float = 1.0,
) -> dict[str, float]:
    """Acurácia e AUC fora da amostra em validação cruzada (com ou sem expurgo)."""
    X = conjunto.X.to_numpy(dtype=float)
    y = conjunto.y.to_numpy(dtype=float)
    p = np.full(len(y), np.nan)
    p0 = np.full(len(y), np.nan)
    for treino, teste in dividir_com_expurgo(conjunto, k, embargo, expurgar):
        if len(treino) < 30 or len(np.unique(y[treino])) < 2:
            continue
        modelo = RegressaoLogistica(l2).ajustar(X[treino], y[treino])
        p[teste] = modelo.prever_probabilidade(X[teste])
        p0[teste] = y[treino].mean()
    avaliado = ~np.isnan(p)
    if avaliado.sum() < 30:
        raise ValueError("Há poucas previsões para avaliar.")
    return {
        "Acurácia do modelo": float(((p[avaliado] > 0.5) == (y[avaliado] == 1)).mean()),
        "Acurácia ingênua": float(((p0[avaliado] > 0.5) == (y[avaliado] == 1)).mean()),
        "AUC": calcular_auc(y[avaliado], p[avaliado]),
    }


# --- previsão de volatilidade -------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoDaVolatilidade:
    prevista: pd.Series  # volatilidade anual prevista para os próximos `horizonte` dias
    ingenua: pd.Series  # "os próximos dias serão como os últimos 20"
    realizada: pd.Series  # volatilidade anual que de fato veio
    metricas: dict[str, float]


def prever_volatilidade(
    dados: pd.DataFrame,
    horizonte: int = 21,
    minimo_de_treino: int = 504,
    passo: int = 63,
) -> ResultadoDaVolatilidade:
    """Regressão linear (estilo HAR) do log da volatilidade futura nas volatilidades passadas."""
    if horizonte < 2:
        raise ValueError("O horizonte precisa ter pelo menos 2 dias.")
    retorno = dados["Close"].pct_change()
    # volatilidade que vem nos próximos `horizonte` dias, anualizada
    realizada = retorno[::-1].rolling(horizonte).std()[::-1].shift(-1) * np.sqrt(
        ind.DIAS_POR_ANO
    )
    v5 = retorno.rolling(5).std()
    v20 = retorno.rolling(20).std()
    v60 = retorno.rolling(60).std()
    variaveis = np.log(pd.concat([v5, v20, v60], axis=1).replace(0, np.nan))
    variaveis.columns = ["v5", "v20", "v60"]
    alvo = np.log(realizada.replace(0, np.nan))
    tabela = pd.concat([variaveis, alvo.rename("alvo")], axis=1).dropna()
    n = len(tabela)
    if n <= minimo_de_treino + passo:
        raise ValueError(
            "O histórico é curto demais para treinar e testar. Use um período maior."
        )
    posicoes = dados.index.get_indexer(tabela.index)
    fim = posicoes + horizonte
    A = np.column_stack([np.ones(n), tabela[["v5", "v20", "v60"]].to_numpy()])
    y = tabela["alvo"].to_numpy()
    previsto = np.full(n, np.nan)
    for inicio in range(minimo_de_treino, n, passo):
        treino = np.flatnonzero((np.arange(n) < inicio) & (fim < posicoes[inicio]))
        bloco = np.arange(inicio, min(inicio + passo, n))
        if len(treino) < 50:
            continue
        coef, *_ = np.linalg.lstsq(A[treino], y[treino], rcond=None)
        previsto[bloco] = A[bloco] @ coef
    ok = ~np.isnan(previsto)
    fator = np.sqrt(ind.DIAS_POR_ANO)
    prevista = pd.Series(np.exp(previsto), index=tabela.index)[ok]
    ingenua = pd.Series(np.exp(tabela["v20"].to_numpy()) * fator, index=tabela.index)[
        ok
    ]
    real = pd.Series(np.exp(y), index=tabela.index)[ok]
    erro_modelo = np.log(prevista) - np.log(real)
    erro_ingenuo = np.log(ingenua) - np.log(real)
    mse_modelo, mse_ingenuo = (
        float((erro_modelo**2).mean()),
        float((erro_ingenuo**2).mean()),
    )
    metricas = {
        "Previsões": int(ok.sum()),
        "Erro do modelo (log)": float(np.sqrt(mse_modelo)),
        "Erro ingênuo (log)": float(np.sqrt(mse_ingenuo)),
        "Melhora sobre o ingênuo": 1 - mse_modelo / mse_ingenuo,
        "Correlação do modelo": float(np.corrcoef(prevista, real)[0, 1]),
        "Correlação ingênua": float(np.corrcoef(ingenua, real)[0, 1]),
    }
    return ResultadoDaVolatilidade(prevista, ingenua, real, metricas)


def posicao_pelo_alvo_de_volatilidade(
    volatilidade_anual: pd.Series, indice: pd.Index, alvo: float
) -> pd.Series:
    """Posição = alvo ÷ volatilidade esperada, no máximo 1 (sem alavancagem); sem dado, caixa."""
    if alvo <= 0:
        raise ValueError("O alvo de volatilidade deve ser maior que zero.")
    posicao = (alvo / volatilidade_anual).clip(upper=1.0)
    return posicao.reindex(indice).fillna(0.0)
