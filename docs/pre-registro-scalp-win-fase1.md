# Scalp no mini índice (WIN), fase 1: critério escrito antes (pré-registro)

**Status: VIGENTE, versão 1.0, escrita em 29/10/2026 antes de qualquer medida.** O commit que traz este
arquivo vem antes do commit do código que mede; a ordem fica no histórico do Git. Pedido do Tiago em
29/10/2026 ("Vamos começar agora"). Pesquisa à parte da M2: não usa o registro da M2 (`pesquisa_m2/`), não
toca no holdout dela e não muda o `docs/pre-registro-m2-v0.4.md`.

> **Aprovar aqui não quer dizer lucro.** Aprovar só justifica a fase 2: um robô em conta demo, com as
> travas de risco, e só com autorização escrita do Tiago (regra 1 do `trader/AGENTS.md`). Reprovar é um
> resultado válido e será registrado como tal. Nada aqui é recomendação de investimento.

## 1. A pergunta

Um robô de scalp simples no WIN, com 1 a 5 contratos e saída em poucos minutos, ganha em média por
operação, **antes dos custos**, mais do que os custos? Se nem regras simples passam do empate no período
que não foi usado para escolhê-las, o robô de scalp não segue para a demo sem uma ideia nova.

## 2. Dados (fechados nesta versão)

- **Fonte:** o arquivo grátis de negócios da B3 (`b3-negocios`), guardado pelo arquivista, lido por
  `base/intradiario_b3.ler_negocios`. Cópia do PC, em `TickerLab-Acervo/acervo/bruto/b3-negocios/2026/`.
- **Contrato do dia:** o símbolo `WIN` + letra do mês + ano (regex `^WIN[FGHJKMNQUVXZ]\d\d$`) com o maior
  volume no boletim oficial (PR) do dia, lido do selo guardado em `intradiario/b3/selo/<dia>.parquet`.
- **Um dia entra só se o selo desse contrato for `completo`** (o arquivo bate com o boletim oficial em
  abertura, máxima, mínima, fechamento, volume e negócios). A regra usa só o boletim, nunca o resultado.
- **Negócios usados:** sessão regular (1); sem as linhas de cancelamento e sem os negócios cancelados; sem
  os negócios inseridos depois (identificador que não é múltiplo de 10); `DataNegocio` igual ao pregão.
- **Janela do dia:** das 09h15 às 17h45 (horário de São Paulo), longe dos leilões de abertura e de
  fechamento. Ordem dos negócios: instante e identificador.

| Pregão | Contrato | Selo | Situação | SHA-256 do arquivo |
|---|---|---|---|---|
| 2026-09-15 | WINV26 | completo | entra | `1b544fed0dc4c1d365c7c671232eeaf776bf3048875fac542ee5b70f79fbb072` |
| 2026-09-16 | WINV26 | completo | entra | `63c96cdf4c8d743b800ed76e8bfe80ee7a3f9e062cf1d773400171e2caa5d2b1` |
| 2026-09-17 | WINV26 | completo | entra | `f186080ae01b193bd153c310b5c124dd5feeae8a21f7dbb7b0cafca11f48a6f3` |
| 2026-09-18 | WINV26 | completo | entra | `d99f509eefb5c33ad6de6641fff4e14ce43c412dc937eb5c51bd2ef4998efd89` |
| 2026-09-21 | WINV26 | completo | entra | `63f5de9f59dbc1a90e8e8361b2f1d45c55551bec4ae0e02c9cf194f7fc14f588` |
| 2026-09-22 | WINV26 | incompleto | fora | `b5f481cb7060203695ec7a74fdc3c71c83366bc5cc4b876bbe15670a2fc84c07` |
| 2026-09-23 | WINV26 | completo | entra | `df0b40253a12b0efe8c65959da65f8095a5097f847c7593a02a267311c43b271` |
| 2026-09-24 | WINV26 | completo | entra | `86db531abe795b3ddd4ffcd62da2a32d9285e450c01e75b1e2b1779e5dd9b04f` |
| 2026-09-25 | WINV26 | incompleto | fora | `955d799aabbc5c348cc55be789b80ca438f6c839a98691397127f9b7eb3416bc` |
| 2026-09-28 | WINV26 | completo | entra | `e45d6ca309e52f8e0b9b68169f38e6e325c20aabae163c1f36bed8dcd0cb9aaa` |
| 2026-09-29 | WINV26 | incompleto | fora | `1a7c580380ec8c5e148884dbf1655f5f2d9a96a9982b02422267f4becb42b085` |
| 2026-09-30 | WINV26 | completo | entra | `7f004e6abe5d25187fea3e0d27a46e0cfa90dfb51af2da27267709b44428f322` |
| 2026-10-01 | WINV26 | completo | entra | `29f7c5804ae8ed0d541dc303f44e5a8046b10f7355bafea09ac62dd567c7067a` |
| 2026-10-02 | WINV26 | completo | entra | `d7d0a32e539d8b1bbaec16540c7f04df3e7529330648125494473e1285365e0d` |
| 2026-10-05 | WINV26 | completo | entra | `3cae4cb5314fbf88787d0f66fb48d0d18614e23475bcf4b16f3306947d278a9b` |
| 2026-10-06 | WINV26 | completo | entra | `8e397b0dcb38551afcf82969aa77f56edeed8d05acf9d739c4afbbeca6538884` |
| 2026-10-07 | WINV26 | completo | entra | `1436aff7e664229549d965442abb68aa4b3a5f7cf8192d4e0dfa5c6d51d2a7b7` |
| 2026-10-08 | WINV26 | completo | entra | `692a94a7c2199fea578f2724cd8d8565f2f3978625885e031f44dba9195e6400` |
| 2026-10-09 | WINV26 | incompleto | fora | `799bcf06be7da994d61538ce7a2c9d22ed0fd220e88cc664e206cea4a4298029` |
| 2026-10-13 | WINV26 | completo | entra | `3bfbe976a4e9415fe18af31b755cbbd2c46904f76bddbe8618d71df0058e5c91` |
| 2026-10-14 | WINZ26 | completo | entra | `0d0af93ec3d827e4a94cdb8589be18beaab951ff7ca5dad4cd5102a399d416d8` |
| 2026-10-15 | WINZ26 | completo | entra | `3488103acb44cf40f3c35372cfbc23d0a00776577952e433a45f496f3d00832f` |
| 2026-10-16 | WINZ26 | completo | entra | `4cd327d297d742779f06b242ffa291f2147321ee7aecafaabfee3e66c575a64e` |
| 2026-10-19 | WINZ26 | completo | entra | `81bee21c2eec77c99fb36587dc17b13611692f703276be83b6af13cbf1100317` |
| 2026-10-20 | WINZ26 | completo | entra | `55fc7791271f9d6ab3cda974bd166fb81e7bbd50f20180a5b7bf3bdf7c70a5b6` |
| 2026-10-21 | WINZ26 | completo | entra | `aae19a5d4a32e151a20a0692688ae3dd74dc822b49bdd3132d819088bd312840` |
| 2026-10-22 | WINZ26 | completo | entra | `ce24e1ce54266d37fca9c774dbec4eb28fb43e9f411e36b4a0e6d1791cda084e` |

Entram **23 pregões**. **Desenvolvimento:** os 11 primeiros (15/09 a 02/10). **Validação:** os 12 últimos
(05/10 a 22/10). Arquivo com hash diferente do da tabela: a rodada para e não mede.

## 3. Medidas

Pontos do WIN: 1 ponto = R$ 0,20 por contrato; 1 tick = 5 pontos.

- **M1. Custo efetivo do spread (S):** por dia, a medida de Roll sobre as mudanças de preço de negócio a
  negócio, S = 2·√(−cov(Δpₜ, Δpₜ₋₁)), em pontos (0 quando a covariância não é negativa). S é a mediana dos
  23 dias. Também a fração das mudanças de preço diferentes de zero que são de um tick.
- **Empate por operação:** E = máx(10; 2,5 + S + 2,5) pontos. O primeiro 2,5 é a tarifa da B3 de ida e
  volta (cerca de R$ 0,50 por contrato, corretagem zero); o segundo é meio tick de derrapagem média. O
  piso de 10 é o cenário C do relatório da pesquisa (spread de 1 tick e derrapagem em metade das saídas).
- **M2. Movimento por horário:** barras de 1 minuto com o preço do último negócio de cada minuto (minuto
  sem negócio herda o anterior). Por faixa de 30 minutos e por horizonte h ∈ {1, 2, 5, 10} minutos: desvio
  padrão e média do valor absoluto da variação de h minutos, em pontos. A média de |variação| é o teto de
  um robô que acertasse sempre a direção; ela é informativa e não entra no critério.
- **M3. Regras de scalp simples (8 variantes, toda a lista):** para cada h ∈ {1, 2, 5, 10} e cada direção
  ∈ {momento, reversão}. A cada h minutos, a partir de 09h15 + h, o robô olha a variação dos últimos h
  minutos: se subiu, compra (momento) ou vende (reversão) 1 contrato; se caiu, o contrário; se ficou igual,
  não opera. Sai h minutos depois. Sem sobreposição; a última entrada é a que sai até 17h45. Ganho bruto
  por operação = direção × (preço na saída − preço na entrada), em pontos.

Limite conhecido: o preço do último negócio oscila entre a compra e a venda, e isso faz a reversão de
1 minuto parecer melhor do que é. O custo S, medido do mesmo arquivo, desconta exatamente esse efeito.

## 4. Critério de aprovação

1. No desenvolvimento, escolhe-se **uma** variante: a de maior ganho bruto médio por operação.
2. Na validação, mede-se **só essa variante**: o ganho bruto médio por operação e o intervalo de 95% por
   bootstrap de dias (10.000 reamostras dos 12 dias, com reposição, semente 20261029, percentis 2,5 e 97,5).
3. **APROVA** (fase 2 justificada para essa variante) se o limite inferior do intervalo for maior que E.
   **REPROVA** em qualquer outro caso.
4. As 8 variantes aparecem no relatório nas duas metades, para transparência; só a escolhida decide.

## 5. Tentativas

Esta rodada é a **tentativa 1**, com 8 variantes. A medida roda uma vez. Se aparecer um erro de código
depois, a correção vira a tentativa 2, com o motivo escrito; o resultado da tentativa 1 continua no
relatório. Regra nova (outro horizonte, filtro de horário, stop, alvo) é pesquisa nova, com versão nova
deste arquivo escrita antes de medir.

## 6. Limites desta fase

- Sem livro de ofertas e sem lado agressor: não se simula a fila de ordem limitada; o robô medido opera
  a mercado.
- 23 pregões, setembro e outubro de 2026, um só regime de mercado. Pouco para aprovar com força; o bastante
  para reprovar uma ideia que não chega perto do custo.
- A janela das 09h15 às 17h45 fica dentro do pregão regular do WIN nos dois horários do ano.
- O imposto de 20% do day trade fica fora: ele só incide sobre o lucro e não muda a resposta do critério.
