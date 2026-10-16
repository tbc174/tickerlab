"""Monta a base de demonstrações "como era na data" e grava um Parquet por ano (série 1 da base de
ML, PR 6; `base/ponto_no_tempo.py`).

    python -m scripts.montar_base_como_era --anos 2023 2024 --pasta dados_locais/base_como_era
    python -m scripts.montar_base_como_era --anos 2023 --baixar-enet 50   (baixa até 50 versões antigas)

Para os fatos de um ano Y junta quatro arquivos dos dados abertos (DFP e ITR de Y e de Y+1: o ano
seguinte traz Y na coluna do ano anterior) e as versões antigas do ENET que já estiverem no acervo.
Cada arquivo vem do acervo (`src/acervo.py`) e só é baixado da CVM se não estiver lá. Com
`--baixar-enet N`, baixa antes até N versões antigas que faltam, um pedido por vez
(`base/enet_coleta.py`).

O cadastro de companhias (`cad_cia_aberta.csv`, do acervo ou baixado) dá as datas de registro:
documento entregue com a empresa fora de qualquer registro vale a partir do registro seguinte
(`base/ponto_no_tempo.divulgacao_publica`).

Versão antiga que falta não vaza o futuro: o documento só aparece a partir da versão que a base tem.
A base fica com um buraco, e o relatório conta quantas faltaram. Feita para o servidor de casa ou o
PC (ADR 0031): no ano inteiro, a memória passa de 1 GB.
"""

import argparse
import hashlib
import logging
import sys
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
import sqlalchemy as sa

from base.cadastro import ler_cadastro
from base.contas_cvm import ler_contas, ler_indice
from base.enet import DocumentoEnet, ler_xml_enet
from base.enet_coleta import Baixador, baixar_em_fila, guardar, ja_guardados
from base.ponto_no_tempo import (
    com_divulgacao,
    conferir_pasta,
    gravar_parquet,
    montar_ano,
    publicadas_do_enet,
    versoes_antigas,
)
from src import demonstracoes as dm
from src import rede
from src.banco.coletas import com_registro, original_mais_recente
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.base_como_era")
FONTE = "cvm-dfp-itr"
PASTA_PADRAO = Path("dados_locais") / "base_como_era"
NAO_ENCONTRADO = 404
URLS = {"DFP": dm.URL_DO_DFP, "ITR": dm.URL_DO_ITR}


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


def _origem(url: str, conteudo: bytes) -> dict[str, str]:
    return {"url": url, "sha256": hashlib.sha256(conteudo).hexdigest()}


def documentos_do_enet(
    conexao: sa.Connection, indice: pd.DataFrame
) -> tuple[list[DocumentoEnet], list[str], list[dict[str, str]]]:
    """As versões antigas do índice que estão no acervo, lidas; os links das que faltam; e a
    origem (endereço e SHA-256 do XML) de cada uma lida."""
    documentos, faltando, origens = [], [], []
    for versao in versoes_antigas(indice).itertuples():
        xml = original_mais_recente(conexao, versao.link)
        if xml is None:
            faltando.append(versao.link)
        else:
            documentos.append(_com_o_cnpj_do_indice(ler_xml_enet(xml), versao.cnpj))
            origens.append(_origem(versao.link, xml))
    return documentos, faltando, origens


def _com_o_cnpj_do_indice(documento: DocumentoEnet, cnpj: str) -> DocumentoEnet:
    """Alguns XMLs do ENET vêm sem o CNPJ (`CnpjEmpresa` vazio): o documento fica com o do índice,
    que é quem diz de que companhia é aquele link. Sem isso, as contas ficavam sem data de divulgação
    e a montagem do ano parava (2020 a 2025, achado em 16/10/2026)."""
    if documento.cnpj:
        return documento
    return replace(documento, cnpj=cnpj, contas=documento.contas.assign(cnpj=cnpj))


def _baixar_versoes_antigas(motor: sa.Engine, indice: pd.DataFrame, limite: int) -> int:
    """Baixa até `limite` versões antigas que faltam no acervo. Devolve quantas baixou."""
    with motor.connect() as conexao:
        feitos = ja_guardados(conexao)
    links = [l for l in versoes_antigas(indice)["link"] if l not in feitos][:limite]

    def ao_baixar(link: str, pacote: bytes) -> None:
        with motor.begin() as conexao:
            guardar(conexao, link, pacote, datetime.now(UTC))

    resultado = baixar_em_fila(links, Baixador().baixar, feitos, ao_baixar)
    for link, erro in resultado.falhas.items():
        log.warning("ENET: %s não veio (%s); fica para a próxima rodada", link, erro)
    return len(resultado.baixados)


@dataclass
class Lido:
    """O que um arquivo anual deu para o ano: as contas, o que faltou e de onde veio cada coisa."""

    cadastro: pd.DataFrame
    publicadas: list[pd.DataFrame] = field(default_factory=list)
    faltando: int = 0
    origens: list[dict[str, str]] = field(default_factory=list)


def _ler_arquivo(
    motor: sa.Engine,
    documento: str,
    ano_do_arquivo: int,
    ano: int,
    limite_enet: int,
    lido: Lido,
) -> None:
    """Junta em `lido` as contas publicadas num arquivo anual (dados abertos + ENET) com fim em `ano`."""
    url = URLS[documento].format(ano=ano_do_arquivo)
    conteudo = _conteudo(motor, url)
    if conteudo is None:
        log.info("%s %s ainda não existe na CVM: pulado", documento, ano_do_arquivo)
        return
    indice = ler_indice(conteudo, documento)
    contas = ler_contas(conteudo, documento, so_as_das_regras=True).contas
    if limite_enet:
        baixadas = _baixar_versoes_antigas(motor, indice, limite_enet)
        log.info(
            "%s %s: %s versões antigas baixadas", documento, ano_do_arquivo, baixadas
        )
    with motor.connect() as conexao:
        documentos, faltando, origens_do_enet = documentos_do_enet(conexao, indice)
    partes = [com_divulgacao(contas, indice, "dados_abertos", cadastro=lido.cadastro)]
    if documentos:  # tabela vazia na junção estragaria o tipo das datas
        partes.append(publicadas_do_enet(documentos, indice, cadastro=lido.cadastro))
    publicadas = pd.concat(partes, ignore_index=True)
    lido.publicadas.append(publicadas[publicadas["fim"].dt.year == ano])
    lido.faltando += len(faltando)
    lido.origens += [_origem(url, conteudo), *origens_do_enet]


def montar(motor: sa.Engine, ano: int, pasta: Path, limite_enet: int) -> pd.DataFrame:
    """A base dos fatos de `ano`, gravada em `<pasta>/<ano>.parquet` com o `<ano>.json`."""
    cadastro = _conteudo(motor, dm.URL_DO_CADASTRO)
    if cadastro is None:
        raise RuntimeError(
            "sem o cadastro da CVM não há data de registro: nada gravado"
        )
    lido = Lido(cadastro=ler_cadastro(cadastro))
    lido.origens.append(_origem(dm.URL_DO_CADASTRO, cadastro))
    for documento in URLS:
        for ano_do_arquivo in (ano, ano + 1):
            _ler_arquivo(motor, documento, ano_do_arquivo, ano, limite_enet, lido)
    if not lido.publicadas:
        log.warning("%s: nenhum arquivo da CVM; nada gravado", ano)
        return pd.DataFrame()
    base = montar_ano(pd.concat(lido.publicadas, ignore_index=True), ano)
    gravar_parquet(base, pasta, origens=lido.origens)
    log.info(
        "%s: %s linhas, %s versões antigas ainda fora do acervo (rode com --baixar-enet)",
        ano, len(base), lido.faltando,
    )  # fmt: skip
    return base


def conferir(pasta: Path) -> int:
    """Confere o hash de cada ano gravado (exigência 9 da ADR 0027). 1 se algum não bate."""
    resultado = conferir_pasta(pasta)
    for ano, igual in resultado.items():
        print(f"{ano}: {'ok' if igual else 'DIFERENTE do anotado'}")
    return 0 if all(resultado.values()) else 1


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--anos", type=int, nargs="+")
    argumentos.add_argument(
        "--conferir", action="store_true", help="só confere os hashes da pasta e sai"
    )
    argumentos.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    argumentos.add_argument(
        "--baixar-enet",
        type=int,
        default=0,
        help="máximo de versões antigas a baixar por arquivo",
    )
    opcoes = argumentos.parse_args(argv)
    if opcoes.conferir:
        return conferir(opcoes.pasta)
    if not opcoes.anos:
        argumentos.error("informe --anos (ou --conferir)")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    # a base vendável só aceita números refeitos de um commit (ADR 0055, exigência 13)
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        for ano in opcoes.anos:
            montar(motor, ano, opcoes.pasta, opcoes.baixar_enet)
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Montagem interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
