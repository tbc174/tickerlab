# Critério de aprovação da M2 (pré-registro)

**Status: APROVADO, versão 0.3, em 11/10/2026, pelo Tiago ("Aprovo a v0.3, pode seguir"). VIGENTE.**
Substitui a v0.2 (aprovada em 11/10/2026, SHA-256 `8d72f930…f24c`, guardada em `docs/pre-
registro-m2-v0.2.md`), que substituiu a v0.1 (`b8074c37…e98`). A única mudança da v0.3 está na seção
3: o risco da carteira passa a ser dividido igualmente **entre grupos de classes**, e não entre
ativos (motivo, efeitos e custo na seção 13). Como manda a seção 7, esta versão soma mais **25
tentativas** ao registro. **Esta mudança também foi feita DEPOIS de ver resultados** (as tentativas
#13 a #15 e a análise de viabilidade do universo ampliado). Qualquer mudança futura vira a v0.4, com
data e mais 25 tentativas. O hash SHA-256 deste texto fica em `trader/holdout.py` e em `historico-
de-alteracoes.md`.

**Para que serve este documento:** decidir, antes de olhar qualquer resultado, o que uma estratégia de
machine learning precisa mostrar para virar *candidata a robô de paper trading* (M3). Combinar o
critério depois de ver os números é a forma mais comum de enganar a si mesmo em finanças. As razões
e as fontes de cada número estão em `pesquisa-ml-quant.md`.

> **Aprovada aqui não significa rentável.** Passar neste critério só autoriza *testar em conta demo*
> (M3). Nenhuma ordem real sem decisão escrita do Tiago, depois da M3 e da M4. Reprovar é um resultado
> válido e será registrado como tal.

---

## 1. Escopo: o que está sendo testado

- **Mercado:** os ativos com `papel = operar` de `trader/universo.py` (forex, metais, energia, agro,
  cripto, ações da B3, índices, ETFs e o dólar). VIX, juros e índice do dólar entram **só como
  atributo**, nunca como ativo operado.
- **Universo ampliado (v0.2):** entram como `operar` ativos de **classes ou regiões que o universo da
  v0.1 não cobria**, escolhidos por esta regra, **sem olhar o desempenho** deles: líquidos e com
  histórico diário desde **no máximo 01/01/2008**. Lista fechada:
  - **Juros e crédito (ETFs):** IEF, SHY, TIP, LQD, HYG, EMB.
  - **Commodities (ETFs, sem o problema de rolagem dos `=F`):** USO, UNG, DBA, DBC, DBB.
  - **Regiões:** EEM, EFA, ^FTSE, ^HSI, ^AXJO, ^STOXX50E, ^KS11.
  - **Imóveis:** VNQ.
  - **Moedas fora do bloco do dólar (MT5):** EURCHF, EURAUD, AUDNZD, CADJPY, USDNOK, USDSEK, EURCAD,
    NZDJPY. Só entra a que tiver histórico diário desde 01/01/2008 no MT5; a que não tiver fica de
    fora, e isso é registrado. Nada fora desta lista entra.
- **Frequência:** candles **diários**. Decisão no fechamento do dia t, vale para o dia t+1.
- **Posição:** de **−1 a +1** por ativo (`trader/backtest.py`), com volatilidade alvo (seção 3).
- **Famílias de estratégia (todas as hipóteses que serão testadas):**
  - **H0 baselines** (seção 4): comprar e segurar, tendência simples, previsão ingênua.
  - **H1 modelo linear:** regressão logística regularizada.
  - **H2 árvores:** floresta aleatória e LightGBM regularizado.
  - **H3 meta-rotulagem:** uma regra simples de tendência decide a direção e um modelo decide se vale
    agir (já temos `src/aprendizado.py`).
  - **H4 deep learning (incluída na v0.2):** redes neurais pequenas, com arquitetura fixada **antes**
    de rodar e **sem busca de hiperparâmetros**, no mesmo rótulo, sinal, CPCV, custos e avaliador da
    H1 e da H2. São **três configurações, nem uma a mais** (cada uma conta como tentativa):
    - **MLP tabular:** os mesmos atributos da H1/H2; camadas ocultas de 64 e 32, ReLU, dropout 0,2,
      decaimento de peso 1e-4.
    - **LSTM:** os últimos 60 pregões de cada ativo (retornos divididos pela volatilidade e os
      atributos do dia), 1 camada de 32 unidades, dropout 0,2.
    - **TCN:** a mesma janela de 60 pregões, 3 blocos convolucionais causais de 16 canais
      (dilatações 1, 2 e 4), dropout 0,2.

    Comum às três: um só modelo para todos os ativos, PyTorch **só na CPU**, otimizador Adam (taxa
    1e-3), lotes de 512, no máximo 30 épocas com **parada antecipada** (paciência 5) numa validação
    tirada dos **últimos 20% do treino de cada divisão, com expurgo de 21 pregões** antes dela;
    semente fixa e algoritmos determinísticos (a seção 8, item 3, vale igual).
  - **H5 séries temporais clássicas (incluída na v0.2):** **uma configuração**: um ARIMA por ativo
    sobre os retornos diários divididos pela volatilidade, com a ordem (p, q de 0 a 2, d = 0) escolhida
    pelo AIC **só no treino de cada divisão**; a previsão da soma dos próximos 5 pregões vira a
    probabilidade de "sobe" e segue o mesmo sinal, CPCV, custos e avaliador. Sem busca além disso.
- **Fora de escopo:** Transformers e outras redes grandes, busca de hiperparâmetros para a H4, opções
  e venda de volatilidade, intradiário, imposto, e qualquer ordem real.

## 2. Dados, divisão do tempo e o holdout lacrado

| Parte | Período | Uso |
|---|---|---|
| **Desenvolvimento** | do começo de cada série até **08/09/2023** | tudo: atributos, modelos, parâmetros, CPCV |
| **Expurgo** | 09/09/2023 a 09/10/2023 (~21 pregões) | descartado, para rótulos que olham até 21 dias à frente não vazarem |
| **Holdout lacrado** | **10/10/2023 a 09/10/2026** (3 anos) | pontuado **uma única vez**, no fim, por um candidato já escolhido |

- O holdout fica **trancado** com um arquivo `holdout.lock` (hash do candidato e da configuração).
  O código de pontuação recusa rodar uma segunda vez. Quem decide destrancar é o Tiago, e isso
  invalida o holdout (seção 7).
- Depois de pontuado o holdout, qualquer nova pesquisa nesses dados é **contaminada**. O teste final de
  verdade passa a ser o **paper trading em dados que ainda não existem (M3)**.
- Nenhum atributo, rótulo ou normalização pode usar informação posterior à data de decisão. Há testes
  automáticos (deslocar o futuro, embaralhar rótulos) descritos na seção 8.

## 3. Como o sinal vira posição e custos

- **Tamanho:** a posição de cada ativo é o sinal (−1 a +1) vezes `10% ÷ volatilidade anual estimada`
  do ativo, com **teto de 2×**. A volatilidade usa 35 dias, misturada com 30% da lenta de 10 anos
  (como no `pysystemtrade`).
- **Carteira (redação da v0.3): risco igual por grupo.** Os ativos são separados em seis grupos:
  **forex** (forex e o dólar/real), **ações da B3**, **índices** (índices e ETFs de ações e imóveis),
  **renda fixa**, **commodities** (ETFs de commodities e metais do MT5) e **cripto**. Em cada dia, o
  retorno de cada grupo é a média dos ativos do grupo que têm dado naquele dia, e o retorno da
  carteira é a média dos grupos que têm dado naquele dia (um grupo que ainda não existe, como a
  cripto antes de 2014, fica de fora e o peso se divide entre os outros). As baselines e todos os
  modelos usam a mesma regra. A concentração (A7) mede a contribuição de cada ativo com esses
  pesos.
- **Buffer de posição:** só se negocia quando a posição ideal sai de uma faixa de ±10% em torno da
  atual (corta custo).
- **Custos (caso base, "×1"):** spread por classe, comissão e deslizamento por lado. Valores propostos
  (a calibrar com o spread real da corretora quando houver conta; o demo da MetaQuotes não prova o real):

  | Classe | Custo por lado (spread/2 + comissão + deslizamento) |
  |---|---|
  | Forex G10 | 0,5 ponto-base de spread (1 pb ida e volta) + 0,5 pb de deslizamento |
  | Forex emergentes, metais, energia, agro | 3 pb |
  | Índices e ETFs | 2 pb |
  | Ações da B3 | 5 pb (padrão do app) |
  | Cripto | 10 pb |

  O swap entra com a taxa **observada** quando houver série; sem ela, **assume-se o pior dos dois
  lados** e isso fica registrado como limitação.
- **Estresse "×2":** todos os custos dobrados. Todo resultado é reportado nos dois casos.

## 4. Baselines que o candidato precisa vencer

| Baseline | Regra |
|---|---|
| **B0 Comprar e segurar** | nos ativos com tendência de alta de longo prazo; para forex/metais, posição zero |
| **B1 Tendência simples (a mais importante)** | média de sinais de médias móveis exponenciais (2/8, 4/16, 8/32, 16/64, 32/128, 64/256 dias), mesma posição e os mesmos custos |
| **B2 Previsão ingênua** | posição de amanhã = sinal do retorno de hoje |

O candidato só conta se **bater a B1** (a regra simples que a literatura mostra funcionar em vários
mercados), líquido de custos. Vencer só a B0 ou a B2 não basta.

## 5. Critérios de aprovação (todos precisam ser cumpridos)

**A. Dentro do desenvolvimento** (validação CPCV: 10 blocos, 2 de teste por vez, expurgo e embargo
de 21 dias, 45 divisões, 9 caminhos de backtest):

| # | Critério | Valor proposto | Por quê |
|---|---|---|---|
| A1 | **Sharpe deflacionado (DSR)**, contando **todas** as tentativas registradas | probabilidade ≥ **0,95** | corrige a seleção do melhor entre muitos |
| A2 | **PBO** (probabilidade de overfitting do backtest) | ≤ **0,25** | convencional é < 0,5; 0,25 é mais exigente |
| A3 | **t-estatística** do retorno médio diário, líquido de custos | ≥ **3,0** | limiar de Harvey, Liu e Zhu para múltiplos testes. Equivale a Sharpe ≈ 0,7 em ~20 anos |
| A4 | **Sharpe líquido mediano** nos 9 caminhos | > 0 em **pelo menos 8 dos 9** | consistência entre caminhos, não um só |
| A5 | **Contra a B1:** diferença de Sharpe (candidato − B1), bootstrap em blocos de 21 dias | limite inferior de 90% **> 0** | tem que ganhar da regra simples, com folga estatística |
| A6 | **Consistência entre ativos:** fração dos ativos com Sharpe líquido > 0 | ≥ **60%** | não pode depender de um ativo |
| A7 | **Concentração:** maior contribuição de um único ativo ao resultado | ≤ **25%** | idem |
| A8 | **Consistência no tempo:** anos civis com retorno líquido > 0 | ≥ **65%** | não pode ser só um período |
| A9 | **Estresse de custos (×2):** Sharpe líquido | continua **> 0** e DSR ≥ **0,90** | custos reais costumam ser maiores que o modelado |
| A10 | **Teste contra o acaso** (`testar_contra_o_acaso`): sinal deslocado no tempo | Sharpe do candidato acima do **percentil 95** dos sinais embaralhados | confere se há habilidade, não só exposição |

**B. No holdout (pontuado uma vez, só se A1 a A10 passaram):**

| # | Critério | Valor proposto |
|---|---|---|
| B1 | Sharpe líquido (custos ×1) | ≥ **max(0,3; 0,5 × Sharpe do desenvolvimento)** |
| B2 | Queda máxima | ≤ **1,5 ×** a queda máxima mediana dos caminhos do desenvolvimento |
| B3 | Contra a B1 | Sharpe do candidato **maior** que o da B1 (estimativa pontual; 3 anos têm pouco poder, e isso fica declarado) |
| B4 | Estresse de custos (×2) | Sharpe líquido **> 0** |

O desconto de 50% em B1 vem da evidência de que sinais perdem de **26% a 58%** depois de descobertos
(McLean e Pontiff). É um valor de partida.

**C. Tamanho mínimo da amostra:** a série do candidato precisa ter, no mínimo, o comprimento mínimo de
acompanhamento (MinTRL, em `src/acaso.py`) para o Sharpe observado. Se não tiver, o resultado é
"inconclusivo", não "aprovado".

## 6. Resultados possíveis

- **Aprovada:** cumpre A, B e C. Vira candidata ao **paper trading em demo (M3)**, com o mesmo critério
  como régua do acompanhamento. Nada de dinheiro real.
- **Reprovada:** falha em qualquer critério. Vai para o relatório de resultados negativos. Isso conta
  como conclusão da pesquisa, com o motivo.
- **Inconclusiva:** passa em tudo, mas a amostra é curta (C) ou há dado ruim. Fica pendente de mais dados.

## 7. Contagem de tentativas e regras que protegem a honestidade

- Todo modelo, rótulo, conjunto de atributos ou parâmetro **testado** entra num **registro** (SQLite,
  com hash da especificação e do commit). O DSR usa o **número total** de entradas. **Não existe
  "tentativa que não conta".**
- **Orçamento: 300 configurações** no total. Se passar disso, o DSR é calculado com o número real
  (que penaliza mais) e o fato é reportado.
- **Mudar este documento depois de aprovado** gera a versão seguinte, com data, e soma 25 tentativas.
- **Destrancar o holdout** antes da hora (ou rodar uma segunda vez) **invalida o holdout**. A pesquisa
  segue, mas o resultado final só vale com dados novos (M3).
- Escolher entre os candidatos olhando o holdout é proibido: **um só candidato** vai ao holdout,
  escolhido **só com o desenvolvimento**.

## 8. Verificações automáticas antes de aceitar qualquer número

1. **Teste do futuro:** deslocar todos os atributos um dia para a frente (olhando o futuro de
   propósito) deve **inflar** o resultado; se não inflar, o teste está quebrado. O resultado normal
   precisa ficar longe disso.
2. **Rótulos embaralhados (redação da v0.2):** treinar com os rótulos de treino sorteados (a
   proporção de "sobe" continua a mesma) deve render **o mesmo que a referência da proporção**: o
   mesmo pipeline, com os mesmos custos, mas prevendo para todas as linhas só a frequência de "sobe"
   do treino da divisão. Medida: o Sharpe da **diferença diária** entre o embaralhado e a referência
   (caminho mediano) precisa ficar em ≈ 0 (± 2 erros-padrão). Sem vazamento, o que o modelo sorteado
   aprende além da proporção é ruído e não pode prever o retorno.
3. **Reexecução:** o mesmo código e a mesma semente dão o mesmo resultado.
4. **Dados:** só entram séries "ok", "reparada" ou "ok com aviso" do relatório de qualidade; saltos de
   rolagem suspeitos e o preço negativo do WTI (20/04/2020) tratados e documentados.

## 9. Limitações declaradas desde já

- **Viés de sobrevivência:** as ações da B3 do universo são as que **existem hoje** (PETR4, VALE3...).
  Empresas que saíram da bolsa ou faliram não estão, o que **infla** o resultado de ações. O resultado
  em ações vale menos que o de forex, índices e commodities.
- **Futuros contínuos sem ajuste de rolagem** (`=F`): retornos em dias de rolagem podem estar errados.
- **Boi gordo, café, mini índice e mini dólar da B3 não têm histórico longo.** Entram por **proxies**
  (`LE=F`, `KC=F`, `^BVSP`, `BRL=X`) que **não são** o contrato negociável. Resultado em proxy não
  prova resultado no contrato.
- **Spread do demo da MetaQuotes** não é o de uma corretora real; os custos da seção 3 são estimativas.
- **Sem imposto.** Resultados são brutos de imposto (day trade 20%, swing 15%, regras próprias no
  exterior; perguntar a um contador antes de qualquer dinheiro real).
- **H4 com poucos dados para deep learning:** ~56 ativos diários é pouco para redes neurais, e o
  estudo de FX do `machine-learning-for-trading` (lido; ver `pesquisa-ml-quant.md`) não achou
  vantagem do deep learning depois de contar as tentativas. A H4 é testada para ter a resposta, não
  porque se espera que passe. Por rodar só na CPU, cada configuração pode levar dezenas de minutos.
- Os limiares vêm de uma pesquisa em fontes secundárias (ver as ressalvas em `pesquisa-ml-quant.md`) e
  precisam ser conferidos nos artigos originais; eles são o **ponto de partida** a aprovar, não verdades.

## 10. O que ainda precisa ser construído para cumprir este critério

| Peça | Estado |
|---|---|
| Sharpe deflacionado, PBO, contra o acaso, MinTRL | **existem** (`src/acaso.py`) |
| Expurgo e embargo, barreira tripla, meta-rotulagem | **existem** (`src/aprendizado.py`) |
| Motor com −1 a +1, custos e swap | **feito** (`trader/backtest.py`) |
| **CPCV** (10 blocos, 45 divisões, 9 caminhos) | falta |
| **Bootstrap em blocos** para comparar com a B1 | falta |
| **Registro de tentativas** (SQLite com hash) | falta |
| **Holdout lacrado** (`holdout.lock`) | falta |
| **Posição por volatilidade e buffer** | falta |
| Baselines B0, B1, B2 e a análise de viabilidade | faltam |
| Modelos de árvores (floresta, LightGBM) | faltam |
| Testes do futuro e de rótulos embaralhados | faltam |
| **H4 (v0.2):** PyTorch só CPU, MLP, LSTM e TCN no mesmo pipeline | falta |
| **Referência da proporção** para o teste de rótulos embaralhados (v0.2) | falta |
| **H5 (v0.2):** ARIMA por ativo (`statsmodels`) no mesmo pipeline | falta |
| **Universo ampliado (v0.2):** baixar, conferir qualidade, refazer viabilidade | falta |
| **Risco igual por grupo (v0.3):** carteira, concentração (A7) e teste contra o acaso | falta |

## 11. O que o Tiago precisa decidir (valores propostos em negrito)

| Decisão | Proposta | Alternativas |
|---|---|---|
| Tamanho do holdout | **3 anos** (10/10/2023 a 09/10/2026) | 2 anos (mais dados para desenvolver, menos poder) ou 4 |
| t-estatística mínima (A3) | **3,0** | 2,5 (mais fácil de passar, menos protegido) |
| PBO máximo (A2) | **0,25** | 0,5 (convencional) |
| DSR mínimo (A1) | **0,95** | 0,90 |
| Desconto de decaimento (B1) | **50%** | 35% (mais otimista) |
| Orçamento de tentativas | **300** | 150 ou 500 |
| Custos | **tabela da seção 3, com estresse ×2** | ajustar quando houver corretora real |
| Famílias H1 a H3 | **linear, árvores, meta-rotulagem** | incluir ou tirar |

**Aprovado em 11/10/2026:** todos os valores da coluna "Proposta" foram aceitos como estão.

---

*Redigido em 11/10/2026 por Claude, a pedido do Tiago, com base em `pesquisa-ml-quant.md`, e aprovado
por ele no mesmo dia.*

## 12. Mudanças da v0.1 para a v0.2 (11/10/2026)

**O que mudou:** (1) a seção 8, item 2 (rótulos embaralhados); a v0.1 dizia "treinar com rótulos
aleatórios deve dar Sharpe ≈ 0 (± 2 erros-padrão)". (2) O **universo ampliado** (seção 1). (3) A
família **H4 deep learning** e (4) a família **H5 séries temporais clássicas** (seção 1), com a
limitação da H4 (seção 9) e as peças que faltam (seção 10). As decisões da seção 11 mostram a
aprovação da v0.1 e não foram reescritas.

**Por que o teste mudou:** sortear os rótulos não muda a proporção de "sobe" (um pouco mais da
metade). O modelo aprende só essa proporção, prevê "sobe um pouco" em tudo e, como o pipeline
reescala o sinal no treino (média absoluta 0,5), fica comprado em todos os ativos, rendendo o que o
mercado subiu (como a B0). Nas tentativas #13 a #15 o embaralhado deu Sharpe 0,41, 0,49 e 0,38
(limites ±0,42, ±0,43 e ±0,42), sem nenhum vazamento: o teste do futuro inflou para 22 a 25 nas
três. A regra da v0.1 reprovava qualquer modelo com viés comprado e deixava de medir o que deveria
(vazamento). A nova regra compara o embaralhado com quem só conhece a proporção, então o viés
comprado aparece dos dois lados e se cancela.

**Por que o universo cresceu:** os 56 ativos operáveis da v0.1 equivalem a só ~9,3 apostas
independentes (correlação média 0,15): 25 ações da B3 andam quase juntas, o forex é quase todo
contra o dólar, as criptos sobem e caem juntas. Faltavam classes inteiras (juros e crédito,
commodities operáveis, várias regiões, imóveis, moedas fora do dólar). Mais apostas independentes
ajudam todas as famílias. Para não virar escolha a dedo, a entrada segue a regra e a lista fechada
da seção 1, definidas sem olhar o desempenho desses ativos (só se conferiu que as séries existem e
desde quando).

**Por que a H4 e a H5 entraram:** o Tiago tinha pedido deep learning e decidiu adiar porque mudar o
critério custa 25 tentativas; também perguntou por modelos de séries temporais. Como cada versão
custa 25 tentativas, não importa quantas mudanças leve, incluí-las junto com a correção do teste sai
sem custo extra. Para não virar uma busca à vontade, a H4 fica limitada a três arquiteturas fixadas
e a H5 a uma configuração, sem ajuste de hiperparâmetros.

**O que acontece com o que já foi feito:** as tentativas #1 a #15 continuam no registro como estão
(universo da v0.1, regra antiga do embaralhado) e continuam contando no Sharpe deflacionado. Com o
universo novo, as baselines B0, B1 e B2 e os três modelos (logística, floresta e LightGBM) são
**rodados de novo como tentativas novas** (+6), com a regra nova; a B1 do universo novo passa a ser
a régua do A5. Isso não pode favorecer os modelos já testados: os três reprovaram em seis ou sete
itens além do V (A1, A3, A5, A9 e A10 em todos), e no universo novo são julgados do zero, pelo mesmo
critério, como qualquer candidato.

**Custo:** +25 tentativas no registro (seção 7), uma vez só para as quatro mudanças, o que deixa o
Sharpe deflacionado (A1) um pouco mais exigente para todos os candidatos seguintes. As novas rodadas
(baselines, modelos refeitos, H3, H4 e H5) contam como tentativas normais. Nada mais muda: limiares,
holdout (as mesmas datas, também para os ativos novos), custos da seção 3 (ETFs com o custo de
"Índices e ETFs"; moedas novas com o de "Forex G10" quando forem G10 e o de emergentes nas demais) e
orçamento de 300 continuam os da v0.1.

## 13. Mudanças da v0.2 para a v0.3 (11/10/2026)

**O que mudou:** só a seção 3, a forma de juntar os ativos na carteira. Na v0.1 e na v0.2, cada
ativo recebia o mesmo risco ("a carteira junta os ativos com risco igual"); agora cada um dos seis
**grupos** recebe o mesmo risco, e dentro do grupo os ativos dividem esse risco igualmente.

**Por quê:** a análise de viabilidade do universo ampliado (83 ativos) deu 9,1 apostas
independentes, contra 9,3 dos 56 ativos da v0.1, porque um único fator, a "bolsa mundial", explica
cerca de 30% da variância nos dois universos. Com risco igual por ativo, 39 dos 83 ativos são ações
(25 da B3 e 14 índices e ETFs), e os índices andam juntos (correlação semanal média de 0,62 entre si
e de 0,34 com as ações da B3). Ampliar o universo não diversifica de verdade enquanto o peso seguir
o número de ativos de cada tipo.

**Efeito nos pesos (declarado para não esconder nada):** com os seis grupos presentes, cada um fica
com 1/6 (≈17%) do risco. Antes: ações da B3 30%, forex 27%, índices 17%, commodities 12%, renda fixa
8% e **cripto 6%**. **O peso da cripto quase triplica, e a cripto foi a classe que mais rendeu na
régua B1 dentro do desenvolvimento** (Sharpe mediano 0,45 por ativo, com histórico que só começa por
volta de 2014 e cobre uma alta excepcional). A mudança foi motivada pela estrutura de correlação,
não pelo desempenho, mas o efeito pode favorecer resultados; por isso fica escrito aqui. Continuam
valendo, sem mudança, A6 (≥ 60% dos ativos com Sharpe > 0), A7 (nenhum ativo com mais de 25% do
resultado, agora medido com os pesos por grupo) e A8 (≥ 65% dos anos positivos).

**O que acontece com o que já foi feito:** nada do universo novo tinha sido rodado; as baselines e
os modelos no universo ampliado rodam direto com a regra da v0.3. As tentativas #1 a #15 continuam
no registro como estão e contando no Sharpe deflacionado.

**Custo:** +25 tentativas no registro (seção 7). Somadas às 25 da v0.2, são 50 tentativas de ajuste
do critério, o que deixa o Sharpe deflacionado (A1) mais exigente para todos os candidatos. Nada
mais muda: limiares, universo, famílias, holdout, custos e orçamento de 300.
