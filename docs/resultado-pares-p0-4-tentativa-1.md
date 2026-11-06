# Pares cointegrados na B3 (ficha P0-4): resultado (tentativa 1 da P0-4)

Rodada em 03/11/2026 (22h26, Brasília) pelo `docs/pre-registro-quant-p0-v0.1.md` (hash conferido pelo código
antes de qualquer número), com a base da linha 577 completada (`docs/conferencia-base-b3-2009-2023.md`).
Código: `python -m trader.estrategias.rodar_pares`. Registro: linha 14 (família P0-4, nome `pares_b3`) em
`pesquisa_quant/registro.db` (fora do Git); é a **1ª das 8 tentativas** da ficha, com **2 execuções**. A 1ª
execução (commit `aaba4613`, o que o registro guarda) quebrou no A6 antes de mostrar qualquer número: um
fechamento zero de BGIP4 no arquivo da B3 virava retorno infinito. A 2ª (commit `6fae08c4`, com a correção do
leitor e do A6, sem mudar a regra) é a deste relatório. Relatório bruto em
`pesquisa_quant/relatorios/rodada_pares_20261104_0126.md` (fora do Git). Só o desenvolvimento (de 04/01/2010
a 08/09/2023); o holdout continua lacrado.

Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: **REPROVADO**. A regra quase não operou: em 26 das 28 janelas nenhum par passou no teste de
cointegração com a correção de Benjamini-Hochberg e na faixa de meia-vida, e a carteira passou 14 anos no CDI
com **2 operações**. Não é uma estratégia que perde dinheiro; é uma regra que, na B3, quase nunca acha um par.

## O veredito, item por item

| Item | O quê | Valor | Limite | Passou |
|---|---|---|---|---|
| A1 | Sharpe do excesso (0,05) > 0 e DSR com 123 tentativas | 0,091 | ≥ 0,95 | não |
| A2 | PBO (a ficha não tem alternativas) | — | não se aplica | sim |
| A3 | platô: menor Sharpe dos vizinhos ÷ Sharpe do candidato | −6,06 | ≥ 0,7 | não |
| A4 | custo, imposto e impacto como fração do Sharpe bruto (0,09) | 0,46 | ≤ 0,333 | não |
| A5 | t-estatística do excesso (correção de Lo) | 0,17 | ≥ 3,0 | não |
| A6 | contra o acaso: p-valor dos sinais deslocados | 0,39 | ≤ 0,05 | não |
| A7 | contra o CDI: limite inferior de 90% da diferença | −0,50 | > 0 | não |
| A8 | estresse (custos × 2, impacto Y = 2) | 0,084 | ≥ 0,9 | não |
| F1 | maior queda do pico | −0,2% | ≥ −35% | sim |
| V | olhar o futuro infla o Sharpe (0,02 contra 0,05) e as outras três verificações | 0,02 | futuro > 0,05 | não |

O V falhou porque a versão que executa no próprio sinal (olhando o futuro) não ficou melhor. Com 2 operações
o atalho quase não muda nada, então o V não acusa erro no código; só confirma que não há o que medir.

## As janelas: por que quase nada operou

| Formação → operação | Pares testados | Cointegrados (BH) | Com meia-vida de 5 a 30 | Escolhidos |
|---|---|---|---|---|
| 3 primeiras (2010 e 01/2011) | 0 | 0 | 0 | nenhum |
| 07/2011 | 3.916 | 7 | 1 | ITSA4/HYPE3 |
| 07/2019 | 7.503 | 4 | 4 | EMBR3 com GFSA3, POMO4, MYPK3 e HYPE3 |
| as outras 23 | 3.403 a 14.196 | 0 a 12 | 0 | nenhum |

- **As três primeiras janelas ficam vazias:** o universo da seção 8 exige balanço divulgado nos 12 meses
  anteriores, e os balanços do acervo começam em 2010.
- **Pouco poder do teste:** com 12 meses de formação e milhares de pares por janela, a correção de
  Benjamini-Hochberg deixa passar quase nada (0 a 12 por janela), e o filtro de meia-vida corta o resto. Isso
  já estava nos "Limites e cuidados" da ficha antes da rodada.
- **Os pares escolhidos** não têm relação econômica óbvia (Embraer com Gafisa, Marcopolo, Iochpe e Hypera).
  É o que se espera de cointegração por acaso entre milhares de testes.

## O candidato e as leituras do Brasil

| Leitura | Sharpe do excesso | Retorno anual | Maior queda | Operações |
|---|---|---|---|---|
| candidato (custos base) | 0,05 | 8,9% | −0,2% | 2 |
| estresse | 0,04 | 8,9% | −0,2% | 2 |
| bruto (sem custo, aluguel, imposto nem impacto) | 0,09 | 8,9% | −0,2% | 2 |
| aluguel a 2% / 5% / 10% a.a. | 0,05 / 0,05 / 0,04 | 8,9% | −0,2% | 2 |
| lote de 100 | 0,05 | 8,9% | −0,2% | 2 |
| só pares do mesmo setor | 0,13 | 8,9% | −0,2% | 1 |
| só ON/PN da mesma empresa | −0,18 | 8,8% | −0,2% | 2 |
| só sobreviventes (sem as deslistadas) | 0,11 | 8,9% | −1,2% | 7 |
| CDI (régua) | — | 8,9% | 0,0% | — |

- O retorno anual de 8,9% é quase todo o CDI do caixa; as duas operações somam R$ 45 de custos, R$ 31 de
  aluguel e R$ 127 de IR.
- **Sem as deslistadas** a regra opera mais (7 vezes) e o Sharpe dobra. É o viés de sobrevivência que a
  seção 2 do pré-registro manda medir: a base sem as empresas que sumiram faria a regra parecer melhor.
- **Platô:** os vizinhos vão de −0,29 (formação de 14 meses) a 0,41 (entrada em z = 1,6). Nenhum é estável,
  e o melhor deles é uma leitura do mesmo candidato, não outra tentativa (seção 9).

## Base usada

- 3.428 papéis do COTAHIST de 2009 a 2023, com 2.365 que deixaram de negociar no período.
- Preços ajustados por 515 eventos do formulário de referência e 461 desdobramentos pelo preço; os proventos
  ficam de fora (limitação declarada).
- CNPJ de 380 dos 394 papéis líquidos (77 emissores antigos ligados pelo nome e conferidos por dois modelos).

## Limites e cuidados

- Só o desenvolvimento: nada aqui diz o que o holdout mostraria, e com este veredito não há motivo para
  abri-lo.
- Os proventos não entram nos preços. Nos pares o erro tende a se compensar entre as pernas; com 2 operações,
  não muda o veredito.
- Ligação de CNPJ pelo nome: dois modelos podem errar juntos. 14 papéis líquidos ficaram sem CNPJ e saem do
  universo (até 2% dos papéis de 2010 em diante).
- O aluguel é uma taxa fixa por leitura; a taxa real muda e algumas ações nem têm doador.
- A 1ª execução quebrou e foi refeita na mesma tentativa, depois de corrigir um defeito de dado, sem nenhum
  número visto e sem mudar a regra. As duas execuções ficam no registro.
- **Próximas tentativas da P0-4 (restam 7):** qualquer mudança (formação maior, outro teste, só pares do
  mesmo setor) é uma tentativa nova, escrita antes de rodar. As leituras acima não autorizam escolher a
  melhor delas depois de vê-las.
