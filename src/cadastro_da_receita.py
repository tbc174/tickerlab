"""O cadastro da Receita de uma empresa, lido da vista do CNPJ publicada no servidor (`base.vista_do_cnpj`).

A busca por CNPJ lê daqui o que mostra das empresas sem ficha na CVM: os estabelecimentos da raiz, o Simples e
o MEI, o quadro de sócios e as mudanças de 12 meses. A porta é o CNPJ: uma empresa por chamada, lida só nos
grupos do Parquet que têm a raiz dela (a vista é ordenada pela raiz). Sem vista (antes de ela chegar ao
servidor) ou sem o CNPJ nela, a resposta é None, e a busca segue como antes.

Os sócios saem só por `base.pessoas.consulta.socios_da_empresa`: o nome da pessoa física depende do portão da
fonte e das oposições, e a vista nem tem o pseudônimo (o restrito com os nomes fica em casa).
"""

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from base import vista_do_cnpj
from base.pessoas import consulta

PASTA_RAIZ = Path(__file__).resolve().parent.parent
VARIAVEL_DA_PASTA = "TICKERLAB_CNPJ"
PASTA_PADRAO = PASTA_RAIZ / "dados_locais" / "cnpj" / "atual"
RESTRITO = (
    "restrito"  # nunca publicado: sem ele (e com o portão fechado) nenhum nome sai
)


@dataclass(frozen=True)
class CadastroDaReceita:
    mes: str  # o mês da publicação da Receita (AAAA-MM)
    disponivel_em: date  # desde quando aquela publicação era pública
    estabelecimentos: pd.DataFrame  # todos os da raiz, a matriz primeiro
    simples: (
        dict | None
    )  # a linha do Simples e do MEI; None se a empresa nunca esteve lá
    socios: pd.DataFrame  # as colunas de `consulta.COLUNAS_DE_SAIDA`
    mudancas: dict[str, pd.DataFrame]  # por tabela da vista (`vista_do_cnpj.MUDANCAS`)


def pasta_da_vista() -> Path:
    return Path(os.environ.get(VARIAVEL_DA_PASTA) or PASTA_PADRAO)


def _da_raiz(vista: Path, grupo: str, tabela: str, raiz: str) -> pd.DataFrame:
    arquivo = vista / grupo / tabela / f"{raiz[: vista_do_cnpj.PREFIXO]}.parquet"
    if not arquivo.is_file():
        return pd.DataFrame()
    filtro = [("cnpj_basico", "==", raiz)]
    return pq.read_table(arquivo, filters=filtro).to_pandas()


def _manifesto(vista: Path) -> dict | None:
    arquivo = vista / "manifesto.json"
    if not arquivo.is_file():
        return None
    return json.loads(arquivo.read_text(encoding="utf-8"))


def cadastro_do_cnpj(cnpj: str, vista: Path | None = None) -> CadastroDaReceita | None:
    """O cadastro da empresa do CNPJ (14 caracteres, sem pontuação); None se a vista não o tem."""
    vista = vista or pasta_da_vista()
    manifesto = _manifesto(vista)
    if manifesto is None:
        return None
    raiz = cnpj[: vista_do_cnpj.TAMANHO_DA_RAIZ]
    estabelecimentos = _da_raiz(vista, "vigente", "estabelecimentos", raiz)
    if estabelecimentos.empty or cnpj not in set(estabelecimentos["cnpj"]):
        return None
    simples = _da_raiz(vista, "vigente", "simples", raiz)
    return CadastroDaReceita(
        mes=manifesto["mes"],
        disponivel_em=date.fromisoformat(manifesto["disponivel_em"]),
        estabelecimentos=estabelecimentos.sort_values(
            ["matriz", "cnpj"], ascending=[False, True]
        ).reset_index(drop=True),
        simples=simples.iloc[0].to_dict() if not simples.empty else None,
        socios=consulta.socios_da_empresa(vista, vista / RESTRITO, cnpj),
        mudancas={
            tabela: _da_raiz(vista, "mudancas", tabela, raiz)
            for tabela in vista_do_cnpj.MUDANCAS
        },
    )
