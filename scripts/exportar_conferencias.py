"""Exporta as conferências por CNPJ para a ficha do Ficha Clara: `base/conferencias_por_cnpj.py`.

    python -m scripts.exportar_conferencias --destino <arquivo.sqlite>
    python -m scripts.exportar_conferencias --destino <arquivo.sqlite> --vista <vista do CNPJ>

Lê as tabelas da base (sanções, dívida ativa, licenças, incentivos e processos do DJEN), o cadastro da CVM
guardado no acervo (quem a busca do DJEN cobre) e, com `--vista`, as ligações do grupo econômico, e grava um SQLite só de leitura que o portal abre. Só entra o que é vigente e já público no dia,
sem pessoa física. Feita para o servidor de casa (ADR 0031), depois das cargas do mês; recusa rodar sem a
versão do código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 nenhuma fonte na base.
"""

import argparse
import logging
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base import conferencias_por_cnpj
from base.cadastro import cadastro_do_acervo
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.exportar_conferencias")


def cadastro_da_cvm() -> pd.DataFrame | None:
    """O cadastro da CVM mais recente do acervo; None sem ele ou sem o banco (a ficha então não
    marca nenhuma companhia aberta como "não encontrada" nos processos)."""
    try:
        with obter_engine().connect() as conexao:
            achado = cadastro_do_acervo(conexao)
    except (sa.exc.SQLAlchemyError, OSError) as erro:
        log.warning("cadastro da CVM indisponível: %s", type(erro).__name__)
        return None
    return achado[0] if achado else None


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--destino", type=Path, required=True)
    argumentos.add_argument("--base", type=Path, default=None)
    argumentos.add_argument("--vista", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    base = (
        opcoes.base
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    estado = conferencias_por_cnpj.montar(
        base, opcoes.destino, opcoes.vista, cadastro=cadastro_da_cvm()
    )
    for fonte in estado["fontes"]:
        log.info(
            "%s: %s empresas, conferido até %s",
            fonte["tabela"],
            fonte["empresas"],
            fonte["conferido_ate"],
        )
    if not estado["fontes"]:
        log.warning("nenhuma fonte de conferência na base")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
