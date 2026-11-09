# Estratégias quant P0 e carteira própria: pré-registro (critério, fichas, freios, alavancagem e universo)

**Status: RASCUNHO da versão 0.3, escrito em 09/11/2026, esperando a aprovação do Tiago.** Enquanto não for
aprovado, vale a v0.2 (aprovada em 04/11/2026 03h31, SHA-256 `abea3c855641…`, guardada em
`docs/pre-registro-quant-p0-v0.2.md`), e nenhuma rodada usa este texto. Com a aprovação, esta linha passa a dizer a
data e as palavras do Tiago, o hash desta versão entra em `trader/criterio_quant.py` e, como manda a seção 10, a
versão soma **+25 tentativas** ao registro.

**A v0.3 só acrescenta o HMM** (modelo oculto de Markov, que estima em que "regime" o mercado está). A v0.1 e a v0.2
já diziam que o HMM "fica para uma versão nova" (ficha P0-8 e seção 11). Esta é essa versão. Ela acrescenta três
fichas (H-1, H-2 e H-3, na seção 9) e põe as séries delas no papel (seção 5). **Nenhuma régua, nenhum limite do
critério e nenhum parâmetro das fichas da v0.2 muda.** A seção 16 diz o que mudou e por quê, e a seção 17 lista as
escolhas para o Tiago aprovar.

**Como a v0.2, a v0.3 foi escrita DEPOIS de ver os resultados**: todas as fichas que rodaram foram reprovadas
(seção 16). O HMM não foi escolhido por causa de um resultado, porque estava previsto desde a v0.1, escrita antes de
qualquer número. Mas a decisão de testá-lo agora veio depois dos resultados, e o período de desenvolvimento já foi
visto por 158 tentativas. Por isso, só o papel e o holdout dão uma prova limpa (seção 12).

O texto da v0.2 segue abaixo, igual, com as marcas **(v0.3)** onde algo foi acrescentado.

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
6. **(v0.2)** A **carteira combinada** das camadas (ficha C-1) e a tendência em cripto no **par em reais**
   (ficha P0-1b).
7. **(v0.2)** Como o **papel** (sinais gravados daqui para a frente, sem dinheiro) é julgado (seção 5).
8. **(v0.3)** O **HMM**: um modelo comum (seção 9, "Modelo HMM das fichas H"), a alocação por regime no BOVA11
   (ficha H-1) e em BTC e ETH (ficha H-2) e o HMM como filtro de uma estratégia aprovada (ficha H-3).

O que fica de fora de propósito: pesos entre as camadas da carteira real (só depois dos backtests, Emenda 1 item 8;
a regra de pesos da ficha C-1 é só a do teste e não fixa a carteira do Tiago), valor do real
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

**Holdout da C-1 (v0.2):** a C-1 é feita das camadas. Abrir o holdout dela mostra o holdout de cada camada e o do
BTC e do ETH, que a P0-1b também usa. Por isso, abrir o holdout da C-1 gasta o lacre da C-1, das seis camadas dela e
da P0-1b, e nenhuma delas abre de novo.

**Papel (v0.2):** os dados que chegam depois da aprovação desta versão não foram vistos por nenhuma tentativa. O papel
grava, todo dia, o sinal e a carteira simulada de cada série da lista abaixo, com o hash e a data, antes do pregão em
que valeriam. Nada vai para corretora. O papel não é candidatura: uma série que passa no papel continua sem dinheiro,
e só uma ficha nova, numa versão nova, pode fazer dela uma candidata.

| Série gravada | Sharpe do excesso de referência (desenvolvimento) |
|---|---|
| carteira multiativo (P0-3, risk parity a 1,0x, registro 5) | 0,41 |
| tendência em cripto (P0-1, registro 11, série em USDT × PTAX) | 0,68 |
| tendência no DI1 (a versão de comparação da P0-2, registro 12) | 0,44 |
| C-1, candidata e comparação (seção 9) | o da 1ª tentativa de cada uma |
| P0-1b (seção 9), se rodar | o da 1ª tentativa |
| **(v0.3)** H-1, alocação por regime no BOVA11 (seção 9), se rodar | o da 1ª tentativa |
| **(v0.3)** H-2, alocação por regime em BTC e ETH (seção 9), se rodar | o da 1ª tentativa |

- **Início único:** o primeiro pregão depois do merge do código que grava o papel. Todas as séries começam no mesmo
  dia, e a cripto grava todo dia corrido. **(v0.3)** As séries H-1 e H-2 começam no primeiro pregão depois do merge do
  código que as grava, e o julgamento delas conta 12 meses a partir desse dia. O HMM do papel é reestimado como no
  backtest (no primeiro dia de cada mês, com os dados até o fim do mês anterior). O papel não reestima nada fora
  dessa regra.
- **Julgamento 12 meses corridos depois do início**, com os mesmos custos e impostos da série:

| # | Critério do papel | Limite |
|---|---|---|
| P1 | Sharpe do excesso sobre o CDI no papel | > 0 e ≥ 50% do de referência da tabela acima |
| P2 | Queda máxima no papel | ≤ 1,5 × a do desenvolvimento da mesma série |
| P3 | Gravação: cada dia tem hash e data anteriores ao pregão; nenhum dia regravado; no máximo 5 dias sem gravação | todos |

- **Dia sem gravação** conta como falta e nunca é preenchido depois. **Defeito de código ou de dado** no papel:
  corrige-se dali para a frente, os dias já gravados ficam como estão e o relatório conta o defeito.
- **Resultado:** passou, a série ganha mais 12 meses de papel; não passou, sai da lista. **No máximo duas
  renovações** (36 meses). Depois disso, a série sai da lista ou entra numa ficha nova, numa versão nova, com o
  papel inteiro como dado.
- Passar no papel não é aprovação: com 12 meses o t fica longe de 3. Dinheiro continua pedindo A1 a A8, F1, V e o
  holdout. O papel não gasta tentativa, porque só grava o que a regra registrada manda e não muda nada nela.

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
  ao dia do rebalanceamento (aprovado com o texto da v0.1, seção 13, item 4; a marca "a confirmar" que estava aqui
  sobrou do rascunho), inclusive as que deixaram de existir. Uma classe por empresa (a mais líquida).
- Fora: BDRs, ETFs, FIIs, ações em recuperação judicial no dia (fato público), ações com menos de 12 meses de
  pregão, ações sem balanço disponível (`disponivel_em`) nos últimos 12 meses.
- O universo é recalculado **a cada rebalanceamento mensal**, só com dados até aquele dia.

## 9. Fichas

Cada ficha tem: regra; parâmetros fixos (tudo o que tem número); alternativas que entram no PBO (se houver);
régua (A7); execução; teste só por causa do Brasil; orçamento de tentativas. **Orçamento total desta versão: 78
tentativas** (soma das fichas; eram 60 na v0.1, a v0.2 somou 8 das fichas C-1 e P0-1b e a v0.3 soma 10 das fichas
H-1, H-2 e H-3); reexecução e correção de defeito contam.

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
  nem a queda máxima. HMM fica para uma versão nova. **(v0.3)** Essa versão é esta: o HMM como filtro está na
  ficha H-3, à parte. Nada na P0-8 muda.
- **Orçamento:** 4 tentativas.

### Ficha C-1. Carteira combinada das camadas (v0.2; camada A1 com A2)

- **Por que existe:** cada camada da v0.1 reprovou sozinha, e várias têm Sharpe pequeno e pouca correlação entre si.
  Juntar apostas pouco correlacionadas pode dar um Sharpe maior que o de cada uma. A pergunta é se a soma passa no
  critério, e não se alguma camada passa.
- **Candidata: todas as candidatas da v0.1 que operam**, sem escolher pelo resultado. Cada camada é a configuração de
  uma linha do registro, rodada com o código da `main` no dia da aprovação desta versão:

| Camada | Registro | Sharpe do excesso no desenvolvimento |
|---|---|---|
| P0-3, carteira multiativo, risk parity a 1,0x | 5 (`p0_3_risk_parity`, tentativa 3) | 0,41 |
| F-B3, fatores na B3 | 17 (`fatores_b3`) | −0,03 |
| P0-1, tendência em BTC e ETH (USDT × PTAX) | 11 (`p0_1_tendencia_btc_eth`) | 0,68 |
| P0-2, tendência no BOVA11 | 12 (`p0_2_tendencia_bova11`, versão BOVA11) | −0,16 |
| P0-4, pares | 14 (`pares_b3`) | 0,05 |
| P0-5, PEAD | 16 (`pead_b3`) | 0,08 |

  Ficam fora o estudo (P0-7), o monitor (P0-6), o filtro (P0-8) e as versões de comparação das fichas.
- **Comparação, que não vira candidata nesta versão:** as três de maior Sharpe do excesso (P0-3, P0-1 e o DI1 da
  P0-2, registro 12, versão DI1). Essa lista foi escolhida **olhando o resultado**, e o relatório diz isso ao lado de
  cada número dela.
- **Série de cada camada:** a série diária líquida (custo e imposto dentro da camada, com a versão dos custos que a
  rodada registrou), **com o freio de 40% da seção 6**, que é como a camada operaria. Se o código da camada só tiver a
  série sem freio, a C-1 aplica o freio de `trader/freios.py` sobre ela. Antes de usar a série, a C-1 confere que a
  reexecução reproduz o resultado gravado no registro; se não reproduzir, a rodada para e isso é defeito, contado como
  tentativa da C-1. Toda rodada da C-1 conta no orçamento da C-1, e não no da camada.
- **Pesos, em passos, no primeiro pregão D de cada mês:**
  1. Entram as camadas com pelo menos 252 pregões de retorno até D.
  2. σ de cada uma = desvio-padrão dos 252 retornos diários do excesso sobre o CDI até o fechamento de D.
  3. Peso-alvo ∝ 1 ÷ σ, somando 1.
  4. Teto de 40% por camada: a camada acima do teto fica em 40%, e o resto se divide entre as outras na proporção de
     1 ÷ σ. Repete até nenhuma passar do teto. Se todas estiverem no teto, a sobra vai para o CDI.
  5. Banda: a carteira só volta aos pesos-alvo se alguma camada estiver a mais de 20% do peso-alvo dela (|peso −
     alvo| > 0,2 × alvo). Quando volta, todas voltam.
  6. Os pesos novos valem a partir do retorno de D+1 (sinal em D, execução em D+1, como na seção 4). Entre um
     rebalanceamento e outro, os pesos andam com o retorno de cada camada.
- **Retorno do dia** = soma dos pesos × retornos das camadas, mais a sobra × CDI. Calendário dos pregões da B3: o
  retorno da cripto nos dias sem pregão é **composto** e entra no pregão seguinte. Num dia em que a camada está sem
  posição, o retorno dela é o do caixa que ela já tem (CDI).
- **Período avaliado:** do primeiro pregão com pelo menos duas camadas no peso até 08/09/2023. A cripto entra em
  08/2018 (P0-1: dados desde 17/08/2017, mais 1 ano de aquecimento e 252 pregões de retorno).
- **Custo e imposto do rebalanceamento entre camadas:** o valor trocado paga o custo à vista da seção 3 (corretagem e
  emolumentos); o impacto já está dentro de cada camada. O valor retirado de uma camada paga 15% de IR sobre a parte
  que é lucro, medida pelo retorno da camada desde a última vez que ela recebeu dinheiro, sem isenção (aproximação
  conservadora). A C-1 não compensa o prejuízo de uma camada com o lucro de outra (seção 12).
- **Parâmetros fixos:** σ de 252 pregões, teto de 40%, banda de 20%, mensal. O platô (A3) mexe ±20% na janela da σ,
  no teto e na banda.
- **Alternativas (PBO):** nenhuma. A2 não se aplica.
- **Régua:** carteira 60/40 (BOVA11 e CDI), rebalanceada ao mês e líquida, como na P0-3; e CDI.
- **Teste do Brasil:** (a) com e sem a camada de cripto; (b) a correlação entre as camadas, mês a mês, contra o ganho
  de Sharpe da combinação; (c) o imposto pago no ano pela soma das camadas contra o de uma carteira que compensasse os
  prejuízos entre as camadas de ações (só como medida, sem mudar a regra).
- **O que se espera, escrito antes:** a maioria das camadas candidatas teve Sharpe do excesso perto de zero ou
  negativo (F-B3 −0,03; BOVA11 −0,16). A candidata provavelmente reprova. A comparação provavelmente vai melhor, mas
  esse ganho tem viés de seleção e não autoriza nada: o que vale para ela é o papel (seção 5). A P0-4 ficou quase
  todo o tempo no CDI e tem σ quase zero; pela regra, ela vai ao teto de 40% e funciona como caixa. Isso está escrito
  aqui para não ser mudado depois.
- **Orçamento:** 6 tentativas.

### Ficha P0-1b. Tendência em cripto no par em reais (v0.2; camada A2)

- **Por que existe:** na P0-1, o IOF e o spread de câmbio (0,88% por ordem) foram o maior custo, e sem eles o Sharpe
  do excesso iria de 0,68 para 1,01. O par cotado direto em reais (BTCBRL e ETHBRL na Binance) não tem câmbio.
  **Esta ficha foi escolhida depois de ver esse número**, e o relatório diz isso.
- **Regra:** a da P0-1, sem mudar nada (9 janelas, sinal médio, vol alvo de 25%, σ90, 50/50, alavancagem ≤ 1, caixa a
  CDI, execução no fechamento do dia seguinte), com uma diferença, a **banda**: a posição só muda quando difere do
  peso-alvo em mais de 20% dele. Quando o alvo é zero, a posição zera. Quando a posição é zero, ela abre se o alvo
  passar de 0,5% do patrimônio (a mesma convenção da P0-1). O objetivo é cortar o giro de 5,5 vezes por ano.
- **Dados:** candles diários de BTCBRL e ETHBRL do Binance Vision (mesma licença de uso interno da P0-1). O download
  foi aprovado com esta versão (seção 15, escolha 4). Cada série começa no 1º candle do par, a confirmar no download; os pares em reais
  começaram depois dos pares em USDT.
- **Impacto e spread:** o mesmo modelo de impacto, sobre o volume do par em reais, que é bem menor que o do par em
  USDT. O livro em reais não tem histórico de spread. **O critério usa 0,3% por lado** (conservador); o relatório
  mostra também 0,1% só como leitura.
- **Parâmetros fixos:** os da P0-1, mais a banda de 20%. **Alternativas (PBO):** nenhuma. A2 não se aplica.
- **Régua:** comprar e segurar BTCBRL (líquido); e CDI.
- **Teste do Brasil:** (a) caixa a CDI contra caixa a 0%; (b) meses acima do teto de R$ 35 mil e o imposto; (c) a
  P0-1 no mesmo período, para medir o que o câmbio custava; (d) com e sem a banda.
- **O que se espera, escrito antes:** o desenvolvimento vai do 1º candle mais 1 ano de aquecimento até 08/09/2023, o
  que deve dar poucos anos. Com poucos anos, só um Sharpe bem acima de 1 chega a t = 3 (com 3 anos, perto de 1,7). A
  ficha provavelmente sai inconclusiva pela régua de anos ≈ (t/SR)², e o que decide é o papel.
- **Orçamento:** 2 tentativas.

### Modelo HMM das fichas H (v0.3)

O mesmo modelo serve às três fichas H. Tudo o que tem número está aqui, e nada muda depois de ver um resultado.

- **O que o modelo observa:** o retorno logarítmico diário do **excesso sobre o CDI** do ativo (retorno do ativo
  menos o CDI do dia). Uma série só, sem outras variáveis.
- **O modelo:** HMM gaussiano de **2 estados**, em que a média e a variância mudam com o estado e a matriz de
  transição 2×2 é constante (o modelo de troca de regime de Hamilton, 1989). Código:
  `statsmodels.tsa.regime_switching.markov_regression.MarkovRegression(k_regimes=2, trend="c", switching_variance=True)`,
  na versão pinada em `requirements-trader.txt` (statsmodels 0.15.0). **Nenhuma dependência nova.**
- **Estimação:** máxima verossimilhança, com **20 pontos de partida** sorteados com semente fixa (0), ficando o de
  maior verossimilhança. Janela **expansiva**: do primeiro dia da série até o último dia do mês anterior.
- **Reestimação:** no primeiro dia (pregão, na B3) de cada mês. Os parâmetros ficam fixos durante o mês.
- **Mínimo de dados:** a primeira estimação pede **2 anos** de retornos (504 pregões na B3, 730 dias na cripto),
  contados desde o primeiro dia da série. O aquecimento de 1 ano da seção 2 fica dentro desses 2 anos. Antes disso
  não há posição, e o período avaliado (estratégia e régua) começa no primeiro dia com o modelo estimado.
- **Nome dos estados:** "calmo" é o estado com a **menor variância estimada**, e "turbulento" é o outro. O nome é
  dado de novo a cada reestimação, o que resolve a troca de rótulos entre uma estimação e outra.
- **Probabilidade usada:** a **filtrada**, P_D(calmo), que usa só os retornos até o fechamento de D (o algoritmo para
  a frente, com os parâmetros do mês). **Nunca a suavizada**, que usa os dias depois de D e olharia o futuro.
- **Quando a estimação falha:** se a otimização não convergir, ou se a variância de um estado sair abaixo de 10⁻¹⁰,
  ficam os parâmetros do mês anterior (no primeiro mês, nenhuma posição). O relatório diz quantos meses isso
  aconteceu.
- **Verificação própria (além de V1 a V4):** a mesma regra com a probabilidade **suavizada** tem de dar um resultado
  maior que a filtrada. Se não der, o código está errado e a rodada para, como no V1. A suavizada só serve para
  essa conferência e nunca entra num número de resultado.
- **Platô (A3):** ±20% no limiar (0,4 e 0,6 em vez de 0,5) e no mínimo de dados (1,6 e 2,4 anos). Os 2 estados não
  entram no platô: 1,6 ou 2,4 estados não existem, e 3 estados seriam outro modelo, fora desta versão.

### Ficha H-1. Alocação por regime no BOVA11 (v0.3; camada A2)

- **Por que existe:** a v0.1 deixou o HMM para uma versão nova. A pergunta é se um modelo que estima o regime do
  mercado, sem nenhuma regra escolhida à mão, consegue sair do Ibovespa nas fases ruins e ganhar do CDI depois de
  custo e imposto.
- **Ativo:** BOVA11, a mesma série da P0-2 (dados congelados de `trader/estrategias/dados_congelados.py`, conferidos
  pelo SHA-256), em pregões da B3.
- **Regra:** modelo HMM desta seção sobre o excesso do BOVA11. Posição-alvo **100% em BOVA11 quando P_D(calmo) > 0,5**
  e **0% (tudo no CDI) quando P_D(calmo) ≤ 0,5**. Sem alavancagem e sem venda a descoberto.
- **Parâmetros fixos:** os do modelo (2 estados, média e variância por estado, 20 partidas, semente 0, mínimo de 2
  anos, reestimação mensal) e o limiar de 0,5.
- **Alternativas (PBO):** nenhuma. A2 não se aplica.
- **Comparação, que não vira candidata nesta versão:** a mesma regra com a média de 200 pregões no lugar do HMM
  (100% em BOVA11 quando o fechamento de D está acima da média, CDI quando não), que é a condição mais simples da
  P0-8. Ela responde se o HMM acrescenta alguma coisa a uma regra que qualquer um vê no gráfico.
- **Régua:** comprar e segurar BOVA11 (líquido); e CDI.
- **Execução:** fechamento do pregão seguinte (sinal em D, execução em D+1, seção 4).
- **Teste do Brasil:** (a) caixa a CDI contra caixa a 0%; (b) quantas trocas por ano e quanto do Sharpe o IR de 15%
  do ETF (sem isenção) leva em cada saída; (c) as mudanças de regime contra as reuniões do Copom, só como leitura
  (o modelo pega os ciclos de juros?), sem mudar a regra.
- **O que se espera, escrito antes:** o BOVA11 rendeu menos que o CDI de 2010 a 2023 (7,4% contra 8,9% ao ano, com
  queda de −49,7%, no relatório da P0-2), e a tendência no BOVA11 teve Sharpe do excesso de −0,16. Modelos de regime costumam cortar a queda máxima
  mais do que aumentam o Sharpe, porque reconhecem o regime turbulento com atraso. A leitura do Claude é que a H-1
  provavelmente reprova em A5 (t ≥ 3) e A7 (contra a régua), mesmo que passe em F1. Com cerca de 12 anos avaliados, só
  um Sharpe perto de 0,9 chegaria a t = 3.
- **Orçamento:** 4 tentativas.

### Ficha H-2. Alocação por regime em BTC e ETH (v0.3; camada A2)

- **Ativos:** BTC e ETH em reais, **a mesma série da P0-1** (par em USDT × dólar já conhecido na véspera), em dias
  corridos (365 dias). Não usa o par em reais da P0-1b, que tem menos de 2 anos no desenvolvimento.
- **Regra:** um modelo HMM desta seção para cada ativo, sobre o excesso dele. Posição-alvo de cada um = **50% do
  capital quando P_D(calmo) > 0,5** e 0% quando não. A parte sem posição fica no CDI. Sem alavancagem e sem
  perpétuos.
- **Parâmetros fixos:** os do modelo, o limiar de 0,5 e os 50% por ativo (os da P0-1).
- **Alternativas (PBO):** nenhuma. A2 não se aplica.
- **Comparação, que não vira candidata nesta versão:** a mesma regra com a média de 200 dias no lugar do HMM, como
  na H-1.
- **Régua:** comprar e segurar BTC em reais (líquido); e CDI.
- **Execução:** fechamento do dia seguinte (365 dias, seção 4).
- **Teste do Brasil:** (a) caixa a CDI contra caixa a 0%; (b) quantos meses passam do teto de R$ 35 mil de vendas e
  quanto imposto geram; (c) quanto o IOF e o spread de câmbio levam, como na P0-1.
- **O que se espera, escrito antes:** a série começa em 17/08/2017. Com 2 anos de estimação, o período avaliado vai
  de 08/2019 a 08/09/2023, cerca de 4 anos. Com 4 anos, só um Sharpe perto de 1,5 chega a t = 3. A ficha provavelmente sai **inconclusiva** pela régua de anos ≈ (t/SR)², e o que decide é o papel.
- **Orçamento:** 4 tentativas.

### Ficha H-3. O HMM como filtro de uma estratégia aprovada (v0.3)

- **Regra:** igual à P0-8, com o HMM no lugar das condições observáveis: a estratégia aprovada opera quando
  P_D(calmo) > 0,5 no ativo principal dela e vai para o CDI quando não. O estado de D vale no fechamento de D+1, e
  cada troca paga o custo de uma ida ao mercado (as convenções do `trader/estrategias/regime.py`).
- **Teste:** a estratégia aprovada **com e sem** o filtro. O filtro só entra se melhorar o DSR sem piorar o PBO nem a
  queda máxima (a mesma regra da P0-8, `filtro_entra`).
- **Hoje sem objeto:** nenhuma estratégia foi aprovada (como a P0-8, `docs/resultado-regime-p0-8-sem-objeto.md`). Pôr
  o filtro numa reprovada seria procurar um jeito de salvá-la, e a seção 10 proíbe isso. A H-3 também não se aplica
  à H-1 nem à H-2, que já são o HMM.
- **Orçamento:** 2 tentativas.

## 10. Tentativas e honestidade

- Registro único (`trader/registro.py`); o DSR de toda estratégia usa N = tudo o que o registro tem.
- Orçamento desta versão: **78 tentativas** (seção 9). Esgotou: versão nova, +25. A v0.2 já soma as +25 dela ao N
  do DSR de toda rodada feita depois da aprovação. **(v0.3)** A v0.3 soma mais +25 a partir da aprovação dela.
- As tentativas gastas na v0.1 continuam contando no orçamento de cada ficha (por exemplo, à F-B3 restam 9 das 10).
- Defeito corrigido depois de ver um resultado é tentativa nova, explicada no relatório.
- Candidatos fixos em cada ficha. Uma comparação que vence o candidato **não vira candidato** nesta versão.
- Rodada sem o hash deste texto não roda (`trader/criterio_quant.py` confere, como `trader/p2/preregistro.py`).
- Cada relatório de resultado tem a seção "Limites e cuidados" e diz o que reprovou.

## 11. Fora de escopo nesta versão

Machine learning; HMM fora das fichas H-1 a H-3 (mais de 2 estados, outras variáveis observadas, outros ativos,
probabilidade suavizada); perpétuos e alavancagem em cripto; alavancagem fora do núcleo ou acima de 1,3x; perna
vendida nos fatores; intradiário; busca de parâmetros; ordens reais; agentes analistas (A3, documento próprio).
**(v0.2)** Também fora: uma pergunta nova para o núcleo (por exemplo, "não perde do CDI com queda pequena"), que só
vale para dados ainda não vistos e é uma decisão do Tiago à parte; o aumento de capital por subscrição privada
como sinal para evitar a ação, que só faz sentido sobre uma carteira comprada aprovada; e o Focus e o open interest
de cripto da P0-8, que pedem o ok do download. **(v0.3)** Também fora: a C-1 no papel, que o
`docs/papel-quant-v0.2.md` prometeu para a v0.3. Ela pede uma regra de aquecimento própria, que não está escrita (seção
17, escolha 6).

## 12. Limitações declaradas

- Séries brasileiras curtas: várias conclusões ficarão "inconclusivas" pela régua de anos ≈ (t/SR)², e o relatório
  dirá isso em vez de aprovar.
- Deslistadas: dependem do que a base tem (seção 2).
- Tarifas "a confirmar" dos custos; impacto de mercado com Y não medido no Brasil.
- Custos e impostos de hoje aplicados ao passado inteiro.
- O freio por camada no backtest usa uma regra de volta mecânica (12 meses) que na vida real é uma revisão escrita.
- Os agentes analistas (A3) não têm backtest honesto e por isso não estão aqui.
- **(v0.2)** A v0.2 foi escrita depois de ver os resultados. As duas fichas novas e a comparação da C-1 têm viés de
  seleção que o DSR só corrige em parte (as +25 tentativas). Por isso, só o papel e o holdout dão uma prova limpa.
- **(v0.2)** A C-1 soma camadas com o imposto de cada uma. Na vida real, o prejuízo de uma camada de ações
  compensaria o lucro de outra no mesmo mês, e o imposto seria menor. A cripto tem regra própria. O teste (c) da
  ficha mede essa diferença.
- **(v0.2)** O papel dura 12 meses. É pouco para um t alto e só decide se a estratégia continua sendo gravada.
- **(v0.3)** O HMM foi previsto antes de qualquer número (v0.1), mas a decisão de testá-lo agora veio depois de todas
  as fichas reprovarem, no mesmo período de desenvolvimento. As +25 do DSR corrigem só em parte.
- **(v0.3)** O HMM de 2 estados com média e variância por estado é o mais simples que existe. Um resultado ruim não
  prova que nenhum modelo de regime funciona; prova só que este, com estes números fixos, não funcionou.
- **(v0.3)** A estimação por máxima verossimilhança pode cair em ótimos locais. Os 20 pontos de partida com semente
  fixa deixam a conta reproduzível, mas não garantem o ótimo global.

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

## 14. O que mudou da v0.1 e por quê (v0.2)

| Mudança | Por quê | Muda alguma ficha da v0.1? |
|---|---|---|
| Ficha C-1, carteira combinada | Camadas fracas e pouco correlacionadas podem passar juntas, e nenhuma passou sozinha | não |
| Ficha P0-1b, cripto no par em reais | O câmbio foi o maior custo da P0-1 | não; a P0-1 segue com 9 tentativas, na série em USDT |
| Regra do papel (seção 5) | Os dados de daqui para a frente são os únicos que nenhuma tentativa viu, além do holdout | não; o papel só grava |
| Holdout da C-1 gasta o das camadas (seção 5) | As camadas e a P0-1b estão dentro da C-1 | não; só fecha uma porta |
| Seção 8 sem "a confirmar" | O piso de R$ 5 milhões foi aprovado com o texto da v0.1 (seção 13, item 4) | não; é o mesmo número |
| Orçamento de 60 para 68 e +25 no DSR | Versão nova (seção 10) | não |

Nenhum limite do critério (A1 a A8, F1, V, B1, B2, C) mudou, nenhuma régua mudou e nenhum candidato da v0.1 mudou.

## 15. Escolhas para o Tiago aprovar (v0.2)

**Aprovadas as seis em 04/11/2026 03h31** ("Pode, como está"), inclusive o download da escolha 4.

Propostas do Claude; com o "pode", passam a fazer parte do critério como qualquer outro item.

1. **A candidata da C-1 é a soma de todas as candidatas que operam**, e não só das três de maior Sharpe. A lista das
   três fica como comparação e vai para o papel. (Recomendação: aprovar; escolher as três como candidata seria
   escolher pelo resultado.)
2. **Os pesos da C-1:** inverso da volatilidade com teto de 40%, mensal, banda de 20%, e o IR de 15% sobre o lucro
   do que sai de cada camada. (Recomendação: aprovar; é a regra mais simples e não estima correlações.)
3. **Abrir o holdout da C-1 gasta o lacre das camadas dela e da P0-1b.** (Recomendação: aprovar; senão o holdout
   seria visto duas vezes.)
4. **A banda de 20% e o spread de 0,3% na P0-1b**, e o download do BTCBRL e do ETHBRL no Binance Vision (arquivos
   mensais públicos, sem custo, poucos MB; licença de uso interno). (Recomendação: aprovar.)
5. **O julgamento do papel em 12 meses** com P1 a P3, no máximo duas renovações, e a lista fixa das séries
   gravadas. (Recomendação: aprovar; é a única prova limpa antes do holdout.)
6. **Orçamento de 68 tentativas e +25 no DSR.** (Recomendação: aprovar; é o que a seção 10 manda.)

## 16. O que mudou da v0.2 e por quê (v0.3)

O que já tinha rodado quando a v0.3 foi escrita (todas reprovadas, 158 tentativas no DSR da última rodada): P0-3,
P0-1, P0-2, P0-4, P0-5, F-B3, C-1 e P0-1b. P0-6 e P0-7 não têm critério. A P0-8 ficou sem objeto.

| Mudança | Por quê | Muda alguma ficha da v0.2? |
|---|---|---|
| Modelo HMM comum e fichas H-1 (BOVA11) e H-2 (BTC e ETH) | A v0.1 e a v0.2 deixaram o HMM para uma versão nova | não |
| Ficha H-3, o HMM como filtro | É o "HMM fica para uma versão nova" da P0-8, sem mexer na P0-8 | não; a P0-8 só ganhou uma frase que aponta para a H-3 |
| H-1 e H-2 no papel, se rodarem (seção 5) | O papel é a única prova limpa antes do holdout | não; as séries da v0.2 continuam como estão |
| Seção 11: o HMM sai da lista do que está fora, menos o que as fichas H não cobrem | As fichas H agora existem | não |
| Orçamento de 68 para 78 e +25 no DSR | Versão nova (seção 10) | não |

Nenhum limite do critério (A1 a A8, F1, V, B1, B2, C) mudou, nenhuma régua mudou e nenhum candidato da v0.2 mudou.

## 17. Escolhas para o Tiago aprovar (v0.3)

Propostas do Claude; com o "pode", passam a fazer parte do critério como qualquer outro item.

1. **O modelo HMM das fichas H**, com tudo fixo: 2 estados, média e variância por estado, só o excesso sobre o CDI,
   janela expansiva com mínimo de 2 anos, reestimação mensal, 20 partidas com semente 0, probabilidade filtrada e
   limiar de 0,5. (Recomendação: aprovar; é o HMM mais simples, e cada número a mais seria uma porta para ajuste.)
2. **Os ativos: BOVA11 (H-1) e BTC e ETH na série da P0-1 (H-2).** São os ativos das camadas A2, e o multiativo e
   os fatores ficam fora. (Recomendação: aprovar.)
3. **A média de 200 dias como comparação**, que não vira candidata. (Recomendação: aprovar; sem ela não dá para saber
   se o HMM acrescenta algo a uma regra simples.)
4. **A H-3 como filtro**, hoje sem objeto, com a mesma regra de entrada da P0-8. (Recomendação: aprovar; não custa
   nada enquanto nenhuma estratégia for aprovada.)
5. **H-1 e H-2 no papel, se rodarem**, e o **orçamento de 78 tentativas com +25 no DSR**. (Recomendação: aprovar; é o
   que as seções 5 e 10 mandam.)
6. **A C-1 no papel fica fora da v0.3.** O `docs/papel-quant-v0.2.md` prometeu a C-1 para a v0.3, com uma regra de
   aquecimento própria que ainda não está escrita. Pôr a C-1 aqui economiza uma versão (cada versão soma +25 ao N do
   DSR), mas atrasa o HMM até essa regra estar pronta. (Recomendação: deixar fora e fazer o HMM primeiro.)
