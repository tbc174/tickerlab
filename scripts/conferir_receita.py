"""Confere a Receita contra outro órgão (exigência 6 de `cnpj_empresas_pj` e `cnpj_estabelecimentos_pj`).

    python -m scripts.conferir_receita [--par NOME]

Roda os pares de `base/cruzada_por_taxa.py` (UF contra ANATEL, ANVISA, ANCINE e IF.data; situação contra o
IF.data; razão social contra a CVM e o IF.data), todos pela porta. Grava `<acervo>/placar/<dia>/cruzada_receita.json`
(só nomes de par, contagens, taxa, piso e causas: nenhum CNPJ nem nome) e, ao lado, 50 divergências de cada par
em `amostra_receita/` para uma pessoa conferir; essa amostra tem CNPJ e fica no acervo, nunca no repositório.
Sai com 1 se algum par ficou abaixo do piso, e com 2 se alguma causa "não explicado" passou do máximo (avisar a
Diretoria antes de gravar a prontidão).

Roda: manual, a cada rodada de prova da exigência 6 das tabelas da Receita (a prova vale 90 dias).
"""

import argparse
import json
import sys
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from base import porta
from base.cruzada_por_taxa import (
    NAO_EXPLICADO,
    PARES,
    ParPorTaxa,
    RelatorioPorTaxa,
    avaliar,
    causa_da_situacao,
    causa_da_uf,
    causa_do_nome,
    nomes_concordam,
)
from base.parquet import gravar_atomico
from src import acervo

BRASILIA = ZoneInfo("America/Sao_Paulo")
LOTE = 50_000
TAMANHO_DA_AMOSTRA = 50
SEMENTE = 20261111
ATIVA = "02"


def _digitos(serie: pd.Series) -> pd.Series:
    return serie.astype("string").str.replace(r"\D", "", regex=True)


def _lotes(valores: Sequence[str]) -> Iterator[list[str]]:
    for inicio in range(0, len(valores), LOTE):
        yield list(valores[inicio : inicio + LOTE])


def _ler_por_lotes(
    p: porta.Porta, tabela: str, coluna: str, valores: Sequence[str], colunas: list[str]
) -> pd.DataFrame:
    partes = [
        p.ler(tabela, filtros={coluna: lote}, colunas=colunas)
        for lote in _lotes(sorted(set(valores)))
    ]
    return (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=colunas)
    )


def _idade_em_anos(datas: pd.Series, hoje: pd.Timestamp) -> pd.Series:
    return (hoje - pd.to_datetime(datas, errors="coerce")).dt.days / 365.25


def _ufs_por_raiz(p: porta.Porta, raizes: Sequence[str]) -> dict[str, set[str]]:
    est = _ler_por_lotes(
        p, "cnpj_estabelecimentos_pj", "cnpj_basico", raizes, ["cnpj_basico", "uf"]
    )
    return est.groupby("cnpj_basico")["uf"].agg(lambda s: set(s.dropna())).to_dict()


def _comparar_uf(
    p: porta.Porta,
    outro: pd.DataFrame,
    receita: pd.DataFrame,
    chave: str,
    hoje: pd.Timestamp,
) -> pd.DataFrame:
    """`outro`: chave, uf, data. `receita`: chave, uf, situacao_cadastral, cnpj_basico."""
    junto = outro.merge(receita, on=chave, suffixes=("_outro", "_receita"))
    junto["concorda"] = junto["uf_outro"] == junto["uf_receita"]
    junto["idade"] = _idade_em_anos(junto["data"], hoje)
    divergentes = junto[~junto["concorda"]]
    ufs = _ufs_por_raiz(p, divergentes["cnpj_basico"].dropna().unique().tolist())
    junto["causa"] = None
    junto.loc[~junto["concorda"], "causa"] = [
        causa_da_uf(
            linha.uf_outro,
            ufs.get(linha.cnpj_basico, set()),
            None if pd.isna(linha.idade) else float(linha.idade),
            str(linha.situacao_cadastral),
        )
        for linha in divergentes.itertuples()
    ]
    return junto


def _uf_de_um_cnpj(p: porta.Porta, tabela: str, hoje: pd.Timestamp) -> pd.DataFrame:
    """ANATEL, ANVISA e ANCINE: o registro mais recente de cada CNPJ de 14 dígitos com UF."""
    colunas = ["cnpj", "uf", "publicado_em", "concedido_em"]
    outro = p.ler(tabela, colunas=colunas)
    outro["cnpj"] = _digitos(outro["cnpj"])
    outro["data"] = outro["publicado_em"].fillna(outro["concedido_em"])
    outro = outro[outro["cnpj"].str.len() == 14].dropna(subset=["uf"])
    outro = outro.sort_values("data", ascending=False).drop_duplicates("cnpj")[
        ["cnpj", "uf", "data"]
    ]
    receita = _ler_por_lotes(
        p,
        "cnpj_estabelecimentos_pj",
        "cnpj",
        outro["cnpj"].tolist(),
        ["cnpj", "cnpj_basico", "uf", "situacao_cadastral"],
    )
    return _comparar_uf(p, outro, receita, "cnpj", hoje)


def _ifdata(p: porta.Porta) -> pd.DataFrame:
    """A linha mais recente de cada raiz de CNPJ no cadastro do IF.data."""
    colunas = ["cnpj_raiz", "instituicao", "uf", "situacao", "data_base"]
    ifdata = p.ler("ifdata_cadastro", colunas=colunas).dropna(subset=["cnpj_raiz"])
    ifdata["cnpj_basico"] = _digitos(ifdata["cnpj_raiz"]).str.zfill(8)
    return ifdata.sort_values("data_base", ascending=False).drop_duplicates(
        "cnpj_basico"
    )


def _matrizes(p: porta.Porta, raizes: Sequence[str]) -> pd.DataFrame:
    est = _ler_por_lotes(
        p,
        "cnpj_estabelecimentos_pj",
        "cnpj_basico",
        raizes,
        ["cnpj_basico", "matriz", "uf", "situacao_cadastral"],
    )
    return est[est["matriz"].astype(bool)].drop_duplicates("cnpj_basico")


def _par_uf_ifdata(p: porta.Porta, hoje: pd.Timestamp) -> pd.DataFrame:
    ifdata = _ifdata(p).dropna(subset=["uf"])
    outro = ifdata.rename(columns={"data_base": "data"})[["cnpj_basico", "uf", "data"]]
    return _comparar_uf(
        p, outro, _matrizes(p, outro["cnpj_basico"].tolist()), "cnpj_basico", hoje
    )


def _par_situacao_ifdata(p: porta.Porta, hoje: pd.Timestamp) -> pd.DataFrame:
    ifdata = _ifdata(p)
    ativas = ifdata[ifdata["situacao"] == "A"]
    junto = ativas.merge(
        _matrizes(p, ativas["cnpj_basico"].tolist()),
        on="cnpj_basico",
        suffixes=("_outro", "_receita"),
    )
    junto["concorda"] = junto["situacao_cadastral"] == ATIVA
    junto["idade"] = _idade_em_anos(junto["data_base"], hoje)
    junto["causa"] = None
    nao = ~junto["concorda"]
    junto.loc[nao, "causa"] = [
        causa_da_situacao(
            str(linha.situacao_cadastral),
            None if pd.isna(linha.idade) else float(linha.idade),
        )
        for linha in junto[nao].itertuples()
    ]
    return junto


def _comparar_nomes(p: porta.Porta, outro: pd.DataFrame) -> pd.DataFrame:
    """`outro`: cnpj_basico, nome. A razão social vem de `cnpj_empresas_pj`."""
    empresas = _ler_por_lotes(
        p,
        "cnpj_empresas_pj",
        "cnpj_basico",
        outro["cnpj_basico"].tolist(),
        ["cnpj_basico", "razao_social"],
    )
    junto = outro.merge(empresas.drop_duplicates("cnpj_basico"), on="cnpj_basico")
    junto["concorda"] = [
        nomes_concordam(a, b)
        for a, b in zip(junto["nome"], junto["razao_social"], strict=True)
    ]
    junto["causa"] = None
    nao = ~junto["concorda"]
    junto.loc[nao, "causa"] = [
        causa_do_nome(a, b)
        for a, b in zip(
            junto.loc[nao, "nome"], junto.loc[nao, "razao_social"], strict=True
        )
    ]
    return junto


def _par_nome_cvm(p: porta.Porta, _hoje: pd.Timestamp) -> pd.DataFrame:
    fca = p.ler("fca_geral", colunas=["cnpj", "empresa", "referencia"]).dropna(
        subset=["cnpj", "empresa"]
    )
    fca["cnpj_basico"] = _digitos(fca["cnpj"]).str[:8]
    fca = fca.sort_values("referencia", ascending=False).drop_duplicates("cnpj_basico")
    return _comparar_nomes(
        p, fca.rename(columns={"empresa": "nome"})[["cnpj_basico", "nome"]]
    )


def _par_nome_ifdata(p: porta.Porta, _hoje: pd.Timestamp) -> pd.DataFrame:
    ifdata = _ifdata(p).dropna(subset=["instituicao"])
    return _comparar_nomes(
        p, ifdata.rename(columns={"instituicao": "nome"})[["cnpj_basico", "nome"]]
    )


COMPARADORES: dict[str, Callable[[porta.Porta, pd.Timestamp], pd.DataFrame]] = {
    "uf_anatel_x_receita": lambda p, h: _uf_de_um_cnpj(p, "anatel_outorgas", h),
    "uf_anvisa_x_receita": lambda p, h: _uf_de_um_cnpj(p, "anvisa_registros", h),
    "uf_ancine_x_receita": lambda p, h: _uf_de_um_cnpj(p, "ancine_agentes", h),
    "uf_ifdata_x_receita": _par_uf_ifdata,
    "situacao_ifdata_x_receita": _par_situacao_ifdata,
    "razao_social_cvm_x_receita": _par_nome_cvm,
    "razao_social_ifdata_x_receita": _par_nome_ifdata,
}


def conferir(
    p: porta.Porta, par: ParPorTaxa, hoje: pd.Timestamp
) -> tuple[RelatorioPorTaxa, pd.DataFrame]:
    comparacao = COMPARADORES[par.nome](p, hoje)
    divergentes = comparacao[~comparacao["concorda"].astype(bool)]
    amostra = divergentes.sample(
        min(TAMANHO_DA_AMOSTRA, len(divergentes)), random_state=SEMENTE
    )
    return avaliar(par, comparacao), amostra


def gravar(
    dia: str, relatorios: list[RelatorioPorTaxa], amostras: dict[str, pd.DataFrame]
) -> Path:
    raiz = acervo.pasta_do_acervo()
    if raiz is None:
        raise SystemExit("o acervo está desligado: defina TICKERLAB_ACERVO")
    pasta = raiz / "placar" / dia
    (pasta / "amostra_receita").mkdir(parents=True, exist_ok=True)
    for nome, amostra in amostras.items():
        csv = amostra.drop(columns=["data"], errors="ignore").to_csv(
            index=False, sep=";"
        )
        gravar_atomico(
            pasta / "amostra_receita" / f"{nome}.csv",
            lambda t, c=csv: t.write_text(c, encoding="utf-8"),
        )
    texto = json.dumps(
        {
            "dia": dia,
            "aprovado": all(r.aprovado for r in relatorios if not r.informativo),
            "avisa_a_diretoria": any(
                r.avisa_a_diretoria for r in relatorios if not r.informativo
            ),
            "pares": [r.como_dict() for r in relatorios],
        },
        ensure_ascii=False,
        indent=2,
    )
    destino = pasta / "cruzada_receita.json"
    gravar_atomico(destino, lambda t: t.write_text(texto, encoding="utf-8"))
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--par", choices=[par.nome for par in PARES])
    args = parser.parse_args(argv)
    agora = datetime.now(BRASILIA)
    hoje = pd.Timestamp(agora.date())
    relatorios, amostras = [], {}
    with porta.abrir() as p:
        for par in [x for x in PARES if not args.par or x.nome == args.par]:
            relatorio, amostra = conferir(p, par, hoje)
            relatorios.append(relatorio)
            amostras[par.nome] = amostra
            marca = "ok" if relatorio.aprovado else "ABAIXO DO PISO"
            marca += " (informativo, não conta)" if relatorio.informativo else ""
            print(
                f"{par.nome}: {relatorio.concordam}/{relatorio.comparadas} = {relatorio.taxa:.1%} "
                f"(piso {par.piso:.0%}) {marca}; não explicado {relatorio.nao_explicado:.0%} das divergências"
            )
            for causa, n in sorted(relatorio.causas.items(), key=lambda x: -x[1]):
                print(
                    f"    {n:>7}  {causa}"
                    + (
                        "  <-- avisar a Diretoria"
                        if causa == NAO_EXPLICADO and relatorio.avisa_a_diretoria
                        else ""
                    )
                )
    print(f"gravado em {gravar(agora.date().isoformat(), relatorios, amostras)}")
    valem = [r for r in relatorios if not r.informativo]
    if not all(r.aprovado for r in valem):
        return 1
    return 2 if any(r.avisa_a_diretoria for r in valem) else 0


if __name__ == "__main__":
    sys.exit(main())
