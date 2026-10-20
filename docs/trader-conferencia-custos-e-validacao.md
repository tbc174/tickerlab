# Trader: conferência da biblioteca, dos custos e da validação

Comparação do `trader/` com o projeto aberto Vibe-Trading (licença MIT), feita em 20/10/2026 para
trazer as ideias úteis sem copiar código. Nada aqui muda o critério da M2
(`docs/pre-registro-m2-v0.4.md`, selado em `trader/holdout.py`): o que for adotado entra pelo próximo
pré-registro, antes de ver resultado.

## Biblioteca quantitativa

A `quantlib` deles junta fórmulas testadas por família. A tabela diz o que cada família tem, onde o
mesmo já existe aqui e o que se fez com o que falta.

| Família (deles) | O que tem | Aqui | Decisão |
|---|---|---|---|
| Desempenho (`performance`) | retorno ponderado no tempo e pelo dinheiro, Dietz, TIR | `src/metricas.py` (retorno total, curva) | Não precisa: a pesquisa não tem aportes nem resgates |
| Risco (`risk`) | VaR histórico e paramétrico, CVaR, série de quedas, úlcera, índice de dor, duração das quedas, Monte Carlo GBM, cauda GPD | maior queda (`trader/avaliacao.py`); úlcera e duração da queda (`src/metricas.py`) | **Novo:** `var_historico` e `cvar_historico` (`trader/quant.py`). VaR paramétrico e GPD ficam de fora: supõem uma distribuição, e a pesquisa mede a cauda que aconteceu |
| Testes múltiplos (`multipletesting`) | Sharpe, PSR, Sharpe máximo esperado, DSR, Benjamini-Hochberg, PBO | PSR, comprimento mínimo, Sharpe máximo esperado, DSR e PBO (`src/acaso.py`); DSR no critério (A1) | **Novo:** `benjamini_hochberg` e `p_ajustados_bh` (`trader/quant.py`), para quando um catálogo de fatores for testado de uma vez |
| Teste do VaR (`var_backtest`) | Kupiec, Christoffersen, semáforo de Basileia | — | Só faz sentido se o VaR virar regra de tamanho de posição; fica para quando isso for proposto |
| Validação cruzada (`crossvalidation`) | k-fold com expurgo, por grupo, walk-forward, CPCV, detector de vazamento na borda | CPCV com expurgo e embargo (pipeline da M2), walk-forward (`src/validacao.py`), conferência de vazamento (`trader/vazamento.py`) | Já coberto; o k-fold por grupo é discutido na seção de validação |
| Séries temporais (`timeseries`) | ADF, cointegração, meia-vida, OU, Granger, GARCH, Markov, testes de resíduo, bootstrap do Sharpe | bootstrap em blocos da diferença de Sharpe (`trader/validacao.py`), ARIMA (`trader/arima.py`) | Não entra agora: serve a estratégias de reversão (pares) e regimes, que não estão na fila |
| Volatilidade (`volatility`) | Heston | — | Não serve: é apreçamento de opções |
| Carteira (`portfolio`) | HRP e pesos pelo inverso da variância | pesos iguais por grupo (`trader/avaliacao.py`) | Fica para a M3, se ela tiver mais de um ativo por classe |
| Atribuição (`attribution`) | Brinson, Carino | `participacao_por_ativo` (`trader/avaliacao.py`) | Não precisa: a pesquisa não tem um índice de referência a bater |

As duas funções novas têm exemplo calculado à mão e teste de propriedade (`tests/test_trader_quant.py`):
o CVaR nunca é menor que o VaR, os dois crescem na mesma proporção da posição e caem na medida exata de
um ganho fixo, e o BH aprova pelo menos o que Bonferroni aprova, sempre as menores primeiro.
