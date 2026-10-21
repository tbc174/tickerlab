"""Carga do CNPJ da Receita na base, um mês por vez (ADR 0106, PR 5). Roda no servidor de casa.

    python -m scripts.carga_receita_retrato --base <pasta> --restrita <pasta> --ensaio   (só lista os meses)
    python -m scripts.carga_receita_retrato --base <pasta> --restrita <pasta>            (carrega os que faltam)
    python -m scripts.carga_receita_retrato ... --ate 2026-10                            (para neste mês)

Para cada mês pendente (retoma do último gravado): confere 30 GB livres, baixa os ZIPs de Estabelecimentos,
Simples e Sócios, anota o SHA-256 de cada um, lê em partes, grava o vigente e as mudanças em `--base` e os
nomes de sócios pessoa física só em `--restrita`, e apaga os ZIPs. O ZIP dos meses âncora (05/2023, 01/2024,
01/2025, 01/2026) vai para o acervo (`--ancoras`). A chave dos pseudônimos vem de `TICKERLAB_PESSOAS_CHAVE`
ou de `/etc/tickerlab/pessoas.chave`; sem ela nada roda. Saída 0 tudo certo; 1 falha (última linha `FALHAS:`).
"""

import argparse
import logging
import shutil
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from base.arquivo.cliente_http import ClienteHttp
from base.arquivo.fontes import arquivos_do_mes, meses_do_cnpj
from base.pessoas.chave import ErroSemChave, ler_chave
from base.receita_retrato import (
    ErroDeCpfInteiro,
    ErroDeLayout,
    ler_estabelecimentos,
    ler_qsa,
    ler_simples,
)
from scripts import carga_receita_mes as carga
from src import acervo

log = logging.getLogger("tickerlab.carga_receita_retrato")
NOMES = ("Estabelecimentos", "Simples", "Socios")
MESES_ANCORA = frozenset({"2023-05", "2024-01", "2025-01", "2026-01"})
TAMANHO_MAXIMO_DO_RESUMO = 300  # a linha `FALHAS:` vai no endereço do push do Kuma


def _baixar_do_mes(
    cliente: ClienteHttp, mes: str, temporaria: Path
) -> dict[str, list[Path]]:
    """Baixa os ZIPs do mês e devolve os caminhos por tipo (`Estabelecimentos`, `Simples`, `Socios`)."""
    por_tipo: dict[str, list[Path]] = {nome: [] for nome in NOMES}
    for alvo in arquivos_do_mes(cliente, mes, NOMES):
        destino = temporaria / alvo.url.rsplit("/", 1)[-1].split("?")[0]
        cliente.baixar(alvo.url, destino)
        for nome in NOMES:
            if destino.name.startswith(nome):
                por_tipo[nome].append(destino)
    return por_tipo


def _guardar_ancora(mes: str, zips: dict[str, list[Path]]) -> None:
    quando = datetime(int(mes[:4]), int(mes[5:]), 1, tzinfo=UTC)
    for arquivo in (a for lista in zips.values() for a in lista):
        sha256 = carga.sha256_do_arquivo(arquivo)
        copia = arquivo.with_name(arquivo.name + ".ancora")
        shutil.copyfile(arquivo, copia)
        acervo.guardar_arquivo(
            carga.FONTE, f"cnpj/{mes}/{arquivo.name}", copia, sha256, quando
        )


def carregar_mes(
    mes: str,
    pasta: Path,
    restrita: Path,
    chave: bytes,
    baixar: Callable[[str, Path], dict[str, list[Path]]],
) -> None:
    carga.exigir_disco(pasta)
    with tempfile.TemporaryDirectory(dir=pasta.parent) as temporaria:
        zips = baixar(mes, Path(temporaria))
        arquivos = {
            a.name: carga.sha256_do_arquivo(a) for z in zips.values() for a in z
        }
        if mes in MESES_ANCORA:
            _guardar_ancora(mes, zips)
        carga.processar_mes(
            mes,
            pasta,
            restrita,
            estabelecimentos=(
                p for z in zips["Estabelecimentos"] for p in ler_estabelecimentos(z)
            ),
            simples=(p for z in zips["Simples"] for p in ler_simples(z)),
            qsa=ler_qsa(zips["Socios"]),
            chave_de_pessoas=chave,
            arquivos=arquivos,
        )


def main(argv: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    analisador.add_argument("--base", type=Path, required=True)
    analisador.add_argument("--restrita", type=Path, required=True)
    analisador.add_argument(
        "--ate", default=None, help="último mês a carregar (AAAA-MM)"
    )
    analisador.add_argument("--ensaio", action="store_true")
    opcoes = analisador.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cliente = ClienteHttp()
    meses = [m for m in meses_do_cnpj(cliente) if opcoes.ate is None or m <= opcoes.ate]
    pendentes = carga.pendentes(meses, opcoes.base)
    log.info("meses pendentes: %s", ", ".join(pendentes) or "nenhum")
    if opcoes.ensaio:
        return 0
    try:
        chave = ler_chave()
        for mes in pendentes:
            log.info("carregando %s", mes)
            carregar_mes(
                mes,
                opcoes.base,
                opcoes.restrita,
                chave,
                lambda m, t: _baixar_do_mes(cliente, m, t),
            )
    except (ErroSemChave, carga.PoucoDisco, ErroDeLayout, ErroDeCpfInteiro) as erro:
        print(
            f"FALHAS: carga do CNPJ: {type(erro).__name__}"[:TAMANHO_MAXIMO_DO_RESUMO]
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
