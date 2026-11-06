# Pesquisa 2: pré-registro (critério e plano de testes)

**Status: APROVADO, versão 0.1, em 11/10/2026, pelo Tiago** (questionário: início em 1980, pesos
30/30/15/15/10, régua B1 no A5, anos positivos ≥ 60%; "Aprovo tudo como está"). VIGENTE. O hash
SHA-256 deste texto fica em `trader/p2/preregistro.py` e no histórico. Daqui em diante, nada muda sem uma versão nova, com data, motivo e **+25 tentativas**
no registro (como na M2). Nenhum resultado de estratégia foi calculado até esta data.

Base: `pesquisa-2-plano.md`, `pesquisa-2-literatura.md`, `pesquisa-2-inventario-de-dados.md` e as
decisões 0006, 0007, 0012, 0013 e 0014 (pasta privada `projeto-acoes/`).

> **Aprovada aqui não significa rentável.** Passar só autoriza o teste em conta demo (M3). Nenhuma
> ordem real sem decisão escrita do Tiago (decisão 0007). Reprovar é um resultado válido.

## 1. A pergunta

**Uma carteira de prêmios conhecidos (tendência lenta e carry), com regras e parâmetros tirados
da literatura e operada em CFDs, passa no critério depois de custos realistas e de descontar todas
as tentativas já feitas (M2 + Pesquisa 2)?**

## 2. Dados e divisão do tempo

| Parte | Período | Uso |
|---|---|---|
| Aquecimento | do início de cada série até 1 ano depois | só para os sinais terem histórico (256 pregões) |
| **Desenvolvimento** | **01/01/1980 a 08/09/2023** | todos os testes deste documento |
| Expurgo | 09/09/2023 a 09/10/2023 | descartado |
| **Holdout** | **10/10/2023 a 09/10/2026** | uma única vez, só para o candidato aprovado (o mesmo da M2, nunca aberto) |

- Universo: os 28 mercados de `trader/p2/mercados.py` (11 moedas, 11 índices, 3 metais, 2 de
  energia, 1 título). Cada mercado entra na carteira quando tem 1 ano de dados; antes disso, o
  peso do grupo se divide entre os que existem.
- Leitura **só pelo desenvolvimento** (como `holdout.carregar_desenvolvimento` na M2); novo
  `holdout.lock` para a Pesquisa 2.

## 3. Como o retorno de cada CFD é montado (sem olhar o futuro)

Retorno diário de uma posição comprada de 1 unidade de capital (vendida = o sinal oposto, com o
mesmo custo de margem):

| Classe | Retorno do preço | Carry diário (dias corridos / 365) |
|---|---|---|
| Moedas (BASE/COTAÇÃO) | variação do câmbio | + juro da base − juro da cotação |
| Índices | variação do índice | + dividendo − juro da moeda do índice |
| Metais | variação do preço | − juro do dólar |
| Energia | variação do preço à vista | − juro do dólar (o carry da curva não existe nos dados gratuitos) |
| Título (10 anos dos EUA) | − duração × variação do rendimento (duração de um título ao par de 10 anos, recalculada todo dia) | + rendimento de 10 anos − juro do dólar |

- **Juros:** juros curtos de cada moeda (`JUROS_CURTOS`); onde a OCDE começa tarde (Japão 2002,
  Suíça 1999), a taxa básica do BIS. Séries mensais valem do primeiro dia do mês seguinte ao
  publicado (sem olhar o futuro).
- **Dividendos:** S&P 500 pela base de Shiller (mensal, defasada 1 mês); demais índices, 2,5% ao ano
  (decisão 0013).
- **Regras de dados (decisão 0014):** retorno entre duas cotações seguidas, sem preço inventado;
  retorno simples sobre o preço absoluto (WTI negativo).
- **Moeda da carteira:** dólar. Índices fora dos EUA e o cobre/ouro já em dólar; índices em outra
  moeda são convertidos **com proteção cambial** (o CFD rende o índice na moeda local e a margem é
  pequena): o retorno usado é o do índice na moeda local.

## 4. Custos (todos em todos os testes)

- **Negociação (por lado, % do valor):** moedas principais 0,01%; moedas emergentes (MXN, BRL)
  0,03%; índices 0,02%; metais 0,03%; energia 0,03%; título (CFD do ETF) 0,02%.
- **Custo de manter (decisão 0013):** a margem da corretora sobre o valor da posição, comprada ou
  vendida: **2,5% ao ano** em índices, metais, energia e título; **1% ao ano** em moedas.
- **Estresse A:** custos de negociação × 2. **Estresse B:** margens da tabela da Admirals lida em
  11/10/2026 (moedas ~2,5% ao ano).

## 5. As regras (nenhum parâmetro ajustado aos dados)

- **Volatilidade de cada mercado:** desvio dos retornos diários com média móvel exponencial de 35
  dias, misturado com 30% da média de 10 anos (como na M2), anualizado.
- **T1, tendência lenta:** três cruzamentos de médias exponenciais do preço, 16/64, 32/128 e
  64/256 dias, cada um dividido pelo desvio do preço e multiplicado pela escala publicada por Carver
  (3,75; 2,65; 1,87), limitado a ±20; média simples dos três × multiplicador de diversificação
  fixo de 1,1; limitado a ±20.
- **C1, carry:** carry anual do mercado (seção 3) dividido pela volatilidade anual, média dos
  últimos 90 dias, × escala **30** (Carver, *Advanced Futures Trading Strategies*, p. 216),
  limitado a ±20. Só em moedas, índices e título; zero em metais e energia.
- **Combinação K2 (o candidato):** 60% T1 + 40% C1 nos mercados com carry, 100% T1 nos demais,
  × multiplicador fixo de 1,2, limitado a ±20.
- **K1 (controle):** só T1, para medir quanto o carry acrescenta.
- **Réguas:** **B1** = tendência com as 6 velocidades da M2 (2/8 a 64/256); **B0** = comprar e
  segurar com o mesmo dimensionamento.

**Configurações testadas: só K1, K2, B0 e B1.** Nada de variar velocidades, pesos ou escalas.

## 6. Da previsão à posição

- Posição (fração do capital) = previsão ÷ 10 × volatilidade alvo × peso de risco do mercado ×
  IDM ÷ volatilidade do mercado.
- **Volatilidade alvo da carteira: 12% ao ano** (decisão 0012).
- **Pesos de risco por grupo:** moedas 30%, índices 30%, metais 15%, energia 15%, títulos 10%;
  dentro do grupo, partes iguais.
- **IDM:** multiplicador de diversificação entre mercados, calculado só com o passado (janela que
  cresce), limitado a 2,5.
- Decisão no fechamento do dia t, posição vale a partir de t+1. **Buffer de 10%**. Exposição
  máxima por mercado: 2× o valor de referência.
- Tamanho mínimo de lote dos CFDs não entra na simulação; a P5 informa quantas posições ficariam
  abaixo do mínimo com R$ 200 mil.

## 7. Critério de aprovação (só o candidato K2; todos precisam passar)

| # | Critério | Limite |
|---|---|---|
| A1 | Sharpe deflacionado, contando **todas** as tentativas (101 da M2 + as da Pesquisa 2) | ≥ 0,95 |
| A2 | Estabilidade no tempo: Sharpe > 0 em cada década (1980–89, 1990–99, 2000–09, 2010–23) | ≥ 3 das 4, inclusive 2010–23 |
| A3 | t-estatística do retorno médio diário, líquido | ≥ 3,0 |
| A4 | Anos civis com retorno líquido > 0 | ≥ 60% |
| A5 | **Contra a régua:** limite inferior de 90% (bootstrap em blocos de 21 dias) da diferença de Sharpe K2 − B1 | > 0 |
| A6 | Mercados com contribuição positiva | ≥ 60% |
| A7 | Maior contribuição de um único mercado | ≤ 25% |
| A8 | Maior contribuição de um único grupo | ≤ 50% |
| A9 | Estresse A e B: Sharpe líquido > 0 e DSR ≥ 0,90 | os dois |
| A10 | Contra o acaso: Sharpe acima do percentil 95 de 1.000 sinais deslocados no tempo | p ≤ 0,05 |
| V | Verificações: (1) usar o sinal do próprio dia (olhando o futuro) **infla** o resultado; (2) reexecução idêntica; (3) dados conforme a decisão 0014 | todas |

Mudanças em relação à M2: sem CPCV e sem PBO (as regras não têm parâmetro ajustado; não há o que
treinar nem configuração para escolher); estabilidade medida por década (A2); concentração também
por grupo (A8); anos positivos ≥ 60% (a tendência histórica fica perto disso).

**Holdout (só se A1–A10 e V passarem):** os itens B1–B4 e C da M2, sem mudança.

## 8. Tentativas e honestidade

- Registro novo (`pesquisa_p2/registro.db`); o DSR usa **101 + as tentativas da Pesquisa 2**.
- Orçamento da Pesquisa 2: **20 tentativas** (4 configurações + reexecuções e correções contadas).
- Defeito de implementação corrigido depois de ver um resultado é registrado como tentativa nova e
  explicado no relatório.
- **K2 é o único candidato.** Se K2 reprovar e K1 passar, K1 **não** vira candidato nesta versão
  (seria escolher depois de ver); isso exigiria uma versão nova, com +25.

## 9. Fora de escopo

Machine learning, valor, momentum relativo, agrícolas, gás natural, intradiário, busca de
parâmetros, ordens reais.

## 10. Limitações declaradas

- Retornos de CFD **reconstruídos** (preço + juros), não o histórico real de cada CFD.
- Dividendos fora dos EUA fixos em 2,5%; título reconstruído pela duração; energia sem carry.
- Margens de custo atuais aplicadas ao passado inteiro.
- Universo com 1 título e 2 energias quase iguais.
- Os anos 2000–2023 já foram muito olhados na M2 (compensado pelo DSR com 101 tentativas).
- Sem imposto.
