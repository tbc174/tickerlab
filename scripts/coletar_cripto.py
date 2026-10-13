"""Coleta da base de cripto no servidor de casa (série 1 de cripto; `base/cripto/coleta.py`).

    python -m scripts.coletar_cripto mb          (Mercado Bitcoin: só os dias que faltam)
    python -m scripts.coletar_cripto kraken      (Kraken: os últimos 720 dias)
    python -m scripts.coletar_cripto cftc        (posições nos futuros de Bitcoin da CME)
    python -m scripts.coletar_cripto wikipedia   (acessos ao artigo "Bitcoin")
    python -m scripts.coletar_cripto gdelt       (notícias; um dia por vez, 6 s entre pedidos)
    python -m scripts.coletar_cripto receita     (planilha de criptoativos da Receita)
    python -m scripts.coletar_cripto no          (nó do Bitcoin; cookie em BITCOIN_COOKIE)
    python -m scripts.coletar_cripto kraken-arquivo XBTUSD_1440.csv   (carga única do histórico)

A base fica em `<TICKERLAB_ACERVO>/base/cripto/`. Cada arquivo baixado vai para o acervo do
original e para o registro de coletas (`com_registro`). Qualquer falha devolve 1 (o Kuma avisa) e
nada é tratado como dado ausente: a rodada seguinte pede de novo desde o último dia guardado.
"""

import argparse
import logging
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import requests

from base.cripto import coleta
from base.cripto.leitura import CadeiaInconsistente
from base.cripto.no_bitcoin import ClienteRPC, ErroDoNo
from src import acervo
from src.banco.coletas import com_registro

log = logging.getLogger("coletar_cripto")

AGENTE = "TickerLab (tickerlab.com.br; contato@tickerlab.com.br)"
TEMPO_LIMITE_EM_SEGUNDOS = 120
VARIAVEL_DO_COOKIE = "BITCOIN_COOKIE"
# fonte da linha de comando: (nome no registro de coletas, função de coleta)
COLETAS: dict[str, tuple[str, Callable[[Path, datetime, coleta.Baixar], int]]] = {
    "mb": ("mb-candles", coleta.coletar_mercado_bitcoin),
    "kraken": ("kraken-ohlc", coleta.coletar_kraken),
    "cftc": ("cftc-tff", coleta.coletar_cftc),
    "wikipedia": ("wiki-acessos", coleta.coletar_wikipedia),
    "gdelt": ("gdelt-cripto", coleta.coletar_gdelt),
    "receita": ("rfb-cripto", coleta.coletar_receita),
}
# a carga única do histórico: o CSV diário que vem dentro do zip oficial da Kraken
ARQUIVO_DA_KRAKEN = "https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_Full.zip/XBTUSD_1440.csv"
FALHAS_ESPERADAS = (
    requests.RequestException,
    ValueError,
    KeyError,
    ErroDoNo,
    CadeiaInconsistente,
)


def pasta_da_base() -> Path:
    """`<acervo>/base/cripto`, ao lado das outras bases (combinado com a sessão da base de ML)."""
    return (acervo.pasta_do_acervo() or acervo.PASTA_PADRAO) / "base" / "cripto"


def _baixar_da_fonte(url: str) -> bytes:
    resposta = requests.get(
        url, timeout=TEMPO_LIMITE_EM_SEGUNDOS, headers={"User-Agent": AGENTE}
    )
    resposta.raise_for_status()
    return resposta.content


def _coletar(fonte: str, pasta: Path, agora: datetime, caminho: str | None) -> int:
    if fonte == "kraken-arquivo":
        if not caminho:
            raise ValueError(
                "Informe o caminho do XBTUSD_1440.csv extraído do arquivo da Kraken."
            )
        ler = com_registro("kraken-arquivo", lambda _url: Path(caminho).read_bytes())
        return coleta.carregar_arquivo_kraken(pasta, agora, ler(ARQUIVO_DA_KRAKEN))
    if fonte == "no":
        cliente = ClienteRPC(Path(os.environ[VARIAVEL_DO_COOKIE]))
        return coleta.coletar_no(pasta, agora, cliente)
    nome_no_registro, coletar = COLETAS[fonte]
    return coletar(pasta, agora, com_registro(nome_no_registro, _baixar_da_fonte))


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("fonte", choices=[*COLETAS, "no", "kraken-arquivo"])
    argumentos.add_argument(
        "caminho", nargs="?", help="só para kraken-arquivo: o CSV diário"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        novas = _coletar(
            opcoes.fonte, pasta_da_base(), datetime.now(UTC), opcoes.caminho
        )
    except FALHAS_ESPERADAS as erro:
        log.error("Coleta de cripto (%s) falhou: %r", opcoes.fonte, erro)
        return 1
    log.info("Coleta de cripto (%s): %d linhas novas.", opcoes.fonte, novas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
