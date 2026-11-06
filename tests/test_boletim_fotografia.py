"""Fotografia da base para o boletim diário (`base/boletim/fotografia.py`): o retrato dos manifestos
de cada dia e a comparação com o retrato anterior."""

import json
from datetime import date

import pandas as pd
import pytest

from base.boletim import fotografia as fo
from base.parquet import gravar_tabela
from src import versao_do_codigo as vc


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv(vc.VARIAVEL, "587cb6c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7")
    raiz = tmp_path / "base"
    gravar_tabela(
        pd.DataFrame({"cnpj": ["1", "2"]}), raiz / "fca" / "emissores", [], ["cnpj"]
    )
    gravar_tabela(pd.DataFrame({"cnpj": ["3"]}), raiz / "cda" / "2026", [], ["cnpj"])
    return raiz


def test_fotografa_cada_tabela_com_linhas_hash_e_versoes(base):
    # uma versão guardada da tabela de antes (`base/parquet.py`) conta, mas não vira tabela
    (base / "cda" / "2026.v1.parquet").write_bytes(b"x")
    (base / "cda" / "2026.v1.json").write_text("{}", encoding="utf-8")
    foto = fo.fotografar(base)
    assert set(foto["tabelas"]) == {"fca/emissores", "cda/2026"}
    emissores = foto["tabelas"]["fca/emissores"]
    assert emissores["linhas"] == 2
    assert len(emissores["sha256"]) == 64
    assert emissores["bytes"] > 0
    assert emissores["versoes_guardadas"] == 0
    assert foto["tabelas"]["cda/2026"]["versoes_guardadas"] == 1
    assert foto["formato"] == fo.FORMATO


def test_tabela_sem_manifesto_aparece_sem_linhas(base):
    (base / "solta").mkdir()
    pd.DataFrame({"a": [1]}).to_parquet(base / "solta" / "t.parquet")
    foto = fo.fotografar(base)
    assert foto["tabelas"]["solta/t"]["linhas"] is None
    assert foto["tabelas"]["solta/t"]["sha256"] is None


def test_licenca_e_aviso_do_contrato_vem_do_manifesto(base):
    manifesto = base / "fca" / "emissores.json"
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    dados["licenca"] = {"marca": "vendavel"}
    dados["conferencia_do_contrato"] = {"aprovada": False, "problemas": ["a", "b"]}
    manifesto.write_text(json.dumps(dados), encoding="utf-8")
    t = fo.fotografar(base)["tabelas"]["fca/emissores"]
    assert t["licenca"] == "vendavel"
    assert t["contrato"] == "com_problemas"
    assert t["problemas_do_contrato"] == 2


def test_comparar_sem_anterior_e_so_o_retrato(base):
    d = fo.comparar(None, fo.fotografar(base))
    assert d.primeira is True
    assert d.novas == [] and d.sumidas == [] and d.mudaram == []


def test_comparar_acha_novas_sumidas_linhas_e_conteudo(base):
    antes = fo.fotografar(base)
    gravar_tabela(
        pd.DataFrame({"cnpj": ["1", "2", "9"]}),
        base / "fca" / "emissores",
        [],
        ["cnpj"],
    )
    (base / "cda" / "2026.parquet").unlink()
    (base / "cda" / "2026.json").unlink()
    gravar_tabela(
        pd.DataFrame({"cnpj": ["5"]}), base / "ratings" / "ratings", [], ["cnpj"]
    )
    d = fo.comparar(antes, fo.fotografar(base))
    assert d.primeira is False
    assert d.novas == ["ratings/ratings"]
    assert d.sumidas == ["cda/2026"]
    assert [(m.tabela, m.linhas_antes, m.linhas_agora) for m in d.mudaram] == [
        ("fca/emissores", 2, 3)
    ]
    assert d.linhas_antes == 3 and d.linhas_agora == 4


def test_mesma_tabela_regravada_igual_nao_muda(base):
    antes = fo.fotografar(base)
    gravar_tabela(
        pd.DataFrame({"cnpj": ["1", "2"]}), base / "fca" / "emissores", [], ["cnpj"]
    )
    assert fo.comparar(antes, fo.fotografar(base)).mudaram == []


def test_agrupa_por_pasta_de_cima(base):
    gravar_tabela(pd.DataFrame({"cnpj": ["7"]}), base / "cda" / "2025", [], ["cnpj"])
    grupos = fo.por_grupo(fo.fotografar(base))
    assert grupos["cda"]["tabelas"] == 2 and grupos["cda"]["linhas"] == 2
    assert grupos["fca"]["linhas"] == 2


def test_guarda_e_acha_a_ultima_fotografia_antes_do_dia(base, tmp_path):
    pasta = tmp_path / "fotos"
    foto = fo.fotografar(base)
    fo.guardar(foto, pasta, date(2026, 10, 14))
    fo.guardar(foto, pasta, date(2026, 10, 15))
    fo.guardar(foto, pasta, date(2026, 10, 17))
    dia, achada = fo.ultima_antes(pasta, date(2026, 10, 17))
    assert dia == date(2026, 10, 15)
    assert achada["tabelas"].keys() == foto["tabelas"].keys()
    assert fo.ultima_antes(pasta, date(2026, 10, 14)) is None
    assert fo.ultima_antes(tmp_path / "nao-existe", date(2026, 10, 14)) is None
