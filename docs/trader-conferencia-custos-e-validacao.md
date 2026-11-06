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

## Custos: o que o `trader/custos.py` cobra e o que a B3 cobraria à vista

O `trader/custos.py` (tabela v0.2) modela **CFDs no MetaTrader 5**, não o mercado à vista: ações da B3
pagam **5 pb por lado** (meio spread, comissão e deslizamento juntos) e um swap diário enquanto a posição
fica aberta (carry menos 0,5% ao ano de margem; sem taxas de juro, 2% ao ano dos dois lados). Vender a
descoberto custa o mesmo que comprar. Isso vale para a M2, que opera CFDs; se uma pesquisa futura
operar **ações à vista**, a conta muda nos pontos abaixo.

Tarifas da B3 conferidas em 20/10/2026 na
[página oficial de tarifas do mercado à vista](https://www.b3.com.br/pt_br/produtos-e-servicos/tarifas/listados-a-vista-e-derivativos/renda-variavel/tarifas-de-acoes-e-fundos-de-investimento/a-vista/)
(a página não traz data de vigência; os valores incluem PIS, COFINS e ISS):

| Ponto | Regra à vista (B3 e Receita) | No `custos.py` (CFD) | O que mudaria à vista |
|---|---|---|---|
| Tarifas da B3 | 0,0300% por lado em operação normal (negociação 0,005% + contraparte central 0,0224% + TTA 0,0026%) até R$ 3 milhões de média diária no mês; 0,0230% no day trade na menor faixa | dentro dos 5 pb | as tarifas comem 3 dos 5 pb; sobram 2 pb para spread e deslizamento, apertado para ações menos líquidas |
| Leilão de fechamento | a negociação custa 0,007% (não 0,005%) nos leilões de abertura e de fechamento | não existe | a M2 decide no fechamento e executa no seguinte: à vista, isso é o leilão de fechamento, com essa tarifa e o preço do leilão |
| Túnel de preço | uma ordem que mexe o preço além do túnel manda o papel para leilão | não existe | em dias de notícia o preço de execução pode sair longe do último negócio; o deslizamento precisa de estresse maior para papéis menores |
| Lote | lote padrão de 100 ações; de 1 a 99, o fracionário (código com F), menos líquido | posição contínua (fração do capital) | com pouco capital, arredondar para lotes muda a posição; o fracionário tem spread maior |
| Liquidação | D+2 (a B3 planeja D+1 para fevereiro de 2028) | não existe | vender e comprar outro papel no mesmo dia usa limite da corretora até o dinheiro liquidar |
| Venda a descoberto | só com aluguel de ações (BTC da B3): taxa combinada entre doador e tomador, mais a tarifa de registro da B3, com garantia de 100% do valor | mesmo custo do lado comprado, com swap | o lado vendido fica mais caro e às vezes impossível (papel sem doador); uma estratégia comprada e vendida precisa da taxa de aluguel histórica de cada papel |
| Imposto | 15% do ganho líquido do mês nas operações comuns e 20% no day trade; prejuízo compensa ganho futuro; isenção para vendas de até R$ 20 mil **no mês** (não por operação), que não vale para day trade; retenção na fonte de 0,005% das vendas e de 1% do ganho no day trade | não entra (resultado antes do imposto) | a comparação com CDI ou com um fundo precisa do resultado depois do imposto, calculado mês a mês; uma estratégia que gira muito quase nunca cabe na isenção |
| Swap | não há: ação à vista não paga carregamento | carry menos 0,5% ao ano | o lado comprado fica mais barato (sem margem de corretora); o vendido troca o swap pelo aluguel |
| Corretagem | depende da corretora (muitas cobram zero para pessoa física em ações) | dentro dos 5 pb | pode ser zero; conferir a da corretora escolhida |

As regras do imposto estão consolidadas na Instrução Normativa RFB 1.585/2015. A MP 1.303/2025, que propunha alíquota
única de 17,5%, caducou em 8/10/2025 sem votação, e as regras acima continuam valendo.

**Nada muda no código por esta conferência:** mudar a tabela de custos é decisão do Tiago, entra numa
versão nova do critério e conta +25 tentativas. Se a próxima pesquisa operar à vista, a proposta é uma
tabela própria (tarifas da B3 com a data, spread medido por papel no boletim diário, aluguel e imposto
mensal), sem alterar a tabela dos CFDs.

## Validação: o Monte Carlo e o k-fold por grupo deles contra o que a M2 já faz

| Deles | O que faz | Aqui | Proposta para o próximo critério |
|---|---|---|---|
| Monte Carlo embaralhando os retornos do dia | sorteia os retornos da estratégia em outra ordem e refaz a curva: dá a distribuição da maior queda e do resultado final | o A10 (`src/acaso.py`) gira a **posição** no tempo, mantendo exposição e número de operações, e exige Sharpe acima do percentil 95; o bootstrap em blocos de 21 dias (`trader/validacao.py`) compara dois Sharpes sem fingir dias independentes | o A10 é mais exigente: embaralhar o dia não testa habilidade, porque mantém o Sharpe. Falta só a **distribuição da maior queda**: reamostrar em blocos de 21 dias (não dia a dia, que esconde as sequências ruins) e mostrar o percentil 95 da queda no relatório, como informação, sem ser regra |
| Monte Carlo embaralhando as operações | sorteia a ordem das operações fechadas: mesma soma, outra sequência de ganhos e perdas | o diário das operações (`trader/diario.py`) já tem cada operação com custo e retorno | embaralhar operações supõe que uma não depende da outra, o que vale pouco com posições seguidas no mesmo ativo; se entrar, fica como informação no relatório, junto do aviso de janela curta do diário (menos de 30 operações) |
| k-fold com expurgo por grupo | os grupos (por exemplo, o ativo) nunca estão no treino e no teste ao mesmo tempo, com expurgo nas bordas | CPCV de 10 grupos **de datas**, 2 de teste, expurgo e embargo de 21 pregões, 45 divisões e 9 caminhos; a mesma data nunca está no treino e no teste, para todos os ativos juntos; os grupos de ativos (`trader/universo.py`) servem ao risco igual por grupo, não à divisão | o CPCV por datas já impede o vazamento entre ativos no mesmo dia. O que ele não mede é se o modelo funciona num **ativo que nunca viu**: proposta de conferência extra, deixar um grupo de ativos inteiro fora do treino em cada divisão (combinado com o corte por datas e o mesmo expurgo), como teste de robustez |
| Detector de vazamento na borda | procura atributos que usam dados depois do corte | `trader/vazamento.py` (variantes "futuro", "embaralhado" e "proporção") e os testes de "cortar o futuro não muda o passado" | já coberto; o `trader/aquecimento.py` acrescentou a medida de que atributo depende de onde a série começa (só a `tendencia` depende, linha 70 da fila) |

**Como as propostas entram:** escritas como proposta, não aplicadas. Qualquer uma que vire regra exige
uma versão nova do pré-registro, com data, +25 tentativas, cópia do registro e aprovação do Tiago,
antes de ver qualquer resultado. As que são só informação no relatório (queda reamostrada, operações
embaralhadas) também esperam o próximo pré-registro, para não serem escolhidas depois de ver o número.
