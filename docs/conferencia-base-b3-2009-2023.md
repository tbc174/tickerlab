# Base das fichas F-B3 e P0-4 (linha 577): conferência do COTAHIST anual de 2009 a 2023

Gerado em 03/11/2026 (21h35, Brasília) pela conversa "Satélites · carteira própria e trade 24/7", plano v2
da carteira própria (ADR 0118, Emenda 1). É conferência de dados: **nenhuma estratégia rodou e nenhuma
tentativa foi gasta**.

Nada aqui é recomendação de investimento.

## O que entrou

- **Os 15 COTAHIST anuais** (`COTAHIST_A2009.ZIP` a `COTAHIST_A2023.ZIP`, 378 MB, da área de séries
  históricas da B3, baixados em 03/11 com o ok do Tiago), em `pesquisa_quant/f_b3/` (fora do Git), com o
  SHA-256 de cada um em `SHA256SUMS.txt` na mesma pasta. Os tamanhos batem com os cabeçalhos da B3.
  Mercado à vista: de 722 papéis e 246 pregões (2009) a 2.136 papéis e 248 pregões (2023).
- **Correção do leitor (`dados_f_b3.ler_cotahist_anual`):** o arquivo traz papéis cotados por lote de mil
  (fator de cotação 1000): 3.969 linhas em 2009, 1.287 em 2014 e cerca de 500 por ano de 2015 em diante.
  O leitor não dividia pelo fator, e cada troca de cotação viraria um salto falso de mil vezes. Agora o
  preço é por ação; o volume já vinha em reais. A F-B3 e o carregador dos agentes usam o mesmo leitor
  (os agentes só leem o volume, que não muda).
- **Preços ajustados (`trader/estrategias/ajuste_b3.py`):** o fechamento corrigido pelos desdobramentos,
  grupamentos e bonificações da tabela `eventos_de_capital` do acervo (formulário de referência da CVM),
  com a data ex achada pelo salto do preço perto da data do evento. As regras estão no topo do módulo,
  escritas antes de qualquer número das fichas. `python -m trader.estrategias.ajuste_b3` grava
  `precos_ajustados.parquet` e a conferência.

## O que a conferência achou

| Medida | Valor |
|---|---|
| Papéis no mercado à vista (2009–2023) | 3.428 |
| Eventos aplicados (data ex achada) | 480 |
| Eventos sem data ex (nenhum pregão bateu) | 328 (209 em ações) |
| Saltos de 2× para cima ou para baixo sem evento | 2.898 em 900 papéis; **42 no universo líquido** |

### Lacuna 1: CNPJ dos papéis que saíram antes de 2018

O CNPJ de cada papel vem do código do emissor no ISIN, ligado pelo cadastro de emissores do FCA, que só
tem tickers desde 2018 (o FCA de 2010 a 2017 do acervo não traz o código de negociação). Dos **394
papéis** (ON, PN e units) que em algum dia têm média de R$ 5 milhões por pregão nos 60 anteriores, **78
ficam sem CNPJ**: Ambev antiga (AMBV3/4), Drogasil (DROG3), Raia (RAIA3), Souza Cruz (CRUZ3), Kroton
(KROT3), ALL (ALLL3), Vivo, Telemar, Brasil Telecom, Redecard, Amil, VCP, Tam e outros.

Sem CNPJ o papel fica sem balanço e sem eventos, e o universo da seção 8 (que exige balanço nos 12 meses)
o deixa de fora. A parte do universo que se perde, por ano:

| 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 em diante |
|---|---|---|---|---|---|---|---|---|---|
| 35% | 27% | 24% | 19% | 17% | 13% | 11% | 7% | 4% | ≤ 2% |

São justamente as empresas que deixaram de existir, ou seja, **viés de sobrevivência**. Pela seção 2 do
pré-registro, resultado assim não pode autorizar dinheiro. Por isso a tentativa 1 da P0-4 não rodou.

### Lacuna 2: desdobramentos que faltam no formulário de referência

Dos 42 saltos sem evento no universo líquido, parte são desdobramentos ou grupamentos que o formulário de
referência do acervo não tem (B3 em 05/2021, Inter em 05/2021, BTG em 07/2021, PDG em 01/2019, Casas
Bahia em 12/2023) ou que ficaram sem evento por falta do CNPJ (Ambev e Drogasil em 12/2010, Souza Cruz
em 03/2011, Kroton em 2013 e 2014, Rumo em 2015). Outra parte é movimento de verdade e não deve ser
ajustada: Americanas em 01/2023, cisões (Assaí em 03/2021, Éxito em 08/2023), dividendos grandes
(Bradespar em 12/2021) e reorganizações.

### Lacuna 3: proventos

O acervo tem dividendos e JCP por exercício, sem valor por ação nem data ex. Os preços ajustados ficam sem
os proventos (limitação declarada no topo de `ajuste_b3.py`): nos pares, a perna comprada deixa de
receber e a vendida deixa de pagar, então o erro tende a se compensar, mas não some.

## Limites e cuidados

- Nenhum número de estratégia foi produzido; esta é só a conferência da base.
- O ajuste para trás multiplica todo o passado de cada evento pela mesma constante: retornos e o z de uma
  janela sem evento não mudam com eventos posteriores (há teste).
- Lote de 100 sobre preço ajustado: antes de um desdobramento, o valor do lote na simulação não é o da
  época (declarado nas fichas).
- Desenvolvimento só até 08/09/2023; o holdout continua lacrado. Os saltos de 2023 depois dessa data
  (Casas Bahia, SLC) não entram em nenhuma ficha.

## Próximo passo (decisão do Tiago)

Completar a base antes da tentativa 1: (1) ligar os 78 papéis antigos ao CNPJ; (2) cobrir os
desdobramentos que faltam; (3) decidir se os proventos ficam como limitação. As opções estão na conversa
e na fila (linha 577).
