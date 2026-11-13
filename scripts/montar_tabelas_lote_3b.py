"""Monta `sigsif_estabelecimentos`, `receita_transacoes_individual` e `receita_transacoes_adesao` (linha 904, lote 3).

    python -m scripts.montar_tabelas_lote_3b --sigsif <pasta de montar_tabelas_lote_3 --baixar-sigsif>
    python -m scripts.montar_tabelas_lote_3b --transacoes <pasta de carga_receita_transacoes --baixar>
    python -m scripts.montar_tabelas_lote_3b --sigsif <pasta> --transacoes <pasta> --pasta /tmp/base

Os downloads são os dos scripts irmãos (mesmas pastas, mesmo `modificados.json`). Os arquivos baixados são dados de
fora: ficam numa pasta nova, nunca no repositório, e esta carga os lê com o Python em modo isolado (`python -I`).

Grava, só de pessoa jurídica (`base/derivadas_do_lote_3b.py`: quem é pessoa sai da tabela inteira e nenhum nome é
gravado), com manifesto e versões (`base/parquet.py::gravar_com_versoes`), um Parquet por tabela em
`<base>/<tabela>/<tabela>.parquet`. Pergunta à Receita guardada (`base/pgfn.py::pessoas_pela_receita`) quais raízes
são de pessoa; sem ela, nada entra. O log diz, por tabela, as linhas lidas, as que saíram e as que ficaram. Recusa
rodar sem a versão do código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 arquivo faltando ou tabela vazia.

Roda: manual (python -m scripts.montar_tabelas_lote_3b), no servidor de casa; sem uso registrado em 13/11/2026 (a
carga pede o "pode" da Diretoria).
"""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from base import derivadas_do_lote_3 as derivadas
from base import derivadas_do_lote_3b as derivadas_b
from base import receita_transacoes as transacoes
from base import sigsif
from base.parquet import gravar_com_versoes
from scripts import carga_receita_transacoes as carga
from scripts.montar_tabelas_lote_3 import (
    ARQUIVOS_DO_SIGSIF,
    ENDERECO_DO_SIGSIF,
    MODIFICADOS,
    _baixado_em,
    _faltam,
    _modificado_em,
    _origem,
    _pessoas_pela_receita,
    _sha256,
    _vazia,
)
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.montar_tabelas_lote_3b")

ORDEM_DOS_ESTABELECIMENTOS = list(derivadas_b.CHAVE_DOS_ESTABELECIMENTOS)
ORDEM_DOS_ACORDOS = list(derivadas_b.CHAVE_DOS_ACORDOS)
ORDEM_DAS_ADESOES = ["cnpj", "data_requerimento", "hash_linha"]


def montar_estabelecimentos(
    origem: Path,
    saida: Path,
    descobrir: derivadas.DescobrirPessoas,
    agora: pd.Timestamp,
    versao: str,
    forcar: bool = False,
) -> dict[str, object]:
    """Os estabelecimentos registrados no SIF, só de pessoa jurídica e sem a razão social."""
    caminho = origem / "registrados.csv"
    dados: dict[str, object] = {}

    def montar() -> pd.DataFrame:
        data = _modificado_em(origem, caminho.name)
        lido = sigsif.ler_estabelecimentos(caminho.read_bytes(), data)
        dados["registrados_sem_cnpj_descartados"] = lido.attrs["descartadas_sem_cnpj"]
        tabela, contagem = derivadas_b.estabelecimentos_para_a_base(lido, descobrir)
        dados.update(contagem)
        return derivadas.com_linhagem(
            tabela, data, _sha256(caminho), _baixado_em(caminho), agora, versao
        )

    tabela = derivadas_b.TABELA_ESTABELECIMENTOS
    dados["gravou"] = gravar_com_versoes(
        montar,
        saida / tabela / tabela,
        _origem(caminho, ENDERECO_DO_SIGSIF + ARQUIVOS_DO_SIGSIF[caminho.name]),
        ORDEM_DOS_ESTABELECIMENTOS,
        forcar=forcar,
    )
    return dados


def _montar_transacoes(
    origem: Path,
    saida: Path,
    nome: str,
    tabela: str,
    ordem: list[str],
    descobrir: derivadas.DescobrirPessoas,
    carimbos: tuple[pd.Timestamp, str],
    forcar: bool,
) -> dict[str, object]:
    """Uma das duas tabelas de transações (`nome` é o CSV da Receita); a contagem vai no resultado."""
    caminho = origem / nome
    individual = nome == carga.ARQUIVO_INDIVIDUAL
    dados: dict[str, object] = {}

    def montar() -> pd.DataFrame:
        lida = transacoes.Contagem()
        data = _modificado_em(origem, nome)
        leitor = transacoes.ler_individual if individual else transacoes.ler_adesao
        with open(caminho, "rb") as fluxo:
            lido = leitor(fluxo, data, lida)
        converter = (
            derivadas_b.acordos_para_a_base
            if individual
            else derivadas_b.adesoes_para_a_base
        )
        tabela_pj, contagem = converter(lido, descobrir)
        dados.update({**lida.para_manifesto(), **contagem})
        agora, versao = carimbos
        return derivadas.com_linhagem(
            tabela_pj, data, _sha256(caminho), _baixado_em(caminho), agora, versao
        )

    dados["gravou"] = gravar_com_versoes(
        montar,
        saida / tabela / tabela,
        _origem(caminho, f"{carga.RAIZ}{nome}"),
        ordem,
        forcar=forcar,
    )
    return dados


def montar_acordos(
    origem: Path,
    saida: Path,
    descobrir: derivadas.DescobrirPessoas,
    agora: pd.Timestamp,
    versao: str,
    forcar: bool = False,
) -> dict[str, object]:
    return _montar_transacoes(
        origem,
        saida,
        carga.ARQUIVO_INDIVIDUAL,
        derivadas_b.TABELA_ACORDOS,
        ORDEM_DOS_ACORDOS,
        descobrir,
        (agora, versao),
        forcar,
    )


def montar_adesoes(
    origem: Path,
    saida: Path,
    descobrir: derivadas.DescobrirPessoas,
    agora: pd.Timestamp,
    versao: str,
    forcar: bool = False,
) -> dict[str, object]:
    return _montar_transacoes(
        origem,
        saida,
        carga.ARQUIVO_ADESAO,
        derivadas_b.TABELA_ADESOES,
        ORDEM_DAS_ADESOES,
        descobrir,
        (agora, versao),
        forcar,
    )


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--sigsif", type=Path, default=None)
    argumentos.add_argument("--transacoes", type=Path, default=None)
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--forcar", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if not (opcoes.sigsif or opcoes.transacoes):
        argumentos.error("passe --sigsif e/ou --transacoes (pastas já baixadas)")
    faltam: list[str] = []
    if opcoes.sigsif:
        faltam += _faltam(opcoes.sigsif, ["registrados.csv", MODIFICADOS])
    if opcoes.transacoes:
        faltam += _faltam(opcoes.transacoes, [*carga.ARQUIVOS, carga.MODIFICADOS])
    if faltam:
        log.error("faltam: %s", ", ".join(faltam))
        return 1
    saida = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    versao = exigir_versao_do_codigo()
    log.info("Versão do código: %s", versao)
    agora = pd.Timestamp(datetime.now(UTC))
    resultados: dict[str, dict[str, object]] = {}
    with obter_engine().connect() as conexao:
        descobrir = _pessoas_pela_receita(conexao)
        if opcoes.sigsif:
            resultados[derivadas_b.TABELA_ESTABELECIMENTOS] = montar_estabelecimentos(
                opcoes.sigsif, saida, descobrir, agora, versao, opcoes.forcar
            )
        if opcoes.transacoes:
            resultados[derivadas_b.TABELA_ACORDOS] = montar_acordos(
                opcoes.transacoes, saida, descobrir, agora, versao, opcoes.forcar
            )
            resultados[derivadas_b.TABELA_ADESOES] = montar_adesoes(
                opcoes.transacoes, saida, descobrir, agora, versao, opcoes.forcar
            )
    for tabela, dados in resultados.items():
        log.info("%s: %s", tabela, dados)
    vazias = [t for t, d in resultados.items() if _vazia(d)]
    if vazias:
        log.error("tabela sem nenhuma linha: %s", ", ".join(vazias))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
