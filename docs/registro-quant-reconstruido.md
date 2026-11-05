# Registro das P0: perdido em 03/11/2026 e reconstruído

O registro de tentativas das fichas P0 (`pesquisa_quant/registro.db`, fora do Git) ficava dentro da cópia do
repositório (worktree) da conversa que roda a pesquisa. Em 03/11/2026, logo depois do merge do PR #795, a
cópia foi apagada e levou junto o registro e os dados baixados (COTAHIST da B3, candles da Binance e caches
do BCB). Nada do que estava no Git se perdeu.

## O que mudou no código

- A pesquisa agora fica em `~/TickerLab-Pesquisa/pesquisa_quant` (ou na pasta da variável
  `TICKERLAB_PESQUISA_QUANT`), fora de qualquer cópia do repositório (`trader/registro.py`,
  `pasta_da_pesquisa_quant`). Há teste que confere que ela não fica dentro do repositório.
- Cada escrita no registro de verdade guarda uma cópia do banco (`registro_AAAAMMDD_HHMMSS_*.db`) no
  OneDrive, quando existe, ou em `pesquisa_quant/copias` (variável `TICKERLAB_COPIAS_DA_PESQUISA`). Ficam as
  50 mais recentes. Os registros de teste não guardam cópia.
- O registro da Pesquisa 2 (`pesquisa_p2/registro.db`) continua dentro da cópia do repositório e tem o
  mesmo risco. É de outra conversa: fica apontado aqui, sem mudança.

## Como o registro foi refeito

As 14 linhas foram refeitas dos relatórios de resultado em `docs/`, dos logs das rodadas e da conversa que
rodou as fichas, onde ficou impressa uma listagem completa do registro (ids 1 a 13; a linha 14 saiu em outras
duas impressões). Cada linha tem `"reconstruido": true` na especificação, com as fontes e a confiança.

| ids | Ficha | Tentativa | Execuções |
|---|---|---|---|
| 1 a 4 | P0-3 | tentativa 1 (candidato e três esquemas) | 1 cada |
| 5 a 8 | P0-3 | tentativas 2 e 3 e a alavancagem 1,0x | 3, 2, 2 e 2 |
| 9 e 10 | P0-3 | alavancagem 1,3x (WIN e DI1) | 1 cada |
| 11 | P0-1 | tendência BTC e ETH | 1 |
| 12 | P0-2 | tendência BOVA11 | 1 |
| 13 | P0-7 | simulador do SD | 1 |
| 14 | P0-4 | pares na B3 | 2 |

- **Total do DSR:** 123 (M2 101 + scalp 2 + 20 execuções), o mesmo do último veredito antes da perda (P0-4,
  tentativa 1). Os totais dos vereditos anteriores fecham com a mesma conta.
- **Lacunas:** o hash da especificação das linhas 1 a 4, 9, 10 e 13 não ficou impresso em lugar nenhum; nessas
  linhas o hash é o de um texto de reconstrução. O commit das linhas 1 a 4 é deduzido (confiança média).
- **Na dúvida, para cima:** nenhuma execução foi descontada. Uma ficha só volta a rodar a mesma configuração
  com uma execução a mais, como antes.
- **Pesquisa 2:** o registro dela não estava nesta cópia e entrou como 0 no total, mas houve ao menos uma
  rodada da P2. O 123 pode estar baixo; o número certo depende do registro da conversa dona da P2.

## O que não foi refeito

Os dados baixados não foram baixados de novo. O COTAHIST (cerca de 378 MB) só volta com o "pode" do Tiago,
quando uma ficha da B3 precisar dele.
