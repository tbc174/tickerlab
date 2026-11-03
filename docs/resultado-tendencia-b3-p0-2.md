# Tendência na B3 (ficha P0-2): resultado (tentativa 1 da P0-2)

**Veredito: REPROVADA.** A candidata, o BOVA11, falhou em A1, A3, A4, A5, A6, A7 e A8; as duas versões de
comparação também reprovaram (WIN nos mesmos sete itens; DI1 em A1, A5, A7 e A8). Rodada única em 03/11/2026,
pelo critério do `docs/pre-registro-quant-p0-v0.1.md` (hash `ea45eddf09e8…`, conferido pelo código antes de
qualquer número). Código: `python -m trader.estrategias.rodar_tendencia_b3`, commit `59065762` (gravado no
registro; o commit seguinte deste PR só muda a formatação do relatório bruto). Registro: linha 12 (família P0-2,
nome `p0_2_tendencia_bova11`) em `pesquisa_quant/registro.db` (fora do Git); 140 tentativas contadas no DSR.
Relatório bruto em `pesquisa_quant/relatorios/rodada_tendencia_b3_20261103_2044.md` (fora do Git).
Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: na bolsa brasileira de 2010 a 2023 a regra de tendência sobre o excesso do BOVA11 ao CDI não achou
tendência nenhuma (Sharpe do excesso −0,16, e o sinal não se distingue do acaso: p-valor 0,59); o único sinal de
verdade apareceu no DI1 de 2 anos, que é só comparação e mesmo assim não chega ao critério (t = 1,75; seriam
≈ 46 anos de dados para t = 3).

## O que o pré-registro pedia (seção 4, ficha P0-2)

- **Ativos:** BOVA11 à vista (a candidata, a mais simples de executar à mão); WIN (futuro, margem a CDI, rolagem
  pelo calendário) e DI1 (vértice de 2 anos, rolado ao ano) como comparação. Três versões pré-registradas,
  nada entre elas.
- **Regra:** a mesma família da P0-1, agora em pregões: nove canais de Donchian ({5, 10, 20, 30, 60, 90, 150,
  250, 360} pregões) sobre o índice do **excesso ao CDI** do ativo; sinal = média dos 9; peso = sinal ×
  min(1; 0,25 ÷ σ de 90 pregões do excesso); posição zerada vai para CDI.
- **Execução:** sinal no fechamento de D, ordem no leilão de abertura de D+1.
- **Régua:** comprar e segurar BOVA11 (líquido) e CDI. **Alternativas (PBO):** nenhuma; A2 não se aplica.
- **Teste do Brasil:** (a) quantas saídas viram day trade (20%); (b) BOVA11 (15% sem isenção) × WIN × cesta das
  10 maiores do Ibovespa (isenção de R$ 20 mil); (c) custo da rolagem do WIN por ano.
- **Orçamento:** 8 tentativas; esta é a primeira.

## Os itens do critério (seção 5 do pré-registro)

| Item | O quê | BOVA11 (candidata) | WIN | DI1 | Limite |
|---|---|---|---|---|---|
| A1 | DSR do Sharpe do excesso com 140 tentativas | 0,001 (SR −0,16): não | 0,001 (SR −0,13): não | 0,164 (SR 0,44): não | ≥ 0,95 |
| A2 | PBO | não se aplica: sim | não se aplica: sim | não se aplica: sim | só com alternativas |
| A3 | platô: menor vizinho ÷ candidato | 0,000: não | 0,000: não | 0,938: sim | ≥ 0,7 |
| A4 | custo, imposto e impacto ÷ Sharpe bruto | bruto −0,07: não | bruto −0,08: não | 0,292 (bruto 0,62): sim | ≤ 0,333 |
| A5 | t-estatística com a correção de Lo | −0,61: não | −0,49: não | 1,75: não | ≥ 3,0 |
| A6 | p-valor dos sinais deslocados | 0,593: não | 0,603: não | 0,008: sim | ≤ 0,05 |
| A7 | limite inferior de 90% da diferença contra as réguas (BOVA11; CDI) | −0,45; −0,59: não | −0,42; −0,56: não | −0,01; −0,00: não | > 0 em todas |
| A8 | estresse (custos × 2, Y = 2, spread × 2): Sharpe do excesso e DSR | −0,21; 0,001: não | −0,17; 0,001: não | 0,37; 0,134: não | ≥ 0,9 |
| F1 | maior queda do pico (líquida, diária) | −10,6%: sim | −10,6%: sim | −2,9%: sim | ≥ −35% |
| V | futuro infla, reexecução idêntica, dados conforme, cortar o futuro | 1,76 > −0,16: sim | 1,88 > −0,13: sim | 1,91 > 0,44: sim | todas |

Com Sharpe negativo, A3 vale zero por definição (o platô só existe em volta de um candidato positivo) e A4 não tem
fração (não há Sharpe bruto a ser comido).

## As três versões

| Versão | Sharpe do excesso | Sharpe (sobre zero) | Retorno anual | Volatilidade | Maior queda | Exposição média | Giro/ano | Custos ÷ capital | IR ÷ capital | Meses com IR |
|---|---|---|---|---|---|---|---|---|---|---|
| BOVA11 | −0,16 | 0,92 | 7,5% | 8,2% | −10,6% | 0,31 | 7,9 | 7,9% | 8,3% | 24 de 160 |
| WIN | −0,13 | 0,94 | 7,8% | 8,3% | −10,6% | 0,31 | 9,5 | 6,8% | 2,3% | 7 de 160 |
| DI1 | 0,44 | 5,19 | 9,7% | 1,9% | −2,9% | 0,46 | 9,5 | 3,6% | 4,8% | 36 de 160 |
| BOVA11 estresse | −0,21 | 0,86 | 7,1% | 8,2% | −11,0% | 0,31 | 7,9 | 15,4% | 7,9% | 26 de 160 |
| WIN estresse | −0,17 | 0,91 | 7,5% | 8,3% | −10,7% | 0,31 | 9,5 | 13,2% | 2,2% | 7 de 160 |
| DI1 estresse | 0,37 | 5,12 | 9,5% | 1,9% | −2,9% | 0,46 | 9,5 | 7,1% | 4,8% | 36 de 160 |

Custos (bolsa, impacto, spread e rolagem) e IR são a soma do período (13,2 anos simulados, de 22/06/2010 a
08/09/2023) dividida pelo capital inicial de R$ 100 mil. O "Sharpe sobre zero" inclui o CDI do caixa e só serve
para leitura; o critério usa o Sharpe do excesso. Freio de 40% no BOVA11: nenhum disparo. Menor caixa ÷
patrimônio do BOVA11: 0,01 (o caixa não ficou negativo).

**Por que a régua perde para o CDI e o Sharpe sobre zero é alto:** com exposição média de 0,31, dois terços do
patrimônio ficam no CDI; o retorno anual de 7,5% é quase todo CDI, e a parte em bolsa rende menos que o CDI.

### Teste do Brasil

- **(a) Day trade:** nenhuma saída virou day trade nas três versões (BOVA11 0, WIN 0, DI1 0). A regra manda uma
  ordem por pregão, no leilão de abertura; as duas pernas da rolagem são contratos diferentes.
- **(b) Imposto:**

| Versão | Sharpe do excesso | IR total | IR por ano | Meses com IR | Meses com vendas acima de R$ 20 mil |
|---|---|---|---|---|---|
| BOVA11 (ETF, 15% sem isenção) | −0,16 | R$ 8.284 | R$ 650 | 24 de 160 | não se aplica |
| WIN (15% sobre o ajuste do mês) | −0,13 | R$ 2.346 | R$ 184 | 7 de 160 | não se aplica |
| cesta das 10 maiores (ações, isenção de R$ 20 mil) | 0,30 | R$ 36.189 | R$ 2.840 | 41 de 160 | 134 |
| cesta, a mesma conta sem a isenção | 0,30 | R$ 36.628 | R$ 2.875 | 43 de 160 | — |

  Com R$ 100 mil e giro de 9 vezes o patrimônio por ano, a cesta vende mais de R$ 20 mil em 134 dos 160 meses:
  a isenção quase não muda o imposto (R$ 439 em 13 anos). O BOVA11 paga mais IR que o WIN porque o ETF é
  tributado a cada venda com lucro, e o WIN só pelo ajuste líquido do mês.
- **(c) Rolagem do WIN:** 58 das 79 rolagens do período tinham posição; R$ 1.092 no período, R$ 86 por ano,
  0,050% do patrimônio médio por ano. O DI1 rolou 12 vezes com posição (0,012% ao ano).

### Réguas, platô e bruto

| Régua | Sharpe (sobre zero) | Retorno anual | Maior queda |
|---|---|---|---|
| BOVA11 comprar e segurar (líquido) | 0,30 | 7,4% | −49,7% |
| CDI | — | 8,9% | 0,0% |

| Vizinho (±20%) | BOVA11 | WIN | DI1 |
|---|---|---|---|
| vol alvo 0,20 | −0,18 | −0,16 | 0,44 |
| vol alvo 0,30 | −0,15 | −0,12 | 0,44 |
| janela da vol 72 | −0,15 | −0,11 | 0,44 |
| janela da vol 108 | −0,15 | −0,13 | 0,44 |
| janelas × 0,8 | −0,18 | −0,13 | 0,43 |
| janelas × 1,2 | −0,14 | −0,11 | 0,41 |
| bruto (sem custo, imposto nem impacto) | −0,07 | −0,08 | 0,62 |
| olhando o futuro (sem custo) | 1,76 | 1,88 | 1,91 |

Contra o acaso (sem custo, como os sinais deslocados): BOVA11 Sharpe real −0,12 contra o percentil 95 de 0,17
(p-valor 0,593); WIN −0,11 contra 0,19 (p-valor 0,603); DI1 0,57 contra 0,46 (p-valor 0,008).

## O que isto diz

- **No BOVA11 não há tendência para seguir.** Mesmo sem custo nem imposto o Sharpe do excesso é negativo
  (−0,07), os seis vizinhos são todos negativos e o sinal não se distingue de sinais deslocados ao acaso. Não é o
  custo que mata a candidata: é a falta de sinal. O próprio BOVA11 rendeu menos que o CDI no período (7,4% contra
  8,9% ao ano, com queda de −49,7%).
- **O WIN confirma o BOVA11.** É a mesma regra sobre o mesmo excesso, com custo e imposto um pouco menores; o
  resultado segue o do BOVA11, como deveria.
- **O DI1 tem sinal, mas não basta.** Os juros prefixados de 2 anos têm tendência que o acaso não explica (p-valor
  0,008), o platô é largo (0,94) e o custo come só 29% do Sharpe bruto. Mas o Sharpe do excesso de 0,44 em 13 anos
  dá t = 1,75, e o DSR com 140 tentativas fica em 0,16. Com t = 3 e SR = 0,44 seriam ≈ 46 anos de dados.
- **Nada muda de versão.** A candidata pré-registrada é o BOVA11; o pré-registro não deixa trocar a candidata pelo
  DI1 depois de ver o resultado. Uma ficha de tendência em juros seria uma ficha nova, escrita antes de qualquer
  número, e entraria no fim da fila.
- **Trilha B não abre.** A P0-2 fica registrada como reprovada na tentativa 1 (orçamento 8); não há papel
  contínuo nem robô.

## Limites e cuidados

- Desenvolvimento só (02/01/2009 a 08/09/2023; simulação de 22/06/2010, depois do aquecimento de 360 pregões):
  nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.
- **Dados:** BOVA11 do Yahoo Finance (barras diárias com `auto_adjust`; o ETF não distribui proventos); barras de
  feriado (volume zero e preço repetido) saem; o calendário da ficha são os pregões do BOVA11 com negócio (desde
  02/01/2009). CDI do SGS 12 do Banco Central. A abertura do Yahoo faz o papel do preço do leilão de abertura.
- **WIN e DI1 são sintéticos:** o WIN é o excesso do BOVA11 ao CDI, com margem a CDI e rolagem pelo calendário dos
  meses pares; o DI1 é o prefixado de 2 anos da curva nominal do acervo menos o CDI, rolado ao ano. Contratos
  fracionários (o capital de R$ 100 mil não compra um número inteiro de DI1 em toda data). O DI1 executa na
  marcação do fechamento de D+1, porque a série não tem abertura. O impacto do WIN usa o volume do BOVA11 (bem
  menor que o do WIN: erra contra a estratégia).
- **A cesta (teste b)** são as 10 maiores participações da carteira teórica do Ibovespa de 03/11/2026 (B3, lida no
  dia) que têm série no `dados_mt5/`: PETR4, VALE3, ITUB4, PETR3, AXIA3, BBDC4, WEGE3, ABEV3, PRIO3 e BBAS3
  (ficaram de fora SBSP3, ITSA4, EMBJ3, B3SA3, BPAC11 e ENEV3, sem série). Lista de hoje aplicada ao passado: viés
  de sobrevivência, que favorece a cesta. Preços ajustados por proventos: o dividendo vira ganho de capital no IR
  (erra contra). A cesta é simulada como um índice de pesos iguais: o rebalanceamento entre os dez papéis não conta
  como venda (favorece a cesta na isenção). Serve só para a comparação de imposto, não é candidata.
- **Itens "a confirmar" lidos na fonte antes do primeiro número** (seção 3 do pré-registro), nas tabelas de tarifas
  da B3 lidas em 03/11/2026: à vista 0,030% (negociação 0,005%, liquidação 0,0224%, registro 0,0026%); ordem no
  leilão de abertura ou de fechamento 0,032% (negociação 0,007%); day trade 0,023% na primeira faixa; WIN R$ 1,97
  por contrato × fator 0,2 do minicontrato = R$ 0,394 por contrato por lado. A tarifa do DI1 está numa tabela em
  imagem e continua **a confirmar**: a rodada usa a do WIN. Como as leituras mudaram valores da v0.1, os custos
  passaram para a **v0.2** (`trader/custos_br.py`), sem mudar o critério.
- **Lote:** BOVA11 em lotes de 100 cotas; WIN, DI1 e cesta fracionários.
- **Convenções fixadas antes de rodar:** não negocia diferença menor que 0,5% do patrimônio; o custo de aquisição
  do IR é o preço pago, sem as taxas (erra contra a estratégia); o DARF sai do caixa mesmo que ele fique negativo;
  o IR dos meses que ainda não venceram é pago no último pregão dos dados.
- **DSR:** as séries testadas são as três versões e os seis vizinhos de cada uma (21 colunas), mais as 119
  tentativas anteriores de todas as fichas (140 no total).
- **Régua do tempo:** anos ≈ (t ÷ SR)²; com Sharpe do excesso negativo no BOVA11, nenhum prazo chega a t = 3.
- Toda execução conta como tentativa; esta é a primeira da ficha P0-2 (orçamento 8).
- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.
