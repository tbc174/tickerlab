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
- **Bloco 8** (achado da série 4): as ações que os fundos informam como "demais ativos", com o CNPJ do
  emissor, vão para `<pasta>/../cda_bloco_8/<ano>.parquet`, com as mesmas regras (versões, "como era
  na data"). Pessoa física nunca entra (`base/cda.py::ler_acoes_do_bloco_8`).
"""

import argparse
import logging
import sys
from collections.abc import Callable
from datetime import datetime
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import sqlalchemy as sa

from base import cda, publicacao
from base.parquet import gravar_com_versoes
from src import acervo, rede
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
CHAVE = [
    "competencia",
    "cnpj_fundo",
]  # uma carteira por fundo e mês: a chave do `visto_em`
ORDEM_DO_BLOCO_8 = ["competencia", "cnpj_fundo", "cnpj_emissor", "tipo"]
PASTA_DO_BLOCO_8 = "cda_bloco_8"  # ao lado da pasta do CDA


def _baixar_da_fonte(url: str) -> bytes | None:
    resposta = rede.obter(
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


def _origens(versoes: list[publicacao.Versao]) -> list[dict[str, str]]:
    """Todas as versões guardadas de cada arquivo: delas sai o `visto_em`."""
    return [{"url": v.url, "sha256": v.sha256} for v in versoes]


def montar_ano(
    lidos: list[tuple[str, bytes]], vistos: pd.DataFrame | None = None
) -> pd.DataFrame:
    partes = [p for _, c in lidos for p in cda.ler_posicoes_historicas(c)]
    tabela = pd.concat(partes, ignore_index=True)
    return _com_visto_em(tabela.assign(disponivel_em=cda.disponivel_em(tabela)), vistos)


def _com_visto_em(tabela: pd.DataFrame, vistos: pd.DataFrame | None) -> pd.DataFrame:
    if vistos is None:
        vistos = pd.DataFrame(columns=[*CHAVE, publicacao.VISTO_EM])
    return publicacao.com_visto_em(tabela, vistos, CHAVE)


def montar_bloco_8(
    lidos: list[tuple[str, bytes]], vistos: pd.DataFrame | None = None
) -> pd.DataFrame:
    partes = [p for _, c in lidos for p in cda.ler_acoes_do_bloco_8(c)]
    tabela = (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=list(cda.COLUNAS_DO_BLOCO_8))
    )
    for coluna in ("competencia", "confidencial_ate"):
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    return _com_visto_em(tabela.assign(disponivel_em=cda.disponivel_em(tabela)), vistos)


def carregar_bloco_8(
    lidos: list[tuple[str, bytes]],
    ano: int,
    pasta: Path,
    versoes: list[publicacao.Versao],
    vistos: Callable[[], pd.DataFrame],
    *,
    refazer: bool = False,
) -> str:
    def montar() -> pd.DataFrame:
        tabela = montar_bloco_8(lidos, vistos())
        log.info(
            "Bloco 8 de %s: %s posições em ações com CNPJ do emissor", ano, len(tabela)
        )
        return tabela

    destino = pasta.parent / PASTA_DO_BLOCO_8 / str(ano)
    return gravar_com_versoes(
        montar, destino, _origens(versoes), ORDEM_DO_BLOCO_8, forcar=refazer
    )


def carregar_ano(
    conexao: sa.Connection, ano: int, pasta: Path, *, refazer: bool = False
) -> str:
    """Grava o ano e diz o que aconteceu: "gravado", "igual" (pulado) ou "sem arquivo"."""
    lidos = ler_ano(conexao, ano)
    if not lidos:
        return "sem arquivo"
    versoes = publicacao.todas_as_versoes(conexao, lidos)

    @cache
    def vistos() -> (
        pd.DataFrame
    ):  # o dia em que cada carteira apareceu, versão por versão
        return publicacao.vistos_nas_versoes(versoes, cda.chaves_do_cda, CHAVE)

    def montar() -> pd.DataFrame:
        tabela = montar_ano(lidos, vistos())
        fundos = tabela["cnpj_fundo"].nunique()
        log.info("CDA de %s: %s posições de %s fundos", ano, len(tabela), fundos)
        return tabela

    resultado = gravar_com_versoes(
        montar, pasta / str(ano), _origens(versoes), ORDEM, forcar=refazer
    )
    bloco_8 = carregar_bloco_8(lidos, ano, pasta, versoes, vistos, refazer=refazer)
    log.info("Bloco 8 de %s: %s", ano, bloco_8)
    return resultado


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    argumentos.add_argument("--desde", type=int, default=PRIMEIRO_ANO)
    argumentos.add_argument("--ate", type=int, default=hoje.year)
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument(
        "--refazer",
        action="store_true",
        help="regrava mesmo com as mesmas origens (o leitor mudou)",
    )
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
                resultado = carregar_ano(conexao, ano, pasta, refazer=opcoes.refazer)
                log.info("CDA de %s: %s", ano, resultado)
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
