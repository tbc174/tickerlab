# Chat de IA do app (linha 903)

O analista pergunta em português na tela Perguntar (`POST /v1/chat`) e um modelo da Anthropic responde
consultando só as 12 ferramentas do conector, só de leitura e sem pessoa física. O código fica em
`src/chat/` (como funciona, na docstring do `src/chat/__init__.py`) e a rota em `src/api_v1/chat.py`.

## As variáveis (no `.env` do servidor, lido pelo serviço `tickerlab-api`)

| Variável | O que faz | Quem põe |
|---|---|---|
| `ANTHROPIC_API_KEY_CHAT` | A chave do modelo, **só do chat**. Sem ela, o chat responde "não disponível". | O Tiago, pelo script abaixo |
| `TICKERLAB_CHAT` | `1` liga o chat; sem a variável, desligado. | Só o Tiago |
| `TICKERLAB_CHAT_MODELO` | Troca o modelo (padrão em `src/chat/__init__.py`). | Opcional |

**Por que uma chave própria:** a geral, `ANTHROPIC_API_KEY`, é o interruptor de outros usos pagos (os
tópicos das notícias em `src/topicos_modelo.py` e a leitura do boletim em `base/boletim/leitura_ia.py`:
"sem a chave, fica desligado"). Se o chat usasse a geral, pôr a chave dele no servidor ligaria esses usos
sem ninguém pedir e misturaria o gasto. O chat lê só `ANTHROPIC_API_KEY_CHAT` e a entrega ao SDK de forma
explícita (sozinho, o SDK leria a geral); sem ela, o cliente do modelo nem é criado. É o mesmo molde de
`ANTHROPIC_API_KEY_VITRINE` (`scripts/ler_releases.py`) e `ANTHROPIC_API_KEY_MA` (`scripts/extrair_ma.py`).

## Pôr a chave no servidor (o Tiago, no VPS)

```bash
cd /opt/stacks/tickerlab && python3 scripts/gravar_chave_do_chat.py
docker compose up -d --force-recreate tickerlab-api
```

O script pede a chave no terminal, sem eco, confere só o formato (não vazia, sem espaço nem quebra de
linha), grava `ANTHROPIC_API_KEY_CHAT` no `.env` com permissão 600 (mantendo as outras linhas) e nunca
mostra o valor. Para trocar uma chave que já existe: `--trocar`. **Ele não liga o chat**: `TICKERLAB_CHAT`
fica como estava. O segundo comando recria a API para ela ler o `.env` novo.

## Ligar o chat (só o Tiago, depois da chave)

Pôr `TICKERLAB_CHAT=1` no `.env` e recriar a `tickerlab-api` do mesmo jeito. Antes de ligar: a linha da
política de privacidade sobre o chat (a pergunta vai ao provedor do modelo), com as duas revisões.
