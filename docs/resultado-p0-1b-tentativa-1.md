# Tendência em cripto no par em reais (ficha P0-1b): resultado (tentativa 1 de 2)

**Veredito: REPROVADA** em A1, A3, A4, A5, A6, A7 e A8 (passou em F1 e V; A2 não se aplica). Rodada única em
04/11/2026, pelo critério do `docs/pre-registro-quant-p0-v0.2.md` (hash `abea3c85…`, conferido pelo código antes de
qualquer número). Código: `python -I -m trader.estrategias.rodar_p0_1b`, commit `167b78de` (gravado no registro sem
`+alterado`: o código foi commitado antes da tentativa). Registro: linha 18 (família P0-1b, nome
`p0_1b_tendencia_btcbrl_ethbrl`) em `pesquisa_quant/registro.db` (fora do Git); 152 tentativas contadas no DSR.
Relatório bruto em `pesquisa_quant/relatorios/rodada_p0_1b_20261104_0708.md` (fora do Git).
Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: nos 23 meses que o par em reais permite simular (13/10/2021 a 08/09/2023, quase todos de queda do
cripto e de CDI alto), a regra da P0-1 perdeu do CDI antes de qualquer custo (Sharpe bruto do excesso −0,82) e
depois deles (−1,16); o sinal não se distingue do acaso (p = 0,73), e a banda cortou só 10% do giro.

**Esta ficha foi escolhida depois de ver o resultado da P0-1** (o câmbio era o maior custo dela). O DSR conta
todas as tentativas anteriores, mas o viés de escolha não some; aqui ele não chegou a importar, porque o
resultado é negativo.

## O que o pré-registro pedia (seção 9, ficha P0-1b)

- **Regra:** a da P0-1 sem mudança (importada de `trader/estrategias/tendencia_cripto.py`, que segue igual), com a
  **banda**: a posição só muda quando difere do alvo em mais de 20% dele; alvo zero zera; posição zero abre se o
  alvo passar de 0,5% do patrimônio. Quando muda, vai ao alvo. O mínimo de 0,5% do patrimônio por ordem da P0-1
  continua valendo (a banda vem por cima).
- **Dados:** candles diários de BTCBRL e ETHBRL do Binance Vision, já em reais, sem câmbio.
- **Spread do livro em reais:** 0,3% por lado no critério; 0,1% só como leitura. Impacto: o modelo da P0-1 sobre
  o volume do par em reais.
- **Régua:** comprar e segurar BTCBRL (líquido) e CDI. **Alternativas (PBO):** nenhuma.
- **Teste do Brasil:** (a) caixa a CDI contra caixa a 0%; (b) meses acima do teto de R$ 35 mil e o imposto;
  (c) a P0-1 no mesmo período, para medir o câmbio; (d) com e sem a banda.
- **O que se esperava, escrito antes:** poucos anos e, por isso, provavelmente inconclusivo. Saiu pior: reprovada
  em quase tudo, com a amostra ainda menor que o MinTRL.

## Os dados

- 72 zips mensais (BTCBRL e ETHBRL, 2020-10 a 2023-09) baixados em 04/11/2026 numa pasta nova
  (`pesquisa_quant/binance_brl`), com o SHA-256 de cada um em `sha256.json`; lidos com `python -I`.
- **Primeiro candle (o que a ficha deixou "a confirmar"):** BTCBRL em 13/10/2020, ETHBRL em 30/10/2020. Nenhum
  dia faltando depois do primeiro candle até 30/09/2023 (os dias depois de 08/09/2023 são cortados pelo holdout).
- Simulação de 13/10/2021 (aquecimento de 365 dias) a 08/09/2023: **1,9 ano**, 24 meses de apuração do IR. O ETH
  só entra em 30/10/2021, depois do aquecimento dele.
- Volume mediano por dia (10/2020 a 09/2023): R$ 48 milhões no BTCBRL e R$ 18 milhões no ETHBRL (bem menor que no par em USDT, como a
  ficha previa); o impacto continua pequeno para uma carteira de R$ 100 mil.

## Os itens do critério (seção 5 do pré-registro)

| Item | O quê | Valor | Limite | Passou |
|---|---|---|---|---|
| A1 | DSR do Sharpe do excesso (−1,16) com 152 tentativas | 0,022 | ≥ 0,95 | não |
| A2 | PBO | não se aplica | só com alternativas | sim |
| A3 | platô: menor vizinho ÷ candidato | 0,000 | ≥ 0,7 | não |
| A4 | custo, imposto e impacto como fração do Sharpe bruto (−0,82) | infinito | ≤ 0,333 | não |
| A5 | t-estatística com a correção de Lo | −1,751 | ≥ 3,0 | não |
| A6 | p-valor dos 1.000 sinais deslocados | 0,732 | ≤ 0,05 | não |
| A7 | contra as réguas: limite inferior de 90% da diferença | BTCBRL −1,17; CDI −2,19 | > 0 em todas | não |
| A8 | estresse (taxa × 2, Y = 2, spread × 2): Sharpe do excesso −1,50, DSR | 0,007 | ≥ 0,9 | não |
| F1 | maior queda do pico (líquida, diária) | −7,9% | ≥ −35% | sim |
| V | futuro infla (1,31 > −1,16), reexecução idêntica, dados conforme, cortar o futuro | sim | todas | sim |

A3 e A4 saem em 0 e infinito porque o candidato e o bruto são negativos: a razão não tem sentido com Sharpe
negativo, e o critério reprova.

## O candidato

| Versão | Sharpe do excesso | Sharpe (252) | Retorno anual | Volatilidade | Maior queda | Exposição média | Giro/ano | Ordens | Custos ÷ capital | Spread ÷ capital | IR ÷ capital | Meses acima de R$ 35 mil |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (spread 0,3%) | −1,16 | 0,32 | 2,4% | 7,6% | −7,9% | 0,12 | 6,1 | 321 | 5,2% | 3,5% | 0,0% | 5 de 24 |
| estresse | −1,50 | −0,03 | −0,2% | 7,6% | −8,4% | 0,12 | 6,1 | 322 | 10,2% | 6,9% | 0,0% | 5 de 24 |
| leitura: spread 0,1% | −1,01 | 0,47 | 3,6% | 7,6% | −7,6% | 0,12 | 6,1 | 321 | 2,9% | 1,2% | 0,0% | 5 de 24 |

Custos, spread e IR são a soma do período dividida pelo capital inicial de R$ 100 mil. Freio de 40%: nenhum
disparo. Menor caixa ÷ patrimônio: 0,56. O Sharpe do excesso é sobre o CDI (11,2% ao ano no período), com os
dias compostos em dias úteis; o Sharpe (252) da tabela é o do retorno total, só para leitura.

### Teste do Brasil

- **(a) Caixa a CDI contra caixa a 0%:** retorno anual 2,4% contra −7,5%; Sharpe 0,32 contra −0,99. Com 88% do
  patrimônio em caixa, o CDI é tudo o que a estratégia ganhou; a parte em cripto perdeu.
- **(b) Teto de R$ 35 mil:** 5 dos 24 meses passam do teto de vendas, mas o imposto foi **zero**: nesses meses o
  resultado das vendas foi prejuízo.
- **(c) A P0-1 no mesmo período** (a regra e a série dela, BTCUSDT e ETHUSDT × PTAX da véspera, cortadas em
  13/10/2021 a 08/09/2023): Sharpe do excesso −1,45 com câmbio e −0,81 sem; o câmbio custou R$ 22.796 no
  período (giro de 6,2 por ano). A P0-1b ficou em −1,16: tirar o câmbio ajudou (de −1,45 para −1,16), mas o
  spread de 0,3% por lado do livro em reais comeu boa parte do ganho (a série em USDT sem câmbio, −0,81, é quase
  o bruto da P0-1b, −0,82).
- **(d) Com e sem a banda:** Sharpe do excesso −1,16 contra −1,27; giro 6,1 contra 6,8 por ano; 321 contra 412
  ordens. A banda cortou 22% das ordens e só 10% do giro: a maior parte do giro vem de mudanças grandes do sinal
  (entrar e sair do canal), que passam de qualquer banda.

### Réguas, platô e bruto

| Régua | Sharpe | Retorno anual | Maior queda |
|---|---|---|---|
| BTCBRL comprar e segurar (líquido) | −0,57 | −30,9% | −77,6% |
| CDI | — | 11,2% | 0,0% |

| Vizinho (±20%) | Sharpe do excesso |
|---|---|
| vol alvo 0,20 | −1,15 |
| vol alvo 0,30 | −1,16 |
| janela da vol 72 | −1,24 |
| janela da vol 108 | −1,10 |
| janelas × 0,8 | −1,12 |
| janelas × 1,2 | −0,81 |
| banda 0,16 | −1,23 |
| banda 0,24 | −1,15 |
| bruto (sem taxa, imposto, impacto nem spread) | −0,82 |

Contra o acaso: Sharpe real −0,96 (sem imposto, como os sinais deslocados), percentil 95 dos 1.000 deslocamentos
−0,02, p-valor 0,732.

## O que isto diz

- **O período é curto e ruim para a regra.** Os 23 meses vão do topo de 2021 ao fundo de 2022 e à recuperação
  lenta de 2023: o BTCBRL caiu 31% ao ano, com queda de −78%. A regra ficou pouco exposta (0,12 do patrimônio, em
  média) e perdeu pouco (−7,9% do pico), mas entrou e saiu em falsos rompimentos, e o bruto já perde do CDI.
- **Não é custo, é sinal:** o Sharpe bruto do excesso é −0,82 e o p-valor contra o acaso 0,73. Com um bruto
  negativo, nenhum corte de custo (sem câmbio, banda, spread menor) faz a regra passar.
- **O câmbio era mesmo um custo grande** (c): no mesmo período a P0-1 perdia 0,64 de Sharpe com ele. O par em
  reais tira essa conta, mas troca por um spread de livro que ninguém mediu; a 0,1% (leitura) o Sharpe seria −1,01.
- **A banda não fez o que a ficha esperava:** o giro foi de 6,8 para 6,1, não para perto de zero.
- **Inconclusivo pelo tempo, reprovado pelo resto:** com 1,9 ano a amostra é menor que o MinTRL; mesmo assim o
  bruto negativo (A4), o platô (A3) e o teste contra o acaso (A6, p = 0,73) reprovam com folga.
- **A tentativa 2 não vai ser usada para "melhorar" a regra.** O orçamento de 2 serve para um defeito achado
  depois; nenhum foi achado. A série P0-1b entra no papel com a tentativa 1 como referência (Sharpe do excesso
  −1,16), como a seção 5 do pré-registro manda.

## Limites e cuidados

- **Escolha depois de ver o resultado:** a ficha existe porque a P0-1 mostrou o câmbio como maior custo. O
  relatório diz isso; o DSR (152 tentativas) penaliza, mas não apaga o viés.
- Desenvolvimento só (13/10/2020 a 08/09/2023; simulação de 13/10/2021): nada aqui diz o que o holdout vai
  mostrar. Abri-lo é decisão escrita do Tiago e gasta o lacre da C-1, das camadas e da P0-1b de uma vez.
- **Poucos anos:** 1,9 ano simulado, menos que o MinTRL; um ciclo só do cripto (queda), com CDI alto (11,2% ao
  ano). Com outro período o número pode ser bem outro, para cima ou para baixo.
- **Dados:** Binance Vision (candles diários de BTCBRL e ETHBRL; licença CC BY-NC-SA, uso interno: esta pesquisa é
  interna), já em reais. Dia sem candle repete o preço e não negocia (não houve nenhum depois do 1º candle).
  Para o teste (c): BTCUSDT e ETHUSDT do Binance Vision × PTAX de venda (SGS 1) da véspera, a série da P0-1.
  CDI: SGS 12 do Banco Central.
- **Spread do livro:** não há histórico de spread do BTCBRL e do ETHBRL; 0,3% por lado é uma hipótese
  conservadora escrita antes; 0,1% é só leitura. Taxa da Binance e isenção de R$ 35 mil iguais às da P0-1
  (`trader/custos_br.py` v0.1).
- **Impacto:** raiz quadrada Y·σ·√(Q/V)·Q com Y = 1 sobre a média dos 60 dias anteriores do volume em reais do par.
- **Convenções fixadas antes de rodar:** a banda vem por cima do mínimo de 0,5% do patrimônio da P0-1; o custo de
  aquisição do IR é o preço pago, sem as taxas (erra contra a estratégia); o DARF sai do caixa mesmo que ele fique
  negativo (não aconteceu); o IR dos meses que ainda não venceram é pago no último dia dos dados.
- **DSR:** as séries testadas são o candidato e os oito vizinhos (os seis da P0-1 e a banda 0,16 e 0,24), mais
  as tentativas anteriores de todas as fichas (152 no total). O critério anualiza com 252 (fim de semana composto
  na segunda).
- **O teste (c) roda a P0-1 sem mudança** e corta o resultado; não é tentativa nova da P0-1 (não entra no registro
  como tentativa).
- Toda execução conta como tentativa; esta é a primeira das duas da ficha P0-1b. Uma terceira é recusada pelo
  código antes de registrar.
- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.
