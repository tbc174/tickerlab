"""Validação do backtest: separa o que foi *ajustado* ao passado do que se sustenta fora dele.

Três ferramentas:
- treino/teste: escolhe os parâmetros num pedaço dos dados e confere no pedaço seguinte;
- walk-forward: repete isso várias vezes, andando no tempo, e junta só os resultados "de fora";
- mapa de parâmetros: mostra o Sharpe de uma grade de valores. Um pico isolado é sorte; uma
  região grande e suave é sinal de robustez.

Os sinais são calculados UMA vez sobre todos os dados: como nenhuma estratégia olha o futuro
(há testes para isso), a posição de um dia só depende do passado, e cortar o resultado por
datas depois é seguro. Assim os indicadores já chegam "aquecidos" ao começo do teste.
"""

from collections.abc import Hashable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import indicadores as ind
from src.backtest import executar_backtest
from src.estrategias import ESTRATEGIAS, Parametro, gerar_posicao
from src.protecoes import Protecoes, aplicar_protecoes

VALORES_POR_PARAMETRO = 7  # tamanho de cada lado da grade
MIN_DIAS_NA_JANELA = (
    30  # com menos retornos que isso o Sharpe de uma janela não diz nada
)
FRACAO_DE_TREINO_PADRAO = 0.7


# --- Grade de candidatos -----------------------------------------------------------------


def valores_do_parametro(
    parametro: Parametro, quantidade: int = VALORES_POR_PARAMETRO
) -> list[float | str]:
    """Valores espalhados entre o mínimo e o máximo do parâmetro, incluindo o padrão."""
    if parametro.opcoes:
        return list(parametro.opcoes)
    bruto = np.linspace(parametro.minimo, parametro.maximo, quantidade)
    passo = parametro.passo
    valores = {round(round(v / passo) * passo, 10) for v in bruto}
    valores.add(parametro.padrao)
    if all(isinstance(x, int) for x in (parametro.minimo, parametro.maximo, passo)):
        return sorted(int(v) for v in valores)
    return sorted(valores)


def parametros_numericos(nome_da_estrategia: str) -> list[Parametro]:
    """Os parâmetros que podem variar na grade (os de escolha ficam fixos)."""
    return [p for p in ESTRATEGIAS[nome_da_estrategia].parametros if not p.opcoes]


def montar_candidatos(
    nome_da_estrategia: str, valores_atuais: dict, livres: list[str]
) -> list[dict]:
    """Todas as combinações dos parâmetros `livres`; os demais ficam nos valores atuais."""
    por_nome = {p.nome: p for p in ESTRATEGIAS[nome_da_estrategia].parametros}
    desconhecidos = set(livres) - set(por_nome)
    if desconhecidos:
        raise ValueError(f"Parâmetros desconhecidos: {sorted(desconhecidos)}.")
    candidatos = [dict(valores_atuais)]
    for nome in livres:
        candidatos = [
            {**candidato, nome: valor}
            for candidato in candidatos
            for valor in valores_do_parametro(por_nome[nome])
        ]
    return candidatos


def calcular_retornos_dos_candidatos(
    dados: pd.DataFrame,
    nome_da_estrategia: str,
    candidatos: list[dict],
    custo_por_operacao: float,
    protecoes: Protecoes | None = None,
) -> tuple[pd.DataFrame, list[dict]]:
    """Retorno diário de cada candidato (uma coluna cada). Combinações inválidas são puladas.

    Devolve a tabela e a lista dos candidatos que valeram, na ordem das colunas.
    """
    colunas, validos = {}, []
    for candidato in candidatos:
        try:
            posicao = gerar_posicao(nome_da_estrategia, dados, **candidato)
            if protecoes is not None:
                posicao = aplicar_protecoes(dados, posicao, protecoes)
        except ValueError:
            continue  # por exemplo, média curta maior que a longa
        resultado = executar_backtest(dados["Close"], posicao, custo_por_operacao)
        colunas[len(validos)] = resultado.retorno
        validos.append(candidato)
    if not colunas:
        raise ValueError("Nenhuma combinação de parâmetros foi válida.")
    return pd.DataFrame(colunas), validos


# --- Sharpe e escolha do melhor ----------------------------------------------------------


def sharpe_de_cada_coluna(
    retornos: pd.DataFrame, taxa_livre_de_risco: float = 0.0
) -> pd.Series:
    """Sharpe anualizado de cada candidato (vazio quando não dá para calcular)."""
    return retornos.apply(
        lambda coluna: ind.calcular_indice_sharpe(coluna, taxa_livre_de_risco)
    )


def escolher_o_melhor(
    retornos: pd.DataFrame, taxa_livre_de_risco: float = 0.0
) -> tuple[int, float] | None:
    """Coluna de maior Sharpe e o valor dele; `None` se nenhuma tiver Sharpe calculável."""
    sharpes = sharpe_de_cada_coluna(retornos, taxa_livre_de_risco).dropna()
    if sharpes.empty:
        return None
    melhor = sharpes.idxmax()
    return int(melhor), float(sharpes[melhor])


# --- Treino e teste ----------------------------------------------------------------------


def data_de_corte(indice: pd.DatetimeIndex, fracao_de_treino: float) -> pd.Timestamp:
    """Primeiro dia do teste: o treino ocupa a fração inicial dos dias, em ordem cronológica."""
    if not 0.1 <= fracao_de_treino <= 0.9:
        raise ValueError("A fração de treino deve ficar entre 10% e 90%.")
    posicao = int(len(indice) * fracao_de_treino)
    if posicao < MIN_DIAS_NA_JANELA or len(indice) - posicao < MIN_DIAS_NA_JANELA:
        raise ValueError(
            f"Poucos dados: treino e teste precisam de pelo menos {MIN_DIAS_NA_JANELA} dias cada."
        )
    return indice[posicao]


@dataclass(frozen=True)
class ResultadoTreinoTeste:
    corte: pd.Timestamp
    melhor_do_treino: dict  # parâmetros que deram o maior Sharpe no treino
    sharpe_no_treino: float  # Sharpe desse melhor candidato no treino (o "bonito")
    sharpe_no_teste: float  # o mesmo candidato no teste (o "de verdade")
    retorno_no_treino: pd.Series
    retorno_no_teste: pd.Series


def avaliar_treino_e_teste(
    retornos: pd.DataFrame,
    candidatos: list[dict],
    corte: pd.Timestamp,
    taxa_livre_de_risco: float = 0.0,
) -> ResultadoTreinoTeste:
    """Escolhe o melhor candidato SÓ com o treino e mede esse mesmo candidato no teste."""
    treino = retornos.loc[retornos.index < corte]
    teste = retornos.loc[retornos.index >= corte]
    if len(treino) < MIN_DIAS_NA_JANELA or len(teste) < MIN_DIAS_NA_JANELA:
        raise ValueError("Treino e teste precisam de mais dias.")
    escolha = escolher_o_melhor(treino, taxa_livre_de_risco)
    if escolha is None:
        raise ValueError("Nenhum candidato operou no treino: não há o que escolher.")
    coluna, sharpe_treino = escolha
    sharpe_teste = ind.calcular_indice_sharpe(teste[coluna], taxa_livre_de_risco)
    return ResultadoTreinoTeste(
        corte=corte,
        melhor_do_treino=candidatos[coluna],
        sharpe_no_treino=sharpe_treino,
        sharpe_no_teste=float(sharpe_teste),
        retorno_no_treino=treino[coluna],
        retorno_no_teste=teste[coluna],
    )


# --- Walk-forward ------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoWalkForward:
    janelas: (
        pd.DataFrame
    )  # uma linha por janela: datas, parâmetros escolhidos e Sharpes
    retorno_fora_da_amostra: pd.Series  # só os dias de teste, emendados em ordem
    sharpe_fora_da_amostra: float
    sharpe_medio_no_treino: float

    @property
    def eficiencia(self) -> float:
        """Sharpe de fora dividido pelo médio de dentro: perto de 1 = o ajuste se sustentou."""
        if np.isnan(self.sharpe_medio_no_treino) or self.sharpe_medio_no_treino <= 0:
            return float("nan")
        return self.sharpe_fora_da_amostra / self.sharpe_medio_no_treino


def executar_walk_forward(
    retornos: pd.DataFrame,
    candidatos: list[dict],
    dias_de_treino: int,
    dias_de_teste: int,
    taxa_livre_de_risco: float = 0.0,
) -> ResultadoWalkForward:
    """Anda no tempo: treina em `dias_de_treino`, opera `dias_de_teste`, e repete a partir dali.

    Em cada janela o candidato é escolhido SÓ com o treino; o teste nunca entra na escolha.
    As janelas de teste não se sobrepõem, então os retornos de fora emendam sem repetição.
    """
    if dias_de_treino < MIN_DIAS_NA_JANELA or dias_de_teste < MIN_DIAS_NA_JANELA:
        raise ValueError(
            f"Cada janela precisa de pelo menos {MIN_DIAS_NA_JANELA} dias."
        )
    linhas, pedacos = [], []
    inicio = 0
    while inicio + dias_de_treino + dias_de_teste <= len(retornos):
        meio = inicio + dias_de_treino
        fim = meio + dias_de_teste
        treino = retornos.iloc[inicio:meio]
        teste = retornos.iloc[meio:fim]
        escolha = escolher_o_melhor(treino, taxa_livre_de_risco)
        if escolha is None:  # ninguém operou neste treino: a janela fica em caixa
            candidato, sharpe_treino, sharpe_teste = {}, np.nan, np.nan
            pedacos.append(pd.Series(0.0, index=teste.index))
        else:
            coluna, sharpe_treino = escolha
            candidato = candidatos[coluna]
            sharpe_teste = ind.calcular_indice_sharpe(
                teste[coluna], taxa_livre_de_risco
            )
            pedacos.append(teste[coluna])
        linhas.append(
            {
                "Começo do treino": treino.index[0],
                "Começo do teste": teste.index[0],
                "Fim do teste": teste.index[-1],
                "Parâmetros escolhidos": candidato,
                "Sharpe no treino": sharpe_treino,
                "Sharpe no teste": sharpe_teste,
            }
        )
        inicio += dias_de_teste
    if not linhas:
        raise ValueError(
            "Não há dados para nenhuma janela completa: encurte o treino ou o teste, "
            "ou escolha um período maior."
        )
    janelas = pd.DataFrame(linhas)
    fora = pd.concat(pedacos)
    return ResultadoWalkForward(
        janelas=janelas,
        retorno_fora_da_amostra=fora,
        sharpe_fora_da_amostra=float(
            ind.calcular_indice_sharpe(fora, taxa_livre_de_risco)
        ),
        sharpe_medio_no_treino=float(janelas["Sharpe no treino"].mean()),
    )


# --- Mapa de parâmetros ------------------------------------------------------------------


def montar_mapa_de_sharpe(
    retornos: pd.DataFrame,
    candidatos: list[dict],
    eixo_x: str,
    eixo_y: str | None = None,
    taxa_livre_de_risco: float = 0.0,
) -> pd.DataFrame:
    """Tabela de Sharpe: colunas = valores de `eixo_x`, linhas = valores de `eixo_y`.

    Com um só parâmetro livre (`eixo_y=None`) sai uma única linha.
    """
    sharpes = sharpe_de_cada_coluna(retornos, taxa_livre_de_risco)
    tabela = pd.DataFrame(
        {
            "x": [c[eixo_x] for c in candidatos],
            "y": [c[eixo_y] if eixo_y else "" for c in candidatos],
            "sharpe": sharpes.to_numpy(),
        }
    )
    return tabela.pivot_table(index="y", columns="x", values="sharpe")


@dataclass(frozen=True)
class ResumoDaGrade:
    mediana: float
    melhor: float
    fracao_positiva: float  # fatia das combinações com Sharpe acima de zero


def resumir_grade(mapa: pd.DataFrame) -> ResumoDaGrade | None:
    """Mediana, melhor e fatia positiva do Sharpe nas combinações da grade (None se vazia)."""
    valores = pd.Series(mapa.to_numpy(dtype=float).ravel()).dropna()
    if valores.empty:
        return None
    return ResumoDaGrade(
        mediana=float(valores.median()),
        melhor=float(valores.max()),
        fracao_positiva=float((valores > 0).mean()),
    )


def melhor_candidato(retornos: pd.DataFrame, taxa_livre_de_risco: float) -> Hashable:
    """A coluna (candidato) com o maior Sharpe."""
    return retornos.apply(
        lambda r: ind.calcular_indice_sharpe(r, taxa_livre_de_risco)
    ).idxmax()
