"""O chat de IA do app (linha 903): a pergunta do analista respondida pelo modelo com as ferramentas do conector.

Como funciona, em ordem:

1. A rota `POST /v1/chat` (`src/api_v1/chat.py`) confere a chave de ligar, a chave do modelo, a organização
   da conta, a cota e o teto, e só então grava a pergunta (`src/banco/perguntas_do_chat.py`).
2. `ferramentas.py` abre as 12 ferramentas do conector remoto, só de leitura, com o contrato da organização:
   o mesmo código do conector, chamando a API externa por dentro do processo (sem rede e sem a chave).
3. `conversa.py` roda as voltas entre o modelo e as ferramentas e devolve os eventos que a tela mostra:
   cada ferramenta chamada, o texto da resposta e, no fim, o "Como cheguei aqui".
4. `modelo_anthropic.py` é o modelo de verdade; os testes usam um dublê, e nenhuma chamada paga sai deles.

Nasce desligado: sem `TICKERLAB_CHAT=1` a rota responde que o chat não está disponível e nenhuma chamada sai.
Ligar em produção é só do Tiago. A chave do modelo é só do chat (`ANTHROPIC_API_KEY_CHAT`): a geral
(`ANTHROPIC_API_KEY`) é o interruptor de outros usos pagos (tópicos, leitura do boletim), e pôr uma no
servidor não pode ligar o outro nem misturar o gasto. Ela vai ao SDK pelo `modelo_anthropic.py`, de forma
explícita (o SDK, sozinho, só leria a geral), e nunca vai para log, banco ou resposta. Quem a grava no VPS
é o Tiago, com `scripts/gravar_chave_do_chat.py` (ver `docs/chat-de-ia.md`).
"""

import os
from collections.abc import Mapping

VARIAVEL_DE_LIGAR = "TICKERLAB_CHAT"
VARIAVEL_DO_MODELO = "TICKERLAB_CHAT_MODELO"
# só a do chat, sem cair na geral (ANTHROPIC_API_KEY), no molde de ANTHROPIC_API_KEY_VITRINE e _MA
VARIAVEL_DA_CHAVE_DO_MODELO = "ANTHROPIC_API_KEY_CHAT"
# o padrão (13/11/2026): o Opus mais novo; o Sonnet 5.5 custa a metade e é a troca pela variável
MODELO_PADRAO = "claude-opus-5-5"


def _ambiente(ambiente: Mapping[str, str] | None) -> Mapping[str, str]:
    return ambiente if ambiente is not None else os.environ


def chat_ligado(ambiente: Mapping[str, str] | None = None) -> bool:
    """O chat só existe com `TICKERLAB_CHAT=1`."""
    return _ambiente(ambiente).get(VARIAVEL_DE_LIGAR, "").strip() == "1"


def modelo_do_chat(ambiente: Mapping[str, str] | None = None) -> str:
    """O nome do modelo: o da variável, ou o padrão escrito aqui."""
    return _ambiente(ambiente).get(VARIAVEL_DO_MODELO, "").strip() or MODELO_PADRAO


def chave_do_modelo(ambiente: Mapping[str, str] | None = None) -> str | None:
    """A chave do chat, para entregar ao SDK; None sem ela (nunca a geral, `ANTHROPIC_API_KEY`)."""
    return _ambiente(ambiente).get(VARIAVEL_DA_CHAVE_DO_MODELO, "").strip() or None


def tem_chave_do_modelo(ambiente: Mapping[str, str] | None = None) -> bool:
    """Se a chave do chat está no ambiente (a rota só confere a presença)."""
    return chave_do_modelo(ambiente) is not None
