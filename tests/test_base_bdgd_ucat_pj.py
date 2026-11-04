"""BDGD `UCAT_PJ` agregado por município e CNAE (base/bdgd_ucat_pj.py). Nada vai à internet: o CSV é
fabricado com o layout de 101 colunas conferido em 04/11/2026."""

from datetime import date

import pandas as pd
import pytest

from base import bdgd_ucat_pj as ucat

COLETA = date(2026, 11, 4)
CABECALHO = (
    ["COD_ID_ENCR", "PN_CON", "DIST", "PAC", "CTAT", "SUB", "CONJ", "MUN", "CEG_GD", "LGRD", "BRR", "CEP"]
    + ["CLAS_SUB", "CNAE", "TIP_CC", "FAS_CON", "GRU_TEN", "TEN_FORN", "GRU_TAR", "SIT_ATIV", "DAT_CON"]
    + ["CAR_INST", "LIV", "ARE_LOC", "TIP_SIST", "DEM_CONT"]
    + [f"DEM_{f}_{m}" for f in "PF" for m in ucat.MESES]
    + ucat.COLUNAS_DE_ENERGIA
    + [f"DIC_{m}" for m in ucat.MESES]
    + [f"FIC_{m}" for m in ucat.MESES]
    + ["DESCR", "POINT_X", "POINT_Y"]
)  # fmt: skip


def _unidade(
    mun: str, cnae: str, ponta: float = 100.0, fora: float = 900.0, **campos: str
) -> dict[str, str]:
    linha = dict.fromkeys(CABECALHO, "")
    linha |= {
        "COD_ID_ENCR": "SEGREDO-HEX-DA-UNIDADE",
        "LGRD": "RUA DO SIGILO 10",
        "BRR": "BAIRRO DO SIGILO",
        "CEP": "20000000",
        "DESCR": "DESCRICAO-DO-SIGILO",
        "POINT_X": "-43.2",
        "POINT_Y": "-22.9",
        "MUN": mun,
        "CNAE": cnae,
        "CAR_INST": "50.5",
        "DEM_CONT": "40",
    }
    linha |= {f"ENE_P_{m}": str(ponta) for m in ucat.MESES}
    linha |= {f"ENE_F_{m}": str(fora) for m in ucat.MESES}
    linha |= campos
    return linha


def _csv(tmp_path, unidades: list[dict[str, str]], codificacao: str = "utf-8"):
    caminho = tmp_path / "ucat_pj.csv"
    linhas = [";".join(CABECALHO)] + [
        ";".join(u[c] for c in CABECALHO) for u in unidades
    ]
    caminho.write_bytes("\n".join(linhas).encode(codificacao))
    return caminho


def _tres(mun: str = "3557105", cnae: str = "0151-2/01") -> list[dict[str, str]]:
    return [_unidade(mun, cnae) for _ in range(3)]


def test_soma_por_municipio_e_cnae(tmp_path):
    tabela, resumo = ucat.agregar_arquivo(_csv(tmp_path, _tres()), COLETA)
    (linha,) = tabela.to_dict("records")
    assert linha["codigo_ibge_municipio"] == "3557105"
    assert linha["cnae"] == "0151201"
    assert linha["unidades"] == 3
    assert linha["carga_instalada_kw"] == pytest.approx(151.5)
    assert linha["demanda_contratada_kw"] == pytest.approx(120)
    assert linha["energia_ponta_kwh_ano"] == pytest.approx(3 * 12 * 100)
    assert linha["energia_fora_ponta_kwh_ano"] == pytest.approx(3 * 12 * 900)
    assert linha["disponivel_em"] == pd.Timestamp(COLETA)
    assert resumo["celulas"] == 1


def test_nenhuma_linha_individual_sai_da_agregacao(tmp_path):
    caminho = _csv(tmp_path, _tres())
    tabela, _ = ucat.agregar_arquivo(caminho, COLETA)
    assert tuple(tabela.columns) == ucat.COLUNAS
    texto = tabela.to_csv()
    for sigilo in ("SEGREDO", "SIGILO", "20000000", "-43.2"):
        assert sigilo not in texto
    assert set(ucat.ler(caminho).columns) == set(ucat.COLUNAS_LIDAS)


def test_celula_com_menos_de_tres_unidades_fica_retida(tmp_path):
    unidades = _tres() + [
        _unidade("3530805", "2451-2/00"),
        _unidade("3530805", "2451-2/00"),
    ]
    tabela, resumo = ucat.agregar_arquivo(_csv(tmp_path, unidades), COLETA)
    assert list(tabela["codigo_ibge_municipio"]) == ["3557105"]
    assert resumo["celulas_retidas"] == 1
    assert resumo["unidades_retidas"] == 2
    assert resumo["unidades_lidas"] == 5


def test_unidade_sem_municipio_ou_cnae_valido_nao_entra(tmp_path):
    unidades = _tres() + [
        _unidade("", "0151-2/01"),
        _unidade("3557105", "x"),
        _unidade("3557105", ""),
    ]
    tabela, resumo = ucat.agregar_arquivo(_csv(tmp_path, unidades), COLETA)
    assert tabela["unidades"].tolist() == [3]
    assert resumo["unidades_sem_chave"] == 3


def test_mes_em_branco_conta_zero_e_decimal_com_virgula(tmp_path):
    unidades = [
        _unidade("3557105", "0151-2/01", ENE_P_01="", ENE_F_01="1000,5"),
        *_tres()[:2],
    ]
    tabela, _ = ucat.agregar_arquivo(_csv(tmp_path, unidades), COLETA)
    assert tabela.loc[0, "energia_ponta_kwh_ano"] == pytest.approx(
        11 * 100 + 2 * 12 * 100
    )
    assert tabela.loc[0, "energia_fora_ponta_kwh_ano"] == pytest.approx(
        1000.5 + 11 * 900 + 2 * 12 * 900
    )


def test_codigos_nao_perdem_o_zero_a_esquerda(tmp_path):
    tabela, _ = ucat.agregar_arquivo(
        _csv(tmp_path, _tres("1100015", "0111-3/01")), COLETA
    )
    assert tabela.loc[0, "cnae"] == "0111301"
    assert tabela.loc[0, "codigo_ibge_municipio"] == "1100015"


def test_aceita_latin1_quando_o_arquivo_nao_e_utf8(tmp_path):
    unidades = [
        _unidade("3557105", "0151-2/01", DESCR="PRAÇA DO SIGILO") for _ in range(3)
    ]
    tabela, _ = ucat.agregar_arquivo(_csv(tmp_path, unidades, "latin-1"), COLETA)
    assert tabela["unidades"].tolist() == [3]


def test_coluna_que_falta_e_erro_nao_palpite(tmp_path):
    caminho = tmp_path / "ucat_pj.csv"
    caminho.write_text("MUN;CNAE\n3557105;0151-2/01\n", encoding="utf-8")
    with pytest.raises(ValueError, match="faltam as colunas"):
        ucat.agregar_arquivo(caminho, COLETA)


def test_ordem_das_linhas_do_arquivo_nao_muda_o_resultado(tmp_path):
    unidades = _tres("3557105", "0151-2/01") + _tres("3530805", "2451-2/00")
    a, _ = ucat.agregar_arquivo(_csv(tmp_path, unidades), COLETA)
    b, _ = ucat.agregar_arquivo(_csv(tmp_path, unidades[::-1]), COLETA)
    pd.testing.assert_frame_equal(a, b)


def test_atribuicao_cita_a_aneel_e_a_licenca():
    assert "ANEEL" in ucat.ATRIBUICAO and "ODbL" in ucat.ATRIBUICAO
    assert ucat.LICENCA == "ODbL"
