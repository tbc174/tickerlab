"""A lista de raízes de empresa: interseção das duas tabelas sem pessoa, leve e sem as versões antigas."""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from base.raizes_de_empresa import RaizesDeEmpresa, raizes_de_empresa


def _tabela(base: Path, nome: str, arquivos: dict[str, list[str]]) -> None:
    pasta = base / nome
    pasta.mkdir(parents=True)
    for arquivo, raizes in arquivos.items():
        pd.DataFrame({"cnpj_basico": raizes}).to_parquet(pasta / arquivo)


def _como_lista(raizes: RaizesDeEmpresa) -> set[str]:
    return set(raizes.valores.to_pylist())


def test_a_lista_e_a_intersecao_das_duas_tabelas_arquivo_a_arquivo(tmp_path: Path):
    _tabela(
        tmp_path,
        "cnpj_empresas_pj",
        {"11.parquet": ["11000001", "11000002"], "22.parquet": ["22000001"]},
    )
    _tabela(
        tmp_path,
        "cnpj_estabelecimentos_pj",
        {"11.parquet": ["11000002", "11000003"], "22.parquet": ["22000001"]},
    )
    assert _como_lista(raizes_de_empresa(tmp_path)) == {"11000002", "22000001"}


def test_ignora_as_versoes_antigas_e_o_arquivo_sem_par(tmp_path: Path):
    _tabela(
        tmp_path,
        "cnpj_empresas_pj",
        {
            "11.parquet": ["11000001"],
            "11.v1.parquet": ["99999999"],
            "33.parquet": ["33000001"],
        },
    )
    _tabela(
        tmp_path,
        "cnpj_estabelecimentos_pj",
        {"11.parquet": ["11000001"], "11.v1.parquet": ["99999999"]},
    )
    assert _como_lista(raizes_de_empresa(tmp_path)) == {"11000001"}


def test_sem_a_tabela_recusa(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        raizes_de_empresa(tmp_path)


def test_a_impressao_muda_quando_um_arquivo_muda(tmp_path: Path):
    for nome in ("cnpj_empresas_pj", "cnpj_estabelecimentos_pj"):
        _tabela(tmp_path, nome, {"11.parquet": ["11000001"]})
    antes = raizes_de_empresa(tmp_path).impressao
    assert raizes_de_empresa(tmp_path).impressao == antes
    pd.DataFrame({"cnpj_basico": ["11000001", "11000009"]}).to_parquet(
        tmp_path / "cnpj_empresas_pj" / "11.parquet"
    )
    assert raizes_de_empresa(tmp_path).impressao != antes


def test_esta_na_lista_confere_o_vetor():
    raizes = RaizesDeEmpresa.de_lista({"11111111"})
    achado = raizes.esta_na_lista(pa.array(["11111111", "22222222", ""]))
    assert achado.to_pylist() == [True, False, False]
