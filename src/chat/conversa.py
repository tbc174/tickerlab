"""As voltas de uma pergunta ao chat (linha 903): o modelo pede ferramentas, o código as roda, e no fim sai a
resposta com o "Como cheguei aqui".

Só tipos simples na saída (dicionários prontos para virar JSON): cada evento é uma linha do NDJSON da rota
`POST /v1/chat`, e a tela (Streamlit hoje, JavaScript depois) só mostra o que recebe:

- `{"tipo": "ferramenta", "nome", "titulo", "filtros"}`: o modelo consultou uma ferramenta;
- `{"tipo": "texto", "texto"}`: um pedaço da resposta;
- `{"tipo": "recomeco"}`: a volta recomeçou (o texto parcial desta volta deve ser descartado);
- `{"tipo": "fim", "como_cheguei_aqui", "avisos", "aviso_final"}`: a lista das consultas feitas, com os
  filtros, se deram certo e quanto demoraram, montada pelo código e não pelo modelo.

O modelo é qualquer coisa com `turno(pedido)` (`Modelo`): o de verdade (`modelo_anthropic.py`) ou o dublê
dos testes. Os tetos (voltas de ferramenta, tokens por volta, tamanho do histórico) vêm de `LIMITES_DO_CHAT`.
"""

import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from src.chat.custo import UsoDoModelo
from src.chat.ferramentas import CaixaDeFerramentas, ResultadoDaFerramenta
from src.planos import LimitesDoChat

RESPONDIDA = "respondida"
RECUSADA = "recusada"
PARADA_DE_FERRAMENTA = "tool_use"
PARADA_DE_RECUSA = "refusal"
PARADA_DE_TAMANHO = "max_tokens"
MILISSEGUNDOS_POR_SEGUNDO = 1000
CARACTERES_DO_FILTRO = 120

MENSAGEM_LIMITE_DE_VOLTAS = "Limite de consultas desta pergunta atingido: responda com o que já foi consultado e diga o que faltou."
AVISO_RECUSA = "O modelo não respondeu a esta pergunta."
AVISO_CORTADA = "A resposta passou do tamanho máximo e foi cortada."
AVISO_VOLTAS = (
    "A pergunta passou do limite de consultas; a resposta pode estar incompleta."
)
AVISO_FINAL = (
    "Resposta escrita por IA com os dados do TickerLab: confira a fonte e a data de cada número. "
    "Nada aqui é recomendação de investimento."
)


@dataclass(frozen=True)
class ChamadaDeFerramenta:
    """Um pedido de ferramenta do modelo (`tool_use`)."""

    id: str
    nome: str
    entrada: object


@dataclass(frozen=True)
class PedidoAoModelo:
    """Tudo o que uma volta manda ao modelo."""

    sistema: str
    ferramentas: list[dict[str, object]]
    mensagens: list[dict[str, object]]
    max_tokens: int


@dataclass(frozen=True)
class TextoParcial:
    texto: str


@dataclass(frozen=True)
class Recomeco:
    """O streaming da volta falhou e ela vai ser refeita."""


@dataclass(frozen=True)
class FimDoTurno:
    """O fim de uma volta: o conteúdo inteiro (para voltar ao modelo), os pedidos de ferramenta e o uso."""

    conteudo: Sequence[object]
    chamadas: tuple[ChamadaDeFerramenta, ...]
    parada: str | None
    uso: UsoDoModelo


ParteDoTurno = TextoParcial | Recomeco | FimDoTurno


class Modelo(Protocol):
    def turno(self, pedido: PedidoAoModelo) -> AsyncIterator[ParteDoTurno]: ...


@dataclass(frozen=True)
class TrocaAnterior:
    """Uma pergunta e a resposta de antes, que a tela manda para o modelo ter o contexto."""

    pergunta: str
    resposta: str


def mensagens_iniciais(
    pergunta: str, historico: Sequence[TrocaAnterior], limites: LimitesDoChat
) -> list[dict[str, object]]:
    """As trocas mais recentes que cabem no teto do histórico, e a pergunta nova por último."""
    cabem: list[TrocaAnterior] = []
    sobra = limites.caracteres_do_historico
    for troca in reversed(historico[-limites.perguntas_no_historico :]):
        tamanho = len(troca.pergunta) + len(troca.resposta)
        if tamanho > sobra:
            break
        cabem.insert(0, troca)
        sobra -= tamanho
    mensagens: list[dict[str, object]] = []
    for troca in cabem:
        mensagens.append({"role": "user", "content": troca.pergunta})
        mensagens.append({"role": "assistant", "content": troca.resposta})
    mensagens.append(
        {"role": "user", "content": pergunta[: limites.caracteres_da_pergunta]}
    )
    return mensagens


def resumo_dos_filtros(entrada: object) -> dict[str, object]:
    """Os parâmetros que a ferramenta recebeu, sem os vazios e com texto curto (para a tela)."""
    if not isinstance(entrada, dict):
        return {}
    resumo: dict[str, object] = {}
    for nome, valor in entrada.items():
        if valor is None or valor == [] or valor == "":
            continue
        if isinstance(valor, str):
            valor = valor[:CARACTERES_DO_FILTRO]
        elif not isinstance(valor, int | float | bool):
            valor = str(valor)[:CARACTERES_DO_FILTRO]
        resumo[str(nome)[:CARACTERES_DO_FILTRO]] = valor
    return resumo


def _resultado_para_o_modelo(
    chamada: ChamadaDeFerramenta, resultado: ResultadoDaFerramenta
) -> dict[str, object]:
    bloco: dict[str, object] = {
        "type": "tool_result",
        "tool_use_id": chamada.id,
        "content": resultado.texto,
    }
    if resultado.erro:
        bloco["is_error"] = True
    return bloco


@dataclass
class Conversa:
    """Uma pergunta: roda as voltas e soma o uso. `estado` e `uso` valem depois do último evento."""

    modelo: Modelo
    caixa: CaixaDeFerramentas
    instrucoes: str
    limites: LimitesDoChat
    uso: UsoDoModelo = field(default_factory=UsoDoModelo)
    chamadas: int = 0
    # voltas refeitas: o uso da tentativa que falhou não chega (o SDK não entrega a mensagem final)
    recomecos: int = 0
    estado: str = RESPONDIDA

    async def _turno(
        self, mensagens: list[dict[str, object]]
    ) -> AsyncIterator[dict[str, object] | FimDoTurno]:
        pedido = PedidoAoModelo(
            sistema=self.instrucoes,
            ferramentas=[d.para_o_modelo() for d in self.caixa.definicoes],
            mensagens=list(mensagens),
            max_tokens=self.limites.tokens_por_volta,
        )
        fim: FimDoTurno | None = None
        async for parte in self.modelo.turno(pedido):
            if isinstance(parte, TextoParcial):
                yield {"tipo": "texto", "texto": parte.texto}
            elif isinstance(parte, Recomeco):
                self.recomecos += 1
                yield {"tipo": "recomeco"}
            else:
                fim = parte
        if fim is None:
            raise RuntimeError("O modelo terminou a volta sem o fim do turno.")
        self.uso = self.uso + fim.uso
        yield fim

    async def _consultar(
        self, chamada: ChamadaDeFerramenta, esgotou: bool, como: list[dict[str, object]]
    ) -> ResultadoDaFerramenta:
        if esgotou:
            return ResultadoDaFerramenta(MENSAGEM_LIMITE_DE_VOLTAS, erro=True)
        inicio = time.perf_counter()
        resultado = await self.caixa.executar(chamada.nome, chamada.entrada)
        self.chamadas += 1
        como.append(
            {
                "nome": chamada.nome,
                "titulo": self.caixa.titulo(chamada.nome),
                "filtros": resumo_dos_filtros(chamada.entrada),
                "ok": not resultado.erro,
                "duracao_ms": round(
                    (time.perf_counter() - inicio) * MILISSEGUNDOS_POR_SEGUNDO
                ),
            }
        )
        return resultado

    async def eventos(
        self, pergunta: str, historico: Sequence[TrocaAnterior] = ()
    ) -> AsyncIterator[dict[str, object]]:
        """Os eventos da resposta, em ordem; o último é sempre o `fim`."""
        mensagens = mensagens_iniciais(pergunta, historico, self.limites)
        como: list[dict[str, object]] = []
        avisos: list[str] = []
        voltas = 0
        while True:
            fim: FimDoTurno | None = None
            async for parte in self._turno(mensagens):
                if isinstance(parte, FimDoTurno):
                    fim = parte
                else:
                    yield parte
            assert fim is not None
            if fim.parada == PARADA_DE_RECUSA:
                self.estado = RECUSADA
                avisos.append(AVISO_RECUSA)
                break
            if fim.parada == PARADA_DE_TAMANHO:
                avisos.append(AVISO_CORTADA)
                break
            if fim.parada != PARADA_DE_FERRAMENTA or not fim.chamadas:
                break
            if voltas > self.limites.voltas_de_ferramenta:
                # já recebeu o aviso do limite e pediu mais: para aqui
                avisos.append(AVISO_VOLTAS)
                break
            esgotou = voltas >= self.limites.voltas_de_ferramenta
            mensagens.append({"role": "assistant", "content": list(fim.conteudo)})
            resultados: list[dict[str, object]] = []
            for chamada in fim.chamadas:
                yield {
                    "tipo": "ferramenta",
                    "nome": chamada.nome,
                    "titulo": self.caixa.titulo(chamada.nome),
                    "filtros": resumo_dos_filtros(chamada.entrada),
                }
                resultado = await self._consultar(chamada, esgotou, como)
                resultados.append(_resultado_para_o_modelo(chamada, resultado))
            mensagens.append({"role": "user", "content": resultados})
            voltas += 1
        yield {
            "tipo": "fim",
            "como_cheguei_aqui": como,
            "avisos": avisos,
            "aviso_final": AVISO_FINAL,
        }
