# Scalp no mini índice (WIN), fase 1: resultado da tentativa 1

**Veredito: REPROVA.** Rodada única em 29/10/2026, pelo critério do `docs/pre-registro-scalp-win-fase1.md`
(versão 1.0, SHA-256 `5c4e4bb8...6428e2`, commit anterior ao código que mede). Código:
`python -m trader.scalp_win`. Nenhuma regra simples de scalp passou do custo no período que não foi usado
para escolhê-la. O robô de scalp não segue para a demo sem uma ideia nova, com pré-registro novo.
Nada aqui é recomendação de investimento.

## Custo (M1)

| Medida | Valor |
|---|---|
| Spread de Roll, mediana dos 23 dias | 2,6 pontos (de 2,4 a 3,3 por dia) |
| Mudanças de preço de um tick (5 pontos) | 92% a 99% por dia |
| Empate por operação, E | **10 pontos** (vale o piso; a conta deu 2,5 + 2,6 + 2,5 = 7,6) |

O preço quase sempre anda de um tick em um tick. O Roll fica abaixo de um tick porque negócios seguidos do
mesmo lado (um agressor varrendo o livro) diminuem o vai e vem entre compra e venda que ele mede.

## As 8 regras (M3), ganho bruto médio por operação, em pontos

| Regra | Desenvolvimento (11 dias) | Validação (12 dias) | Operações (des. / val.) |
|---|---|---|---|
| momento 1 min | +2,9 | −1,4 | 5.388 / 5.925 |
| reversão 1 min | −2,9 | +1,4 | 5.388 / 5.925 |
| momento 2 min | +2,5 | +0,1 | 2.724 / 2.974 |
| reversão 2 min | −2,5 | −0,1 | 2.724 / 2.974 |
| momento 5 min | +10,3 | −3,2 | 1.098 / 1.199 |
| reversão 5 min | −10,3 | +3,2 | 1.098 / 1.199 |
| **momento 10 min (escolhida)** | **+23,9** | **−8,5** | 546 / 591 |
| reversão 10 min | −23,9 | +8,5 | 546 / 591 |

Escolhida no desenvolvimento: **momento de 10 minutos**. Na validação: −8,5 pontos por operação, intervalo
de 95% por bootstrap de dias de **−35,9 a +18,3**. O limite inferior está abaixo do empate de 10, e por isso
o critério reprova. Momento e reversão de mesmo horizonte são as mesmas operações com o sinal trocado. Na
prática, são 4 testes, e em todos o sinal do desenvolvimento se inverteu ou sumiu na validação.

## Movimento por horário (M2)

Média do tamanho da variação (|variação|), todos os dias: 72 pontos em 1 minuto, 103 em 2, 168 em 5 e 241
em 10. Um robô que acertasse sempre a direção passaria do custo com folga. O problema não é o custo, é
acertar a direção. A variação de 5 minutos é maior entre 10h00 e 11h30 (média de 260 a 320 pontos) e menor
perto do fechamento (63 pontos na faixa das 17h30).

## O que isso quer dizer

- **O ganho médio fica perto de zero e o ruído é grande.** Em operações de 10 minutos, o desvio de uma
  operação passa de 300 pontos. A diferença de +24 para −8 entre as metades é do tamanho do acaso.
- **23 pregões não bastam para achar uma vantagem de poucos pontos**, nem para descartá-la de vez. Bastam
  para dizer que regras de direção simples não têm uma vantagem grande e estável.
- **Uma ideia nova precisa de outro tipo de informação**: o livro de ofertas, o lado agressor, notícias com
  horário, ou ficar parado nos horários de pouco movimento. Esses dados não estão no arquivo grátis da B3.
  Cada ideia é pesquisa nova, com pré-registro novo escrito antes de medir.

## Limites

Os do pré-registro (seção 6): sem livro de ofertas nem lado agressor; ordem a mercado; um só regime de
mercado (setembro e outubro de 2026). Tentativas desta pesquisa: **1**.
