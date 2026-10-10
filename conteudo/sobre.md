## O que é o TickerLab
O TickerLab é um laboratório de estudo sobre ações. Você digita um ticker, o app baixa o histórico de preços, calcula números de retorno e risco e deixa você testar o que teria acontecido se seguisse uma regra de investimento no passado.

Foi feito como projeto da matéria de Python e Pandas. O foco não é dizer o que comprar, e sim **mostrar como testar uma ideia sem se enganar**.

## Aviso importante
**Nada aqui é recomendação de investimento.** Os resultados são simulações com dados do passado e rentabilidade passada não garante resultado futuro. Investir envolve risco de perder dinheiro. Antes de decidir, converse com um profissional habilitado.

## De onde vêm os dados
- **Preços:** Yahoo Finance, pela biblioteca `yfinance`, já ajustados por dividendos e desdobramentos. Podem ter atraso, lacunas ou erros.
- **CDI:** série diária do Banco Central do Brasil (Sistema Gerenciador de Séries Temporais, série 12), usada como taxa livre de risco quando você escolhe essa opção.
- **Histórico:** o app trabalha com até 5 anos de dados.

## Como o backtest funciona
Um backtest é uma simulação: aplica uma regra aos preços do passado e mostra o resultado.

- **Sem olhar o futuro.** A decisão tomada no fim de um dia só vale a partir do dia seguinte. Sem isso, a simulação usaria informação que ainda não existia e o resultado seria falso.
- **Custos em cada operação.** Corretagem, taxas e a diferença entre o preço visto e o executado (slippage) descontam o resultado em toda compra e venda.
- **Imposto opcional.** Uma versão simplificada das regras de renda variável (swing trade na B3). Não é orientação tributária.
- **Escrito do zero em Pandas,** sem biblioteca pronta de backtest, e coberto por testes automatizados.

## O que o app faz para não enganar
Testar muitas regras e mostrar só a melhor é o jeito mais fácil de se iludir. Por isso o app inclui:

- **Treino e teste, walk-forward e mapa de parâmetros:** a regra é escolhida num período e avaliada em outro.
- **Monte Carlo e teste contra o acaso:** mostram quanto do resultado uma posição sem relação com o preço também alcançaria.
- **Sharpe deflacionado e PBO:** descontam o número de combinações testadas.
- **Comparação com uma base ingênua:** modelos de aprendizado de máquina precisam vencer uma previsão simples para valer algo.

## Limites
- **Poucos dados:** 5 anos é um período curto e específico. Mudar o período pode mudar a conclusão.
- **Viés de sobrevivência:** só aparecem empresas que existem hoje, o que tende a deixar os resultados melhores do que a realidade.
- **Custos e imposto simplificados:** os valores padrão são estimativas. Confira os da sua corretora e as regras da Receita Federal e da B3.
- **Venda a descoberto:** o pairs trading assume que dá para vender ações emprestadas e não inclui o custo do aluguel.
- **Resultados valem para o ativo e o período escolhidos,** não para o mercado em geral.
- **Fórmulas estatísticas:** foram implementadas a partir dos artigos e conferidas com testes e simulações; não substituem uma revisão nas fontes originais.

## Referências
- Bailey e López de Prado (2014), *The Deflated Sharpe Ratio*.
- Bailey, Borwein, López de Prado e Zhu (2017), *The Probability of Backtest Overfitting*.
- López de Prado (2016), paridade hierárquica de risco; e *Advances in Financial Machine Learning* (barreira tripla, expurgo e embargo, meta-rotulagem).
- Moreira e Muir (2017), *Volatility-Managed Portfolios*.
- Faber (2007), *A Quantitative Approach to Tactical Asset Allocation*.
- Engle e Granger (1987), cointegração.
