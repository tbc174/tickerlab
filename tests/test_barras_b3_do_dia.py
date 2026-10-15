"""Script diário das barras e do selo da B3 (plano dos intradiários grátis, PR 2, tarefa 2.4).

Lê o que o arquivista guardou no acervo (pelo manifesto), processa os pregões que ainda não têm
barras ou cujos arquivos mudaram, e imprime `FALHAS:` quando um pregão sai `incompleto`.
"""

import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts import barras_b3_do_dia as script
from tests.test_base_intradiario_b3 import (
    PETR4_NO_BOLETIM,
    linha,
    registro_do_cotahist,
    xml_do_boletim,
    zip_de_negocios,
    zip_do_boletim,
    zip_do_cotahist,
)

DIA = date(2026, 10, 13)
URL_DOS_NEGOCIOS = "https://arquivos.b3.com.br/rapinegocios/tickercsv/2026-10-13"
URL_DO_PR = "https://www.b3.com.br/pesquisapregao/download?filelist=PR261013.zip"
URL_DO_COTAHIST = (
    "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D13102026.ZIP"
)
# PETR4 com 3 negócios (um no after) e 600 ações, como o PR e o COTAHIST montados abaixo
NEGOCIOS_BONS = [
    linha("PETR4", "30,10", 100, "100000047", 10),
    linha("PETR4", "30,30", 200, "120000000", 20),
    linha("PETR4", "30,30", 300, "182500100", 30, sessao=6),
]


def guardar(acervo: Path, fonte: str, url: str, origem: Path, hora: str) -> None:
    """Põe o arquivo no acervo e a linha no manifesto, como o arquivista faz."""
    relativo = f"bruto/{fonte}/2026/{origem.stem}-{hora[11:13]}.zip"
    (acervo / relativo).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(origem, acervo / relativo)
    manifesto = acervo / "manifesto" / f"{hora[:10]}.jsonl"
    manifesto.parent.mkdir(parents=True, exist_ok=True)
    with manifesto.open("a", encoding="utf-8") as arquivo:
        linha_do_manifesto = {
            "fonte": fonte,
            "url": url,
            "sha256": f"sha-{origem.stem}-{hora}",
            "caminho": relativo,
            "hora": hora,
        }
        arquivo.write(json.dumps(linha_do_manifesto) + "\n")


@pytest.fixture
def acervo(tmp_path, monkeypatch):
    pasta = tmp_path / "acervo"
    monkeypatch.setenv("TICKERLAB_ACERVO", str(pasta))
    originais = tmp_path / "originais"
    originais.mkdir()
    guardar(
        pasta,
        "b3-boletim-pr",
        URL_DO_PR,
        zip_do_boletim(
            originais,
            {
                "A.xml": (
                    pd.Timestamp("2026-10-13 21:00"),
                    xml_do_boletim([PETR4_NO_BOLETIM]),
                )
            },
        ),
        "2026-10-14T05:00:00+00:00",
    )
    guardar(
        pasta,
        "b3-cotahist-dia",
        URL_DO_COTAHIST,
        zip_do_cotahist(originais, [registro_do_cotahist("PETR4", "010")]),
        "2026-10-14T05:00:00+00:00",
    )
    return pasta, originais


def guardar_negocios(acervo, linhas, hora="2026-10-14T01:00:00+00:00"):
    pasta, originais = acervo
    guardar(
        pasta,
        "b3-negocios",
        URL_DOS_NEGOCIOS,
        zip_de_negocios(originais, linhas, f"negocios-{hora[11:13]}.zip"),
        hora,
    )


def resumo(pasta: Path) -> dict:
    return json.loads(
        (pasta / "intradiario/b3/selo/2026-10-13.json").read_text("utf-8")
    )


def test_dia_bom_vira_barras_selo_e_resumo(acervo, capsys):
    guardar_negocios(acervo, NEGOCIOS_BONS)
    assert script.main([]) == 0
    pasta = acervo[0]
    barras = pd.read_parquet(pasta / "intradiario/b3/barras/2026-10-13.parquet")
    assert barras["negocios"].sum() + barras["negocios_after"].sum() == 3
    selo = pd.read_parquet(pasta / "intradiario/b3/selo/2026-10-13.parquet")
    assert selo.set_index("simbolo").loc["PETR4", "selo"] == "completo"
    dados = resumo(pasta)
    assert dados["selo_do_dia"] == "completo"
    assert dados["sha256_do_arquivo"].startswith("sha-negocios")
    assert dados["a_vista"] == {"completo": 1}
    assert "FALHAS" not in capsys.readouterr().out


def test_dia_quebrado_imprime_falhas_e_sai_com_1(acervo, capsys):
    guardar_negocios(acervo, NEGOCIOS_BONS[:1])  # faltam negócios do PETR4
    assert script.main([]) == 1
    saida = capsys.readouterr().out.strip().splitlines()
    assert saida[-1].startswith("FALHAS: b3-barras 2026-10-13 incompleto")
    assert resumo(acervo[0])["selo_do_dia"] == "incompleto"


def test_dia_ja_processado_nao_e_refeito(acervo, capsys):
    guardar_negocios(acervo, NEGOCIOS_BONS[:1])
    script.main([])
    capsys.readouterr()
    assert (
        script.main([]) == 0
    )  # o quebrado já avisou; só avisa de novo se o arquivo mudar
    assert "Nada a processar" in capsys.readouterr().out


def test_versao_nova_do_arquivo_e_processada_de_novo(acervo):
    guardar_negocios(acervo, NEGOCIOS_BONS[:1])
    script.main([])
    guardar_negocios(acervo, NEGOCIOS_BONS, hora="2026-10-15T01:00:00+00:00")
    assert script.main([]) == 0
    assert resumo(acervo[0])["selo_do_dia"] == "completo"


def test_sem_boletim_ainda_nao_e_falha(tmp_path, monkeypatch, capsys):
    pasta = tmp_path / "acervo"
    monkeypatch.setenv("TICKERLAB_ACERVO", str(pasta))
    originais = tmp_path / "originais"
    originais.mkdir()
    guardar_negocios((pasta, originais), NEGOCIOS_BONS)
    assert script.main([]) == 0
    assert resumo(pasta)["selo_do_dia"] == "sem_boletim"
    assert "FALHAS" not in capsys.readouterr().out


def test_usa_a_versao_mais_nova_de_cada_arquivo(acervo):
    guardar_negocios(acervo, NEGOCIOS_BONS, hora="2026-10-14T01:00:00+00:00")
    guardar_negocios(acervo, NEGOCIOS_BONS[:1], hora="2026-10-14T02:00:00+00:00")
    arquivos = script.arquivos_no_acervo(acervo[0])
    assert (
        arquivos["b3-negocios"][DIA].sha256
        == "sha-negocios-02-2026-10-14T02:00:00+00:00"
    )


def test_regra_nova_refaz_os_pregoes(acervo, capsys, monkeypatch):
    guardar_negocios(acervo, NEGOCIOS_BONS)
    script.main([])
    assert resumo(acervo[0])["versao_da_regra"] == script.b3.VERSAO_DA_REGRA
    monkeypatch.setattr(script.b3, "VERSAO_DA_REGRA", script.b3.VERSAO_DA_REGRA + 1)
    capsys.readouterr()
    script.main([])
    assert "2026-10-13: completo" in capsys.readouterr().out
