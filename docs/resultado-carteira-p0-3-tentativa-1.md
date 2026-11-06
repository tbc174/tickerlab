# Carteira multiativo brasileira (ficha P0-3), tentativa 1: resultado

**Veredito: REPROVADO** (falhou em A1, A5, A6, A7 e A8). Rodada única em 03/11/2026, pelo critério do
`docs/pre-registro-quant-p0-v0.1.md` (hash `ea45eddf09e8…`, conferido pelo código antes de qualquer número).
Código: `python -m trader.estrategias.rodar_p0_3` (motor `trader/estrategias/carteira_rp.py`, versão 0.1).
Registro: 4 tentativas na família P0-3 (ids 1 a 4 de `pesquisa_quant/registro.db`, fora do Git), 107 tentativas
contadas no DSR. Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: entre 2010 e 2023, uma carteira de NTN-B, BOVA11, ouro e S&P 500 com pesos por paridade de risco
rendeu acima do CDI (Sharpe do excesso 0,36), mas não o bastante para distinguir do acaso nem de uma carteira
60/40, e o estresse de custos não muda nada porque o que come o resultado é o imposto, não a corretagem.

## Os dados

- Desenvolvimento só: de 12/05/2010 (primeiro dia da curva real do Tesouro no Acervo) a 08/09/2023 (fim do
  desenvolvimento, `trader/holdout.py`); 3.311 pregões; holdout lacrado e não aberto.
- NTN-B: índice sintético de 5 anos (curva real do Tesouro Direto + IPCA pro rata); BOVA11 pelo fechamento do
  MT5; ouro (GLD) e S&P 500 em reais pelo dólar do dia; CDI (SGS 12) e IPCA (SGS 433) do Banco Central.
- Volumes para o impacto fixados antes dos números: R$ 5 mi (NTN-B), R$ 1 bi (BOVA11), R$ 10 mi (ouro),
  R$ 50 mi (S&P).
- Carteira de R$ 100 mil, decisão no último pregão do mês, execução no fechamento do pregão seguinte, banda de
  20%, janela de 252 pregões, IR de 15% com DARF pago no último pregão do mês seguinte.

## Os itens do critério (seção 5 do pré-registro)

| Item | O quê | Valor | Limite | Passou |
|---|---|---|---|---|
| A1 | Sharpe do excesso sobre o CDI (0,36) > 0 e DSR com 107 tentativas | 0,737 | ≥ 0,95 | não |
| A2 | PBO (a ficha não tem alternativas) | — | não se aplica | sim |
| A3 | platô: menor Sharpe dos vizinhos ÷ Sharpe do candidato | 0,882 | ≥ 0,7 | sim |
| A4 | custo, imposto e impacto como fração do Sharpe bruto (0,45) | 0,198 | ≤ 0,333 | sim |
| A5 | t-estatística do excesso com a correção de Lo | 1,571 | ≥ 3,0 | não |
| A6 | contra o acaso: p-valor dos sinais deslocados | 0,292 | ≤ 0,05 | não |
| A7 | contra as réguas: limite inferior de 90% da diferença (60/40 +0,03; CDI −0,00) | −0,004 | > 0 em todas | não |
| A8 | estresse (custos × 2, Y = 2): Sharpe do excesso (0,36) > 0 e DSR | 0,733 | ≥ 0,9 | não |
| F1 | maior queda do pico (líquida, diária) | −12,9% | ≥ −35% | sim |
| V | futuro infla (0,45 > 0,36), reexecução idêntica, dados conforme, cortar o futuro não muda o passado | — | todas | sim (ver achado 1) |

## Os três esquemas (custos base, modo vender)

| Esquema | Sharpe do excesso | Sharpe | Retorno anual | Volatilidade | Maior queda | Giro |
|---|---|---|---|---|---|---|
| risk parity (candidato) | 0,36 | 1,49 | 11,7% | 7,9% | −12,9% | 0,29 |
| inverso da volatilidade | 0,35 | 1,37 | 11,9% | 8,7% | −14,2% | 0,24 |
| mínima variância | 0,23 | 1,09 | 11,3% | 10,3% | −13,1% | 0,51 |

Pesos-alvo do risk parity ao longo do tempo (148 decisões): NTN-B 61% em média (46% a 78%), BOVA11 12%,
ouro 14%, S&P 12%. É uma carteira de renda fixa com um pouco de risco, o que explica o Sharpe cheio alto
(1,49) e o Sharpe do excesso baixo (0,36): a maior parte do retorno é o próprio juro.

## Estresse (custos × 2, impacto Y = 2)

Os números são os mesmos da tabela acima até a segunda casa: os custos de negociação dobraram (R$ 582 → R$ 1.161
em 13 anos para o risk parity), mas o imposto (R$ 26,5 mil) é 45 vezes maior que eles. O estresse do
pré-registro não aperta esta ficha; o que importa aqui é o IR, que não entra no estresse.

## O teste do Brasil: vender para rebalancear ou só aportar 1% ao mês

| Modo | Sharpe do excesso | Sharpe | Retorno anual | Volatilidade | Maior queda | Giro |
|---|---|---|---|---|---|---|
| vender | 0,36 | 1,49 | 11,7% | 7,9% | −12,9% | 0,29 |
| aporte (só compra) | 0,40 | 1,52 | 12,1% | 8,0% | −12,3% | 0,13 |

Só aportar ficou um pouco melhor: nunca vende, logo nunca paga IR e gira menos da metade. A diferença é
pequena e não foi testada contra o acaso (não é item do critério).

## Réguas e platô

| Régua | Sharpe | Retorno anual | Maior queda |
|---|---|---|---|
| 60/40 (BOVA11 60%, caixa no CDI 40%, rebalanceio mensal) | 0,58 | 8,2% | −29,2% |
| CDI | — | 8,9% | 0,0% |

O risk parity ganha da 60/40 com folga em Sharpe e em queda, e o limite inferior do bootstrap da diferença é
positivo (+0,03). Contra o CDI, não: o limite inferior de 90% do Sharpe do excesso encosta no zero (−0,004).

| Vizinho | Sharpe do excesso |
|---|---|
| janela 202 | 0,32 |
| janela 302 | 0,39 |
| banda 16% | 0,36 |
| banda 24% | 0,38 |
| bruto (sem custo, imposto nem impacto) | 0,45 |

O platô é liso (A3 passa): os vizinhos ficam entre 88% e 108% do candidato.

## Achados desta tentativa (defeitos corrigidos depois do resultado; a correção é a tentativa 2)

1. **Janela sem variação virava NaN em silêncio.** De 12/04 a 07/08/2019 a curva real do Tesouro no Acervo
   não tem o ponto de 5 anos (o Tesouro Direto só vendia IPCA+ de 10 anos ou mais; o ponto de 10 anos existe).
   O índice da NTN-B ficou parado por 80 pregões. Na rodada principal isso só distorceu a volatilidade da NTN-B
   nas janelas que cobrem esse trecho (peso dela um pouco maior). Na rodada que olha o futuro, cuja janela é o
   mês seguinte, uma janela inteira sem variação levou a 0/0 no risk parity: 3 decisões com pesos NaN e 1.085
   pregões com retorno NaN, que a função do Sharpe descartou. O item V passou com 0,45 > 0,36, mas calculado
   sobre 2.226 pregões, não 3.311. Correção (motor 0.2): janela com coluna sem variação é erro, não NaN, e o
   motor recusa pesos-alvo não finitos; o ponto de 5 anos que falta segue o de 10 anos em paralelo; dia sem
   curva mantém a taxa e rende o carry e o IPCA.
2. **Barras de feriado no BOVA11.** O export do MT5 tem 91 barras com volume zero e o preço repetido entre
   2010 e 2023 (feriados da B3); 6 caíram em dia de decisão e 3 em dia de execução, onde a execução saiu ao
   preço do dia anterior. Correção: barras sem negócio ficam fora do calendário.
3. **Falha passageira do Banco Central** na primeira consulta ao SGS; a segunda tentativa funcionou e o cache
   em `pesquisa_quant/` guardou as séries.

Os três achados não mudam o veredito desta tentativa: os itens que reprovaram (A1, A5, A6, A7, A8) foram
medidos na rodada principal, que não teve NaN.

## Limites e cuidados

- Desenvolvimento só: nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.
- A NTN-B é um índice sintético de prazo constante (curva de 5 anos + IPCA pro rata), não o B5P211; a curva do
  Tesouro do dia D fica pública em D+1, antes da execução no fechamento de D+1.
- Ouro e S&P 500 em reais sem hedge; feriado lá fora usa o último preço em dólar.
- Quantidades fracionárias: os índices não têm cota, o lote de 100 não foi aplicado.
- Volumes para o impacto são estimativas conservadoras fixadas antes dos números.
- O DARF é pago no último pregão do mês seguinte, vendendo se o caixa não cobre.
- 13 anos de dados: pela régua de anos ≈ (t/SR)², um Sharpe do excesso de 0,36 precisaria de ~70 anos para
  dar t = 3. O critério foi feito para reprovar o que não se distingue do acaso, e foi o que aconteceu.
- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.
