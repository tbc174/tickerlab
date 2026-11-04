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

- Ligação pelo nome: dois modelos podem errar juntos; o CNPJ errado traria o balanço de outra empresa. A tabela fica no Git para qualquer pessoa conferir linha por linha.

- Nenhum número de estratégia foi produzido; esta é só a conferência da base.
- O ajuste para trás multiplica todo o passado de cada evento pela mesma constante: retornos e o z de uma
  janela sem evento não mudam com eventos posteriores (há teste).
- Lote de 100 sobre preço ajustado: antes de um desdobramento, o valor do lote na simulação não é o da
  época (declarado nas fichas).
- Desenvolvimento só até 08/09/2023; o holdout continua lacrado. Os saltos de 2023 depois dessa data
  (Casas Bahia, SLC) não entram em nenhuma ficha.

## Segunda passada: a base completada (03/11, depois das 22h)

O Tiago escolheu completar sem baixar nada ("Pelo nome, sem baixar"): ligar os papéis antigos ao CNPJ
pelo nome, com os dados da CVM que o acervo já tem, cobrir os desdobramentos pelo preço e deixar os
proventos como limitação. Continua sendo conferência de dados: nenhuma tentativa foi gasta aqui.

### Lacuna 1 fechada em boa parte: `trader/estrategias/emissores_antigos.csv`

- **Como:** para os 96 emissores sem CNPJ com média de pelo menos R$ 1 milhão por pregão, os 8 nomes
  mais parecidos entre os 2.347 pares (CNPJ, nome) do FCA geral de 2010 a 2023, das demonstrações de
  2010 a 2017 e do FCA de emissores. Dois modelos escolheram às cegas, cada um sem ver a lista do outro
  (Claude Opus e Claude Sonnet). Empresa incorporada fica com o próprio CNPJ ou com nenhum, nunca com o
  da que a incorporou.
- **Resultado:** 77 ligações em que os dois concordam; 6 em que discordaram (RUMO, BBTG, DURA, LVTC,
  IENG e SFSA) e 13 que nenhum achou (Aracruz, Unibanco, Sadia, GVT, Nossa Caixa, Brasil Telecom
  Participações e outros, cujo CNPJ não está nos arquivos da CVM do acervo) ficam **sem CNPJ**, pela
  regra da conferência automática: quem discordou fica vazio. A tabela guarda as 96 linhas, com o nome
  de pregão, o nome na CVM e a conferência de cada uma.
- **No cadastro:** `dados_f_b3.ler_emissores` junta o FCA e a tabela; no mesmo emissor vale o FCA.

| Medida | Antes | Depois |
|---|---|---|
| Papéis líquidos (média de R$ 5 mi em algum dia) sem CNPJ | 78 de 394 | **14 de 394** |
| Parte do universo sem CNPJ em 2009 | 35% | 8% |
| Em 2010 / 2011 a 2017 / 2018 em diante | 27% / 4 a 24% | 1% / até 2% / até 0,2% |

Os 14 que sobram: ABNB3, ABYA3, AGIN3, ARCZ6, BBTG11, BNCA3, BRTP3, BRTP4, DURA4, GVTT3, LVTC3,
RUMO3, SDIA4 e UBBR11. Em 2009 não há decisão (é o ano de formação; a primeira decisão é em 2010).

### Lacuna 2 fechada em boa parte: desdobramento pelo preço

O COTAHIST traz o número de distribuição (DISMES, posições 243 a 245), que a B3 muda no dia ex de todo
evento. A regra, escrita no topo de `ajuste_b3.py` antes de qualquer número da P0-4: depois dos eventos
do formulário, um salto de 2× ou mais no dia em que o DISMES mudou é desdobramento ou grupamento se a
razão de preços ficar a até 5% de um fator usual (2 a 10, 12, 15, 16, 20, 25, 30, 40, 50, 60, 80, 100,
200, 250, 500, 1000 e os inversos). A quebra da Americanas (01/2023) não muda o DISMES e não ajusta;
o dividendo da Bradespar (razão 2,41) e a cisão do Assaí (3,56) mudam, mas ficam longe de um fator usual
e também não ajustam. A tolerância de 5% foi escolhida olhando esses casos conhecidos, na conferência.

| Medida | Primeira passada | Segunda |
|---|---|---|
| Eventos do formulário aplicados | 480 | 515 (mais CNPJs ligados) |
| Desdobramentos pelo preço | — | 461 (14 no universo líquido) |
| Saltos de 2× sem evento | 2.898 | 2.403 (depois de o preço zero do arquivo virar dia sem preço); **15 no universo líquido** |

No universo líquido, os 14 pelo preço são B3 (05/2021), Inter (05/2021, três classes), BTG (07/2021),
Méliuz (06/2023), Cielo (05/2011), JSL (11/2020), OGX (12/2009), GPA (08/2023), PDG (01/2019), Rumo
(08/2015), Refinaria de Manguinhos (07/2010) e SLC (12/2023, no holdout). Os de GPA e JSL caem em reorganizações
(a cisão do Éxito e a da Simpar) com razão perto de 3. Se forem cisões, o ajuste pela razão do dia
aproxima o retorno do acionista que recebeu as ações da empresa nova, que é o certo para os pares. Os
15 saltos que sobram são movimentos de verdade: Americanas, Casas Bahia (holdout), Bradespar (dividendo),
Lojas Americanas (reorganização com a B2W), GPA (cisão do Assaí), BR Properties, MMX, Mundial, Syn e
Viver.

### Lacuna 3: proventos continuam como limitação declarada

Sem valor por ação nem data ex no acervo, os preços ajustados não incluem dividendos e JCP. Nos pares,
o erro tende a se compensar entre as pernas, mas não some.

## Próximo passo

Com a base completada, a tentativa 1 da P0-4 rodou em 03/11 (`python -m trader.estrategias.rodar_pares`)
e foi **reprovada**: a regra quase não achou par cointegrado (2 operações em 14 anos). O resultado está em
`docs/resultado-pares-p0-4-tentativa-1.md`. A regra da ficha não mudou.
