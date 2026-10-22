"""Troca da chave-mestra da sala de dados, no servidor (RIPD da sala, risco R-S2).

    python -m scripts.trocar_chave_da_sala situacao
    python -m scripts.trocar_chave_da_sala reembrulhar
    python -m scripts.trocar_chave_da_sala pode-retirar 1

`situacao` mostra quantas operações usam cada versão; `reembrulhar` passa a chave de cada operação
para a versão mais nova da variável (idempotente; não recifra arquivo); `pode-retirar N` sai com 0
só se a versão N já não embrulha nenhuma operação. Roda no contêiner da API, com o `.env.sala`
lido; nunca imprime chave. Roteiro completo: `configurar-chave-da-sala.ps1` (passo "adicionar versão").
"""

import argparse
import logging
import sys

import sqlalchemy as sa

from src.banco.conexao import criar_engine
from src.configuracao import url_do_banco
from src.sala import cofre, troca_de_chave

log = logging.getLogger("tickerlab.troca_da_chave")


def _executar(conexao: sa.Connection, comando: str, versao: int | None) -> int:
    if comando == "situacao":
        for numero, total in sorted(troca_de_chave.uso_por_versao(conexao).items()):
            log.info("v%s: %s operação(ões)", numero, total)
        log.info("versões na variável: %s", sorted(cofre.chaves_mestras()))
    elif comando == "reembrulhar":
        resultado = troca_de_chave.reembrulhar(conexao)
        log.info(
            "Reembrulhadas %s operação(ões) para a v%s; %s já estavam nela",
            resultado.reembrulhadas,
            resultado.versao_nova,
            resultado.ja_na_versao_nova,
        )
    else:
        assert versao is not None
        troca_de_chave.pode_retirar(conexao, versao)
        log.info("A v%s pode sair da variável: nenhuma operação a usa", versao)
    return 0


def main(argumentos: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("comando", choices=["situacao", "reembrulhar", "pode-retirar"])
    parser.add_argument("versao", nargs="?", type=int)
    dados = parser.parse_args(argumentos)
    if dados.comando == "pode-retirar" and dados.versao is None:
        parser.error("pode-retirar pede o número da versão")
    motor = criar_engine(url_do_banco())
    try:
        with motor.begin() as conexao:
            return _executar(conexao, dados.comando, dados.versao)
    except (cofre.ChaveDaSalaAusenteError, troca_de_chave.VersaoEmUsoError) as erro:
        log.error("%s", erro)
        return 1
    except (cofre.CifraInvalidaError, sa.exc.SQLAlchemyError) as erro:
        log.error("Troca interrompida (nada foi gravado): %s", erro.__class__.__name__)
        return 1
    finally:
        motor.dispose()


if __name__ == "__main__":
    sys.exit(main())
