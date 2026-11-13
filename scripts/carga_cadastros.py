"""Carga dos cadastros que a fonte publica inteiros a cada vez (`base/cadastros_em_retrato.py`) para a base.

    python -m scripts.carga_cadastros                          (as cinco tabelas)
    python -m scripts.carga_cadastros --tabela mte_lista_suja  (só uma; repita a opção para mais)
    python -m scripts.carga_cadastros --pasta /tmp/base        (outra pasta de saída)
    python -m scripts.carga_cadastros --refazer                (relê mesmo sem retrato novo: código novo)

As cinco tabelas: `ans_operadoras`, `susep_cadastro`, `mte_lista_suja`, `ibama_embargos` e `gleif_ponte`.
Até a linha 915 nenhum script as montava, e o acervo de produção não tinha pasta delas. Lê os arquivos que
o arquivista já guardou no acervo (não baixa nada). Só pessoa jurídica com CNPJ de dígito certo entra;
nome e CPF nunca (ADR 0075); empresário individual e MEI ficam marcados em `trata_como_pessoa`, pela
Receita guardada (sem ela, todos marcados). Saída padrão: `<TICKERLAB_ACERVO>/base/<tabela>/<cadastro>.parquet`.
Feita para o servidor de casa (ADR 0031); recusa rodar sem a versão do código (exigência 13 da ADR
0055). Saída 0 quando ao menos uma das pedidas foi montada (a que não tem arquivo guardado sai
em aviso no log); 1 quando nenhuma tem. A pasta de saída resolvida vai para o log.

Roda: manual no servidor de casa, com o "pode" da Diretoria (linha 915; o agendamento fica para depois de
20/11/2026).
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import (
    ans_operadoras,
    gleif,
    ibama_embargos,
    mte_lista_suja,
    susep_cadastro,
)
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_cadastros")

# A ordem é a de montagem: do menor arquivo ao maior (o termo de embargo do IBAMA tem ~200 MB por retrato)
MODULOS = {
    modulo.TABELA: modulo
    for modulo in (
        ans_operadoras,
        susep_cadastro,
        mte_lista_suja,
        gleif,
        ibama_embargos,
    )
}


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--refazer", action="store_true")
    argumentos.add_argument(
        "--tabela", action="append", choices=sorted(MODULOS), default=None
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    log.info("Pasta de saída: %s", pasta.resolve())
    pedidas = [t for t in MODULOS if t in (opcoes.tabela or MODULOS)]
    montadas = 0
    with obter_engine().connect() as conexao:
        for tabela in pedidas:
            resumo = MODULOS[tabela].montar(
                conexao, pasta, datetime.now(UTC), refazer=opcoes.refazer
            )
            if not resumo:
                log.warning("%s: nenhum arquivo guardado no acervo", tabela)
                continue
            montadas += 1
            for cadastro, contagem in resumo.items():
                log.info("%s/%s: %s", tabela, cadastro, contagem)
    return 0 if montadas else 1


if __name__ == "__main__":
    raise SystemExit(main())
