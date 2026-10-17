"""Carga da dívida ativa da União (PGFN) para a base: a tabela `pgfn_divida` (`base/pgfn.py`).

    python -m scripts.carga_pgfn                    (todos os retratos guardados)
    python -m scripts.carga_pgfn --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_pgfn --refazer          (relê os ZIPs já montados: código novo)

Lê os ZIPs da fonte `pgfn-divida` que o arquivista já guardou no acervo (não baixa nada). Só pessoa
jurídica com CNPJ de dígito certo entra; nome e CPF nunca (ADR 0075). Duas leituras de cada ZIP: a
1ª, leve, junta as raízes dos devedores para perguntar à Receita guardada quais são empresário
individual ou MEI (`trata_como_pessoa`); a 2ª soma as inscrições, um CSV de cada vez. Saída padrão:
`<TICKERLAB_ACERVO>/base/pgfn_divida/<AAAA-MM>/<sistema>-<região>-<1º caractere>.parquet`
(11 pedaços por CSV: ~1 GB no maior). Feita para o servidor de
casa (ADR 0031); recusa rodar sem a versão do código (exigência 13 da ADR 0055). Saída 0 tudo certo;
1 nenhum ZIP da PGFN guardado.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import pgfn
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_pgfn")


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--refazer", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    with obter_engine().connect() as conexao:
        resumo = pgfn.montar(conexao, pasta, datetime.now(UTC), refazer=opcoes.refazer)
    if not resumo:
        log.warning("nenhum ZIP da PGFN guardado no acervo")
        return 1
    for arquivo, contagem in resumo.items():
        log.info("%s: %s", arquivo, contagem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
