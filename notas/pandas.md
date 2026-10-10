# Pandas

Notas da sessão 1 (`estudos/sessao01.ipynb`), com os dados de `PETR4.SA` (2 anos, 501 dias).

## DataFrame e Series
- **O que é:** o **DataFrame** é uma tabela (aqui, um dia por linha; colunas `Close`, `High`, `Low`, `Open`, `Volume`). A **Series** é uma coluna só, com o índice (as datas) ao lado.
- **Para que serve:** guardar e calcular sobre os preços sem fazer laço.
- **Exemplo:** `dados` é o DataFrame; `fechamento = dados["Close"]` é uma Series.
- **Cuidado:** o `yfinance` devolve colunas em dois níveis (preço e ticker). Por isso a linha `dados.columns = dados.columns.droplevel("Ticker")`.
- **Data:** 10/10/2026

## Olhar a tabela: `head()`, `tail()`, `shape`, `info()`, `describe()`
- **O que é:** formas rápidas de conhecer os dados antes de calcular.
- **Como usar:** `head()` mostra as 5 primeiras linhas, `tail()` as 5 últimas, `shape` dá `(linhas, colunas)`, `info()` lista colunas, tipos e vazios, `describe()` resume média, mínimo, máximo e quartis.
- **Cuidado:** `shape`, `index` e `columns` não levam parênteses (são informações, não ações); `head()` e `describe()` levam.
- **Data:** 10/10/2026

## Tamanho, datas e nomes das colunas
- **Como usar:**
  - `len(dados)` ou `dados.shape[0]`: número de linhas (dias).
  - `dados.index`: o rótulo de cada linha (as datas). `dados.index[0]` é a primeira e `dados.index[-1]` a última (o `-1` conta de trás para frente).
  - `dados.columns`: nomes das colunas. Para ter uma lista de verdade: `list(dados.columns)`.
- **Cuidado:** `min(dados.index)` e `max(dados.index)` também funcionam, mas percorrem tudo; `index[0]` e `index[-1]` são mais diretos quando os dados estão em ordem.
- **Data:** 10/10/2026

## Maior, menor e onde estão: `max()`, `min()`, `idxmax()`, `idxmin()`
- **O que é:** `max()` e `min()` dão o **valor**; `idxmax()` e `idxmin()` dão o **rótulo do índice** (a data) onde ele está.
- **Exemplo:** `fechamento.max()` (341,07) e `fechamento.idxmax()` (25/09/2026).
- **Cuidado:** valores como `341.07000732421875` vêm do ajuste de dividendos do Yahoo. Arredondar (`round(x, 2)`) só para mostrar, nunca nos dados.
- **Data:** 10/10/2026

## Retorno diário: `pct_change()`
- **O que é:** a variação percentual de cada dia em relação ao anterior, como fração (0,15 = +15%).
- **Exemplo:** `retorno = fechamento.pct_change()`
- **Cuidado:** o primeiro dia não tem dia anterior e fica `NaN` (vazio). `max`, `min`, `mean` ignoram o vazio sozinhos; para trabalhar sem ele, `retorno.dropna()`.
- **Data:** 10/10/2026

## Média e contagem com filtro: `mean()` e `(retorno < 0).sum()`
- **O que é:** `mean()` é a média. `retorno < 0` devolve uma Series de verdadeiro/falso, um valor por dia; `.sum()` soma os `True` (cada um vale 1), então conta os dias negativos.
- **Exemplo:** `(retorno < 0).sum()` deu 231 dias negativos de 500.
- **Cuidado:** `retorno[retorno < 0]` (colchetes) **filtra**, devolvendo só as linhas negativas; `len()` dessa série também conta.
- **Data:** 10/10/2026

## Retorno acumulado: `cumprod()`
- **O que é:** o produto acumulado: em cada dia, multiplica todos os valores até ali. Primo do `cumsum()`, que soma.
- **Para que serve:** juntar os retornos diários num retorno total. `(1 + retorno).cumprod() - 1` dá, para cada dia, quanto se ganhou desde o começo.
- **Exemplo:** o último valor da série acumulada é igual a `fechamento.iloc[-1] / fechamento.iloc[0] - 1`. É o mesmo número por dois caminhos.
- **Cuidado:** não confundir **um número** (o retorno total, só o último ponto) com **uma série** (o retorno acumulado, um valor por dia). Foi o erro do exercício D.
- **Data:** 10/10/2026

## Janela deslizante: `rolling(N)`
- **O que é:** olha, em cada dia, os últimos N dias. Depois se aplica um cálculo: `.mean()` (média móvel) ou `.std()` (volatilidade móvel).
- **Exemplo:** `fechamento.rolling(20).mean()`. Os primeiros 19 dias ficam `NaN`, porque ainda não existem 20 dias de histórico.
- **Cuidado:** `rolling(20)` sozinho não calcula nada; falta dizer o quê (`.mean()`, `.std()`...).
- **Data:** 10/10/2026

## Desvio padrão: `std()`
- **O que é:** o quanto os valores se afastam da própria média.
- **Para que serve:** medir a volatilidade dos retornos.
- **Exemplo:** `retorno.std()` (diário) e `retorno.std() * np.sqrt(DIAS_POR_ANO)` (anualizado).
- **Cuidado:** o `std()` ignora o `NaN` do primeiro dia. Se trocar o `NaN` por 0 (`fillna(0)`), o 0 entra na conta e a volatilidade sai um pouco menor do que a real.
- **Data:** 10/10/2026

## Máximo acumulado: `cummax()`
- **O que é:** em cada dia, o maior valor visto até aquele dia.
- **Para que serve:** achar o "pico até agora", base do drawdown: `fechamento / fechamento.cummax() - 1`.
- **Exemplo:** `drawdown.min()` é a pior queda; `drawdown.idxmin()` é a data do fundo.
- **Data:** 10/10/2026

## Comparar séries inteiras
- `(fechamento > mm20).sum()` compara dia a dia duas séries e conta quantos dias deram verdadeiro. Dias com `NaN` na média móvel contam como falso.
- **Data:** 10/10/2026

## A ver
- Selecionar várias colunas e filtrar linhas de um DataFrame
- `groupby` e `resample`
- Alinhar datas de dois tickers

*(Tiago: reescreva com suas palavras o que ficou estranho.)*
