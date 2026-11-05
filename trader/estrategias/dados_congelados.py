"""Congelamento, por hash, dos arquivos que as rodadas da P0-4, da P0-5 e da C-1 leem.

A 1ª tentativa da C-1 parou porque os arquivos de entrada da P0-4 e da P0-5 foram regravados depois
das rodadas delas e os antigos não existiam mais (`docs/resultado-c1-tentativa-1.md`). Para não
repetir: antes de rodar, cada arquivo lido ganha um SHA-256 num manifesto e uma cópia em
`pesquisa_quant/congelados/<data>/`; a marca do manifesto entra na especificação de cada tentativa,
e o rodador confere no fim que nada mudou durante a rodada.

O que entra é o que os carregadores leem do desenvolvimento: a pasta da pesquisa (F-B3, Binance,
funding e as séries do BCB guardadas até 08/09/2023), os preços do `dados_mt5/` e, do acervo, a
curva de juros (lida inteira e cortada depois, como o carregador faz) e os arquivos anuais até 2023.
Ler o byte para o hash não usa o dado: o corte do holdout continua nos carregadores.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from trader.estrategias import dados_f_b3, dados_p0_3

ULTIMO_ANO = dados_f_b3.ULTIMO_ANO
FIM_DAS_SERIES_GUARDADAS = (
    "20230908"  # o fim do desenvolvimento no nome dos caches do BCB
)
PASTAS_DA_PESQUISA = ("f_b3", "binance", "binance_brl", "funding")
PASTAS_ANUAIS_DO_ACERVO = ("fca_geral", "demonstracoes", "eventos", "insolvencia")
ARQUIVOS_DO_FCA = ("fca/emissores.parquet", "fca/tickers.parquet")
NOME_DO_MANIFESTO = "SHA256SUMS.json"
BLOCO_DE_LEITURA = 1 << 20


def _arquivos(pasta: Path) -> Iterator[Path]:
    return (c for c in sorted(pasta.rglob("*")) if c.is_file())


def _cache_do_desenvolvimento(caminho: Path) -> bool:
    """`cdi_20090102_20230908.parquet` entra; o do papel (`cdi_20261010_...`) não."""
    return (
        caminho.suffix == ".parquet"
        and caminho.stem.rsplit("_", 1)[-1] == FIM_DAS_SERIES_GUARDADAS
    )


def _anual_ate_o_fim(caminho: Path) -> bool:
    """`2015.parquet` entra; `2024.parquet` e a versão anterior `2015.v1.parquet` não."""
    return (
        caminho.suffix == ".parquet"
        and caminho.stem.isdigit()
        and int(caminho.stem) <= ULTIMO_ANO
    )


def arquivos_lidos(
    pesquisa: Path = dados_p0_3.PASTA_DA_PESQUISA,
    mt5: Path = dados_p0_3.PASTA_DO_MT5,
    acervo: Path = dados_f_b3.PASTA_DO_ACERVO,
) -> dict[str, Path]:
    """Nome no manifesto (`origem/caminho relativo`) → arquivo de verdade."""
    achados: dict[str, Path] = {}

    def guardar(origem: str, raiz: Path, caminho: Path) -> None:
        achados[f"{origem}/{caminho.relative_to(raiz).as_posix()}"] = caminho

    for nome in PASTAS_DA_PESQUISA:
        for c in _arquivos(pesquisa / nome):
            guardar("pesquisa", pesquisa, c)
    for c in sorted(pesquisa.glob("*.parquet")):
        if _cache_do_desenvolvimento(c):
            guardar("pesquisa", pesquisa, c)
    for c in _arquivos(mt5):
        guardar("mt5", mt5, c)
    for c in sorted((acervo / "curva_juros").glob("*.parquet")):
        guardar("acervo", acervo, c)
    for nome in PASTAS_ANUAIS_DO_ACERVO:
        for c in sorted((acervo / nome).glob("*.parquet")):
            if _anual_ate_o_fim(c):
                guardar("acervo", acervo, c)
    for relativo in ARQUIVOS_DO_FCA:
        guardar("acervo", acervo, acervo / relativo)
    return achados


def sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(BLOCO_DE_LEITURA):
            resumo.update(bloco)
    return resumo.hexdigest()


def manifesto(arquivos: dict[str, Path]) -> dict[str, str]:
    return {nome: sha256(caminho) for nome, caminho in sorted(arquivos.items())}


def marca(manifesto_: dict[str, str]) -> str:
    """Um hash só para o manifesto inteiro: é o que vai na especificação da tentativa."""
    texto = json.dumps(manifesto_, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def congelar(destino: Path, arquivos: dict[str, Path] | None = None) -> str:
    """Copia os arquivos para `destino` com o manifesto e devolve a marca.

    Rodar de novo com os mesmos arquivos não copia nada e devolve a mesma marca; com arquivos
    diferentes, recusa (um congelamento não se sobrescreve).
    """
    arquivos = arquivos_lidos() if arquivos is None else arquivos
    atual = manifesto(arquivos)
    caminho_do_manifesto = destino / NOME_DO_MANIFESTO
    if caminho_do_manifesto.exists():
        gravado = json.loads(caminho_do_manifesto.read_text(encoding="utf-8"))
        if gravado != atual:
            raise RuntimeError(
                f"{destino} já guarda outros arquivos; congele numa pasta nova"
            )
        return marca(atual)
    for nome, caminho in arquivos.items():
        copia = destino / nome
        copia.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(caminho, copia)
        if sha256(copia) != atual[nome]:
            raise RuntimeError(f"a cópia de {nome} não bate com o original")
    caminho_do_manifesto.write_text(
        json.dumps(atual, indent=1, sort_keys=True), encoding="utf-8"
    )
    return marca(atual)


def exigir_a_mesma_marca(
    esperada: str, arquivos: dict[str, Path] | None = None
) -> None:
    """Depois da rodada: algum arquivo mudou no meio (a cópia diária do acervo, por exemplo)?"""
    arquivos = arquivos_lidos() if arquivos is None else arquivos
    if marca(manifesto(arquivos)) != esperada:
        raise RuntimeError(
            "os arquivos de entrada mudaram durante a rodada; a tentativa é defeito de dado"
        )


FUSO = ZoneInfo("America/Sao_Paulo")
PASTA_DOS_CONGELADOS = dados_p0_3.PASTA_DA_PESQUISA / "congelados"


def congelar_hoje() -> str:
    """O que os rodadores chamam antes de registrar: congela em `congelados/<hoje>/`."""
    return congelar(PASTA_DOS_CONGELADOS / f"{datetime.now(FUSO):%Y-%m-%d}")
