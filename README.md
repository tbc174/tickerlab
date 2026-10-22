<p align="center">
  <img src="docs/imagens/banner.png" alt="TickerLab: analise ativos e teste estratégias com dados do passado" width="100%">
</p>

<p align="center">
  <a href="https://github.com/tbc174/tickerlab/actions/workflows/testes.yml"><img src="https://github.com/tbc174/tickerlab/actions/workflows/testes.yml/badge.svg?branch=main" alt="Testes"></a>
  <img src="https://img.shields.io/badge/Python-3.12-2962FF?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Streamlit-app-2962FF?logo=streamlit&logoColor=white" alt="Streamlit">
  <img src="https://img.shields.io/badge/React-TypeScript-2962FF?logo=react&logoColor=white" alt="React e TypeScript">
  <img src="https://img.shields.io/badge/PostgreSQL-16-2962FF?logo=postgresql&logoColor=white" alt="PostgreSQL 16">
  <img src="https://img.shields.io/badge/testes-3.500%2B-2EBD85" alt="Mais de 3.500 testes">
  <img src="https://img.shields.io/badge/cobertura-m%C3%ADnimo%2085%25-2EBD85" alt="Cobertura mínima de 85%">
  <img src="https://img.shields.io/badge/Stripe-modo%20de%20teste-F5B83D?logo=stripe&logoColor=white" alt="Stripe em modo de teste">
  <img src="https://img.shields.io/badge/direitos-reservados-93A0B8" alt="Todos os direitos reservados">
</p>

<p align="center">
  <a href="https://tickerlab.com.br"><b>Site</b></a> ·
  <a href="https://app.tickerlab.com.br"><b>Abrir o app</b></a> ·
  <a href="https://tickerlab.com.br/ferramentas.html"><b>Ferramentas grátis</b></a> ·
  <a href="https://tickerlab.com.br/metodologia.html"><b>Metodologia</b></a> ·
  <a href="https://tickerlab.com.br/precos.html"><b>Planos</b></a> ·
  <a href="#tickerlab-trade-a-pesquisa-de-trading-quantitativo"><b>TickerLab Trade</b></a>
</p>

O **TickerLab** é uma **plataforma brasileira de inteligência financeira**, em fase de testes,
para quem investe na bolsa brasileira (B3) e na americana. Ele junta quatro coisas que costumam
estar separadas:

1. **Análise e teste de estratégias com dados do passado**, num motor de backtest escrito à mão
   (sem biblioteca pronta de backtest), que desconta custos, imposto e a sorte de escolher a
   melhor entre muitas ideias.
2. **Research das empresas**: fatos relevantes da CVM e da SEC lidos e classificados, fundamentos
   tirados dos balanços oficiais, relatório completo da empresa, alertas e a carteira real da
   pessoa, lida das planilhas da B3.
3. **Uma base de dados própria e auditável**, montada a partir dos arquivos oficiais (CVM, BCB,
   Tesouro, B3 e outros órgãos), com cada original guardado, cada valor datado do dia em que ficou
   público e cada versão ancorada no Bitcoin.
4. **Ferramentas grátis no site** (14 calculadoras e simuladores) que trazem gente para o produto.

Cada número vem explicado em português, e o produto mostra também o que **não** funciona.

> [!IMPORTANT]
> Nada aqui é recomendação de investimento. Os preços vêm do Yahoo Finance e os demais dados de
> fontes oficiais; todos podem ter atraso ou erros. Rentabilidade passada não garante resultado
> futuro.

## Para quem vai avaliar o projeto

Esta seção é um mapa para quem chega de fora (investidor, banca, auditor ou um assistente de IA)
e quer entender o projeto inteiro sem ler as 134 mil linhas de Python.

**Em uma frase:** um produto de assinatura em teste, no ar em produção, criado e mantido por Tiago
Borsari Coelho com uso intenso de assistentes de IA, com disciplina de engenharia (PR com CI verde, testes,
cobertura mínima, deploy automático com volta sozinha) e uma regra que atravessa tudo: **mostrar os
números como eles são**.

**O que está no ar hoje (15/10/2026):**

| Parte | Estado |
|---|---|
| Site público e 14 ferramentas grátis | no ar, em `tickerlab.com.br` |
| App (37 páginas, login com o Google, 3 planos) | no ar, em `app.tickerlab.com.br`, em fase de testes: as telas novas em React na raiz, as demais na versão clássica, em `app.tickerlab.com.br/classico/` |
| Cobrança | Stripe **só em modo de teste**: nenhum pagamento real é feito. O Plus existe, mas ainda não está à venda |
| App novo em React (substituto do Streamlit) | é o principal desde 18/10/2026, na raiz de `app.tickerlab.com.br`: 9 telas; um link antigo de página que ainda não migrou abre na versão clássica |
| API de leitura v1 | pronta e documentada (`docs/api/`), **desligada em produção**; no ar só a rota pública da ferramenta "Quanto daria?" |
| Base de dados | em construção contínua: 92 tabelas com contrato versionado, coletas diárias, âncora no Bitcoin toda noite |
| Newsletter | pronta, enviada só para administradores até o parecer jurídico |
| TickerLab Trade (pesquisa de trading com ML) | fase M2 terminada **sem modelo aprovado**; pesquisa pausada |

**Ordem de leitura sugerida:**

1. Este README, inteiro.
2. `CLAUDE.md`: as regras de engenharia que valem para qualquer pessoa ou IA que programa aqui.
3. `docs/padroes-de-codigo.md`: o guia de estilo.
4. `src/paginas.py` (o mapa do produto) e `src/planos.py` (o modelo de negócio em código).
5. `docs/dicionario-da-base.md`, `docs/CHANGELOG-da-base.md` e `docs/ancoragem-da-base.md`: a base
   de dados.
6. `docs/api/README.md` e `docs/api/openapi-v1.json`: a API.
7. `notas/erros-e-solucoes.md`: 84 erros reais, com sintoma, causa e solução.
8. `docs/pre-registro-m2-v0.1.md` a `v0.4.md`: o método da pesquisa de trading.

**Como conferir o que este README diz:** os números da seção "Em números" saem do próprio
repositório (contagem de arquivos, de testes e de linhas); o CI de cada commit está público na aba
Actions; o histórico de PRs mostra como cada parte entrou. As decisões de arquitetura (as ADRs
citadas por número no código e nos commits) e o planejamento ficam numa pasta privada do autor.

## A história

O TickerLab começou como trabalho da matéria de **Python e Pandas** na faculdade: um script que
baixava o preço de uma ação e desenhava um gráfico. Cada pergunta nova virou uma página ("e se eu
tivesse seguido esta regra?", "isso foi sorte?", "e com vários ativos?"), e o projeto cresceu até
virar um serviço web completo, no ar em [tickerlab.com.br](https://tickerlab.com.br), com contas,
planos, relatórios em PDF, research das empresas, uma base de dados própria e uma pesquisa de
trading quantitativo com machine learning.

O código, os textos e as explicações estão em português, e o caminho do aprendizado ficou
registrado no próprio repositório (`notas/`, `guias/`, `estudos/`).

## Em números

Contados no repositório em 15/10/2026.

| 37 páginas no app | 14 ferramentas grátis | 92 tabelas catalogadas na base | 58 fontes arquivadas | mais de 3.500 testes |
|:---:|:---:|:---:|:---:|:---:|
| análise, estratégias, research, carteira, relatórios e conta | calculadoras e simuladores no site | com contrato de dados versionado | CVM, BCB, Tesouro, B3, órgãos públicos e cripto | com PostgreSQL de verdade e cobertura mínima de 85% |

| ~1.700 ativos na busca | 12 estratégias | 37 migrações do banco | ~134 mil linhas de Python | ~13 mil linhas de TypeScript |
|:---:|:---:|:---:|:---:|:---:|
| B3, S&P 500, índices, cripto e câmbio | tendência e reversão, com custos e stops | Alembic, de 0001 a 0037 | app, base, pesquisa, scripts e testes | site, ferramentas e o app novo |

Mais de 290 pull requests e 470 commits desde a criação do repositório no GitHub, em 10/10/2026.

## As partes do projeto

| Parte | O que é | Onde fica |
|---|---|---|
| **App** (`app.tickerlab.com.br`) | o serviço web: análises, estratégias, research, carteira da B3, relatórios em PDF, contas e planos. O Streamlit é a **versão clássica**, em `app.tickerlab.com.br/classico/` | `app.py`, `telas/`, `src/` |
| **App novo** (raiz de `app.tickerlab.com.br`) | a troca do Streamlit por React, uma tela por vez, consumindo a API; é o principal, e manda à versão clássica o que ainda não migrou | `web/src/app/`, gerado em `novo/` |
| **Site público** (`tickerlab.com.br`) | apresenta o produto, os planos e a metodologia, e oferece as ferramentas grátis | `site/`, gerado pelo React (`web/`) e por `scripts/gerar_site.py` |
| **API** (`api.tickerlab.com.br`) | saúde, webhook do Stripe, descadastro de e-mails, a rota pública do "Quanto daria?" e a API de leitura v1 (desligada) | `src/api.py`, `src/api_v1/` |
| **Base de dados** | arquivista dos originais oficiais, tabelas "como eram na data", contratos de dados e âncora no Bitcoin | `base/`, `scripts/` |
| **TickerLab Trade** | pesquisa de trading quantitativo com machine learning e MetaTrader 5, em conta de demonstração | `trader/` (roda no PC, fora do app) |
| **Caderno de estudos** | anotações do aprendizado: Python, Pandas, Git, Streamlit, finanças e os erros resolvidos | `notas/`, `guias/`, `estudos/` |

**Tecnologias:** Python 3.12, Pandas, yfinance, Streamlit, Plotly, SQLAlchemy 2, Alembic,
PostgreSQL 16, FastAPI, Parquet, Stripe (modo de teste), React com TypeScript e Vite, Docker
Compose e GitHub Actions. Na pesquisa: scikit-learn, LightGBM, statsmodels, PyTorch (CPU), numba,
joblib e o pacote MetaTrader5.

## O que o app faz

No menu do topo, **Início** e **Gerar relatório** ficam como links diretos, seguidos dos grupos
abaixo. Cada página tem uma frase dizendo para que serve, e cada número tem uma explicação em
português ao passar o mouse no **?**. O mapa fica num lugar só, `src/paginas.py`.

| Grupo | Páginas | Pergunta que respondem |
|---|---|---|
| (direto no menu) | Início, Gerar relatório | Por onde começo? Como levo a análise comigo em PDF? |
| Analisar | Visão geral, Risco, Retorno mensal, Comparar ativos, Correlação e beta | Como o ativo se comportou: retorno, volatilidade, quedas, calendário, comparação com Ibovespa e S&P 500, beta |
| Estratégias | Backtest, Ranking de estratégias, Carteira, Experimentos, Fases do mercado | E se eu tivesse seguido uma regra? Qual estratégia foi melhor, descontando a sorte? E com vários ativos? |
| Avançado (Pro) | Aprendizado de máquina, Pairs trading | Um modelo vence a previsão ingênua? Pares de ativos cointegrados |
| Research | Acontecimentos, Pulse, Diário de Teses, Carteira da B3, Juros e inflação, Linha do tempo, Fundamentos, Relatório da empresa, Pessoas de dentro, Donos e fundos, Newsletter, Minha carteira, Alertas, Parâmetros | O que as empresas comunicaram? O que mudou desde a minha última visita? Como estão os balanços? Quem compra e vende? Como vai a minha carteira de verdade? |
| Aprender | Guia e glossário (e, no rodapé, Termos de uso e Política de privacidade) | Como os números são calculados e o que cada termo quer dizer |
| Minha conta | Minhas simulações, Favoritos e momentum, Meus dados e privacidade, Planos e assinatura | O que é meu: simulações guardadas, favoritos, exportar e apagar os dados, plano |
| Mais | TickerLab Trade (Beta) | Em que fase está a pesquisa de trading quantitativo? |
| Administração | Administração | Usuários, planos, assinaturas e registro de ações (só administradores) |

![Evolução do capital: estratégia contra comprar e segurar](docs/imagens/backtest.png)

### Análise e estratégias

- **Backtest:** 12 estratégias (tendência e reversão), custos, stops, CDI, imposto e validação
  (treino e teste, walk-forward, mapa de parâmetros, Monte Carlo, teste contra o acaso, Sharpe
  deflacionado e PBO). O **Ranking** compara todas descontando a sorte de escolher a melhor
  entre muitas. A ficha **"Foi sorte?"** resume cinco checagens num veredito.
- **Carteira:** rotação, momentum dual, inverso da volatilidade, baixa volatilidade, canário e
  paridade hierárquica de risco (HRP).
- **Relatórios em PDF (Report Studio):** relatórios do ativo, de comparação, de backtest, de
  carteira e da empresa, com prévia real antes de baixar, modelos (Executivo, Completo ou
  Personalizado), escolha e ordem das seções e três estilos visuais. Os números saem das mesmas
  funções que a tela usa, e a seção "Limites e cuidados" é obrigatória.
- **Busca de ativos:** autocomplete por código ou nome, num catálogo de cerca de 1.700 ativos (B3,
  S&P 500, índices, criptomoedas e câmbio). Um código digitado nunca é trocado em silêncio.
- **Compartilhar:** link secreto de 256 bits, com prazo e revogável, guardado só como hash; CSV
  pronto para o Excel em todos os planos.

### Research

- **Acontecimentos e Linha do tempo:** fatos relevantes, comunicados e proventos (CVM no Brasil,
  SEC nos EUA), com o link do documento original e o motivo de cada um aparecer. Cada fato
  relevante ganha um **assunto**, lido do título e do texto pelo "leitor"; a ordem segue
  pertinência, materialidade e urgência, nunca uma nota de atratividade.
- **Pulse:** o que mudou desde a última visita.
- **Fundamentos e Relatório da empresa:** margens, ROE, dívida e múltiplos calculados dos balanços
  entregues à CVM, dizendo de onde veio cada número; notas contra o padrão do setor, notas
  clássicas (como a de Piotroski) e valuation (P/L e P/VP contra o próprio histórico e DCF),
  **sem preço-alvo**.
- **Pessoas de dentro e Donos e fundos:** negociações de administradores (CVM e SEC), carteiras dos
  fundos (CDA da CVM) e formulários 13F da SEC.
- **Carteira da B3:** envie as planilhas da Área do Investidor da B3 (posição,
  movimentação e negociação) para ver a carteira, os proventos recebidos e a receber, o custo
  médio (com a amortização de FII) e o resultado realizado mês a mês, com day trade à parte. Os
  arquivos são lidos só na memória: nada é gravado e nada vai para os logs.
- **Minha carteira (Pro):** com o consentimento da pessoa, guarda só os pesos (em %) da carteira,
  para o Research e a Newsletter darem mais destaque às maiores posições.
- **Alertas:** regras com várias condições ("e" ou "ou"), conferidas todo dia ou toda semana.
- **Diário de Teses:** anotações datadas por ativo, ligadas aos backtests salvos.
- **Juros e inflação:** Selic, CDI, IPCA, juro real e o que o mercado espera (Focus), com a data
  e a fonte de cada número.
- **Newsletter:** edição montada dos acontecimentos, com opt-in.

| Preço e médias móveis | Comparar ativos |
|---|---|
| ![Preço da PETR4 com médias móveis e volume](docs/imagens/preco.png) | ![Comparação de ativos](docs/imagens/comparar.png) |
| **Risco (quedas)** | **Retorno mensal** |
| ![Drawdown](docs/imagens/drawdown.png) | ![Retorno mensal](docs/imagens/retorno-mensal.png) |

### Planos

Os limites ficam num lugar só (`src/planos.py`) e valem também no banco de dados. A cobrança é
**só em modo de teste** do Stripe: nenhum pagamento real é feito, e hoje só o Pro tem assinatura
(o Plus ainda não está à venda).

| | Gratuito | Plus | Pro |
|---|---|---|---|
| Simulações guardadas | 5 | 30 | ilimitadas |
| Favoritos | 3 | 10 | 20 |
| Ativos na carteira | 4 | 6 | 8 |
| Relatórios em PDF | do ativo, 3 a cada 24 h | todos os tipos, 20 a cada 24 h | todos, sem limite |
| PDFs originais guardados | 10 | 50 | 200 |
| Parâmetros só para um ativo | não | 10 | 50 |
| Listas do Research | 1, de até 10 ativos | 3, de até 20 | 10, de até 50 |
| Alertas compostos | 1 | 5 | 20 |
| Links compartilhados ativos | 3 | 20 | 100 |
| Aprendizado de máquina, Pairs trading e Carteira no Research | não | não | sim |
| Exportar CSV | sim | sim | sim |

### Identidade visual

Segue o manual de identidade v1: marinho `#0A1F44`, azul elétrico `#2962FF`, claro `#F6F8FB` e
azul claro `#E8F0FF`, o símbolo T geométrico em dois traços (`static/marca/`) e a assinatura
"Dados auditáveis para quem analisa empresas no Brasil.". O site abre claro, com faixas em marinho e um
botão para o tema escuro; o app é escuro em marinho. As fontes Manrope e JetBrains Mono são
servidas pelo próprio site, sem Google Fonts. As cores ficam num lugar só, `src/marca.py`, de
onde saem o tema do Streamlit, o CSS, o tema dos gráficos, os relatórios em PDF e o site público.

## Ferramentas grátis no site

Catorze páginas em `tickerlab.com.br/ferramentas.html`, sem login. As contas de referência estão
em Python (`src/ferramentas/`) e foram copiadas em TypeScript para rodar no navegador
(`web/src/ferramentas/`); um teste "golden" confere que as duas dão o mesmo número.

| Ferramenta | O que calcula |
|---|---|
| Juros compostos | juros simples e compostos, mês a mês |
| Aportes e metas | valor futuro, aporte para chegar à meta e meses até lá |
| Viver de renda | quanto juntar e quanto tempo o dinheiro dura |
| Renda fixa | CDB, LCI/LCA, Tesouro Selic, Prefixado e IPCA+, poupança, com IR, IOF e custódia, e o ponto de empate |
| Fundo ou CDB | fundo DI (taxas e come-cotas) contra CDB |
| Juro real | juro descontada a inflação (equação de Fisher) |
| Correção pela inflação | valor corrigido pelo IPCA, do jeito da Calculadora do Cidadão |
| Conversor de moedas | conversão pela PTAX, com cotação cruzada |
| Preço médio | preço médio de ações e FIIs, com as regras do app |
| DARF | o imposto de ações do ano inteiro: 15% e 20%, isenção de R$ 20 mil e compensação de prejuízo |
| Simulador de financiamento | SAC contra Price, com amortização extra |
| Custo das taxas e da queda | quanto uma taxa anual e uma queda custam no longo prazo |
| Sorte em série | estratégias de cara ou coroa: a melhor parece genial |
| Quanto daria? Foi sorte? | quanto um valor aplicado num mês teria virado em CDI, poupança, dólar, Ibovespa e bitcoin, e onde essa data cai entre todas as possíveis |

Os dados (PTAX, séries do BC, Focus e taxas do Tesouro Direto) são atualizados uma vez por dia
pelo `scripts/exportar_dados_das_ferramentas.py`. O "Quanto daria?" usa uma rota pública da API
que devolve **só o resultado**, nunca a série de preços, com limite de pedidos por IP.

## A base de dados

O pacote `base/` monta a base de dados que alimenta o research e os modelos. Ele roda fora do app
(o app só lê o que vai para o banco). A ideia central: **várias fontes oficiais só mostram o
"agora" ou reescrevem o passado sem avisar**, então a base guarda cada original e consegue
responder como os dados **eram** em qualquer data.

- **Fontes (58 no catálogo do arquivista, `base/arquivo/fontes.py`):** CVM (IPE, DFP, ITR, FRE,
  FCA, CDA, VLMO, FIDC, ofertas, sancionador e cadastros, inclusive as versões antigas em XML do
  ENET), Banco Central (IF.data e SCR.data), Tesouro, B3 (negócios do pregão), órgãos públicos
  (CGU, PGFN, Receita, IBAMA, ANP, ONS, ANEEL e outros), SEC, IEX e fontes de cripto.
- **Original guardado:** cada arquivo baixado fica no acervo com o SHA-256 como nome, e cada
  coleta entra num registro e num manifesto diário.
- **Ponto no tempo:** cada linha tem a data em que ficou pública e até quando valeu;
  `como_era_em(base, data)` devolve a base como era naquele dia. Nada usa informação do futuro.
- **Versão só quando o conteúdo muda:** baixar de novo o mesmo dado não cria versão; quando o
  conteúdo muda, a tabela anterior é guardada.
- **Linhagem:** cada linha de cada tabela se liga ao manifesto, à coleta e ao original no acervo;
  as tabelas derivadas seguem até os originais das tabelas de entrada.
- **Contrato de dados:** as 92 tabelas têm catálogo (`base/contratos/catalogo.json`), contrato
  congelado por versão e changelog (`docs/CHANGELOG-da-base.md`), com versão semântica conferida
  no CI. O dicionário de cada coluna está em `docs/dicionario-da-base.md`.
- **Âncora no Bitcoin:** toda noite, se a base mudou, uma raiz de Merkle dos manifestos é
  carimbada pelo OpenTimestamps. Qualquer pessoa pode provar que uma versão da base já existia
  naquele bloco, e um cliente pode conferir uma tabela sem ver as outras. O recibo prova a data,
  não que o dado está certo (`docs/ancoragem-da-base.md`).
- **Regras de qualidade** que apontam problemas e nunca corrigem em silêncio, e empresas que
  saíram da bolsa mantidas na base (contra o viés de sobrevivência).
- **Dados intradiários grátis (só pesquisa):** negócios do pregão da B3 e da IEX viram barras de 1
  minuto com um "selo" de completude por ativo e por pregão; uma segunda cópia dos negócios da B3
  é conferida contra a primeira pelo SHA-256, e um alarme avisa se um pregão vai sumir da fonte sem
  estar salvo.

### Inteligência artificial, com trava

Modelos de linguagem entram em dois pontos do research, e só com controles escritos antes:

- **Assunto dos fatos relevantes** que o leitor por regras não classifica.
- **Rótulos da fila de eventos** (nota, tema e assunto), enviados em lote com teto de gasto. Antes
  do envio, o nome da empresa, os códigos e o CNPJ viram marcadores, para o modelo não "reconhecer"
  a empresa. A resposta precisa vir de uma lista fechada e citar um trecho que exista no documento.
- **Auditoria:** os rótulos da IA só entram em treino se concordarem com pelo menos 300 rótulos
  feitos às cegas pelo autor (kappa e acerto mínimos), e se a IA reconhecer a empresa em no máximo
  10% dos casos. Rótulo de IA fica marcado e nunca se mistura com os humanos.

## TickerLab Trade: a pesquisa de trading quantitativo

Uma linha de pesquisa separada do app, para responder com rigor: **um modelo de machine learning,
treinado só com o passado, consegue operar melhor do que uma regra simples de tendência, depois de
custos e descontando a sorte de testar muitas ideias?**

- **Fases:** M0 ambiente (MetaTrader 5 em conta de demonstração) → M1 dados (histórico diário de
  mais de 80 ativos: forex, ações da B3, índices, renda fixa, commodities e cripto) → M2 pesquisa
  com ML → M3 teste em conta demo → M4 controles de risco → M5 painel. A M2 terminou sem nenhum
  modelo aprovado e a pesquisa está pausada.
- **Método da M2:** critério de aprovação escrito e aprovado **antes** de ver qualquer resultado
  (Sharpe deflacionado, PBO, t-estatística ≥ 3, vitória sobre a regra de tendência com folga
  estatística, consistência entre ativos e no tempo, estresse de custos, teste contra o acaso);
  validação cruzada combinatória com expurgo (CPCV); custos por classe de ativo e carry de juros;
  testes automáticos de vazamento de informação; registro de **todas** as tentativas; os últimos
  3 anos de dados lacrados como prova final.
- **Resultado da M2:** nenhum modelo foi aprovado (regressão logística, floresta aleatória,
  LightGBM, meta-rotulagem, redes neurais MLP e LSTM e ARIMA), e os 3 anos lacrados continuam sem
  uso. Resultado negativo também é publicado. A versão 0.4 do critério declara no próprio texto
  que foi escrita depois de ver resultados.
- **Regras:** só leitura (há testes que impedem o código de enviar ordens), só conta de
  demonstração, nenhuma ordem com dinheiro real sem decisão escrita do autor, e nada disso roda no
  app público. O pacote `MetaTrader5` só funciona no Windows, por isso a pesquisa roda no PC.

O código das fases M1 e M2 (dados, critério em código, validação, modelos e um painel só de
leitura) está em `trader/`, e os critérios pré-registrados, em `docs/pre-registro-m2-v0.1.md` a
`v0.4.md`.

## Qualidade e testes

- **Mais de 3.500 testes** (pytest) em 267 arquivos, rodando com **PostgreSQL 16 de verdade**, em
  5 máquinas ao mesmo tempo no GitHub Actions. A cobertura mínima é de **85%** (`.coveragerc`); o
  CI falha abaixo disso.
- **Estilo e tipos:** `ruff` (estilo e formatação) e `pyright` (tipos) em todo commit.
- **Testes "golden":** guardam os números da análise, das estratégias, da carteira, do teste contra
  o acaso e do ML; um número que muda sem subir a versão da fórmula quebra o teste.
- **Princípios com teste:** sem olhar o futuro (cortar o futuro não muda o passado), isolamento
  entre usuários, nenhuma ordem enviada pela pesquisa, a API sem preço bruto.
- **Front-end:** licenças das dependências, `npm audit`, tipos, testes (vitest) e build conferido
  contra o que está no Git.
- **Imagem Docker:** o CI constrói a imagem e confere que o app, a API, as migrações e o login do
  Google abrem dentro dela.
- **Fluxo:** nada entra na `main` sem PR e CI verde; a `main` vai para produção sozinha.

## Como rodar no seu computador

Requer Python 3.12.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
```

Sem a configuração do login (`.streamlit/secrets.toml`), o app roda em **modo local**: sem
contas, com todos os recursos liberados e um banco SQLite em `dados_locais/`. Sem internet (ou se
o Yahoo Finance falhar), marque "Usar dados de exemplo" em "Opções avançadas": ele usa cópias de
5 anos de 13 tickers guardadas em `dados_de_exemplo/`.

Site público e pesquisa:

```powershell
.venv\Scripts\python -m scripts.gerar_site                     # parte do Python de site/
.venv\Scripts\python -m scripts.exportar_conteudo              # conteúdo para o React
cd web; npm ci; npm run site                                     # páginas de site/ (React)
.venv\Scripts\python -m pip install -r requirements-trader.txt  # só para a pesquisa (Windows)
```

Testes e estilo (a suíte inteira leva cerca de 2 minutos em 4 processos):

```powershell
.venv\Scripts\python -m pytest -q -n 4 --dist loadgroup
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m pyright
```

## Configuração (produção)

<details>
<summary>Segredos, variáveis de ambiente e migrações do banco</summary>

Segredos nunca vão para o Git: ficam em arquivos com permissão 600 no servidor.

| Onde | O que |
|---|---|
| `.env` (modelo em `.env.example`) | `TICKERLAB_DATABASE_URL` (PostgreSQL), `TICKERLAB_AMBIENTE=producao` (sem o login configurado, o app não abre), `TICKERLAB_ADMINS`, chaves do Stripe de **teste** (`rk_test_`/`sk_test_`: chaves de produção são recusadas), `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET`, `TICKERLAB_URL_PUBLICA` (e, só quando for ligar a API de leitura, `TICKERLAB_API_V1=1`) |
| `.streamlit/secrets.toml` (modelo em `secrets.toml.example`) | Cliente OAuth do Google (`[auth]`) |

O esquema do banco é criado pelas migrações do Alembic (`migracoes/`, de 0001 a 0037), aplicadas
sozinhas quando o contêiner sobe: `python -m alembic upgrade head`.

</details>

## Publicar com Docker

<details>
<summary>Os contêineres do app e da API</summary>

O `compose.yaml` sobe dois serviços com a mesma imagem: `tickerlab` (o app, `127.0.0.1:8501`) e
`tickerlab-api` (FastAPI, `127.0.0.1:8000`). As portas ficam só em `127.0.0.1`; o acesso de fora
vem de um túnel (Cloudflare Tunnel), sem nenhuma porta aberta para a internet.

```bash
mkdir -p dados_locais && touch .streamlit/secrets.toml   # pasta do cache e arquivo de login
docker compose up -d --build
```

Veja `projeto-acoes/stripe.md` (fora deste repositório, na pasta do projeto) para ligar a
cobrança de teste.

</details>

## Operação

- **Hospedagem:** um VPS em São Paulo com os contêineres Docker e o PostgreSQL, sem nenhuma porta
  aberta para a internet. O tráfego chega pelo Cloudflare Tunnel: `app.tickerlab.com.br` (app),
  `api.tickerlab.com.br` (API e webhook) e `tickerlab.com.br` (site público, servido pelo nginx).
  A administração do servidor é feita só por uma rede privada (Tailscale). As coletas pesadas da
  base rodam numa segunda máquina do autor.
- **Deploy automático:** `scripts/deploy-automatico.sh`, no cron do servidor (a cada minuto),
  implanta o commit mais novo da `main` **cujos testes passaram**, espera as tarefas agendadas
  terminarem, reconstrói os contêineres, espera o app e a API ficarem saudáveis e, se não ficarem,
  volta sozinho para a versão anterior. A imagem leva o commit, então se sabe sempre qual versão
  está no ar.
- **Tarefas agendadas:** coletas diárias (fundamentos, eventos da CVM e da SEC, séries
  macroeconômicas, dados das ferramentas, newsletter), o arquivista das fontes oficiais, as barras
  intradiárias e a âncora da base no Bitcoin. Toda tarefa que falha termina com uma linha
  `FALHAS:` que vira alarme.
- **Logs:** uma linha de JSON por registro (`TICKERLAB_LOG_FORMATO=json`), sem e-mail nem nome:
  `docker logs tickerlab-api | jq`.
- **Monitor:** um Uptime Kuma em outra máquina verifica de fora o app, a API, o site, a rota do
  webhook e as tarefas agendadas.
- **Carga leve:** `python scripts/carga_leve.py URL --total 300 --simultaneas 20`.

## Segurança e privacidade

- Login só com o Google; e-mail não verificado é recusado. Cada pessoa vê apenas os próprios
  dados (toda consulta filtra pelo usuário, com testes de isolamento).
- Webhook do Stripe com assinatura verificada, idempotente e tolerante a eventos fora de ordem.
  O plano só muda pelo webhook.
- API v1 com o token do Google conferido pela assinatura, limite de pedidos por minuto e o plano
  conferido rota por rota; ela entrega números calculados, nunca preço bruto.
- Painel de administração confere o papel **no banco** a cada ação e registra tudo em uma
  auditoria que guarda só ids, nunca e-mail ou nome. Erros do banco não expõem dados pessoais.
- LGPD: aceite dos termos no primeiro acesso (com versão e data), exportação dos dados em JSON e
  exclusão da conta em cascata, encerrando antes a cobrança no Stripe. As planilhas da B3 nunca
  são gravadas. E-mails (newsletter e novidades) só com opt-in e descadastro sem login. Os textos
  estão em `conteudo/termos.md` e `conteudo/privacidade.md` (ainda sem revisão de advogado; a
  revisão jurídica vem antes da cobrança real).
- Política de segurança e como relatar uma falha: `SECURITY.md`.

## Princípios do projeto

- **Sem olhar o futuro.** Toda decisão tomada no fim do dia só vale a partir do dia seguinte, e
  há testes que conferem que cortar o futuro não muda o passado. Na base, cada valor vale a partir
  do dia em que ficou público.
- **Honestidade com os números.** O app mostra o que não funcionou: a maioria das estratégias
  não passa no teste contra o acaso, o Sharpe vem com intervalo e o modelo de aprendizado de
  máquina é comparado com uma previsão ingênua. Na pesquisa, as regras são escritas antes dos
  resultados e resultado negativo também conta.
- **Origem de cada número.** Fundamentos, eventos e dados da base levam o link do documento
  oficial e a data em que ficaram públicos.
- **Limites explícitos.** Custos e imposto simplificados, perna vendida do pairs trading sem o
  custo do aluguel, dados do Yahoo sujeitos a erro.
- **Cada conceito explicado.** O glossário (`conteudo/glossario.md`) e as explicações de cada
  estratégia (`conteudo/estrategias.md`) aparecem na tela e são conferidos por testes.
- **Sem promessa de rentabilidade e sem preço-alvo.** Em nenhuma tela, relatório ou página do site.

## Estado atual e limites conhecidos

Para uma avaliação justa, o que ainda **não** está pronto:

- **Sem receita:** a cobrança está em modo de teste; antes da cobrança real vêm a revisão jurídica
  dos termos e da política de privacidade e a decisão sobre o Plus.
- **Newsletter** liberada só para administradores até o parecer jurídico.
- **API v1** pronta, mas desligada; a documentação (`docs/api/`) ainda não lista as rotas mais
  novas (links compartilhados e ferramentas).
- **App novo em React** com 9 telas; as demais páginas continuam no Streamlit (a versão clássica,
  em `/classico/`).
- **Base de dados** sem carga do histórico completo do COTAHIST da B3; os intradiários são só
  para pesquisa e não aparecem no app.
- **TickerLab Trade** pausado depois da M2 sem modelo aprovado; não há operação com dinheiro real.
- **Documentação de decisões fora do repositório:** o planejamento e as ADRs ficam numa pasta
  privada do autor; o código foi escrito com ajuda intensa de assistentes de IA, sempre por PR,
  com testes e CI.

## Estrutura

<details>
<summary>Mapa das pastas e dos módulos</summary>

```
app.py                configura o app, monta o menu e roda a página
telas/                a cola com o Streamlit: um arquivo ou pasta por grupo de páginas
src/                  as contas, as regras e os dados (não importa o Streamlit)
  paginas.py          o mapa do app: grupos, páginas e a frase de cada uma
  modulos.py          o catálogo de módulos da página "Produto" do site
  planos.py           limites do Gratuito, do Plus e do Pro (um lugar só)
  marca.py            cores e fontes da identidade visual
  autenticacao.py, conformidade.py, auditoria.py, administracao.py   login, LGPD, auditoria e admin
  banco/              modelo, conexão, usuários, coletas e dados por usuário (SQLAlchemy)
  cobranca.py         Stripe: pagamento, portal e eventos (idempotentes)
  api.py, api_v1/     FastAPI: saúde, webhook, descadastro, ferramentas e a API de leitura v1
  dados.py, armazenamento.py, exemplos.py, moedas.py, catalogo.py   preços, cache, exemplos, câmbio e busca
  indicadores.py, metricas.py, analise.py               números básicos e métricas de desempenho
  backtest.py, estrategias.py, protecoes.py, imposto.py motor vetorizado, 12 estratégias, stops e IR
  validacao.py, acaso.py, ranking.py, ficha.py          validação honesta e a ficha "Foi sorte?"
  carteiras.py, hrp.py, experimentos.py, regimes.py, aprendizado.py, pares.py
  research.py, eventos*.py, leitura.py, topicos*.py, linha_do_tempo.py, pulse.py   acontecimentos e leitor
  fundamentos*.py, demonstracoes.py, notas*.py, valuation.py, relatorio_empresa*.py   balanços e empresa
  negociacoes*.py, detentores.py, fundos_cvm.py, fundos_sec.py   pessoas de dentro, fundos e 13F
  carteira_b3.py, movimentacao_b3.py, negociacao_b3.py, dividendos_e_custo.py, proventos_a_receber.py,
  resultado_por_mes.py   planilhas da Área do Investidor da B3
  alertas.py, diario_de_teses.py, compartilhamentos.py, exportacao.py, simulacoes.py
  newsletter.py, novidades.py, envio_*.py               e-mails com opt-in
  bcb.py, cdi.py, juros_e_inflacao.py, tesouro_*.py     dados do BC e do Tesouro
  rotulos_ia.py, auditoria_rotulos.py, evidencias.py    rotulagem por IA e a auditoria dela
  iex_tops.py, barras_intradiarias.py, calendario_nyse.py, prazos.py   intradiários e calendários
  ferramentas/        contas de referência das ferramentas grátis
  relatorios.py, relatorio_pdf.py, estilos_pdf.py, graficos_pdf.py, previa_pdf.py   relatórios em PDF
  graficos.py         gráficos Plotly
base/                 a base de dados: arquivista, ponto no tempo, linhagem, contratos e âncora
  arquivo/            o arquivista das fontes oficiais (58 fontes)
  contratos/          catálogo e contratos versionados das tabelas
  conferidas/         tabelas conferidas à mão
  cripto/, leitor/, modelos/   dados de cripto, lote de medição do leitor e rótulos dos modelos
trader/               TickerLab Trade: pesquisa de trading, só leitura do MetaTrader 5
web/                  React + TypeScript: o site, as ferramentas e o app novo
site/                 site público estático (gerado)
novo/                 app novo em React, servido na raiz de app.tickerlab.com.br (gerado)
static/               fontes e símbolo servidos pelo próprio site
conteudo/             glossário, estratégias, catálogo de ativos, termos e privacidade
migracoes/            migrações do banco (Alembic)
scripts/              deploy, coletas, cargas da base, âncora, site, golden, imagens do README
tests/                testes automatizados (pytest)
docs/                 padrões de código, base de dados, API, pré-registros e imagens
notas/, guias/, estudos/   caderno de estudos do autor
```

</details>

## Referências das técnicas

Sharpe probabilístico e deflacionado (Bailey e López de Prado, 2014), PBO (Bailey, Borwein,
López de Prado e Zhu, 2017), barreira tripla, expurgo e embargo, validação cruzada combinatória,
meta-rotulagem e HRP (López de Prado), variância gerida (Moreira e Muir, 2017), cointegração
(Engle e Granger), limiar de t-estatística para múltiplos testes (Harvey, Liu e Zhu, 2016),
decaimento de sinais depois de publicados (McLean e Pontiff, 2016), F-score (Piotroski, 2000),
árvores de Merkle no formato da RFC 6962 e o OpenTimestamps. As fórmulas foram implementadas a
partir da descrição dos artigos e conferidas por testes e simulações; vale conferi-las nas fontes
originais antes de qualquer uso sério.

## Direitos autorais

© 2026 Tiago Borsari Coelho. **Todos os direitos reservados.**

Este repositório é público para consulta (avaliação acadêmica, de investidores e portfólio), mas
**não tem licença de código aberto**: o código, os textos e a identidade visual do TickerLab não
podem ser copiados, modificados, redistribuídos nem usados em outro produto ou serviço sem
autorização por escrito do autor. Ver o código no GitHub e criar um fork pela própria plataforma é
permitido pelos termos de uso do GitHub; isso não dá direito de uso fora dele.

Componentes de terceiros continuam com as próprias licenças: as bibliotecas listadas em
`requirements.txt`, `requirements-trader.txt` e `web/package.json`, e as fontes Manrope e
JetBrains Mono (SIL Open Font License, textos em `static/fontes/`). Os dados abertos republicados
seguem as licenças das fontes.

---

<p align="center">
  <img src="static/marca/icone.png" alt="" width="40"><br>
  Feito por <b>Tiago Borsari Coelho</b> · começou na matéria de Python e Pandas<br>
  <sub>Não é recomendação de investimento. Sem promessa de rentabilidade.</sub>
</p>
