# APIs do TickerLab

Duas APIs, no mesmo serviço FastAPI (`src/api.py`):

- **API de leitura (`/api/v1`)**, para o app novo e o site: a conta entra pelo navegador.
- **API externa de dados (`/data/v1`, TickerLab Data)**, para quem integra: a organização entra pela
  chave dela. Ver [a seção dela](#api-externa-de-dados-datav1).

Em produção, a de leitura está **no ar** e serve o app; a externa segue **desligada**. Cada uma só
entra no serviço com a variável dela (`TICKERLAB_API_V1=1` e `TICKERLAB_API_EXTERNA=1`).

# API de leitura (v1)

A interface nova do TickerLab (React, ADR 0048) não calcula nada: ela pede os números à API, que
chama as mesmas funções de `src/` que as telas do Streamlit usam. Assim, o número na tela nova é o
mesmo da tela antiga.

**Estado:** **no ar** em produção, servindo o app (com login). As rotas só são montadas com
`TICKERLAB_API_V1=1` no ambiente; sem isso, toda rota `/api/v1/...` responde 404. O login pelo Google
precisa também de `TICKERLAB_GOOGLE_CLIENT_ID`; sem ele, responde 503.

## Onde está cada coisa

| O quê | Onde |
|---|---|
| Rotas das páginas do app | `src/api_v1/rotas.py` |
| Conta (login, sair, termos) e entrada por código | `src/api_v1/conta.py`, `src/api_v1/entrada.py`, `src/api_v1/sessao.py` |
| Rotas públicas do site (sem login) | `src/api_v1/ferramentas.py`, `src/api_v1/estudos.py`, `src/api_v1/base_publica.py`, `src/api_v1/base_tabelas.py` |
| Links compartilhados e sala de dados | `src/api_v1/compartilhados.py`, `src/api_v1/sala*.py` |
| Formato das respostas | `src/api_v1/esquemas.py` (Pydantic) |
| Sessão, chave liga/desliga e limite de pedidos | `src/api_v1/acesso.py` |
| Carregar o ativo (preços, retorno, taxa livre de risco) | `src/api_v1/contexto.py` |
| O que cada página mostra | `src/analises.py` |
| Contrato de cada página (entradas, rota e resposta) | `Pagina.contrato` em `src/paginas.py` |
| Esquema publicado (OpenAPI) | `docs/api/openapi-v1.json` |

## Login

A tela faz o login no navegador e abre uma **sessão de 30 dias num cookie** (`__Host-tl_sessao`,
`HttpOnly`, `Secure`, `SameSite=Lax`); daí em diante as rotas leem só o cookie.

- **Google:** a tela manda o *ID token* uma vez para `POST /api/v1/conta`. A API confere a
  assinatura (chaves públicas do Google), o destino (`aud` = o client ID do TickerLab), o emissor, a
  validade e o e-mail verificado; cria a conta no primeiro acesso.
- **Código por e-mail:** `POST /api/v1/entrada/codigo` manda um código de 6 dígitos e responde sempre
  202 (não revela quem tem conta); `POST /api/v1/entrada/confirmar` confere o código e abre a sessão.
- **Sair:** `POST /api/v1/sair` (esta sessão) e `POST /api/v1/sair-de-todos`.

Todo pedido que muda algo e chega com o cookie precisa provar que saiu do próprio app: o cabeçalho
`X-TickerLab-Pedido: 1` e a origem (`Origin`) igual ao endereço do app. A conta precisa ter aceitado
os termos atuais (`POST /api/v1/aceite-dos-termos`), menos para baixar os próprios dados (LGPD), e o
plano dela precisa abrir a página da rota.

| Resposta | Quando |
|---|---|
| 401 | sem sessão, token inválido ou sessão vencida |
| 403 | conta sem os termos atuais, plano que não abre a página ou pedido vindo de fora do app |
| 404 | API desligada, ou ativo sem dados |
| 422 | pedido fora dos limites (período, janela, custo, parâmetros) ou período curto demais |
| 429 | mais de 60 pedidos por minuto da mesma conta |
| 503 | login não configurado, o Google fora do ar, ou séries de juros ainda não coletadas |

No 401 e no 403, o cabeçalho `X-TickerLab-Motivo` diz o porquê, para a tela mostrar o caminho certo:
`sem-token`, `token-invalido` e `sessao` (entrar de novo), `termos` (aceitar os termos), `plano`
(o caminho para o plano maior) e `pedido-de-fora` (pedido com o cookie que não saiu do app).

## Rotas

A lista completa, com cada entrada e cada resposta, é o esquema publicado (`docs/api/openapi-v1.json`).
As principais páginas:

| Página | Rota | Resposta |
|---|---|---|
| (antes do login) | `GET /api/v1/configuracao` (sem token) | `ConfiguracaoV1`: o client ID do Google |
| (a conta) | `GET /api/v1/eu` | `EuV1`: plano e limites, sem e-mail |
| (a conta) | `GET /api/v1/meu-plano`, `GET /api/v1/meus-dados` | o plano e o uso; a exportação dos dados (LGPD) |
| Visão geral | `GET /api/v1/visao-geral?ticker=PETR4&periodo=2y` | `VisaoGeralV1` |
| Risco | `GET /api/v1/risco?ticker=PETR4&janela=20` | `RiscoDoAtivoV1` |
| Retorno mensal | `GET /api/v1/retorno-mensal?ticker=PETR4` | `RetornoMensalDoAtivoV1` |
| Comparar ativos | `GET /api/v1/comparacao?ticker=PETR4&com=VALE3&com=AAPL` | `ComparacaoDoAtivoV1` |
| Backtest | `POST /api/v1/backtest` (corpo `PedidoDeBacktestV1`) | `BacktestDoAtivoV1` |
| Juros e inflação | `GET /api/v1/juros-e-inflacao` | `JurosEInflacaoV1` |
| Linha do tempo | `GET /api/v1/linha-do-tempo?ticker=PETR4&materialidade_minima=50` | `LinhaDoTempoDoAtivoV1` |
| Simulações guardadas | `GET /api/v1/simulacoes`, `POST /api/v1/salvar-simulacao`, `POST /api/v1/apagar-simulacao` | as simulações da conta |
| Relatório da empresa | `GET /api/v1/relatorio-empresa` (e `/apresentacao`, `/markdown`) | a ficha da companhia |
| Busca por CNPJ | `POST /api/v1/busca-por-cnpj` (e `/pdf`) | o que a base sabe de um CNPJ |
| Setores | `GET /api/v1/setores`, `GET /api/v1/relatorio-setor` (e `/pdf`, `/apresentacao`) | o relatório do setor |
| Pulse | `GET /api/v1/pulse` | o que mudou desde a última visita |
| Assinatura | `POST /api/v1/pagamento-da-assinatura`, `POST /api/v1/portal-da-assinatura` | o endereço do Stripe (modo de teste) |
| Links compartilhados | `GET /api/v1/links-compartilhados`, `POST /api/v1/revogar-link` | os links da conta |

Fora do esquema publicado, de propósito: o link compartilhado (`/api/v1/compartilhados/...`) e a sala
de dados por operação (`/api/v1/operacoes/...`, aberta a toda conta logada; outra conta recebe 404).

**Rotas públicas do site** (sem login, com limite por IP): `GET /api/v1/ferramentas/quanto-daria`, o
pregão do dia (`GET /api/v1/estudos/pregao/ultimo` e `/{data}`), os destaques da busca por companhia
(`GET /api/v1/base/destaques`) e a consulta às tabelas da base (abaixo).

### Consulta e exportação das tabelas da base

A página Dados do site consulta e exporta cada tabela da base por estas rotas (`src/api_v1/base_tabelas.py`;
virada de 5/11/2026, fase 1, PR 3). Só sai tabela que `base.dossie.pode_consultar` deixa: que pode ser
mostrada, que a porta da base (`base/porta`) serve por Parquet, que diz em `publico_em` o dia em que
cada linha ficou pública e que separa as linhas de pessoa (a situação especial e a cadastral do CNPJ, que
cobrem MEI e empresário individual sem essa marca, esperam por ela). Nenhuma tabela de pessoa natural,
nenhuma linha marcada como de pessoa, e cada resposta traz a origem (fonte e licença; o dia público e a
linhagem são colunas da própria tabela).

A consulta corta o futuro sempre: sem `como_era_em`, vale hoje (a linha que só fica pública depois não
sai), e a data nunca pode ser futura. A ordem é total: as chaves do contrato e, para desempatar, as
demais colunas, então páginas seguidas não perdem nem repetem linha.

| Rota | O que devolve |
|---|---|
| `GET /api/v1/base/tabelas` | as tabelas consultáveis, cada uma com as colunas (nome, tipo e descrição), as chaves, a versão do contrato, a fonte, a licença e o começo do histórico; cache público de 1 hora |
| `GET /api/v1/base/tabelas/{nome}` | uma página de linhas em JSON, na ordem das chaves do contrato, com `total`, `colunas`, `linhas` e a origem; `cnpj` filtra (14 dígitos ou com pontuação), `como_era_em` mostra a base como era naquele dia (só o que já era público; padrão: hoje), `limite` (padrão 100, até 1.000) e `deslocamento` (até 100.000; para ir além, filtre por CNPJ) paginam; `teto_do_csv` diz quantas linhas o CSV leva |
| `GET /api/v1/base/tabelas/{nome}.csv` | a mesma consulta (mesmos filtros) em CSV, de uma consulta só, em fluxo, UTF-8 com BOM (o Excel abre com acento certo), até 100.000 linhas; cada linha leva no fim `fonte_do_dado` e `licenca_do_dado`; o teto vai no cabeçalho `X-TickerLab-Teto`. Quando o arquivo para antes do fim, a última linha começa com `#` e diz por quê: "Arquivo cortado em 100000 linhas" (a tabela tem mais) ou "Arquivo incompleto" (a leitura falhou no meio, com a resposta já em 200) |

Erros: 404 para tabela que não existe, de pessoa, barrada ou fora da porta (a mesma resposta, para
não revelar o que existe); 422 para entrada inválida (CNPJ, data futura, limite fora da faixa); 429
quando o IP passa do limite por minuto; 503 quando a porta não abre, a tabela não está nesta base ou
as portas ao mesmo tempo estão todas ocupadas (no máximo 2 por processo, cada uma com 512MB e 2
threads do DuckDB: o contêiner é pequeno e serve também o webhook).

**Em produção, estas rotas dependem da base montada no contêiner:** a API v1 está no ar, e o contêiner
da API (`compose.yaml`, serviço `tickerlab-api`) lê a base de `TICKERLAB_ACERVO`, uma pasta só de
leitura com o recorte sem pessoa que `scripts/montar_recorte_da_api.py` envia. Com a pasta ausente ou
vazia, a API sobe igual e estas rotas respondem 503; a tabela que não está no recorte também dá 503.
Na página Dados, a coluna "Consulta", a frase e o painel nascem escondidos e só aparecem quando
`GET /api/v1/base/tabelas` responde. A `fidc_informe` (410 colunas) não cabe nos 512MB da porta nem
numa leitura simples e fica fora do recorte: a consulta aberta não a anuncia nem a serve (404, como as outras 14 da linha 842) até ter prontidão.

Sem `taxa`, a taxa livre de risco é o CDI do período (zero se o Banco Central não responder), como
na tela. Toda resposta traz `ativo` com o período real, a origem dos preços (`atual`,
`cache_antigo` ou `exemplo`) e a taxa usada, para a tela mostrar os mesmos avisos.

**Juros e inflação** não tem ativo: devolve o painel de hoje (Brasília) lido do acervo de séries do
Banco Central, com a referência, a divulgação e a fonte de cada número, e os textos prontos da tela
(`texto`, `legenda`, `avisos`). Responde 503 se as séries ainda não foram coletadas no servidor.
**Linha do tempo** devolve a curva **em base 100** e os documentos da CVM ou da SEC do período
(`materialidade_minima`: 70 = os mais relevantes, 50 = relevantes, 0 = todos); a taxa vem zerada,
porque a página não usa taxa livre de risco.

**Sem preço bruto:** pela licença dos preços (ADR 0008), a API entrega só números calculados,
quedas, volatilidades e curvas em base 100. Há teste que recusa campos de preço nos esquemas.

## Como uma tela nova usa isto

1. Ler o contrato da página em `src/paginas.py`. Na visão geral, as entradas são `ticker`
   (obrigatório), `periodo` (opções `6mo`, `1y`, `2y`, `5y`; padrão `2y`), `taxa` (0 a 1, opcional)
   e `confianca_do_var` (90 a 99, padrão 95), e a resposta é `VisaoGeralV1`.
2. Gerar os tipos do TypeScript a partir de `docs/api/openapi-v1.json` (por exemplo, com
   `openapi-typescript`).
3. Montar os campos com esses limites, chamar a rota e desenhar a resposta.

## Mudou uma rota ou um esquema?

```powershell
.venv\Scripts\python -m scripts.gerar_openapi
```

Revise o diff de `docs/api/openapi-v1.json` no PR: ele mostra o que muda para a tela nova. Os
testes falham se o arquivo ficar velho ou se um contrato de página não bater com a rota.

# API externa de dados (`/data/v1`)

O dado da base para quem integra (TickerLab Data, ADR 0108), pela chave da organização cliente.

**Estado:** em construção e **desligada**. Só entra no serviço com `TICKERLAB_API_EXTERNA=1`; sem
isso, as rotas nem são montadas (respondem 404). O MCP vem depois do beta.

| O quê | Onde |
|---|---|
| Rotas | `src/api_externa/rotas.py` |
| Chave, quota do mês e limite do minuto | `src/api_externa/acesso.py`, `src/banco/chaves_da_api.py` |
| Catálogo e consumo da organização | `src/api_externa/catalogo.py` |
| Fonte, data e atribuição de cada campo | `src/api_externa/envelope.py` |
| Consulta em lote | `src/api_externa/lote.py` |
| Nomes de fora (inglês) e de dentro (português) | `src/api_externa/nomes.py` |
| O que cada conjunto lê da base | `src/api_externa/conjuntos/` |
| **Contrato publicado (OpenAPI)** | [`openapi-data-v1.json`](openapi-data-v1.json), gerado por `scripts/gerar_openapi_data.py` |

## Chave

A chave vai **só no cabeçalho**: `Authorization: Bearer <chave>` ou `X-API-Key: <chave>`. Chave na
URL é recusada com 400 (`api_key_in_url`), sem ecoar nada, porque iria para os logs de acesso. Toda
chave recusada recebe o mesmo 401 (`invalid_api_key`), com o mesmo corpo; o motivo fica só no log.

Cada campo passa por **duas travas**: o contrato da organização (o que ela comprou) e o portão da
base (o direito do TickerLab de redistribuir aquele campo, para aquela finalidade). Tabela sem
prontidão fica fora. Um conjunto pode ser suspenso para todas as organizações de uma vez.

## Rotas

| Rota | O que devolve | Conta na quota do mês? |
|---|---|---|
| `GET /data/v1/catalog` | o que esta chave pode pedir hoje: conjuntos, campos, licença e atribuição de cada fonte | não |
| `GET /data/v1/usage` | o consumo do mês da organização e o que falta da quota | não |
| `GET /data/v1/companies/{cnpj}` | a situação cadastral do estabelecimento na Receita (conjunto `companies`) | sim |
| `POST /data/v1/companies/batch` | o mesmo, para até 100 CNPJs | sim, um por CNPJ válido |
| `GET /data/v1/companies/{cnpj}/profile` | o perfil da empresa: o cadastro na Receita e as entregas de DFP e ITR à CVM como eram (`profiles`, ver abaixo) | sim, 1 |
| `GET /data/v1/companies/{cnpj}/comparables` | os pares da companhia aberta no mesmo grupo de setores, com os números do último DFP e a mediana de cada razão (`comparables`, ver abaixo) | sim, 1 |
| `GET /data/v1/companies/{cnpj}/links` | os vínculos da empresa na rede (controle, coligação e participação pelo FRE, auditoria pelo FCA), de 1 a 3 saltos (`links`, ver abaixo); `depth` e `types` | sim, 1 |
| `GET /data/v1/companies/{cnpj}/events` | os documentos da companhia no IPE da CVM e as trocas de auditor, do mais novo ao mais velho (`events`, ver abaixo); `types` filtra, `cursor` pega a página seguinte | sim, 1 |
| `GET /data/v1/companies/{cnpj}/financials` | as DFP e os ITR da companhia, um valor por conta e período (`financials`); `period_end` filtra o período | sim |
| `GET /data/v1/funds/{cnpj}` | taxas, custo da taxa e carteira do fundo (`funds`); o custo só com `assumed_return` | sim |
| `POST /data/v1/funds/batch` | o mesmo, para até 100 CNPJs | sim, um por CNPJ válido |
| `GET /data/v1/credit/{cnpj}` | a ficha de crédito da empresa como era em `known_at` (só fatos, ver abaixo) | sim, 1 |
| `POST /data/v1/credit/batch` | a mesma ficha para até 100 CNPJs, com o status de cada um | sim, 1 por CNPJ |
| `GET /data/v1/sectors` | os setores do relatório que a ficha da noite tem, com o dia dela | não |
| `GET /data/v1/sectors/{key}` | o mercado de um setor (molde D, ver abaixo) | sim, 1 |

Todas contam no limite do minuto (o lote conta 1). Toda leitura de dado aceita **`known_at=AAAA-MM-DD`**:
a resposta é a que a base dava naquele dia (só o que já era público nele, sem a revisão que veio depois);
sem ele, hoje. Endereços, campos e códigos saem em **inglês**; as tabelas e o código continuam em
português, e a tradução mora num lugar só (`nomes.py`): um nome sem tradução não sai.

Cada campo sai com o valor, a fonte, o dia em que ficou público e o momento em que o TickerLab o viu,
mais a licença e a frase de atribuição de cada fonte usada (`envelope.py`). O lote aceita até 100
CNPJs por chamada, conta N na quota do mês e 1 no limite do minuto, devolve o lote inteiro com 429 se
ele não couber, e diz a situação de cada item (`ok`, `not_available` ou `invalid_cnpj`).

**MEI, empresário individual e pessoa física nunca saem:** o CNPJ de uma pessoa responde
`not_available`, igual a um CNPJ que não existe.

| Resposta | `detail` | Quando |
|---|---|---|
| 400 | `api_key_in_url` | chave na URL |
| 400 | `invalid_cnpj`, `invalid_known_at`, `invalid_assumed_return`, `invalid_batch`, `invalid_cursor`, `invalid_event_type` | CNPJ que não é CNPJ, `known_at` no futuro, retorno fora do plausível, lote vazio ou com mais de 100, cursor que não veio da página anterior, tipo de evento que não existe |
| 401 | `invalid_api_key` | chave ausente, errada ou revogada, ou organização suspensa |
| 404 | `not_available` | nada a servir: CNPJ fora da base, pessoa, contrato ou direito que não cobre, tabela sem prontidão (a resposta não diz qual); com `Not Found`, a API externa está desligada |
| 429 | `rate_limited`, `monthly_quota_exceeded` | limite do minuto ou quota do mês |
| 503 | `service_unavailable` | a base não está disponível neste servidor agora |

O contrato traz, rota a rota, os códigos que cada uma pode dar.

**Parte não disponível para a organização** (linhas 878, 880 e 881; `src/api_externa/nao_disponivel.py`):
quando um pedido junta partes que o portão libera uma a uma (os tipos de evento, os tipos de vínculo, os sinais
dos compradores, os documentos das entregas, os números dos comparáveis), a parte que a organização não tem não
some em silêncio, porque a lista vazia leria como "a empresa não tem". A resposta traz a lista das partes
pedidas e não liberadas, `unavailable_<o que>` (`unavailable_event_types` em `/events`, `unavailable_link_types`
em `/links`, `unavailable_signals` em `/buyers`, `unavailable_filings` em `/profile`, `unavailable_figures` em
`/comparables`), vazia quando tudo foi consultado. A parte cuja tabela a base não tem (ou não tem pronta) também
entra na lista: nos dois casos ela não foi consultada. Os `limits` só falam das partes servidas
e, quando há parte de fora, trazem a frase de que ela não foi consultada. Se nenhuma parte pedida está liberada,
a resposta é 404 `not_available`, como o resto do contrato. Todo conjunto novo com partes segue o mesmo molde.

### Perfil (`profiles`, linha 736)

O que a base sabia da empresa no dia, campo a campo pelo portão (`conjuntos/ficha.py`):

- `registration`: o cadastro na Receita, pelo mesmo leitor de `/companies/{cnpj}` (a situação e o Simples
  como eram). A razão social e a natureza saem do retrato mensal da Receita sem pessoa mais novo que já era
  público em `known_at`, e `registry_snapshot_month` diz de que mês é esse retrato (é o retrato daquele mês,
  não "como era" no dia);
- `periodic_filings`: da companhia aberta, cada DFP e ITR que ela devia até o dia, da mais nova à mais
  velha, com o prazo da CVM (feriados e prorrogações), o dia da primeira entrega, os dias úteis de atraso
  e a situação: `on_time`, `gray_zone` (atraso curto, que um feriado local pode explicar), `late`,
  `severely_late` ou `not_filed`. Vem de `rotulos_atraso` (o índice das entregas da DFP e do ITR), pela
  mesma regra da ficha da noite (`base.dossie.entregas_conhecidas_em`). Com algum documento consultado, a
  lista sai sempre, vazia quando a base não conhece entrega da empresa;
- `unavailable_filings` (linha 881): os documentos (`DFP`, `ITR`) que o portão não libera para a organização.
  Eles não foram consultados: a lista de entregas não diz nada sobre eles, e os `limits` avisam. Sem nenhum
  documento, `periodic_filings` não sai.

Sem olhar o futuro: a entrega que só aconteceu depois de `known_at` sai `not_filed`, sem a data dela, e
os dias úteis contam até o dia pedido; a falta de um documento vale pelo prazo e só conta até o dia em
que a base a conferiu (a montagem da tabela). A situação e os dias úteis são contas nossas; o portão as
trata como derivado. A dívida com a União (PGFN) fica fora. Sem cadastro no dia, nada sai: o perfil de
pessoa (MEI, empresário individual) e de quem a rede não conhece é `not_available`. O perfil não traz
porte, CNAE nem município.

### Comparáveis (`comparables`, linha 736)

Os pares de uma companhia aberta como eram no dia (`conjuntos/comparaveis.py`):

- `sector_group`: o grupo de setores da empresa (o mesmo de `src/setores.py`, que o app usa), pelo setor do
  último FCA já entregue à CVM (`fca_geral`, como era: a empresa que muda de setor muda de pares no dia da
  entrega do FCA novo);
- `subject_company` e `peers`: cada companhia com o cadastro do FCA (`company_name`, `sector`) e os números
  do último DFP já entregue (`demonstracoes_como_era`, consolidado; sem ele, o individual): `revenue` (DRE
  3.01), `ebitda` (EBIT mais D&A, a mesma conta de `base/indicadores_de_caixa.py`), `net_income`,
  `net_assets` (patrimônio líquido), `net_debt` (empréstimos e financiamentos menos caixa e aplicações) e as
  razões `ebitda_margin`, `net_margin`, `return_on_equity` e `net_debt_to_ebitda` (só com o denominador
  positivo). Par é quem tem DFP de um exercício que terminou até 18 meses antes do dia; os pares vêm da
  maior receita para a menor e são cortados no limite de linhas do plano (`truncated`);
- `peer_medians`: a mediana de cada razão entre todos os pares (sem a empresa pedida), só quando pelo
  menos 8 pares a têm;
- `unavailable_figures` (linha 881): os números e as razões, com o nome de fora, que o portão não libera para a
  organização. Eles somem dos pares e das medianas, e os `limits` avisam: a mediana que falta por isso não quer
  dizer que faltaram pares.

Cada número traz o dia da entrega do DFP; o cadastro, o dia da entrega do FCA. Número que a base não tem
some, nunca vira zero. EBITDA, dívida líquida, as razões e o grupo de setores são contas nossas; o portão
os trata como derivado. Bancos e seguradoras têm outro plano de contas: as razões deles não se comparam às
das outras empresas. Empresa sem FCA no dia, setor que não cai em nenhum grupo, pessoa (MEI, empresário
individual) e quem a rede não conhece saem `not_available`; par que a rede trata como pessoa não entra.

### Eventos (`events`, linha 736)

Os eventos de uma companhia como eram no dia (`conjuntos/eventos.py`), do mais novo ao mais velho:

- `ipe_filing`: cada documento entregue à CVM pelo IPE (`eventos`) com o CNPJ de qualquer estabelecimento da
  mesma raiz: `filing_id` (protocolo), `category` e `kind` (os da CVM), `reference_period` e `document_url` (o documento
  no sistema da CVM). O assunto escrito pela companhia **não sai**: é texto livre e pode trazer nome de pessoa;
- `auditor_change`: cada troca da firma de auditoria informada nos FCAs (`trocas_de_auditor`): `previous`,
  `new`, `effective_on` e `years_with_previous` (conta nossa, marcada como derivado). A troca com auditor que
  pode ser pessoa física não sai.

Cada campo traz a fonte e o dia em que ficou público (o da entrega do documento; o do FCA que informou a
troca); nada publicado depois de `known_at` entra. `types=ipe_filing` ou `types=auditor_change` (repetível)
filtra. A página vai até o limite de linhas do plano (`truncated`); `next_cursor` traz a seguinte, sem perder
nem repetir evento. A rotulagem de insolvência nunca sai (inferência
individual); a empresa sem eventos não quer dizer que nada aconteceu. Pessoa (MEI, empresário individual) e
quem a rede não conhece saem `not_available`.

### Vínculos (`links`, linha 736)

Os vínculos de uma empresa como eram no dia (`conjuntos/vinculos.py`), lidos da rede de entidades do TickerLab
(ADR 0077) de 1 a 3 saltos (`depth`), nos dois sentidos:

- `subsidiary_of`, `affiliate_of` e `investee_of`: a sociedade controlada, coligada ou só participada da outra
  (`from` é a controlada; `to`, quem a controla), com `ownership_pct`, como o FRE informou (`controladas`, fonte
  `cvm-hist-fre`);
- `audits`: a firma de auditoria (`from`) que auditava a companhia (`to`), pelo FCA (`auditores`, fonte
  `cvm-hist-fca`).

Cada vínculo traz `hops` (o salto a partir da empresa pedida), `kind` (o tipo, no envelope, com a fonte e o
dia em que ficou público), `valid_from` e, quando acabou, `valid_until`. Cada ponta sai com `entity_id` (o id
na rede), `cnpj_root`, `legal_name` e `registry_snapshot_month`: a razão social do retrato mensal mais novo
da lista sem pessoa da Receita já público em `known_at` (`rfb-cnpj`, o mesmo de `GET /companies/{cnpj}`) e o mês
desse retrato. É o nome daquele retrato, não necessariamente o que valia no dia exato; antes do primeiro retrato,
numa ponta sem CNPJ ou numa raiz que não está no retrato, a ponta sai sem nome. Nada publicado depois de `known_at` entra, e o fim que só se soube depois do dia não aparece. `types` filtra (repetível); a
lista vai até o limite de linhas do plano (`truncated`). O fundo que detém o papel, o conglomerado do Banco
Central e a série do regulador não saem por aqui. A ponta que é pessoa (MEI, empresário individual, sócio
pessoa física) ou que a rede trata como pessoa não sai, nem a ligação com ela; a empresa sem vínculos não quer
dizer que ela não tenha grupo. O tipo pedido que não está disponível para a organização vem em
`unavailable_link_types`, e os `limits` não falam da fonte dele. Pessoa e quem a rede não conhece saem
`not_available`.

### Ficha de crédito (`credit`, linha 754)

Os fatos públicos de uma empresa que um FIDC ou uma plataforma de duplicatas consulta sobre o cedente
e o sacado: a situação na Receita e a situação especial, os fatos relevantes dos últimos 12 meses na
CVM e a presença como cedente nos FIDCs (informe mensal da CVM). Cada fato sai no envelope, com a fonte
e o dia em que ficou público; nada publicado depois de `known_at` entra. O contrato precisa do conjunto
`credit` com a finalidade `credito` (um contrato de análise não abre a ficha).

Ficam fora, na leitura mais estreita: os resultados das regras de elegibilidade (sobre quem emite valor
mobiliário seria opinião de crédito, que é de agência registrada: Resolução CVM 9/2020, art. 1º),
rating, insolvência, o SCR (só agregado) e as fontes cujas marcas não deixam redistribuir. Pessoa
natural (MEI, empresário individual) e CNPJ que a rede não conhece saem `not_available`.

### Setor (`sectors`, linha 781)

O molde D de `docs/padrao-de-analise.md` para os setores do relatório (`src/relatorio_setor.py`:
`eletricas`, `bancos`, `seguros`, `saude_suplementar`, `telecom`): por série de agência, o total do
mercado, CR4, HHI, a faixa e a variação do HHI por ano; a fatia de cada companhia aberta; e a lista das
companhias, com o motivo de estarem no setor. É a exceção ao "só pela porta da base": a rota lê a seção
`setor` da ficha da noite (`src.dossie.secao_do_setor`), onde a conta sobre várias tabelas já está feita e
conferida (a mesma do app e do PDF). Cada coluna passa pelo portão com a fonte de onde saiu: a concentração
é **agregado** de mercado (a única linha de direito `agregado` da API) e a fatia é fato de companhia, as
duas pela fonte da agência; a lista, pela CVM. A prontidão confere também a ligação às companhias
(`empresa_serie`, `cadastro_das_companhias`).

A base não guarda quando a agência publicou cada mês, então `published_at` é o dia da noite e `observed_at`
sai vazio; só existe a noite mais nova, e um `known_at` antes dela sai `not_available`. Linha sem CNPJ de
14 dígitos não sai: nenhuma pessoa física. O lado a lado por entidade e o mercado de energia (CCEE, ONS)
ficam fora desta versão.

## Mudou uma rota da `/data/v1`?

```powershell
.venv\Scripts\python -m scripts.gerar_openapi_data
```

Revise o diff de `docs/api/openapi-data-v1.json` no PR: é o que a CLI (`cli/`) e os clientes leem.
O teste (`tests/test_api_externa_por_cnpj_contrato.py`) falha se o arquivo ficar velho, se um código
de erro do código não estiver no contrato, ou se uma leitura por CNPJ não aceitar `known_at`.
