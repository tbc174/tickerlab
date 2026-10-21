"""Expurgo diário da sala de dados: apaga as operações vencidas e os arquivos delas (LGPD, D14).

    python -m scripts.expurgar_salas

Operação cujo prazo de guarda (`retencao_ate`) já passou some do banco (junto com a chave dela, o
que deixa os arquivos ilegíveis na hora), do disco e, em até 14 dias, do backup (`sala-*.tar.age`).
Pastas sem operação também são apagadas. Pensado para rodar uma vez por dia (cron, de madrugada,
antes do backup da sala). Nenhum nome de operação, de arquivo ou de pessoa aparece nos registros
(logs): só as contagens. Sai com erro (1) se algo ficou por apagar, para o Kuma avisar.
"""

import logging
import sys

import sqlalchemy as sa

from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.sala import expurgo, retencao

log = logging.getLogger("tickerlab.expurgo")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.begin() as conexao:
            resultado = expurgo.expurgar(conexao, hoje=retencao.hoje_em_brasilia())
    except sa.exc.SQLAlchemyError as erro:
        log.error("Expurgo das salas interrompido: %s", erro.__class__.__name__)
        return 1
    finally:
        motor.dispose()
    log.info(
        "Expurgo das salas: %s operações vencidas, %s pastas órfãs, %s falhas no disco",
        resultado.operacoes_vencidas,
        resultado.pastas_orfas,
        resultado.falhas_no_disco,
    )
    return 1 if resultado.falhas_no_disco else 0


if __name__ == "__main__":
    sys.exit(main())
