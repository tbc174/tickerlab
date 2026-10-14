"""Carga das carteiras dos fundos (CDA) para a base, desde 2005 (série 3 da base de ML, PR 4;
`base/cda.py`).

    python -m scripts.carga_cda                      (2005 até o ano atual)
    python -m scripts.carga_cda --desde 2022 --ate 2022 --pasta <acervo>/base/cda

Um Parquet por ano (`<pasta>/<ano>.parquet`, com manifesto: `base/parquet.py`) com as posições em
ações de todos os fundos e a data desde quando cada uma era pública (`disponivel_em`). De 2005 a 2022
a CVM publica um arquivo por ano (`HIST/`); de 2023 em diante, um por mês. Cada arquivo vem do acervo
(o arquivista já guarda os do CDA, #191) e só é baixado se não estiver lá (fonte `cvm-cda`), um
pedido por vez.

- **Ano igual ao que já tem** (as mesmas origens no manifesto): pulado, sem regravar.
- **Arquivo regravado pela CVM** (outra origem): o Parquet anterior vira `<ano>.v<N>` e o novo entra
  no lugar; nada é apagado.
- Recusa rodar sem a versão do código (exigência 13 da ADR 0055). Feita para o servidor de casa: o
  ano mais pesado (2022) ocupa ~320 MB de memória.
"""

import argparse
import hashlib
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import sqlalchemy as sa

from base import cda
from base.parquet import gravar_com_versoes
from src import acervo
from src.banco.coletas import com_registro, original_mais_recente
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_cda")
FONTE = "cvm-cda"
PASTA_DA_CVM = "https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/"
PRIMEIRO_ANO = 2005
ULTIMO_ANO_HISTORICO = 2022  # de 2023 em diante, um arquivo por mês
MESES = range(1, 13)
NAO_ENCONTRADO = 404
SUBPASTA = Path("base") / "cda"
ORDEM = ["competencia", "cnpj_fundo", "isin", "tipo"]


def _baixar_da_fonte(url: str) -> bytes | None:
    resposta = requests.get(
        url, timeout=900, headers={"User-Agent": "TickerLab (contato@tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return resposta.content


baixar = com_registro(FONTE, _baixar_da_fonte)


def enderecos_do_ano(ano: int) -> list[str]:
    if ano <= ULTIMO_ANO_HISTORICO:
        return [f"{PASTA_DA_CVM}HIST/cda_fi_{ano}.zip"]
    return [f"{PASTA_DA_CVM}cda_fi_{ano}{mes:02d}.zip" for mes in MESES]


def ler_ano(conexao: sa.Connection, ano: int) -> list[tuple[str, bytes]]:
    """(endereço, conteúdo) dos arquivos do ano que existem (do acervo ou da CVM)."""
    lidos = []
    for url in enderecos_do_ano(ano):
        conteudo = original_mais_recente(conexao, url) or baixar(url)
        if conteudo is not None:
            lidos.append((url, conteudo))
    return lidos


def _origens(lidos: list[tuple[str, bytes]]) -> list[dict[str, str]]:
    return [{"url": u, "sha256": hashlib.sha256(c).hexdigest()} for u, c in lidos]


def montar_ano(lidos: list[tuple[str, bytes]]) -> pd.DataFrame:
    partes = [p for _, c in lidos for p in cda.ler_posicoes_historicas(c)]
    tabela = pd.concat(partes, ignore_index=True)
    return tabela.assign(disponivel_em=cda.disponivel_em(tabela))


def carregar_ano(conexao: sa.Connection, ano: int, pasta: Path) -> str:
    """Grava o ano e diz o que aconteceu: "gravado", "igual" (pulado) ou "sem arquivo"."""
    lidos = ler_ano(conexao, ano)
    if not lidos:
        return "sem arquivo"

    def montar() -> pd.DataFrame:
        tabela = montar_ano(lidos)
        fundos = tabela["cnpj_fundo"].nunique()
        log.info("CDA de %s: %s posições de %s fundos", ano, len(tabela), fundos)
        return tabela

    return gravar_com_versoes(montar, pasta / str(ano), _origens(lidos), ORDEM)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    argumentos.add_argument("--desde", type=int, default=PRIMEIRO_ANO)
    argumentos.add_argument("--ate", type=int, default=hoje.year)
    argumentos.add_argument("--pasta", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    raiz = acervo.pasta_do_acervo()
    pasta = opcoes.pasta or (None if raiz is None else raiz / SUBPASTA)
    if pasta is None:
        argumentos.error("acervo desligado: informe --pasta")
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            for ano in range(opcoes.desde, opcoes.ate + 1):
                log.info("CDA de %s: %s", ano, carregar_ano(conexao, ano, pasta))
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
