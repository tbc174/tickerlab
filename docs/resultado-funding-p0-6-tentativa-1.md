# Monitor de funding e basis em cripto (ficha P0-6): tentativa 1

Rodada em 03/11/2026 (23h16, Brasília) pelo `docs/pre-registro-quant-p0-v0.1.md` (hash conferido pelo código
antes de qualquer número). Código: `python -m trader.estrategias.rodar_funding`. Registro: linha 15 (família
P0-6, nome `monitor_funding`) em `~/TickerLab-Pesquisa/pesquisa_quant/registro.db` (fora do Git; ver
`docs/registro-quant-reconstruido.md`). É a **1ª das 2 tentativas** da ficha, com 1 execução. Relatório bruto
em `pesquisa_quant/relatorios/rodada_funding_20261104_0216.md` (fora do Git).

Nada aqui é recomendação de investimento; funding passado não garante funding futuro.

Em uma frase: **hoje os dois alertas estão desligados**. O funding de BTC e ETH está baixo (líquido de 3,7% e
−3,3% a.a.), e o carry em reais fica abaixo do CDI porque o cupom cambial (6,2%) é maior que o funding. No
desenvolvimento os alertas ligaram muito em 2020 e 2021 e quase nada de 2022 em diante.

A P0-6 é monitor: **não passa pelo critério da seção 5**, não tem veredito de aprovação e não gera ordem.

## As definições (fixadas no código antes da rodada)

- **Funding do dia:** a soma dos pagamentos do perpétuo USD-M no dia de Brasília.
- **Anualizado bruto:** média dos últimos 7 dias × 365.
- **Líquido:** bruto menos o custo do carry (comprado à vista e vendido no perpétuo, montado e desfeito a cada
  30 dias: 4 pernas × 0,1% × 365/30 = **4,87% a.a.**) e, se positivo, menos 15% de IR.
- **Alerta 1:** líquido acima de 10% a.a.
- **Carry em reais:** líquido + CDI − cupom cambial de 30 dias (curva DOC da B3), os dois conhecidos antes do
  dia. **Alerta 2:** carry em reais acima do CDI, que é o mesmo que líquido acima do cupom.
- **Basis:** o índice de prêmio do perpétuo contra o índice à vista; só mostrado.

## Hoje (02/11/2026, o último dia completo)

| Par | Funding bruto | Líquido | Alerta 1 | CDI | Cupom 30d | Carry em reais | Alerta 2 | Basis |
|---|---|---|---|---|---|---|---|---|
| BTC | 9,2% | 3,7% | desligado | 13,6% | 6,2% | 11,2% | desligado | −0,027% |
| ETH | 1,6% | −3,3% | desligado | 13,6% | 6,2% | 4,2% | desligado | −0,019% |

Nos 18 dias do trecho recente (de 16/10, depois dos 7 dias de aquecimento, a 02/11) nenhum alerta ligou.

## Quanto tempo os alertas ficaram ligados no desenvolvimento

| Par | Ano | Dias | Líquido mediano | Alerta 1 | Alerta 2 |
|---|---|---|---|---|---|
| BTC | 2020 | 360 | 5,2% | 38% | 75% |
| BTC | 2021 | 365 | 10,2% | 50% | 86% |
| BTC | 2022 | 365 | 0,0% | 0% | 22% |
| BTC | 2023 (até 08/09) | 251 | 1,3% | 0% | 0% |
| ETH | 2020 | 360 | 8,1% | 48% | 95% |
| ETH | 2021 | 365 | 11,9% | 54% | 91% |
| ETH | 2022 | 365 | −1,6% | 0% | 16% |
| ETH | 2023 (até 08/09) | 251 | 1,4% | 2% | 2% |

- No período todo (1.341 dias por par), o alerta 1 ligou em 24% dos dias no BTC e 28% no ETH; a maior sequência
  foi de 77 e 131 dias. O alerta 2 ligou em 50% e 55% dos dias.
- O líquido vai de −4,2% (p10) a 32,0% (p90) no BTC e de −5,1% a 43,3% no ETH: o funding alto vem em ondas,
  nos anos de alta forte, e some depois.
- O cupom mediano do desenvolvimento foi 2,0%; no trecho recente, 5,5%. Com o cupom de hoje, o alerta 2 pede
  um funding líquido acima de ~6% a.a., o que dá cerca de 12% bruto.
- O basis mediano ficou perto de zero (−0,01% a −0,05%): o perpétuo anda colado no índice à vista.

## Os dados

| Fonte | O quê | Período |
|---|---|---|
| Binance Vision (meses) | funding e índice de prêmio de BTCUSDT e ETHUSDT | 01/2020 a 08/09/2023 (antes de 2020 o Vision não tem arquivo) |
| API pública da Binance | os mesmos dois | 10/10/2026 a 02/11/2026 |
| B3, taxas referenciais | curva DOC (cupom limpo), um arquivo por fim de mês no desenvolvimento e um por pregão no recente | 08/2019 a 09/2023 e 10/2026 |
| BCB, SGS 12 | CDI | os dois trechos |

- 249 arquivos, 20 MB, em `pesquisa_quant/funding` (fora do Git), com SHA-256 em `sha256.json`. O arquivo da B3
  é um executável que se descompacta: não foi executado, só lido com `zipfile`. A leitura rodou em Python
  isolado (`-I`).
- O holdout (10/10/2023 a 09/10/2026) não foi baixado: todo pedido passa por uma conferência que recusa
  qualquer data dele, e há teste para isso.
- A linha 520 da fila também falava da Hyperliquid e do open interest; ficaram de fora porque a ficha e o
  "pode baixar" do Tiago só cobrem a Binance, o cupom e o CDI.

## Limites e cuidados

- Monitor, não estratégia: sem backtest, sem ordem e sem critério de aprovação. Os percentuais de dias com
  alerta não dizem quanto um carry teria rendido.
- O custo supõe montar e desfazer o carry a cada 30 dias, sem impacto, spread, margem parada nem o risco da
  corretora. Não inclui IOF nem câmbio, que pesam para quem sai do real.
- No desenvolvimento o cupom é o do último fim de mês (atraso de até um mês); no recente, o da véspera. Os
  primeiros dias do trecho recente (10 a 13/10) ainda não tinham curva da B3.
- O cupom de 30 dias perto da virada do mês sofre o efeito da PTAX: a ponta curta da curva DOC é ruidosa.
- O funding de 8 h pode mudar de intervalo (a Binance encurta em dias agitados); a soma por dia já cobre isso.
- O registro grava o commit `e19f9ed1` (só um documento a mais que `98b2c648`, o código da rodada): o commit
  do documento entrou durante a coleta.
- Binance só para uso interno (CC BY-NC-SA).
- Resta 1 tentativa da P0-6 (só reexecução da coleta). Rodar de novo para atualizar o "hoje" gasta essa
  tentativa; um monitor diário de verdade pede uma versão nova do pré-registro.
- Nada aqui é recomendação de investimento.
