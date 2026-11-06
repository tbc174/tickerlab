# Estudo de eventos do IPE e PEAD na B3 (ficha P0-5): tentativa 1

Rodada em 04/11/2026 (registrada às 00h30 e terminada às 01h10, Brasília) pelo `docs/pre-registro-quant-p0-v0.1.md`.
O código conferiu o hash do pré-registro antes de calcular qualquer número. Código:
`python -m trader.estrategias.rodar_pead`, commit `6482c164`, feito antes da rodada. Registro: linha 16 (família P0-5,
nome `pead_b3`, 1 execução) em `~/TickerLab-Pesquisa/pesquisa_quant/registro.db` (fora do Git). É a **1ª das 6
tentativas** da ficha. O relatório bruto está em `pesquisa_quant/relatorios/rodada_pead_20261104_0410.md` (fora do Git).

Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: **REPROVADO**. Comprar o terço de empresas com a maior surpresa de lucro, um pregão depois do anúncio no IPE, rendeu
10,2% ao ano de 2013 a 2023. É o mesmo que o Ibovespa líquido (10,3%) e pouco acima do CDI (8,8%), e o excesso
sobre o CDI é indistinguível do acaso (t = 0,26, p = 0,41).

## O veredito (seção 5 do pré-registro)

| Item | O quê | Valor | Limite | Passou |
|---|---|---|---|---|
| A1 | Sharpe do excesso (0,08) e DSR com 125 tentativas | 0,43 | ≥ 0,95 | não |
| A2 | PBO | não se aplica (a ficha não tem alternativas) | - | sim |
| A3 | platô: menor Sharpe dos vizinhos ÷ Sharpe do candidato | 0,29 | ≥ 0,70 | não |
| A4 | custo, imposto e impacto como fração do Sharpe bruto (0,15) | 0,48 | ≤ 0,33 | não |
| A5 | t do excesso (correção de Lo) | 0,26 | ≥ 3 | não |
| A6 | p-valor contra 1.000 sinais deslocados | 0,41 | ≤ 0,05 | não |
| A7 | limite inferior de 90% da diferença contra CDI e Ibovespa | −0,43 e −0,32 | > 0 nas duas | não |
| A8 | estresse (custos × 2, impacto × 2): DSR | 0,41 | ≥ 0,90 | não |
| F1 | maior queda do pico | −33,5% | ≥ −35% | sim (por pouco) |
| V | o futuro infla (entrada em D: 0,21 > 0,08), reexecução idêntica, dados conformes, cortar o futuro não muda o passado | - | as quatro | sim |

As verificações (V) passaram: o código não olha o futuro, e entrar no dia D, antes do documento, dá um resultado bem
melhor, como deveria. A ficha falha no sinal, não na conta.

## A regra (fixada no código antes da rodada)

- **Lucro:** conta 3.11 do consolidado, trimestre a trimestre a partir dos acumulados do ano (ITR e DFP).
- **SUE:** a variação sazonal (trimestre contra o mesmo trimestre do ano anterior) dividida pelo desvio das 8 variações
  anteriores.
- **Data do anúncio (D):** o primeiro recebimento no IPE entre os documentos de resultado do trimestre (press-release,
  ITR, DFP, apresentação), depois do fim do trimestre. O IPE só tem a data, não a hora, então o **dia zero é D+1** e a
  entrada é no leilão de abertura do pregão seguinte ao dia zero (D+2).
- **Tercil de cima:** o corte vem dos anúncios dos 365 dias anteriores (no mínimo 30). Cada entrada leva 1/30 do
  patrimônio, a saída é na abertura 60 pregões depois e não há rebalanceamento.
- **Universo:** o da seção 8 (liquidez e deslistadas) no dia zero. Custos da F-B3, IR de 15% no swing com DARF no mês
  seguinte e CDI no caixa.

## O funil dos anúncios

| Etapa | Trimestres |
|---|---|
| trimestres com lucro na base | 21.054 |
| anúncio mais de 6 meses depois do trimestre | −2.483 |
| fora dos pregões | −882 |
| fora do universo (liquidez) | −12.108 |
| ITR ou DFP só na base no dia da entrada ou depois | −573 |
| sem 8 variações para o desvio | −987 |
| **com SUE** | **4.021** |
| sinais no tercil de cima | 1.308 |
| ignorados (o papel já estava na carteira) | 130 |
| posições abertas | 1.029 |

## O candidato, o estresse e o bruto (de 10/05/2013 a 08/09/2023)

| Leitura | Sharpe do excesso | Retorno anual | Maior queda | Posições | Retorno médio da posição | Acerto |
|---|---|---|---|---|---|---|
| candidato | 0,08 | 10,2% | −33,5% | 1.029 | 3,1% | 52% |
| estresse | 0,05 | 9,7% | −33,6% | 1.020 | 3,1% | 52% |
| bruto (sem custo, IR nem impacto) | 0,15 | 11,6% | −33,0% | 1.014 | 3,0% | 52% |
| CDI | - | 8,8% | 0,0% | - | - | - |
| Ibovespa líquido (BOVA11) | - | 10,3% | −46,9% | - | - | - |

A exposição média foi de 70% (o resto ficou no CDI). Custos e IR comeram quase metade do pouco que o sinal tinha.

## O teste do Brasil: o IPE não tem hora

| Leitura | Sharpe do excesso | Retorno anual |
|---|---|---|
| dia zero = D+1 (o candidato) | 0,08 | 10,2% |
| dia zero = D (otimista, proibido) | 0,03 | 9,2% |

A leitura otimista, que entra um pregão antes, foi **pior**, e não melhor. Então não há sinal de que o efeito esteja no
primeiro dia depois do anúncio: a diferença entre as duas leituras é ruído. O dia zero = D fica fora do resultado final,
como manda a ficha.

## O platô e as deslistadas

| Vizinho (±20%; inteiros arredondados) | Sharpe do excesso |
|---|---|
| 6 e 10 trimestres no desvio | 0,07 e 0,10 |
| fração de cima 0,27 e 0,40 | 0,16 e 0,05 |
| 48 e 72 pregões na posição | 0,18 e 0,02 |
| 24 e 36 posições | 0,06 e 0,10 |

O resultado varia de 0,02 a 0,18 conforme o vizinho. Isso é o ruído em torno de um Sharpe perto de zero, não um platô.
Usando só as ações que sobreviveram até o fim (828 posições), o Sharpe cai para 0,05. Neste caso, deixar as deslistadas
de fora não inflou o resultado.

## Estudo dos eventos: CAR (+1, +60) pelo modelo de mercado

São 53.419 documentos do IPE de empresas do universo, contando só a primeira versão de cada um e um por empresa, tipo e
dia zero. Os tipos com mais eventos:

| Tipo | Eventos | CAR médio | t |
|---|---|---|---|
| Comunicado ao Mercado · outros | 13.352 | −1,3% | −7,1 |
| Fato Relevante | 7.269 | −1,0% | −3,5 |
| Apresentações a analistas | 4.904 | −1,1% | −3,7 |
| Assembleia · AGE | 3.934 | −0,8% | −1,9 |
| Press-release | 3.530 | −0,3% | −0,9 |
| Assembleia · AGO | 2.303 | +1,2% | +2,6 |
| Aumento de capital por subscrição privada | 498 | −5,3% | −4,9 |
| Relatório de proventos | 205 | +3,1% | +2,8 |

| Tercil da SUE | Eventos | CAR médio | t |
|---|---|---|---|
| de baixo | 1.316 | +0,7% | +1,2 |
| do meio | 1.229 | −0,6% | −1,2 |
| de cima | 1.245 | −2,5% | −4,6 |

Estes são os fatos. As leituras abaixo são deduções minhas:

- Quase todos os tipos têm CAR médio negativo, perto de −1%. O mais provável é um viés do modelo de mercado na B3: a
  janela de estimação de 252 pregões dá um α que não continua depois do evento. Então vale comparar os tipos entre si e
  não contra o zero.
- Mesmo comparando os tercis entre si, o de cima ficou abaixo do de baixo. No desenvolvimento, a B3 não mostrou o PEAD
  na direção clássica dos EUA. O retorno bruto da posição (+3,1% em 60 pregões) e o CAR negativo do tercil de cima não se
  contradizem: o primeiro é o retorno total, e o segundo desconta o mercado e o α da janela.
- O sinal negativo de "aumento de capital por subscrição privada" (−5,3%) é o resultado que a literatura espera
  (diluição). Ele não foi testado como estratégia, e testá-lo pediria uma ficha nova, escrita antes, gastando tentativas.

## Limites e cuidados

- **Só o desenvolvimento** (até 08/09/2023): nada aqui diz o que o holdout mostraria, e abri-lo é decisão escrita do Tiago.
- **O período de avaliação começa na primeira posição (10/05/2013).** A SUE pede 12 trimestres de lucro, e a base de
  demonstrações começa em 2010. Isso foi declarado no código antes da rodada.
- **O t dos CARs exagera a confiança:** os eventos se sobrepõem no tempo e entre empresas (mesmo dia, mesmo setor).
- **O lucro é o do consolidado (3.11):** empresa que só publica o individual fica de fora.
- **Anúncio cujo ITR ou DFP só entrou na base no dia da entrada ou depois foi descartado** (573 casos), porque o
  número poderia ser de uma reapresentação.
- **A recuperação judicial não é filtrada:** o acervo não tem essa tabela (limitação declarada da seção 8).
- **O ajuste dos preços tem 42 saltos sem explicação** (os mesmos da F-B3), e o registro da pesquisa_p2 entra no DSR
  como 0 tentativas (ver `docs/registro-quant-reconstruido.md`).
- **A régua do Ibovespa é o BOVA11 comprado e mantido**, sem o IR da venda final. O CDI é o do BCB.
- **O IPE foi lido do acervo local** (`eventos/<ano>.parquet`). O COTAHIST anual de 2009 a 2023 foi baixado de novo da
  B3 em 03/11 (com o "pode baixar" do Tiago), com SHA-256 e lido em Python isolado (`-I`).
- **A rodada terminou com erro, mas só ao imprimir o relatório no terminal** (um "β" que o cp1252 do Windows não
  mostra). A conta, o registro e o relatório em arquivo já estavam gravados. O PR corrige a impressão e traz um teste de
  regressão. Essa correção não muda nenhum número.
- **Restam 5 das 6 tentativas.** O resultado está longe da barra (t de 0,26 contra 3; p de 0,41 contra 0,05). Gastar
  outra tentativa nesta regra só faria sentido com uma hipótese nova, escrita antes de rodar.
- Nada aqui é recomendação de investimento.
