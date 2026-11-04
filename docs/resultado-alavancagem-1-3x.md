# Núcleo (ficha P0-3) a 1,3x via WIN e via DI1, e os freios: resultado (tentativa 4 da P0-3)

**Veredito: nenhuma versão entra.** A 1,0x continua reprovada (A1, A5, A6 e A8, os mesmos itens da tentativa 3);
a 1,3x via WIN reprova em A1, A5, A6, A7 e A8; a 1,3x via DI1 reprova em A1, A5, A6 e A8. Rodada única em
03/11/2026, pelo critério do `docs/pre-registro-quant-p0-v0.1.md` (hash `ea45eddf09e8…`, conferido pelo código
antes de qualquer número). Código: `python -m trader.estrategias.rodar_alavancagem` (o conteúdo deste PR; o
registro gravou o commit `a7b113ab` porque o código ainda não estava commitado quando rodou). Registro: linhas 9
(1,3x WIN) e 10 (1,3x DI1) da família P0-3 em `pesquisa_quant/registro.db` (fora do Git), mais a terceira execução
da linha 5 (a 1,0x, mesma configuração da tentativa 3); 118 tentativas contadas no DSR. Relatório bruto da rodada em
`pesquisa_quant/relatorios/rodada_alavancagem_20261103_1843.md` (fora do Git).
Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: alavancar o núcleo pelo WIN piora tudo (Sharpe do excesso de 0,41 para 0,17, queda máxima de −11,3%
para −26,9%); pelo DI1 quase não muda (0,42 e −12,6%); nenhum dos três passa do acaso, e o freio de 40% não dispara
nenhuma vez em 13 anos de desenvolvimento, porque nenhuma versão cai 40% do pico.

## O que o pré-registro pedia (seções 6 e 7)

- **Duas versões só:** 1,0x e 1,3x (exposição total ÷ patrimônio, medida todo dia; a 1,3x ajustada no primeiro
  pregão de cada mês e nas rolagens), nada entre as duas. A 1,3x só entra se passar o critério inteiro, inclusive F1.
- **Margem a CDI, rolagem pelo calendário:** WIN roda no pregão anterior ao vencimento (meses pares); DI1 troca o
  contrato de janeiro quando o vértice de 2 anos muda (perto de julho).
- **Queda máxima com e sem freio:** cada versão roda com e sem o freio de 40% por camada; o freio global de 35%
  e a volta em 12 meses ficam em `trader/freios.py` (testados num histórico artificial e nas datas de 2008 e 2020).

## Os itens do critério (seção 5 do pré-registro)

| Item | O quê | 1,0x | 1,3x WIN | 1,3x DI1 | Limite |
|---|---|---|---|---|---|
| A1 | DSR do Sharpe do excesso com 118 tentativas | 0,557 (não) | 0,241 (não) | 0,575 (não) | ≥ 0,95 |
| A2 | PBO | não se aplica | não se aplica | não se aplica | só com alternativas |
| A3 | platô: menor vizinho ÷ candidato | 0,919 | 0,901 | 0,927 | ≥ 0,7 |
| A4 | custos como fração do Sharpe bruto | 0,177 | 0,218 | 0,164 | ≤ 0,333 |
| A5 | t-estatística com a correção de Lo | 1,756 (não) | 0,688 (não) | 1,777 (não) | ≥ 3,0 |
| A6 | p-valor dos sinais deslocados (o da base) | 0,320 (não) | 0,320 (não) | 0,320 (não) | ≤ 0,05 |
| A7 | contra as réguas: limite inferior de 90% | 0,034 | −0,234 (não; perde do CDI) | 0,037 | > 0 em todas |
| A8 | estresse (custos × 2, Y = 2, spread × 2): DSR | 0,548 (não) | 0,231 (não) | 0,566 (não) | ≥ 0,9 |
| F1 | maior queda do pico (líquida, diária) | −11,3% | −26,9% | −12,6% | ≥ −35% |
| V | futuro infla, reexecução idêntica, dados conforme, cortar o futuro | sim | sim | sim | todas |

## As três versões (custos base)

| Versão | Sharpe do excesso | Sharpe | Retorno anual | Volatilidade | Maior queda | Com freio 40% | Custo de rolagem/ano | Dias com margem > 30% | Exposição média |
|---|---|---|---|---|---|---|---|---|---|
| 1,0x | 0,41 | 1,58 | 11,9% | 7,6% | −11,3% | −11,3% | 0 | 0 | 1,00 |
| 1,3x WIN | 0,17 | 0,79 | 11,3% | 14,3% | −26,9% | −26,9% | 0,05% | 0 | 1,30 |
| 1,3x DI1 | 0,42 | 1,53 | 12,2% | 8,0% | −12,6% | −12,6% | 0,007% | 0 | 1,30 |

Estresse (custos × 2, impacto Y = 2, spread × 2): os mesmos números até a segunda casa (WIN 0,16; DI1 0,42; custo de
rolagem dobra: 0,10% e 0,014% ao ano). A margem exigida nunca passa do aviso de 30% do patrimônio (WIN 15% e DI1 5%
do nocional, valores a confirmar na B3): com 0,3 de patrimônio em nocional, a garantia fica em 5% (WIN) e 1,6%
(DI1) do patrimônio.

## Freios (seção 6)

- **Por camada (40%):** nenhum disparo em nenhuma versão entre 2010 e 2023; a maior queda é a do WIN (−26,9%).
- **Global (35%):** com o núcleo só, a carteira é a própria camada A1; a queda fica longe dos 35%.
- O que está testado: no histórico artificial, o freio dispara no dia em que o fechamento cruza o limite, sai no
  pregão seguinte (nunca no fechamento do próprio dia), fica em CDI e volta no primeiro pregão 12 meses depois, com
  o pico recomeçando na volta; com o calendário real da B3, dispara em 29/09/2008 e 12/03/2020 num histórico
  plantado para cruzar o limite nessas datas. Os dados de desenvolvimento começam em 12/05/2010: a crise de 2008
  não está na rodada real.

## Réguas, platô e bruto

| Régua | Sharpe | Retorno anual | Maior queda |
|---|---|---|---|
| 60/40 (BOVA11 60%, caixa no CDI 40%, rebalanceio mensal) | 0,58 | 8,3% | −29,2% |
| CDI | — | 8,9% | 0,0% |

| Vizinho | 1,0x | 1,3x WIN | 1,3x DI1 |
|---|---|---|---|
| janela 202 | 0,37 | 0,15 | 0,39 |
| janela 302 | 0,39 | 0,16 | 0,41 |
| banda 16% | 0,41 | 0,17 | 0,42 |
| banda 24% | 0,41 | 0,17 | 0,43 |
| bruto (sem custo, imposto, impacto nem spread) | 0,49 | 0,22 | 0,50 |

## O que isto diz

- **A alavancagem não cria o que a base não tem.** A 1,3x multiplica o excesso sobre o CDI da base (que é pequeno e
  não se distingue do acaso: p-valor 0,32) e soma a perna do futuro. Pelo WIN, a perna é o BOVA11 menos o CDI, que
  no período rende menos que o CDI com muita volatilidade: a versão perde do CDI (A7) e dobra a queda. Pelo DI1,
  a perna é o prefixado de 2 anos menos o CDI: quase zero no período, com pouco risco; a versão fica igual à base.
- **O freio de 40% nunca aparece neste núcleo**, que tem 7,6% de volatilidade; ele é feito para as camadas de
  risco (fatores, cripto), não para o núcleo. Fica medido e pronto para os próximos PRs.
- **Profit Ultra:** a pergunta que ficou para depois deste backtest (nível 1, Tiago em 03/11) era se vale assinar
  para ter o histórico do WIN e do DI1. As pernas sintéticas respondem a forma do resultado (o WIN piora, o DI1
  não muda); o que a assinatura acrescentaria é a base de mercado dos futuros, que não muda a conclusão sobre o
  critério, porque o problema está na base (A1, A5, A6), não na perna. A decisão continua do Tiago.

## Limites e cuidados

- Desenvolvimento só (12/05/2010 a 08/09/2023): nada aqui diz o que o holdout vai mostrar; abri-lo é decisão
  escrita do Tiago.
- **Pernas sintéticas:** não há histórico do WIN nem do DI1 na base. O WIN é o BOVA11 em reais menos o CDI (fica
  de fora a base de mercado do futuro e o descasamento entre o Ibovespa e o ETF); o DI1 é um prefixado de prazo
  constante de 2 anos marcado no vértice de 2 anos da curva nominal do Tesouro Direto menos o CDI (sem a base entre
  a curva do Tesouro e a da B3). Os dois erram a favor do backtest: a base de mercado e o spread real tendem a
  custar mais, não menos.
- Margem exigida (WIN 15%, DI1 5% do nocional), valor do contrato (WIN R$ 20 mil, DI1 R$ 80 mil), tarifa por
  contrato e spread (0,01% por lado) são aproximações marcadas "a confirmar"; os contratos são fracionários.
- O caixa de margem pode ficar negativo dentro do mês (empréstimo ao CDI) até o ajuste do primeiro pregão; na
  vida real seria um aporte ou um corte da posição.
- O item A6 (contra o acaso) é o da base (os pesos do risk parity): a alavancagem não tem sinal próprio para
  deslocar.
- A soma das camadas no `freiar_carteira` usa pesos fixos por dia (sem rebalanceio entre camadas): simplificação
  declarada, suficiente para o núcleo só.
- Toda execução conta como tentativa; esta é a quarta da ficha P0-3 (orçamento 8). Os 118 tentativas do DSR
  incluem as de todas as fichas até aqui.
- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.
