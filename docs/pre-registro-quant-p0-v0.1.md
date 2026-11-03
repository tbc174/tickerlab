# Estratégias quant P0 e carteira própria: pré-registro (critério, fichas, freios, alavancagem e universo)

**Status: APROVADO, versão 0.1, em 03/11/2026 01h18, pelo Tiago** ("Pode, como está", inclusive as sete escolhas da
seção 13). VIGENTE. O hash SHA-256 deste texto fica em `trader/criterio_quant.py` e no registro. Daqui em diante nada
muda sem uma versão nova, com data, motivo e **+25 tentativas** no registro (a mesma regra da M2 e da P2). Nenhum
número de estratégia foi calculado até esta data.

Base: relatório "Estratégias quant cripto e B3" de 29/10/2026 (seção 14, "critério único"), ADR 0118 com a Emenda 1 de
03/11/2026 e o plano v2 (pasta privada do autor), `trader/AGENTS.md`, `trader/custos_br.py` (v0.1) e
`trader/calendario.py`.

> **Aprovada aqui não significa rentável.** Passar no critério só autoriza o que a Emenda 1 diz para cada trilha:
> a camada da carteira própria recebe dinheiro pela mão do Tiago (trilha A) ou a estratégia entra em 3 meses de papel
> (trilha B). Nenhuma ordem automática sem a ADR do robô. Reprovar é um resultado válido e esperado para a maioria.
> Nada aqui é recomendação de investimento.

## 1. O que este documento fixa

1. O **critério único** que todas as P0 (e os fatores na B3) precisam passar (seção 5).
2. Os **freios** da carteira própria (35% global, 40% por camada) e como o backtest os simula (seção 6).
3. A **alavancagem** do núcleo (1,3x via WIN/DI1) e a regra que a derruba para 1,0x (seção 7).
4. O **universo** dos fatores na B3 (seção 8).
5. A **ficha de cada estratégia**: regra, parâmetros fixos, régua, teste do Brasil e orçamento de tentativas
   (seção 9). A ficha diz tudo o que o código pode fazer; o que não está nela não roda nesta versão.

O que fica de fora de propósito: pesos entre as camadas (só depois dos backtests, Emenda 1 item 8), valor do real
pequeno da trilha B, critérios dos agentes analistas (A3; o Tiago escreve antes da primeira rodada).

## 2. Dados e divisão do tempo

| Parte | Período | Uso |
|---|---|---|
| Aquecimento | do início de cada série até 1 ano depois | só para os sinais terem histórico |
| **Desenvolvimento** | **início de cada série a 08/09/2023** | todos os testes deste documento |
| Expurgo | 09/09/2023 a 09/10/2023 | descartado |
| **Holdout** | **10/10/2023 a 09/10/2026** | o mesmo lacre da M2 e da P2 (`holdout.lock`), uma única vez, só para a estratégia que passar A1 a A8 |

- Cada série entra quando tem 1 ano de dados. As séries brasileiras são curtas (BOVA11 desde 2008, BTC em reais
  desde ~2013, NTN-B pela curva do Tesouro); o relatório de cada P0 escreve o primeiro dia útil de cada série e a
  régua de "anos ≈ (t/SR)²" diz se o histórico basta para a conclusão.
- **Ponto no tempo em tudo:** balanço só a partir de `disponivel_em` (data de recebimento na CVM), dado macro só a
  partir da divulgação, feriado como era conhecido na data (`base/dias_uteis.py`), composição de índice e cadastro
  pela data (`base/ponto_no_tempo.py`).
- **Deslistadas:** o universo de ações é o histórico, com as que deixaram de existir. Se a base não tiver as
  deslistadas de um período, o relatório declara **viés de sobrevivência** e a estratégia **não pode receber
  dinheiro** até o universo ser completado (nova versão).
- Nada é lido do holdout fora da rotina de `trader/holdout.py` (`carregar_desenvolvimento`, `exigir_sem_holdout`).

## 3. Custos (em todos os testes)

Tudo pelo `trader/custos_br.py` v0.1, com os valores da tabela de lá (corretagem, emolumentos de 0,03% à vista,
IR de 15% no swing e 20% no day trade, isenção de R$ 20 mil só em ações, 15% em cripto com isenção de R$ 35 mil
[não verificado], aluguel com mínimo de R$ 10, IOF e spread de câmbio). Caixa a CDI diário
(`src/cdi.retorno_diario_do_caixa`). Lote de 100 (ou fracionário, dito na ficha).

- **Estresse:** `em_estresse` (dobra corretora e bolsa; não mexe em lei).
- **Itens "a confirmar"** (tarifas de day trade, futuros, cripto, isenção de R$ 35 mil): lidos na fonte antes do
  primeiro número; o relatório diz o valor lido e a data. Se a leitura mudar um valor da v0.1 dos custos, isso é
  versão nova dos custos (v0.2), **não** do critério.
- **Impacto de mercado:** raiz quadrada (Y·σ·√(Q/V)) com Y = 1 para ações e cripto; o relatório diz quanto do
  resultado some com Y = 2.

## 4. Calendário e execução

- **Sinal no fechamento do dia D, execução em D+1** (`calendario.proxima_execucao`): no leilão de abertura (P0-2,
  fatores) ou no fechamento de D+1 (as demais), dito na ficha. Nunca no mesmo dia. Há teste (V1) de que usar o
  sinal do próprio dia infla o resultado.
- **WIN:** rolagem no pregão anterior ao vencimento (`rolagem_do_win`), com o custo das duas pernas.
  **DI1:** vértice de janeiro mais perto de 2 anos (`di1_de_janeiro`), rolado uma vez por ano no primeiro pregão de
  dezembro.
- **Cripto:** 365 dias; sinal à meia-noite de Brasília, execução no dia seguinte.
- **Execução real (trilha A) pela mão do Tiago no dia seguinte:** o backtest simula exatamente esse atraso.

## 5. Critério único de aprovação (vale para cada P0 e para os fatores na B3)

Todos os itens precisam passar; a medição é no desenvolvimento, com retornos diários líquidos de custo e imposto.

| # | Critério | Limite | Origem |
|---|---|---|---|
| A1 | Sharpe líquido **sobre o CDI** > 0 e Sharpe deflacionado (DSR) com N = **todas** as tentativas do registro (101 da M2 + P2 + scalp + estas) | DSR ≥ 0,95 | seção 14 |
| A2 | PBO por CSCV, onde há parâmetro escolhido entre alternativas | ≤ 0,30 | seção 14 |
| A3 | Platô: ±20% em cada parâmetro mantém ≥ 70% do Sharpe | ≥ 70% | seção 14 |
| A4 | Custo + imposto consomem no máximo ⅓ do Sharpe bruto | ≤ ⅓ | seção 14 |
| A5 | t-estatística do retorno médio diário líquido (correção de Lo para autocorrelação) | ≥ 3,0 | **acréscimo** (seção 6.1 do relatório; já é o A3 da M2 e da P2) |
| A6 | Contra o acaso: Sharpe acima do percentil 95 de 1.000 sinais deslocados no tempo | p ≤ 0,05 | **acréscimo** (A10 da M2 e da P2) |
| A7 | Contra a régua da ficha: limite inferior de 90% (bootstrap em blocos de 21 dias) da diferença de Sharpe estratégia − régua | > 0 | **acréscimo** (A5 da P2; é o que "retorno alto" exige) |
| A8 | Estresse de custos (seção 3) e impacto com Y = 2: Sharpe líquido > 0 e DSR ≥ 0,90 | os dois | seção 14 + M2 |
| F1 | **Queda máxima da estratégia (do pico, diária, líquida) no desenvolvimento** | ≤ 35% | Emenda 1, item 5 ("regra que passa de 35% no passado não entra") |
| V | Verificações: (1) sinal do próprio dia infla o resultado; (2) reexecução idêntica (mesmo hash de saída); (3) nenhum dado antes da data pública; (4) cortar o futuro não muda o passado | todas | M2, P2 e `trader/AGENTS.md` |

**Holdout (só se A1 a A8, F1 e V passarem, e só com decisão escrita do Tiago, como na M2):** B1 Sharpe no holdout
≥ 50% do de desenvolvimento e ≥ 0,30; B2 queda máxima no holdout ≤ 1,5× a do desenvolvimento; C MinTRL com 95%
cabe no histórico. Uma única abertura por estratégia.

Estratégia sem parâmetro escolhido (todos fixos da literatura, como na P2) declara "A2 não se aplica" na ficha e
não pode variar nada depois. PBO só existe onde a ficha lista alternativas, e todas as alternativas contam.

## 6. Freios da carteira própria (Emenda 1, itens 5 e 6)

- **Freio global: queda de 35% do pico da carteira inteira** (patrimônio líquido diário, marcado a mercado, imposto
  do mês provisionado). Disparou: tudo vai para CDI no pregão seguinte e só volta com revisão escrita do Tiago.
- **Freio por camada: queda de 40% do pico da própria camada**: aquela camada vai para CDI no pregão seguinte.
- **Como o backtest simula:** cada estratégia roda **com e sem** o freio de 40% (o relatório mostra os dois). No
  backtest, a camada freada **volta no primeiro pregão 12 meses depois do disparo** (o equivalente da revisão anual;
  proposta do Claude, aprovada com o texto, para o freio ter uma regra de volta que não dependa de ninguém olhar o resultado). O freio global de
  35% só existe quando houver carteira montada (PR 9) e é simulado sobre a soma das camadas com os pesos que o
  Tiago fixar depois dos backtests.
- **`trader/freios.py`** terá teste de que o freio dispara nas datas certas num histórico artificial e de que nunca
  usa o fechamento do próprio dia para sair.

## 7. Alavancagem do núcleo (Emenda 1, item 8)

- Só na camada A1 (multiativo P0-3 + fatores B3), via WIN (índice) ou DI1 (juros), nunca em cripto nem em A2 e A3.
- Duas versões, as duas pré-registradas: **1,0x** e **1,3x** (exposição total ÷ patrimônio, medida todo dia; margem
  dos futuros rende CDI; rolagem pelo calendário). **Nada entre as duas**: não existe "1,15x escolhido depois de
  olhar".
- Regra: a versão 1,3x só entra se passar o critério inteiro, **inclusive F1 (queda ≤ 35%)**. Se a 1,3x reprovar e
  a 1,0x passar, a camada opera a 1,0x (é o que a Emenda 1 manda, e não é "escolher depois de ver", porque a regra
  de queda está escrita aqui antes).
- O relatório mostra, para as duas: queda máxima, Sharpe, custo de rolagem por ano e quantos dias a margem exigida
  passou de 30% do patrimônio (aviso de chamada de margem).

## 8. Universo dos fatores na B3

- Todas as ações (ON, PN e units) com **volume financeiro médio diário ≥ R$ 5 milhões nos 60 pregões anteriores**
  ao dia do rebalanceamento [a confirmar pelo Tiago; a Emenda 1 diz "proposta: R$ 5 milhões"], inclusive as que
  deixaram de existir. Uma classe por empresa (a mais líquida).
- Fora: BDRs, ETFs, FIIs, ações em recuperação judicial no dia (fato público), ações com menos de 12 meses de
  pregão, ações sem balanço disponível (`disponivel_em`) nos últimos 12 meses.
- O universo é recalculado **a cada rebalanceamento mensal**, só com dados até aquele dia.

## 9. Fichas

Cada ficha tem: regra; parâmetros fixos (tudo o que tem número); alternativas que entram no PBO (se houver);
régua (A7); execução; teste só por causa do Brasil; orçamento de tentativas. **Orçamento total desta versão: 60
tentativas** (soma das fichas); reexecução e correção de defeito contam.

### Ficha F-B3. Fatores na B3 (camada A1, parte 2; não era P0 do relatório, entrou pela Emenda 1)

- **Regra:** no primeiro pregão de cada mês, para cada ação do universo (seção 8), quatro notas em escore-z dentro do
  universo: **valor** (lucro operacional dos últimos 12 meses ÷ valor da firma), **qualidade** (retorno sobre o
  patrimônio dos últimos 12 meses, com o balanço disponível na data), **momento** (retorno dos 12 meses anteriores
  pulando o último), **baixa volatilidade** (menos o desvio dos retornos diários de 252 pregões). Nota final = média
  simples das quatro. **Comprado nas 20% melhores, pesos iguais, sem vender a descoberto** (aluguel e recall no
  Brasil inviabilizam a perna vendida nesta versão). Rebalanceamento mensal com banda de 20% do peso-alvo.
- **Parâmetros fixos:** 4 fatores, pesos iguais, quintil, 252 pregões de vol, momento 12-1, banda 20%.
- **Alternativas (PBO):** nenhuma. A2 não se aplica.
- **Régua:** Ibovespa total em reais, líquido do imposto de um ETF (15% nas vendas do rebalanceamento), e CDI.
- **Execução:** leilão de abertura do pregão seguinte; lote de 100 (fracionário para o que sobrar).
- **Teste do Brasil:** (a) com e sem as deslistadas (quanto o viés de sobrevivência infla); (b) a isenção de R$ 20
  mil de vendas no mês muda o resultado para uma carteira de R$ 100 mil, R$ 500 mil e R$ 2 milhões? (c) o
  rebalanceamento pela chegada do balanço (`disponivel_em`) contra a versão proibida (data do balanço).
- **Orçamento:** 10 tentativas.

### Ficha P0-3. Carteira multiativo brasileira (camada A1, parte 1)

- **Ativos:** CDI, NTN-B (índice sintético pela curva do Tesouro, prazo de 5 anos), Ibovespa (BOVA11), ouro em
  reais, S&P 500 em reais (sem proteção cambial).
- **Regra:** rebalanceamento mensal com banda de 20% do peso-alvo; três esquemas de peso, **os três
  pré-registrados** e comparados: inverso da volatilidade (σ de 252 pregões), risk parity (contribuição igual ao
  risco, covariância de 252 pregões) e mínima variância com teto de 40% por ativo. **O candidato à carteira é o
  risk parity**; os outros dois são comparação e não viram candidato nesta versão.
- **Alternativas (PBO):** nenhuma (o candidato está escolhido antes). A2 não se aplica.
- **Régua:** carteira 60/40 (BOVA11 e CDI) rebalanceada ao mês, líquida; e CDI.
- **Execução:** fechamento do pregão seguinte.
- **Teste do Brasil:** o imposto do ETF (15% sem isenção) zera o ganho do rebalanceamento? Comparar rebalancear
  vendendo contra rebalancear só por aporte mensal (1% do patrimônio).
- **Orçamento:** 8 tentativas.

### Ficha P0-1. Tendência em cripto em reais (camada A2; candidata ao trade 24/7)

- **Ativos:** BTC e ETH em reais (BTCBRL e ETHBRL da Binance, ou o par em USDT × dólar já conhecido na véspera;
  a ficha de dados diz qual, e o resultado usa a mesma série do começo ao fim).
- **Regra:** conjunto de canais de Donchian com janelas {5, 10, 20, 30, 60, 90, 150, 250, 360} dias; comprado quando
  o fechamento passa a máxima da janela, zerado quando cai abaixo do meio do canal; sinal = média dos 9 sinais;
  peso = sinal × min(1; 0,25 ÷ σ de 90 dias anualizada); **alavancagem ≤ 1, sem perpétuos**; caixa a CDI; BTC e
  ETH com metade do capital cada.
- **Parâmetros fixos:** as 9 janelas, 25% de vol alvo, σ90, 50/50.
- **Alternativas (PBO):** nenhuma. A2 não se aplica.
- **Régua:** comprar e segurar BTC em reais (líquido); e CDI.
- **Execução:** fechamento do dia seguinte (365 dias).
- **Teste do Brasil:** (a) caixa a CDI contra caixa a 0%; (b) quantos meses passam do teto de R$ 35 mil de vendas e
  quanto imposto geram; (c) IOF e spread de câmbio contra a série em USDT.
- **Trilha B:** passou → 3 meses em papel contínuo (sinais gravados na hora, hash e data). O real pequeno e o robô
  vêm só com a ADR própria.
- **Orçamento:** 10 tentativas.

### Ficha P0-2. Tendência na B3 (camada A2)

- **Ativos:** BOVA11 (à vista), WIN (futuro, margem a CDI, rolagem pelo calendário) e DI1 (vértice de 2 anos,
  rolado ao ano); **três versões pré-registradas e comparadas**; a candidata à carteira é o BOVA11 (a mais simples
  de executar à mão); WIN e DI1 são comparação.
- **Regra:** a mesma família da P0-1 (9 janelas de Donchian, sinal médio, vol alvo de 25%, σ90) sobre o **excesso
  ao CDI** do ativo; posição zerada vai para CDI.
- **Alternativas (PBO):** nenhuma. A2 não se aplica.
- **Régua:** comprar e segurar BOVA11 (líquido); e CDI.
- **Execução:** leilão de abertura do pregão seguinte.
- **Teste do Brasil:** (a) quantas saídas viram day trade (20%); (b) BOVA11 (15% sem isenção) × WIN × cesta das 10
  maiores do Ibovespa (isenção de R$ 20 mil); (c) custo da rolagem do WIN por ano.
- **Orçamento:** 8 tentativas.

### Ficha P0-7. Simulador do Synthetic Dividend e rebalanceamento

- **Escopo:** Full, só em máxima histórica, comprar e segurar e constant-mix com banda adaptativa r = σ ÷ √F; Monte
  Carlo (GBM, 2.000 caminhos, 3 anos) e histórico de BTC e Ibovespa em reais; saídas: mediana, p5 e p95.
- **Não é candidata a dinheiro:** é estudo (responde a pergunta original do relatório) e teste de ponta a ponta dos
  custos. Não passa pelo critério da seção 5; o relatório é educativo e mostra onde perde para comprar e segurar.
- **Teste do Brasil:** o CDI aumenta a vantagem do constant-mix? O teto de vendas e o bloqueio de day trade mudam
  o resultado?
- **Orçamento:** 4 tentativas.

### Ficha P0-4. Pares por cointegração na B3

- **Regra:** formação de 12 meses, operação nos 6 seguintes (janelas rolando a cada 6 meses); Engle-Granger com
  valores críticos de MacKinnon e correção de Benjamini-Hochberg para o número de pares testados; meia-vida entre 5
  e 30 dias; entrada |z| > 2, saída |z| < 0,5, stop |z| > 4 ou 3× a meia-vida; no máximo 10 pares ao mesmo tempo,
  pesos iguais; universo da seção 8.
- **Alternativas (PBO):** nenhuma. A2 não se aplica.
- **Régua:** CDI (estratégia neutra ao mercado).
- **Execução:** fechamento do pregão seguinte; a perna vendida paga aluguel (seção 3).
- **Teste do Brasil:** aluguel a 2, 5 e 10% a.a. com mínimo de R$ 10 (até haver histórico de taxas por papel);
  lote de 100 e holding ≥ 1 pregão; pares ON/PN contra pares de setor; OPA e deslistagem.
- **Orçamento:** 8 tentativas.

### Ficha P0-5. Eventos do IPE da CVM e PEAD

- **Regra:** retorno anormal acumulado (+1, +60) por tipo de documento do IPE (modelo de mercado, 252 pregões
  antes); PEAD: surpresa de lucro padronizada (sazonal, 8 trimestres), comprado no tercil de cima, entrada em D+2
  da **data de recebimento** no IPE, saída em 60 pregões; universo da seção 8.
- **Alternativas (PBO):** nenhuma. A2 não se aplica.
- **Régua:** Ibovespa líquido e CDI.
- **Execução:** leilão de abertura de D+2.
- **Teste do Brasil:** dia zero = D+1 (o IPE não tem hora) contra dia zero = D (otimista e **proibida** no
  resultado final).
- **Orçamento:** 6 tentativas.

### Ficha P0-6. Monitor de funding e basis em cripto

- **Escopo:** coleta e monitor; **nenhuma ordem, nenhum backtest de estratégia**. Alerta quando o funding anualizado
  líquido passar de 10% a.a. e quando o carry em reais (funding em dólar + CDI − cupom cambial) passar do CDI.
- Não passa pelo critério da seção 5. Binance só para uso interno (licença CC BY-NC-SA).
- **Orçamento:** 2 tentativas (só reexecução da coleta).

### Ficha P0-8. Filtro de regime com variáveis observáveis

- **Regra:** liga ou desliga cada estratégia por um filtro com atraso de um dia: preço acima da média de 200 dias,
  percentil da vol realizada de 21 dias abaixo de 90%, drawdown do ativo acima de −20%, ciclo da Selic pelo Focus
  (próximas reuniões), funding e open interest fora dos extremos (cripto). Regras de corte fixas (as deste parágrafo).
- **Teste:** cada estratégia aprovada **com e sem** o filtro. O filtro só entra se melhorar o DSR sem piorar o PBO
  nem a queda máxima. HMM fica para uma versão nova.
- **Orçamento:** 4 tentativas.

## 10. Tentativas e honestidade

- Registro único (`trader/registro.py`); o DSR de toda estratégia usa N = tudo o que o registro tem.
- Orçamento desta versão: **60 tentativas** (seção 9). Esgotou: versão nova, +25.
- Defeito corrigido depois de ver um resultado é tentativa nova, explicada no relatório.
- Candidatos fixos em cada ficha. Uma comparação que vence o candidato **não vira candidato** nesta versão.
- Rodada sem o hash deste texto não roda (`trader/criterio_quant.py` confere, como `trader/p2/preregistro.py`).
- Cada relatório de resultado tem a seção "Limites e cuidados" e diz o que reprovou.

## 11. Fora de escopo nesta versão

Machine learning e HMM; perpétuos e alavancagem em cripto; alavancagem fora do núcleo ou acima de 1,3x; perna
vendida nos fatores; intradiário; busca de parâmetros; ordens reais; agentes analistas (A3, documento próprio).

## 12. Limitações declaradas

- Séries brasileiras curtas: várias conclusões ficarão "inconclusivas" pela régua de anos ≈ (t/SR)², e o relatório
  dirá isso em vez de aprovar.
- Deslistadas: dependem do que a base tem (seção 2).
- Tarifas "a confirmar" dos custos; impacto de mercado com Y não medido no Brasil.
- Custos e impostos de hoje aplicados ao passado inteiro.
- O freio por camada no backtest usa uma regra de volta mecânica (12 meses) que na vida real é uma revisão escrita.
- Os agentes analistas (A3) não têm backtest honesto e por isso não estão aqui.

## 13. Escolhas aprovadas junto com o texto

Estas escolhas foram propostas pelo Claude e aprovadas pelo Tiago com o texto (03/11/2026 01h18); fazem parte do
critério como qualquer outro item.

1. Os **acréscimos A5, A6 e A7** ao critério único da seção 14 (t ≥ 3; contra o acaso; contra a régua): sem A7,
   "retorno alto" não é medido contra nada.
2. **F1 = 35% de queda máxima no desenvolvimento** para toda estratégia, não só para a alavancagem.
3. A **volta do freio de 40%** no backtest em 12 meses.
4. **Piso de liquidez de R$ 5 milhões** (60 pregões) e os **4 fatores em pesos iguais, só comprados, quintil**.
5. **Candidatos fixos:** risk parity na P0-3; BOVA11 na P0-2; BTC e ETH 50/50 na P0-1.
6. **Orçamento de 60 tentativas** nesta versão.
7. P0-7 e P0-6 **sem critério** (estudo e monitor, não candidatas a dinheiro).
