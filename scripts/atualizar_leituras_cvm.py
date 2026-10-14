"""Lê os fatos relevantes da CVM e guarda o resumo e o assunto (Research R5 e leitor v2, ADR 0069).

    python -m scripts.atualizar_leituras_cvm             (até 20 fatos dos últimos 30 dias)
    python -m scripts.atualizar_leituras_cvm --lote base/leitor/lote_medicao_v1.csv

Com `--lote`, depois dos fatos recentes o dia é completado com os do lote de medição do leitor v2
(fatos antigos, que não estão no banco; plano do leitor de fatos relevantes), até o máximo.

O texto vem do PDF original no sistema da CVM (RAD). A CVM limita os downloads por endereço: a
coleta baixa poucos documentos, com intervalo de um minuto, e para no primeiro sinal de limite
(uma página de aviso no lugar do PDF), continuando no dia seguinte. Não apaga nada.
"""

import argparse
import csv
import logging
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import requests
import sqlalchemy as sa

from src import leitura, topicos, topicos_modelo
from src.banco.coletas import com_registro
from src.banco.conexao import criar_engine, migrar_para
from src.banco.leituras import (
    RESUMO,
    TOPICO,
    TOPICO_MODELO,
    fatos_sem_leitura,
    gravar_leitura,
)
from src.banco.leituras import lidos as lidos_no_banco
from src.configuracao import url_do_banco
from src.eventos import FONTE_IPE, identificador
from src.links_das_fontes import link_da_fonte

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


def assunto(
    conteudo: bytes, titulo: str, cliente: anthropic.Anthropic | None
) -> tuple[dict, dict | None]:
    """O assunto do fato (leitor v2) pelas regras e, se elas deixam "Outros" e há chave, pelo modelo."""
    texto, _ = _texto(conteudo)
    pelas_regras = topicos.topico_do_documento(titulo, texto)
    pelo_modelo = None
    if cliente is not None and texto and pelas_regras.principal == topicos.OUTROS:
        pelo_modelo = topicos_modelo.ler_com_modelo(cliente, titulo, texto)
    return asdict(pelas_regras), asdict(pelo_modelo) if pelo_modelo else None


Pendente = tuple[
    str, str, date, str, str
]  # (protocolo, cnpj, data, link, título do IPE)


def ler_lote(caminho: Path) -> list[Pendente]:
    """O lote de medição (colunas do IPE da CVM, separado por ;); só links da CVM ou da SEC.

    A chave é a mesma dos eventos do banco: o protocolo, ou "rad-<número do link>" quando a CVM
    não o informa (o IPE de 2003 vem sem protocolo); sem nenhum dos dois, a linha fica de fora.
    """
    with caminho.open(encoding="utf-8") as arquivo:
        return [
            (chave[0], linha["CNPJ_Companhia"],
             date.fromisoformat(linha["Data_Entrega"]), seguro, linha["Assunto"])
            for linha in csv.DictReader(arquivo, delimiter=";")
            if (seguro := link_da_fonte(linha["Link_Download"]))
            and (chave := identificador(linha["Protocolo_Entrega"], "", seguro))
        ]  # fmt: skip


def _do_lote(conexao: sa.Connection, caminho: Path, vagas: int) -> list[Pendente]:
    """Os primeiros do lote ainda sem assunto lido, até preencher as vagas do dia."""
    if vagas <= 0:
        return []
    lote = ler_lote(caminho)
    feitos = lidos_no_banco(
        conexao, FONTE_IPE, TOPICO, [p[0] for p in lote], versao=topicos.VERSAO
    )
    return [p for p in lote if p[0] not in feitos][:vagas]


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--maximo", type=int, default=MAXIMO_POR_VEZ)
    argumentos.add_argument(
        "--lote",
        type=Path,
        help="lote de medição do leitor v2 (CSV do IPE, separado por ;)",
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    cliente = (
        topicos_modelo.cliente_da_chave()
    )  # sem a chave, a camada do modelo fica desligada
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
            if opcoes.lote:
                pendentes += _do_lote(
                    conexao, opcoes.lote, opcoes.maximo - len(pendentes)
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
                pelas_regras, pelo_modelo = assunto(conteudo, titulo, cliente)
                for tipo, resultado in (
                    (TOPICO, pelas_regras),
                    (TOPICO_MODELO, pelo_modelo),
                ):
                    if resultado is not None:
                        gravar_leitura(
                            conexao, FONTE_IPE, protocolo, tipo, cnpj, publicado,
                            resultado, versao=topicos.VERSAO,
                        )  # fmt: skip
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
