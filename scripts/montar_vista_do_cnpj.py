"""Monta a vista do CNPJ que vai para o servidor e mede a busca nela. Roda em casa.

    python -m scripts.montar_vista_do_cnpj --base <base do CNPJ> --destino <pasta nova>
    python -m scripts.montar_vista_do_cnpj --destino <vista pronta> --medir 200   (só mede)

PR 6 do plano da base de CNPJ com sócios (20/10/2026). A vista leva da base do CNPJ (`scripts.carga_receita_mes`)
só o que a busca por CNPJ mostra (cadastro até o município, Simples e MEI, quadro de sócios sem o pseudônimo,
o mesmo quadro virado pela raiz do sócio pessoa jurídica, para o grupo econômico, e as
mudanças de 12 meses), com o desenho descrito em `base/porta/vista_do_cnpj.py`, por onde a busca a lê. As
mudanças já vêm sem as linhas em que só mudou o que a vista não leva. `--medir N` lê o cadastro de N empresas
sorteadas, como a busca faz, e escreve o tamanho da vista e o tempo de cada consulta (mediana, p95 e máximo).
Nenhum CNPJ é escrito.

Fica em casa (RIPD e ADR 0106): o endereço abaixo do município (regra 3.4: MEI e empresário individual são
pessoas, e a vista ainda não sabe quem é um e quem é outro), os contatos, o motivo da situação cadastral e a
situação especial (sinal negativo de MEI e EI, regra 3.7), a CNAE secundária e o `id_pessoa` (o pseudônimo
não sai de casa). A coluna `id_pessoa` vai vazia, para `base.pessoas.consulta.socios_da_empresa` ler a vista
como lê a base.
"""

import argparse
import json
import logging
import random
import shutil
import statistics
import sys
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from base import receita_diff
from base.porta.vista_do_cnpj import (
    COLUNAS_DAS_PARTICIPACOES,
    MANIFESTO,
    MESES_DAS_MUDANCAS,
    MUDANCAS,
    PARTICIPACOES,
    PREFIXO,
    TAMANHO_DA_RAIZ,
)
from src.cadastro_da_receita import cadastro_do_cnpj

log = logging.getLogger("tickerlab.montar_vista_do_cnpj")

VIGENTE = {
    "estabelecimentos": (
        "cnpj_basico", "cnpj", "matriz", "situacao_cadastral", "data_situacao_cadastral",
        "data_inicio_atividade", "cnae_principal", "uf", "municipio",
    ),
    "simples": (
        "cnpj_basico", "optante_simples", "data_opcao_simples", "data_exclusao_simples",
        "optante_mei", "data_opcao_mei", "data_exclusao_mei",
    ),
    "qsa": (
        "cnpj_basico", "tipo_socio", "qualificacao", "data_entrada", "pais", "raiz_socio_pj",
    ),
}  # fmt: skip
SOCIO_PESSOA_JURIDICA = "1"  # `tipo_socio` da Receita
VAZIAS = {"qsa": ("id_pessoa",)}  # colunas que a leitura espera e que não saem de casa
LINHAS_POR_GRUPO = 20_000  # um grupo pequeno: a leitura filtrada pela raiz abre pouco
ENTROU, SAIU, MUDOU = "entrou", "saiu", "mudou"
PARTES = ".partes"  # as mudanças de cada mês, por prefixo, antes de juntar os meses
SEMENTE = 20261024  # o mesmo sorteio a cada medição, para comparar uma com a outra
PERCENTIL_ALTO = 0.95
MEGA = 1024 * 1024


def _arquivos(caminho: Path) -> list[Path]:
    """Um mês ou um prefixo pode ser um arquivo só ou uma pasta de partes."""
    if caminho.is_file():
        return [caminho]
    return sorted(caminho.glob("*.parquet")) if caminho.is_dir() else []


def _ler(arquivos: list[Path], colunas: list[str] | None = None) -> pa.Table:
    return pa.concat_tables([pq.read_table(a, columns=colunas) for a in arquivos])


def _gravar(tabela: pa.Table, arquivo: Path) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(tabela, arquivo, row_group_size=LINHAS_POR_GRUPO, compression="zstd")


def _prefixos(pasta: Path) -> list[str]:
    nomes = {p.name.removesuffix(".parquet") for p in pasta.iterdir()}
    return sorted(n for n in nomes if len(n) == PREFIXO)


def montar_vigente(base: Path, destino: Path) -> None:
    """O retrato vigente, só com as colunas da busca, ordenado pela raiz."""
    for tabela, colunas in VIGENTE.items():
        origem = base / "vigente" / tabela
        for prefixo in _prefixos(origem):
            arquivos = _arquivos(origem / f"{prefixo}.parquet") or _arquivos(
                origem / prefixo
            )
            dados = _ler(arquivos, list(colunas))
            for coluna in VAZIAS.get(tabela, ()):
                dados = dados.append_column(coluna, pa.array([""] * len(dados)))
            ordem = [("cnpj_basico", "ascending")]
            if "cnpj" in colunas:
                ordem.append(("cnpj", "ascending"))
            _gravar(
                dados.sort_by(ordem),
                destino / "vigente" / tabela / f"{prefixo}.parquet",
            )


def montar_participacoes(destino: Path) -> None:
    """O QSA vigente da vista virado: uma linha por sócia pessoa jurídica e empresa, pela raiz da sócia.

    Lido da própria vista (já sem o pseudônimo), um prefixo por vez e só as linhas de sócio pessoa jurídica.
    """
    pasta = destino / "vigente" / "qsa"
    filtro = [("tipo_socio", "==", SOCIO_PESSOA_JURIDICA)]
    colunas = list(COLUNAS_DAS_PARTICIPACOES)
    partes = [
        pq.read_table(arquivo, columns=colunas, filters=filtro)
        for arquivo in sorted(pasta.glob("*.parquet"))
    ]
    if not partes:
        return
    socias = pa.concat_tables(partes).to_pandas()
    socias = socias[
        socias["raiz_socio_pj"].fillna("").str.len().eq(TAMANHO_DA_RAIZ)
        & socias["raiz_socio_pj"].ne(socias["cnpj_basico"])
    ]
    for prefixo, parte in socias.groupby(socias["raiz_socio_pj"].str[:PREFIXO]):
        ordenada = parte.sort_values(["raiz_socio_pj", "cnpj_basico"])
        _gravar(
            pa.Table.from_pandas(ordenada, preserve_index=False),
            destino / "vigente" / PARTICIPACOES / f"{prefixo}.parquet",
        )


def meses_da_janela(meses: list[str], quantos: int = MESES_DAS_MUDANCAS) -> list[str]:
    """Os meses publicados nos últimos `quantos` meses até o último (2024-09 e 12 → de 2023-10 em diante)."""
    ultimo = max(meses)
    ano, mes = int(ultimo[:4]), int(ultimo[5:])
    total = ano * 12 + mes - 1 - quantos
    piso = f"{total // 12:04d}-{total % 12 + 1:02d}"
    return sorted(m for m in meses if m > piso)


def _mudou(dados: pd.DataFrame, campos: tuple[str, ...]) -> pd.Series:
    """Linha em que algum campo da busca tem outro valor depois (dois vazios são iguais)."""
    algum = pd.Series(False, index=dados.index)
    for campo in campos:
        antes, depois = dados[f"{campo}_antes"], dados[f"{campo}_depois"]
        algum |= (antes != depois) & ~(antes.isna() & depois.isna())
    return algum


def _sem_trocas(
    dados: pd.DataFrame, chaves: tuple[str, ...], campos: tuple[str, ...]
) -> pd.DataFrame:
    """Tira os pares de "saiu" e "entrou" iguais sem as colunas que ficaram em casa.

    O mesmo sócio com outro pseudônimo, por exemplo: sem o id, nada mudou para quem olha a vista.
    """
    saiu = dados["tipo"] == SAIU
    entrou = dados["tipo"] == ENTROU
    valores = [
        dados[f"{c}_antes"].where(saiu, dados[f"{c}_depois"]).astype(str)
        for c in campos
    ]
    chave = pd.concat([dados[list(chaves)].astype(str), *valores], axis=1).agg(
        "|".join, axis=1
    )
    vez = dados.groupby([chave, dados["tipo"]]).cumcount().astype(str)
    marca = chave + "#" + vez
    trocas = set(marca[saiu]) & set(marca[entrou])
    return dados[~((saiu | entrou) & marca.isin(trocas))]


def _mudancas_do_mes(tabela: str, arquivos: list[Path]) -> pd.DataFrame:
    chaves, campos = MUDANCAS[tabela]
    pares = [f"{c}_{lado}" for c in campos for lado in ("antes", "depois")]
    dados = _ler(arquivos, ["mes", "tipo", *chaves, *pares]).to_pandas()
    if "cnpj_basico" not in dados:
        dados.insert(2, "cnpj_basico", dados["cnpj"].str[:TAMANHO_DA_RAIZ])
    dados = dados[(dados["tipo"] != MUDOU) | _mudou(dados, campos)]
    return _sem_trocas(dados, chaves, campos)


def _partes_por_prefixo(dados: pd.DataFrame) -> Iterator[tuple[str, pd.DataFrame]]:
    yield from dados.groupby(dados["cnpj_basico"].str[:PREFIXO], sort=True)


def montar_mudancas(base: Path, destino: Path, meses: list[str]) -> None:
    """As mudanças dos `meses`, por prefixo da raiz, das mais antigas para as mais novas."""
    for tabela in MUDANCAS:
        origem = base / "mudancas" / tabela
        partes = destino / PARTES / tabela
        for mes in meses:
            arquivos = _arquivos(origem / f"{mes}.parquet") or _arquivos(origem / mes)
            if not arquivos:
                continue
            for prefixo, parte in _partes_por_prefixo(
                _mudancas_do_mes(tabela, arquivos)
            ):
                _gravar(
                    pa.Table.from_pandas(parte, preserve_index=False),
                    partes / prefixo / f"{mes}.parquet",
                )
        for pasta in sorted(partes.iterdir()) if partes.is_dir() else []:
            juntas = _ler(sorted(pasta.glob("*.parquet")))
            ordem = [("cnpj_basico", "ascending"), ("mes", "ascending")]
            _gravar(
                juntas.sort_by(ordem),
                destino / "mudancas" / tabela / f"{pasta.name}.parquet",
            )
    shutil.rmtree(destino / PARTES, ignore_errors=True)


def _contagens(destino: Path) -> dict[str, dict[str, int]]:
    contagens = {}
    for grupo in ("vigente", "mudancas"):
        for pasta in sorted((destino / grupo).glob("*")):
            arquivos = sorted(pasta.glob("*.parquet"))
            contagens[f"{grupo}/{pasta.name}"] = {
                "linhas": sum(pq.ParquetFile(a).metadata.num_rows for a in arquivos),
                "bytes": sum(a.stat().st_size for a in arquivos),
            }
    return contagens


def montar(base: Path, destino: Path, quantos_meses: int = MESES_DAS_MUDANCAS) -> dict:
    """A vista inteira em `destino` (que não pode existir com outra vista dentro); devolve o manifesto."""
    publicados = sorted(
        json.loads((base / "manifesto.json").read_text(encoding="utf-8"))["meses"]
    )
    janela = meses_da_janela(publicados, quantos_meses)
    montar_vigente(base, destino)
    montar_participacoes(destino)
    montar_mudancas(base, destino, janela)
    manifesto = {
        "mes": publicados[-1],
        "disponivel_em": receita_diff.disponivel_em(publicados[-1]).isoformat(),
        "meses_das_mudancas": janela,
        "tabelas": _contagens(destino),
        "montada_em": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    (destino / MANIFESTO).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifesto


def _sortear_cnpjs(vista: Path, quantos: int) -> list[str]:
    """`quantos` CNPJs da vista, de prefixos sorteados (lê só a coluna `cnpj`)."""
    sorteio = random.Random(SEMENTE)
    arquivos = sorted((vista / "vigente" / "estabelecimentos").glob("*.parquet"))
    escolhidos: list[str] = []
    while len(escolhidos) < quantos and arquivos:
        arquivo = sorteio.choice(arquivos)
        coluna = pq.read_table(arquivo, columns=["cnpj"]).column("cnpj").to_pylist()
        escolhidos.append(sorteio.choice(coluna))
    return escolhidos


def medir(vista: Path, quantos: int) -> dict[str, float]:
    """O tempo, em milissegundos, de `cadastro_do_cnpj` para `quantos` empresas da vista."""
    tempos = []
    for cnpj in _sortear_cnpjs(vista, quantos):
        inicio = time.perf_counter()
        cadastro_do_cnpj(cnpj, vista)
        tempos.append((time.perf_counter() - inicio) * 1000)
    tempos.sort()
    return {
        "consultas": len(tempos),
        "mediana_ms": round(statistics.median(tempos), 1),
        "p95_ms": round(tempos[int(PERCENTIL_ALTO * (len(tempos) - 1))], 1),
        "maximo_ms": round(tempos[-1], 1),
    }


def main(argv: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    analisador.add_argument("--base", type=Path, default=None)
    analisador.add_argument("--destino", type=Path, required=True)
    analisador.add_argument(
        "--medir", type=int, default=0, help="quantas consultas medir"
    )
    opcoes = analisador.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if opcoes.base is not None:
        inicio = time.perf_counter()
        manifesto = montar(opcoes.base, opcoes.destino)
        log.info("vista montada em %.0f s", time.perf_counter() - inicio)
    else:
        manifesto = json.loads((opcoes.destino / MANIFESTO).read_text(encoding="utf-8"))
    for tabela, numeros in manifesto["tabelas"].items():
        log.info(
            "%s: %d linhas, %.1f MB", tabela, numeros["linhas"], numeros["bytes"] / MEGA
        )
    if opcoes.medir:
        log.info("consulta: %s", medir(opcoes.destino, opcoes.medir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
