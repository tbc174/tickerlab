"""Coleta em gotas dos documentos de M&A do IPE no sistema de documentos da CVM (RAD; `base/ma_textos.py`).

    python -m scripts.coletar_ma_textos                       (até 25 documentos)
    python -m scripts.coletar_ma_textos --maximo 5
    python -m scripts.coletar_ma_textos --pedidos LISTA.txt   (estes protocolos primeiro, um por linha)

A lista é a de `ma_candidatos` (`base/ma_ipe.py`), montada dos arquivos anuais do IPE já guardados no
acervo. A ordem: os protocolos pedidos, depois os fatos relevantes com tipo e os editais de OPA, os
fatos genéricos e por fim os comunicados; do mais novo ao mais velho em cada grupo. Cada documento vai
bruto para o acervo com registro (fonte `cvm-ipe-ma`, com SHA-256) e o texto para
`<acervo>/ma/textos/<protocolo>.txt` (`ma_textos.nome_do_texto`; cada reentrega tem protocolo próprio, como na amostra de ouro). O que já veio, ou que a CVM disse não existir, não é pedido de novo.

A CVM limita os downloads por endereço: uma pausa entre os pedidos e, com duas páginas seguidas no
lugar do documento, a coleta para sem erro e continua na próxima rodada. Uma página sozinha conta como
tentativa daquele documento (ele pode estar quebrado na fonte); depois de três, ele vai para o fim da
fila. Roda de hora em hora aos 30 min, entre os ratings (xx:05) e a rotulagem por IA (xx:40). Recusa
rodar sem a versão do código (exigência 13 da ADR 0055).
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base import ma_ipe
from base import ma_textos as mt
from src import acervo, leitura, rede
from src.banco.coletas import com_registro
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import coletas
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.coletar_ma_textos")
PAUSA_ENTRE_DOWNLOADS = 60  # segundos: a CVM limita os downloads por endereço
MAXIMO_POR_RODADA = 25
PAGINAS_SEGUIDAS_PARA_PARAR = (
    2  # uma página pode ser o documento quebrado; duas, o limite
)
NAO_ENCONTRADO = 404
JA_RESOLVIDO = ("ok", "nao_encontrado")


class LimiteDaCVM(Exception):
    """A CVM devolveu uma página (ou um PDF pela metade) no lugar do documento."""


@dataclass(frozen=True)
class Rodada:
    pedidos: int
    textos: int
    sem_texto: int
    paginas: int


def conferir_documento(conteudo: bytes | None) -> bytes | None:
    """O documento como veio; `None` (não existe) passa; página ou PDF cortado é o limite (a mesma
    regra da rotulagem por IA, que baixou os textos da amostra de ouro)."""
    if conteudo is not None and leitura.parece_limite_da_cvm(
        leitura.formato_do_documento(conteudo)
    ):
        raise LimiteDaCVM("a CVM devolveu uma página no lugar do documento")
    return conteudo


def _baixar_da_fonte(url: str) -> bytes | None:
    resposta = rede.obter(
        url, timeout=120, headers={"User-Agent": "TickerLab (contato@tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return conferir_documento(resposta.content)


baixar = com_registro(mt.FONTE_DOS_DOCUMENTOS, _baixar_da_fonte)


def _ja_resolvidos(conexao: sa.Connection) -> set[str]:
    return set(
        conexao.execute(
            sa.select(coletas.c.url).where(
                coletas.c.fonte == mt.FONTE_DOS_DOCUMENTOS,
                coletas.c.situacao.in_(JA_RESOLVIDO),
            )
        ).scalars()
    )


def _paginas_por_documento(conexao: sa.Connection) -> dict[str, int]:
    """Quantas vezes cada documento voltou página da CVM."""
    linhas = conexao.execute(
        sa.select(coletas.c.url, sa.func.count())
        .where(
            coletas.c.fonte == mt.FONTE_DOS_DOCUMENTOS,
            coletas.c.situacao == "falhou",
            coletas.c.detalhe == LimiteDaCVM.__name__,
        )
        .group_by(coletas.c.url)
    ).all()
    return {url: int(n) for url, n in linhas}


def ler_pedidos(arquivo: Path | None) -> set[str]:
    """Os protocolos de um arquivo (um por linha; linha vazia e `#` não contam)."""
    if arquivo is None:
        return set()
    linhas = (
        linha.strip() for linha in arquivo.read_text(encoding="utf-8").splitlines()
    )
    return {linha for linha in linhas if linha and not linha.startswith("#")}


def coletar(fila: pd.DataFrame, maximo: int, pasta_dos_textos: Path) -> Rodada:
    """Baixa até `maximo` documentos da fila, com pausa, e grava o texto de cada um."""
    pedidos = textos = sem_texto = paginas = seguidas = 0
    for linha in fila.head(maximo).itertuples(index=False):
        if pedidos:
            time.sleep(PAUSA_ENTRE_DOWNLOADS)
        pedidos += 1
        try:
            conteudo = baixar(linha.link)
        except LimiteDaCVM:
            paginas += 1
            seguidas += 1
            if seguidas >= PAGINAS_SEGUIDAS_PARA_PARAR:
                log.warning("A CVM devolveu páginas seguidas (limite): para aqui.")
                break
            continue
        seguidas = 0
        if conteudo is None:
            continue
        texto = mt.texto_do_documento(conteudo, linha.categoria)
        mt.gravar_texto(pasta_dos_textos, mt.nome_do_texto(linha.protocolo), texto)
        textos += bool(texto)
        sem_texto += not texto
    return Rodada(pedidos, textos, sem_texto, paginas)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--maximo", type=int, default=MAXIMO_POR_RODADA)
    argumentos.add_argument("--pedidos", type=Path, help="protocolos que vêm primeiro")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    pasta = acervo.pasta_do_acervo()
    if pasta is None:
        log.error("Sem acervo (%s desligado): nada a fazer.", acervo.VARIAVEL_DA_PASTA)
        return 1
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            candidatos, _ = ma_ipe.candidatos_guardados(conexao)
            resolvidos = _ja_resolvidos(conexao)
            tentativas = _paginas_por_documento(conexao)
    finally:
        motor.dispose()
    fila = mt.fila(candidatos, resolvidos, tentativas, ler_pedidos(opcoes.pedidos))
    rodada = coletar(fila, opcoes.maximo, pasta / mt.PASTA_DOS_TEXTOS)
    log.info(
        "M&A do IPE: %s candidatos, faltavam %s; pedidos %s, com texto %s, sem texto %s, páginas %s",
        len(candidatos),
        len(fila),
        rodada.pedidos,
        rodada.textos,
        rodada.sem_texto,
        rodada.paginas,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
