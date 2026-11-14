"""Base histórica (série B1): as tabelas da CVM de todos os anos, lidas dos originais do acervo.

O arquivista (`base/arquivo/`) guarda os arquivos anuais da CVM desde 2003 (`cvm-hist-*`). Aqui cada
arquivo é lido com o **mesmo leitor do app** (`src/eventos.ler_ipe`, `src/negociacoes_cvm.ler_vlmo`,
`base/fre.py`) e vira `<pasta>/<tabela>/<ano>.parquet`. O banco de produção continua com poucos
anos (ADR 0031): o histórico longo é da base de ML, no servidor de casa.

Cada linha leva a **origem**: o SHA-256 do arquivo da CVM de onde saiu, quando ele foi coletado e quando
a tabela foi montada. Nada é baixado: sem original no acervo, o ano não entra.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import sqlalchemy as sa

from base import (
    auditores,
    controladas,
    fca_geral,
    fre,
    pareceres,
    rotulos,
    securitizacao,
)
from base.cadastro import cadastro_do_acervo
from base.parquet import LINHAGEM, gravar_se_mudou
from base.ponto_no_tempo import divulgacao_publica
from base.raizes_de_empresa import RaizesDeEmpresa
from src import acervo
from src.banco.coletas import exigir_licenca, originais_mais_recentes
from src.eventos import ler_ipe
from src.negociacoes_cvm import ler_vlmo
from src.versao_do_codigo import versao_do_codigo

log = logging.getLogger(__name__)
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
    e_rotulo: bool = (
        False  # rótulo de modelo: a fonte precisa poder rotular (ADR 0008, Emenda 1)
    )
    # outras fontes do arquivista que entram na mesma tabela (CRI, CRA e OTS são três fontes); os
    # arquivos de todas as fontes do mesmo ano vão juntos para o `<ano>.parquet`
    outras_fontes: tuple[str, ...] = ()
    # a fonte guarda mais de um tipo de arquivo (o informe mensal de CRI e CRA vem com os `dfin_*`
    # e um `meta_*.txt`): só entra o original cujo endereço tem este trecho; vazio = todos
    so_url_com: str = ""
    # coluna de CNPJ: só fica a linha cuja raiz é empresa (`base/raizes_de_empresa.py`); empresário
    # individual e MEI são pessoa. Sem a lista, a montagem recusa (linha 784)
    so_raiz_de_empresa: str = ""


FONTES_DE_SECURITIZACAO = ("cvm-cra", "cvm-securitizadoras-ots")
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
        e_rotulo=True,
    ),
    # série B3: mandatos de auditor por empresa (base/auditores.py); as trocas saem deles. O FCA
    # do pedido de registro só fica público perto do registro (conferência de 16/10/2026)
    "auditores": Tabela(  # desde 2010
        "cvm-hist-fca", auditores.ler_auditores_do_fca, data_publica="conhecido_em"
    ),
    # série T, T2: parecer do auditor (base/pareceres.py); DFP desde 2010 e ITR desde 2011
    "pareceres_dfp": Tabela(
        "cvm-hist-dfp", pareceres.ler_pareceres_do_dfp, data_publica="disponivel_em"
    ),
    "pareceres_itr": Tabela(
        "cvm-hist-itr", pareceres.ler_pareceres_do_itr, data_publica="disponivel_em"
    ),
    # modelo 8 (nota i do critério de pronto): setor, categoria e controle como eram em cada FCA
    "fca_geral": Tabela(  # desde 2010
        "cvm-hist-fca", fca_geral.ler_geral_do_fca, data_publica="conhecido_em"
    ),
    # série 6, PR 1 (B-16): informe mensal de CRI, CRA e OTS; o leitor vê o produto pelo nome dos CSVs
    "securitizacao_certificados": Tabela(
        "cvm-cri",
        securitizacao.ler_certificados,
        outras_fontes=FONTES_DE_SECURITIZACAO,
        so_url_com="inf_mensal",
    ),
    "securitizacao_cedente_devedor": Tabela(
        "cvm-cri",
        securitizacao.ler_cedentes_e_devedores,
        outras_fontes=FONTES_DE_SECURITIZACAO,
        so_url_com="inf_mensal",
        so_raiz_de_empresa="cnpj",
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


def so_empresa(
    dados: pd.DataFrame, coluna: str, raizes: RaizesDeEmpresa
) -> pd.DataFrame:
    """Só as linhas cujo CNPJ (14 dígitos, formatado ou não) tem raiz na lista de empresas."""
    digitos = dados[coluna].fillna("").astype(str).str.replace(r"\D", "", regex=True)
    completo = digitos.str.len() == 14
    na_lista = raizes.esta_na_lista(
        pa.array(digitos.str[:8].tolist(), type=pa.string())
    ).to_numpy(zero_copy_only=False)
    return dados[completo.to_numpy() & na_lista].reset_index(drop=True)


def _exigir_a_lista(nome: str, tabela: Tabela, raizes: RaizesDeEmpresa | None) -> None:
    if tabela.so_raiz_de_empresa and (raizes is None or len(raizes.valores) == 0):
        raise ValueError(
            f"{nome}: sem a lista de empresas (raizes), ou ela veio vazia: não se grava CNPJ"
        )


def _origem_do_arquivo(
    url: str, sha256: str, tabela: Tabela, raizes: RaizesDeEmpresa | None
) -> dict[str, str]:
    """O arquivo da CVM; a impressão da lista de empresas vai dentro dele (`raizes_sha256`, como na
    carga da ANM), sem criar uma origem que não é fonte (a marca de licença não vira "a confirmar")."""
    origem = {"url": url, "sha256": sha256}
    if raizes is not None and tabela.so_raiz_de_empresa:
        origem["raizes_sha256"] = raizes.impressao
    return origem


def _so_empresa_da_tabela(
    nome: str,
    ano: int,
    dados: pd.DataFrame,
    tabela: Tabela,
    raizes: RaizesDeEmpresa | None,
) -> pd.DataFrame:
    """Tira as linhas de raiz fora da lista de empresas, quando a tabela pede, e conta no log."""
    if raizes is None or not tabela.so_raiz_de_empresa:
        return dados
    so = so_empresa(dados, tabela.so_raiz_de_empresa, raizes)
    log.info(
        "%s %d: %d linhas de fora da lista de empresas tiradas",
        nome,
        ano,
        len(dados) - len(so),
    )
    return so


def _com_data_publica(
    dados: pd.DataFrame, coluna: str, cadastro: pd.DataFrame
) -> pd.DataFrame:
    recebido = pd.to_datetime(dados[coluna])
    publica = divulgacao_publica(dados["cnpj"], recebido, cadastro)
    return dados.assign(**{coluna: publica.dt.date})


def montar(
    nome: str,
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    raizes: RaizesDeEmpresa | None = None,
) -> dict[int, int]:
    """Monta `<pasta>/<nome>/<ano>.parquet` para cada arquivo anual guardado; devolve linhas por ano.

    Levanta `KeyError` (tabela desconhecida), `LicencaNaoPermiteError` (rótulo com fonte que não
    pode rotular) e `ArquivoIlegivel` (original que não abre: nada é
    gravado para aquele ano, e a falha aparece em vez de virar um ano vazio; ou, para tabela com
    `data_publica`, sem o cadastro no acervo).
    """
    tabela = TABELAS[nome]
    _exigir_a_lista(nome, tabela, raizes)
    if tabela.e_rotulo:
        exigir_licenca("rotular", [tabela.fonte], onde=nome)
    linhas_por_ano: dict[int, int] = {}
    cadastro = None
    if tabela.data_publica:
        cadastro = cadastro_do_acervo(conexao)
        if cadastro is None:
            raise ArquivoIlegivel(
                f"{nome}: sem o cadastro de companhias no acervo para a data pública"
            )
    # só a tabela que olha todos os anos, ou junta fontes, guarda os anos na memória
    junta_antes_de_gravar = tabela.com_todos_os_anos is not None or bool(
        tabela.outras_fontes
    )
    lidos: list[tuple[int, pd.DataFrame, list[dict[str, str]]]] = []
    for fonte in (tabela.fonte, *tabela.outras_fontes):
        for original in originais_mais_recentes(conexao, fonte):
            if tabela.so_url_com and tabela.so_url_com not in original.url:
                continue
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
            dados = _so_empresa_da_tabela(nome, ano, dados, tabela, raizes)
            if dados.empty:
                linhas_por_ano.setdefault(ano, 0)
                continue
            origens = [
                _origem_do_arquivo(original.url, original.sha256, tabela, raizes)
            ]
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
            if junta_antes_de_gravar:
                lidos.append((ano, dados, origens))
            else:
                _gravar(dados, pasta / nome / f"{ano}.parquet", origens)
            linhas_por_ano[ano] = linhas_por_ano.get(ano, 0) + len(dados)
    if junta_antes_de_gravar and lidos:
        juntos = pd.concat([dados for _, dados, _ in lidos], ignore_index=True)
        if tabela.com_todos_os_anos is not None:
            juntos = tabela.com_todos_os_anos(juntos)
        for ano in sorted({ano for ano, _, _ in lidos}):
            do_ano = juntos[juntos["ano_do_arquivo"] == ano].reset_index(drop=True)
            origens_do_ano = [o for a, _, os in lidos if a == ano for o in os]
            _gravar(do_ano, pasta / nome / f"{ano}.parquet", origens_do_ano)
    return linhas_por_ano
