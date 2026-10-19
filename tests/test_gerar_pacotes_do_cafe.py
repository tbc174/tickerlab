"""Os pacotes do café gravados a partir de uma mini-base, lidos só pela porta.

A mini-base tem as tabelas do teste do painel (`tests/test_painel_do_cafe.py`) e, para o mapa, os 5
municípios de exemplo (`tests/test_commodities_cafe_pacote_do_mapa.py`), com a malha guardada no
acervo como o arquivista a guarda (o original e a linha do manifesto).
"""

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from scripts import gerar_pacotes_do_cafe as gerar
from src.commodities.cafe import pacote_do_mapa, pacote_do_painel, painel
from tests.test_commodities_cafe_pacote_do_mapa import (
    HOJE,
    PASTA,
    _mensal,
    pacote_de_exemplo,
)
from tests.test_painel_do_cafe import DIA, tabelas_de_exemplo

ARQUIVOS = {
    "cftc": "setoriais/cftc/2026.parquet",
    "comex": "commodities/comex_cafe/2026.parquet",
    "usda": "commodities/usda_psd/2026.parquet",
    "conab": "commodities/conab_cafe/2026.parquet",
    "clima": "commodities/clima_regiao_cafe/2026.parquet",
}
AREA = "commodities/area_cafe_municipio/municipios.parquet"
VERSAO = "abc1234"


def _gravar(base: Path, relativo: str, tabela: pd.DataFrame) -> None:
    destino = base / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(destino)
    destino.with_suffix(".json").write_text(
        json.dumps({"sha256_da_tabela": f"hash-{destino.parent.name}"}),
        encoding="utf-8",
    )


def _base_do_painel(base: Path, sem: tuple[str, ...] = ()) -> None:
    for nome, tabela in tabelas_de_exemplo().tabelas.items():
        if nome not in sem:
            _gravar(base, ARQUIVOS[nome], tabela)


def _area_da_base() -> pd.DataFrame:
    """A PAM e o MapBiomas dos 5 municípios lado a lado, como a tabela `area_cafe_municipio`."""
    from base.commodities.area_municipio import COLUNAS, ler_mapbiomas, ler_pam

    texto = (PASTA / "pam_cafe_area_e_producao_5_municipios.json").read_text(
        encoding="utf-8"
    )
    pam = ler_pam(json.loads(texto))
    mapbiomas = ler_mapbiomas(PASTA / "mapbiomas_cafe_5_municipios.xlsx")
    juntas = pam.merge(mapbiomas, on=["codigo", "ano"], how="outer")
    juntas["referencia"] = pd.to_datetime(juntas["ano"].astype(str) + "-12-31")
    juntas["disponivel_em"] = pd.to_datetime((juntas["ano"] + 1).astype(str) + "-10-31")
    return juntas.reindex(columns=list(COLUNAS))


def _acervo_com_malha(raiz: Path) -> None:
    original = raiz / "bruto" / gerar.FONTE_DA_MALHA / "2026" / "abc.json"
    original.parent.mkdir(parents=True)
    original.write_bytes((PASTA / "malha_pequena.geojson").read_bytes())
    registro = {
        "fonte": gerar.FONTE_DA_MALHA,
        "url": "https://servicodados.ibge.gov.br/api/v3/malhas/estados/31",
        "sha256": "abc",
        "caminho": original.relative_to(raiz).as_posix(),
        "hora": "2026-10-18T04:00:00-03:00",
    }
    (raiz / "manifesto").mkdir()
    (raiz / "manifesto" / "2026-10-18.jsonl").write_text(
        json.dumps(registro) + "\n", encoding="utf-8"
    )


def _montar(raiz: Path, dia: date = DIA) -> gerar.Resumo:
    agora = datetime(dia.year, dia.month, dia.day, 6, 30, tzinfo=gerar.FUSO)
    return gerar.montar(raiz / "base", raiz, raiz / "cafe", agora, VERSAO)


def _manifesto(raiz: Path) -> dict:
    return json.loads(
        (raiz / "cafe" / gerar.ARQUIVO_DO_MANIFESTO).read_text(encoding="utf-8")
    )


def test_o_pacote_do_painel_e_o_das_tabelas_em_d(tmp_path):
    _base_do_painel(tmp_path / "base")
    _montar(tmp_path)
    lido = pacote_do_painel.ler_pacote(tmp_path / "cafe" / gerar.ARQUIVO_DO_PAINEL)
    assert lido is not None and lido.gerado_em == DIA
    esperado = pacote_do_painel.montar_pacote(
        tabelas_de_exemplo().tabelas, {}, DIA, painel.MESES_DAS_EXPORTACOES
    )
    assert set(lido.tabelas) == set(painel.TABELAS_DA_BASE) and not lido.motivos
    for nome, tabela in esperado.tabelas.items():
        assert len(lido.tabelas[nome]) == len(tabela), nome


def test_o_pacote_do_mapa_e_o_mesmo_do_exemplo(tmp_path):
    _gravar(tmp_path / "base", AREA, _area_da_base())
    _gravar(tmp_path / "base", ARQUIVOS["clima"], _mensal())
    _acervo_com_malha(tmp_path)
    _montar(tmp_path, HOJE)
    lido = pacote_do_mapa.ler_pacote(tmp_path / "cafe" / gerar.ARQUIVO_DO_MAPA)
    assert lido is not None
    assert pacote_do_mapa.em_dicionario(lido) == pacote_do_mapa.em_dicionario(
        pacote_de_exemplo()
    )


def test_manifesto_traz_versao_hashes_pacotes_e_o_que_faltou(tmp_path):
    _base_do_painel(tmp_path / "base", sem=("usda",))
    resumo = _montar(tmp_path)
    manifesto = _manifesto(tmp_path)
    assert manifesto["versao_do_codigo"] == VERSAO
    assert manifesto["pacotes"] == [gerar.ARQUIVO_DO_PAINEL]
    assert "usda_psd_cafe" in manifesto["faltando"]
    assert "area_cafe_municipio" in manifesto["faltando"]
    assert any(h.startswith("hash-") for h in manifesto["tabelas"].values())
    assert any("mapa: sem" in f for f in resumo.falhas)
    lido = pacote_do_painel.ler_pacote(tmp_path / "cafe" / gerar.ARQUIVO_DO_PAINEL)
    assert lido is not None and lido.motivos["usda"] == painel.motivo_sem_tabela(
        "usda_psd_cafe"
    )


def test_base_sem_o_cafe_nao_apaga_o_pacote_da_noite_anterior(tmp_path):
    _base_do_painel(tmp_path / "base")
    _montar(tmp_path)
    for relativo in ARQUIVOS.values():
        (tmp_path / "base" / relativo).unlink()
    resumo = _montar(tmp_path)
    assert "painel: nenhuma tabela do café na base" in resumo.falhas
    assert (
        pacote_do_painel.ler_pacote(tmp_path / "cafe" / gerar.ARQUIVO_DO_PAINEL)
        is not None
    )
    assert not list((tmp_path / "cafe").glob(".*.montando"))


def test_main_avisa_as_falhas_na_ultima_linha(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gerar, "exigir_versao_do_codigo", lambda: VERSAO)
    (tmp_path / "base").mkdir()
    saida = gerar.main(
        ["--pasta", str(tmp_path / "base"), "--saida", str(tmp_path / "cafe")]
    )
    assert saida == 1
    ultima = capsys.readouterr().out.strip().splitlines()[-1]
    assert (
        ultima.startswith("FALHAS: café: ")
        and len(ultima) <= gerar.TAMANHO_MAXIMO_DO_RESUMO
    )


@pytest.mark.parametrize("com_chirps", [True, False])
def test_o_mapa_usa_o_chirps_quando_a_base_tem(com_chirps):
    mensal = _mensal()
    if not com_chirps:
        mensal["fonte"] = pacote_do_mapa.FONTE_INMET
    esperado = pacote_do_mapa.FONTE_CHIRPS if com_chirps else pacote_do_mapa.FONTE_INMET
    assert gerar.fonte_do_clima(mensal) == esperado
