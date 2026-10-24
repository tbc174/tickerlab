"""O cadastro da Receita de uma empresa, lido da vista do CNPJ publicada no servidor
(`base.porta.vista_do_cnpj`).

A busca por CNPJ lê daqui o que mostra das empresas sem ficha na CVM: os estabelecimentos da raiz, o Simples e
o MEI, o quadro de sócios e as mudanças de 12 meses. A porta é o CNPJ: uma empresa por chamada, lida só nos
grupos do Parquet que têm a raiz dela (a vista é ordenada pela raiz). Sem vista (antes de ela chegar ao
servidor) ou sem o CNPJ nela, a resposta é None, e a busca segue como antes.

Os sócios saem só por `base.pessoas.consulta.socios_da_empresa`: o nome da pessoa física depende do portão da
fonte e das oposições, e a vista nem tem o pseudônimo (o restrito com os nomes fica em casa).
"""

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from base.pessoas import consulta
from base.porta import vista_do_cnpj

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


def cadastro_do_cnpj(cnpj: str, vista: Path | None = None) -> CadastroDaReceita | None:
    """O cadastro da empresa do CNPJ (14 caracteres, sem pontuação); None se a vista não o tem."""
    vista = vista or pasta_da_vista()
    manifesto = vista_do_cnpj.manifesto(vista)
    if manifesto is None:
        return None
    raiz = cnpj[: vista_do_cnpj.TAMANHO_DA_RAIZ]
    estabelecimentos = vista_do_cnpj.da_raiz(vista, "vigente", "estabelecimentos", raiz)
    if estabelecimentos.empty or cnpj not in set(estabelecimentos["cnpj"]):
        return None
    simples = vista_do_cnpj.da_raiz(vista, "vigente", "simples", raiz)
    return CadastroDaReceita(
        mes=manifesto["mes"],
        disponivel_em=date.fromisoformat(manifesto["disponivel_em"]),
        estabelecimentos=estabelecimentos.sort_values(
            ["matriz", "cnpj"], ascending=[False, True]
        ).reset_index(drop=True),
        simples=simples.iloc[0].to_dict() if not simples.empty else None,
        socios=consulta.socios_da_empresa(vista, vista / RESTRITO, cnpj),
        mudancas={
            tabela: vista_do_cnpj.da_raiz(vista, "mudancas", tabela, raiz)
            for tabela in vista_do_cnpj.MUDANCAS
        },
    )
