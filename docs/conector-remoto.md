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
   na hora) e troca os dois tokens. O token de renovação usado devolve os **mesmos** tokens por 120 s
   (`JANELA_DE_REUSO_S`) e depois não serve mais; se a API não responde, a renovação sai sem a conferência
   (ver "Renovação que não derruba", abaixo).

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
  sai sem a conferência (abaixo) e a página diz que o TickerLab não respondeu, sem contar no limite por IP.
- **Renovação que não derruba (18/11/2026, queda de 17/11).** A renovação respondia 400 em dois casos que não
  eram culpa do analista, e a IA derrubava a conexão (o cliente oficial do SDK do MCP apaga os tokens em
  qualquer resposta da renovação que não seja 200; o SDK do servidor só sabe responder 400 a um
  `TokenError`, então um 503 não está ao alcance e não ajudaria): (1) **API sem resposta** ao conferir a
  chave: agora os tokens novos saem sem a conferência, com um aviso no log com o id público da chave.
  Chave revogada não ganha nada com isso: cada chamada do `/mcp` confere a chave na API, e a renovação
  seguinte, com a API de volta, responde `invalid_grant`. (2) **Mesmo token de renovação duas vezes**
  (resposta perdida no caminho, ou duas conversas renovando juntas): nos 120 s seguintes à troca, o mesmo
  token devolve os mesmos tokens já emitidos (quem chega durante a troca espera por ela; a API é conferida
  uma vez só). Depois da janela, `invalid_grant`. A janela guarda na memória a resposta já emitida (a
  chave vai cifrada dentro dos tokens, como sempre), presa ao cliente que trocou. Falha inesperada no meio
  da troca não gasta o token, e quem esperava por ela refaz a troca em vez de receber erro.
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

## Uma base, três portas

Cada consulta do TickerLab Data e o nome dela em cada porta (o conector MCP, a CLI `tickerlab` e a API `/data/v1`), com o motivo quando uma porta não a oferece. A tabela é gerada da lista única (`conector_remoto/consultas_das_portas.py`) e um teste confere que está em dia; pessoa física fica fora dela.

<!-- gerado: lista das portas (python -m scripts.exportar_conteudo); não edite à mão -->
| Consulta | Conector | CLI | API (`/data/v1`) |
|---|---|---|---|
| **Buscar empresas**: achar empresas por atividade (CNAE), UF, município, porte ou idade no cadastro da Receita; só empresa, sem sócio nem contato | `buscar_empresas` | `tickerlab prospectar` | `GET /companies` |
| **Ficha da empresa**: a triagem de um CNPJ antes da reunião: o cadastro na Receita e, se for companhia aberta, cada DFP e ITR com o prazo da CVM | `ficha_da_empresa` | `tickerlab empresa` | `GET /companies/{cnpj}/profile`, `GET /companies/{cnpj}` |
| **Análise completa**: cada bloco que a chave vê numa resposta (cadastro, sócios pessoa jurídica, vínculos, eventos, crédito, ativos, comparáveis e as bases das agências), com a frase do topo, a linha do tempo e o que não foi achado | `analise_completa` | `tickerlab analise` | `GET /companies/{cnpj}/analysis` |
| **Comparáveis**: as companhias abertas do mesmo grupo de setores, com os números do último DFP e a mediana de cada razão | `comparaveis` | `tickerlab comparaveis` | `GET /companies/{cnpj}/comparables` |
| **Demonstrações**: a DFP e o ITR da companhia aberta, conta a conta; empresa fechada não tem, e a base não estima o faturamento dela | `demonstracoes` | `tickerlab demonstracoes` | `GET /companies/{cnpj}/financials` |
| **Eventos**: o que a companhia aberta entregou à CVM (fato relevante, comunicado, assembleia) e as trocas de auditor, do mais novo ao mais velho | `eventos` | `tickerlab eventos` | `GET /companies/{cnpj}/events` |
| **Vínculos**: as controladas, coligadas e participadas da empresa e quem a auditava, como eram num dia, pelo FRE e pelo FCA da CVM; só companhia aberta informa, uma vez por ano | `vinculos` | `tickerlab vinculos` | `GET /companies/{cnpj}/links` |
| **Ativos físicos**: os contratos de exploração e produção de petróleo e gás da ANP e, quando a chave os vê, as barragens e os royalties de mineração da ANM | `ativos` | `tickerlab ativos` | `GET /companies/{cnpj}/assets` |
| **Registros nas agências reguladoras**: os indicadores da ANEEL e o IDSS da ANS e, com as fontes ampliadas no contrato, Anatel, ANM, ANP e PAT, quando a chave os vê; cada valor com a fonte e o dia em que ficou público, sem abrir a análise inteira | `registros_nas_agencias` | `tickerlab registros` | `GET /companies/{cnpj}/registrations` |
| **Compras públicas**: com o conjunto de compras públicas no contrato, o cadastro de fornecedor no SICAF e as compras de saúde do BPS em que a empresa é a fornecedora, quando a chave os vê; cada valor com a fonte e o dia em que ficou público, sem abrir a análise inteira | `compras_publicas` | `tickerlab compras` | `GET /companies/{cnpj}/public-procurement` |
| **Quem já se mexeu no setor**: quem entrou como sócio, fundo sócio ou controla empresa do setor nos últimos anos; só pessoa jurídica, e movimento passado não é intenção de compra | `compradores_do_setor` | `tickerlab compradores` | `GET /buyers` |
| **Fundo**: o raio-x de um fundo na CVM: cadastro, taxas e carteira | `fundo` | `tickerlab fundo` | `GET /funds/{cnpj}` |
| **Setores**: os setores acompanhados e, de cada um, o tamanho do mercado, a concentração (CR4 e HHI) e a fatia de cada companhia aberta | `setores`, `setor` | `tickerlab setor` | `GET /sectors`, `GET /sectors/{key}` |
| **Novidades da pesquisa**: as fontes públicas de órgão que a pesquisa provou na semana, com o trecho literal e o hash do original | `novidades` | `tickerlab novidades` | `GET /research/news` |
| **O que posso ver**: o que a sua chave libera (conjuntos, campos, fontes e licenças) e o consumo do mês | `o_que_posso_ver` | `tickerlab catalogo`, `tickerlab consumo` | `GET /catalog`, `GET /usage` |
| **De onde vem um conjunto ou um campo**: a fonte, a licença e a atribuição de cada campo que a sua chave vê, e quais campos são de piloto, para saber de onde veio um número antes de citá-lo; não traz dado de empresa | `de_onde_vem` | `tickerlab de-onde-vem` | não tem (lê o `GET /catalog` (a consulta `catalogo`); não é rota própria) |
| **Fatos de crédito de uma empresa**: situação na Receita, fatos relevantes dos últimos 12 meses e a cessão de recebíveis a FIDC, cada fato com a fonte e o dia em que ficou público; não é rating, nota nem elegibilidade, não traz o SCR individual e só aparece para a chave com o conjunto de crédito | `credito_da_empresa` | `tickerlab credito` | `GET /credit/{cnpj}` |
| **O que mudou numa empresa desde um dia**: o cadastro, os vínculos e os eventos como a base os sabia no dia escolhido contra como os sabe hoje, só a diferença, cada item com a fonte e o dia em que ficou público; serve para retomar uma empresa já analisada e mostra só os blocos que a sua chave vê | `o_que_mudou` | não tem (linha 980, onda 1: o comando da CLI vem depois, em PR próprio (fila.md)) | não tem (composta no conector: compara o retrato de hoje com o de `desde` (cadastro, vínculos e eventos)) |
| **Fichas de 2 a 5 empresas lado a lado**: o cadastro e as entregas à CVM de cada empresa em colunas; o que a base não tem vem como «não disponível», nunca como zero, e não há nota nem ordenação das empresas | `comparar_empresas` | não tem (linha 980, onda 1: o comando da CLI vem depois, em PR próprio (fila.md)) | não tem (composta no conector: as fichas de 2 a 5 CNPJs (para sistema, há o lote `POST /companies/batch`)) |
| **Acompanhar uma lista de empresas**: o que mudou em 2 a 5 empresas desde um dia, numa chamada: cadastro, vínculos e eventos, só a diferença, com a fonte de cada item; a empresa sem mudança aparece numa linha só | `acompanhar_empresas` | não tem (linha 980, onda 2: composta no conector; a CLI não tem o comando) | não tem (composta no conector: o `o_que_mudou` de cada empresa da lista) |
| **Dossiê**: perfil, eventos, vínculos e comparáveis do CNPJ numa saída só | não tem (Diretoria 11/11: no conector a IA compõe o dossiê pelas instruções do servidor (#1050)) | `tickerlab dossie` | não tem (composto na CLI com quatro rotas: a ficha, os eventos, os vínculos e os comparáveis) |
| **Deck**: o deck (.pptx) da empresa ou do setor, com a fonte e a data de cada tabela | não tem (grava um arquivo .pptx; o conector devolve texto, não arquivo (Diretoria 12/11, linha 782)) | `tickerlab deck` | `GET /companies/{cnpj}/deck`, `GET /sectors/{key}/deck` |
| **Lotes**: até 100 CNPJs num pedido, para sistema | não tem (lote de até 100 CNPJs é para sistema; na conversa, `comparar_empresas` põe 2 a 5 lado a lado) | não tem (lote é para sistema; a CLI pede um CNPJ por vez) | `POST /companies/batch`, `POST /funds/batch`, `POST /credit/batch` |
| **Chave**: guardar e apagar a chave da API no PC | não tem (a chave entra pela página /autorizar do OAuth; quem corta o acesso é revogar a chave) | `tickerlab login`, `tickerlab logout` | não tem (não leem a base: guardam e apagam a chave no PC) |
| **Instruções do agente**: o AGENTS.md e a skill que ensinam a IA do PC a usar a CLI | não tem (no conector, a descrição de cada ferramenta ensina a IA a chamá-la) | `tickerlab instrucoes` | não tem (não lê a base: ensina a IA do PC a chamar a CLI) |
<!-- fim da lista das portas -->

## As ferramentas e a CLI

Cada comando de leitura da CLI `tickerlab` tem uma ferramenta no conector, e a ferramenta faz à API os
mesmos pedidos que o comando faz: mesma rota e mesmos parâmetros, portanto a mesma regra. O teste
`tests/test_conector_remoto_paridade_cli.py` falha quando um comando novo da CLI não tem ferramenta. Nesse
caso, ou se cria a ferramenta ou se escreve o motivo em `SEM_FERRAMENTA`, como já está para `login`,
`logout` e `instrucoes`, que não leem a base, `deck`, que grava um arquivo, e `dossie`, que a IA compõe
com as ferramentas que existem.

| CLI | Conector |
|---|---|
| `prospectar` | `buscar_empresas` (filtros, `limite` e `cursor`) |
| `empresa` | `ficha_da_empresa` (as 8 entregas de DFP e ITR mais novas; `limite_de_entregas`, de 1 a 100, pede mais; o corte vai em `truncated` e em `limits`) |
| `analise` | `analise_completa` (a data, `blocos` e `limite`; cada bloco que a chave vê numa resposta, cortada em até ~50 mil caracteres, repartidos entre as listas de todos os blocos, com `truncated` e o que ficou de fora em `limits`; o bloco que a API deu como `timed_out` ganha em `limits` o aviso de pedir de novo, com a ferramenta própria do bloco quando existe; inclusive os das tabelas ligadas pelo CNPJ do registro `src/api_externa/tabelas_por_cnpj.py` (regulados, balanço no BC, administradora de FII e, com o conjunto `integrity` no contrato, sanções da CGU, embargos do IBAMA e cadastro de empregadores do MTE, só pessoa jurídica), com a frase do topo, a linha do tempo, as leituras e o que não foi achado; um pedido por bloco na quota; com `pessoa_no_conector` e sem a data, um segundo bloco com a resposta de `socios_e_donos`, que é mais um pedido na quota e some se a API negar ou a tranca recusar) |
| `comparaveis` | `comparaveis` (a data e `limite` de 1 a 50 pares, padrão 10; o corte é no conector, na ordem da API, e as medianas seguem sobre todos os pares) |
| `demonstracoes` | `demonstracoes` (um período, a versão mais nova de cada conta e o consolidado onde houver; `demonstrativo`, `visao` e `conta` escolhem o recorte; o que não coube vai em `truncated` e em `limits`) |
| `eventos` | `eventos` (tipos, `limite` e `cursor`) |
| `fundo` | `fundo` |
| `setor` | `setores` e `setor` |
| `catalogo` e `consumo` | `o_que_posso_ver` |
| `vinculos` | `vinculos` (tipos, `profundidade` de 1 a 3 e a data) |
| `ativos` | `ativos` (a data; conjunto `assets`: contratos de E&P da ANP e, quando a chave os vê, barragens e royalties de mineração da ANM; `tipo_de_ativo`, `uf`, `somente_operador` e `limite`, filtros do conector que não vão à API; o que passa do teto da conversa fica de fora, com `truncated` e a contagem em `limits`) |
| `compradores` | `compradores_do_setor` (`cnae`, `uf`, `anos` de 1 a 10, `limite` de 1 a 50 e a data) |
| `novidades` | `novidades` (`dias` de 1 a 30; lista vazia vem com `limits` dizendo se o arquivo da pesquisa não chegou ao servidor ou a data da última geração) |

Ferramentas do analista, que só compõem o que a API já devolve (linha 980, onda 1; código em
`conector_remoto/ferramentas_do_analista.py`, que não abre rota nem direito novo):

| Ferramenta | O que faz | Conjunto que a chave precisa |
|---|---|---|
| `credito_da_empresa` | Os fatos de crédito da rota `/credit` (situação na Receita, fatos relevantes e cessão a FIDC), cada um com fonte e dia em que ficou público; `como_era_em` vai como `known_at`. Não traz rating, elegibilidade como cedente ou sacado, SCR individual nem pessoa. Ainda sem comando na CLI (está em `SO_NO_CONECTOR`). | `credit` |
| `o_que_mudou` | A diferença entre o que a base sabia em `desde` e o que sabe hoje, em até três blocos: cadastro (com as entregas de DFP e ITR), vínculos e eventos, cada um com o antes e o depois (ou só o que entrou ou saiu), a fonte e o dia em que ficou público. Os seis pedidos correm juntos; o lado antigo vai com `known_at = desde` e, mesmo que a API deixasse passar, a ferramenta tira dele o que ficou público depois de `desde`. Bloco que a chave não vê ou a API não serve vem em `not_consulted`; `before_not_available`, `after_not_available` e `partial` avisam o que faltou. Com `partial` (página de 100 cheia) a ferramenta não lista o que saiu, porque o que ficou fora da página não saiu da base. O mês do retrato da Receita não conta como mudança; a entrega de DFP/ITR se identifica por documento e período, e o vínculo por tipo, pontas e começo. Erro que não é 404 em qualquer bloco derruba a resposta inteira. `blocos` (cadastro, vinculos, eventos) pede só alguns (os outros vêm em `not_consulted` com `not_requested`) e `limite` (1 a 200) limita as mudanças por lista; o que passa do teto da conversa fica de fora, com `truncated`, `changes_shown` (`changes_found` continua a conta inteira) e a contagem em `limits`. A trava de pessoa lê cada resposta crua, mas o teto de tamanho só vale para o que vai à IA. Não traz mudança ainda não publicada na base nem pessoa. Ainda sem comando na CLI (está em `SO_NO_CONECTOR`). | `profiles` ou `companies`, `links`, `events` (qualquer um; cada bloco pede o seu) |
| `comparar_empresas` | A ficha de 2 a 5 empresas lado a lado: uma linha por campo do cadastro na Receita, uma coluna por empresa (a chave é o CNPJ), mais as 8 entregas de DFP e ITR mais novas de cada uma (`filings_cut` diz quantas a base tem; lista que a chave não consultou vem como `não disponível`, e o que faltou vai em `unavailable_filings` e `unavailable_registration_fields`), cada valor com fonte e dia em que ficou público. O que a base não tem de uma empresa vem como `não disponível`, nunca como zero; a empresa que a base não serve vem em `not_available`. Os pedidos correm juntos. Mais de 5, menos de 2, CNPJ repetido ou CPF dão mensagem clara sem chamar a API; erro que não é 404 em qualquer empresa derruba a resposta. Não traz pessoa, nota nem ordenação. Ainda sem comando na CLI (está em `SO_NO_CONECTOR`). | `profiles` ou `companies` |
| `de_onde_vem` | De onde vem um conjunto ou um campo que a chave vê: a fonte de cada campo, a licença e a atribuição dessa fonte, a finalidade do conjunto e a marca de piloto, com o aviso uma vez só e a lista dos campos de piloto (`pilot_fields`). Lê só o `/catalog` (o mesmo de `o_que_posso_ver`), sem dado de empresa. Conjunto ou campo que a chave não vê dá a mesma mensagem de quem não existe. O catálogo não traz o significado de cada campo nem o dia do retrato; a resposta diz isso em `limits`. Mais de 50 achados vêm cortados (`truncated`). Ainda sem comando na CLI (está em `SO_NO_CONECTOR`). | nenhum (vale para toda chave) |

Resposta acima do teto (`conector_remoto/saida.py`, `TETO_DE_CARACTERES`) vira erro com o jeito de pedir menos que aquela ferramenta tem (`DICAS_DE_RESPOSTA_GRANDE` em `conector_remoto/ferramentas.py`); a que não tem parâmetro para isso diz que o pedido não cabe. Um teste confere que a frase só cita parâmetro da própria ferramenta.

**Próximo passo no fim da lista** (linha 984, item 2; `conector_remoto/proximo_passo.py`). A resposta de cada
ferramenta de lista (`buscar_empresas`, `compradores_do_setor`, `comparaveis`, `eventos`, `vinculos`,
`setores`) traz o campo `next_step`: uma frase fixa que diz qual ferramenta chamar a seguir; com a lista vazia,
diz o que ficou de fora do pedido, como alargá-lo e que não se estima. O texto não vem da API, não repete o
que o analista digitou e só cita ferramentas e parâmetros que existem (um teste confere, e confere também que
não há preço, promessa, recomendação nem palavra de pessoa). O rodapé é só do conector: o chat do app usa as
mesmas ferramentas, mas não tem todas as que o texto cita, então `registrar_ferramentas` o desliga por
padrão. O erro "não disponível" também diz o que fazer (`o_que_posso_ver`) e pede para não estimar.

Ferramenta que chega antes do comando da CLI fica em `SO_NO_CONECTOR` no teste de paridade, com o motivo;
quando o comando entra, ela passa a `FERRAMENTAS_DO_COMANDO` e ganha um caso. Hoje a lista tem `socios_e_donos`, `credito_da_empresa`, `o_que_mudou`, `comparar_empresas` e `de_onde_vem`.

Cada ferramenta tem um título (`title`, em `TITULOS_DAS_FERRAMENTAS`), que é o que o analista vê no
cliente ao lado da chamada: curto, em português e sem promessa. O nome técnico (`buscar_empresas`) não muda,
porque é o que as instruções, os prompts e o ensaio citam. Ferramenta nova precisa de título: o teste do
servidor falha sem ele.

A descrição de cada ferramenta (a docstring) segue a regra do diretório de conectores do Claude: diz o que a
ferramenta devolve e nunca instrui o modelo. Tem sempre as mesmas partes: o que volta, "Serve para" (a
pergunta que ela responde), "Fonte:" e "Não traz:" (faturamento de empresa fechada, pessoa física e o que mais
faltar). O que orienta o modelo (como citar, o dossiê, o mapa pergunta → ferramenta) fica nas `INSTRUCOES` do
servidor. O teste do servidor cobra as partes e recusa imperativo, "você", nome de IA, preço e promessa, na
descrição e nos argumentos.

O comparar de duas a cinco empresas ainda não tem rota na API externa. Entra pelo mesmo caminho: rota na
API, comando na CLI e ferramenta aqui, com a paridade cobrando.

## Prompts

Além das ferramentas, o conector oferece oito prompts (`conector_remoto/prompts.py`, linhas 901 e 980), um
para cada fluxo da casa de M&A: `triagem_de_cnpj`, `alvos_no_setor`, `compradores_no_setor`,
`comparaveis_da_empresa` e `dossie_da_empresa`, mais os três da linha 980: `preparar_reuniao` (uma página
com quem é a empresa, o que aconteceu e cinco perguntas, cada uma ligada a um fato da base),
`perfil_sem_nome` (o perfil para circular sem razão social, CNPJ, município, UF nem nada que identifique; só
consulta a `ficha_da_empresa`) e `lista_longa_de_compradores` (todos os que a base traz do setor, até 50,
sem corte). Nenhum pede faturamento estimado nem recomendação. O analista escolhe o prompt no cliente e preenche os
argumentos. O prompt só monta o pedido, que leva às ferramentas, e não lê a base nem a API: o dado continua
saindo só pelas ferramentas, com o portão por conjunto e o filtro de pessoa delas.

- **Argumentos:** são conferidos antes de entrar no pedido (CNPJ, CNAE, UF, data e anos). Argumento fora da
  forma vira erro de parâmetro (`-32602`) com uma frase nossa, que não repete o que foi digitado.
- **Dossiê:** usa a mesma orientação das instruções (`ORIENTACAO_DO_DOSSIE`), um lugar só para ela.
- **Fecho comum:** todo prompt termina com o mesmo pedido de fonte e data, de lacunas à parte e de nenhum
  dado de pessoa física.
  A exceção é `perfil_sem_nome`, cujo fecho (`FECHO_ANONIMO`) também proíbe o nome de sócio, porque nome de
  pessoa identifica a empresa.
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

O filtro de pessoa (`pessoa.py`) recusa a resposta inteira quando um campo parece dado de pessoa física. A
exceção é `socios_e_donos` (e o segundo bloco da `analise_completa`), que aparece só para a chave de uma
organização com `pessoa_no_conector`, desligada por padrão, e passa pela tranca própria de
`socios_e_donos.py`: só nome, qualificação e data de entrada, nunca CPF, menor, endereço ou contato
(política de privacidade, versão 19). Os
testes, os exemplos e este guia não usam dado de pessoa real nem CNPJ de empresa real escolhido à mão.
