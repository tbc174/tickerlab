"""Uma tabela da base em Parquet com manifesto (série 3 da base de ML, PR 3; ADR 0027, exigência 9;
ADR 0055, exigência 13).

Para as fontes novas que não são "por ano de balanço" (código da ação, emissores, cadastros): grava
`<nome>.parquet` sem ficar pela metade e, ao lado, `<nome>.json` com as linhas, o SHA-256 do
conteúdo (independente da ordem das linhas), a ordem usada no hash, as origens (endereço e SHA-256 de
cada original) e a versão do código que gravou. `conferir_tabela` diz se o Parquet ainda é o anotado.
"""

import hashlib
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from src.versao_do_codigo import versao_do_codigo

log = logging.getLogger(__name__)
ALGARISMOS_SIGNIFICATIVOS = "%.17g"  # o mesmo número sempre vira o mesmo texto


def gravar_atomico(destino: Path, gravar: Callable[[Path], object]) -> None:
    """Grava num arquivo ao lado e troca de nome no fim: quem lê nunca vê o arquivo pela metade."""
    temporario = destino.with_name(destino.name + ".parcial")
    gravar(temporario)
    os.replace(temporario, destino)


def hash_da_tabela(tabela: pd.DataFrame, ordem: list[str]) -> str:
    """SHA-256 do conteúdo, sem depender da ordem das linhas: ordena por `ordem` e por todas as colunas."""
    canonica = tabela.sort_values(
        [*ordem, *[c for c in tabela.columns if c not in ordem]],
        na_position="first",
        kind="stable",
    ).reset_index(drop=True)
    texto = canonica.to_csv(
        index=False, float_format=ALGARISMOS_SIGNIFICATIVOS, date_format="%Y-%m-%d"
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def gravar_tabela(
    tabela: pd.DataFrame, destino: Path, origens: list[dict[str, str]], ordem: list[str]
) -> Path:
    """Grava `<destino>.parquet` e o manifesto `<destino>.json`; devolve o caminho do Parquet."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    arquivo = destino.with_suffix(".parquet")
    gravar_atomico(arquivo, lambda caminho: tabela.to_parquet(caminho, index=False))
    manifesto = {
        "linhas": len(tabela),
        "sha256_da_tabela": hash_da_tabela(tabela, ordem),
        "ordem": ordem,
        "origens": origens,
        "versao_do_codigo": versao_do_codigo(),
    }
    texto = json.dumps(manifesto, ensure_ascii=False, indent=1)
    gravar_atomico(
        destino.with_suffix(".json"),
        lambda caminho: Path(caminho).write_text(texto, encoding="utf-8"),
    )
    return arquivo


def ler_tabela(arquivo: Path) -> pd.DataFrame:
    return pd.read_parquet(arquivo)


def conferir_tabela(arquivo: Path) -> bool:
    """O Parquet ainda tem o hash anotado no manifesto? (False sem manifesto)"""
    manifesto = arquivo.with_suffix(".json")
    if not manifesto.exists():
        return False
    anotado = json.loads(manifesto.read_text(encoding="utf-8"))
    return anotado.get("sha256_da_tabela") == hash_da_tabela(
        ler_tabela(arquivo), anotado.get("ordem", [])
    )


# --- versões: quando a fonte regrava um arquivo, a tabela anterior fica guardada ----------------
GRAVADO, IGUAL = "gravado", "igual"


def origens_gravadas(destino: Path) -> list[dict[str, str]] | None:
    """As origens anotadas no manifesto de `destino` (None se ainda não foi gravado)."""
    manifesto = destino.with_suffix(".json")
    if not manifesto.exists():
        return None
    return json.loads(manifesto.read_text(encoding="utf-8")).get("origens")


def _hash_gravado(destino: Path) -> str | None:
    manifesto = destino.with_suffix(".json")
    return json.loads(manifesto.read_text(encoding="utf-8")).get("sha256_da_tabela")


def guardar_versao_anterior(destino: Path) -> Path:
    """`<destino>.parquet` e `.json` viram `<destino>.v<N>`, com o primeiro N livre."""
    n = 1
    while destino.with_name(f"{destino.name}.v{n}.parquet").exists():
        n += 1
    versao = destino.with_name(f"{destino.name}.v{n}")
    for extensao in (".parquet", ".json"):
        destino.with_name(destino.name + extensao).rename(
            versao.with_name(versao.name + extensao)
        )
    log.info(
        "%s mudou na fonte: a versão anterior ficou como %s", destino.name, versao.name
    )
    return versao


def gravar_com_versoes(
    montar: Callable[[], pd.DataFrame],
    destino: Path,
    origens: list[dict[str, str]],
    ordem: list[str],
) -> str:
    """Grava a tabela se o conteúdo mudou (`GRAVADO`), guardando a anterior; senão, `IGUAL`.

    `montar` só é chamada quando precisa: com as mesmas origens, nada é lido nem regravado. Com
    origens novas e o mesmo conteúdo (o BC devolve o cadastro do IF.data com outros bytes), fica a
    tabela atual com o original anterior, que continua no acervo: versão só quando o dado muda.
    """
    anteriores = origens_gravadas(destino)
    if anteriores == origens:
        return IGUAL
    tabela = montar()
    if anteriores is not None:
        if _hash_gravado(destino) == hash_da_tabela(tabela, ordem):
            return IGUAL
        guardar_versao_anterior(destino)
    gravar_tabela(tabela, destino, origens, ordem)
    return GRAVADO
