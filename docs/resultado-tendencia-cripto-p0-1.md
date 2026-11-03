# Tendência em cripto em reais (ficha P0-1): resultado (tentativa 1 da P0-1)

**Veredito: REPROVADA** em A1, A4, A5, A7 e A8. Rodada única em 03/11/2026, pelo critério do
`docs/pre-registro-quant-p0-v0.1.md` (hash `ea45eddf09e8…`, conferido pelo código antes de qualquer número).
Código: `python -m trader.estrategias.rodar_tendencia_cripto` (o conteúdo deste PR; o registro gravou o commit
`5eb22b8a` porque o código ainda não estava commitado quando rodou). Registro: linha 11 (família P0-1, nome
`p0_1_tendencia_btc_eth`) em `pesquisa_quant/registro.db` (fora do Git); 119 tentativas contadas no DSR. Relatório
bruto da rodada em `pesquisa_quant/relatorios/rodada_tendencia_cripto_20261103_1936.md` (fora do Git).
Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: a regra segue a tendência de verdade (o sinal não é acaso: p-valor 0,004, e olhar o futuro infla o
Sharpe de 0,68 para 2,19), mas, em reais e com custo, imposto e câmbio, o que sobra é pequeno (Sharpe do excesso
0,68, t = 1,5 em cinco anos), perde da régua de comprar e segurar BTC e gasta 43% do Sharpe bruto em custos; com
este Sharpe seriam ≈ 20 anos de dados para chegar a t = 3.

## O que o pré-registro pedia (seção 4, ficha P0-1)

- **Ativos:** BTC e ETH em reais, metade do capital cada. A ficha de dados escolheu o par em USDT da Binance
  (BTCUSDT e ETHUSDT, Binance Vision) × dólar PTAX de venda (SGS 1) **da véspera**; a mesma série do começo ao fim.
- **Regra:** nove canais de Donchian ({5, 10, 20, 30, 60, 90, 150, 250, 360} dias corridos); comprado quando o
  fechamento passa a máxima da janela, zerado quando cai abaixo do meio do canal; sinal = média dos 9; peso =
  sinal × min(1; 0,25 ÷ σ de 90 dias anualizada); alavancagem ≤ 1, sem perpétuos; caixa a CDI.
- **Execução:** sinal no fechamento de D, ordem no fechamento de D+1, todo dia do ano (365).
- **Régua:** comprar e segurar BTC em reais (líquido) e CDI. **Alternativas (PBO):** nenhuma; A2 não se aplica.
- **Teste do Brasil:** (a) caixa a CDI contra caixa a 0%; (b) meses acima do teto de R$ 35 mil e o imposto;
  (c) IOF e spread de câmbio contra a série em USDT.
- **Orçamento:** 10 tentativas; esta é a primeira.

## Os itens do critério (seção 5 do pré-registro)

| Item | O quê | Valor | Limite | Passou |
|---|---|---|---|---|
| A1 | DSR do Sharpe do excesso (0,68) com 119 tentativas | 0,880 | ≥ 0,95 | não |
| A2 | PBO | não se aplica | só com alternativas | sim |
| A3 | platô: menor vizinho ÷ candidato | 0,857 | ≥ 0,7 | sim |
| A4 | custo, imposto, impacto e câmbio como fração do Sharpe bruto (1,20) | 0,432 | ≤ 0,333 | não |
| A5 | t-estatística com a correção de Lo | 1,475 | ≥ 3,0 | não |
| A6 | p-valor dos 1.000 sinais deslocados | 0,004 | ≤ 0,05 | sim |
| A7 | contra as réguas: limite inferior de 90% da diferença | BTC −0,580; CDI −0,110 | > 0 em todas | não |
| A8 | estresse (custos × 2, Y = 2, spread × 2): Sharpe do excesso 0,46, DSR | 0,705 | ≥ 0,9 | não |
| F1 | maior queda do pico (líquida, diária) | −10,6% | ≥ −35% | sim |
| V | futuro infla (2,19 > 0,68), reexecução idêntica, dados conforme, cortar o futuro | sim | todas | sim |

## O candidato

| Versão | Sharpe do excesso | Sharpe (252) | Sharpe (365) | Retorno anual | Volatilidade | Maior queda | Exposição média | Giro/ano | Custos ÷ capital | IR ÷ capital | Meses com IR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 0,68 | 1,21 | 1,26 | 15,5% | 12,8% | −10,6% | 0,13 | 5,5 | 47,3% | 15,4% | 29 de 62 |
| estresse | 0,46 | 0,99 | 1,03 | 12,7% | 12,8% | −13,1% | 0,13 | 5,4 | 70,3% | 11,2% | 25 de 62 |

Custos e IR são a soma do período (cinco anos) dividida pelo capital inicial de R$ 100 mil. Freio de 40%: nenhum
disparo (a queda máxima é −10,6%). Menor caixa ÷ patrimônio: 0,58 (o caixa nunca ficou negativo).

**Exposição média de 0,13:** a volatilidade do BTC e do ETH em reais fica em 60% a 90% ao ano na maior parte do
período, então o fator 0,25 ÷ σ fica perto de 0,3; com o sinal entre 0 e 1 e metade do capital por ativo, a
posição total raramente passa de 0,3 do patrimônio. É a regra como foi pré-registrada; o retorno anual de 15,5%
é 6,8% de CDI mais 8,7% de cripto.

### Teste do Brasil

- **(a) Caixa a CDI contra caixa a 0%:** retorno anual 15,5% contra 10,0%; Sharpe 1,21 contra 0,78. Com 87% do
  patrimônio em caixa, o CDI é mais da metade do retorno.
- **(b) Teto de R$ 35 mil:** 29 dos 62 meses passam do teto de vendas; imposto total R$ 15.362 (R$ 3.033 por
  ano, 3% do capital inicial por ano). O giro de 5,5 vezes o patrimônio por ano é o que leva as vendas acima do teto.
- **(c) IOF e spread de câmbio:** R$ 42.282 no período (0,88% por ordem, em toda compra e toda venda, porque a
  série é em reais via dólar). Sem o câmbio (a série em USDT) o Sharpe do excesso vai de 0,68 para 1,01: o câmbio
  é o maior custo da estratégia, maior que a taxa da corretora, o impacto e o imposto juntos.

### Réguas, platô e bruto

| Régua | Sharpe | Retorno anual | Maior queda |
|---|---|---|---|
| BTC comprar e segurar (em reais, líquido) | 0,79 | 56,0% | −78,0% |
| CDI | — | 6,8% | 0,0% |

| Vizinho (±20%) | Sharpe do excesso |
|---|---|
| vol alvo 0,20 | 0,74 |
| vol alvo 0,30 | 0,63 |
| janela da vol 72 | 0,68 |
| janela da vol 108 | 0,69 |
| janelas × 0,8 | 0,58 |
| janelas × 1,2 | 0,79 |
| bruto (sem custo, imposto, impacto nem câmbio) | 1,20 |

Contra o acaso: Sharpe real 1,01 (sem custo, como os sinais deslocados), percentil 95 dos 1.000 deslocamentos
0,80, p-valor 0,004.

## O que isto diz

- **O sinal existe, o resultado em reais não paga.** A6 e V dizem que a regra pega tendência de verdade (o acaso
  não explica e olhar o futuro triplica o Sharpe); A4 diz que custo, imposto e câmbio comem 43% do Sharpe bruto,
  e A5 que cinco anos de dados não bastam para distinguir 0,68 de zero (t = 1,5).
- **A régua de comprar e segurar ganha no limite inferior (A7):** o BTC em reais rendeu 56% ao ano no período com
  queda de −78%; a estratégia troca retorno por queda pequena (−10,6%), mas o critério pede ganhar da régua em
  Sharpe, e o limite inferior de 90% da diferença é −0,58.
- **O câmbio é o custo que decide:** sem IOF e spread o Sharpe do excesso seria 1,01, ainda abaixo do que A1 e A5
  pedem com 119 tentativas e cinco anos. Comprar o par em reais direto (BTCBRL) tiraria o câmbio da conta, mas a
  ficha de dados fixou a série em USDT × dólar para o começo ao fim; trocar a série é outra tentativa, com a mesma
  regra, e só depois de registrada.
- **Trilha B não abre:** a ficha diz "passou → 3 meses em papel contínuo"; não passou, então não há papel
  contínuo nem robô. A P0-1 fica registrada como reprovada na tentativa 1 (orçamento 10).

## Limites e cuidados

- Desenvolvimento só (17/08/2017 a 08/09/2023; simulação de 17/08/2018, depois do aquecimento de 365 dias):
  nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.
- **Dados:** Binance Vision (candles diários de BTCUSDT e ETHUSDT; licença CC BY-NC-SA, só uso interno: esta
  pesquisa é interna) × PTAX de venda (SGS 1) da véspera (sábado, domingo e segunda usam a de sexta). Dia sem
  candle repete o preço e não negocia. Primeiro preço de cada série: BTC 17/08/2017, ETH 17/08/2017.
- **Itens "a confirmar" lidos na fonte antes do primeiro número** (seção 3 do pré-registro): taxa da Binance à
  vista para usuário comum 0,100% por lado (tabela de taxas da Binance, lida em 03/11/2026) = `taxa_cripto_por_lado`
  0,001; isenção de R$ 35 mil de vendas no mês (Lei 9.250/1995, art. 22, II, texto compilado no Planalto, e
  Perguntas e Respostas IRPF 2024 da Receita, perguntas 627 e 653, lidos em 03/11/2026) = `isencao_cripto_no_mes`.
  Os valores batem com `trader/custos_br.py` v0.1: não há custos v0.2. A Lei 14.754/2023 mudou a tributação de
  corretoras no exterior a partir de 2024, fora do período de desenvolvimento.
- **Impacto:** raiz quadrada Y·σ·√(Q/V)·Q com Y = 1 sobre a média dos 60 dias anteriores do volume em reais; o
  estresse usa Y = 2 junto com taxa e spread dobrados (Sharpe do excesso de 0,68 para 0,46); o efeito do Y = 2
  sozinho não foi separado nesta rodada.
- **Convenções fixadas antes de rodar:** não negocia diferença menor que 0,5% do patrimônio; o custo de
  aquisição do IR é o preço pago, sem as taxas (erra contra a estratégia); o DARF sai do caixa mesmo que ele fique
  negativo (não aconteceu); o IR dos meses que ainda não venceram é pago no último dia dos dados.
- **DSR:** as séries testadas são o candidato e os seis vizinhos (7 colunas), mais as 112 tentativas anteriores de
  todas as fichas (119 no total). O critério anualiza com 252: a série em dias corridos entra na evidência com
  sábado e domingo compostos na segunda; o Sharpe (365) da tabela é só para leitura.
- **Régua do tempo:** anos ≈ (t ÷ SR)²; com t = 3 e SR = 0,68, ≈ 20 anos.
- Toda execução conta como tentativa; esta é a primeira da ficha P0-1 (orçamento 10).
- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.
