# TickerLab

Projeto da matéria de Python e Pandas. App web (Streamlit) em que se digita o ticker de uma
empresa, busca-se os dados no Yahoo Finance, analisa-se com Pandas e testam-se estratégias com
um motor de backtest escrito à mão, sem biblioteca pronta de backtest.

> Projeto educacional. Nada aqui é recomendação de investimento. Os dados vêm do Yahoo Finance
> e podem ter atraso ou erros. Rentabilidade passada não garante resultado futuro.

## Como rodar

Requer Python 3.12.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
```

Testes e verificação de estilo:

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check .
```

Ao mudar algo em `src/`, reinicie o Streamlit (`Ctrl+C` e rode de novo) para ver o efeito.

## O que o app faz

Cada aba responde a uma pergunta, sempre com explicações em português e avisos sobre os
limites do que está sendo mostrado.

| Aba | Pergunta |
|---|---|
| Visão geral, Risco, Retorno mensal | Como o ativo se comportou: retorno, volatilidade, quedas, melhores e piores dias, calendário de retornos |
| Comparar | Como ele se compara com outros ativos e com índices (Ibovespa, S&P 500) |
| Backtest | E se eu tivesse seguido uma regra? 12 estratégias (tendência e reversão), custos, stops, CDI, imposto e validação (treino e teste, walk-forward, mapa de parâmetros, Monte Carlo, teste contra o acaso, Sharpe deflacionado e PBO) |
| Ranking | Qual das 12 estratégias foi melhor, descontando a sorte de escolher a melhor entre muitas |
| Carteira | E com vários ativos? Rotação, momentum dual, inverso da volatilidade, baixa volatilidade, canário e paridade hierárquica de risco (HRP) |
| Experimentos | Aporte único × parcelado, rebalanceamento, retorno da noite × do dia, virada do mês |
| Regimes | O ativo se comporta diferente em fases calmas e agitadas? Filtro por regime, variância gerida e disjuntor de drawdown |
| Aprendizado de máquina | Um modelo vence a previsão ingênua? Sinal do dia, barreira tripla com validação com expurgo, meta-rotulagem e previsão de volatilidade |
| Pares | Pairs trading: pares de ativos, cointegração e simulação com a relação estimada só no treino |

## Princípios do projeto

- **Sem olhar o futuro.** Toda decisão tomada no fim do dia só vale a partir do dia seguinte, e
  há testes que conferem que cortar o futuro não muda o passado.
- **Honestidade com os números.** O app mostra o que não funcionou: a maioria das estratégias
  não passa no teste contra o acaso, o Sharpe vem com intervalo e o modelo de aprendizado de
  máquina é comparado com uma previsão ingênua.
- **Limites explícitos.** Só 5 anos de dados, viés de sobrevivência, custos e imposto
  simplificados, perna vendida do pairs trading sem o custo do aluguel.
- **Cada conceito explicado.** O glossário (`conteudo/glossario.md`) e as explicações de cada
  estratégia (`conteudo/estrategias.md`) aparecem na tela e são conferidos por testes.

## Estrutura

```
app.py                interface (só mostra; os cálculos ficam em src/)
src/
  dados.py            download e limpeza (yfinance)
  indicadores.py      indicadores e métricas básicas
  metricas.py         métricas de desempenho (Sharpe, Sortino, Calmar, Ulcer, Ômega, Kelly...)
  backtest.py         motor vetorizado de um ativo
  estrategias.py      12 estratégias com parâmetros e limites
  protecoes.py        stops, tamanho por risco, alvo de volatilidade
  validacao.py        treino e teste, walk-forward, mapa de parâmetros
  acaso.py            Monte Carlo, teste contra o acaso, DSR, PBO, comprimento mínimo
  ranking.py          comparação de todas as estratégias
  cdi.py, imposto.py  CDI do Banco Central e imposto de renda simplificado
  carteiras.py, hrp.py  estratégias de vários ativos e HRP
  experimentos.py     aporte, rebalanceamento, noite × dia, virada do mês
  regimes.py          regimes de mercado, variância gerida, disjuntor de drawdown
  aprendizado.py      modelo logístico à mão, barreira tripla, expurgo, volatilidade
  pares.py            cointegração e pairs trading
  graficos.py         gráficos Plotly
conteudo/             glossário e explicações das estratégias
tests/                testes automatizados (pytest)
```

## Referências das técnicas

Sharpe probabilístico e deflacionado (Bailey e López de Prado, 2014), PBO (Bailey, Borwein,
López de Prado e Zhu, 2017), barreira tripla, expurgo e embargo, meta-rotulagem e HRP
(López de Prado), variância gerida (Moreira e Muir, 2017), cointegração (Engle e Granger).
As fórmulas foram implementadas a partir da descrição dos artigos e conferidas por testes e
simulações; vale conferi-las nas fontes originais antes de qualquer uso sério.
