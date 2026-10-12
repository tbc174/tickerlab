"""Baixa todas as séries gratuitas da Pesquisa 2 e escreve o relatório de qualidade.

    python -m trader.p2.baixar

Grava em `dados_p2/` (fora do Git) uma série por arquivo e `dados_p2/relatorio_de_qualidade.csv`
com o resultado de cada uma e se o mercado entra no universo. Só lê dados: não olha desempenho.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from trader.p2.dividendos import baixar_shiller
from trader.p2.fontes import (
    PASTA_PADRAO,
    baixar_fred,
    baixar_mt5,
    baixar_yahoo,
    medir_qualidade,
    salvar_serie,
)
from trader.p2.mercados import JUROS_CURTOS, MERCADOS, entra_no_universo

Baixador = Callable[[str], pd.Series]
INICIO_DO_BIS = "1970-01-01"
ARQUIVO_DO_BIS = "bis_taxas_basicas.parquet"
ARQUIVO_DE_SHILLER = "shiller_dividendos.parquet"
BAIXADORES_PADRAO: dict[str, Baixador] = {
    "fred": baixar_fred,
    "yahoo": baixar_yahoo,
    "mt5": baixar_mt5,
}


def _linha_do_relatorio(
    papel: str,
    codigo: str,
    fonte: str,
    serie_id: str,
    serie: pd.Series | None,
    e_preco: bool,
    erro: str = "",
    entra: bool | None = None,
) -> dict[str, object]:
    qualidade = medir_qualidade(serie, e_preco) if serie is not None else None
    return {
        "papel": papel,
        "codigo": codigo,
        "fonte": fonte,
        "serie": serie_id,
        "pontos": qualidade.pontos if qualidade else 0,
        "inicio": qualidade.inicio.date()
        if qualidade and qualidade.inicio is not None
        else None,
        "fim": qualidade.fim.date()
        if qualidade and qualidade.fim is not None
        else None,
        "maior_lacuna_dias": qualidade.maior_lacuna_em_dias if qualidade else None,
        "saltos_suspeitos": qualidade.saltos_suspeitos if qualidade else None,
        "aprovada": qualidade.aprovada if qualidade else False,
        "entra_no_universo": entra,
        "erro": erro,
    }


def _baixar_uma(
    baixadores: dict[str, Baixador], fonte: str, serie_id: str, pasta: Path
) -> tuple[pd.Series | None, str]:
    try:
        serie = baixadores[fonte](serie_id)
    except Exception as erro:  # noqa: BLE001 (uma série ruim não pode parar as outras)
        return None, str(erro)[:120]
    salvar_serie(serie, fonte, serie_id, pasta)
    return serie, ""


def _baixar_bis() -> pd.DataFrame:
    from trader.juros import baixar_do_bis

    return baixar_do_bis(inicio=INICIO_DO_BIS)


def _baixar_extras(
    pasta: Path,
    baixar_bis: Callable[[], pd.DataFrame],
    baixar_dividendos: Callable[[], pd.Series],
) -> list[dict[str, object]]:
    """Taxas básicas do BIS (desde 1970) e dividendos do S&P (Shiller): uma linha de relatório cada."""
    linhas = []
    for codigo, baixar, arquivo in (
        ("BIS", baixar_bis, ARQUIVO_DO_BIS),
        ("SHILLER", baixar_dividendos, ARQUIVO_DE_SHILLER),
    ):
        try:
            dados = baixar()
        except Exception as erro:  # noqa: BLE001 (uma fonte ruim não pode parar as outras)
            linhas.append(
                _linha_do_relatorio(
                    "extra",
                    codigo,
                    codigo.lower(),
                    arquivo,
                    None,
                    False,
                    str(erro)[:120],
                )
            )
            continue
        tabela = dados.to_frame("valor") if isinstance(dados, pd.Series) else dados
        tabela.to_parquet(pasta / arquivo)
        primeira = tabela.dropna(how="all")
        serie = pd.Series(1.0, index=primeira.index)
        linhas.append(
            _linha_do_relatorio("extra", codigo, codigo.lower(), arquivo, serie, False)
        )
    return linhas


def baixar_tudo(
    baixadores: dict[str, Baixador] | None = None,
    pasta: Path = PASTA_PADRAO,
    baixar_bis: Callable[[], pd.DataFrame] | None = None,
    baixar_dividendos: Callable[[], pd.Series] | None = None,
) -> pd.DataFrame:
    """Baixa os mercados e os juros curtos; devolve (e grava) o relatório de qualidade."""
    baixadores = baixadores or BAIXADORES_PADRAO
    linhas = []
    for mercado in MERCADOS:
        serie, erro = _baixar_uma(baixadores, mercado.fonte, mercado.serie, pasta)
        inicio = serie.index[0] if serie is not None and not serie.empty else None
        linhas.append(
            _linha_do_relatorio(
                "mercado",
                mercado.codigo,
                mercado.fonte,
                mercado.serie,
                serie,
                e_preco=not mercado.rendimento,
                erro=erro,
                entra=entra_no_universo(mercado, inicio),
            )
        )
    for moeda, serie_id in JUROS_CURTOS.items():
        serie, erro = _baixar_uma(baixadores, "fred", serie_id, pasta)
        linhas.append(
            _linha_do_relatorio(
                "juros", moeda, "fred", serie_id, serie, e_preco=False, erro=erro
            )
        )
    pasta.mkdir(parents=True, exist_ok=True)
    linhas += _baixar_extras(
        pasta, baixar_bis or _baixar_bis, baixar_dividendos or baixar_shiller
    )
    relatorio = pd.DataFrame(linhas)
    relatorio.to_csv(pasta / "relatorio_de_qualidade.csv", index=False)
    return relatorio


def main() -> int:
    relatorio = baixar_tudo()
    print(relatorio.drop(columns=["erro"]).to_string(index=False))
    falhas = relatorio[relatorio["erro"] != ""]
    for _, linha in falhas.iterrows():
        print(f"FALHOU {linha['codigo']} ({linha['serie']}): {linha['erro']}")
    return 1 if not falhas.empty else 0


if __name__ == "__main__":
    sys.exit(main())
