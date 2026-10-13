"""Cliente JSON-RPC do nó do Bitcoin Core (base de cripto, série 1, PR 2).

O nó roda no servidor de casa e só aceita conexão local (`127.0.0.1`). A senha é o **cookie** que o
próprio nó escreve ao ligar (`<pasta de dados>/.cookie`, `__cookie__:<senha>`): muda a cada
reinício, então é lida a cada pedido, e nunca aparece em mensagem de erro nem em log.

Os números vêm como `Decimal` (não float), para os valores em BTC chegarem exatos a `para_satoshis`.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests

from base.cripto.blocos import para_satoshis

ENDERECO_PADRAO = "http://127.0.0.1:8332"
# bloco com milhares de transações no formato detalhado demora para o nó montar
TEMPO_LIMITE_EM_SEGUNDOS = 300
# getblock com o valor e a altura de cada moeda gasta (prevout)
DETALHE_COM_PREVOUT = 3


class ErroDoNo(RuntimeError):
    """O nó respondeu com erro ou recusou o acesso."""


class ClienteRPC:
    """Fala com o Bitcoin Core; tem o mesmo contrato que a leitura espera (`FonteDeBlocos`)."""

    def __init__(
        self, arquivo_do_cookie: Path, endereco: str = ENDERECO_PADRAO
    ) -> None:
        self.arquivo_do_cookie = arquivo_do_cookie
        self.endereco = endereco

    def altura_do_topo(self) -> int:
        """A altura do bloco mais novo que o nó conhece."""
        return self._chamar("getblockcount")

    def hash_na_altura(self, altura: int) -> str:
        """O hash do bloco desta altura na cadeia que o nó segue hoje."""
        return self._chamar("getblockhash", altura)

    def bloco(self, hash_do_bloco: str) -> dict:
        """O bloco inteiro, com o `prevout` de cada entrada."""
        return self._chamar("getblock", hash_do_bloco, DETALHE_COM_PREVOUT)

    def liberar_ate(self, altura: int) -> None:
        """Deixa o nó apagar os arquivos de blocos até esta altura (poda manual, `prune=1`)."""
        self._chamar("pruneblockchain", altura)

    def total_nao_gasto(self, altura: int) -> int:
        """Total das moedas não gastas na altura, em satoshis (precisa do `coinstatsindex=1`)."""
        resumo = self._chamar("gettxoutsetinfo", "none", altura)
        return para_satoshis(resumo["total_amount"])

    def _chamar(self, metodo: str, *parametros: object) -> Any:  # noqa: ANN401 (JSON do nó)
        usuario, senha = (
            self.arquivo_do_cookie.read_text(encoding="utf-8").strip().split(":", 1)
        )
        pedido = {
            "jsonrpc": "1.0",
            "id": "tickerlab",
            "method": metodo,
            "params": list(parametros),
        }
        resposta = requests.post(
            self.endereco,
            json=pedido,
            auth=(usuario, senha),
            timeout=TEMPO_LIMITE_EM_SEGUNDOS,
        )
        try:
            corpo = json.loads(resposta.text, parse_float=Decimal)
        except json.JSONDecodeError:
            raise ErroDoNo(
                f"{metodo}: o nó recusou o pedido (HTTP {resposta.status_code})."
            ) from None
        if corpo.get("error"):
            raise ErroDoNo(
                f"{metodo}: {corpo['error'].get('message', 'erro sem mensagem')}"
            )
        return corpo["result"]
