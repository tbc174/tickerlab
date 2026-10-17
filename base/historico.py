"""Base histórica (série B1): as tabelas da CVM de todos os anos, lidas dos originais do acervo.

O arquivista (`base/arquivo/`) guarda os arquivos anuais da CVM desde 2003 (`cvm-hist-*`). Aqui cada
arquivo é lido com o **mesmo leitor do app** (`src/eventos.ler_ipe`, `src/negociacoes_cvm.ler_vlmo`,
`base/fre.py`) e vira `<pasta>/<tabela>/<ano>.parquet`. O banco de produção continua com poucos
anos (ADR 0031): o histórico longo é da base de ML, no servidor de casa.

Cada linha leva a **origem**: o SHA-256 do arquivo da CVM de onde saiu, quando ele foi coletado e quando
a tabela foi montada. Nada é baixado: sem original no acervo, o ano não entra.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base import auditores, controladas, fre, rotulos
from base.cadastro import cadastro_do_acervo
from base.parquet import LINHAGEM, gravar_se_mudou
from base.ponto_no_tempo import divulgacao_publica
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.eventos import ler_ipe
from src.negociacoes_cvm import ler_vlmo
from src.versao_do_codigo import versao_do_codigo

ANO_NO_NOME = re.compile(r"_(\d{4})\.(?:zip|csv)$")


@dataclass(frozen=True)
class Tabela:
    fonte: str  # a fonte do arquivista que guarda os arquivos anuais
    ler: Callable[[bytes], pd.DataFrame]
    # coluna com o dia do recebimento pela CVM que passa a valer a partir do registro seguinte
    # quando a entrega foi feita fora do registro (`base/ponto_no_tempo.divulgacao_publica`)
    data_publica: str | None = None
    # passo que olha todos os anos juntos antes de gravar (o processo de uma companhia atravessa
    # os arquivos anuais); recebe e devolve a tabela de todos os anos com `ano_do_arquivo`
    com_todos_os_anos: Callable[[pd.DataFrame], pd.DataFrame] | None = None


TABELAS = {
    "eventos": Tabela("cvm-hist-ipe", ler_ipe),  # desde 2003
    "negociacoes": Tabela("cvm-hist-vlmo", ler_vlmo),  # desde 2018
    "proventos": Tabela(
        "cvm-hist-fre", fre.ler_proventos
    ),  # 2010 a 2022 (o FRE novo não tem a tabela)
    "eventos_de_capital": Tabela("cvm-hist-fre", fre.ler_eventos_de_capital),
    # série B2: rótulos de recuperação judicial, falência e liquidação (base/rotulos.py)
    "insolvencia": Tabela(
        "cvm-hist-ipe",
        rotulos.ler_insolvencia_do_ipe,
        com_todos_os_anos=rotulos.rotular_com_contexto,
    ),
    # série B3: mandatos de auditor por empresa (base/auditores.py); as trocas saem deles. O FCA
    # do pedido de registro só fica público perto do registro (conferência de 16/10/2026)
    "auditores": Tabela(  # desde 2010
        "cvm-hist-fca", auditores.ler_auditores_do_fca, data_publica="conhecido_em"
    ),
    # série B13: controladas e coligadas pelo FRE (base/controladas.py), desde 2010
    "controladas": Tabela("cvm-hist-fre", controladas.ler_controladas_do_fre),
}


class ArquivoIlegivel(Exception):
    """Um original do acervo não abre com o leitor da tabela (formato mudou ou arquivo quebrado)."""


def ano_do_arquivo(url: str) -> int | None:
    """2024 em `..._2024.zip`; None para arquivos mensais (`_202609.zip`) ou sem ano."""
    achado = ANO_NO_NOME.search(url)
    return int(achado.group(1)) if achado else None


def _gravar(tabela: pd.DataFrame, destino: Path, origens: list[dict[str, str]]) -> str:
    """Com manifesto (entra na âncora, ADR 0078); remontar o mesmo dado não regrava, e o ano que
    mudou guarda o anterior como `.vN`."""
    return gravar_se_mudou(tabela, destino, origens, [], carimbos=LINHAGEM)


def _com_data_publica(
    dados: pd.DataFrame, coluna: str, cadastro: pd.DataFrame
) -> pd.DataFrame:
    recebido = pd.to_datetime(dados[coluna])
    publica = divulgacao_publica(dados["cnpj"], recebido, cadastro)
    return dados.assign(**{coluna: publica.dt.date})


def montar(
    nome: str, conexao: sa.Connection, pasta: Path, agora: datetime
) -> dict[int, int]:
    """Monta `<pasta>/<nome>/<ano>.parquet` para cada arquivo anual guardado; devolve linhas por ano.

    Levanta `KeyError` (tabela desconhecida) e `ArquivoIlegivel` (original que não abre: nada é
    gravado para aquele ano, e a falha aparece em vez de virar um ano vazio; ou, para tabela com
    `data_publica`, sem o cadastro no acervo).
    """
    tabela = TABELAS[nome]
    linhas_por_ano: dict[int, int] = {}
    cadastro = None
    if tabela.data_publica:
        cadastro = cadastro_do_acervo(conexao)
        if cadastro is None:
            raise ArquivoIlegivel(
                f"{nome}: sem o cadastro de companhias no acervo para a data pública"
            )
    lidos: list[tuple[int, pd.DataFrame, list[dict[str, str]]]] = []
    for original in originais_mais_recentes(conexao, tabela.fonte):
        ano = ano_do_arquivo(original.url)
        conteudo = acervo.ler_original(original.caminho_do_original)
        if ano is None or conteudo is None:
            continue
        try:
            dados = tabela.ler(conteudo)
        except Exception as erro:  # zip quebrado, CSV com formato novo
            raise ArquivoIlegivel(
                f"{nome} {ano}: {type(erro).__name__}: {erro}"
            ) from erro
        if dados.empty:
            linhas_por_ano[ano] = 0
            continue
        origens = [{"url": original.url, "sha256": original.sha256}]
        if tabela.data_publica and cadastro is not None:
            dados = _com_data_publica(dados, tabela.data_publica, cadastro[0])
            origens.append(cadastro[1])
        dados = dados.assign(
            ano_do_arquivo=ano,
            origem_sha256=original.sha256,
            origem_coletada_em=pd.Timestamp(original.baixado_em).isoformat(),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )
        # só a tabela que olha todos os anos guarda os anos na memória
        if tabela.com_todos_os_anos is None:
            _gravar(dados, pasta / nome / f"{ano}.parquet", origens)
        else:
            lidos.append((ano, dados, origens))
        linhas_por_ano[ano] = len(dados)
    if tabela.com_todos_os_anos is not None and lidos:
        juntos = tabela.com_todos_os_anos(
            pd.concat([dados for _, dados, _ in lidos], ignore_index=True)
        )
        for ano, _, origens in lidos:
            do_ano = juntos[juntos["ano_do_arquivo"] == ano].reset_index(drop=True)
            _gravar(do_ano, pasta / nome / f"{ano}.parquet", origens)
    return linhas_por_ano
