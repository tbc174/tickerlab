"""Download único dos dois TXT públicos do Paraná, com robots e sem redirecionar."""

import time
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from urllib.parse import urlsplit

import requests
from urllib3.exceptions import HTTPError

from base.arquivo.agente import AGENTE
from base.arquivo.coleta import conferir_freio, espaco_do_disco, pacote_de_certificados
from base.arquivo.robots import pausa_pedida, pode_buscar
from base.sintegra_estadual import MAX_TEXTO, URLS_PR

MAX_ROBOTS = 256 * 1024
BYTES_POR_BLOCO = 64 * 1024
TEMPO_LIMITE = 15
MAX_DURACAO = 300
MAX_CRAWL_DELAY = 60


class ClienteSintegra:
    """Só aceita a lista fechada do PR; sem retry, captcha, login ou formulário."""

    def __init__(self) -> None:
        self.sessao = requests.Session()
        self.sessao.headers["User-Agent"] = AGENTE
        self.sessao.headers["Accept-Encoding"] = "identity"
        # requests consome este atributo ao enviar; o vulture não vê esse uso.
        self.sessao.verify = pacote_de_certificados()
        self._robots: str | None = None
        self._ultimo_pedido = 0.0
        self._prazo = time.monotonic() + MAX_DURACAO

    def _tempo_restante(self) -> float:
        restante = self._prazo - time.monotonic()
        if restante <= 0:
            raise TimeoutError("Sintegra: duração total excedida")
        return min(TEMPO_LIMITE, restante)

    def _ler_bytes(self, resposta: requests.Response) -> Iterator[bytes]:
        # read1 devolve os bytes disponíveis em uma leitura de socket; read/iter_content
        # esperariam encher o bloco, deixando gotejamento adiar a conferência do prazo.
        while True:
            self._tempo_restante()
            try:
                bloco = resposta.raw.read1(BYTES_POR_BLOCO, decode_content=False)
            except HTTPError:
                raise requests.RequestException("Sintegra: falha de leitura") from None
            self._tempo_restante()
            if not bloco:
                return
            yield bloco

    def _ler_robots(self) -> str:
        if self._robots is not None:
            return self._robots
        url = "http://processos.fazenda.pr.gov.br/robots.txt"
        with self.sessao.get(
            url, timeout=self._tempo_restante(), stream=True, allow_redirects=False
        ) as resposta:
            if resposta.headers.get("cf-mitigated", "").lower() == "challenge":
                raise ValueError("Sintegra: desafio no robots.txt")
            if resposta.status_code == 404:
                self._robots = ""
            else:
                _conferir_resposta(resposta)
                partes = bytearray()
                for bloco in self._ler_bytes(resposta):
                    partes.extend(bloco)
                    if len(partes) > MAX_ROBOTS:
                        raise ValueError("Sintegra: robots.txt acima do limite")
                self._robots = partes.decode("utf-8-sig", errors="strict")
        self._ultimo_pedido = time.monotonic()
        return self._robots

    def baixar(self, url: str, destino: Path) -> Mapping[str, str]:
        """Confere a autorização por caminho e baixa uma vez, com limite e freio."""
        if url not in URLS_PR.values():
            raise ValueError("Sintegra: URL fora da lista de arquivos permitidos")
        regras = self._ler_robots()
        if not pode_buscar(regras, urlsplit(url).path):
            raise ValueError("Sintegra PR: robots.txt proíbe o arquivo")
        pausa = pausa_pedida(regras) or 0.0
        if pausa > MAX_CRAWL_DELAY:
            raise ValueError("Sintegra: Crawl-delay acima do teto; coleta recusada")
        # Não reduzir o Crawl-delay pedido pela fonte.
        espera = pausa - (time.monotonic() - self._ultimo_pedido)
        if espera > 0:
            if espera >= self._prazo - time.monotonic():
                raise TimeoutError("Sintegra: pausa excederia a duração total")
            time.sleep(espera)
        conferir_freio(*espaco_do_disco(destino.parent))
        with self.sessao.get(
            url, timeout=self._tempo_restante(), stream=True, allow_redirects=False
        ) as resposta:
            self._ultimo_pedido = time.monotonic()
            _conferir_resposta(resposta)
            _gravar_resposta(resposta, destino, self._ler_bytes(resposta))
            return dict(resposta.headers)


def _conferir_resposta(resposta: requests.Response) -> None:
    if (
        resposta.status_code != 200
        or resposta.headers.get("cf-mitigated", "").lower() == "challenge"
        or "html" in resposta.headers.get("Content-Type", "").lower()
        or resposta.headers.get("Content-Encoding", "identity").lower()
        not in ("", "identity")
    ):
        raise ValueError("Sintegra: resposta indisponível, redirecionada ou bloqueada")


def _gravar_resposta(
    resposta: requests.Response, destino: Path, blocos: Iterable[bytes]
) -> None:
    tamanho = resposta.headers.get("Content-Length")
    if tamanho is not None and (
        not tamanho.isascii() or not tamanho.isdigit() or int(tamanho) > MAX_TEXTO
    ):
        raise ValueError("Sintegra: tamanho do arquivo inválido ou acima do limite")
    recebido = 0
    with destino.open("wb") as arquivo:
        for bloco in blocos:
            recebido += len(bloco)
            if recebido > MAX_TEXTO:
                raise ValueError("Sintegra: arquivo acima do limite")
            conferir_freio(*espaco_do_disco(destino.parent))
            arquivo.write(bloco)
    # requests pode descompactar HTTP; Content-Length só confere sem essa camada.
    if (
        tamanho
        and not resposta.headers.get("Content-Encoding")
        and recebido != int(tamanho)
    ):
        raise ValueError("Sintegra: download incompleto")
