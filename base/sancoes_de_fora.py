"""Sanções internacionais de **entidades** (tabela `sancoes_de_fora`): OFAC (SDN e lista consolidada
não SDN), União Europeia e Reino Unido, cada uma direto do arquivo da própria fonte. Uma linha por
entidade e lista; é o complemento das sanções da CGU (`base/sancoes.py`), que são só do Brasil.

Lê os arquivos que o arquivista já guardou (não baixa nada); o filtro que deixa pessoa física fora e o
que se lê de cada formato estão em `base/arquivo/sancoes_xml.py`. Cada arquivo é um **retrato** da lista
no dia em que foi baixado, e o motor de `base/retratos.py` os junta numa tabela que só cresce.

- **Sem olhar o futuro** (`disponivel_em` = `visto_em`): a linha vale a partir do dia em que o arquivo
  foi visto, também no primeiro. A data da designação (`designado_em`) é para ler, nunca a data em que
  a base soube: a lista de hoje não diz o que dizia antes.
- O que sai e volta ganha as duas linhas, mesmo que o arquivo da volta seja igual a um de antes.
- O que sai da lista ganha uma linha `consta=False` no dia em que sumiu (retirada da designação, ou a
  fonte passou a tratar o registro de outro jeito: não é, sozinho, prova de que a sanção acabou).
- **Não há CNPJ aqui.** Ligar a uma empresa brasileira ou ao grupo dela é por nome, é dedução e sai
  marcada como tal; não está nesta tabela.

Fora, de propósito: a lista da ONU (sem licença aberta declarada) e a lista consolidada do Comércio dos
EUA (as listas que não são da OFAC vêm sem o tipo e misturam pessoa).
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import retratos as motor
from base.arquivo import sancoes_xml
from base.parquet import LINHAGEM
from src.versao_do_codigo import versao_do_codigo

TABELA = "sancoes_de_fora"
SEPARADOR_DE_VALORES = " | "  # outros nomes, países e programas numa célula só
SEPARADOR_DO_ID = "|"  # entre a lista e o id, na chave de um retrato
JA_MONTADO = motor.JA_MONTADO
VALORES = ["nome", "outros_nomes", "paises", "programas", "designado_em", "consta"]
COLUNAS = [
    "lista",
    "id_na_fonte",
    "nome",
    "outros_nomes",
    "paises",
    "programas",
    "designado_em",
    "fonte",
    "url_da_fonte",
    "consta",
    "visto_em",
    "disponivel_em",
]
COLUNAS_GRAVADAS = [*COLUNAS, *LINHAGEM]
ORDEM = ["lista", "id_na_fonte", "visto_em"]


@dataclass(frozen=True)
class Cadastro:
    """Um arquivo de lista: de que coleta vem e quem o publica (`motor.CadastroDeRetratos`)."""

    nome: str
    fonte: str  # id da coleta no arquivista
    orgao: str  # quem publica, com a licença que pede atribuição
    formato: sancoes_xml.Formato
    tabela: str = TABELA

    @property
    def url_termina_em(self) -> str:
        """Só o arquivo XML: a coleta antiga (CSV) da mesma fonte continua no acervo e fica fora.

        Os dois últimos trechos do endereço: na União Europeia o último é igual no CSV e no XML.
        """
        return "/".join(self.formato.url.rsplit("/", 2)[-2:])


CADASTROS: dict[str, Cadastro] = {
    c.nome: c
    for c in (
        Cadastro(
            "ofac_sdn",
            "ofac-sdn",
            "OFAC, U.S. Department of the Treasury",
            sancoes_xml.OFAC_SDN,
        ),
        Cadastro(
            "ofac_consolidada",
            "ofac-sdn",
            "OFAC, U.S. Department of the Treasury",
            sancoes_xml.OFAC_CONSOLIDADA,
        ),
        Cadastro(
            "uniao_europeia",
            "eufsf-sancoes",
            "Comissão Europeia (DG FISMA), Decisão 2011/833/UE; mantidas só as entidades; "
            "só o Jornal Oficial da UE é autêntico",
            sancoes_xml.UNIAO_EUROPEIA,
        ),
        Cadastro(
            "reino_unido",
            "ofsi-conlist",
            "Reino Unido (FCDO, UK Sanctions List), OGL v3.0",
            sancoes_xml.REINO_UNIDO,
        ),
    )
}


def _linhas(registro: sancoes_xml.Registro, cadastro: Cadastro) -> list[dict]:
    comum = {
        "nome": registro.nome,
        "outros_nomes": SEPARADOR_DE_VALORES.join(registro.outros_nomes),
        "paises": SEPARADOR_DE_VALORES.join(registro.paises),
        "programas": SEPARADOR_DE_VALORES.join(registro.programas),
        "fonte": cadastro.orgao,
        "url_da_fonte": cadastro.formato.url,
    }
    return [
        {
            "id_na_fonte": f"{lista}{SEPARADOR_DO_ID}{registro.id}",  # separados na gravação
            "designado_em": designado_em,
            **comum,
        }
        for lista, designado_em in registro.listas
    ]


def ler_retrato(
    caminho: Path, cadastro: Cadastro
) -> tuple[pd.DataFrame, dict[str, int]]:
    """As linhas de um arquivo guardado (entidade e lista) e quantas entidades ele tem."""
    registros = sancoes_xml.entidades(motor.original(caminho), cadastro.formato)
    linhas = pd.DataFrame(
        [linha for r in registros for linha in _linhas(r, cadastro)],
        columns=["id_na_fonte", *VALORES[:-1], "fonte", "url_da_fonte"],
    )
    repetida = linhas["id_na_fonte"].duplicated(keep="first")
    pronta = linhas[~repetida].reset_index(drop=True)
    for coluna in ("outros_nomes", "paises", "programas"):
        pronta[coluna] = motor.sem_vazio(pronta[coluna])
    return pronta, {"entidades": len(registros), "id_repetido": int(repetida.sum())}


def _no_dia_do_arquivo(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    return pd.Series(dia, index=novos.index)


def juntar_retratos(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES, _no_dia_do_arquivo)


def _para_gravar(
    tabela: pd.DataFrame, _pessoas: np.ndarray, agora: datetime
) -> pd.DataFrame:
    chave = tabela["id_na_fonte"].str.split(SEPARADOR_DO_ID, n=1, expand=True)
    return (
        tabela.assign(
            lista=chave[0],
            id_na_fonte=chave[1],
            designado_em=pd.to_datetime(tabela["designado_em"]).dt.date,
            visto_em=pd.to_datetime(tabela["visto_em"]).dt.date,
            disponivel_em=pd.to_datetime(tabela["disponivel_em"]).dt.date,
            consta=tabela["consta"].astype(bool),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )[COLUNAS_GRAVADAS]
        .sort_values(ORDEM, kind="stable")
        .reset_index(drop=True)
    )


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    refazer: bool = False,
    cadastros: Collection[Cadastro] | None = None,
) -> dict[str, dict[str, int]]:
    """`<pasta>/sancoes_de_fora/<cadastro>.parquet` para cada lista com arquivo guardado.

    Lista sem arquivo fica de fora do resumo; sem arquivo novo desde a última montagem, é pulada
    (`refazer` relê mesmo assim, para código novo).
    """
    return motor.montar_cadastros(
        conexao,
        pasta,
        agora,
        list(cadastros or CADASTROS.values()),
        ler=ler_retrato,
        juntar=juntar_retratos,
        para_gravar=_para_gravar,
        ordem=ORDEM,
        pessoas=set(),  # não há CNPJ aqui: nada a perguntar à Receita
        refazer=refazer,
        com_voltas=True,  # saiu e voltou igual: o arquivo repetido conta de novo
    )
