"""Carga dos processos judiciais por CNPJ para a base: as tabelas `processos_comunicacoes`,
`processos_partes`, `processos` e `processos_nas_notas` (`base/processos.py`), e as internas do
DataJud, `processos_datajud` e `processos_datajud_movimentos` (`base/processos_datajud.py`, só uso
interno).

    python -m scripts.carga_processos                    (todas as consultas guardadas)
    python -m scripts.carga_processos --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_processos --refazer          (relê mesmo sem consulta nova: código novo)

Lê as consultas do DJEN por companhia (`djen-partes`) e por processo (`djen-processos`), a TPU do CNJ
(`cnj-tpu`) e o cadastro da CVM que o arquivista já guardou no acervo (não baixa nada). Nome de pessoa
física nunca entra na tabela. Saída padrão: `<TICKERLAB_ACERVO>/base/<tabela>/djen.parquet`. Os
números de processo que as companhias citam nas notas da DFP saem da tabela `notas_dfp` da mesma pasta
(`processos_nas_notas/dfp.parquet`), lida pela porta.

A consulta por processo do arquivista lê a `processos_comunicacoes` que esta carga grava: na primeira
semana só a busca pelo nome roda; a partir da segunda, o arquivista busca pelo número os processos que
a carga anterior ligou a uma companhia.
Feita para o servidor de casa (ADR 0031), toda semana depois do arquivista; recusa rodar sem a versão
do código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 nenhuma consulta do DJEN guardada.

Roda: manual (python -m scripts.carga_processos); ver dicionario-da-base.md; citado em
dicionario.py.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import processos, processos_datajud
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_processos")


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
    agora = datetime.now(UTC)
    with obter_engine().connect() as conexao:
        resumo = processos.montar(conexao, pasta, agora, refazer=opcoes.refazer)
        # o DataJud (só uso interno) lê as próprias consultas guardadas: monta mesmo sem DJEN novo
        datajud = processos_datajud.montar(
            conexao, pasta, agora, refazer=opcoes.refazer
        )
    # as notas da DFP não dependem do DJEN: as citações se montam mesmo sem consulta guardada
    log.info("processos nas notas da DFP: %s", processos.montar_citacoes(pasta, agora))
    log.info("processos no DataJud (só uso interno): %s", datajud)
    if not resumo:
        log.warning("nenhuma consulta do DJEN guardada no acervo")
        return 1
    log.info("processos: %s", resumo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
