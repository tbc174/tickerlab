# Critério de aprovação da M2 (pré-registro)

**Status: APROVADO, versão 0.1, em 11/10/2026, pelo Tiago ("aprovo a v0.1", sem mudanças).**
**VIGENTE. Não muda a partir de agora.** Qualquer mudança vira a versão 0.2, com data, e conta como 25
tentativas a mais (seção 7). Esta aprovação foi dada **antes** de qualquer resultado de ML ter sido visto.
O hash SHA-256 deste texto e a cópia no Git ficam registrados em `historico-de-alteracoes.md`; a cópia
de referência é `docs/pre-registro-m2-v0.1.md` no repositório.

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
- **Frequência:** candles **diários**. Decisão no fechamento do dia t, vale para o dia t+1.
- **Posição:** de **−1 a +1** por ativo (`trader/backtest.py`), com volatilidade alvo (seção 3).
- **Famílias de estratégia (todas as hipóteses que serão testadas):**
  - **H0 baselines** (seção 4): comprar e segurar, tendência simples, previsão ingênua.
  - **H1 modelo linear:** regressão logística regularizada.
  - **H2 árvores:** floresta aleatória e LightGBM regularizado.
  - **H3 meta-rotulagem:** uma regra simples de tendência decide a direção e um modelo decide se vale
    agir (já temos `src/aprendizado.py`).
- **Fora de escopo:** deep learning (LSTM, Transformer), opções e venda de volatilidade, intradiário,
  imposto, e qualquer ordem real.

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
  (como no `pysystemtrade`). A carteira junta os ativos com **risco igual**.
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
2. **Rótulos embaralhados:** treinar com rótulos aleatórios deve dar Sharpe ≈ 0 (± 2 erros-padrão).
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
