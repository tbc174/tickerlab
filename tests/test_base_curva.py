"""Curva de juros própria (série B12): leitura do Tesouro Direto, flat-forward e montagem."""

import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from base import curva
from src.banco.coletas import com_registro

AGORA = datetime(2026, 10, 14, 7, tzinfo=UTC)
URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/df56/resource/796d/download/"
    "precotaxatesourodireto.csv"
)
CABECALHO = (
    "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;"
    "PU Compra Manha;PU Venda Manha;PU Base Manha"
)


def _csv(*linhas: tuple[str, str, str, str, str]) -> bytes:
    corpo = [f"{t};{v};{b};{c};{d};0,00;0,00;0,00" for t, v, b, c, d in linhas]
    return "\n".join([CABECALHO, *corpo]).encode("latin-1")


DIA = "13/10/2026"
EXEMPLO = _csv(
    ("Tesouro Prefixado", "01/01/2028", DIA, "12,50", "12,62"),
    ("Tesouro Prefixado", "01/01/2032", DIA, "12,40", "12,52"),
    ("Tesouro IPCA+", "15/05/2029", DIA, "6,70", "6,82"),
    ("Tesouro IPCA+", "15/05/2045", DIA, "6,60", "6,72"),
    ("Tesouro Selic", "01/03/2031", DIA, "0,09", "0,10"),
    # título só à venda para resgate: usa a taxa de venda
    ("Tesouro IPCA+", "15/08/2050", DIA, "0,00", "6,55"),
    # sem taxa nenhuma: fica de fora
    ("Tesouro Prefixado", "01/01/2027", DIA, "0,00", "0,00"),
)


def test_leitura_escolhe_a_taxa_e_conta_dias_uteis_da_liquidacao():
    tabela = curva.ler_tesouro_direto(EXEMPLO)
    assert len(tabela) == 6
    resgate = tabela[tabela["vencimento"] == "2050-08-15"].iloc[0]
    assert (resgate["lado"], resgate["taxa"]) == ("venda", pytest.approx(0.0655))
    ltn = tabela[tabela["vencimento"] == "2028-01-01"].iloc[0]
    # liquidação em 14/10/2026; o prazo em anos é dias úteis / 252
    assert ltn["prazo_anos"] == ltn["dias_uteis"] / 252
    assert 300 < ltn["dias_uteis"] < 310


def test_flat_forward_reproduz_os_titulos_e_nao_extrapola():
    prazos, taxas = np.array([1.0, 2.0]), np.array([0.10, 0.12])
    assert curva.flat_forward(prazos, taxas, 1.0) == pytest.approx(0.10)
    assert curva.flat_forward(prazos, taxas, 2.0) == pytest.approx(0.12)
    # no meio: o logaritmo do fator anda em linha reta
    esperado = math.exp((math.log(1.10) + 2 * math.log(1.12)) / 2 / 1.5) - 1
    assert curva.flat_forward(prazos, taxas, 1.5) == pytest.approx(esperado)
    assert math.isnan(curva.flat_forward(prazos, taxas, 0.5))
    assert math.isnan(curva.flat_forward(prazos, taxas, 3.0))


def test_curvas_nominal_real_e_implicita_sem_extrapolar():
    curvas = curva.montar_curvas(curva.ler_tesouro_direto(EXEMPLO))
    vertices = {
        nome: dict(zip(grupo["prazo_anos"], grupo["taxa"], strict=True))
        for nome, grupo in curvas.groupby("curva")
    }
    assert set(vertices["nominal"]) == {2, 3, 5}  # títulos de ~1,2 a ~5,2 anos
    assert 10 not in vertices["nominal"]  # nada além do título mais longo
    assert set(vertices["real"]) == {3, 5, 10, 20}
    assert set(vertices["implicita"]) == {3, 5}
    implicita = (1 + vertices["nominal"][5]) / (1 + vertices["real"][5]) - 1
    assert vertices["implicita"][5] == pytest.approx(implicita)
    assert (curvas["disponivel_em"] > curvas["data_base"]).all()


def test_curva_de_um_dia_nao_muda_com_os_outros_dias():
    """Sem olhar o futuro: o dia 13 é igual com ou sem as taxas do dia seguinte."""
    amanha = _csv(
        ("Tesouro Prefixado", "01/01/2028", "14/10/2026", "20,00", "20,10"),
        ("Tesouro Prefixado", "01/01/2032", "14/10/2026", "25,00", "25,10"),
    ).split(b"\n", 1)[1]
    sozinho = curva.montar_curvas(curva.ler_tesouro_direto(EXEMPLO))
    com_amanha = curva.montar_curvas(curva.ler_tesouro_direto(EXEMPLO + b"\n" + amanha))
    dia_13 = com_amanha[com_amanha["data_base"] == "2026-10-13"].reset_index(drop=True)
    pd.testing.assert_frame_equal(sozinho, dia_13)


def test_montagem_grava_por_ano_com_a_origem(banco, tmp_path):
    com_registro("tesouro-br-direto", lambda _url: EXEMPLO)(URL)
    with banco.connect() as conexao:
        linhas = curva.montar(conexao, tmp_path / "base", AGORA)
    assert linhas == {2026: 9}
    tabela = pd.read_parquet(tmp_path / "base" / "curva_juros" / "2026.parquet")
    assert len(tabela["origem_sha256"].iloc[0]) == 64
    assert tabela["montado_em"].iloc[0] == AGORA.isoformat()


def test_montagem_ignora_o_pdf_de_metadados(banco, tmp_path):
    com_registro("tesouro-br-direto", lambda _url: b"%PDF-1.5")(
        URL.replace("precotaxatesourodireto.csv", "taxa.pdf")
    )
    with banco.connect() as conexao:
        assert curva.montar(conexao, tmp_path / "base", AGORA) == {}


def test_comando_monta_a_curva(banco, tmp_path):
    from scripts import montar_base_historica

    com_registro("tesouro-br-direto", lambda _url: EXEMPLO)(URL)
    assert (
        montar_base_historica.main(["curva_juros", "--pasta", str(tmp_path / "b")]) == 0
    )
    assert (tmp_path / "b" / "curva_juros" / "2026.parquet").exists()
