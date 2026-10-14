"""Arquiva as fontes que só mostram o "agora" (servidor de casa; `base/arquivo/`).

    python -m scripts.arquivar_fontes --listar        (o catálogo)
    python -m scripts.arquivar_fontes diaria          (CVM, CGU, termos e catálogos; 2h)
    python -m scripts.arquivar_fontes semanal         (FIAGRO, FIDC, CRI/CRA, IBAMA, lista suja, GLEIF)
    python -m scripts.arquivar_fontes mensal          (CNPJ e PGFN, pesadas)
    python -m scripts.arquivar_fontes cvm-fiagro      (uma fonte só)

Cada arquivo vai para o acervo (`TICKERLAB_ACERVO`), para o registro de coletas e para o manifesto do
dia. Saída: 0 tudo certo; 1 alguma falha (o Kuma avisa); 2 nada falhou, mas um termo de uso ou um
catálogo mudou (aviso para alguém ler). Fonte desconhecida também sai com 2.
"""

import argparse
import logging
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import requests

from base.arquivo.coleta import (
    ErroDeDescoberta,
    Fonte,
    FreioDeDisco,
    Resposta,
    Resultado,
    arquivar,
)
from base.arquivo.fontes import FONTES, GRUPOS, POR_ID
from src import acervo

log = logging.getLogger("arquivar_fontes")

# alguns portais bloqueiam por alguns minutos e depois liberam (o firewall do BC, 14/10/2026): uma
# nova tentativa depois de esperar, nunca um laço
ESPERA_PARA_TENTAR_DE_NOVO = 300

AGENTE = "TickerLab (tickerlab.com.br; contato@tickerlab.com.br)"
TEMPO_LIMITE_EM_SEGUNDOS = 120
OK, FALHA, AVISO = 0, 1, 2


class ClienteHttp:
    """O `Cliente` do arquivista com `requests`: um pedido por vez, com o nosso `User-Agent`."""

    def __init__(self) -> None:
        self.sessao = requests.Session()
        self.sessao.headers["User-Agent"] = AGENTE

    def ler(
        self,
        url: str,
        *,
        metodo: str = "GET",
        cabecalhos: Mapping[str, str] | None = None,
    ) -> Resposta:
        resposta = self.sessao.request(
            metodo,
            url,
            headers=dict(cabecalhos or {}),
            timeout=TEMPO_LIMITE_EM_SEGUNDOS,
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


def _uma_rodada(
    fonte: Fonte, cliente: ClienteHttp, temporaria: Path
) -> Resultado | None:
    """Arquiva a fonte; None quando a fonte inteira falhou (descoberta, rede)."""
    try:
        return arquivar(fonte, cliente, datetime.now(UTC), temporaria)
    except (ErroDeDescoberta, requests.RequestException) as erro:
        log.error("%s: %s", fonte.id, erro)
        return None


def _arquivar_com_nova_tentativa(
    fonte: Fonte, cliente: ClienteHttp, temporaria: Path
) -> Resultado | None:
    """Uma rodada; se falhou (toda ou em parte), espera e tenta mais uma vez. Freio de disco não
    tenta de novo (vira falha na hora)."""
    try:
        resultado = _uma_rodada(fonte, cliente, temporaria)
        if resultado is not None and not resultado.falhas:
            return resultado
        log.warning(
            "%s: falhou; nova tentativa em %d s", fonte.id, ESPERA_PARA_TENTAR_DE_NOVO
        )
        time.sleep(ESPERA_PARA_TENTAR_DE_NOVO)
        return _uma_rodada(fonte, cliente, temporaria)
    except FreioDeDisco as erro:
        log.error("%s: %s", fonte.id, erro)
        return None


def escolher(alvo: str) -> list[Fonte]:
    """As fontes de um grupo ("diaria") ou a fonte pelo id ("cvm-fiagro"); vazio se não existe."""
    if alvo in GRUPOS:
        return [fonte for fonte in FONTES if fonte.grupo == alvo]
    return [POR_ID[alvo]] if alvo in POR_ID else []


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "alvo", nargs="?", help="grupo (diaria, semanal, mensal) ou id da fonte"
    )
    argumentos.add_argument(
        "--listar", action="store_true", help="mostra o catálogo e sai"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if opcoes.listar:
        for fonte in FONTES:
            marcas = ", ".join(
                m for m, s in (("pesada", fonte.pesada), ("vigia", fonte.vigia)) if s
            )
            print(f"{fonte.grupo:8} {fonte.id:28} {fonte.tipo:8} {marcas}")
        return OK
    fontes = escolher(opcoes.alvo or "")
    if not fontes:
        log.error("Fonte ou grupo desconhecido: %r (veja --listar)", opcoes.alvo)
        return AVISO

    pasta = acervo.pasta_do_acervo()
    temporaria = (pasta or Path.cwd()) / ".temporario"
    cliente = ClienteHttp()
    falhou = mudou = False
    for fonte in fontes:
        resultado = _arquivar_com_nova_tentativa(fonte, cliente, temporaria)
        if resultado is None:
            falhou = True
            continue
        log.info(
            "%s: %d novos, %d iguais, %d sem mudança nos cabeçalhos, %d falhas",
            fonte.id,
            resultado.novos,
            resultado.iguais,
            resultado.pulados,
            len(resultado.falhas),
        )
        falhou = falhou or bool(resultado.falhas)
        for url in resultado.mudaram:
            log.warning("%s: o texto mudou em %s (ler de novo)", fonte.id, url)
            mudou = True
    if falhou:
        return FALHA
    return AVISO if mudou else OK


if __name__ == "__main__":
    sys.exit(main())
