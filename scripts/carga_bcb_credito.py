"""Carga do IF.data dos bancos (desde 2000) e do SCR.data do crédito por setor (desde 2012) para a base
(série 3 da base de ML, PR 7; `base/bcb_ifdata.py` e `base/bcb_scr.py`).

    python -m scripts.carga_bcb_credito                     (tudo, até hoje)
    python -m scripts.carga_bcb_credito --so ifdata --desde 2024
    python -m scripts.carga_bcb_credito --so scr --pasta <acervo>/base/bcb

Grava, com manifesto e versões (`base/parquet.py::gravar_com_versoes`):
- `ifdata/valores/tipo_<t>/<AAAAMM>.parquet`: os 15 relatórios de uma data-base e um tipo de
  instituição, no formato longo da fonte, com `disponivel_em`;
- `ifdata/cadastro/<AAAAMM>.parquet`: o cadastro da data-base (com a raiz do CNPJ);
- `ifdata/ligacao_dos_bancos.parquet`: instituição → CNPJ → tickers (com as tabelas da `carga_fca`);
- `scr/<ano>.parquet`: os meses do SCR.data versão 2 do ano, com `disponivel_em`.

As 8 datas-base mais novas do IF.data e os 2 anos mais novos do SCR são baixados de novo a cada carga
(o BC revisa os números; cada revisão vira versão). O resto vem do acervo se já estiver lá. Um pedido
por vez, com pausa; se o firewall do BC bloquear, espera 5 minutos e tenta mais uma vez. Recusa rodar
sem a versão do código (exigência 13 da ADR 0055).
"""

import argparse
import calendar
import hashlib
import logging
import re
import sys
import time
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import sqlalchemy as sa

from base import bcb_ifdata, bcb_scr
from base.parquet import GRAVADO, IGUAL, gravar_com_versoes, gravar_tabela
from base.publicacao import dia_da_coleta
from src import acervo
from src.banco.coletas import (
    coletas_guardadas,
    com_registro,
    original_mais_recente,
)
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_bcb_credito")
FONTE_IFDATA = "bcb-ifdata"
FONTE_SCR = "bcb-scr-base"  # o arquivista guarda os mesmos arquivos como `bcb-scr`
SUBPASTA = Path("base") / "bcb"
SUBPASTA_DO_FCA = Path("base") / "fca"
DATAS_RECENTES = 8  # do IF.data: dois anos de trimestres
ANOS_RECENTES = 2  # do SCR
PAUSA_IFDATA, PAUSA_SCR = 1.0, 30.0  # segundos entre pedidos
ESPERA_DEPOIS_DO_BLOQUEIO = 300.0
NAO_ENCONTRADO = 404
ORDEM_DOS_VALORES = ["cod_inst", "relatorio", "conta", "grupo", "coluna"]
ORDEM_DO_CADASTRO = ["cod_inst"]


def _baixar_da_fonte(url: str) -> bytes | None:
    for tentativa in (1, 2):
        try:
            resposta = requests.get(
                url,
                timeout=900,
                headers={"User-Agent": "TickerLab (contato@tickerlab.com.br)"},
            )
            if resposta.status_code == NAO_ENCONTRADO:
                return None
            resposta.raise_for_status()
            return resposta.content
        except requests.RequestException:
            if tentativa == 2:
                raise
            log.warning("o BC não respondeu %s: tento de novo em 5 minutos", url)
            time.sleep(ESPERA_DEPOIS_DO_BLOQUEIO)
    return None


baixar_ifdata = com_registro(FONTE_IFDATA, _baixar_da_fonte)
baixar_scr = com_registro(FONTE_SCR, _baixar_da_fonte)


def _origem(url: str, conteudo: bytes) -> dict[str, str]:
    return {"url": url, "sha256": hashlib.sha256(conteudo).hexdigest()}


def _obter(
    conexao: sa.Connection,
    url: str,
    baixar: Callable[[str], bytes | None],
    de_novo: bool,
    pausa: float,
) -> bytes | None:
    if not de_novo and (guardado := original_mais_recente(conexao, url)) is not None:
        return guardado
    conteudo = baixar(url)
    time.sleep(pausa)
    return conteudo


def _data_da_base(data_base: int) -> date:
    ano, mes = divmod(data_base, 100)
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def _coletas_do_relatorio(
    conexao: sa.Connection, url: str, lido: bytes
) -> list[tuple[pd.Timestamp, bytes]]:
    """Cada resposta guardada do relatório (o dia da baixada e o conteúdo). Sem nenhuma guardada
    (acervo desligado), só a que foi lida agora, sem dia."""
    guardadas = coletas_guardadas(conexao, url)
    if not guardadas:
        return [(pd.NaT, lido)]
    return [(dia_da_coleta(baixado_em), c) for baixado_em, _, c in guardadas]


def _valores_do_tipo(
    coletas: dict[str, list[tuple[pd.Timestamp, bytes]]],
) -> pd.DataFrame:
    """Os relatórios de um tipo, cada um com as revisões do BC (uma coleta por baixada)."""
    partes = []
    for guardadas in coletas.values():
        lidas = [(dia, bcb_ifdata.ler_valores(c)) for dia, c in guardadas]
        lidas = [(dia, t) for dia, t in lidas if not t.empty]
        if lidas:
            partes.append(bcb_ifdata.valores_com_revisoes(lidas))
    return pd.concat(partes, ignore_index=True)


def carregar_ifdata_data(
    conexao: sa.Connection, data_base: int, pasta: Path, de_novo: bool
) -> str:
    """Os 15 relatórios de cada tipo de instituição e o cadastro de uma data-base."""
    resultados = []
    for tipo in bcb_ifdata.tipos_da_data(data_base):
        lidos = []
        for relatorio in bcb_ifdata.RELATORIOS:
            url = bcb_ifdata.endereco_dos_valores(data_base, tipo, relatorio)
            conteudo = _obter(conexao, url, baixar_ifdata, de_novo, PAUSA_IFDATA)
            if conteudo is not None:
                lidos.append((url, conteudo))
        coletas = {u: _coletas_do_relatorio(conexao, u, c) for u, c in lidos}
        origens = [
            _origem(u, c) for u, guardadas in coletas.items() for _, c in guardadas
        ]
        if all(bcb_ifdata.ler_valores(c).empty for _, c in lidos):
            resultados.append("vazio")
            continue
        resultados.append(
            gravar_com_versoes(
                lambda c=coletas: _valores_do_tipo(c),
                pasta / "ifdata" / "valores" / f"tipo_{tipo}" / str(data_base),
                origens,
                ORDEM_DOS_VALORES,
            )
        )
    if all(r == "vazio" for r in resultados):
        return "sem dados (ainda não publicada?)"
    url = bcb_ifdata.endereco_do_cadastro(data_base)
    conteudo = _obter(conexao, url, baixar_ifdata, de_novo, PAUSA_IFDATA)
    if conteudo is not None:
        cadastro = bcb_ifdata.ler_cadastro(conteudo)
        resultados.append(
            gravar_com_versoes(
                lambda: cadastro,
                pasta / "ifdata" / "cadastro" / str(data_base),
                [_origem(url, conteudo)],
                ORDEM_DO_CADASTRO,
            )
        )
    return f"{resultados.count(GRAVADO)} gravadas, {resultados.count(IGUAL)} iguais"


def montar_ligacao(pasta: Path, pasta_do_fca: Path) -> int:
    """A ligação instituição → CNPJ → tickers, de todos os cadastros já gravados."""
    # só o cadastro atual de cada data-base (`202506`), nunca as versões anteriores (`202506.v1`)
    arquivos = sorted(
        a
        for a in (pasta / "ifdata" / "cadastro").glob("*.parquet")
        if re.fullmatch(r"\d{6}", a.stem)
    )
    if not arquivos:
        return 0
    cadastro = pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)
    entradas = [pasta_do_fca / "emissores.parquet", pasta_do_fca / "tickers.parquet"]
    emissores, tickers = (pd.read_parquet(a) for a in entradas)
    ligacao = bcb_ifdata.ligacao_dos_bancos(cadastro, emissores, tickers)
    origens = [
        {
            "url": a.relative_to(a.parents[2]).as_posix(),
            "sha256": hashlib.sha256(a.read_bytes()).hexdigest(),
        }
        for a in [*arquivos, *entradas]
    ]
    gravar_tabela(
        ligacao,
        pasta / "ifdata" / "ligacao_dos_bancos",
        origens,
        ["data_base", "cod_inst"],
    )
    return len(ligacao)


def carregar_scr_ano(
    conexao: sa.Connection, ano: int, pasta: Path, de_novo: bool
) -> str:
    url = bcb_scr.endereco_do_ano(ano)
    conteudo = _obter(conexao, url, baixar_scr, de_novo, PAUSA_SCR)
    if conteudo is None:
        return "sem arquivo"
    return gravar_com_versoes(
        lambda: (t := bcb_scr.ler_ano(conteudo)).assign(
            disponivel_em=bcb_scr.disponivel_em(t)
        ),
        pasta / "scr" / str(ano),
        [_origem(url, conteudo)],
        list(bcb_scr.COLUNAS_DE_TEXTO),
    )


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    argumentos.add_argument("--so", choices=("ifdata", "scr"), default=None)
    argumentos.add_argument("--desde", type=int, default=None)
    argumentos.add_argument("--ate", type=int, default=hoje.year)
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--fca", type=Path, default=None, help="pasta da carga_fca")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    raiz = acervo.pasta_do_acervo()
    pasta = opcoes.pasta or (None if raiz is None else raiz / SUBPASTA)
    pasta_do_fca = opcoes.fca or (None if raiz is None else raiz / SUBPASTA_DO_FCA)
    if pasta is None:
        argumentos.error("acervo desligado: informe --pasta")
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            if opcoes.so in (None, "ifdata"):
                desde = opcoes.desde or bcb_ifdata.PRIMEIRO_ANO
                datas = [
                    d
                    for d in bcb_ifdata.datas_base(desde, opcoes.ate)
                    if _data_da_base(d) < hoje
                ]
                todas = [
                    d
                    for d in bcb_ifdata.datas_base(bcb_ifdata.PRIMEIRO_ANO, hoje.year)
                    if _data_da_base(d) < hoje
                ]
                recentes = set(todas[-DATAS_RECENTES:])
                for data_base in datas:
                    resultado = carregar_ifdata_data(
                        conexao, data_base, pasta, data_base in recentes
                    )
                    log.info("IF.data %s: %s", data_base, resultado)
                if (
                    pasta_do_fca is not None
                    and (pasta_do_fca / "tickers.parquet").exists()
                ):
                    log.info(
                        "ligação dos bancos: %s linhas",
                        montar_ligacao(pasta, pasta_do_fca),
                    )
                else:
                    log.warning(
                        "sem as tabelas da carga_fca: ligação dos bancos não montada"
                    )
            if opcoes.so in (None, "scr"):
                desde = opcoes.desde or bcb_scr.PRIMEIRO_ANO
                for ano in range(max(desde, bcb_scr.PRIMEIRO_ANO), opcoes.ate + 1):
                    resultado = carregar_scr_ano(
                        conexao, ano, pasta, ano > hoje.year - ANOS_RECENTES
                    )
                    log.info("SCR %s: %s", ano, resultado)
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
