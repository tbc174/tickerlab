# Conector remoto (servidor MCP dos analistas)

Guia interno da linha 570. O conector é o servidor MCP que o Claude e o ChatGPT usam para consultar a API
externa (`/data/v1`) em nome de cada analista. Ele fica em `conector_remoto/`, não importa nada de `src/`,
`base/` ou `telas/` (há teste) e não tem banco, acervo nem o `.env` do app: tudo o que ele sabe vem da API,
com a chave do próprio analista.

## Como o analista entra

**Uma chave por pessoa.** Cada analista tem a própria chave `tld_...`, criada pela organização dele na
API. O conector nunca usa uma chave compartilhada: tudo o que a IA consulta conta na chave de quem ligou,
e revogar a chave de uma pessoa corta só ela.

Há duas entradas, que levam ao mesmo lugar:

| Entrada | Quem usa | Como |
|---|---|---|
| OAuth 2.1 (`/register`, `/authorize`, `/autorizar`, `/token`) | Claude (claude.ai e apps) e ChatGPT | O analista cola o endereço `https://<host do conector>/mcp` na IA; a IA abre a página `/autorizar`, onde ele cola a chave. |
| Chave direta (`Authorization: Bearer tld_...`) | Claude Code e o plano B no PC | A chave vai no cabeçalho, sem OAuth. |

### O caminho do OAuth

1. **Registro (DCR, RFC 7591).** Só os endereços de volta do Claude (`https://claude.ai/api/mcp/auth_callback`)
   e do ChatGPT (`https://chatgpt.com/connector_platform_oauth_redirect` e
   `https://chatgpt.com/connector/oauth/<id>`) são aceitos (`oauth.ENDERECOS_DE_VOLTA`). Qualquer outro é
   recusado com `invalid_redirect_uri`, inclusive `localhost`.
2. **`/authorize`.** PKCE S256 obrigatório. O conector responde com a página `/autorizar?pedido=...`; o
   pedido é selado (não dá para mexer) e não leva chave nenhuma. Vale 10 minutos.
3. **`/autorizar`.** Mostra qual IA pede (tirada do endereço de volta, nunca do nome que o cliente mandou)
   e o aviso "Só continue se foi você que começou esta ligação agora". A chave vai só no corpo do POST.
   A página não abre em moldura (`frame-ancestors 'none'`, `X-Frame-Options: DENY`), não fica em cache
   (`no-store`) e confere o CSRF por cookie duplicado (`__Host-`, HttpOnly, Secure, SameSite=Strict).
4. **Código de uso único.** A chave aceita pela API (`/catalog`, sem a memória de 60 s) vira um código
   aleatório de 256 bits que vive **60 s na memória deste processo**. Código reusado, vencido, de outro
   cliente ou com o verificador PKCE errado é recusado (`invalid_grant`); a primeira tentativa gasta o
   código, mesmo errada.
5. **Tokens.** O token de acesso (1 h) e o de renovação (30 dias) são a chave do analista cifrada com a chave
   do servidor (AES-256-GCM, `selo.py`), presos ao cliente e ao recurso `/mcp`. A cada chamada o conector
   abre o token e consulta a API com a chave de dentro.
6. **Renovação.** Confere a chave na API de novo (chave revogada: `invalid_grant`, e o token de acesso cai
   na hora) e troca os dois tokens. O token de renovação usado não serve outra vez.

### Decisões (aceite da Diretoria, 10/11/2026)

- **Registro sem estado.** O `client_id` é um pacote selado com os endereços de volta, o método de entrada
  e as concessões; o segredo do cliente confidencial é derivado do `client_id` com a chave do servidor
  (HMAC). Nada é gravado: reiniciar o conector não derruba registros, e trocar a chave do servidor derruba
  todos. A IA se registra de novo sozinha quando o `client_id` deixa de abrir.
- **Código na memória, processo único.** O contêiner roda um processo do uvicorn. Com mais de um, o código
  emitido num processo não seria achado no outro: se um dia houver réplicas, o código precisa ir para um
  lugar comum (Redis ou banco) antes.
- **Renovação usada só na memória.** A lista de tokens de renovação já usados some quando o processo
  reinicia: depois de um reinício, um token de renovação capturado e já usado voltaria a valer até vencer.
  O risco é pequeno (o token é cifrado e preso ao cliente) e o incidente abaixo corta tudo de uma vez.
- **Sem rota de revogação.** Quem corta o acesso é a revogação da chave na API, que vale na chamada
  seguinte (o catálogo da chave fica no máximo 60 s na memória; nenhum dado sai com a chave revogada,
  porque cada ferramenta chama a API com ela).
- **Sem o `iss` na volta (RFC 9207).** O ChatGPT usa então o endereço `connector/oauth/<id>`, que está na
  lista fechada.

## Limite por IP atrás do túnel

A página `/autorizar` aceita no máximo **20 falhas por IP a cada 15 minutos** (chave errada, CSRF errado,
pedido mexido); passou disso, 429 até a janela andar. Acerto não conta: um escritório inteiro entra pelo
mesmo IP.

O conector só é alcançado pelo túnel. A porta 8010 fica só no `127.0.0.1` do VPS, e o IP de quem chamou
vem no cabeçalho `CF-Connecting-IP`, que **só vale quando o pedido chega de uma rede de confiança**
(`TICKERLAB_MCP_PROXIES_CONFIAVEIS`; padrão `127.0.0.0/8`, `::1/128` e `172.16.0.0/12`, a rede do
Compose). Vindo de outro lugar, o cabeçalho é ignorado e conta o endereço da conexão (há teste).

## Variáveis de ambiente

| Variável | Padrão | Para quê |
|---|---|---|
| `TICKERLAB_MCP_CHAVE_DOS_TOKENS` | (nenhum) | **Segredo.** 32 bytes em base64url que selam os tokens. Sem ela, o conector cria uma chave só do processo e avisa no log (reiniciar obriga todos a entrar de novo). Em produção ela é obrigatória. |
| `TICKERLAB_MCP_API_URL` | `http://tickerlab-api:8000` | Onde está a API externa (rede do Compose). |
| `TICKERLAB_MCP_URL_PUBLICA` | `https://mcp.tickerlab.com.br` | O endereço público do conector; também é o `issuer` do OAuth. |
| `TICKERLAB_MCP_HOSTS` | (vazio) | Hosts extras aceitos além do público (o resto recebe 421). |
| `TICKERLAB_MCP_PROXIES_CONFIAVEIS` | `127.0.0.0/8,::1/128,172.16.0.0/12` | Redes de onde o `CF-Connecting-IP` vale. |
| `TICKERLAB_MCP_ESCUTA` / `TICKERLAB_MCP_PORTA` | `127.0.0.1` / `8010` | Onde o uvicorn escuta. |

A chave do servidor nunca aparece em `repr`, log ou mensagem de erro (há teste), nem neste repositório.

## Incidente: a chave do servidor vazou

Quem tem a chave do servidor e um token capturado lê a chave do analista dentro dele. Então:

1. **Troque a chave do servidor.** Gere uma nova e grave no `.env` do contêiner do conector, sem eco e sem
   log (o roteiro de produção traz o script). Reinicie o contêiner. Todos os tokens e registros antigos
   deixam de abrir: cada analista entra de novo pela página `/autorizar`.
2. **Revogue as chaves das pessoas** que usaram o conector desde a data provável do vazamento e entregue
   chaves novas. Sem isso, quem copiou um token antes da troca ainda teria a chave de dentro dele.
3. **Confira o uso** das chaves revogadas no registro de uso da API, no período, e anote o incidente.

Se vazou a chave **de um analista** (e não a do servidor), basta revogar a chave dele na API: o token do
conector para de funcionar na chamada seguinte.

## Pessoa física

O filtro de pessoa (`pessoa.py`) recusa a resposta inteira quando um campo parece dado de pessoa física. Os
testes, os exemplos e este guia não usam dado de pessoa real nem CNPJ de empresa real escolhido à mão.
