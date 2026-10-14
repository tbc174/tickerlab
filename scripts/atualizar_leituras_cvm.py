"""Lê os fatos relevantes da CVM e guarda o resumo e o assunto (Research R5 e leitor v2, ADR 0069).

    python -m scripts.atualizar_leituras_cvm             (até 20 fatos dos últimos 30 dias)

O texto vem do PDF original no sistema da CVM (RAD). A CVM limita os downloads por endereço: a
coleta baixa poucos documentos, com intervalo de um minuto, e para no primeiro sinal de limite
(uma página de aviso no lugar do PDF), continuando no dia seguinte. Não apaga nada.
"""

import argparse
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import sqlalchemy as sa

from src import leitura, topicos
from src.banco.coletas import com_registro
from src.banco.conexao import criar_engine, migrar_para
from src.banco.leituras import RESUMO, TOPICO, fatos_sem_leitura, gravar_leitura
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


def _texto(conteudo: bytes) -> tuple[str, str | None]:
    """(texto, motivo): o motivo diz por que não há texto (PDF malformado ou só imagem)."""
    try:
        texto = leitura.texto_do_pdf(conteudo)
    except Exception:  # noqa: BLE001 (PDF malformado: guarda o motivo e segue)
        return "", "PDF ilegível."
    if len(texto.split()) < leitura.MIN_PALAVRAS_POR_FRASE:
        return "", "O PDF é só imagem (escaneado): não há texto para ler."
    return texto, None


def ler(conteudo: bytes) -> dict:
    """O resumo do documento (um PDF sem texto vira um resumo vazio, com o motivo)."""
    texto, motivo = _texto(conteudo)
    if motivo:
        return {"motivo": motivo, "versao": leitura.VERSAO}
    return leitura.resumir_fato_relevante(texto).para_guardar()


def assunto(conteudo: bytes, titulo: str) -> dict:
    """O assunto do fato (leitor v2): o título decide; se for genérico, o texto."""
    texto, _ = _texto(conteudo)
    return asdict(topicos.topico_do_documento(titulo, texto))


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
        for i, (protocolo, cnpj, publicado, link, titulo) in enumerate(pendentes):
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
                gravar_leitura(
                    conexao,
                    FONTE_IPE,
                    protocolo,
                    TOPICO,
                    cnpj,
                    publicado,
                    assunto(conteudo, titulo),
                    versao=topicos.VERSAO,
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
