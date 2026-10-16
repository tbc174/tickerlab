"""Roda as regras fixas do selo de qualidade sobre os arquivos de DFP e ITR da CVM e grava os
achados (série 1 da base de ML, PR 3; `base/regras.py`, `base/rodada.py`).

    python -m scripts.atualizar_qualidade              (DFP dos 2 anos anteriores e do atual; ITR do
                                                        ano anterior e do atual)
    python -m scripts.atualizar_qualidade --ano 2025   (como se fosse 2025)

Roda fora do app (no VPS, uma vez por dia, depois de `atualizar_fundamentos`, num contêiner
próprio: o ITR inteiro não cabe ao lado do app). Lê cada arquivo do acervo do original
(`src/acervo.py`) e só baixa da CVM o que não estiver lá. Um arquivo que falha não para os outros;
qualquer falha devolve 1, para a conferência das tarefas avisar.
"""

import argparse
import gc
import logging
import sys
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import sqlalchemy as sa

from base.cadastro import ler_cadastro
from base.contas_cvm import ler_contas, ler_indice
from base.rodada import (
    Arquivo,
    Rodada,
    principais,
    regras_de_um_documento,
    regras_entre_documentos,
)
from src import demonstracoes as dm
from src import rede
from src.banco.coletas import com_registro, original_mais_recente
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import eventos
from src.banco.qualidade import gravar_achados
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.qualidade")
FONTE = (
    "cvm-dfp-itr"  # a mesma de `atualizar_fundamentos`: os arquivos já estão no acervo
)
ANOS_DE_DFP = 3  # o do ano anterior precisa do de antes (R3, R8) e do seguinte (R6)
ANOS_DE_ITR = 2
ANOS_DE_EVENTOS = 4  # a R7 olha um ano antes da DFP mais velha
FUSO = ZoneInfo("America/Sao_Paulo")
NAO_ENCONTRADO = 404


def _baixar_da_fonte(url: str) -> bytes | None:
    """O arquivo da CVM, ou None se ele ainda não existe (404)."""
    resposta = rede.obter(
        url, timeout=300, headers={"User-Agent": "TickerLab (tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return resposta.content


baixar = com_registro(FONTE, _baixar_da_fonte)


def _conteudo(motor: sa.Engine, url: str) -> bytes | None:
    with motor.connect() as conexao:
        guardado = original_mais_recente(conexao, url)
    return guardado if guardado is not None else baixar(url)


def _eventos(motor: sa.Engine, desde: date) -> pd.DataFrame:
    with motor.connect() as conexao:
        linhas = conexao.execute(
            sa.select(eventos.c.cnpj, eventos.c.publicado_em).where(
                eventos.c.publicado_em >= desde
            )
        ).all()
    tabela = pd.DataFrame(linhas, columns=["cnpj", "publicado_em"])
    tabela["publicado_em"] = pd.to_datetime(tabela["publicado_em"])
    return tabela


def _gravar(motor: sa.Engine, rodada: Rodada, agora: datetime) -> bool:
    """Grava uma rodada; devolve se alguma regra dela falhou."""
    if rodada.regras:
        with motor.begin() as conexao:
            resumo = gravar_achados(
                conexao,
                rodada.achados,
                regras=rodada.regras,
                documento=rodada.documento,
                referencias=rodada.referencias,
                agora=agora,
            )
        log.info(
            "%s %s: %s novos, %s atualizados, %s fechados",
            rodada.documento, "/".join(rodada.regras),
            resumo.novos, resumo.atualizados, resumo.fechados,
        )  # fmt: skip
    for regra in rodada.falhas:
        log.error(
            "%s %s falhou: os achados dela ficaram como estavam",
            rodada.documento,
            regra,
        )
    return bool(rodada.falhas)


def _ler_arquivo(
    motor: sa.Engine, documento: str, ano: int, hoje: pd.Timestamp, agora: datetime
) -> tuple[Arquivo | None, bool]:
    """Roda as regras de um documento só e guarda o resumo do arquivo. (arquivo, houve falha)"""
    modelo = dm.URL_DO_DFP if documento == "DFP" else dm.URL_DO_ITR
    try:
        conteudo = _conteudo(motor, modelo.format(ano=ano))
    except (requests.RequestException, OSError) as erro:
        log.error("%s %s: não consegui baixar (%s)", documento, ano, erro)
        return None, True
    if conteudo is None:
        log.info("%s %s ainda não existe na CVM: pulado", documento, ano)
        return None, False
    leitura = ler_contas(conteudo, documento, so_as_das_regras=True)
    indice = ler_indice(conteudo, documento)
    falhou = _gravar(
        motor, regras_de_um_documento(leitura, documento, indice, hoje), agora
    )
    arquivo = Arquivo(documento, ano, principais(leitura.contas), indice)
    del leitura, conteudo
    gc.collect()  # um arquivo inteiro por vez na memória
    return arquivo, falhou


def _cadastro(motor: sa.Engine) -> pd.DataFrame | None:
    try:
        conteudo = _conteudo(motor, dm.URL_DO_CADASTRO)
    except (requests.RequestException, OSError) as erro:
        log.error("Cadastro: não consegui baixar (%s); a R8 fica para amanhã", erro)
        return None
    return ler_cadastro(conteudo) if conteudo else None


def _processar(
    motor: sa.Engine,
    documento: str,
    anos: range,
    eventos_do_ipe: pd.DataFrame,
    cadastro: pd.DataFrame | None,
    agora: datetime,
) -> bool:
    """Todas as regras de um tipo de documento; devolve se algo falhou."""
    hoje = pd.Timestamp(agora.astimezone(FUSO).date())
    lidos = {ano: _ler_arquivo(motor, documento, ano, hoje, agora) for ano in anos}
    falhou = any(f for _, f in lidos.values())
    arquivos = {ano: a for ano, (a, _) in lidos.items() if a is not None}
    for ano, atual in arquivos.items():
        rodadas = regras_entre_documentos(
            atual,
            arquivos.get(ano - 1),
            arquivos.get(ano + 1),
            eventos_do_ipe,
            cadastro,
            hoje,
        )
        for rodada in rodadas:
            falhou = _gravar(motor, rodada, agora) or falhou
    return falhou


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--ano", type=int, help="o ano atual (padrão: o de hoje)")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    agora = datetime.now(UTC)
    ano = opcoes.ano or agora.astimezone(FUSO).year
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        eventos_do_ipe = _eventos(motor, date(ano - ANOS_DE_EVENTOS, 1, 1))
        cadastro = _cadastro(motor)
        falhou = cadastro is None
        pedidos = {
            "DFP": range(ano - ANOS_DE_DFP + 1, ano + 1),
            "ITR": range(ano - ANOS_DE_ITR + 1, ano + 1),
        }
        for documento, anos in pedidos.items():
            falhou = (
                _processar(motor, documento, anos, eventos_do_ipe, cadastro, agora)
                or falhou
            )
    except sa.exc.SQLAlchemyError as erro:
        log.error("Regras de qualidade interrompidas: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
