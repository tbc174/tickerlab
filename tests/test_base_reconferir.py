"""Refazer a conferência nos manifestos que já estão no disco (`base/reconferir.py`, API A3)."""

import json

import pandas as pd

from base.reconferir import parquets_da_tabela, reconferir_tabela
from tests.test_base_conferencia import _balanco_e_dre


def _gravar(base, nome_do_arquivo, quadro, manifesto):
    pasta = base / "demonstracoes"
    pasta.mkdir(parents=True, exist_ok=True)
    quadro.to_parquet(pasta / f"{nome_do_arquivo}.parquet", index=False)
    if manifesto is not None:
        (pasta / f"{nome_do_arquivo}.json").write_text(
            json.dumps(manifesto), encoding="utf-8"
        )


def test_grava_a_conferencia_sem_mexer_no_resto_do_manifesto(tmp_path):
    _gravar(
        tmp_path, "2024", _balanco_e_dre(), {"linhas": 3, "sha256_da_tabela": "abc"}
    )
    resumo = reconferir_tabela(tmp_path, "demonstracoes_como_era")
    manifesto = json.loads(
        (tmp_path / "demonstracoes" / "2024.json").read_text(encoding="utf-8")
    )
    assert manifesto["linhas"] == 3 and manifesto["sha256_da_tabela"] == "abc"
    assert manifesto["conferencia_do_contrato"]["tabela"] == "demonstracoes_como_era"
    assert resumo.arquivos == 1


def test_so_ver_nao_grava(tmp_path):
    _gravar(tmp_path, "2024", _balanco_e_dre(), {"linhas": 3})
    reconferir_tabela(tmp_path, "demonstracoes_como_era", gravar=False)
    manifesto = json.loads(
        (tmp_path / "demonstracoes" / "2024.json").read_text(encoding="utf-8")
    )
    assert "conferencia_do_contrato" not in manifesto


def test_registra_reprovacao_e_ignora_versoes_antigas_e_sem_manifesto(tmp_path):
    quadro = _balanco_e_dre()
    _gravar(tmp_path, "2024", pd.concat([quadro, quadro.iloc[[1]]]), {"linhas": 4})
    _gravar(tmp_path, "2023", quadro, None)
    _gravar(tmp_path, "2022.v1", quadro, {"linhas": 3})
    nomes = [p.name for p in parquets_da_tabela(tmp_path, "demonstracoes_como_era")]
    assert nomes == ["2023.parquet", "2024.parquet"]
    resumo = reconferir_tabela(tmp_path, "demonstracoes_como_era")
    assert resumo.sem_manifesto == ["demonstracoes/2023.parquet"]
    assert list(resumo.reprovados) == ["demonstracoes/2024.parquet"]
