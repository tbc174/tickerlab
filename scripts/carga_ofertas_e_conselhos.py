"""Carga das ofertas públicas e dos conselhos para a base (série 4 da base de ML, PR 6; `base/ofertas.py`
e `base/conselhos.py`).

    python -m scripts.carga_ofertas_e_conselhos                     (a base do acervo)
    python -m scripts.carga_ofertas_e_conselhos --base <pasta>

Lê os originais que o arquivista já guardou (não baixa nada) e grava, com manifesto e versões
(`gravar_com_versoes`: com as mesmas origens, nada é lido de novo):
- `<base>/ofertas/antigas.parquet` e `<base>/ofertas/resolucao_160.parquet` (a baixada mais nova);
- do FRE de cada ano, `<base>/fre_<tabela>/<ano>.parquet` para conselho, comitês, remuneração,
  extremos da remuneração, diversidade, capital social e empregados (`base/fre_governanca.py`), juntando todas as baixadas guardadas do ano (as versões
  antigas dos formulários continuam valendo com a data delas).
Nenhuma pessoa entra: as colunas de nome, CPF, nascimento e currículo nem são lidas. Recusa rodar sem
a versão do código (exigência 13 da ADR 0055).
"""

import argparse
import logging
import re
import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base import conselhos, fre_governanca, ofertas
from base.parquet import gravar_com_versoes
from src import acervo
from src.banco.coletas import coletas_guardadas, originais_mais_recentes
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_ofertas_e_conselhos")
FONTE_DO_FRE = "cvm-hist-fre"
ANO_DO_FRE = re.compile(r"/fre_cia_aberta_(\d{4})\.zip$")
DOCUMENTO = ["cnpj", "referencia", "versao"]
# pasta → (leitor, colunas de ordem do hash)
TABELAS_DO_FRE: dict[str, tuple[Callable[[bytes], pd.DataFrame], list[str]]] = {
    "fre_conselho": (conselhos.ler_conselho, [*DOCUMENTO, "orgao"]),
    "fre_comites": (conselhos.ler_comites, [*DOCUMENTO, "tipo_de_comite"]),
    "fre_remuneracao": (
        conselhos.ler_remuneracao,
        [*DOCUMENTO, "fim_do_exercicio", "orgao"],
    ),
    "fre_remuneracao_extremos": (
        conselhos.ler_remuneracao_extremos,
        [*DOCUMENTO, "fim_do_exercicio", "orgao"],
    ),
    "fre_diversidade": (conselhos.ler_diversidade, [*DOCUMENTO, "orgao"]),
    "fre_capital_social": (
        fre_governanca.ler_capital_social,
        [*DOCUMENTO, "id_capital_social"],
    ),
    "fre_empregados": (
        fre_governanca.ler_empregados,
        [*DOCUMENTO, "recorte", "grupo"],
    ),
}
# nome do Parquet → (leitor, colunas de ordem do hash)
TABELAS_DAS_OFERTAS: dict[str, tuple[Callable[[bytes], pd.DataFrame], list[str]]] = {
    "antigas": (
        ofertas.ler_antigas,
        ["numero_processo", "numero_registro_oferta", "cnpj_emissor"],
    ),
    "resolucao_160": (
        ofertas.ler_resolucao_160,
        ["numero_requerimento", "cnpj_emissor"],
    ),
}


def carregar_ofertas(conexao: sa.Connection, base: Path) -> None:
    linhas = [
        lin
        for lin in originais_mais_recentes(conexao, ofertas.FONTE)
        if lin.url == ofertas.URL
    ]
    if not linhas:
        log.warning("ofertas: nenhum original guardado de %s", ofertas.URL)
        return
    linha = linhas[0]
    conteudo = acervo.ler_original(linha.caminho_do_original)
    if conteudo is None:
        raise FileNotFoundError(f"original fora do acervo: {linha.url}")
    origens = [{"url": linha.url, "sha256": linha.sha256}]
    for nome, (ler, ordem) in TABELAS_DAS_OFERTAS.items():
        resultado = gravar_com_versoes(
            lambda ler=ler: ler(conteudo), base / "ofertas" / nome, origens, ordem
        )
        log.info("ofertas %s: %s", nome, resultado)


def _anos_do_fre(conexao: sa.Connection) -> dict[str, str]:
    """Ano → endereço do arquivo anual do FRE guardado."""
    anos = {}
    for linha in originais_mais_recentes(conexao, FONTE_DO_FRE):
        if achado := ANO_DO_FRE.search(linha.url):
            anos[achado.group(1)] = linha.url
    return dict(sorted(anos.items()))


def carregar_fre(conexao: sa.Connection, base: Path) -> None:
    for ano, url in _anos_do_fre(conexao).items():
        guardadas = coletas_guardadas(conexao, url)
        origens = [{"url": url, "sha256": sha256} for _, sha256, _ in guardadas]
        for pasta, (ler, ordem) in TABELAS_DO_FRE.items():

            def montar(
                ler: Callable[[bytes], pd.DataFrame] = ler, guardadas: list = guardadas
            ) -> pd.DataFrame:
                return conselhos.juntar_baixadas([ler(c) for _, _, c in guardadas])

            resultado = gravar_com_versoes(montar, base / pasta / ano, origens, ordem)
            log.info("%s %s: %s", pasta, ano, resultado)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--base", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    raiz = acervo.pasta_do_acervo()
    base = opcoes.base or (None if raiz is None else raiz / "base")
    if base is None:
        argumentos.error("acervo desligado: informe --base")
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            carregar_ofertas(conexao, base)
            carregar_fre(conexao, base)
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
