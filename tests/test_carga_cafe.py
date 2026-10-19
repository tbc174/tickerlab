"""Carga das tabelas do café (`scripts/carga_cafe.py`): lê os originais que o arquivista guardou (aqui,
as amostras pequenas de `tests/arquivos/commodities/` e `dados_de_exemplo/commodities/`) e grava
`<base>/commodities/<tabela>/`. Sem internet."""

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base.commodities import clima_regiao, comex_cafe, conab_cafe, usda_psd
from base.parquet import ler_tabela
from base.porta import Porta
from scripts import carga_cafe
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para
from tests.ajudantes_da_conab import planilha

TESTES = Path(__file__).parent / "arquivos" / "commodities"
EXEMPLOS = Path(__file__).resolve().parent.parent / "dados_de_exemplo" / "commodities"
VERSAO = "4d2b0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
COMEX = "https://balanca.mdic.gov.br/balanca/bd/"
PRIMEIRA = datetime(2026, 1, 20, 12, tzinfo=UTC)
SEGUNDA = datetime(2026, 3, 20, 12, tzinfo=UTC)
CONAB = "https://www.gov.br/conab/x/3o-levantamento-de-cafe-safra-2026/site_previsao-de-safra-cafe-set-2026.xls"
SIDRA = "https://apisidra.ibge.gov.br/values/t/1613/n6/in%20n3%2031/v/216,214/p/2024-2025/c82/31619,31620,2723"
MAPBIOMAS = "https://drive.google.com/uc?id=x&export=download"
INMET = "https://portal.inmet.gov.br/uploads/dadoshistoricos/2024.zip"


def _zip(nome: str, conteudo: bytes) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as pacote:
        pacote.writestr(nome, conteudo)
    return saida.getvalue()


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    return tmp_path / "acervo" / "base", criar_engine(url)


def _guardar(motor, fonte, url, conteudo, quando=PRIMEIRA):
    caminho = acervo.guardar_original(fonte, url, conteudo, quando)
    with motor.begin() as c:
        registrar(
            c, fonte, url, conteudo, "ok", agora=quando, caminho_do_original=caminho
        )


def _guardar_tudo(motor):
    exportacao = (TESTES / "comex_exp_cafe_pequeno.csv").read_bytes()
    _guardar(
        motor, comex_cafe.FONTE, f"{COMEX}comexstat-bd/ncm/EXP_2025.csv", exportacao
    )
    _guardar(
        motor,
        comex_cafe.FONTE,
        f"{COMEX}tabelas/PAIS.csv",
        (TESTES / "comex_pais_pequeno.csv").read_bytes(),
    )
    _guardar(motor, conab_cafe.FONTE, CONAB, planilha(2026))
    psd = _zip("psd_coffee.csv", (EXEMPLOS / "psd_coffee_pequeno.csv").read_bytes())
    _guardar(
        motor,
        usda_psd.FONTE,
        "https://apps.fas.usda.gov/psdonline/downloads/psd_coffee_csv.zip",
        psd,
    )
    _guardar(
        motor,
        carga_cafe.FONTE_DO_INMET,
        INMET,
        (TESTES / "inmet_3_estacoes_2024.zip").read_bytes(),
    )
    _guardar(
        motor,
        carga_cafe.FONTE_DO_SIDRA,
        SIDRA,
        (EXEMPLOS / "pam_cafe_area_e_producao_5_municipios.json").read_bytes(),
    )
    _guardar(
        motor,
        carga_cafe.FONTE_DO_MAPBIOMAS,
        MAPBIOMAS,
        (EXEMPLOS / "mapbiomas_cafe_5_municipios.xlsx").read_bytes(),
    )


def test_grava_as_cinco_tabelas_e_a_porta_le(ambiente):
    base, motor = ambiente
    _guardar_tudo(motor)
    assert carga_cafe.main(["--base", str(base)]) == 0
    with Porta(base) as porta:
        assert len(porta.ler("comex_cafe")) == 18
        assert set(porta.ler("conab_cafe")["divulgado_em"]) == {
            pd.Timestamp("2026-01-20")
        }
        assert len(porta.ler("usda_psd_cafe")) > 0
        assert set(porta.ler("clima_regiao_cafe")["fonte"]) == {"inmet"}
        area = porta.ler("area_cafe_municipio")
        assert (
            area["area_mapbiomas_ha"].notna().any()
            and area["area_arabica_ha"].notna().any()
        )


def test_rodar_de_novo_nao_regrava(ambiente, caplog):
    base, motor = ambiente
    _guardar_tudo(motor)
    carga_cafe.main(["--base", str(base)])
    caplog.clear()
    with caplog.at_level("INFO"):
        assert carga_cafe.main(["--base", str(base)]) == 0
    assert "GRAVADO" not in caplog.text.upper().replace("IGUAL", "")


def test_coleta_repetida_do_comex_nao_gera_linha_nova_e_guarda_a_primeira_data(
    ambiente,
):
    base, motor = ambiente
    exportacao = (TESTES / "comex_exp_cafe_pequeno.csv").read_bytes()
    url = f"{COMEX}comexstat-bd/ncm/EXP_2025.csv"
    _guardar(
        motor,
        comex_cafe.FONTE,
        f"{COMEX}tabelas/PAIS.csv",
        (TESTES / "comex_pais_pequeno.csv").read_bytes(),
    )
    _guardar(motor, comex_cafe.FONTE, url, exportacao)
    repetida = exportacao + b"\n"  # os mesmos números em outra baixada
    _guardar(motor, comex_cafe.FONTE, url, repetida, SEGUNDA)
    assert carga_cafe.main(["comex", "--base", str(base)]) == 0
    tabela = ler_tabela(base / "commodities" / "comex_cafe" / "2025.parquet")
    assert set(tabela["divulgado_em"]) == {pd.Timestamp("2026-01-20")}


def test_conab_usa_a_primeira_coleta_como_data(ambiente):
    base, motor = ambiente
    _guardar(motor, conab_cafe.FONTE, CONAB, planilha(2026))
    _guardar(motor, conab_cafe.FONTE, CONAB, planilha(2026, 1.1), SEGUNDA)
    assert carga_cafe.main(["conab", "--base", str(base)]) == 0
    tabela = ler_tabela(base / "commodities" / "conab_cafe" / "levantamentos.parquet")
    assert set(tabela["divulgado_em"]) == {pd.Timestamp("2026-01-20")}


def test_planilha_antiga_ilegivel_da_conab_e_pulada_e_as_outras_entram(
    ambiente, caplog
):
    base, motor = ambiente
    antiga = CONAB.replace("safra-2026", "safra-2019")
    _guardar(motor, conab_cafe.FONTE, antiga, b"nao e uma planilha")
    _guardar(motor, conab_cafe.FONTE, CONAB, planilha(2026))
    assert carga_cafe.main(["conab", "--base", str(base)]) == 0
    assert "pulada" in caplog.text
    tabela = ler_tabela(base / "commodities" / "conab_cafe" / "levantamentos.parquet")
    assert len(tabela) > 0


def test_fonte_sem_original_avisa_com_falhas_e_as_outras_seguem(ambiente, capsys):
    base, motor = ambiente
    _guardar(motor, conab_cafe.FONTE, CONAB, planilha(2026))
    assert carga_cafe.main(["--base", str(base)]) == 1
    ultima = capsys.readouterr().out.strip().splitlines()[-1]
    assert (
        ultima.startswith("FALHAS: café: ") and "comex" in ultima and "area" in ultima
    )
    assert (base / "commodities" / "conab_cafe" / "levantamentos.parquet").exists()


def test_area_sem_a_pam_nao_grava_so_o_mapbiomas(ambiente, capsys):
    base, motor = ambiente
    _guardar(
        motor,
        carga_cafe.FONTE_DO_MAPBIOMAS,
        MAPBIOMAS,
        (EXEMPLOS / "mapbiomas_cafe_5_municipios.xlsx").read_bytes(),
    )
    assert carga_cafe.main(["area", "--base", str(base)]) == 1
    assert "ibge-sidra" in capsys.readouterr().out
    assert not (base / "commodities" / "area_cafe_municipio").exists()


def test_tirar_repeticoes_do_comex_guarda_a_primeira_vista_de_cada_valor():
    linha = {c: "x" for c in comex_cafe.COLUNAS}
    antes = pd.DataFrame(
        [{**linha, "kg_liquido": 1.0, "divulgado_em": pd.Timestamp("2026-01-20")}]
    )
    igual = antes.assign(divulgado_em=pd.Timestamp("2026-03-20"))
    revisado = antes.assign(kg_liquido=2.0, divulgado_em=pd.Timestamp("2026-03-20"))
    unica = carga_cafe.tirar_repeticoes_do_comex(pd.concat([antes, igual]))
    assert unica["divulgado_em"].tolist() == [pd.Timestamp("2026-01-20")]
    assert (
        len(carga_cafe.tirar_repeticoes_do_comex(pd.concat([antes, igual, revisado])))
        == 2
    )


def test_chirps_do_mes_le_o_mes_do_endereco(monkeypatch):
    monkeypatch.setattr(
        clima_regiao,
        "ler_chirps",
        lambda _conteudo, _mascaras: pd.DataFrame(
            {"codigo": ["3170701"], "chuva_mm": [50.0]}
        ),
    )
    monkeypatch.setattr(carga_cafe, "_conteudo", lambda _linha: b"")

    class Linha:
        url = "https://data.chc.ucsb.edu/x/chirps-v2.0.2026.09.tif.gz"

    mensal = carga_cafe._chirps_do_mes(Linha(), {})
    assert set(mensal["fonte"]) == {"chirps"}
    assert set(pd.to_datetime(mensal["competencia"])) == {pd.Timestamp("2026-09-30")}
    outra = type("L", (), {"url": "https://x/sem-mes.tif"})()
    assert carga_cafe._chirps_do_mes(outra, {}) is None


def test_a_carga_do_clima_junta_o_chirps_recente_e_o_historico_sem_repetir_endereco():
    """O CHIRPS vem de duas fontes do arquivista (`chirps-mensal` e `chirps-historico`)."""
    assert carga_cafe.FONTES_DO_CHIRPS == ("chirps-mensal", "chirps-historico")

    class Linha:
        def __init__(self, url):
            self.url = url

    a, b = Linha("u1"), Linha("u2")
    assert carga_cafe._sem_repetir([a, b, Linha("u1")]) == [a, b]
