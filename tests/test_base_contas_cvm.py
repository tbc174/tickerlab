"""Leitura das contas completas dos CSVs originais da CVM (base de ML, série 1, PR 1)."""

import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from base.contas_cvm import ler_contas

CABECALHO_DRE = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;"
    "DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA"
)
CABECALHO_BPA = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;"
    "DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA"
)
ZIP_REAL = (
    Path(__file__).parent
    / "arquivos"
    / "cvm"
    / "fundamentos"
    / "dfp_cia_aberta_2024.zip"
)


def _zip(arquivos: dict[str, list[str]]) -> bytes:
    """Um zip como o da CVM: CSVs com ';' em latin-1."""
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        for nome, linhas in arquivos.items():
            z.writestr(nome, "\n".join(linhas).encode("latin-1"))
    return saida.getvalue()


def _dre(
    escala: str = "MIL", valor: str = "24172.0000000000", ordem: str = "ÚLTIMO"
) -> str:
    return (
        f"43.514.079/0001-81;2022-12-31;1;CLI SUL S.A.;012345;DF Consolidado - Demonstração do "
        f"Resultado;REAL;{escala};{ordem};2022-01-01;2022-12-31;3.11;Lucro/Prejuízo Consolidado "
        f"do Período;{valor};S"
    )


def _bpa() -> str:
    return (
        "43.514.079/0001-81;2022-12-31;1;CLI SUL S.A.;012345;DF Individual - Balanço Patrimonial "
        "Ativo;REAL;UNIDADE;PENÚLTIMO;2021-12-31;1;Ativo Total;1500.5000000000;S"
    )


def test_le_todas_as_contas_com_as_duas_colunas():
    zip_bytes = _zip(
        {
            "dfp_cia_aberta_DRE_con_2022.csv": [
                CABECALHO_DRE,
                _dre(),
                _dre(ordem="PENÚLTIMO", valor="5689.0000000000"),
            ],
            "dfp_cia_aberta_BPA_ind_2022.csv": [CABECALHO_BPA, _bpa()],
        }
    )

    contas = ler_contas(zip_bytes, "DFP").contas

    assert len(contas) == 3
    assert set(contas["demonstracao"]) == {"DRE", "BPA"}
    assert set(contas["grupo"]) == {"con", "ind"}
    assert set(contas["ordem"]) == {"ultimo", "penultimo"}
    lucro = contas[(contas["conta"] == "3.11") & (contas["ordem"] == "ultimo")].iloc[0]
    assert lucro["cnpj"] == "43.514.079/0001-81"
    assert lucro["documento"] == "DFP"
    assert lucro["referencia"] == pd.Timestamp("2022-12-31")
    assert lucro["versao"] == 1
    assert lucro["inicio"] == pd.Timestamp("2022-01-01")
    assert lucro["fim"] == pd.Timestamp("2022-12-31")
    assert lucro["conta_fixa"]
    assert lucro["descricao"] == "Lucro/Prejuízo Consolidado do Período"
    balanco = contas[contas["demonstracao"] == "BPA"].iloc[0]
    assert pd.isna(balanco["inicio"])  # balanço é saldo numa data, sem início


def test_escala_mil_vira_reais():
    zip_bytes = _zip(
        {"dfp_cia_aberta_DRE_con_2022.csv": [CABECALHO_DRE, _dre(escala="MIL")]}
    )

    valor = ler_contas(zip_bytes, "DFP").contas["valor"].iloc[0]

    assert valor == pytest.approx(24_172_000.0)


def test_escala_unidade_fica_igual():
    zip_bytes = _zip({"dfp_cia_aberta_BPA_ind_2022.csv": [CABECALHO_BPA, _bpa()]})

    assert ler_contas(zip_bytes, "DFP").contas["valor"].iloc[0] == pytest.approx(1500.5)


def test_escala_desconhecida_e_recusada():
    zip_bytes = _zip(
        {"dfp_cia_aberta_DRE_con_2022.csv": [CABECALHO_DRE, _dre(escala="BILHAO")]}
    )

    with pytest.raises(ValueError, match="BILHAO"):
        ler_contas(zip_bytes, "DFP")


def test_tira_e_conta_linhas_repetidas():
    zip_bytes = _zip(
        {"dfp_cia_aberta_DRE_con_2022.csv": [CABECALHO_DRE, _dre(), _dre(), _dre()]}
    )

    leitura = ler_contas(zip_bytes, "DFP")

    assert len(leitura.contas) == 1
    assert leitura.repetidas["linhas"].sum() == 2
    linha = leitura.repetidas.iloc[0]
    assert (linha["cnpj"], linha["demonstracao"], linha["grupo"]) == (
        "43.514.079/0001-81",
        "DRE",
        "con",
    )


def test_ignora_arquivos_que_nao_sao_demonstracoes():
    zip_bytes = _zip(
        {
            "dfp_cia_aberta_2022.csv": ["CNPJ_CIA;DT_REFER;VERSAO", "x;2022-12-31;1"],
            "dfp_cia_aberta_composicao_capital_2022.csv": ["CNPJ_CIA", "x"],
            "dfp_cia_aberta_DRE_con_2022.csv": [CABECALHO_DRE, _dre()],
        }
    )

    assert len(ler_contas(zip_bytes, "DFP").contas) == 1


def test_le_o_zip_real_de_teste():
    leitura = ler_contas(ZIP_REAL.read_bytes(), "DFP")

    contas = leitura.contas
    assert contas["cnpj"].nunique() == 4
    assert {"BPA", "BPP", "DRE", "DFC_MI"} <= set(contas["demonstracao"])
    assert contas["valor"].notna().all()
    ativo = contas[(contas["conta"] == "1") & (contas["ordem"] == "ultimo")]
    assert (ativo["valor"] > 1e9).all()  # bancos e grandes empresas, em reais


def _dre_na_conta(conta: str) -> str:
    return _dre().replace(";3.11;", f";{conta};")


def test_so_as_contas_das_regras_deixa_a_dfc_e_o_detalhe_da_dre_de_fora():
    zip_bytes = _zip(
        {
            "dfp_cia_aberta_DRE_con_2022.csv": [
                CABECALHO_DRE,
                _dre_na_conta("3.01"),
                _dre_na_conta("3.04.02"),
                _dre_na_conta("3.11"),
            ],
            "dfp_cia_aberta_BPA_ind_2022.csv": [CABECALHO_BPA, _bpa()],
            "dfp_cia_aberta_DFC_MI_con_2022.csv": [
                CABECALHO_DRE,
                _dre_na_conta("6.01"),
            ],
        }
    )
    completa = ler_contas(zip_bytes, "DFP").contas
    das_regras = ler_contas(zip_bytes, "DFP", so_as_das_regras=True).contas
    assert len(completa) == 5
    assert sorted(das_regras["conta"]) == ["1", "3.01", "3.11"]
    assert list(das_regras.columns) == list(completa.columns)


def test_so_as_contas_das_regras_ainda_conta_as_repetidas():
    linha = _dre_na_conta("3.04.02")
    zip_bytes = _zip({"dfp_cia_aberta_DRE_con_2022.csv": [CABECALHO_DRE, linha, linha]})
    leitura = ler_contas(zip_bytes, "DFP", so_as_das_regras=True)
    assert leitura.contas.empty
    assert leitura.repetidas["linhas"].tolist() == [1]


def test_so_as_contas_das_regras_tambem_filtra_contas_ja_lidas():
    """O ENET traz o plano inteiro: a base usa o mesmo recorte dos dados abertos."""
    from base.contas_cvm import so_as_contas_das_regras

    zip_bytes = _zip(
        {
            "dfp_cia_aberta_DRE_con_2022.csv": [
                CABECALHO_DRE,
                _dre_na_conta("3.01"),
                _dre_na_conta("3.04.02"),
            ],
            "dfp_cia_aberta_BPA_ind_2022.csv": [CABECALHO_BPA, _bpa()],
            "dfp_cia_aberta_DFC_MI_con_2022.csv": [
                CABECALHO_DRE,
                _dre_na_conta("6.01"),
            ],
        }
    )
    completa = ler_contas(zip_bytes, "DFP").contas
    assert sorted(so_as_contas_das_regras(completa)["conta"]) == ["1", "3.01"]
