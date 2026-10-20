"""Segunda cópia dos negócios do pregão da B3, no VPS (ADR 0073; `base/arquivo/copia_b3.py`).

    python - --pasta /app/pesquisa/b3-negocios < scripts/copiar_b3_negocios.py

Roda no cron do VPS (23h e 3h), num contêiner próprio, sem o banco e sem a rede `db`: o dado da B3
é só pesquisa e fica numa pasta que o app não monta. Baixa os dias da janela que ainda não estão
inteiros e apaga os pregões com mais de 90 dias (a casa guarda tudo).

Saída 0 tudo certo; 1 alguma falha, com a última linha `FALHAS: ...` (vai para o aviso do Kuma).
"""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from base.arquivo.cliente_http import ClienteHttp
from base.arquivo.coleta import (
    PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS,
    FreioDeDisco,
    espaco_do_disco,
)
from base.arquivo.copia_b3 import RETENCAO_EM_DIAS, apagar_antigos, copiar_janela
from base.arquivo.fontes import FUSO_DA_B3

log = logging.getLogger("copiar_b3_negocios")

PAUSA = PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS
TAMANHO_MAXIMO_DO_RESUMO = 300  # o resumo vai no endereço do push do Kuma


def agora() -> datetime:
    """O relógio da rodada; o teste troca esta função para fixar o momento."""
    return datetime.now(UTC)


def _avisar(problemas: list[str]) -> int:
    linha = "FALHAS: b3-negocios no VPS: " + "; ".join(problemas)
    print(linha[:TAMANHO_MAXIMO_DO_RESUMO])
    return 1


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", required=True, type=Path)
    argumentos.add_argument("--retencao", type=int, default=RETENCAO_EM_DIAS)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    momento = agora()
    try:
        rodada = copiar_janela(
            ClienteHttp(), opcoes.pasta, momento, pausa=PAUSA, espaco=espaco_do_disco
        )
    except FreioDeDisco as erro:
        return _avisar([f"FreioDeDisco: {erro}"])
    apagados = apagar_antigos(
        opcoes.pasta, momento.astimezone(FUSO_DA_B3).date(), opcoes.retencao
    )
    log.info(
        "b3-negocios: %d novos, %d iguais, %d já inteiros, %d sem arquivo, %d falhas; "
        "%d pregões antigos apagados",
        rodada.novos,
        rodada.iguais,
        rodada.pulados,
        rodada.sem_arquivo,
        len(rodada.falhas),
        len(apagados),
    )
    return _avisar(rodada.falhas) if rodada.falhas else 0


if __name__ == "__main__":
    sys.exit(main())
