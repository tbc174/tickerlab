# Carteira multiativo brasileira (ficha P0-3), tentativa 3: resultado

**Veredito: REPROVADO** (falhou em A1, A5, A6 e A8). Rodada única em 03/11/2026, pelo critério do
`docs/pre-registro-quant-p0-v0.1.md` (hash `ea45eddf09e8…`, conferido pelo código antes de qualquer número).
Código: `python -m trader.estrategias.rodar_p0_3` com o filtro de barras corrigido (o conteúdo deste PR, sobre o
`#745`; o registro gravou o commit `d35a2028` porque a correção ainda não estava commitada quando rodou).
Registro: tentativas 5 a 8 da família P0-3 em `pesquisa_quant/registro.db` (fora do Git), segunda execução de
cada uma (mesmo hash de configuração); 111 tentativas contadas no DSR (ver "Achado desta tentativa").
Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.

Em uma frase: com os 18 pregões de março e abril de 2021 de volta ao calendário (3.238 pregões), o resultado
é o mesmo da tentativa 2 até a segunda casa (Sharpe do excesso sobre o CDI 0,41), e a ficha P0-3 fica
reprovada em três tentativas pelo mesmo motivo: não se distingue do acaso com 13 anos de dados.

## O que mudou desde a tentativa 2

- Barra sem negócio passou a ser a que tem volume zero **e** o preço igual ao da anterior (73 feriados fora);
  os 18 pregões que só vieram sem o volume (12/03 a 07/04/2021) ficaram. Calendário com 3.238 pregões e o maior
  buraco de 6 dias corridos (carnaval).

## Os itens do critério (seção 5 do pré-registro)

| Item | O quê | Valor | Limite | Passou |
|---|---|---|---|---|
| A1 | Sharpe do excesso sobre o CDI (0,41) > 0 e DSR com 111 tentativas | 0,770 | ≥ 0,95 | não |
| A2 | PBO (a ficha não tem alternativas) | — | não se aplica | sim |
| A3 | platô: menor Sharpe dos vizinhos ÷ Sharpe do candidato | 0,919 | ≥ 0,7 | sim |
| A4 | custo, imposto e impacto como fração do Sharpe bruto (0,49) | 0,177 | ≤ 0,333 | sim |
| A5 | t-estatística do excesso com a correção de Lo | 1,756 | ≥ 3,0 | não |
| A6 | contra o acaso: p-valor dos sinais deslocados | 0,320 | ≤ 0,05 | não |
| A7 | contra as réguas: limite inferior de 90% da diferença (60/40 +0,05; CDI +0,03) | 0,034 | > 0 em todas | sim |
| A8 | estresse (custos × 2, Y = 2): Sharpe do excesso (0,40) > 0 e DSR | 0,767 | ≥ 0,9 | não |
| F1 | maior queda do pico (líquida, diária) | −11,3% | ≥ −35% | sim |
| V | futuro infla (0,47 > 0,41), reexecução idêntica, dados conforme, cortar o futuro não muda o passado | — | todas | sim |

## Os três esquemas (custos base, modo vender)

| Esquema | Sharpe do excesso | Sharpe | Retorno anual | Volatilidade | Maior queda | Giro |
|---|---|---|---|---|---|---|
| risk parity (candidato) | 0,41 | 1,58 | 11,9% | 7,6% | −11,3% | 0,27 |
| inverso da volatilidade | 0,41 | 1,46 | 12,3% | 8,4% | −12,6% | 0,25 |
| mínima variância | 0,27 | 1,12 | 11,7% | 10,4% | −13,3% | 0,51 |

Estresse (custos × 2, impacto Y = 2): os mesmos números até a segunda casa (risk parity 0,40). Modo só-aporte:
0,45 de Sharpe do excesso, giro 0,13, mesma queda (−11,3%).

## Réguas e platô

| Régua | Sharpe | Retorno anual | Maior queda |
|---|---|---|---|
| 60/40 (BOVA11 60%, caixa no CDI 40%, rebalanceio mensal) | 0,58 | 8,3% | −29,2% |
| CDI | — | 8,9% | 0,0% |

| Vizinho | Sharpe do excesso |
|---|---|
| janela 202 | 0,37 |
| janela 302 | 0,39 |
| banda 16% | 0,41 |
| banda 24% | 0,41 |
| bruto (sem custo, imposto nem impacto) | 0,49 |

## Achado desta tentativa (contagem; corrigido neste PR, sem nova execução)

5. **O DSR contou configurações, não execuções.** O registro guarda cada configuração uma vez (pelo hash) e
   soma as reexecuções na coluna `execucoes`; `Registro.total_para_o_dsr` contava as linhas, então as 4
   reexecuções desta tentativa não entraram: 111 em vez de 115. O pré-registro (seção 9) diz que "reexecução e
   correção de defeito contam". Correção: o total do DSR soma as execuções. Mais tentativas só baixam o DSR, que
   já está em 0,77 contra 0,95: o veredito não muda, e por isso esta correção não gastou uma execução nova.

## O que a ficha P0-3 diz depois de três tentativas

- A carteira de NTN-B, BOVA11, ouro e S&P 500 em reais por paridade de risco rende acima do CDI e ganha da
  60/40 com folga em queda e em Sharpe, mas com 13 anos de dados não dá para distinguir o excesso do acaso
  (t 1,76 contra 3,0; p 0,32 contra 0,05).
- O que come o resultado é o imposto (IR nas vendas do rebalanceio), não a corretagem nem o impacto; o modo
  só-aporte, que nunca vende, fica um pouco melhor e gira a metade.
- Restam 5 das 8 tentativas do orçamento da ficha. Nada aqui autoriza dinheiro real: pela ADR 0118, a camada A1
  só recebe capital com ficha aprovada.

## Limites e cuidados

- Desenvolvimento só: nada aqui diz o que o holdout vai mostrar; abri-lo é decisão escrita do Tiago.
- A NTN-B é um índice sintético de prazo constante (curva de 5 anos + IPCA pro rata), não o B5P211; de
  12/04 a 07/08/2019 o ponto de 5 anos é o de 10 anos deslocado, não um dado do Tesouro.
- Os 18 pregões de 2021 sem volume no export entram no calendário com o preço, mas o volume médio para o
  impacto (fixado antes dos números) não depende deles.
- Ouro e S&P 500 em reais sem hedge; feriado lá fora usa o último preço em dólar.
- Quantidades fracionárias: os índices não têm cota, o lote de 100 não foi aplicado.
- Volumes para o impacto são estimativas conservadoras fixadas antes dos números.
- O DARF é pago no último pregão do mês seguinte, vendendo se o caixa não cobre.
- 13 anos de dados: um Sharpe do excesso de 0,41 precisaria de ~54 anos para dar t = 3 pela régua
  anos ≈ (t/SR)². O critério foi feito para reprovar o que não se distingue do acaso.
- Nada aqui é recomendação de investimento; retorno passado não garante retorno futuro.
