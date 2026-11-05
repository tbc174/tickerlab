"""Montagem em Parquet dos cadastros que a fonte publica inteiros a cada vez (linha 679 da fila).

Os leitores da linha 227 (`ans_operadoras`, `susep_cadastro`, `mte_lista_suja`, `ibama_embargos`) sabem ler
um arquivo guardado; aqui os retratos viram uma tabela que só cresce (`base/retratos.py`), gravada em
`<pasta>/<tabela>/<cadastro>.parquet` com manifesto, no molde de `base/licencas.py`.

- **Um endereço só por cadastro**: se vários endereços da fonte casam com `url_termina_em` (a lista do
  MTE linka um CSV por layout), vale o do retrato mais novo; os outros ficam de fora e são contados em
  `enderecos_ignorados`. Misturar layouts faria o 2º arquivo parecer uma mudança em massa do 1º.
- **`trata_como_pessoa`** (ADR 0075): empresário individual, natureza do grupo 4, MEI ou CNPJ que a
  Receita guardada não tem. Linha sem CNPJ (entidade estrangeira da SUSEP) nunca é de pessoa.
- Sem retrato novo desde a última montagem, o cadastro é pulado (`refazer` relê mesmo assim).
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import retratos as motor
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from base.pgfn import pessoas_pela_receita
from src.versao_do_codigo import versao_do_codigo

JA_MONTADO = {"ja_montado": 1}  # no resumo: nenhum retrato novo desde a última montagem
ORDEM = ["id_na_fonte", "visto_em"]
CARIMBOS_DA_LINHA = ["consta", "trata_como_pessoa", "visto_em", "disponivel_em"]

Leitor = Callable[[motor.Retrato], tuple[pd.DataFrame, dict[str, int]]]
Juntador = Callable[
    [list[tuple[motor.Retrato, pd.DataFrame]]], tuple[pd.DataFrame, int]
]
Achador = Callable[[sa.Connection], tuple[list[motor.Retrato], int]]


@dataclass(frozen=True)
class Cadastro:
    """Um cadastro em retrato: de que fonte vem, como se lê um arquivo e como se juntam os arquivos."""

    tabela: str
    nome: str
    fonte: str
    ler: Leitor
    juntar: Juntador
    colunas: tuple[str, ...]
    datas: tuple[str, ...]
    url_termina_em: str | None = None
    achar: Achador | None = (
        None  # quando o cadastro não é um arquivo por retrato (o GLEIF: páginas)
    )


def _do_endereco_mais_novo(
    achados: list[motor.Retrato],
) -> tuple[list[motor.Retrato], int]:
    """Só os retratos do endereço do retrato mais novo, e quantos endereços ficaram de fora."""
    if not achados:
        return [], 0
    mais_novo = max(achados, key=lambda r: r.baixado_em).url
    return [r for r in achados if r.url == mais_novo], len(
        {r.url for r in achados} - {mais_novo}
    )


def _origens(achados: list[motor.Retrato]) -> list[dict[str, str]]:
    return [{"url": r.url, "sha256": r.sha256} for r in achados]


def _lidos(
    achados: list[motor.Retrato], cadastro: Cadastro, resumo: dict[str, int]
) -> list[tuple[motor.Retrato, pd.DataFrame]]:
    lidos = []
    for retrato in achados:
        tabela, contagem = cadastro.ler(retrato)
        for chave, valor in contagem.items():
            resumo[chave] = resumo.get(chave, 0) + valor
        lidos.append((retrato, tabela))
    return lidos


def como_numeros(pessoas: Collection[str] | np.ndarray) -> np.ndarray:
    if isinstance(pessoas, np.ndarray):
        return pessoas
    return cnpjs.ordenados(cnpjs.raizes_em_numeros(pd.Series(list(pessoas), dtype=str)))


def raizes(tabela: pd.DataFrame) -> pd.Series:
    return tabela["cnpj_basico"].dropna().drop_duplicates().astype(str)


def de_pessoa(tabela: pd.DataFrame, pessoas: np.ndarray) -> pd.Series:
    """Para cada linha, se a raiz do CNPJ é de pessoa (sem CNPJ: falso)."""
    com_cnpj = tabela["cnpj_basico"].notna()
    resposta = pd.Series(False, index=tabela.index)
    if com_cnpj.any():
        raizes = tabela.loc[com_cnpj, "cnpj_basico"].astype(str)
        resposta[com_cnpj] = cnpjs.contem(pessoas, cnpjs.raizes_em_numeros(raizes))
    return resposta


def _para_gravar(
    tabela: pd.DataFrame, cadastro: Cadastro, pessoas: np.ndarray, agora: datetime
) -> pd.DataFrame:
    datas = [*cadastro.datas, "visto_em", "disponivel_em"]
    return (
        tabela.assign(
            trata_como_pessoa=de_pessoa(tabela, pessoas),
            **{c: pd.to_datetime(tabela[c]).dt.date for c in datas},
            consta=tabela["consta"].astype(bool),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )[[*cadastro.colunas, *CARIMBOS_DA_LINHA, *LINHAGEM]]
        .sort_values(ORDEM, kind="stable")
        .reset_index(drop=True)
    )


def montar(
    cadastros: tuple[Cadastro, ...],
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/<tabela>/<cadastro>.parquet` para cada cadastro com arquivo guardado.

    Cadastro sem arquivo guardado fica de fora do resumo. `pessoas`: as raízes de pessoa já sabidas;
    sem elas, pergunta à Receita guardada (`base/pgfn.py`).
    """
    resumo: dict[str, dict[str, int]] = {}
    for cadastro in cadastros:
        achados, ignorados = (
            cadastro.achar(conexao)
            if cadastro.achar
            else _do_endereco_mais_novo(
                motor.retratos(conexao, cadastro.fonte, cadastro.url_termina_em)
            )
        )
        if not achados:
            continue
        destino = pasta / cadastro.tabela / cadastro.nome
        if not refazer and origens_gravadas(destino) == _origens(achados):
            resumo[cadastro.nome] = JA_MONTADO
            continue
        contagem: dict[str, int] = {}
        tabela, pulados = cadastro.juntar(_lidos(achados, cadastro, contagem))
        if pessoas is None:
            sabidas = pessoas_pela_receita(
                conexao, cnpjs.ordenados(cnpjs.raizes_em_numeros(raizes(tabela)))
            )
        else:
            sabidas = como_numeros(pessoas)
        gravar_se_mudou(
            _para_gravar(tabela, cadastro, sabidas, agora),
            destino,
            _origens(achados),
            ORDEM,
            carimbos=LINHAGEM,
        )
        resumo[cadastro.nome] = {
            **contagem,
            "retratos": len(achados),
            "retratos_pulados": pulados,
            "enderecos_ignorados": ignorados,
            "na_tabela": len(tabela),
        }
    return resumo
