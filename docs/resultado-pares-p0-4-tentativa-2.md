# Pares cointegrados na B3 (ficha P0-4): resultado (tentativa 2 da P0-4)

Rodada em 04/11/2026 (registrada às 11h16 e terminada às 13h42, Brasília) pelo `docs/pre-registro-quant-p0-v0.2.md`.
O código conferiu o hash do pré-registro antes de calcular qualquer número. Código:
`python -m trader.estrategias.rodar_pares`, commit `6727134e`, feito antes da rodada. Registro: linha 21 (família P0-4,
nome `pares_b3`, 1 execução) em `pesquisa_quant/registro.db` (fora do Git). É a **2ª das 8 tentativas** da ficha. O
relatório bruto está em `pesquisa_quant/relatorios/rodada_pares_20261104_1642.md` (fora do Git). Só o desenvolvimento
(de 04/01/2010 a 08/09/2023); o holdout continua lacrado.

Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: **REPROVADO de novo**. Com os arquivos de hoje a regra fez 4 operações em 14 anos (eram 2), e o Sharpe do
excesso foi de 0,16 (era 0,05). Continua sendo uma regra que quase nunca acha um par, com resultado indistinguível do
acaso.

## Por que esta tentativa existe

A regra é a mesma da tentativa 1: nenhum parâmetro mudou. O que mudou foram os arquivos de entrada:

- A 1ª tentativa da C-1 (carteira combinada) roda cada camada de novo e confere o Sharpe gravado. A P0-4 deu 0,164 contra
  0,05 gravado ([`resultado-c1-tentativa-1.md`](resultado-c1-tentativa-1.md)).
- O código não tinha mudado. O COTAHIST, os preços ajustados, a DFP e o ITR da CVM e as ações em circulação foram
  regravados entre 03/11 23h53 e 04/11 02h08, depois da tentativa 1. Os arquivos antigos não existem mais.
- O pré-registro (seção 9) manda contar isso como defeito de dado. O Tiago aprovou rodar de novo como tentativa nova
  ("Sim, rodar", 04/11 ~10h52).

Para não repetir o problema, os 724 arquivos que a P0-4, a P0-5 e a C-1 leem foram copiados para
`pesquisa_quant/congelados/2026-11-04/`, cada um com o seu SHA-256 (`trader/estrategias/dados_congelados.py`). A marca do
manifesto está na especificação da linha 21. No fim da rodada o código conferiu que nenhum arquivo mudou durante a
conta.

## O veredito, item por item

| Item | O quê | Valor | Limite | Passou |
|---|---|---|---|---|
| A1 | Sharpe do excesso (0,16) > 0 e DSR com 155 tentativas | 0,17 | ≥ 0,95 | não |
| A2 | PBO (a ficha não tem alternativas) | — | não se aplica | sim |
| A3 | platô: menor Sharpe dos vizinhos ÷ Sharpe do candidato | −1,77 | ≥ 0,7 | não |
| A4 | custo, imposto e impacto como fração do Sharpe bruto (0,22) | 0,27 | ≤ 0,333 | sim |
| A5 | t-estatística do excesso (correção de Lo) | 0,57 | ≥ 3,0 | não |
| A6 | contra o acaso: p-valor dos sinais deslocados | 0,22 | ≤ 0,05 | não |
| A7 | contra o CDI: limite inferior de 90% da diferença | −0,41 | > 0 | não |
| A8 | estresse (custos × 2, impacto Y = 2): DSR | 0,16 | ≥ 0,9 | não |
| F1 | maior queda do pico | −0,4% | ≥ −35% | sim |
| V | olhar o futuro infla o Sharpe (0,14 contra 0,16) e as outras três verificações | 0,14 | futuro > 0,16 | não |

O V falhou como na tentativa 1: com 4 operações, entrar no próprio dia do sinal quase não muda nada. Isso não aponta
erro no código; só mostra que não há o que medir.

## As janelas

| Formação → operação | Pares testados | Cointegrados (BH) | Com meia-vida de 5 a 30 | Escolhidos |
|---|---|---|---|---|
| 3 primeiras (2010 e 01/2011) | 0 | 0 | 0 | nenhum |
| 07/2011 | 3.916 | 7 | 1 | ITSA4/HYPE3 |
| 07/2019 | 7.260 | 7 | 5 | EMBR3 com GFSA3, POMO4, MYPK3, HYPE3 e DTEX3 |
| as outras 23 | 3.403 a 13.695 | 0 a 12 | 0 | nenhum |

Fatos, comparando com a tentativa 1: a janela de 07/2019 testou 7.260 pares (eram 7.503) e escolheu 5 (eram 4, agora com
EMBR3/DTEX3). As outras janelas com par escolhido não mudaram. Dedução minha: os arquivos regravados mudaram o universo
de 2019 (liquidez e CNPJ), e isso basta para dobrar o número de operações de uma regra que quase não opera.

## O candidato e as leituras do Brasil

| Leitura | Sharpe do excesso | Retorno anual | Maior queda | Operações |
|---|---|---|---|---|
| candidato (custos base) | 0,16 | 8,9% | −0,4% | 4 |
| estresse | 0,15 | 8,9% | −0,4% | 4 |
| bruto (sem custo, aluguel, imposto nem impacto) | 0,22 | 8,9% | −0,4% | 4 |
| aluguel a 2% / 5% / 10% a.a. | 0,17 / 0,16 / 0,16 | 8,9% | −0,4% | 4 |
| lote de 100 | 0,17 | 8,9% | −0,4% | 4 |
| só pares do mesmo setor | 0,13 | 8,9% | −0,2% | 1 |
| só ON/PN da mesma empresa | −0,24 | 8,8% | −0,3% | 3 |
| só sobreviventes (sem as deslistadas) | 0,11 | 8,9% | −1,2% | 7 |
| CDI (régua) | — | 8,9% | 0,0% | — |

- O retorno anual de 8,9% continua sendo quase todo o CDI do caixa. As 4 operações somam R$ 121 de custos, R$ 51 de
  aluguel e R$ 484 de IR.
- **Sem as deslistadas** o Sharpe agora cai (0,11 contra 0,16), ao contrário da tentativa 1. Com tão poucas operações,
  a direção desse viés é ruído.
- **Platô:** os vizinhos vão de −0,29 (formação de 14 meses) a 0,30 (entrada em z = 1,6). Não há platô.

## Limites e cuidados

- Só o desenvolvimento: nada aqui diz o que o holdout mostraria, e com este veredito não há motivo para abri-lo.
- **Esta tentativa troca a tentativa 1 como a camada P0-4 da C-1** (linha 21 em vez da 14), porque é a que se reproduz
  com os arquivos de hoje. A tentativa 1 continua no registro e conta no DSR.
- **Os arquivos antigos da tentativa 1 se perderam**, então não dá para provar qual mudança de dado causou a diferença.
  A dedução acima (o universo de 2019) vem só da comparação das tabelas.
- Os proventos não entram nos preços. Nos pares o erro tende a se compensar entre as pernas; com 4 operações, não muda o
  veredito.
- Ligação de CNPJ pelo nome: dois modelos podem errar juntos, e papel líquido sem CNPJ sai do universo.
- O aluguel é uma taxa fixa por leitura; a taxa real muda e algumas ações nem têm doador.
- **Restam 6 das 8 tentativas.** Qualquer mudança na regra (formação maior, outro teste, só pares do mesmo setor) é uma
  tentativa nova, escrita antes de rodar. As leituras acima não autorizam escolher a melhor delas depois de vê-las.
- Nada aqui é recomendação de investimento.
