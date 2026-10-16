"""Conferência medida das canceladas (ADR 0027, exigência 4; critério de pronto do modelo 8).

Cada companhia cancelada desde 2010 (cadastro da CVM, sem registro ativo) × cada tabela da base que
o modelo 8 usa, separando o que a CVM nunca publicou (`sem_documento_na_fonte`: limite da fonte,
contado) do que a montagem perdeu (`perdida_na_montagem`: erro). A fonte de cada tabela é o original
do acervo, lido inteiro (todas as companhias, sem os filtros do leitor da tabela):

- `demonstracoes` (DFP e ITR "como era"): o índice das entregas (`cvm-hist-dfp`, `cvm-hist-itr`);
- `auditores` (FCA): o arquivo dos auditores do FCA (`cvm-hist-fca`);
- `eventos` (IPE): o arquivo do IPE (`cvm-hist-ipe`).

Faltas que a fonte tem e a tabela não, com o motivo conferido à mão, ficam em
`base/conferidas/canceladas_explicadas.csv`. Grava `<pasta>/conferencias/canceladas.csv` (uma linha
por companhia e tabela) e sai com 1 se houver perdida. Só lê o acervo e a base:

    python -m scripts.conferir_canceladas [--pasta <acervo>/base]
"""

import argparse
import io
import logging
import sys
import zipfile
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base.cadastro import FonteETabela, cadastro_do_acervo, conferir_canceladas
from base.parquet import arquivos_atuais
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import obter_engine

log = logging.getLogger(__name__)

DESDE = "2010-01-01"
EXPLICADAS = (
    Path(__file__).resolve().parent.parent
    / "base"
    / "conferidas"
    / "canceladas_explicadas.csv"
)
# tabela da base → (fontes do arquivista, prefixo do arquivo no zip, coluna do CNPJ, começo da fonte)
FONTES = {
    # o índice começa na DFP de 2010: o primeiro prazo é 31/03/2011
    "demonstracoes": (
        ("cvm-hist-dfp", "cvm-hist-itr"),
        ("dfp_cia_aberta_2", "itr_cia_aberta_2"),
        "CNPJ_CIA",
        "2011-03-31",
    ),
    # o FCA começa em 2010, com entrega até 31/05
    "auditores": (
        ("cvm-hist-fca",),
        ("fca_cia_aberta_auditor_",),
        "CNPJ_Companhia",
        "2010-05-31",
    ),
    "eventos": (
        ("cvm-hist-ipe",),
        ("ipe_cia_aberta_",),
        "CNPJ_Companhia",
        "2003-01-01",
    ),
}


def _cnpjs_do_zip(conteudo: bytes, prefixos: tuple[str, ...], coluna: str) -> set[str]:
    """Os CNPJs do arquivo principal do zip anual (o que começa com um dos prefixos)."""
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
            nomes = [n for n in arquivo.namelist() if n.startswith(prefixos)]
            if not nomes:
                return set()
            bruto = pd.read_csv(
                arquivo.open(nomes[0]),
                sep=";",
                encoding="latin-1",
                dtype=str,
                usecols=[coluna],
            )
    except zipfile.BadZipFile:
        return set()
    return set(bruto[coluna].dropna().str.strip())


def na_fonte(
    conexao: sa.Connection,
    fontes: tuple[str, ...],
    prefixos: tuple[str, ...],
    coluna: str,
) -> set[str]:
    cnpjs: set[str] = set()
    for fonte in fontes:
        for original in originais_mais_recentes(conexao, fonte):
            conteudo = acervo.ler_original(original.caminho_do_original)
            if conteudo is not None:
                cnpjs |= _cnpjs_do_zip(conteudo, prefixos, coluna)
    return cnpjs


def na_tabela(pasta: Path) -> set[str]:
    cnpjs: set[str] = set()
    for arquivo in arquivos_atuais(pasta):
        cnpjs |= set(pd.read_parquet(arquivo, columns=["cnpj"])["cnpj"].dropna())
    return cnpjs


def explicadas() -> dict[tuple[str, str], str]:
    tabela = pd.read_csv(EXPLICADAS, sep=";", dtype=str)
    return dict(
        zip(
            zip(tabela["tabela"], tabela["cnpj"], strict=True),
            tabela["explicacao"],
            strict=True,
        )
    )


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    with obter_engine().connect() as conexao:
        achado = cadastro_do_acervo(conexao)
        if achado is None:
            log.error("sem o cadastro de companhias no acervo")
            return 1
        tabelas = {
            nome: FonteETabela(
                na_fonte=na_fonte(conexao, fontes, prefixos, coluna),
                na_tabela=na_tabela(pasta / nome),
                comeca_em=comeca_em,
            )
            for nome, (fontes, prefixos, coluna, comeca_em) in FONTES.items()
        }
    conferencia = conferir_canceladas(achado[0], tabelas, DESDE, explicadas())
    destino = pasta / "conferencias" / "canceladas.csv"
    destino.parent.mkdir(parents=True, exist_ok=True)
    conferencia.to_csv(destino, sep=";", index=False)
    resumo = conferencia.groupby(["tabela", "situacao"]).size()
    for (tabela, situacao), quantas in resumo.items():
        log.info("%s, %s: %d", tabela, situacao, quantas)
    perdidas = conferencia.attrs["perdidas"]
    if perdidas:
        log.error("%d canceladas perdidas na montagem (ver %s)", perdidas, destino)
        return 1
    log.info("nenhuma cancelada perdida na montagem (%s)", destino)
    return 0


if __name__ == "__main__":
    sys.exit(main())
