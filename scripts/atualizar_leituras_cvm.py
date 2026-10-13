"""Lê os fatos relevantes da CVM e guarda o resumo do algoritmo próprio (Research R5).

    python -m scripts.atualizar_leituras_cvm             (até 20 fatos dos últimos 30 dias)

O texto vem do PDF original no sistema da CVM (RAD). A CVM limita os downloads por endereço: a
coleta baixa poucos documentos, com intervalo de um minuto, e para no primeiro sinal de limite
(uma página de aviso no lugar do PDF), continuando no dia seguinte. Não apaga nada.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import sqlalchemy as sa

from src import leitura
from src.banco.coletas import com_registro
from src.banco.conexao import criar_engine, migrar_para
from src.banco.leituras import RESUMO, fatos_sem_leitura, gravar_leitura
from src.configuracao import url_do_banco
from src.eventos import FONTE_IPE

log = logging.getLogger("tickerlab.leituras")
CATEGORIA = "Fato Relevante"
MAXIMO_POR_VEZ = 20
PAUSA_ENTRE_DOWNLOADS = 60  # segundos: a CVM limita os downloads por endereço
DIAS = 30


def _baixar_da_fonte(url: str) -> bytes:
    resposta = requests.get(
        url, timeout=120, headers={"User-Agent": "TickerLab (tickerlab.com.br)"}
    )
    resposta.raise_for_status()
    return resposta.content


# cada arquivo baixado fica no registro de coletas (Radar, PR 1)
baixar = com_registro("cvm-documentos", _baixar_da_fonte)


def ler(conteudo: bytes) -> dict:
    """O resumo do documento (um PDF só de imagem vira um resumo vazio, com o motivo)."""
    try:
        texto = leitura.texto_do_pdf(conteudo)
    except Exception:  # noqa: BLE001 (PDF malformado: guarda o motivo e segue)
        return {"motivo": "PDF ilegível.", "versao": leitura.VERSAO}
    if len(texto.split()) < leitura.MIN_PALAVRAS_POR_FRASE:
        return {"motivo": "O PDF é só imagem (escaneado): não há texto para ler.",
                "versao": leitura.VERSAO}  # fmt: skip
    return leitura.resumir_fato_relevante(texto).para_guardar()


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--maximo", type=int, default=MAXIMO_POR_VEZ)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    lidos = 0
    try:
        with motor.connect() as conexao:
            pendentes = fatos_sem_leitura(
                conexao,
                FONTE_IPE,
                CATEGORIA,
                hoje - timedelta(days=DIAS),
                opcoes.maximo,
            )
        for i, (protocolo, cnpj, publicado, link) in enumerate(pendentes):
            if i:
                time.sleep(PAUSA_ENTRE_DOWNLOADS)
            conteudo = baixar(link)
            if not leitura.e_pdf(conteudo):
                log.warning(
                    "A CVM devolveu uma página no lugar do PDF (limite): para e continua amanhã."
                )
                break
            with motor.begin() as conexao:
                gravar_leitura(
                    conexao,
                    FONTE_IPE,
                    protocolo,
                    RESUMO,
                    cnpj,
                    publicado,
                    ler(conteudo),
                )
            lidos += 1
        log.info("Fatos relevantes lidos: %s de %s pendentes", lidos, len(pendentes))
    except (requests.RequestException, sa.exc.SQLAlchemyError) as erro:
        log.error("Leitura interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
