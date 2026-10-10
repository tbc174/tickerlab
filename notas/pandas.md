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

## A ver
- Selecionar várias colunas e filtrar linhas de um DataFrame
- `rolling()` (médias móveis e volatilidade móvel)
- `groupby` e `resample`
- Alinhar datas de dois tickers

*(Tiago: reescreva com suas palavras o que ficou estranho.)*
