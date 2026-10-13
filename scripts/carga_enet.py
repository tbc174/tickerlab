"""Carga noturna das versões antigas de DFP e ITR do ENET (série 1 da base de ML, PR 7).

    python -m scripts.carga_enet                          (2010 até o ano atual, até as 6h)
    python -m scripts.carga_enet --desde 2020 --parar-as 05:30

Roda no servidor de casa, de madrugada (ADR 0031). Para cada arquivo anual da CVM, do DFP mais novo
para o mais velho e depois o ITR, lê o índice e baixa do ENET as versões que não são a mais nova (a
mais nova vem dos dados abertos), um pacote por vez (`base/enet_coleta.py`). Guarda o XML limpo no
acervo e no registro de coletas.

- **Janela:** não começa um pacote depois de `--parar-as` (6h): a noite seguinte retoma de onde
  parou, porque o que já está guardado é pulado.
- **Falha passageira** (pacote cortado, a CVM devolvendo outra coisa) fica para a noite seguinte e
  não derruba a tarefa. A tarefa devolve 1 (o Kuma avisa) só se nada veio e algo falhou: sinal de
  que a fonte está fora do ar ou mudou.
- Depois da carga inicial, a tarefa continua útil: as empresas reapresentam documentos o tempo
  todo, e cada reapresentação nova torna antiga a versão de antes.
"""

import argparse
import logging
import sys
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import sqlalchemy as sa

from base.contas_cvm import ler_indice
from base.enet_coleta import (
    Baixador,
    ResultadoDaFila,
    baixar_em_fila,
    guardar,
    ja_guardados,
)
from base.ponto_no_tempo import versoes_antigas
from src import demonstracoes as dm
from src.banco.coletas import com_registro, original_mais_recente
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.carga_enet")
FUSO = ZoneInfo("America/Sao_Paulo")
PRIMEIRO_ANO = 2010  # os dados abertos de DFP começam em 2010 (ITR em 2011)
PARAR_AS = "06:00"
NAO_ENCONTRADO = 404
URLS = {"DFP": dm.URL_DO_DFP, "ITR": dm.URL_DO_ITR}


def _baixar_da_fonte(url: str) -> bytes | None:
    """O arquivo anual da CVM, ou None se ele não existe (404)."""
    resposta = requests.get(
        url, timeout=300, headers={"User-Agent": "TickerLab (tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return resposta.content


baixar = com_registro("cvm-dfp-itr", _baixar_da_fonte)


def agora() -> datetime:
    return datetime.now(FUSO)


def fim_da_janela(momento: datetime, parar_as: str) -> datetime:
    """O próximo `parar_as` depois de `momento` (às 0h30 → 6h do mesmo dia; às 23h → do seguinte)."""
    hora, minuto = (int(parte) for parte in parar_as.split(":"))
    fim = datetime.combine(momento.date(), time(hora, minuto), tzinfo=momento.tzinfo)
    return fim if momento < fim else fim + timedelta(days=1)


def _indice(motor: sa.Engine, documento: str, ano: int) -> pd.DataFrame | None:
    url = URLS[documento].format(ano=ano)
    with motor.connect() as conexao:
        conteudo = original_mais_recente(conexao, url)
    conteudo = conteudo if conteudo is not None else baixar(url)
    return None if conteudo is None else ler_indice(conteudo, documento)


def _carregar_arquivo(
    motor: sa.Engine,
    documento: str,
    ano: int,
    baixador: Baixador,
    fim: datetime,
) -> ResultadoDaFila | None:
    indice = _indice(motor, documento, ano)
    if indice is None:
        log.info("%s %s não existe na CVM: pulado", documento, ano)
        return None
    with motor.connect() as conexao:
        feitos = ja_guardados(conexao)

    def ao_baixar(link: str, pacote: bytes) -> None:
        with motor.begin() as conexao:
            guardar(conexao, link, pacote, datetime.now(UTC))

    resultado = baixar_em_fila(
        versoes_antigas(indice)["link"],
        baixador.baixar,
        feitos,
        ao_baixar,
        continuar=lambda: agora() < fim,
    )
    log.info(
        "%s %s: %s baixadas, %s já estavam, %s falharam",
        documento, ano, len(resultado.baixados), resultado.pulados, len(resultado.falhas),
    )  # fmt: skip
    return resultado


def carregar(motor: sa.Engine, desde: int, ate: int, parar_as: str) -> tuple[int, int]:
    """Baixa o que falta, DFP do ano mais novo ao mais velho e depois ITR. (baixadas, falhas)"""
    fim = fim_da_janela(agora(), parar_as)
    baixador = Baixador()
    baixadas = falhas = 0
    for documento in URLS:
        for ano in range(ate, desde - 1, -1):
            resultado = _carregar_arquivo(motor, documento, ano, baixador, fim)
            if resultado is None:
                continue
            baixadas += len(resultado.baixados)
            falhas += len(resultado.falhas)
            if resultado.interrompida:
                log.info(
                    "Janela acabou (%s): %s baixadas nesta noite", parar_as, baixadas
                )
                return baixadas, falhas
    log.info("Carga em dia: %s baixadas nesta noite", baixadas)
    return baixadas, falhas


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--desde", type=int, default=PRIMEIRO_ANO)
    argumentos.add_argument("--ate", type=int, help="o ano mais novo (padrão: o atual)")
    argumentos.add_argument(
        "--parar-as", default=PARAR_AS, help="hora de não começar mais"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        baixadas, falhas = carregar(
            motor, opcoes.desde, opcoes.ate or agora().year, opcoes.parar_as
        )
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Carga interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    if falhas and not baixadas:
        log.error(
            "Nada veio e %s pacotes falharam: a fonte pode estar fora do ar", falhas
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
