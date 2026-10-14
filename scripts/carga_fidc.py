"""Carga do informe mensal de FIDC (desde 2013) e do cadastro de fundos para a base (série 3 da base
de ML, PR 6; `base/fidc.py`).

    python -m scripts.carga_fidc                        (2013 até o ano atual, e o cadastro)
    python -m scripts.carga_fidc --desde 2024 --pasta <acervo>/base/fidc

Grava, com manifesto e versões (`base/parquet.py::gravar_com_versoes`):
- `informe/<quadro>/<ano>.parquet`: cada quadro do informe (`tab_I`...) no formato da fonte, com
  `competencia`, `cnpj_fundo` e `disponivel_em`; de 2013 a 2024 pelos arquivos anuais (`HIST/`), de
  2025 em diante pelos mensais;
- `cadastro/cad_fi.parquet`, `cadastro/hist_<tabela>.parquet` e `cadastro/registro_<tabela>.parquet`:
  o cadastro atual, o histórico e o registro da CVM 175.

Nada de dado pessoal: CPF de cedente, diretor e gestor pessoa física saem no leitor. Cada arquivo
vem do acervo (o arquivista guarda os do FIDC, `cvm-fidc`) e só é baixado se faltar (fonte
`cvm-fidc-base`), um pedido por vez. Recusa rodar sem a versão do código (exigência 13 da ADR 0055).
"""

import argparse
import hashlib
import logging
import sys
from collections.abc import Callable
from datetime import datetime
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import sqlalchemy as sa

from base import fidc
from base.parquet import GRAVADO, IGUAL, gravar_com_versoes
from src import acervo
from src.banco.coletas import com_registro, original_mais_recente
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_fidc")
FONTE = "cvm-fidc-base"
PASTA_DO_INFORME = "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/"
PASTA_DO_CADASTRO = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/"
PRIMEIRO_ANO = 2013
ULTIMO_ANO_HISTORICO = 2024  # de 2025 em diante, um arquivo por mês
MESES = range(1, 13)
NAO_ENCONTRADO = 404
SUBPASTA = Path("base") / "fidc"
ORDEM = ["competencia", "cnpj_fundo"]


def _baixar_da_fonte(url: str) -> bytes | None:
    resposta = requests.get(
        url, timeout=600, headers={"User-Agent": "TickerLab (contato@tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return resposta.content


baixar = com_registro(FONTE, _baixar_da_fonte)


def enderecos_do_ano(ano: int) -> list[str]:
    if ano <= ULTIMO_ANO_HISTORICO:
        return [f"{PASTA_DO_INFORME}HIST/inf_mensal_fidc_{ano}.zip"]
    return [f"{PASTA_DO_INFORME}inf_mensal_fidc_{ano}{mes:02d}.zip" for mes in MESES]


def _obter(conexao: sa.Connection, url: str) -> bytes | None:
    return original_mais_recente(conexao, url) or baixar(url)


def _origem(url: str, conteudo: bytes) -> dict[str, str]:
    return {"url": url, "sha256": hashlib.sha256(conteudo).hexdigest()}


def carregar_ano(conexao: sa.Connection, ano: int, pasta: Path) -> str:
    """Grava os quadros do informe de um ano; diz quantos foram gravados e quantos estavam iguais."""
    lidos = [
        (u, c) for u in enderecos_do_ano(ano) if (c := _obter(conexao, u)) is not None
    ]
    if not lidos:
        return "sem arquivo"
    origens = [_origem(u, c) for u, c in lidos]

    @cache
    def quadros() -> dict[str, pd.DataFrame]:  # lido só se algum quadro precisar
        partes: dict[str, list[pd.DataFrame]] = {}
        for _, conteudo in lidos:
            for chave, tabela in fidc.ler_informe(conteudo).items():
                partes.setdefault(chave, []).append(tabela)
        return {k: pd.concat(v, ignore_index=True) for k, v in partes.items()}

    def montar(chave: str) -> Callable[[], pd.DataFrame]:
        return lambda: quadros()[chave].assign(disponivel_em=fidc.disponivel_em)

    nomes = sorted(set().union(*(fidc.quadros_do_arquivo(c) for _, c in lidos)))
    resultados = [
        gravar_com_versoes(
            montar(chave), pasta / "informe" / chave / str(ano), origens, ORDEM
        )
        for chave in nomes
    ]
    return f"{resultados.count(GRAVADO)} quadros gravados, {resultados.count(IGUAL)} iguais"


def carregar_cadastro(conexao: sa.Connection, pasta: Path) -> None:
    """O cadastro atual, o histórico e o registro da CVM 175 (cada arquivo, se mudou)."""
    leitores = {
        "cad_fi.csv": lambda c: {"cad_fi": fidc.ler_cadastro_de_fundos(c)},
        "cad_fi_hist.zip": lambda c: {
            f"hist_{k}": t for k, t in fidc.ler_historico_do_cadastro(c).items()
        },
        "registro_fundo_classe.zip": lambda c: {
            f"registro_{k.removeprefix('registro_')}": t
            for k, t in fidc.ler_registro_de_fundos(c).items()
        },
    }
    for nome, ler in leitores.items():
        url = PASTA_DO_CADASTRO + nome
        conteudo = _obter(conexao, url)
        if conteudo is None:
            log.warning("%s não existe na CVM: pulado", nome)
            continue
        tabelas = ler(conteudo)
        for chave, tabela in tabelas.items():
            resultado = gravar_com_versoes(
                lambda t=tabela: t,
                pasta / "cadastro" / chave,
                [_origem(url, conteudo)],
                [],
            )
            log.info("cadastro %s: %s (%s linhas)", chave, resultado, len(tabela))


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
                log.info("FIDC de %s: %s", ano, carregar_ano(conexao, ano, pasta))
            carregar_cadastro(conexao, pasta)
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
