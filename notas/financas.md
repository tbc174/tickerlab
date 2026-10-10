# Conceitos de finanças

(Cada conceito é explicado quando aparece no app.)

## Preço de fechamento ajustado
- **O que é:** o preço do fim do dia (`Close`), já corrigido por dividendos e desdobramentos quando se usa `auto_adjust=True` no `yfinance`.
- **Para que serve:** comparar preços ao longo do tempo sem "saltos" falsos quando a empresa paga dividendo ou desdobra ações.
- **Cuidado:** por causa do ajuste, os preços antigos podem não bater com o que a corretora mostrava na época, e vêm com muitas casas decimais.
- **Data:** 10/10/2026

## Retorno diário
- **O que é:** quanto o preço variou de um dia para o seguinte, em porcentagem: `(preço de hoje ÷ preço de ontem) − 1`.
- **Para que serve:** é a base de quase todas as métricas (volatilidade, Sharpe, backtest).
- **Exemplo:** na PETR4, o melhor dia dos últimos 2 anos foi +15,3% (09/04/2025) e o pior foi −9,2% (03/04/2025). A média diária foi cerca de 0,09%, e 231 dos 500 dias fecharam em queda.
- **Cuidado:** os melhores e piores dias costumam ficar juntos (aqui, uma semana de diferença): o mercado oscila em ondas.
- **Data:** 10/10/2026

## A ver
- Retorno acumulado
- Volatilidade
- Drawdown
- Sharpe
- Média móvel e cruzamento de médias
- Backtest, look-ahead bias e overfitting
- Beta e correlação

*(Tiago: reescreva com suas palavras.)*
