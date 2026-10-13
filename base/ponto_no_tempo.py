"""Base de demonstrações "como era na data" (série 1 da base de ML, PR 6; ADR 0027, exigência 3).

Um **fato** é o valor de uma conta num período de uma empresa (o lucro consolidado de 2022 da
empresa X). O mesmo fato pode ser publicado várias vezes: na versão 1 do documento, numa
reapresentação (versão 2 em diante, lida do ENET) e de novo no balanço seguinte, na coluna do ano
anterior. A base guarda uma linha por **valor diferente** de cada fato, com:

- `divulgado_em`: o dia em que aquele valor ficou público (a entrega do documento à CVM, o
  `DT_RECEB` do índice). Vale a partir desse dia, inclusive. A CVM informa só o dia, não a hora:
  quem decide no próprio dia deve olhar a véspera.
- `ate`: o dia em que outro valor tomou o lugar (vazio = vale até hoje).
- de onde veio: documento, data, versão, coluna ("ultimo" ou "penultimo") e origem ("enet" ou
  "dados_abertos").

Regras: nenhuma linha sem data de divulgação (a base nunca adivinha a data); o mesmo valor
publicado de novo não vira linha nova (vale desde a primeira vez); no mesmo dia, vale o documento
mais novo e a versão maior; valor que some numa versão nova vira uma linha em branco.
`como_era_em(base, data)` devolve um valor por fato, só com o que era público naquela data.
"""

import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from base.contas_cvm import COLUNAS, so_as_contas_das_regras
from base.enet import DocumentoEnet

FATO = ["cnpj", "grupo", "demonstracao", "conta", "inicio", "fim"]
COLUNAS_DA_BASE = (
    "cnpj",
    "empresa",
    "grupo",
    "demonstracao",
    "conta",
    "descricao",
    "inicio",
    "fim",
    "valor",
    "documento",
    "referencia",
    "versao",
    "ordem",
    "origem",
    "divulgado_em",
    "ate",
)
SEM_DATA = "sem_data"  # arquivo dos fatos sem fim de período (não deveria acontecer)


def com_divulgacao(
    contas: pd.DataFrame, indice: pd.DataFrame, origem: str
) -> pd.DataFrame:
    """As contas com a data de entrega da **própria versão** (do índice da CVM) e a origem.

    `indice` vem de `ler_indice` (todas as versões). Versão que não está no índice fica sem data, e
    `montar_base` a recusa.
    """
    entregas = (
        indice.groupby(["cnpj", "referencia", "versao"])["recebido_em"]
        .min()
        .rename("divulgado_em")
        .reset_index()
    )
    publicadas = contas[list(COLUNAS)].merge(
        entregas, on=["cnpj", "referencia", "versao"], how="left"
    )
    return publicadas.assign(origem=origem)


def versoes_antigas(indice: pd.DataFrame) -> pd.DataFrame:
    """As versões que não são a mais nova de cada documento: as que só o ENET tem.

    A mais nova vem dos dados abertos; as anteriores precisam ser baixadas (`base/enet_coleta.py`).
    """
    mais_nova = indice.groupby(["cnpj", "referencia"])["versao"].transform("max")
    return indice[indice["versao"] < mais_nova].reset_index(drop=True)


def publicadas_do_enet(
    documentos: Iterable[DocumentoEnet], indice: pd.DataFrame
) -> pd.DataFrame:
    """As contas de cada versão lida do ENET, no recorte das regras, com a data dela."""
    partes = [so_as_contas_das_regras(d.contas) for d in documentos]
    contas = (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=list(COLUNAS))
    )
    return com_divulgacao(contas, indice, "enet")


def _mesmo_valor(valor: pd.Series, anterior: pd.Series) -> pd.Series:
    return (valor == anterior) | (valor.isna() & anterior.isna())


def montar_base(publicadas: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por valor diferente de cada fato, com `divulgado_em` e `ate`.

    `publicadas`: contas no formato de `base/contas_cvm.py` mais `divulgado_em` e `origem` (ver
    `com_divulgacao`), de quantos documentos e versões houver.
    """
    sem_data = publicadas["divulgado_em"].isna()
    if sem_data.any():
        exemplo = publicadas.loc[sem_data].iloc[0]
        raise ValueError(
            f"{int(sem_data.sum())} contas sem data de divulgação (ex.: {exemplo['cnpj']} "
            f"{exemplo['documento']} {exemplo['referencia']:%d/%m/%Y} versão {exemplo['versao']})"
        )
    base = publicadas.sort_values(
        [*FATO, "divulgado_em", "referencia", "versao"], na_position="first"
    ).reset_index(drop=True)
    base["_fato"] = base.groupby(FATO, dropna=False, sort=False).ngroup()
    # no mesmo dia, fica a última publicação da ordem acima: o documento mais novo, a versão maior
    base = base.drop_duplicates(["_fato", "divulgado_em"], keep="last")
    anterior = base.groupby("_fato")["valor"].shift(1)
    primeira = base["_fato"].ne(base["_fato"].shift(1))
    base = base[primeira | ~_mesmo_valor(base["valor"], anterior)].copy()
    base["ate"] = base.groupby("_fato")["divulgado_em"].shift(-1)
    return base.reindex(columns=list(COLUNAS_DA_BASE)).reset_index(drop=True)


def montar_ano(publicadas: pd.DataFrame, ano: int) -> pd.DataFrame:
    """A base dos fatos cujo período termina em `ano`.

    Um fato de 2022 sai no arquivo de 2022 (coluna "ultimo") e no de 2023 (coluna "penultimo"): quem
    chama junta os dois arquivos antes.
    """
    return montar_base(publicadas[publicadas["fim"].dt.year == ano])


def como_era_em(base: pd.DataFrame, data: object) -> pd.DataFrame:
    """Um valor por fato: o que era público no dia `data` (nada divulgado depois)."""
    dia = pd.Timestamp(data)  # type: ignore[arg-type]
    valia = (base["divulgado_em"] <= dia) & (base["ate"].isna() | (base["ate"] > dia))
    return base[valia].reset_index(drop=True)


def hash_da_base(base: pd.DataFrame) -> str:
    """SHA-256 do conteúdo da base, sem depender da ordem das linhas (exigência 9 da ADR 0027).

    As linhas são ordenadas pelo fato e pela data, e cada valor vira texto num formato fixo
    (números com 17 algarismos significativos, datas ISO), antes de calcular o hash.
    """
    canonica = (
        base.reindex(columns=list(COLUNAS_DA_BASE))
        .sort_values(
            [*FATO, "divulgado_em", "referencia", "versao"], na_position="first"
        )
        .reset_index(drop=True)
    )
    texto = canonica.to_csv(index=False, float_format="%.17g", date_format="%Y-%m-%d")
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _gravar_atomico(destino: Path, gravar: object) -> None:
    temporario = destino.with_name(destino.name + ".parcial")
    gravar(temporario)  # type: ignore[operator]
    os.replace(temporario, destino)


def gravar_parquet(
    base: pd.DataFrame, pasta: Path, origens: list[dict[str, str]] | None = None
) -> list[Path]:
    """Um arquivo por ano do fim do período (`<pasta>/2022.parquet`), gravado sem ficar pela metade.

    Ao lado de cada um, `<ano>.json`: linhas, `sha256_da_base` e as `origens` (endereço e SHA-256 de
    cada original usado), para refazer e conferir. Gravar de novo substitui o ano.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    anos = base["fim"].dt.year.astype("Int64").astype(str).replace("<NA>", SEM_DATA)
    arquivos = []
    for ano, parte in base.groupby(anos):
        destino = pasta / f"{ano}.parquet"
        _gravar_atomico(
            destino, lambda caminho, p=parte: p.to_parquet(caminho, index=False)
        )
        manifesto = {
            "ano": ano,
            "linhas": len(parte),
            "sha256_da_base": hash_da_base(parte),
            "origens": origens or [],
        }
        texto = json.dumps(manifesto, ensure_ascii=False, indent=1)
        _gravar_atomico(
            pasta / f"{ano}.json",
            lambda caminho, t=texto: Path(caminho).write_text(t, encoding="utf-8"),
        )
        arquivos.append(destino)
    return arquivos


def conferir_pasta(pasta: Path) -> dict[str, bool]:
    """Para cada ano, se o Parquet ainda tem o hash anotado no `<ano>.json`."""
    resultado = {}
    for arquivo in sorted(pasta.glob("*.parquet")):
        manifesto = pasta / f"{arquivo.stem}.json"
        anotado = (
            json.loads(manifesto.read_text(encoding="utf-8"))
            if manifesto.exists()
            else {}
        )
        atual = hash_da_base(pd.read_parquet(arquivo))
        resultado[arquivo.stem] = anotado.get("sha256_da_base") == atual
    return resultado


def ler_parquet(pasta: Path) -> pd.DataFrame:
    """A base inteira de volta (todos os anos)."""
    partes = [pd.read_parquet(arquivo) for arquivo in sorted(pasta.glob("*.parquet"))]
    if not partes:
        return pd.DataFrame(columns=list(COLUNAS_DA_BASE))
    return pd.concat(partes, ignore_index=True)
