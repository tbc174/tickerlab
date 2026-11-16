"""Montagem das tabelas sem pessoa do CNPJ (linha 584): arquivos de mentira, sem internet."""

import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base.receita_retrato import ErroDeLayout
from scripts import montar_empresas_pj as montar

EMPRESAS = (
    '"33000167";"PETROLEO DE MENTIRA S.A.";"2046";"10";"1000,00";"05";""\n'
    '"33111222";"FULANO DE TAL";"2135";"50";"5000,00";"01";""\n'
    '"33333333";"MEI DE LTDA";"2062";"49";"0,00";"01";""\n'
)
AGORA = datetime(2026, 11, 10, tzinfo=UTC)


def _base(tmp_path: Path) -> tuple[Path, Path]:
    cnpj = tmp_path / "cnpj"
    cnpj.mkdir()
    meses = {"meses": {"2026-09": {}, "2026-10": {}}}
    (cnpj / "manifesto.json").write_text(json.dumps(meses))
    estabelecimentos = pd.DataFrame(
        {
            "cnpj": ["33000167000101", "33111222000101", "33333333000101"],
            "cnpj_basico": ["33000167", "33111222", "33333333"],
            "matriz": [True, True, True],
            "situacao_cadastral": ["02"] * 3,
            "data_inicio_atividade": pd.to_datetime(["1953-10-03"] * 3),
            "cnae_principal": ["0600001"] * 3,
            "uf": ["RJ"] * 3,
            "municipio": ["6001"] * 3,
            "logradouro": ["RUA X"] * 3,
        }
    )
    simples = pd.DataFrame({"cnpj_basico": ["33333333"], "optante_mei": [True]})
    for nome, tabela in (("estabelecimentos", estabelecimentos), ("simples", simples)):
        pasta = cnpj / "vigente" / nome
        pasta.mkdir(parents=True)
        tabela.to_parquet(pasta / "33.parquet", index=False)
    arquivo_zip = tmp_path / "Empresas0.zip"
    with zipfile.ZipFile(arquivo_zip, "w") as arquivo:
        arquivo.writestr("K.EMPRECSV", EMPRESAS.encode("latin-1"))
    return cnpj, arquivo_zip


def test_mes_do_vigente_e_o_ultimo_do_manifesto(tmp_path):
    cnpj, _ = _base(tmp_path)
    assert montar.mes_do_vigente(cnpj) == "2026-10"


def test_monta_as_duas_tabelas_sem_pessoa(tmp_path):
    cnpj, arquivo_zip = _base(tmp_path)
    destino = tmp_path / "base"
    contagem = montar.montar(cnpj, destino, "2026-10", [arquivo_zip], AGORA)
    assert contagem == {montar.EMPRESAS: 2, montar.ESTABELECIMENTOS: 1}
    empresas = pd.read_parquet(destino / montar.EMPRESAS / "33.parquet")
    assert set(empresas["cnpj_basico"]) == {"33000167", "33333333"}
    assert set(empresas["mes_do_retrato"]) == {"2026-10"}
    vista = pd.read_parquet(destino / montar.ESTABELECIMENTOS / "33.parquet")
    assert list(vista["cnpj_basico"]) == ["33000167"]
    assert "logradouro" not in vista.columns
    assert "FULANO" not in empresas.to_csv()
    # capital lido do arquivo e estabelecimentos ativos contados na vista (a MEI nem entra nela)
    petroleo = empresas[empresas["cnpj_basico"] == "33000167"].iloc[0]
    assert petroleo["capital_social"] == 1000.0
    assert petroleo["n_estabelecimentos"] == 1


def test_remontar_o_mesmo_mes_nao_regrava(tmp_path):
    cnpj, arquivo_zip = _base(tmp_path)
    destino = tmp_path / "base"
    montar.montar(cnpj, destino, "2026-10", [arquivo_zip], AGORA)
    arquivo = destino / montar.EMPRESAS / "33.parquet"
    antes = arquivo.stat().st_mtime_ns
    depois = datetime(2026, 11, 11, tzinfo=UTC)
    montar.montar(cnpj, destino, "2026-10", [arquivo_zip], depois)
    assert arquivo.stat().st_mtime_ns == antes


def test_carregar_usa_pasta_temporaria_e_so_deixa_as_tabelas_novas(tmp_path):
    cnpj, arquivo_zip = _base(tmp_path)
    destino = tmp_path / "base"
    contagem = montar.carregar(
        cnpj, destino, lambda mes, pasta: [arquivo_zip], lambda: AGORA
    )
    assert contagem[montar.EMPRESAS] == 2
    assert sorted(p.name for p in destino.iterdir()) == [
        montar.EMPRESAS,
        montar.ESTABELECIMENTOS,
    ]


def test_sem_a_tabela_do_simples_inteira_a_montagem_para(tmp_path):
    cnpj, arquivo_zip = _base(tmp_path)
    shutil.rmtree(cnpj / "vigente" / "simples")
    with pytest.raises(ErroDeLayout):
        montar.montar(cnpj, tmp_path / "base", "2026-10", [arquivo_zip], AGORA)
