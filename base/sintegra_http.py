"""Download único dos dois TXT públicos do Paraná, com robots e sem redirecionar."""

import time
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

import requests

from base.arquivo.agente import AGENTE
from base.arquivo.coleta import conferir_freio, espaco_do_disco, pacote_de_certificados
from base.arquivo.robots import pausa_pedida, pode_buscar
from base.sintegra_estadual import MAX_TEXTO, URLS_PR

MAX_ROBOTS = 256 * 1024
BYTES_POR_BLOCO = 1024 * 1024
TEMPO_LIMITE = 120


class ClienteSintegra:
    """Só aceita a lista fechada do PR; sem retry, captcha, login ou formulário."""

    def __init__(self) -> None:
        self.sessao = requests.Session()
        self.sessao.headers["User-Agent"] = AGENTE
        # requests consome este atributo ao enviar; o vulture não vê esse uso.
        self.sessao.verify = pacote_de_certificados()
        self._robots: str | None = None
        self._ultimo_pedido = 0.0

    def _ler_robots(self) -> str:
        if self._robots is not None:
            return self._robots
        url = "http://processos.fazenda.pr.gov.br/robots.txt"
        with self.sessao.get(
            url, timeout=TEMPO_LIMITE, stream=True, allow_redirects=False
        ) as resposta:
            if resposta.headers.get("cf-mitigated", "").lower() == "challenge":
                raise ValueError("Sintegra: desafio no robots.txt")
            if resposta.status_code == 404:
                self._robots = ""
            else:
                _conferir_resposta(resposta)
                partes = bytearray()
                for bloco in resposta.iter_content(chunk_size=BYTES_POR_BLOCO):
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
        # Não reduzir o Crawl-delay pedido pela fonte.
        espera = pausa - (time.monotonic() - self._ultimo_pedido)
        if espera > 0:
            time.sleep(espera)
        conferir_freio(*espaco_do_disco(destino.parent))
        with self.sessao.get(
            url, timeout=TEMPO_LIMITE, stream=True, allow_redirects=False
        ) as resposta:
            self._ultimo_pedido = time.monotonic()
            _conferir_resposta(resposta)
            _gravar_resposta(resposta, destino)
            return dict(resposta.headers)


def _conferir_resposta(resposta: requests.Response) -> None:
    if (
        resposta.status_code != 200
        or resposta.headers.get("cf-mitigated", "").lower() == "challenge"
        or "html" in resposta.headers.get("Content-Type", "").lower()
    ):
        raise ValueError("Sintegra: resposta indisponível, redirecionada ou bloqueada")


def _gravar_resposta(resposta: requests.Response, destino: Path) -> None:
    tamanho = resposta.headers.get("Content-Length")
    if tamanho is not None and (
        not tamanho.isascii() or not tamanho.isdigit() or int(tamanho) > MAX_TEXTO
    ):
        raise ValueError("Sintegra: tamanho do arquivo inválido ou acima do limite")
    recebido = 0
    with destino.open("wb") as arquivo:
        for bloco in resposta.iter_content(chunk_size=BYTES_POR_BLOCO):
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
