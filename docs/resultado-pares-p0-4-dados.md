# Ficha P0-4 (pares por cointegração na B3): conferência da base antes da primeira tentativa

> **Superado:** a base que faltava (COTAHIST anual de 2009 a 2023) foi completada no mesmo dia
> (`docs/conferencia-base-b3-2009-2023.md`) e a ficha rodou em 03/11/2026
> (`docs/resultado-pares-p0-4-tentativa-1.md`). Este arquivo fica só como registro da conferência.

Gerado em 03/11/2026 (21h, Brasília) pela conversa "Satélites · carteira própria e trade 24/7", plano v2
da carteira própria (ADR 0118, Emenda 1). Pré-registro quant v0.1 (hash
`ea45eddf09e89f1cee5af3e7612fac2739cebf05ab1583e5270c6b3c2f403269`), ficha P0-4.

**Veredito: INCONCLUSIVA, sem universo histórico.** A ficha não rodou e **nenhuma das 8 tentativas foi
gasta**. Ela usa o mesmo universo da seção 8 que a F-B3, e a base local não tem o COTAHIST anual de 2009 a
2023 (com as ações deslistadas) nem os preços ajustados. Rodar só com as 25 sobreviventes do MT5 daria
viés de sobrevivência, e a seção 2 diz que esse resultado não autoriza dinheiro. A base que falta é a
mesma da F-B3 (fila, linha 577), menos a quantidade de ações: a regra dos pares não usa valor de mercado.

Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

## O que a base tem e o que falta

| Tabela da ficha | O que há na cópia local do acervo | Falta |
|---|---|---|
| Preços e volume diários de toda a B3 (2009–2023) | COTAHIST diário só desde 09/2026; lote anual de 1986 a 2009; MT5 com 25 sobreviventes | COTAHIST anual de 2009 a 2023 (deslistadas incluídas) |
| Preços ajustados (o spread é em log de preço ajustado) | `eventos_de_capital` e `proventos` de 2010 a 2023 | a base de preços ajustados feita com eles |
| Setor de cada empresa (teste do Brasil, pares do mesmo setor) | `fca_geral/<ano>` de 2010 a 2023: 9.338 entregas, 66 setores, com `conhecido_em` | nada |
| Classe ON/PN e CNPJ (pares ON/PN) | o ISIN do COTAHIST dá o emissor e a especificação dá a classe | nada além do COTAHIST |
| Balanços (o universo exige balanço nos 12 meses) | `demonstracoes/<ano>` de 2010 em diante | nada |
| CDI (a régua) | SGS 12 em cache | nada |

## O que foi entregue mesmo sem a base

- **Motor** `trader/estrategias/pares.py`, com as convenções escritas no topo antes de qualquer número:
  janelas de 12 meses de formação e 6 de operação, rolando a cada 6 meses; Engle-Granger (MQO de log y em
  log x e ADF com 1 defasagem nos resíduos, p-valor de MacKinnon para 2 variáveis) em todos os pares do
  conjunto, com a correção de Benjamini-Hochberg pelo número de pares testados; meia-vida de 5 a 30
  pregões; entrada com |z| > 2, saída com |z| < 0,5, stop com |z| > 4 ou com 3× a meia-vida em aberto
  (o par parado sai da janela); até 10 pares, cada um com 1/10 do patrimônio; sinal no fechamento de D e
  ordem no fechamento de D+1 (tarifa do leilão e impacto de raiz quadrada); a perna vendida paga aluguel
  pelos dias corridos com mínimo de R$ 10; IR mensal de swing com DARF no fim do mês seguinte; perna
  deslistada fecha o par no pregão seguinte e o tira da janela; no último dia da janela tudo fecha.
- **Carregador** `trader/estrategias/dados_pares.py`: usa o COTAHIST da F-B3 sem pedir a quantidade de
  ações e lê o setor do FCA ponto no tempo (cada entrega vale a partir de `conhecido_em`, cortada no fim do
  desenvolvimento). `dados_f_b3` ganhou a opção `com_acoes=False`, sem mudar a F-B3.
- **Rodada** `python -m trader.estrategias.rodar_pares`: sem a base, imprime este veredito e sai com código
  2 sem abrir o registro; com a base, registra uma tentativa por execução e escreve o relatório com as
  janelas (pares testados, cointegrados, escolhidos), o candidato, o estresse, o bruto, a régua, os 12
  vizinhos do platô (±20% em z de entrada, saída e stop, no múltiplo da meia-vida, no número de pares e
  nos meses de formação) e os quatro testes do Brasil: (a) aluguel a 2, 5 e 10% a.a.; (b) lote de 100
  contra ações inteiras, com a contagem de dias de day trade e de pares fechados no dia da entrada;
  (c) todos os pares, só do mesmo setor e só ON/PN da mesma empresa; (d) com e sem as deslistadas, com os
  pares quebrados por deslistagem.
- **Regra que nunca opera:** se nenhum par passar em nenhuma janela, a carteira fica no CDI, o excesso é
  zero e não há Sharpe para deflacionar. A rodada reprova no A1 ("a regra não escolheu nenhum par"), em
  vez de quebrar ou virar inconclusiva: a regra rodou com a base inteira e não produziu nada.
- 56 testes com dados sintéticos (9 ações, três pares cointegrados, um ON/PN, três passeios aleatórios e
  uma deslistada em 14/09/2018): janelas, BH, formação sem olhar o futuro, sinais, D+1, pernas opostas
  pelo β, lote, aluguel, stop, deslistagem, IR, estresse, cortar o futuro, reexecução e a rodada inteira.

## Um aviso escrito antes dos números: a regra tem pouco poder

Com 12 meses de formação (cerca de 250 pregões), o teste de Engle-Granger dá, para um resíduo AR(1) de
coeficiente φ, uma estatística t perto de −√(n(1−φ)/(1+φ)). A meia-vida da ficha fixa o φ:

| Meia-vida (pregões) | φ | t típico | p-valor de MacKinnon |
|---|---|---|---|
| 5 | 0,871 | −4,2 | 0,004 |
| 10 | 0,933 | −2,9 | 0,12 |
| 20 | 0,966 | −2,1 | 0,49 |
| 30 | 0,977 | −1,7 | 0,68 |

A correção de Benjamini-Hochberg pede que o par mais forte tenha p ≤ 0,05 ÷ (número de pares). Com 50
ações no conjunto (1.225 pares) isso é t ≈ −5,3; com 100 (4.950 pares), t ≈ −5,6; com 200 (19.900
pares), t ≈ −5,9. Mesmo um par com meia-vida de 5 pregões fica em torno de −4,2. A previsão, então, é que
em "todos os pares" quase nenhuma janela escolha par, e que os poucos escolhidos sejam os que tiveram
sorte na amostra de formação. Os pares do mesmo setor e, mais ainda, os ON/PN (poucas dezenas de pares
por janela) pedem bem menos e são onde a regra tem chance.

Os dados sintéticos confirmam: com 12 meses de formação, nem os três pares que sabidamente andam juntos
(meia-vida de 6,6 pregões) passam; em 7 janelas, 3 tiveram um par cointegrado depois da correção e nenhum
ficou com meia-vida entre 5 e 30. Por isso os testes do motor usam 24 meses de formação, onde os pares
verdadeiros passam e os passeios aleatórios não.

Isso é uma propriedade da regra aprovada, não um defeito do código, e **a regra não muda**: mudar a
formação ou a correção agora seria escolher a regra olhando o resultado. Uma versão com outra formação só
pode entrar numa nova versão do pré-registro, escrita e aprovada antes de rodar.

## Limites e cuidados

- Nenhum número de retorno foi produzido com dados reais; os testes usam preços sorteados.
- O carregador ainda não foi exercitado com o COTAHIST anual real: a primeira carga será uma conferência de
  dados (não gasta tentativa) antes da tentativa 1.
- O aluguel é uma taxa fixa por leitura (2, 5 ou 10% a.a.) até haver histórico de taxas por papel; algumas
  ações nem têm doador, e a simulação não sabe disso.
- OPA e deslistagem entram pelo fim da negociação no cadastro: o par fecha no pregão seguinte ao último
  preço; o preço da OPA em si não é modelado.
- O IR é o do swing também quando dois pares diferentes compram e vendem o mesmo ticker no mesmo dia (day
  trade entre pares): a rodada conta esses dias para mostrar se importam.
- A régua é só o CDI: a carteira é comprada e vendida ao mesmo tempo, então o Ibovespa não é a comparação.
- Desenvolvimento só (até 08/09/2023); o holdout continua lacrado e só abre com decisão escrita do Tiago.
- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

## Próximo passo

A mesma base da F-B3 (fila, linha 577): COTAHIST anual de 2009 a 2023 e os preços ajustados, em
`pesquisa_quant/f_b3/`. Com os dois, `dados_pares.conferir_base` devolve vazio e a tentativa 1 da P0-4 pode
rodar (a quantidade de ações só é necessária para a F-B3).
