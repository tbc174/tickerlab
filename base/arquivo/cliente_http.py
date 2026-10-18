"""O `Cliente` do arquivista com `requests` (`base/arquivo/coleta.py`): um pedido por vez, com o
nosso `User-Agent`. Fica em `base/` (e não no script) porque a imagem do contêiner não leva
`scripts/`: o arquivista de casa e a cópia da B3 no VPS usam o mesmo cliente."""

from collections.abc import Mapping
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from base.arquivo.coleta import Resposta, pacote_de_certificados

AGENTE = "TickerLab (tickerlab.com.br; contato@tickerlab.com.br)"
TEMPO_LIMITE_EM_SEGUNDOS = 120
HTTP_TRECHO = 206  # resposta a um pedido de trecho (Range)
# a Receita derruba a conexão antes de responder num arquivo diferente a cada rodada do CNPJ
# (`RemoteDisconnected`, 14/10/2026): o pedido é repetido na hora, com espera crescente (0, 4 e 8 s).
# Só quando a conexão cai ou não abre; resposta de erro (404, 500) nunca é repetida aqui
TENTATIVAS_SE_A_CONEXAO_CAI = 3
ESPERA_ENTRE_AS_TENTATIVAS = 2.0
METODOS_QUE_PODEM_REPETIR = frozenset({"GET", "HEAD", "PROPFIND"})


class ClienteHttp:
    """O `Cliente` do arquivista com `requests`: um pedido por vez, com o nosso `User-Agent`."""

    def __init__(self) -> None:
        self.sessao = requests.Session()
        self.sessao.headers["User-Agent"] = AGENTE
        self.sessao.verify = pacote_de_certificados()
        tentativas = Retry(
            total=TENTATIVAS_SE_A_CONEXAO_CAI,
            connect=TENTATIVAS_SE_A_CONEXAO_CAI,
            read=TENTATIVAS_SE_A_CONEXAO_CAI,
            status=0,
            redirect=None,
            backoff_factor=ESPERA_ENTRE_AS_TENTATIVAS,
            allowed_methods=METODOS_QUE_PODEM_REPETIR,
            raise_on_status=False,
        )
        for prefixo in ("https://", "http://"):
            self.sessao.mount(prefixo, HTTPAdapter(max_retries=tentativas))

    def ler(
        self,
        url: str,
        *,
        metodo: str = "GET",
        cabecalhos: Mapping[str, str] | None = None,
        corpo: bytes | None = None,
    ) -> Resposta:
        resposta = self.sessao.request(
            metodo,
            url,
            headers=dict(cabecalhos or {}),
            timeout=TEMPO_LIMITE_EM_SEGUNDOS,
            data=corpo,
        )
        resposta.raise_for_status()
        return Resposta(resposta.url, resposta.content, dict(resposta.headers))

    def cabecalhos(self, url: str) -> Mapping[str, str]:
        resposta = self.sessao.head(
            url, allow_redirects=True, timeout=TEMPO_LIMITE_EM_SEGUNDOS
        )
        resposta.raise_for_status()
        return dict(resposta.headers)

    def baixar(self, url: str, destino: Path) -> Mapping[str, str]:
        with self.sessao.get(
            url, stream=True, timeout=TEMPO_LIMITE_EM_SEGUNDOS
        ) as resposta:
            resposta.raise_for_status()
            with destino.open("wb") as arquivo:
                for parte in resposta.iter_content(chunk_size=1024 * 1024):
                    arquivo.write(parte)
            return dict(resposta.headers)

    def ler_trecho(self, url: str, inicio: int, fim: int) -> bytes:
        with self.sessao.get(
            url,
            headers={"Range": f"bytes={inicio}-{fim}"},
            stream=True,
            timeout=TEMPO_LIMITE_EM_SEGUNDOS,
        ) as resposta:
            resposta.raise_for_status()
            if resposta.status_code != HTTP_TRECHO:
                # o servidor mandaria o arquivo inteiro (GBs): para antes de ler o corpo
                raise ValueError(
                    f"o servidor ignorou o pedido de trecho (HTTP {resposta.status_code})"
                )
            return resposta.content
