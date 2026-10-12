"""Grava os valores "golden" dos cálculos de estratégia: `tests/arquivos/golden_calculos.json`.

    python -m scripts.gerar_golden_calculos

São os números de hoje das telas de Estratégias, Carteira, teste contra o acaso e aprendizado de
máquina, calculados com os dados de exemplo do projeto e pelas mesmas funções que a tela chama.
O teste `tests/test_golden_calculos.py` recalcula e compara: se um número mudar sem querer (numa
refatoração, numa troca de biblioteca), o teste falha. Rodar este script **só** depois de mudar
um cálculo de propósito, e explicar a mudança no PR (o diff do JSON mostra o que mudou).

Complementa o `golden_analise.json` (indicadores da análise do ativo e do Research).
"""

import json
import math
from pathlib import Path

from scripts.gerar_golden_analise import dados
from src import aprendizado
from src.acaso import testar_contra_o_acaso
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest
from src.carteiras import ESTRATEGIAS_DE_CARTEIRA, simular_carteira
from src.comparacao import alinhar_fechamentos
from src.estrategias import ESTRATEGIAS, gerar_posicao
from src.metricas import resumir_desempenho

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "tests" / "arquivos" / "golden_calculos.json"
ATIVOS_DAS_ESTRATEGIAS = ("PETR4.SA", "AAPL")
CARTEIRA_DE_EXEMPLO = (
    "PETR4.SA",
    "VALE3.SA",
    "ITUB4.SA",
    "BBDC4.SA",
    "ABEV3.SA",
    "WEGE3.SA",
)
ESTRATEGIAS_DO_ACASO = ("Cruzamento de médias", "Momentum 12-1")
ATIVO_DO_APRENDIZADO = "PETR4.SA"
LIMIAR_DO_APRENDIZADO = 0.5


def _numeros(valores: dict) -> dict[str, float | None]:
    """Só números, com NaN e infinito trocados por None (o JSON não os aceita)."""
    return {
        chave: None if not math.isfinite(float(valor)) else float(valor)
        for chave, valor in valores.items()
    }


def estrategias() -> dict[str, dict]:
    """Cada estratégia com os parâmetros padrão e o custo padrão, como a tela abre."""
    resultado = {}
    for ticker in ATIVOS_DAS_ESTRATEGIAS:
        tabela = dados(ticker)
        for nome in ESTRATEGIAS:
            backtest = executar_backtest(
                tabela["Close"], gerar_posicao(nome, tabela), CUSTO_PADRAO_POR_OPERACAO
            )
            resumo = resumir_desempenho(
                backtest.retorno, backtest.posicao, backtest.operacoes
            )
            resultado[f"{ticker} | {nome}"] = _numeros(
                {**resumo, "Giro": backtest.giro}
            )
    return resultado


def carteiras() -> dict[str, dict]:
    """Cada estratégia de carteira com os parâmetros padrão, na carteira de exemplo da B3."""
    alinhado, _ = alinhar_fechamentos(
        {ticker: dados(ticker)["Close"] for ticker in CARTEIRA_DE_EXEMPLO}
    )
    resultado = {}
    for nome in ESTRATEGIAS_DE_CARTEIRA:
        carteira = simular_carteira(nome, alinhado, CUSTO_PADRAO_POR_OPERACAO)
        resumo = resumir_desempenho(carteira.retorno, carteira.exposicao)
        resultado[nome] = _numeros({**resumo, "Giro": carteira.giro})
    return resultado


def acaso() -> dict[str, dict]:
    """O teste contra o acaso (semente fixa) de duas estratégias em PETR4."""
    tabela = dados(ATIVOS_DAS_ESTRATEGIAS[0])
    resultado = {}
    for nome in ESTRATEGIAS_DO_ACASO:
        teste = testar_contra_o_acaso(
            tabela["Close"], gerar_posicao(nome, tabela), CUSTO_PADRAO_POR_OPERACAO
        )
        resultado[nome] = _numeros(
            {"Sharpe real": teste.sharpe_real, "p-valor": teste.p_valor}
        )
    return resultado


def aprendizado_de_maquina() -> dict[str, dict]:
    """O modelo do sinal do dia (treino que expande, só com o passado), como na tela."""
    tabela = dados(ATIVO_DO_APRENDIZADO)
    conjunto = aprendizado.rotular_proximo_dia(tabela)
    previsoes = aprendizado.prever_fora_da_amostra(conjunto)
    avaliacao = aprendizado.avaliar_previsoes(
        conjunto.y, previsoes, LIMIAR_DO_APRENDIZADO
    )
    posicao = aprendizado.posicao_a_partir_das_probabilidades(
        previsoes["p"], tabela.index, LIMIAR_DO_APRENDIZADO
    )
    inicio = previsoes["p"].first_valid_index()
    teste = tabela["Close"].loc[inicio:]
    backtest = executar_backtest(teste, posicao.loc[inicio:], CUSTO_PADRAO_POR_OPERACAO)
    return {
        "avaliacao": _numeros(avaliacao),
        "backtest": _numeros(resumir_desempenho(backtest.retorno, backtest.posicao)),
    }


def calcular() -> dict:
    return {
        "estrategias": estrategias(),
        "carteiras": carteiras(),
        "acaso": acaso(),
        "aprendizado": aprendizado_de_maquina(),
    }


def main() -> None:
    DESTINO.write_text(
        json.dumps(calcular(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"golden gravado em {DESTINO}")


if __name__ == "__main__":
    main()
