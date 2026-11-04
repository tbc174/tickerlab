# Estudo de eventos do IPE e PEAD na B3 (ficha P0-5): tentativa 2

Rodada em 04/11/2026 (registrada às 13h44 e terminada às 14h20, Brasília) pelo `docs/pre-registro-quant-p0-v0.2.md`.
O código conferiu o hash do pré-registro antes de calcular qualquer número. Código:
`python -m trader.estrategias.rodar_pead`, commit `6727134e`, feito antes da rodada. Registro: linha 22 (família P0-5,
nome `pead_b3`, 1 execução) em `pesquisa_quant/registro.db` (fora do Git). É a **2ª das 6 tentativas** da ficha. O
relatório bruto está em `pesquisa_quant/relatorios/rodada_pead_20261104_1720.md` (fora do Git). Só o desenvolvimento; o
holdout continua lacrado.

Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: **REPROVADO de novo**. Com os arquivos de hoje, comprar o terço com a maior surpresa de lucro rendeu
10,0% ao ano de 2013 a 2023 (eram 10,2%), com Sharpe do excesso de 0,07 (era 0,08). O excesso sobre o CDI continua
indistinguível do acaso (t = 0,22, p = 0,43).

## Por que esta tentativa existe

A regra é a mesma da tentativa 1 ([`resultado-pead-p0-5-tentativa-1.md`](resultado-pead-p0-5-tentativa-1.md)); nenhum
parâmetro mudou. A 1ª tentativa da C-1 rodou a P0-5 de novo e achou 0,0683 contra 0,0789 gravado, porque os arquivos de
entrada (COTAHIST, preços ajustados, DFP e ITR da CVM, ações em circulação) foram regravados depois da tentativa 1, e os
antigos não existem mais ([`resultado-c1-tentativa-1.md`](resultado-c1-tentativa-1.md)). O pré-registro (seção 9) conta
isso como defeito de dado, e o Tiago aprovou rodar de novo ("Sim, rodar", 04/11 ~10h52).

Os arquivos lidos estão congelados em `pesquisa_quant/congelados/2026-11-04/`, com o SHA-256 de cada um. A marca do
manifesto é a mesma da tentativa 2 da P0-4 ([`resultado-pares-p0-4-tentativa-2.md`](resultado-pares-p0-4-tentativa-2.md)),
e o código conferiu no fim que nada mudou durante a rodada. O Sharpe do excesso da linha 22 (0,0683) é o mesmo que a C-1
tinha achado de manhã.

## O veredito (seção 5 do pré-registro)

| Item | O quê | Valor | Limite | Passou |
|---|---|---|---|---|
| A1 | Sharpe do excesso (0,07) e DSR com 156 tentativas | 0,40 | ≥ 0,95 | não |
| A2 | PBO | não se aplica (a ficha não tem alternativas) | - | sim |
| A3 | platô: menor Sharpe dos vizinhos ÷ Sharpe do candidato | 0,46 | ≥ 0,70 | não |
| A4 | custo, imposto e impacto como fração do Sharpe bruto (0,15) | 0,53 | ≤ 0,33 | não |
| A5 | t do excesso (correção de Lo) | 0,22 | ≥ 3 | não |
| A6 | p-valor contra 1.000 sinais deslocados | 0,43 | ≤ 0,05 | não |
| A7 | limite inferior de 90% da diferença contra CDI e Ibovespa | −0,44 e −0,33 | > 0 nas duas | não |
| A8 | estresse (custos × 2, impacto × 2): DSR | 0,40 | ≥ 0,90 | não |
| F1 | maior queda do pico | −33,2% | ≥ −35% | sim (por pouco) |
| V | o futuro infla (entrada em D: 0,21 > 0,07), reexecução idêntica, dados conformes, cortar o futuro não muda o passado | - | as quatro | sim |

As verificações passaram como na tentativa 1: o código não olha o futuro, e a ficha falha no sinal, não na conta.

## O que mudou com os arquivos de hoje

| | Tentativa 1 (linha 16) | Tentativa 2 (linha 22) |
|---|---|---|
| fora do universo (liquidez) | 12.108 | 12.177 |
| ITR ou DFP só na base no dia da entrada ou depois | 573 | 567 |
| sem 8 variações para o desvio | 987 | 984 |
| trimestres com SUE | 4.021 | 3.961 |
| sinais no tercil de cima | 1.308 | 1.290 |
| posições | 1.029 | 1.014 |
| Sharpe do excesso | 0,079 | 0,068 |
| documentos do IPE no estudo de eventos | 53.419 | 52.162 |

Fatos: os 21.054 trimestres de lucro e os descartes por atraso (2.483) e fora dos pregões (882) são os mesmos. A diferença
está no universo e no número de documentos do IPE de empresas do universo. Dedução minha: o filtro de liquidez da seção 8
mudou com o COTAHIST e os preços regravados, e isso tirou 60 trimestres e 15 posições. Não dá para provar, porque os
arquivos antigos se perderam.

## O candidato, o estresse e o bruto (de 10/05/2013 a 08/09/2023)

| Leitura | Sharpe do excesso | Retorno anual | Maior queda | Posições | Retorno médio da posição | Acerto |
|---|---|---|---|---|---|---|
| candidato | 0,07 | 10,0% | −33,2% | 1.014 | 3,0% | 53% |
| estresse | 0,06 | 9,8% | −33,3% | 1.005 | 3,2% | 52% |
| bruto (sem custo, IR nem impacto) | 0,15 | 11,5% | −32,8% | 1.004 | 2,9% | 52% |
| CDI | - | 8,8% | 0,0% | - | - | - |
| Ibovespa líquido (BOVA11) | - | 10,3% | −46,9% | - | - | - |

A exposição média foi de 69%. Custos (R$ 8.127) e IR (R$ 20.270) comeram mais da metade do pouco que o sinal tinha.

## O teste do Brasil, o platô e as deslistadas

- **O IPE não tem hora:** o dia zero = D (otimista, proibido) deu 0,02, abaixo do candidato (0,07), como na tentativa 1.
  Não há sinal de que o efeito esteja no primeiro dia depois do anúncio.
- **Platô:** os vizinhos vão de 0,03 (fração de cima 0,40; 72 pregões) a 0,20 (48 pregões). É ruído em torno de um
  Sharpe perto de zero, não um platô.
- **Só sobreviventes** (812 posições): 0,05. Deixar as deslistadas de fora não inflou o resultado.

## Estudo dos eventos: CAR (+1, +60)

Os números se moveram pouco e as leituras da tentativa 1 continuam valendo. O tercil de cima da SUE teve CAR médio de
−2,3% (t = −4,4), abaixo do tercil de baixo (+0,7%). "Aumento de capital por subscrição privada" ficou em −4,9%
(t = −4,6). Comunicados e fatos relevantes ficaram perto de −1%, o que provavelmente é viés do modelo de mercado na B3.
Isso é dedução minha, como na tentativa 1.

## Limites e cuidados

- **Só o desenvolvimento** (até 08/09/2023): nada aqui diz o que o holdout mostraria, e abri-lo é decisão escrita do Tiago.
- **Esta tentativa troca a tentativa 1 como a camada P0-5 da C-1** (linha 22 em vez da 16), porque é a que se reproduz
  com os arquivos de hoje. A tentativa 1 continua no registro e conta no DSR.
- **O período de avaliação começa na primeira posição (10/05/2013):** a SUE pede 12 trimestres de lucro, e a base de
  demonstrações começa em 2010.
- **O t dos CARs exagera a confiança:** os eventos se sobrepõem no tempo e entre empresas.
- **O lucro é o do consolidado (3.11):** empresa que só publica o individual fica de fora.
- **A régua do Ibovespa é o BOVA11 comprado e mantido**, sem o IR da venda final. O CDI é o do BCB.
- **A frase do relatório bruto sobre a recuperação judicial está desatualizada.** Ela diz que a recuperação judicial
  não é filtrada porque o acervo não tem a tabela. Mas o universo da seção 8 (`fatores_b3.elegiveis_em`, que a P0-5 usa)
  já tira as empresas em recuperação judicial, lidas de `insolvencia/` no acervo. A frase é só texto fixo do rodador e
  não muda nenhum número; a correção fica para um PR separado. Se essa tabela não existia na tentativa 1, ela é mais
  uma causa possível da diferença. É uma hipótese, que não dá para provar.
- **Restam 4 das 6 tentativas.** Outra tentativa nesta regra só faria sentido com uma hipótese nova, escrita antes de
  rodar.
- Nada aqui é recomendação de investimento.
