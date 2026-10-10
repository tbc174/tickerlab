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

## Retorno acumulado
- **O que é:** quanto se teria ganhado (ou perdido) comprando no começo do período e segurando até hoje.
- **Para que serve:** é o número principal de "comprar e segurar", a primeira estratégia do backtest.
- **Exemplo:** `preço final ÷ preço inicial − 1`. Dá o mesmo resultado que multiplicar os fatores `(1 + retorno)` de todos os dias.
- **Data:** 10/10/2026

## Média móvel
- **O que é:** a média dos últimos N dias do preço. Suaviza as oscilações.
- **Para que serve:** mostrar a tendência. A de 20 dias reage rápido; a de 50 é mais calma. Quando a curta cruza a longa, muita gente vê um sinal: é o **cruzamento de médias**, nossa primeira estratégia de backtest.
- **Cuidado:** a média móvel olha só o passado, então chega **atrasada** às mudanças de tendência.
- **Data:** 10/10/2026

## Volatilidade
- **O que é:** o tamanho dos "sustos" do preço, medido pelo desvio padrão dos retornos.
- **Para que serve:** comparar o risco de ativos diferentes. Quanto maior, mais o preço balança.
- **Como usar:** a volatilidade dos retornos diários multiplicada por `√252` (dias de negociação por ano) vira **volatilidade anual**, a forma que se vê no mercado.
- **Cuidado:** volatilidade não diz se o ativo sobe ou desce, só o quanto balança, para os dois lados.
- **Data:** 10/10/2026

## Drawdown e máximo drawdown
- **O que é:** o quanto o preço está abaixo do seu melhor momento até agora. O **máximo drawdown** é a pior queda do topo até o fundo.
- **Para que serve:** mostrar o susto de quem comprou na hora errada. A volatilidade sozinha esconde isso, porque não diferencia uma queda longa de várias oscilações pequenas.
- **Exemplo:** pico de R$ 100, hoje R$ 80 → drawdown de −20%.
- **Data:** 10/10/2026

## A ver
- Sharpe
- Backtest, look-ahead bias e overfitting
- Beta e correlação

*(Tiago: reescreva com suas palavras.)*

*(Tiago: reescreva com suas palavras.)*
