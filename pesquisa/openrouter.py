"""Modelos grátis da OpenRouter para o agente de pesquisa (`pesquisa/agente.py`).

A OpenRouter fala o formato de chat da OpenAI, então basta o `requests`, sem pacote novo. Os
modelos `:free` têm limite por CONTA, não por chave (documentação da OpenRouter, consultada em
10/11/2026): 20 pedidos por minuto e 50 por dia; 1.000 por dia para quem já comprou US$ 10 em
créditos. Por isso a cota é um arquivo SQLite que vários agentes, em processos diferentes,
dividem: ela conta antes de pedir e espera (ou para) em vez de estourar.

Só dado público de empresa vai para a OpenRouter: os provedores dos modelos grátis podem guardar
o que recebem. A chave vem do ambiente (`OPENROUTER_API_KEY`) ou do `.env`, e nunca aparece em
mensagem de erro.
"""

import os
import sqlite3
import time
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path
from typing import Protocol

import requests

from pesquisa.agente import CotaDoModeloEsgotada, FalhaDoModelo

URL_DO_CHAT = "https://openrouter.ai/api/v1/chat/completions"
URL_DOS_MODELOS = "https://openrouter.ai/api/v1/models"
MODELO_PADRAO = "openrouter/free"  # roteador da OpenRouter: escolhe um modelo grátis que esteja de pé
VARIAVEL_DA_CHAVE = "OPENROUTER_API_KEY"
LIMITE_DIARIO_PADRAO = 50  # conta sem créditos comprados; com US$ 10 comprados, 1.000
POR_MINUTO_PADRAO = 20
UM_DIA = 24 * 60 * 60
UM_MINUTO = 60
TENTATIVAS_NO_429 = 3
ESPERA_NO_429 = 20.0  # segundos, dobrando a cada tentativa
TEMPO_LIMITE = 120.0  # segundos por pedido: modelo grátis às vezes demora


class CotaEsgotada(CotaDoModeloEsgotada):
    """A cota diária da conta acabou: o agente encerra a rodada com o que já tem."""


class SemChave(Exception):
    """Falta a chave da OpenRouter (`OPENROUTER_API_KEY` no ambiente ou no `.env`)."""


class ErroDoModelo(FalhaDoModelo):
    """A OpenRouter respondeu com erro; a mensagem leva o status, nunca a chave."""


class Post(Protocol):
    def __call__(
        self, url: str, *, headers: dict, json: dict, timeout: float
    ) -> requests.Response: ...


class Cota:
    """Pedidos feitos, gravados num SQLite que todos os agentes da conta dividem."""

    def __init__(
        self,
        arquivo: Path,
        *,
        limite_diario: int = LIMITE_DIARIO_PADRAO,
        por_minuto: int = POR_MINUTO_PADRAO,
        dormir: Callable[[float], None] = time.sleep,
        agora: Callable[[], float] = time.time,
    ) -> None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo = arquivo
        self.limite_diario = limite_diario
        self.por_minuto = por_minuto
        self.dormir = dormir
        self.agora = agora
        with closing(self._abrir()) as banco:
            banco.execute("CREATE TABLE IF NOT EXISTS pedidos (em REAL NOT NULL)")

    def _abrir(self) -> sqlite3.Connection:
        return sqlite3.connect(self.arquivo, timeout=30, isolation_level=None)

    def _contar(self, banco: sqlite3.Connection, desde: float) -> int:
        return banco.execute(
            "SELECT COUNT(*) FROM pedidos WHERE em > ?", (desde,)
        ).fetchone()[0]

    def reservar(self) -> None:
        """Conta um pedido antes de ele sair. Dia cheio: `CotaEsgotada`. Minuto cheio: espera."""
        while True:
            with closing(self._abrir()) as banco:
                banco.execute(
                    "BEGIN IMMEDIATE"
                )  # trava entre processos: dois agentes não contam juntos
                agora = self.agora()
                banco.execute("DELETE FROM pedidos WHERE em <= ?", (agora - UM_DIA,))
                if self._contar(banco, agora - UM_DIA) >= self.limite_diario:
                    banco.execute("COMMIT")
                    raise CotaEsgotada(
                        f"{self.limite_diario} pedidos nas últimas 24 horas"
                    )
                no_minuto = banco.execute(
                    "SELECT MIN(em), COUNT(*) FROM pedidos WHERE em > ?",
                    (agora - UM_MINUTO,),
                ).fetchone()
                if no_minuto[1] < self.por_minuto:
                    banco.execute("INSERT INTO pedidos (em) VALUES (?)", (agora,))
                    banco.execute("COMMIT")
                    return
                banco.execute("COMMIT")
            self.dormir(max(no_minuto[0] + UM_MINUTO - agora, 1.0))


class ModeloOpenRouter:
    """Um modelo da OpenRouter que responde ao agente; cada resposta gasta 1 pedido da cota."""

    def __init__(
        self,
        chave: str,
        modelo: str,
        cota: Cota,
        *,
        post: Post = requests.post,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self._chave = chave
        self.nome = modelo
        self.cota = cota
        self.post = post
        self.dormir = dormir

    def responder(self, mensagens: list[dict], ferramentas: list[dict]) -> dict:
        corpo: dict[str, object] = {"model": self.nome, "messages": mensagens}
        if ferramentas:
            corpo["tools"] = ferramentas
            corpo["tool_choice"] = "auto"
        for tentativa in range(TENTATIVAS_NO_429 + 1):
            self.cota.reservar()
            resposta = self.post(
                URL_DO_CHAT,
                headers={
                    "Authorization": f"Bearer {self._chave}",
                    "X-Title": "TickerLab pesquisa",
                },
                json=corpo,
                timeout=TEMPO_LIMITE,
            )
            if resposta.status_code == 429 and tentativa < TENTATIVAS_NO_429:
                self.dormir(ESPERA_NO_429 * 2**tentativa)
                continue
            return self._mensagem(resposta)
        raise ErroDoModelo("a OpenRouter seguiu respondendo 429")  # pragma: no cover

    def _mensagem(self, resposta: requests.Response) -> dict:
        if resposta.status_code != 200:
            raise ErroDoModelo(
                f"OpenRouter respondeu {resposta.status_code}: {_motivo(resposta)}"
            )
        dados = resposta.json()
        escolhas = dados.get("choices") or []
        if not escolhas:
            raise ErroDoModelo(f"OpenRouter respondeu sem escolha: {_motivo(resposta)}")
        return escolhas[0]["message"]


def _motivo(resposta: requests.Response) -> str:
    try:
        erro = resposta.json().get("error") or {}
    except ValueError:
        return "resposta que não é JSON"
    return str(erro.get("message", "sem detalhe"))[:200]


def ler_chave(ambiente: Mapping[str, str], arquivo_env: Path | None) -> str:
    """`OPENROUTER_API_KEY` do ambiente; sem ela, a linha do `.env` (o mesmo do app)."""
    chave = ambiente.get(VARIAVEL_DA_CHAVE, "").strip()
    if not chave and arquivo_env is not None and arquivo_env.is_file():
        for linha in arquivo_env.read_text("utf-8").splitlines():
            nome, separador, valor = linha.partition("=")
            if separador and nome.strip() == VARIAVEL_DA_CHAVE:
                chave = valor.strip().strip('"').strip("'")
    if not chave:
        raise SemChave(
            f"falta {VARIAVEL_DA_CHAVE}: crie a chave em openrouter.ai e ponha no .env"
        )
    return chave


def chave_do_ambiente(arquivo_env: Path) -> str:
    return ler_chave(os.environ, arquivo_env)


def modelos_gratis_com_ferramentas(catalogo: Mapping[str, object]) -> list[str]:
    """Do catálogo público (`GET /api/v1/models`), os modelos sem custo que aceitam ferramentas.
    A lista muda toda semana; por isso é lida na hora, nunca fixada no código."""
    escolhidos = []
    for modelo in catalogo.get("data", []):  # type: ignore[union-attr]
        preco = modelo.get("pricing") or {}
        gratis = preco.get("prompt") == "0" and preco.get("completion") == "0"
        if gratis and "tools" in (modelo.get("supported_parameters") or []):
            escolhidos.append(modelo["id"])
    return escolhidos
