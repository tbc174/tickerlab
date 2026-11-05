# Carteira combinada das camadas (ficha C-1): tentativa 1, parada por defeito de dado

Rodada em 04/11/2026 (registrada às 04h15, terminada às 04h23, Brasília) pelo `docs/pre-registro-quant-p0-v0.2.md`.
O código conferiu o hash do pré-registro antes de qualquer conta. Código: `python -m trader.estrategias.rodar_c1`,
commit `96b37e66`, feito antes da rodada. Registro: linhas **19** (`c1_candidata`) e **20** (`c1_comparacao`), família
C-1, 1 execução cada, em `~/TickerLab-Pesquisa/pesquisa_quant/registro.db` (fora do Git). São **2 das 6 tentativas**
da ficha: cada rodada registra as duas carteiras. O relatório bruto está em
`pesquisa_quant/relatorios/rodada_c1_20261104_0723.md` (fora do Git).

Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: **a rodada parou antes de combinar qualquer coisa**. Duas das seis camadas da candidata, a P0-4 (pares)
e a P0-5 (PEAD), não reproduziram o Sharpe que o registro gravou para elas. A seção 9 manda parar nesse caso e contar
a parada como defeito, e foi o que o código fez. Nenhum número da carteira combinada foi calculado.

## A reprodução das camadas

Antes de usar a série de uma camada, a C-1 roda a camada de novo com o código da `main` e confere o Sharpe do excesso
contra a linha dela no registro (seção 9). As linhas 5, 11, 12 e 14 foram refeitas dos relatórios depois da perda de
03/11 e guardam duas casas, então ali reproduzir é cair no mesmo arredondamento (±0,005). As linhas 16 e 17 guardam o
número exato.

| Camada | Linha | Gravado | Reexecução | Reproduz |
|---|---|---|---|---|
| P0-3 (risk parity a 1,0x) | 5 | 0,41 | 0,406 | sim |
| P0-1 (tendência em cripto) | 11 | 0,68 | 0,679 | sim |
| F-B3 (fatores) | 17 | −0,0307 | −0,0307 | sim (exato) |
| P0-4 (pares) | 14 | 0,05 | 0,164 | **não** |
| P0-5 (PEAD) | 16 | 0,0789 | 0,0683 | **não** |
| P0-2 BOVA11 | 12 | −0,16 | −0,159 | sim |
| P0-2 DI1 (só na comparação) | 12 | 0,44 | 0,442 | sim |

A comparação (P0-3, P0-1 e DI1) tem as três camadas reproduzidas, mas a seção 9 fala em parar **a rodada**. O código
registra as duas carteiras antes de carregar qualquer dado e para as duas juntas; as duas linhas contam.

## A causa: os arquivos de entrada mudaram depois das rodadas das camadas

O código das duas camadas não mudou desde as rodadas delas (`git log` de `pares.py`, `pead.py` e dos carregadores).
O que mudou foram os arquivos em `~/TickerLab-Pesquisa/pesquisa_quant/f_b3/`:

| Arquivo | Gravado em (04/11, Brasília) | Rodada da camada |
|---|---|---|
| COTAHIST anuais (mudança da pasta para fora das cópias, #802) | 03/11 23h53 | P0-4: 03/11 22h26 |
| preços ajustados e conferência do ajuste | 00h01 | P0-4: antes |
| DFP e ITR da CVM (baixados de novo) | 01h58 | P0-5: 01h10 |
| ações em circulação | 02h08 | P0-5: antes |

A F-B3 (linha 17) rodou às 02h46, já com os arquivos novos, e por isso reproduz com exatidão. A prova na P0-5: os
trimestres com lucro são os mesmos 21.054, mas hoje 12.177 ficam fora do universo de liquidez, contra 12.108 na
rodada gravada. Com isso, 3.961 trimestres têm SUE, contra 4.021. Os arquivos antigos foram sobrescritos e não há cópia
deles. Então **as linhas 14 e 16 não se reproduzem mais com nenhum código**.

Isso não é escolha da C-1, e a C-1 não pode contornar: usar a série de hoje da P0-4 seria usar uma camada que nenhuma
tentativa registrou, com Sharpe de 0,16 em vez de 0,05.

## O que muda para a próxima rodada

- **Hash da série de cada camada** (`camadas_da_combinada.hash_da_serie`): a próxima rodada da C-1 grava, ao lado do
  Sharpe, a impressão digital da série base de cada camada. Assim, quando os dados mudarem de novo, fica claro quais
  séries mudaram.
- **Decisão que fica com o Tiago** (nota em `esperando/` e pedido na Central). Para a C-1 rodar de verdade, as linhas
  14 e 16 precisam ser de séries que se reproduzem. A recomendação é rodar a P0-4 e a P0-5 de novo com os arquivos de
  hoje, cada uma como tentativa nova da própria ficha (defeito de dado, contado no orçamento dela: P0-4 iria a 2 de 8 e
  P0-5 a 2 de 6), com os arquivos congelados por hash. Depois, a tentativa 2 da C-1, que fica em 4 de 6. Como o
  defeito foi corrigido depois de ver um resultado, a rodada seguinte é tentativa nova, explicada no relatório (seção
  10). Aqui o resultado visto é só a reprodução, porque a carteira não chegou a ser calculada.

## Limites e cuidados

- **Nenhum número da carteira combinada existe ainda.** O papel (seção 5) pede o Sharpe da 1ª tentativa de cada
  carteira como referência, e a C-1 ainda não tem esse número.
- As linhas 5, 11, 12 e 14 foram refeitas dos relatórios (duas casas). Uma diferença menor que 0,005 nelas passa como
  reprodução, mas não prova que a série é igual à original.
- Na carga para esta rodada, o PTAX e o IPCA do BCB foram baixados de novo da mesma fonte aprovada, porque o cache não
  existia nesta cópia. O CDI veio do cache.
- Os vizinhos, o estresse, o acaso (A6), as réguas, o teste sem cripto, a correlação e o IR compensado estão no código
  e nos testes (`tests/test_trader_combinada*.py`), mas não rodaram com os dados de verdade.
- A comparação (as três de maior Sharpe) foi escolhida olhando o resultado. Quando rodar, cada número dela vem com
  esse aviso.
