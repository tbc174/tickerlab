# APIs do TickerLab

Duas APIs, no mesmo serviço FastAPI (`src/api.py`):

- **API de leitura (`/api/v1`)**, para o app novo e o site: a conta entra pelo navegador.
- **API externa de dados (`/data/v1`, TickerLab Data)**, para quem integra: a organização entra pela
  chave dela. Ver [a seção dela](#api-externa-de-dados-datav1).

As duas estão **desligadas** em produção.

# API de leitura (v1)

A interface nova do TickerLab (React, ADR 0048) não calcula nada: ela pede os números à API, que
chama as mesmas funções de `src/` que as telas do Streamlit usam. Assim, o número na tela nova é o
mesmo da tela antiga.

**Estado:** pronta e **desligada** em produção. Ela só responde com `TICKERLAB_API_V1=1` e
`TICKERLAB_GOOGLE_CLIENT_ID` no ambiente; sem isso, toda rota `/api/v1/...` responde 404.

## Onde está cada coisa

| O quê | Onde |
|---|---|
| Rotas das páginas do app | `src/api_v1/rotas.py` |
| Conta (login, sair, termos) e entrada por código | `src/api_v1/conta.py`, `src/api_v1/entrada.py`, `src/api_v1/sessao.py` |
| Rotas públicas do site (sem login) | `src/api_v1/ferramentas.py`, `src/api_v1/estudos.py`, `src/api_v1/base_publica.py` |
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
pregão do dia (`GET /api/v1/estudos/pregao/ultimo` e `/{data}`) e os destaques da busca por companhia
(`GET /api/v1/base/destaques`).

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

As duas contam no limite do minuto. Endereços, campos e códigos saem em **inglês**; as tabelas e o
código continuam em português, e a tradução mora num lugar só (`nomes.py`): um nome sem tradução não
sai.

**Já em código, esperando a rota de dado:** cada campo sai com o valor, a fonte, o dia em que ficou
público e o momento em que o TickerLab o viu, mais a licença e a frase de atribuição de cada fonte
usada (`envelope.py`); a consulta em lote aceita até 100 CNPJs por chamada, conta N na quota do mês
e 1 no limite do minuto, e devolve o lote inteiro com 429 se ele não couber (`lote.py`).

| Resposta | Quando |
|---|---|
| 400 | chave na URL (`api_key_in_url`) |
| 401 | chave ausente, errada ou revogada, ou organização suspensa (`invalid_api_key`) |
| 404 | API externa desligada |
| 429 | limite do minuto (`rate_limited`) ou quota do mês (`monthly_quota_exceeded`) |
