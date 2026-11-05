# Carteira combinada das camadas (ficha C-1): tentativa 2

Rodada em 04/11/2026 (registrada às 14h21 e terminada às 14h41, Brasília) pelo `docs/pre-registro-quant-p0-v0.2.md`.
O código conferiu o hash do pré-registro antes de qualquer conta. Código: `python -m trader.estrategias.rodar_c1`,
commit `9272010a`, feito antes da rodada. Registro: linhas **23** (`c1_candidata`) e **24** (`c1_comparacao`), família
C-1, 1 execução cada, em `~/TickerLab-Pesquisa/pesquisa_quant/registro.db` (fora do Git). Com as linhas 19 e 20 da
tentativa 1, são **4 das 6 tentativas** da ficha. O relatório bruto está em
`pesquisa_quant/relatorios/rodada_c1_20261104_1741.md` (fora do Git). Só o desenvolvimento; o holdout continua lacrado.

Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: **as duas carteiras foram REPROVADAS**. A candidata (as seis camadas que operam) teve Sharpe do excesso de
0,13 de 2011 a 2023, com 9,5% ao ano e queda máxima de −9,7%. Custos e imposto comem mais da metade do que ela tinha, e
os vizinhos não sustentam o número. A comparação (as três camadas de maior Sharpe, escolhidas olhando o resultado) chegou
mais perto, com Sharpe de 0,50, mas também falhou.

## Por que esta tentativa existe

A tentativa 1 parou antes de combinar qualquer coisa ([`resultado-c1-tentativa-1.md`](resultado-c1-tentativa-1.md)):
a P0-4 e a P0-5 não reproduziam mais o Sharpe gravado, porque os arquivos de entrada foram regravados depois das rodadas
delas. O Tiago aprovou a saída recomendada ("Sim, rodar", 04/11 ~10h52):

1. Os 724 arquivos que a P0-4, a P0-5 e a C-1 leem foram copiados para `pesquisa_quant/congelados/2026-11-04/`, cada um
   com o seu SHA-256 (`trader/estrategias/dados_congelados.py`). A marca do manifesto (`acbfa71c…`) está na especificação
   das linhas 21 a 24. No fim de cada rodada o código conferiu que nenhum arquivo mudou durante a conta.
2. A P0-4 e a P0-5 rodaram de novo, cada uma como tentativa nova da própria ficha. As duas foram reprovadas outra vez
   ([P0-4, linha 21](resultado-pares-p0-4-tentativa-2.md); [P0-5, linha 22](resultado-pead-p0-5-tentativa-2.md)).
3. A C-1 passou a conferir as linhas 21 e 22, com tolerância exata, e rodou esta tentativa. Nenhuma regra da ficha mudou.

## A reprodução das camadas

| Camada | Linha | Gravado | Reexecução | Reproduz |
|---|---|---|---|---|
| P0-3 (risk parity a 1,0x) | 5 | 0,41 | 0,406 | sim (duas casas) |
| P0-1 (tendência em cripto) | 11 | 0,68 | 0,679 | sim (duas casas) |
| F-B3 (fatores) | 17 | −0,0307 | −0,0307 | sim (exato) |
| P0-4 (pares) | 21 | 0,1644 | 0,1644 | sim (exato) |
| P0-5 (PEAD) | 22 | 0,0683 | 0,0683 | sim (exato) |
| P0-2 BOVA11 | 12 | −0,16 | −0,159 | sim (duas casas) |
| P0-2 DI1 (só na comparação) | 12 | 0,44 | 0,442 | sim (duas casas) |

A rodada também gravou o hash da série base de cada camada, ao lado do Sharpe. Se os dados mudarem de novo, esse hash
mostra qual série mudou.

## O veredito da candidata (linha 23, de 02/02/2011 a 08/09/2023)

| Item | O quê | Valor | Limite | Passou |
|---|---|---|---|---|
| A1 | Sharpe do excesso (0,13) e DSR com 158 tentativas | 0,49 | ≥ 0,95 | não |
| A2 | PBO | não se aplica (a ficha não tem alternativas) | - | sim |
| A3 | platô: menor Sharpe dos vizinhos ÷ Sharpe do candidato | 0,12 | ≥ 0,70 | não |
| A4 | custo, imposto e impacto como fração do Sharpe bruto (0,35) | 0,62 | ≤ 0,33 | não |
| A5 | t do excesso (correção de Lo) | 0,50 | ≥ 3 | não |
| A6 | p-valor contra os sinais deslocados | 0,02 | ≤ 0,05 | sim |
| A7 | limite inferior de 90% da diferença contra o 60/40 e o CDI | −0,11 e −0,32 | > 0 nas duas | não |
| A8 | estresse (custos × 2, impacto × 2): DSR | 0,43 | ≥ 0,90 | não |
| F1 | maior queda do pico | −9,7% | ≥ −35% | sim |
| V | o futuro infla (0,40 > 0,13), reexecução idêntica, dados conformes, cortar o futuro não muda o passado | - | as quatro | sim |

| Leitura | Sharpe do excesso | Retorno anual | Volatilidade | Maior queda |
|---|---|---|---|---|
| candidata | 0,13 | 9,5% | 5,1% | −9,7% |
| estresse | 0,08 | 9,2% | 5,1% | −9,8% |
| bruto (sem custo nem IR) | 0,35 | 10,6% | 5,1% | −10,0% |
| sem a cripto | 0,09 | 9,3% | 5,2% | −11,1% |
| vizinhos (janela 202 e 302; teto 0,32 e 0,48; banda 0,16 e 0,24) | 0,02 a 0,17 | 8,9% a 9,7% | 4,4% a 5,7% | −8,4% a −11,0% |
| 60/40 (régua) | - | 8,2% | 14,7% | −29,2% |

Pesos médios: P0-4 40%, P0-3 20%, P0-2 BOVA11 19%, F-B3 10%, P0-5 7%, P0-1 4%; caixa 1%. Foram 37 rebalanceamentos. O
freio da F-B3 disparou em 16/03/2020 e a camada voltou em 16/03/2021; nenhum outro freio disparou.

Fatos:
- **A6 passou** (p = 0,02): a carteira montada com os sinais na data certa ganha da maioria das montagens com os sinais
  deslocados. Mas o ganho sobre o CDI (A5, A7) é pequeno demais para se distinguir de zero.
- **A P0-4 ficou com 40% do peso.** A camada de pares quase nunca opera (4 operações em 14 anos), então a série dela é
  quase toda CDI, com volatilidade perto de zero. Dedução minha: o peso pelo inverso da volatilidade dá muito peso a uma
  camada parada, e isso prende 40% da carteira num caixa disfarçado. Isso explica boa parte do Sharpe baixo, mas mudar a
  regra do peso seria uma tentativa nova, escrita antes de rodar.
- **Sem a cripto** (teste a), o Sharpe cai de 0,13 para 0,09. A P0-1 tem só 4% do peso e quase não se correlaciona com
  as outras (correlação mensal entre −0,05 e 0,16).

## A comparação (linha 24, de 02/08/2011 a 08/09/2023): só referência

A comparação junta as três camadas de maior Sharpe (P0-3, P0-1 e P0-2 DI1). **Ela foi escolhida olhando o resultado**,
então nenhum número dela vale como evidência; serve só para medir quanto a escolha a posteriori infla o resultado.

| Item | Valor | Limite | Passou |
|---|---|---|---|
| A1: Sharpe do excesso (0,50) e DSR com 158 tentativas | 0,93 | ≥ 0,95 | não |
| A3: platô | 0,91 | ≥ 0,70 | sim |
| A4: custo e imposto ÷ Sharpe bruto (0,80) | 0,38 | ≤ 0,33 | não |
| A5: t do excesso (Lo) | 1,85 | ≥ 3 | não |
| A6: p-valor contra os sinais deslocados | 0,22 | ≤ 0,05 | não |
| A7: limite inferior contra o 60/40 e o CDI | 0,04 e 0,05 | > 0 nas duas | sim |
| A8: estresse, DSR | 0,89 | ≥ 0,90 | não |
| F1: maior queda | −6,4% | ≥ −35% | sim |
| V: o futuro infla | −0,40 | > 0,50 | não |

Rendeu 10,9% ao ano, com volatilidade de 4,3%. Pesos médios: P0-3 39%, P0-2 DI1 39%, P0-1 9%; caixa 12%.

Fatos sobre o V da comparação: a leitura "com o futuro" começa só em 03/08/2021 (527 pregões, contra 3.025 da carteira)
e fica 66% em caixa. A da candidata também começa tarde (03/12/2019, 940 pregões), mas lá o futuro inflou e o V passou.
Dedução minha: a leitura com o futuro perde o começo do período, e por isso ela não se compara bem com a carteira. Isso
não muda nenhum veredito: a comparação já falha em A1, A4, A5, A6 e A8. Fica anotado como ponto a conferir no código
antes da próxima tentativa.

## O que esta rodada mostra

- Somar as seis camadas não criou um resultado que nenhuma delas tinha. Entre as camadas que operam, só a P0-3 e a P0-1
  têm Sharpe claramente acima de zero; as outras quatro estão perto de zero ou abaixo.
- Mesmo escolhendo as três melhores depois de ver os resultados, a carteira não passa pelo DSR com 158 tentativas. Isso
  mostra quanto as tentativas acumuladas pesam na conta.
- Compensar prejuízo entre camadas baixa o IR do ano (em 2016, por exemplo, de 2,7% para 2,2% da carteira). O ganho é
  real, mas pequeno perto do que o custo e o imposto comem.

## Limites e cuidados

- **Só o desenvolvimento** (até 08/09/2023): nada aqui diz o que o holdout mostraria, e abri-lo é decisão escrita do
  Tiago.
- **A referência do papel.** O papel (seção 5) pede o Sharpe da 1ª tentativa de cada carteira como referência. A 1ª
  (linhas 19 e 20) parou sem número, então a referência passa a ser esta: **0,134** para a candidata e **0,497** para a
  comparação. A comparação foi escolhida olhando o resultado.
- **As linhas 5, 11 e 12 guardam duas casas** (foram refeitas dos relatórios depois da perda de 03/11). Uma diferença
  menor que 0,005 passa como reprodução, mas não prova que a série é igual à original. As linhas 17, 21 e 22 são exatas.
- **Os arquivos congelados valem para esta data.** Se uma camada for rodada de novo com arquivos regravados, o código
  para, porque a marca muda.
- **Esta tentativa só existe por um defeito de dado corrigido depois de ver a reprodução** (seção 10). Na tentativa 1 a
  carteira não chegou a ser calculada, então nenhum número dela influenciou esta rodada.
- **Restam 2 das 6 tentativas.** Mudar o peso (para não dar 40% a uma camada parada), tirar camadas ou trocar a janela
  seria uma tentativa nova, com a hipótese escrita antes de rodar. Os vizinhos acima não autorizam escolher o melhor
  depois de vê-los.
- Nada aqui é recomendação de investimento.
