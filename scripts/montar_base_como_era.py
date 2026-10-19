"""Monta a base de demonstrações "como era na data" e grava um Parquet por ano (série 1 da base de
ML, PR 6; `base/ponto_no_tempo.py`).

    python -m scripts.montar_base_como_era --anos 2023 2024 --pasta dados_locais/base_como_era
    python -m scripts.montar_base_como_era --anos 2023 --baixar-enet 50   (baixa até 50 versões antigas)
    python -m scripts.montar_base_como_era --anos 2023 --serie-t1   (com DFC, DVA, DRA e a DMPL)

Para os fatos de um ano Y junta quatro arquivos dos dados abertos (DFP e ITR de Y e de Y+1: o ano
seguinte traz Y na coluna do ano anterior) e as versões antigas do ENET que já estiverem no acervo.
Cada arquivo vem do acervo (`src/acervo.py`) e só é baixado da CVM se não estiver lá. Com
`--baixar-enet N`, baixa antes até N versões antigas que faltam, um pedido por vez
(`base/enet_coleta.py`).

O cadastro de companhias (`cad_cia_aberta.csv`, do acervo ou baixado) dá as datas de registro:
documento entregue com a empresa fora de qualquer registro vale a partir do registro seguinte
(`base/ponto_no_tempo.divulgacao_publica`).

**Série T1** (`--serie-t1`): as demonstrações ganham a DFC, a DVA e a DRA inteiras, e a DMPL vai
para a tabela própria (`dmpl_como_era`, em `--pasta-dmpl`; padrão: a pasta `dmpl` ao lado de
`--pasta`), numa segunda passada pelos mesmos arquivos, para a memória não somar as duas. Sem a
opção, a montagem é a de antes: o cron semanal do servidor de casa não remonta a tabela com outro
formato antes de o Tiago autorizar a remontagem (ADR 0101, nível 1).

Versão antiga que falta não vaza o futuro: o documento só aparece a partir da versão que a base tem.
A base fica com um buraco, e o relatório conta quantas faltaram. Feita para o servidor de casa ou o
PC (ADR 0031): no ano inteiro, a memória passa de 1 GB.
"""

import argparse
import hashlib
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
import sqlalchemy as sa

from base import dmpl
from base.cadastro import ler_cadastro
from base.contas_cvm import Recorte, ler_contas, ler_indice
from base.enet import DocumentoEnet, ler_xml_enet
from base.enet_coleta import Baixador, baixar_em_fila, guardar, ja_guardados
from base.ponto_no_tempo import (
    DEMONSTRACOES,
    Formato,
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
    return replace(
        documento,
        cnpj=cnpj,
        contas=documento.contas.assign(cnpj=cnpj),
        dmpl=documento.dmpl.assign(cnpj=cnpj),
    )


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


@dataclass(frozen=True)
class Tabela:
    """Uma tabela "como era na data": como ler os dados abertos e o ENET, e o formato do fato."""

    nome: str
    dos_dados_abertos: Callable[[bytes, str], pd.DataFrame]
    do_enet: Callable[..., pd.DataFrame]  # (documentos, indice, *, cadastro)
    formato: Formato


def demonstracoes(recorte: Recorte) -> Tabela:
    """As demonstrações (`demonstracoes_como_era`) no recorte pedido ("regras" ou "base")."""
    return Tabela(
        "demonstracoes_como_era",
        lambda conteudo, documento: ler_contas(conteudo, documento, recorte).contas,
        lambda documentos, indice, *, cadastro: publicadas_do_enet(
            documentos, indice, cadastro=cadastro, recorte=recorte
        ),
        DEMONSTRACOES,
    )


DMPL = Tabela(
    "dmpl_como_era", dmpl.ler_dmpl, dmpl.publicadas_do_enet, dmpl.FORMATO_DMPL
)


@dataclass
class Lido:
    """O que um arquivo anual deu para o ano: as contas, o que faltou e de onde veio cada coisa."""

    cadastro: pd.DataFrame
    publicadas: list[pd.DataFrame] = field(default_factory=list)
    faltando: int = 0
    origens: list[dict[str, str]] = field(default_factory=list)


def _ler_arquivo(
    motor: sa.Engine,
    tabela: Tabela,
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
    contas = tabela.dos_dados_abertos(conteudo, documento)
    if limite_enet:
        baixadas = _baixar_versoes_antigas(motor, indice, limite_enet)
        log.info(
            "%s %s: %s versões antigas baixadas", documento, ano_do_arquivo, baixadas
        )
    with motor.connect() as conexao:
        documentos, faltando, origens_do_enet = documentos_do_enet(conexao, indice)
    partes = [
        com_divulgacao(
            contas,
            indice,
            "dados_abertos",
            cadastro=lido.cadastro,
            formato=tabela.formato,
        )
    ]
    if documentos:  # tabela vazia na junção estragaria o tipo das datas
        partes.append(tabela.do_enet(documentos, indice, cadastro=lido.cadastro))
    publicadas = pd.concat(partes, ignore_index=True)
    # o arquivo sem a demonstração (a DMPL num zip antigo) dá tabela vazia, sem tipo de data
    do_ano = publicadas[pd.to_datetime(publicadas["fim"]).dt.year == ano]
    if not do_ano.empty:
        lido.publicadas.append(do_ano)
    lido.faltando += len(faltando)
    lido.origens += [_origem(url, conteudo), *origens_do_enet]


def montar(
    motor: sa.Engine,
    ano: int,
    pasta: Path,
    limite_enet: int,
    pasta_dmpl: Path | None = None,
) -> pd.DataFrame:
    """A base dos fatos de `ano`, gravada em `<pasta>/<ano>.parquet` com o `<ano>.json`.

    Com `pasta_dmpl` (série T1), as demonstrações saem no recorte da base (com DFC, DVA e DRA) e a
    DMPL é montada depois, em `<pasta_dmpl>/<ano>.parquet`; sem ela, no recorte das regras.
    """
    cadastro = _conteudo(motor, dm.URL_DO_CADASTRO)
    if cadastro is None:
        raise RuntimeError(
            "sem o cadastro da CVM não há data de registro: nada gravado"
        )
    recorte: Recorte = "regras" if pasta_dmpl is None else "base"
    base = _montar_tabela(
        motor, demonstracoes(recorte), ano, pasta, limite_enet, cadastro
    )
    if pasta_dmpl is not None and not base.empty:
        # as versões antigas já foram baixadas na passada das demonstrações
        _montar_tabela(motor, DMPL, ano, pasta_dmpl, 0, cadastro)
    return base


def _montar_tabela(
    motor: sa.Engine,
    tabela: Tabela,
    ano: int,
    pasta: Path,
    limite_enet: int,
    cadastro: bytes,
) -> pd.DataFrame:
    lido = Lido(cadastro=ler_cadastro(cadastro))
    lido.origens.append(_origem(dm.URL_DO_CADASTRO, cadastro))
    for documento in URLS:
        for ano_do_arquivo in (ano, ano + 1):
            _ler_arquivo(
                motor, tabela, documento, ano_do_arquivo, ano, limite_enet, lido
            )
    if not lido.publicadas:
        log.warning("%s %s: nenhum arquivo da CVM; nada gravado", tabela.nome, ano)
        return pd.DataFrame()
    publicadas = pd.concat(lido.publicadas, ignore_index=True)
    lido.publicadas.clear()  # a memória do ano inteiro passa de 1 GB
    base = montar_ano(publicadas, ano, tabela.formato)
    gravar_parquet(base, pasta, origens=lido.origens, formato=tabela.formato)
    log.info(
        "%s %s: %s linhas, %s versões antigas ainda fora do acervo (rode com --baixar-enet)",
        tabela.nome, ano, len(base), lido.faltando,
    )  # fmt: skip
    return base


def conferir(pasta: Path, formato: Formato = DEMONSTRACOES) -> int:
    """Confere o hash de cada ano gravado (exigência 9 da ADR 0027). 1 se algum não bate."""
    resultado = conferir_pasta(pasta, formato)
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
    argumentos.add_argument(
        "--serie-t1",
        action="store_true",
        help="com DFC, DVA e DRA nas demonstrações e a DMPL na tabela própria",
    )
    argumentos.add_argument(
        "--pasta-dmpl",
        type=Path,
        help="onde gravar a DMPL (padrão: a pasta dmpl ao lado de --pasta)",
    )
    opcoes = argumentos.parse_args(argv)
    pasta_dmpl = opcoes.pasta_dmpl or opcoes.pasta.parent / "dmpl"
    if opcoes.conferir:
        com_dmpl = opcoes.serie_t1 and pasta_dmpl.exists()
        dmpl_ok = conferir(pasta_dmpl, dmpl.FORMATO_DMPL) if com_dmpl else 0
        return max(conferir(opcoes.pasta), dmpl_ok)
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
            montar(
                motor,
                ano,
                opcoes.pasta,
                opcoes.baixar_enet,
                pasta_dmpl if opcoes.serie_t1 else None,
            )
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Montagem interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
