"""Monta `src/commodities/cafe/municipios.csv`: os municípios de cada região produtora de café.

Lê duas fontes públicas e aplica `DEFINICOES` de `src/commodities/cafe/regioes.py`:

- a lista de municípios do IBGE com meso e microrregião
  (`servicodados.ibge.gov.br/api/v1/localidades/municipios?view=nivelado`);
- a área colhida de café (arábica e conilon) por município no ano mais recente da PAM
  (SIDRA, tabela 1613, variável 216, categorias 31619 e 31620), uma consulta por UF.

Entram os municípios das áreas de cada região com pelo menos `AREA_MINIMA_HA` de café. Rode com
internet (`python -m scripts.regioes_do_cafe`) ou aponte uma pasta de cache (`--pasta <pasta>`;
os JSONs baixados ficam lá e são reaproveitados). Confira o diff do CSV antes do commit: mudar a
lista muda o clima por região e o mapa.
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import requests

from src.commodities.cafe.regioes import (
    AREA_MINIMA_HA,
    ARQUIVO_DOS_MUNICIPIOS,
    CODIGO_DA_UF,
    DEFINICOES,
    DefinicaoDaRegiao,
)
from src.ibge_sidra import (
    PAM_CAFE_ARABICA,
    PAM_CAFE_CANEPHORA,
    SEM_NUMERO,
    ZERO_ABSOLUTO,
    montar_url,
)

URL_DOS_MUNICIPIOS = (
    "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?view=nivelado"
)
TABELA_DA_PAM, AREA_COLHIDA = 1613, 216
TEMPO_LIMITE = 120
UFS_DO_CAFE = {"MG": 31, "ES": 32, "SP": 35, "PR": 41, "BA": 29, "RO": 11}
COLUNAS = (
    "codigo", "nome", "uf", "regiao", "mesorregiao", "microrregiao",
    "area_arabica_ha", "area_conilon_ha", "ano_pam",
)  # fmt: skip


def _baixar_json(url: str, cache: Path | None) -> list[dict]:
    if cache is not None and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    resposta = requests.get(url, timeout=TEMPO_LIMITE)
    resposta.raise_for_status()
    if cache is not None:
        cache.write_text(resposta.text, encoding="utf-8")
    return resposta.json()


def _area(texto: str) -> float:
    texto = texto.strip()
    if texto == ZERO_ABSOLUTO or texto in SEM_NUMERO:
        return 0.0
    return float(texto)


def _areas_da_pam(pasta: Path | None) -> tuple[dict[int, dict[str, float]], str]:
    """Área de arábica e de conilon por código de município, e o ano da PAM."""
    areas: dict[int, dict[str, float]] = defaultdict(
        lambda: {"arabica": 0.0, "conilon": 0.0}
    )
    ano = ""
    for codigo_da_uf in CODIGO_DA_UF.values():
        url = montar_url(
            TABELA_DA_PAM,
            (AREA_COLHIDA,),
            {82: (PAM_CAFE_ARABICA, PAM_CAFE_CANEPHORA)},
            "last",
            f"n6/in n3 {codigo_da_uf}",
        )
        cache = pasta / f"pam_{codigo_da_uf}.json" if pasta else None
        for linha in _baixar_json(url, cache)[1:]:  # a 1ª linha é o cabeçalho
            tipo = "arabica" if linha["D4C"] == str(PAM_CAFE_ARABICA) else "conilon"
            areas[int(linha["D1C"])][tipo] += _area(linha["V"])
            ano = linha["D3C"]
    return areas, ano


def _regiao_de(
    municipio: dict, definicoes: tuple[DefinicaoDaRegiao, ...]
) -> str | None:
    for definicao in definicoes:
        if municipio["UF-sigla"] not in definicao.ufs:
            continue
        if (
            municipio["mesorregiao-id"] in definicao.mesorregioes
            or municipio["microrregiao-id"] in definicao.microrregioes
        ):
            return definicao.id
    return None


def montar(pasta: Path | None) -> list[dict[str, object]]:
    municipios = _baixar_json(
        URL_DOS_MUNICIPIOS, pasta / "municipios.json" if pasta else None
    )
    areas, ano = _areas_da_pam(pasta)
    linhas = []
    for municipio in municipios:
        area = areas.get(municipio["municipio-id"])
        if area is None or area["arabica"] + area["conilon"] < AREA_MINIMA_HA:
            continue
        regiao = _regiao_de(municipio, DEFINICOES)
        if regiao is None:
            continue
        linhas.append(
            {
                "codigo": str(municipio["municipio-id"]),
                "nome": municipio["municipio-nome"],
                "uf": municipio["UF-sigla"],
                "regiao": regiao,
                "mesorregiao": municipio["mesorregiao-id"],
                "microrregiao": municipio["microrregiao-id"],
                "area_arabica_ha": area["arabica"],
                "area_conilon_ha": area["conilon"],
                "ano_pam": ano,
            }
        )
    return sorted(linhas, key=lambda linha: (linha["regiao"], linha["codigo"]))


def gravar(
    linhas: list[dict[str, object]], destino: Path = ARQUIVO_DOS_MUNICIPIOS
) -> None:
    with destino.open("w", encoding="utf-8", newline="\n") as aberto:
        escritor = csv.DictWriter(aberto, fieldnames=COLUNAS, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(linhas)


def main(argumentos: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    analisador.add_argument(
        "--pasta", type=Path, help="pasta de cache dos JSONs baixados"
    )
    opcoes = analisador.parse_args(argumentos)
    linhas = montar(opcoes.pasta)
    gravar(linhas)
    por_regiao: dict[str, int] = defaultdict(int)
    for linha in linhas:
        por_regiao[str(linha["regiao"])] += 1
    for regiao, quantos in sorted(por_regiao.items()):
        print(f"{regiao}: {quantos} municípios")
    print(f"{len(linhas)} municípios gravados em {ARQUIVO_DOS_MUNICIPIOS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
