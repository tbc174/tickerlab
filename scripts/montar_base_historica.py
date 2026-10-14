"""Monta a base histórica da CVM (série B1) a partir dos originais do acervo (`base/historico.py`).

    python -m scripts.montar_base_historica                       (todas as tabelas)
    python -m scripts.montar_base_historica eventos negociacoes   (só estas)
    python -m scripts.montar_base_historica cnpj_situacao_especial (retratos do CNPJ, B2)
    python -m scripts.montar_base_historica auditores trocas_de_auditor (B3; as trocas leem os auditores)
    python -m scripts.montar_base_historica --pasta /tmp/base     (outra pasta de saída)

Saída padrão: `<TICKERLAB_ACERVO>/base/<tabela>/<ano>.parquet`. Roda no servidor de casa (ADR 0031),
depois que o arquivista guardou os arquivos `cvm-hist-*`. Saída 0 tudo certo; 1 algum original não
abriu (as outras tabelas e anos continuam).
"""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from base import auditores, historico, rotulos
from src import acervo
from src.banco.conexao import obter_engine

log = logging.getLogger("montar_base_historica")

# retratos mensais da "situação especial" do CNPJ (B2, parte 2): não são arquivos anuais
CNPJ = "cnpj_situacao_especial"
# trocas de auditor (B3): saem de todos os anos de `auditores`, por isso vêm depois deles
TROCAS = "trocas_de_auditor"
TODAS = [*historico.TABELAS, CNPJ, TROCAS]


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("tabelas", nargs="*", choices=[*TODAS, []], default=[])
    argumentos.add_argument("--pasta", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    agora = datetime.now(UTC)
    falhou = False
    with obter_engine().connect() as conexao:
        for nome in opcoes.tabelas or TODAS:
            if nome == CNPJ:
                meses = rotulos.montar_situacao_especial(conexao, pasta, agora)
                log.info("%s: %s", CNPJ, meses or "nenhum mês do CNPJ guardado")
                continue
            if nome == TROCAS:
                log.info("%s: %d trocas", TROCAS, auditores.montar_trocas(pasta, agora))
                continue
            try:
                linhas = historico.montar(nome, conexao, pasta, agora)
            except historico.ArquivoIlegivel as erro:
                log.error("%s", erro)
                falhou = True
                continue
            anos = ", ".join(f"{ano}: {n}" for ano, n in sorted(linhas.items()))
            log.info(
                "%s: %d anos (%s)",
                nome,
                len(linhas),
                anos or "nenhum original guardado",
            )
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
