# API de leitura (v1)

A interface nova do TickerLab (React, ADR 0048) não calcula nada: ela pede os números à API, que
chama as mesmas funções de `src/` que as telas do Streamlit usam. Assim, o número na tela nova é o
mesmo da tela antiga.

**Estado:** pronta e **desligada** em produção. Ela só responde com `TICKERLAB_API_V1=1` e
`TICKERLAB_GOOGLE_CLIENT_ID` no ambiente; sem isso, toda rota `/api/v1/...` responde 404.

## Onde está cada coisa

| O quê | Onde |
|---|---|
| Rotas | `src/api_v1/rotas.py` |
| Formato das respostas | `src/api_v1/esquemas.py` (Pydantic) |
| Login, chave liga/desliga e limite de pedidos | `src/api_v1/acesso.py` |
| Carregar o ativo (preços, retorno, taxa livre de risco) | `src/api_v1/contexto.py` |
| O que cada página mostra | `src/analises.py` |
| Contrato de cada página (entradas, rota e resposta) | `Pagina.contrato` em `src/paginas.py` |
| Esquema publicado (OpenAPI) | `docs/api/openapi-v1.json` |

## Login

A tela faz o login com o Google no navegador e manda o *ID token* em todo pedido:

```
Authorization: Bearer <id token do Google>
```

A API confere a assinatura (RS256, chaves públicas do Google), o destino (`aud` = o client ID do
TickerLab), o emissor, a validade e o e-mail verificado. A conta precisa já existir (o primeiro login
é pelo app) e ter aceitado os termos atuais.

| Resposta | Quando |
|---|---|
| 401 | sem token, token inválido ou conta que nunca entrou no app |
| 403 | conta sem os termos atuais |
| 404 | API desligada, ou ativo sem dados |
| 422 | pedido fora dos limites (período, janela, custo, parâmetros) ou período curto demais |
| 429 | mais de 60 pedidos por minuto da mesma conta |
| 503 | login não configurado, ou o Google fora do ar |

## Rotas

| Página | Rota | Resposta |
|---|---|---|
| (antes do login) | `GET /api/v1/configuracao` (sem token) | `ConfiguracaoV1`: o client ID do Google |
| (a conta) | `GET /api/v1/eu` | `EuV1`: plano e limites, sem e-mail |
| Visão geral | `GET /api/v1/visao-geral?ticker=PETR4&periodo=2y` | `VisaoGeralV1` |
| Risco | `GET /api/v1/risco?ticker=PETR4&janela=20` | `RiscoDoAtivoV1` |
| Retorno mensal | `GET /api/v1/retorno-mensal?ticker=PETR4` | `RetornoMensalDoAtivoV1` |
| Comparar ativos | `GET /api/v1/comparacao?ticker=PETR4&com=VALE3&com=AAPL` | `ComparacaoDoAtivoV1` |
| Backtest | `POST /api/v1/backtest` (corpo `PedidoDeBacktestV1`) | `BacktestDoAtivoV1` |

Sem `taxa`, a taxa livre de risco é o CDI do período (zero se o Banco Central não responder), como
na tela. Toda resposta traz `ativo` com o período real, a origem dos preços (`atual`,
`cache_antigo` ou `exemplo`) e a taxa usada, para a tela mostrar os mesmos avisos.

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
