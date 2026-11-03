# Carteira multiativo brasileira (ficha P0-3), tentativa 2: resultado

**Veredito: REPROVADO** (falhou em A1, A5, A6 e A8). Rodada única em 03/11/2026, pelo critério do
`docs/pre-registro-quant-p0-v0.1.md` (hash `ea45eddf09e8…`, conferido pelo código antes de qualquer número).
Código: `python -m trader.estrategias.rodar_p0_3` no commit `d35a2028` (o conteúdo do PR #745: motor
`trader/estrategias/carteira_rp.py` versão 0.2, curva de 5 anos seguindo a de 10, barras sem volume fora).
Registro: tentativas 5 a 8 da família P0-3 em `pesquisa_quant/registro.db` (fora do Git), 111 tentativas
contadas no DSR. Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: com os três defeitos da tentativa 1 corrigidos, a carteira por paridade de risco melhorou um
pouco (Sharpe do excesso sobre o CDI de 0,36 para 0,40) e passou a ganhar do CDI no bootstrap, mas continua
sem se distinguir do acaso; e a correção dos feriados tirou junto 18 pregões de verdade (achado desta
tentativa), o que leva à tentativa 3.

## O que mudou desde a tentativa 1

- Janela sem variação é erro (motor 0.2); nenhuma decisão com peso NaN, nenhum pregão descartado.
- O ponto de 5 anos da curva real, que falta de 12/04 a 07/08/2019, segue o de 10 anos em paralelo; a NTN-B
  sintética rende carry e IPCA todo pregão (0 dias parados, contra 80 antes).
- Barras com volume zero do BOVA11 fora do calendário: 3.220 pregões em vez de 3.311.

## Os itens do critério (seção 5 do pré-registro)

| Item | O quê | Valor | Limite | Passou |
|---|---|---|---|---|
| A1 | Sharpe do excesso sobre o CDI (0,40) > 0 e DSR com 111 tentativas | 0,772 | ≥ 0,95 | não |
| A2 | PBO (a ficha não tem alternativas) | — | não se aplica | sim |
| A3 | platô: menor Sharpe dos vizinhos ÷ Sharpe do candidato | 0,935 | ≥ 0,7 | sim |
| A4 | custo, imposto e impacto como fração do Sharpe bruto (0,49) | 0,179 | ≤ 0,333 | sim |
| A5 | t-estatística do excesso com a correção de Lo | 1,729 | ≥ 3,0 | não |
| A6 | contra o acaso: p-valor dos sinais deslocados | 0,352 | ≤ 0,05 | não |
| A7 | contra as réguas: limite inferior de 90% da diferença (60/40 +0,04; CDI +0,03) | 0,033 | > 0 em todas | sim |
| A8 | estresse (custos × 2, Y = 2): Sharpe do excesso (0,40) > 0 e DSR | 0,766 | ≥ 0,9 | não |
| F1 | maior queda do pico (líquida, diária) | −11,3% | ≥ −35% | sim |
| V | futuro infla (0,47 > 0,40), reexecução idêntica, dados conforme, cortar o futuro não muda o passado | — | todas | sim |

A7 passou nesta tentativa (na 1 o limite inferior contra o CDI era −0,004). O resto do quadro é o mesmo:
o que reprova é a distância do acaso (A5, A6) e o DSR (A1, A8), não o custo nem a queda.

## Os três esquemas (custos base, modo vender)

| Esquema | Sharpe do excesso | Sharpe | Retorno anual | Volatilidade | Maior queda | Giro |
|---|---|---|---|---|---|---|
| risk parity (candidato) | 0,40 | 1,57 | 11,9% | 7,6% | −11,3% | 0,27 |
| inverso da volatilidade | 0,41 | 1,46 | 12,3% | 8,5% | −12,6% | 0,23 |
| mínima variância | 0,28 | 1,13 | 11,8% | 10,4% | −13,3% | 0,53 |

Estresse (custos × 2, impacto Y = 2): os mesmos números até a segunda casa; como na tentativa 1, o imposto
é o que pesa, e ele não entra no estresse.

## O teste do Brasil: vender para rebalancear ou só aportar 1% ao mês

| Modo | Sharpe do excesso | Sharpe | Retorno anual | Volatilidade | Maior queda | Giro |
|---|---|---|---|---|---|---|
| vender | 0,40 | 1,57 | 11,9% | 7,6% | −11,3% | 0,27 |
| aporte (só compra) | 0,45 | 1,61 | 12,4% | 7,7% | −11,3% | 0,14 |

## Réguas e platô

| Régua | Sharpe | Retorno anual | Maior queda |
|---|---|---|---|
| 60/40 (BOVA11 60%, caixa no CDI 40%, rebalanceio mensal) | 0,58 | 8,3% | −29,2% |
| CDI | — | 8,9% | 0,0% |

| Vizinho | Sharpe do excesso |
|---|---|
| janela 202 | 0,37 |
| janela 302 | 0,39 |
| banda 16% | 0,41 |
| banda 24% | 0,41 |
| bruto (sem custo, imposto nem impacto) | 0,49 |

O platô ficou mais liso que na tentativa 1 (vizinhos entre 93% e 103% do candidato).

## Achado desta tentativa (defeito corrigido depois do resultado; a correção é a tentativa 3)

4. **O filtro de volume tirou 18 pregões de verdade.** Das 91 barras do BOVA11 com volume zero, 73 são
   feriados (preço repetido), mas 18 são os pregões de 12/03 a 07/04/2021, com o preço mudando todo dia: o
   export do MT5 veio sem o volume nesse trecho. O calendário da tentativa 2 ficou com um buraco de 28 dias
   corridos (uma decisão de fim de mês caiu no último pregão antes do buraco e a execução, no primeiro
   depois). Correção: barra sem negócio é a que tem volume zero **e** o preço igual ao da anterior; o pregão
   que só veio sem o volume fica. Com isso o calendário tem 3.238 pregões e o maior buraco é o carnaval
   (6 dias corridos).

O achado não muda o veredito desta tentativa: os itens que reprovaram (A1, A5, A6, A8) estão longe dos
limites, e 18 pregões em 3.238 não os aproximam.

## Limites e cuidados

- Desenvolvimento só: nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.
- A NTN-B é um índice sintético de prazo constante (curva de 5 anos + IPCA pro rata), não o B5P211; de
  12/04 a 07/08/2019 o ponto de 5 anos é o de 10 anos deslocado, não um dado do Tesouro.
- Ouro e S&P 500 em reais sem hedge; feriado lá fora usa o último preço em dólar.
- Quantidades fracionárias: os índices não têm cota, o lote de 100 não foi aplicado.
- Volumes para o impacto são estimativas conservadoras fixadas antes dos números.
- O DARF é pago no último pregão do mês seguinte, vendendo se o caixa não cobre.
- 13 anos de dados: um Sharpe do excesso de 0,40 precisaria de ~56 anos para dar t = 3 pela régua
  anos ≈ (t/SR)². O critério foi feito para reprovar o que não se distingue do acaso.
- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.
