# Fatores na B3 (ficha F-B3): tentativa 1

Rodada em 04/11/2026 (registrada às 02h23 e terminada às 02h46, Brasília) pelo `docs/pre-registro-quant-p0-v0.1.md`.
O código conferiu o hash do pré-registro antes de calcular qualquer número. Código:
`python -m trader.estrategias.rodar_f_b3`, commit `48949955`, feito antes da rodada (versão 0.2 do motor). Registro:
linha 17 (família F-B3, nome `fatores_b3`, 1 execução) em `~/TickerLab-Pesquisa/pesquisa_quant/registro.db` (fora do
Git). É a **1ª das 10 tentativas** da ficha. O relatório bruto está em
`pesquisa_quant/relatorios/rodada_f_b3_20261104_0546.md` (fora do Git).

Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: **REPROVADO**. Uma carteira com o quintil de cima das notas de quatro fatores (valor, momento,
qualidade e baixa volatilidade), rebalanceada todo mês no universo líquido da B3 com as deslistadas, rendeu 8,3% ao
ano de 2009 a 2023. Isso fica abaixo do CDI (8,9%) e do Ibovespa líquido (10,3%), com queda de 50% do pico. Mesmo sem
custo nem imposto, o excesso sobre o CDI é quase zero (Sharpe do excesso 0,03).

## O veredito (seção 5 do pré-registro)

| Item | O quê | Valor | Limite | Passou |
|---|---|---|---|---|
| A1 | Sharpe do excesso (−0,03) e DSR com 126 tentativas | 0,44 | ≥ 0,95 | não |
| A2 | PBO | não se aplica (a ficha não tem alternativas) | - | sim |
| A3 | platô: menor Sharpe dos vizinhos ÷ Sharpe do candidato | 0 (os dois negativos) | ≥ 0,70 | não |
| A4 | custo, imposto e impacto como fração do Sharpe bruto (0,03) | 1,88 | ≤ 0,33 | não |
| A5 | t do excesso (correção de Lo) | −0,12 | ≥ 3 | não |
| A6 | p-valor contra os sinais deslocados | 0,59 | ≤ 0,05 | não |
| A7 | limite inferior de 90% da diferença contra CDI e Ibovespa | −0,47 e −0,34 | > 0 nas duas | não |
| A8 | estresse (custos × 2, impacto × 2): DSR | 0,41 | ≥ 0,90 | não |
| F1 | maior queda do pico | −50,5% | ≥ −35% | não |
| V | o futuro infla (balanço pela data do balanço: 0,13 > −0,03), reexecução idêntica, dados conformes, cortar o futuro não muda o passado | - | as quatro | sim |

As verificações (V) passaram: o código não olha o futuro. Quando o balanço entra na data do balanço, e não na data em
que foi divulgado, o Sharpe do excesso sobe de −0,03 para 0,13, como deveria. A ficha falha no sinal, não na conta.

## O candidato, o estresse e o bruto (de 02/01/2009 a 08/09/2023)

| Leitura | Sharpe do excesso | Retorno anual | Volatilidade | Maior queda | Giro por ano |
|---|---|---|---|---|---|
| candidato | −0,03 | 8,3% | 18,7% | −50,5% | 5,3 |
| estresse | −0,05 | 8,0% | 18,7% | −50,6% | 5,3 |
| bruto (sem custo, imposto nem impacto) | 0,03 | 9,6% | 18,7% | −50,0% | 5,4 |
| CDI | - | 8,9% | - | 0,0% | - |
| Ibovespa líquido (BOVA11) | - | 10,3% | - | −49,7% | - |

A carteira caiu quase o mesmo tanto que o Ibovespa (−50,5% contra −49,7%) e rendeu menos. Custos e IR levaram 1,3
ponto ao ano, que é mais do que o sinal rendia. Em 151 dos 177 meses houve carteira-alvo. Nos primeiros
meses faltavam a história de 12 meses e a quantidade de ações.

## O teste do Brasil

| Pergunta | Leitura | Sharpe do excesso | Retorno anual | Maior queda |
|---|---|---|---|---|
| deslistadas | com elas (o candidato) | −0,03 | 8,3% | −50,5% |
| | só as sobreviventes (viés) | −0,01 | 8,6% | −46,5% |
| tamanho e isenção de R$ 20 mil | R$ 100 mil | −0,03 | 8,3% | −50,5% |
| | R$ 500 mil | −0,04 | 8,1% | −50,6% |
| | R$ 2 milhões | −0,06 | 7,7% | −50,6% |
| data do balanço | pela divulgação (o candidato) | −0,03 | 8,3% | −50,5% |
| | pela data do balanço (olha o futuro) | 0,13 | 11,4% | −50,4% |

- **Deslistadas:** com só as sobreviventes, o resultado melhora um pouco (−0,01 contra −0,03), que é o viés de
  sobrevivência esperado, e a queda máxima fica 4 pontos menor. A base tem 2.365 tickers deslistados entre 3.428.
- **Tamanho:** quanto maior a carteira, pior, porque o impacto cresce e a isenção de R$ 20 mil por mês pesa menos.
- **Data do balanço:** usar o balanço antes de ele ser público acrescentaria 3 pontos ao ano. É o tamanho do erro que
  o código evita.

## O platô

| Vizinho (±20%) | Sharpe do excesso |
|---|---|
| quintil 15% e 25% | −0,04 e −0,04 |
| banda de rebalanceamento 0,16 e 0,24 | −0,03 e −0,03 |

Os vizinhos dão o mesmo resultado que o candidato. Não há um ajuste fino que salve a regra: ela é estável e não rende.

## O que foi montado antes da rodada (sem nenhum número da estratégia)

A rodada exigia três tabelas que a base não tinha. As convenções foram fixadas no código e testadas
(`tests/test_trader_base_f_b3.py`, 28 testes) antes do registro da tentativa:

| Tabela | Fonte | Convenção |
|---|---|---|
| quantidade de ações | capital integralizado do Formulário de Referência (desde 06/2010, já no acervo) e da composição do capital da DFP e do ITR (desde 2020, baixados da CVM com o ok do Tiago) | ON + PN, sem descontar a tesouraria; cada número vale do dia em que a CVM recebeu o documento; no mesmo dia, a DFP ou o ITR vence o FRE |
| unidade da quantidade | a CVM não diz se vem em unidades ou em milhares, e as empresas usam as duas | `corrigir_quantidade`, ponto no tempo: um salto de potência de 10 em relação ao documento anterior é unidade, salvo se o preço confirmar um desdobramento; giro acima de 20% do valor de mercado por dia ou valor de mercado acima de R$ 2 trilhões põem a série em potências de mil |
| recuperação judicial | `insolvencia` do acervo (rótulos de recuperação judicial) | um episódio vai do 1º documento até 12 meses depois do último; 12 meses sem documento fecham o episódio |
| preço por ação | COTAHIST bruto | o fechamento da ON ou PN com mais volume no dia; a unit fica fora (junta várias ações) |

A correção mudou 1.044 documentos de 198 empresas. Numa amostra dos dias de empresas líquidas (um a cada 6 meses), o
giro diário ficou com mediana de 0,47% do valor de mercado e 99% dos casos abaixo de 8,1%. Sobraram 11 de 3.213
casos fora da faixa de 0,005% a 20% ao dia, em 5 empresas. O motor
passou da versão 0.1 para a 0.2 porque o valor da firma passou a usar o preço bruto de uma ação, e não o preço
ajustado por proventos.

## O que isso diz para a carteira própria

- **Os fatores na B3, como foram pré-registrados, não entram no núcleo da carteira própria.** O núcleo segue sem
  esta peça até uma regra passar no desenvolvimento.
- **Restam 9 tentativas na ficha.** Pela seção 10 do pré-registro, uma mudança depois de ver este resultado conta
  como tentativa nova e não pode ser escolhida pelo número de hoje. Uma variante só faz sentido com uma razão
  escrita antes e fonte (por exemplo, um fator só, como momento ou baixa volatilidade).
- **O holdout continua lacrado.** Não há motivo para abri-lo com uma regra reprovada no desenvolvimento.

## Limites e cuidados

- **Desenvolvimento só:** nada aqui diz o que o holdout (10/10/2023 a 09/10/2026) vai mostrar.
- **Quantidade de ações:** antes de 06/2010 não há quantidade; algumas empresas podem ter ficado com o valor de
  mercado errado depois da correção da unidade (5 empresas com giro fora da faixa); 11% dos dias de papéis líquidos
  ficaram sem quantidade, quase todos no começo de 2010 ou em ETFs e BDRs, que não são ações.
- **Tesouraria:** a quantidade não desconta as ações em tesouraria (o FRE não as traz), e o valor de mercado fica um
  pouco maior que o de verdade.
- **Preço:** momento e volatilidade usam o preço ajustado; a execução usa a abertura ajustada pelo mesmo fator.
- **IR:** o DARF é pago no último pregão do mês seguinte, vendendo se o caixa não cobre.
- **Bancos e seguradoras** entram sem o fator valor (plano de contas próprio).
- **O piso de liquidez de R$ 5 milhões por dia** foi aprovado com o texto do pré-registro (seção 13, item 4). A
  marca "a confirmar" da seção 8 sobrou do rascunho.
- **Recuperação judicial:** a CVM não marca o fim do processo; a regra dos 12 meses pode deixar uma empresa fora por
  mais ou menos tempo que o real.
- **Duplicação:** os ZIPs da DFP e do ITR baixados da CVM (13 + 13, SHA-256 em `f_b3/cvm/SHA256SUMS.txt`) também
  estão no acervo bruto. A duplicação é inofensiva e só ocupa espaço.
- **A régua do Ibovespa** é o BOVA11 comprado e mantido, sem o IR da venda final.
- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.
