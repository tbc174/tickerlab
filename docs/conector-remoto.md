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

1. **Registro (DCR, RFC 7591).** Só os endereços de volta do Claude (`https://claude.ai/api/mcp/auth_callback`
   e `https://claude.com/api/mcp/auth_callback`, que a Anthropic avisa que pode passar a usar) e do ChatGPT (`https://chatgpt.com/connector_platform_oauth_redirect` e
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
- **API sem resposta não é chave revogada.** Só 401 e 403 do `/catalog` dizem que a chave não vale.
  Limite de pedidos da organização (429), erro da API (5xx) ou a API desligada (404) são falha passageira:
  o `/mcp` responde 503 com `Retry-After: 30` (um 401 faria a IA pedir a chave de novo), a renovação
  responde `invalid_request` sem gastar o token e a página diz que o TickerLab não respondeu, sem contar
  no limite por IP.
- **Sem o `iss` na volta (RFC 9207).** O ChatGPT usa então o endereço `connector/oauth/<id>`, que está na
  lista fechada.

### Riscos aceitos (revisão cruzada do PR 2)

- **Cadeia de renovação sem prazo final.** Cada renovação emite outro token de 30 dias; quem capturar um
  token de renovação e usá-lo antes do dono segue renovando, e o conector não derruba a família ao ver o
  reuso (não guarda estado). O corte é revogar a chave do analista na API.
- **Ligar o assistente de outra pessoa.** Alguém pode começar a ligação no próprio Claude ou ChatGPT e
  mandar o endereço da página `/autorizar` ao analista. Se ele colar a chave, a conta de quem mandou passa a
  consultar com a chave dele. A chave não vaza e o destino é sempre uma das duas IAs, mas a única defesa
  é o aviso da página ("Só continue se foi você que começou esta ligação agora") e o guia do analista.

## Limite por IP atrás do túnel

A página `/autorizar` aceita no máximo **20 falhas por IP a cada 15 minutos** (chave errada, CSRF errado,
pedido mexido); passou disso, 429 até a janela andar. Acerto não conta: um escritório inteiro entra pelo
mesmo IP. O IPv6 conta pela faixa /64 (um provedor entrega a faixa inteira a cada cliente), e o IPv4
escrito como IPv6 conta como IPv4.

O conector só é alcançado pelo túnel. A porta 8010 fica só no `127.0.0.1` do VPS, e o IP de quem chamou
vem no cabeçalho `CF-Connecting-IP`, que **só vale quando o pedido chega de uma rede de confiança**
(`TICKERLAB_MCP_PROXIES_CONFIAVEIS`; padrão `127.0.0.0/8`, `::1/128` e `172.16.0.0/12`, a rede do
Compose). Vindo de outro lugar, o cabeçalho é ignorado e conta o endereço da conexão (há teste).

## Variáveis de ambiente

| Variável | Padrão | Para quê |
|---|---|---|
| `TICKERLAB_MCP_CHAVE_DOS_TOKENS` | (nenhum) | **Segredo.** 32 bytes em base64url que selam os tokens. Sem ela, o conector cria uma chave só do processo e avisa no log (reiniciar obriga todos a entrar de novo). Em produção ela é obrigatória. |
| `TICKERLAB_MCP_EXIGIR_CHAVE` | (vazio) | `1` no compose de produção: sem a chave do servidor, o conector não sobe. |
| `TICKERLAB_MCP_API_URL` | `http://tickerlab-api:8000` | Onde está a API externa (rede do Compose). |
| `TICKERLAB_MCP_URL_PUBLICA` | `https://mcp.tickerlab.com.br` | O endereço público do conector; também é o `issuer` do OAuth. |
| `TICKERLAB_MCP_HOSTS` | (vazio) | Hosts extras aceitos além do público (o resto recebe 421). |
| `TICKERLAB_MCP_PROXIES_CONFIAVEIS` | `127.0.0.0/8,::1/128,172.16.0.0/12` | Redes de onde o `CF-Connecting-IP` vale. |
| `TICKERLAB_MCP_ESCUTA` / `TICKERLAB_MCP_PORTA` | `127.0.0.1` / `8010` | Onde o uvicorn escuta. |

A chave do servidor nunca aparece em `repr`, log ou mensagem de erro (há teste), nem neste repositório.

## As ferramentas e a CLI

Cada comando de leitura da CLI `tickerlab` tem uma ferramenta no conector, e a ferramenta faz à API os
mesmos pedidos que o comando faz: mesma rota e mesmos parâmetros, portanto a mesma regra. O teste
`tests/test_conector_remoto_paridade_cli.py` falha quando um comando novo da CLI não tem ferramenta. Nesse
caso, ou se cria a ferramenta ou se escreve o motivo em `SEM_FERRAMENTA`, como já está para `login`,
`logout` e `instrucoes`, que não leem a base.

| CLI | Conector |
|---|---|
| `prospectar` | `buscar_empresas` (filtros, `limite` e `cursor`) |
| `empresa` | `ficha_da_empresa` |
| `comparaveis` | `comparaveis` |
| `demonstracoes` | `demonstracoes` |
| `eventos` | `eventos` (tipos, `limite` e `cursor`) |
| `fundo` | `fundo` |
| `setor` | `setores` e `setor` |
| `catalogo` e `consumo` | `o_que_posso_ver` |
| `vinculos` | `vinculos` (tipos, `profundidade` de 1 a 3 e a data) |

Ferramenta que chega antes do comando da CLI fica em `SO_NO_CONECTOR` no teste de paridade, com o motivo;
quando o comando entra, ela passa a `FERRAMENTAS_DO_COMANDO` e ganha um caso. Hoje está lá
`compradores_do_setor`, que chama `/buyers` (conjunto `buyers`, linha 810): `cnae` (classe ou subclasse),
`uf`, `anos` de 1 a 10, `limite` de 1 a 50 e a data.

O comparar de duas a cinco empresas ainda não tem rota na API externa. Entra pelo mesmo caminho: rota na
API, comando na CLI e ferramenta aqui, com a paridade cobrando.

## Prompts

Além das ferramentas, o conector oferece cinco prompts (`conector_remoto/prompts.py`, linha 901), um para
cada fluxo da casa de M&A: `triagem_de_cnpj`, `alvos_no_setor`, `compradores_no_setor`,
`comparaveis_da_empresa` e `dossie_da_empresa`. O analista escolhe o prompt no cliente e preenche os
argumentos. O prompt só monta o pedido, que leva às ferramentas, e não lê a base nem a API: o dado continua
saindo só pelas ferramentas, com o portão por conjunto e o filtro de pessoa delas.

- **Argumentos:** são conferidos antes de entrar no pedido (CNPJ, CNAE, UF, data e anos). Argumento fora da
  forma vira erro de parâmetro (`-32602`) com uma frase nossa, que não repete o que foi digitado.
- **Dossiê:** usa a mesma orientação das instruções (`ORIENTACAO_DO_DOSSIE`), um lugar só para ela.
- **Fecho comum:** todo prompt termina com o mesmo pedido de fonte e data, de lacunas à parte e de nenhum
  dado de pessoa física.
- **Testes:** o teste confere que cada prompt cita só ferramentas que existem.
- **Clientes:** o Claude aceita prompts (documentação de conectores, lida em 13/11/2026). Se o ChatGPT os
  mostra não está confirmado, e nada do roteiro depende deles.

## Em produção

O serviço `tickerlab-mcp` fica num arquivo à parte, `compose.conector.yaml`, que o `docker compose up`
comum não lê. O deploy automático sobe primeiro o app e a API só com o `compose.yaml`, e só eles decidem
se a versão fica. Depois, num passo à parte, sobe o conector, e só quando o `.env.mcp` existe. Assim o merge
não sobe contêiner nenhum, e depois do primeiro `up` o conector acompanha cada versão. Se ele não subir,
fica uma linha no log do deploy, mas o app e a API não são revertidos (há teste em `tests/test_estado_do_ci.py`). Ele usa a mesma
imagem do app, com outro comando (`python -m conector_remoto`). Ele não monta volume nenhum (nem acervo, nem sala, nem cache), não lê o
`.env` do app e roda com o disco só de leitura, sem poderes extras (`cap_drop: ALL`). A porta 8010 fica
só no `127.0.0.1` do VPS, e o `CF-Connecting-IP` só vale vindo do gateway da rede do Docker
(`172.18.0.1/32`). Há teste que confere essas travas (`tests/test_publicacao.py`), e o CI sobe o
contêiner para conferir o 401, o 421 e o 403.

O único segredo fica no `.env.mcp` (permissão 600, fora do Git e da imagem), gravado por
`python3 scripts/gravar_chave_do_conector.py`. O script cria a chave sem mostrá-la e não troca uma chave
que já existe sem `--trocar`.

O guia para quem usa o conector está em `docs/guia-do-analista-conector.md`.

## Medida de uso

Cada chamada de ferramenta grava uma linha de JSON (`conector_remoto/uso.py`) com estes campos:

- `evento: ferramenta_chamada`, a hora e a duração;
- o resultado: `ok`, `erro` ou `recusada`;
- a ferramenta: só um nome registrado; nome inventado sai como `desconhecida`;
- a chave: só o id público, `tld_...`.

A linha nunca leva os argumentos, a resposta nem a mensagem de erro, porque a mensagem de validação repete o
que foi digitado. Há teste para isso. A lista de ferramentas não conta.

Para contar por ferramenta no VPS:

```bash
docker logs tickerlab-mcp 2>&1 | grep ferramenta_chamada
```

## Incidente: a chave do servidor vazou

Quem tem a chave do servidor e um token capturado lê a chave do analista dentro dele. Então:

1. **Troque a chave do servidor.** No VPS: `python3 scripts/gravar_chave_do_conector.py --trocar` (a
   chave nova vai para o `.env.mcp` sem aparecer na tela nem no log) e `docker compose -f compose.yaml
   -f compose.conector.yaml up -d tickerlab-mcp`. Todos os tokens e registros antigos
   deixam de abrir: cada analista entra de novo pela página `/autorizar`.
2. **Revogue as chaves das pessoas** que usaram o conector desde a data provável do vazamento e entregue
   chaves novas. Sem isso, quem copiou um token antes da troca ainda teria a chave de dentro dele.
3. **Confira o uso** das chaves revogadas no registro de uso da API, no período, e anote o incidente.

Se vazou a chave **de um analista** (e não a do servidor), basta revogar a chave dele na API: o token do
conector para de funcionar na chamada seguinte.

## Pessoa física

O filtro de pessoa (`pessoa.py`) recusa a resposta inteira quando um campo parece dado de pessoa física. Os
testes, os exemplos e este guia não usam dado de pessoa real nem CNPJ de empresa real escolhido à mão.
