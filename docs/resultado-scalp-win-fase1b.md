# Scalp no mini índice (WIN), fase 1b: resultado da tentativa 2

**Veredito: REPROVA.** Rodada única em 29/10/2026, pelo critério do `docs/pre-registro-scalp-win-fase1b.md`
(versão 1.0, SHA-256 `d71a7c7c...0e23d87`, commit anterior ao código que mede). Código:
`python -m trader.scalp_win_1b`. Nem o fluxo do agressor nem o das corretoras de lote pequeno previu o preço
dos minutos seguintes o bastante para passar do custo no período que não foi usado para escolher a regra.
Nada aqui é recomendação de investimento.

## Os dados

Os mesmos 23 pregões da fase 1 (de 15/09 a 22/10/2026), com o mesmo hash por arquivo, o mesmo contrato do dia
e a mesma limpeza. São de 4,6 a 9,2 milhões de negócios por dia na janela das 09h15 às 17h45. Nenhum negócio
veio sem o código da corretora compradora ou vendedora.

**O grupo de lote pequeno**, escolhido só nos 11 pregões do desenvolvimento, tem 5 das 31 corretoras que
negociaram o WIN, e elas somam **57% do volume**. São corretoras de muitos negócios pequenos, e não do varejo.
O pré-registro já previa esse limite: robôs de alta frequência também negociam lotes pequenos.

## As 16 regras, ganho bruto médio por operação, em pontos

| Regra | Desenvolvimento (11 dias) | Validação (12 dias) | Operações (des. / val.) |
|---|---|---|---|
| F momento 1 min | +1,8 | −1,1 | 5.598 / 6.103 |
| F reversão 1 min | −1,8 | +1,1 | 5.598 / 6.103 |
| F momento 2 min | +2,2 | −1,3 | 2.794 / 3.047 |
| F reversão 2 min | −2,2 | +1,3 | 2.794 / 3.047 |
| F momento 5 min | +10,7 | +7,6 | 1.111 / 1.212 |
| F reversão 5 min | −10,7 | −7,6 | 1.111 / 1.212 |
| **F momento 10 min (escolhida)** | **+23,4** | **+1,3** | 550 / 600 |
| F reversão 10 min | −23,4 | −1,3 | 550 / 600 |
| C momento 1 min | −0,4 | −0,4 | 5.597 / 6.103 |
| C reversão 1 min | +0,4 | +0,4 | 5.597 / 6.103 |
| C momento 2 min | −3,6 | +2,0 | 2.793 / 3.047 |
| C reversão 2 min | +3,6 | −2,0 | 2.793 / 3.047 |
| C momento 5 min | −16,2 | +16,2 | 1.110 / 1.212 |
| C reversão 5 min | +16,2 | −16,2 | 1.110 / 1.212 |
| C momento 10 min | +4,8 | +6,2 | 550 / 600 |
| C reversão 10 min | −4,8 | −6,2 | 550 / 600 |

Escolhida no desenvolvimento: **F momento de 10 minutos**. Na validação: +1,3 ponto por operação, intervalo
de 95% por bootstrap de dias de **−19,5 a +21,1**. O limite inferior está abaixo do empate de 10, e por isso
o critério reprova.

## O que isso quer dizer

- **O fluxo do agressor quase repete o preço.** Pela regra do tick, o agressor é estimado pela direção do
  preço, então F momento conta quase a mesma história que o momento da fase 1. As duas fases deram números
  parecidos (+23,9 e +23,4 no desenvolvimento de 10 minutos), e nas duas a vantagem sumiu na validação.
- **O fluxo das corretoras troca de sinal entre as metades.** A regra C de 5 minutos foi de −16 para +16.
  Isso é ruído do tamanho que 23 pregões permitem, não uma vantagem.
- **Nenhuma regra fica acima de 10 nas duas metades.** A que mais se aproxima, F momento de 5 minutos (+10,7
  e +7,6), fica abaixo do empate na validação. Ela também não pode ser escolhida agora, olhando a tabela,
  porque isso seria escolher pelo período de teste.
- **Com estes dados grátis, a pesquisa do scalp para aqui.** Os dois tipos de informação que o arquivo da
  B3 tem (preço e corretoras) foram testados. O que falta é o lado agressor de verdade e o livro de ofertas,
  que vêm do MetaTrader 5 de uma corretora da B3 (pede a conta demo aberta pelo Tiago) ou de dado pago.
  Qualquer passo novo é pesquisa nova, com pré-registro novo escrito antes de medir.

## Limites

Os do pré-registro (seção 7): a regra do tick erra parte dos negócios sem mudança de preço; não há livro de
ofertas; a operação é a mercado; são 23 pregões de um só regime de mercado; e esses preços já tinham sido vistos
na fase 1. Tentativas desta pesquisa: **2** (fase 1 e fase 1b).
