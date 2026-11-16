"""A rodada de pesquisa: uma hipótese e os limites dentro dos quais o bot pode procurar.

Os limites vêm do método das rodadas (relatório do Codex de 04/11/2026): sem teto, o bot vira
um rastreador. Passou do teto, o bot para e devolve o que tem, em vez de tentar mais uma vez.
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

MEGABYTE = 1024 * 1024


@dataclass(frozen=True)
class Limites:
    """O que cabe numa rodada. Os padrões são os da linha 697 da fila."""

    buscas: int = 12  # páginas pedidas à rede (`buscar_pagina`)
    candidatos: int = 30  # endereços distintos examinados (página ou documento)
    profundidade: int = 2  # quantos links de distância do endereço de partida
    bytes_maximos: int = 250 * MEGABYTE  # baixado numa rodada, no total
    segundos: int = 30 * 60  # relógio da rodada


class LimiteExcedido(Exception):
    """A rodada gastou um dos limites; a mensagem diz qual e o que fazer."""


@dataclass
class Rodada:
    """Uma hipótese, o relógio e os contadores. Uma rodada tem uma hipótese só."""

    hipotese: str
    limites: Limites = field(default_factory=Limites)
    relogio: Callable[[], float] = time.monotonic
    identificador: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    buscas_feitas: int = 0
    bytes_baixados: int = 0
    candidatos: set[str] = field(default_factory=set)
    profundidades: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._inicio = self.relogio()

    def segundos_gastos(self) -> float:
        return self.relogio() - self._inicio

    def conferir_tempo(self) -> None:
        if self.segundos_gastos() > self.limites.segundos:
            raise LimiteExcedido(
                f"a rodada passou de {self.limites.segundos // 60} minutos: "
                "pare e entregue o que tem"
            )

    def examinar(self, url: str, *, folha: bool = False) -> None:
        """Conta `url` como candidato (a mesma URL não conta duas vezes) e confere a profundidade.

        Documento (`folha`) não abre outros links: o limite vale para as páginas que se seguem, e o
        documento ligado a uma página dentro do limite ainda pode ser baixado (um passo a mais).
        Sem isso, o XLSX da CCEE, a 3 links da raiz, ficava fora de alcance na rodada real."""
        self.conferir_tempo()
        profundidade = self.profundidades.get(url, 0)
        teto = self.limites.profundidade + (1 if folha else 0)
        if profundidade > teto:
            raise LimiteExcedido(
                f"{url} está a {profundidade} links do ponto de partida (limite {teto})"
            )
        cheio = len(self.candidatos) >= self.limites.candidatos
        if url not in self.candidatos and cheio:
            raise LimiteExcedido(
                f"a rodada já examinou {self.limites.candidatos} candidatos: "
                "escolha entre eles"
            )
        self.candidatos.add(url)

    def gastar_busca(self) -> None:
        self.conferir_tempo()
        if self.buscas_feitas >= self.limites.buscas:
            raise LimiteExcedido(f"a rodada já fez {self.limites.buscas} buscas")
        self.buscas_feitas += 1

    def bytes_restantes(self) -> int:
        return max(self.limites.bytes_maximos - self.bytes_baixados, 0)

    def gastar_bytes(self, quantidade: int) -> None:
        self.bytes_baixados += quantidade

    def anotar_links(self, origem: str, destinos: list[str]) -> None:
        """Os links achados em `origem` ficam um passo mais longe (o caminho mais curto vale)."""
        proxima = self.profundidades.get(origem, 0) + 1
        for destino in destinos:
            self.profundidades[destino] = min(
                self.profundidades.get(destino, proxima), proxima
            )

    def resumo(self) -> dict[str, object]:
        limites = self.limites
        return {
            "rodada": self.identificador,
            "hipotese": self.hipotese,
            "buscas": f"{self.buscas_feitas}/{limites.buscas}",
            "candidatos": f"{len(self.candidatos)}/{limites.candidatos}",
            "megabytes": f"{self.bytes_baixados / MEGABYTE:.1f}/{limites.bytes_maximos // MEGABYTE}",
            "minutos": f"{self.segundos_gastos() / 60:.1f}/{limites.segundos // 60}",
            "profundidade_maxima": limites.profundidade,
        }
