# Filtro de regime (ficha P0-8): sem objeto nesta versão, nenhuma tentativa gasta

Escrito em 04/11/2026 pelo `docs/pre-registro-quant-p0-v0.1.md` (seção 9, ficha P0-8). Código:
`trader/estrategias/regime.py` (o filtro) e `trader/estrategias/rodar_regime.py` (a rodada que trava).

Nada aqui é recomendação de investimento.

Em uma frase: **a ficha P0-8 não tem o que testar**. Ela compara "cada estratégia aprovada com e sem o
filtro", e nenhuma estratégia foi aprovada no critério da seção 5. O filtro ficou escrito e testado para a
primeira que passar, e **nenhuma das 4 tentativas da ficha foi gasta**.

## Por que não aplicar o filtro às reprovadas

Pôr o filtro numa estratégia que já reprovou, depois de ver o resultado dela, seria procurar um jeito de
salvá-la. A seção 10 proíbe isso: um defeito corrigido depois de ver o resultado conta como tentativa nova,
e uma comparação que vence o candidato não vira candidato nesta versão. A pergunta da ficha é outra: o
filtro melhora o que **já funciona**?

## O que o registro diz (lido em 04/11/2026)

| Ficha | Tentativas | Veredito |
|---|---|---|
| P0-3 carteira multiativo | 10 linhas (4 de 8 tentativas) | reprovada |
| P0-1 cripto | 1 | reprovada |
| P0-2 BOVA11 | 1 | reprovada |
| P0-4 pares | 1 | reprovada |
| P0-5 PEAD | 1 | reprovada |
| P0-6 monitor, P0-7 estudo | 1 e 1 | sem critério (não são candidatas) |
| F-B3 fatores | 0 | ainda não rodou |

A rodada `python -m trader.estrategias.rodar_regime` conferiu o hash do pré-registro, leu o registro e
respondeu **SEM OBJETO** (saída 3). O registro continuou com 16 linhas e 22 execuções antes e depois.

## O filtro que ficou pronto (convenções fixadas antes de qualquer número)

Os cortes são os da ficha. As convenções que a ficha não diz foram escritas no código antes de existir um
número:

| Condição | Liga quando | Convenção |
|---|---|---|
| Média de 200 dias | preço acima da média simples de 200 pregões | o regime "Alta" de `src/regimes.py` |
| Volatilidade de 21 dias | não passa do percentil 90% | percentil da própria história até o dia (o regime "Calmo" de `src/regimes.py`, com 60 dias de história) |
| Queda do ativo | acima de −20% do maior preço visto | desde o primeiro preço |
| Selic pelo Focus | sem ciclo de alta (mudança esperada nas próximas reuniões ≤ 0) | **leitura minha**: a ficha diz só "ciclo da Selic"; o sentido "alta desliga" pode ser revisto antes da 1ª rodada, sem custo, porque ainda não há número |
| Funding (cripto) | entre os percentis 10% e 90% da própria história | o mesmo corte do monitor da P0-6 |
| Open interest (cripto) | variação de 7 dias entre os percentis 10% e 90% | o nível sobe com o mercado, então a variação |

- **Atraso:** o estado do dia D usa só dados até o fechamento de D e vale no fechamento de D+1 (seção 4).
  O retorno de D+2 é o primeiro que ele decide (há teste).
- **Aquecimento neutro:** sem história suficiente, a condição não desliga, então a estratégia roda como
  roda sem o filtro.
- **Desligada, vai para o CDI**, e cada troca paga o custo de uma ida ao mercado.
- **A regra para o filtro entrar** (`filtro_entra`): o DSR melhora, e nem o PBO nem a queda máxima pioram.
- **Testes** (`tests/test_trader_regime.py`, `tests/test_trader_rodar_regime.py`): cada corte em dados
  sintéticos, cortar o futuro não muda o passado (5 sementes), o atraso da execução, o custo da troca, o
  filtro sempre ligado igual à estratégia sem ele, e a rodada que não registra nada.

## Limites e cuidados

- **Faltam dois dados:** as expectativas da Selic do Focus e o open interest de cripto não estão na base. O
  filtro aceita os dois como entradas opcionais. Baixá-los pede o "pode" do Tiago.
- **A comparação com e sem o filtro ainda não está escrita**, porque ela depende do retorno diário da
  estratégia aprovada. Quando houver uma, a comparação entra num PR antes de rodar, com os cortes daqui.
- **O sentido da Selic é uma leitura**, não o texto da ficha (ver a tabela).
- **Nada aqui foi medido em dado de mercado**: não há Sharpe, nem DSR, nem queda. Isso é de propósito.
- **O holdout continua lacrado.**
- Nada aqui é recomendação de investimento.
