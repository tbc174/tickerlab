"""O modelo de verdade do chat (linha 903): uma volta pelo SDK oficial da Anthropic, com streaming.

Só é criado pela rota com o chat ligado e a chave presente; os testes usam um dublê de `Modelo` e nunca
chegam aqui com rede. A chave (`ANTHROPIC_API_KEY`) é lida pelo próprio SDK, do ambiente.

Escolhas (padrões da skill `claude-api`, 13/11/2026): pensamento adaptativo, esforço médio (respostas de
consulta a dados, não de raciocínio longo), streaming com `eager_input_streaming` nas ferramentas e cache
automático do prefixo (instruções e ferramentas iguais em toda volta). Com a entrada da ferramenta em
streaming, um JSON que o SDK não consegue ler sobe como `ValueError` do iterador: a volta é refeita, no
máximo `RECOMECOS_MAXIMOS` vezes. Os erros tipados da API (limite, chave) sobem para a rota.
"""

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any

import anthropic

from src.bcb import FUSO
from src.chat.conversa import (
    ChamadaDeFerramenta,
    FimDoTurno,
    ParteDoTurno,
    PedidoAoModelo,
    Recomeco,
    TextoParcial,
)
from src.chat.custo import UsoDoModelo

RECOMECOS_MAXIMOS = 2
ESFORCO_PADRAO = "medium"


def instrucoes_com_a_data(sistema: str, agora: datetime) -> str:
    """As instruções com o dia de hoje (Brasília), para o modelo saber o que é "recente"."""
    return (
        f"{sistema}\n\nHoje é {agora.astimezone(FUSO):%d/%m/%Y} (horário de Brasília)."
    )


def parametros_do_pedido(
    modelo: str, pedido: PedidoAoModelo, *, esforco: str = ESFORCO_PADRAO
) -> dict[str, Any]:
    """Os parâmetros de `messages.stream`, sem nada além das ferramentas do pedido (nem busca, nem código)."""
    return {
        "model": modelo,
        "max_tokens": pedido.max_tokens,
        "system": pedido.sistema,
        "tools": pedido.ferramentas,
        "messages": pedido.mensagens,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": esforco},
        "cache_control": {"type": "ephemeral"},
    }


def uso_da_resposta(uso: object) -> UsoDoModelo:
    """Os tokens que a resposta informa (os do cache podem vir vazios)."""

    def numero(nome: str) -> int:
        valor = getattr(uso, nome, None)
        return valor if isinstance(valor, int) else 0

    return UsoDoModelo(
        entrada=numero("input_tokens"),
        saida=numero("output_tokens"),
        cache_lido=numero("cache_read_input_tokens"),
        cache_gravado=numero("cache_creation_input_tokens"),
    )


def chamadas_da_resposta(conteudo: Sequence[object]) -> tuple[ChamadaDeFerramenta, ...]:
    return tuple(
        ChamadaDeFerramenta(id=bloco.id, nome=bloco.name, entrada=bloco.input)
        for bloco in conteudo
        if isinstance(bloco, anthropic.types.ToolUseBlock)
    )


class ModeloDaAnthropic:
    """O `Modelo` da conversa sobre o SDK; o cliente é criado na primeira volta."""

    def __init__(
        self,
        nome: str,
        cliente: anthropic.AsyncAnthropic | None = None,
        *,
        esforco: str = ESFORCO_PADRAO,
    ) -> None:
        self.nome = nome
        self._cliente = cliente
        self._esforco = esforco

    def _cliente_do_sdk(self) -> anthropic.AsyncAnthropic:
        if self._cliente is None:
            self._cliente = anthropic.AsyncAnthropic()
        return self._cliente

    async def turno(self, pedido: PedidoAoModelo) -> AsyncIterator[ParteDoTurno]:
        parametros = parametros_do_pedido(self.nome, pedido, esforco=self._esforco)
        for tentativa in range(RECOMECOS_MAXIMOS + 1):
            try:
                async with self._cliente_do_sdk().messages.stream(
                    **parametros
                ) as fluxo:
                    async for evento in fluxo:
                        if evento.type == "text":
                            yield TextoParcial(evento.text)
                    final = await fluxo.get_final_message()
            except ValueError:
                # o JSON da entrada de uma ferramenta veio ilegível: refaz a volta (sem id para responder)
                if tentativa == RECOMECOS_MAXIMOS:
                    raise
                yield Recomeco()
                continue
            yield FimDoTurno(
                conteudo=list(final.content),
                chamadas=chamadas_da_resposta(final.content),
                parada=final.stop_reason,
                uso=uso_da_resposta(final.usage),
            )
            return
