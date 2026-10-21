"""Leva para `restrito/` os originais que já estão em `bruto/` e trazem nome de pessoa (ADR 0106).

    python -m scripts.mover_acervo_restrito --ensaio    (só lista o que seria movido)
    python -m scripts.mover_acervo_restrito             (move; precisa do "pode" do Tiago)

Para cada coleta de uma fonte de `acervo.FONTES_COM_PESSOA` cujo caminho começa em `bruto/`: confere o
SHA-256 do arquivo contra o registro (arquivo mexido para tudo, nada é movido), move e só então troca o
caminho no registro. Rodar de novo não faz nada. Saída 0 tudo certo; 1 falha de conferência.
"""

import argparse
import gzip
import hashlib
import logging
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

import sqlalchemy as sa

from src import acervo
from src.banco.conexao import criar_engine
from src.banco.modelo import coletas
from src.configuracao import url_do_banco

log = logging.getLogger("mover_acervo_restrito")
PREFIXO_ANTIGO = f"{acervo.PASTA_PUBLICA}/"
PREFIXO_NOVO = f"{acervo.PASTA_RESTRITA}/"


class ErroDeConferencia(RuntimeError):
    """O arquivo no disco não tem o SHA-256 do registro: nada é movido."""


class Movido(NamedTuple):
    de: str
    para: str


def _sha_do_original(arquivo: Path) -> str:
    bruto = arquivo.read_bytes()
    original = gzip.decompress(bruto) if arquivo.name.endswith(".gz") else bruto
    return hashlib.sha256(original).hexdigest()


def _a_mover(conexao: sa.Connection) -> list[sa.Row]:
    return list(
        conexao.execute(
            sa.select(
                coletas.c.id, coletas.c.caminho_do_original, coletas.c.sha256
            ).where(
                coletas.c.fonte.in_(sorted(acervo.FONTES_COM_PESSOA)),
                coletas.c.caminho_do_original.like(f"{PREFIXO_ANTIGO}%"),
            )
        )
    )


def mover(conexao: sa.Connection, pasta: Path, ensaio: bool) -> list[Movido]:
    """Move (ou, no ensaio, só lista) os originais com pessoa; devolve o que foi feito."""
    feitos: list[Movido] = []
    for linha in _a_mover(conexao):
        de = linha.caminho_do_original
        para = PREFIXO_NOVO + de.removeprefix(PREFIXO_ANTIGO)
        origem = pasta / de
        if origem.is_file() and _sha_do_original(origem) != linha.sha256:
            raise ErroDeConferencia(f"SHA-256 diferente do registro: {de}")
        feitos.append(Movido(de, para))
        if ensaio:
            continue
        if origem.is_file():
            destino = pasta / para
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(origem, destino)
        conexao.execute(
            sa.update(coletas)
            .where(coletas.c.id == linha.id)
            .values(caminho_do_original=para)
        )
    return feitos


def main(argv: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    analisador.add_argument("--ensaio", action="store_true")
    ensaio = analisador.parse_args(argv).ensaio
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    pasta = acervo.pasta_do_acervo()
    if pasta is None:
        log.error("acervo desligado")
        return 1
    motor = criar_engine(url_do_banco())
    try:
        with motor.begin() as conexao:
            feitos = mover(conexao, pasta, ensaio)
    except ErroDeConferencia as erro:
        log.error("FALHAS: %s", erro)
        return 1
    log.info("%s %d arquivo(s)", "iria mover" if ensaio else "movidos", len(feitos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
