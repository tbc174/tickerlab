# Synthetic Dividend e rebalanceamento (ficha P0-7): resultado (tentativa 1 da P0-7)

**Estudo, não candidata:** a ficha P0-7 não passa pelo critério da seção 5 e nada aqui vira dinheiro
(pré-registro, ficha P0-7, e escolha 7 da seção 13). Rodada única em 03/11/2026 (20h11, Brasília), pelo
`docs/pre-registro-quant-p0-v0.1.md` (hash `ea45eddf09e8…`, conferido pelo código antes de qualquer número).
Código: `python -m trader.estrategias.rodar_sd` (commit `36f00011`, já commitado antes de rodar). Registro: linha 13
(família P0-7, nome `p0_7_simulador_sd`) em `pesquisa_quant/registro.db` (fora do Git); é a 1ª das 4 tentativas
da ficha. Relatório bruto em `pesquisa_quant/relatorios/rodada_sd_20261103_2311.md` (fora do Git). Reexecução
com a mesma semente: idêntica. Só o desenvolvimento (até 08/09/2023).
Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: na versão brasileira (CDI, custos e IR) o SD e o constant-mix ficam **um pouco à frente** de
comprar e segurar na mediana, quase só porque comprar e segurar paga todo o IR na venda final; eles **perdem a
cauda de cima** (p95 e média menores) em todo cenário de cripto. Sem o CDI no caixa o constant-mix perde de
comprar e segurar em 3 dos 4 cenários. O ETF sem isenção quase não muda nada, e o day trade não aparece. O teto
de vendas da isenção quebra o SD no histórico do BTC.

## O que a ficha pedia

- **Regras:** comprar e segurar; SD Full (passo r = 2^(1/8) − 1 ≈ 9,05%, partilha s = 50%); SD ATH-only (só
  vende, nunca recompra); constant-mix de 50% com banda adaptativa r_t = σ_t ÷ √F (σ dos 90 dias anteriores; F = 30
  em cripto e 12 na B3), com piso de 10 × o custo de ida e volta.
- **Entradas:** Monte Carlo (GBM, 2.000 caminhos, 3 anos) nos quatro cenários da tabela 4.4 do relatório de
  29/10, e o histórico do BTC em reais e do Ibovespa (BOVA11) em janelas de 3 anos.
- **Saídas:** mediana, p5 e p95 do múltiplo do capital.
- **Testes do Brasil:** (a) o CDI aumenta a vantagem do constant-mix? (b) o teto de vendas e (c) o bloqueio de
  day trade mudam o resultado? E (fila 514, relatório 4.5) refazer a tabela 4.4 com CDI, IR e teto: o IR do ETF
  destrói a vantagem?

## Como foi medido (fixado antes dos números)

- **Capital** de R$ 200 mil (o exemplo da seção 4.5). **Múltiplo** = patrimônio **liquidado** no último dia (vende
  tudo, paga o custo e o IR dessa venda) ÷ capital. É a medida justa, porque comprar e segurar adia o IR e as
  outras regras não.
- **Execução:** gatilho no fechamento de D e ordem no fechamento de D+1 (seção 4 do pré-registro). O teste (c) usa
  ordens limitadas, com 8 preços por dia no Monte Carlo.
- **Custos** de `trader/custos_br.py`: 0,10% por lado em cripto; na B3, a tarifa do leilão de fechamento. IR mensal
  por custo médio (15%; 20% no day trade), isenção de R$ 20 mil em ações e de R$ 35 mil em cripto, ETF sem isenção,
  prejuízo compensado e DARF pago do caixa no mês seguinte.
- **Caixa** a CDI de 14% no Monte Carlo e o CDI de verdade no histórico. Sem caixa negativo: a recompra fica
  limitada ao caixa.

## 1. A tabela 4.4 refeita na versão brasileira (Monte Carlo, mediana do múltiplo liquidado)

| Cenário | Comprar e segurar | SD Full | SD ATH-only | Constant-mix | SD Full vence comprar e segurar |
|---|---|---|---|---|---|
| BTC μ 50%, σ 70% | 1,98× | **2,30×** | 2,24× | 2,08× | 62% dos caminhos |
| BTC μ 20%, σ 70% | 0,88× | 1,18× | 1,20× | **1,35×** | 78% |
| Ibovespa μ 17%, σ 25% (ETF) | 1,44× | 1,49× | 1,49× | 1,49× | 63% |
| Ação μ 16%, σ 15% | 1,48× | 1,51× | 1,51× | 1,50× | 69% |

**Onde cada regra perde de comprar e segurar:**

| Cenário | Comprar e segurar (p5 / p95 / média) | SD Full | Constant-mix |
|---|---|---|---|
| BTC μ 50%, σ 70% | 0,29× / **13,31×** / **3,84×** | 0,36× / 8,13× / 2,99× | 0,79× / 5,17× / 2,42× |
| BTC μ 20%, σ 70% | 0,12× / **5,50×** / 1,61× | 0,13× / 4,55× / 1,60× | 0,50× / 3,42× / 1,59× |
| Ibovespa μ 17%, σ 25% | 0,74× / **2,71×** / **1,56×** | 0,75× / 2,50× / 1,55× | **1,07×** / 2,03× / 1,52× |
| Ação μ 16%, σ 15% | 1,01× / **2,16×** / 1,52× | 1,03× / 2,09× / 1,53× | **1,23×** / 1,81× / 1,51× |

- Na **mediana**, as três regras ficam à frente nos quatro cenários. Mas a diferença na B3 é de 0,02× a 0,05× em
  três anos, e quase toda vem do IR que comprar e segurar paga na liquidação. **Sem vender no fim**, comprar e
  segurar empata ou vence o constant-mix (Ibovespa 1,52× a 1,52×; Ação 1,56× a 1,53×; BTC μ 50% 2,16× a 2,11×).
- Na **cauda de cima** (p95) e na **média**, comprar e segurar vence em todo cenário de cripto e no Ibovespa. Quem
  vende na alta abre mão das trajetórias que explodem. É o preço do seguro.
- O **constant-mix** é o que mais reduz a pior trajetória (p5) e a maior queda (37% contra 66% no BTC μ 50%; 13%
  contra 30% no Ibovespa). Esse é o ganho de verdade dele: menos risco, não mais retorno.

## 2. A versão do relatório (para conferir o simulador)

Com as hipóteses do relatório (10 bps por lado, sem IR, caixa negativo livre, ordem no próprio fechamento):

| Cenário | Comprar e segurar (aqui; relatório) | SD8 (aqui; relatório) |
|---|---|---|
| BTC μ 50%, σ 70% | 2,15×; 2,14× | 2,34×; 2,35× |
| BTC μ 20%, σ 70% | 0,88×; 0,87× | 1,19×; **1,11×** |
| Ibovespa μ 17%, σ 25% | 1,52×; 1,52× | 1,58×; 1,57× |
| Ação μ 16%, σ 15% | 1,56×; 1,56× | 1,58×; 1,57× |

Bate dentro do erro do Monte Carlo (~±0,03×) em sete dos oito números. O SD8 no BTC μ 20% sai 0,08× acima do
relatório. Não sabemos a convenção dele (o relatório não publica o código) e não ajustamos nada para bater.

## 3. O histórico (desenvolvimento, janelas de 3 anos que começam em cada mês)

| Série | Janelas | Comprar e segurar | SD Full | SD ATH-only | Constant-mix | Constant-mix vence |
|---|---|---|---|---|---|---|
| BTC em reais (2018-09 a 2020-09) | 25 | 2,77× | 3,32× | **3,46×** | 2,24× | 4% |
| BOVA11 (2010-02 a 2020-08) | 127 | 1,16× | 1,19× | 1,18× | **1,24×** | 65% |

- **BTC:** o SD Full e o ATH-only ficaram à frente na mediana, mas pagaram de 18% a 40% do capital em IR, e o
  constant-mix perdeu em 24 de 25 janelas. São só 25 janelas sobrepostas, de dois anos de começo: é **um** caminho
  (a alta de 2020-2021) visto 25 vezes, não 25 testes.
- **BOVA11:** o constant-mix ganhou em 65% das janelas e cortou a maior queda de 39% para 15%. O ganho na mediana
  foi de 0,08× em três anos.
- O IOF e o spread de câmbio em toda ordem (BTC) tiram 0,15× do SD Full, que negocia 33 vezes por ano, e 0,05× de
  comprar e segurar.

## 4. Os testes do Brasil

**(a) O CDI aumenta a vantagem do constant-mix?** Sim, em todos os casos. Constant-mix menos comprar e segurar
(mediana), com caixa a CDI e com caixa a 0%:

| | Com CDI | Com caixa a 0% |
|---|---|---|
| BTC μ 50% | +0,10× | −0,27× |
| BTC μ 20% | +0,48× | +0,24× |
| Ibovespa | +0,05× | −0,22× |
| Ação | +0,02× | −0,25× |
| BOVA11 (histórico) | +0,08× | −0,07× |
| BTC (histórico) | −0,54× | −0,71× |

Sem o CDI, o constant-mix só vence no BTC μ 20% (o cenário em que o próprio ativo quase não sobe). A "vantagem do
rebalanceamento" no Brasil é, em boa parte, o juro da metade em caixa.

**(b) O teto de vendas da isenção:** no Monte Carlo ele quase não muda a mediana (de 0,00× a +0,02×). No
**histórico do BTC derruba o SD Full de 3,32× para 2,70×**, abaixo de comprar e segurar, com 551 vendas travadas
por janela. O teto, como foi registrado, trava a ordem inteira (não a reduz ao que cabe na isenção). Com R$ 200 mil
e o BTC subindo vários passos por mês, a venda nunca cabe, e o SD segue recomprando nas quedas sem vender nas
altas. Testar um teto que reduz a ordem seria outra tentativa.

**(c) O bloqueio de day trade:** não muda nada. Com 8 preços por dia, nenhum caminho teve day trade: o passo do SD
(9%) e a banda do constant-mix (7% no Ibovespa, 4% na ação, com o piso) são largos demais para ida e volta no
mesmo dia.

**(d) O IR do ETF destrói a vantagem?** Não. O Ibovespa como ETF (sem isenção) e como ações (com a isenção de
R$ 20 mil) difere de 0,01× a 0,02×: o SD Full dá 1,49× contra 1,51× e o constant-mix 1,49× contra 1,50× (no
BOVA11 histórico, 1,24× contra 1,25×). A vantagem já era pequena antes do IR.

## O que fica

- O relatório de 29/10 dizia que o SD vence comprar e segurar em mais da metade dos caminhos. Na versão brasileira
  isso se mantém na mediana, mas a margem é pequena e vem sobretudo do IR adiado de comprar e segurar e do CDI no
  caixa. Em troca, o SD e o constant-mix perdem a cauda de cima.
- O que as regras entregam de forma consistente é **menos risco**: menor queda máxima e p5 maior, sobretudo o
  constant-mix. Se a carteira própria usar alguma delas, o motivo honesto é o controle de risco da camada, não o
  retorno.
- Esta tentativa não abre candidata. As próximas três tentativas da ficha só fazem sentido para uma pergunta nova
  e registrada antes (por exemplo, o teto que reduz a ordem em vez de travá-la).

## Limites e cuidados

- Estudo: não é candidata a dinheiro e não passa pelo critério (pré-registro, ficha P0-7).
- O GBM tem volatilidade constante e não tem saltos. O histórico é um caminho só, visto em janelas sobrepostas: os
  percentis do histórico não são independentes.
- O Monte Carlo usa um calendário sintético: só os meses (IR e DARF) dependem dele.
- Ficou de fora o impacto de mercado. O custo de aquisição do IR não inclui as taxas, o que erra contra quem vende.
- Sem caixa negativo (salvo na versão do relatório): a recompra do SD fica limitada ao caixa.
- O teto e a isenção dependem do capital (R$ 200 mil); com mais capital, o teto pesa mais.
- O day trade paga a taxa à vista (um pouco maior que a de day trade) e é tributado a 20%; o teste (c) roda só na
  B3.
- O cripto é tratado como corretora nacional em reais; o câmbio entra só na variação "com IOF e spread".
- Toda execução conta como tentativa da ficha P0-7 (orçamento de 4; esta é a 1ª).
- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.
