"""Base de demonstrações "como era na data" (série 1 da base de ML, PR 6; ADR 0027, exigência 3):
cada número vale a partir do dia em que ficou público e até ser trocado; olhar uma data nunca mostra
o que foi divulgado depois."""

import pandas as pd
import pytest

from base.contas_cvm import COLUNAS
from base.ponto_no_tempo import (
    COLUNAS_DA_BASE,
    com_divulgacao,
    como_era_em,
    gravar_parquet,
    ler_parquet,
    montar_base,
)

A = "11.111.111/0001-11"
DFP_2022 = pd.Timestamp("2022-12-31")
DFP_2023 = pd.Timestamp("2023-12-31")


def _conta(
    valor,
    divulgado_em,
    referencia=DFP_2022,
    versao=1,
    ordem="ultimo",
    conta="3.11",
    origem="dados_abertos",
    cnpj=A,
):
    """Uma linha de conta publicada (formato de `base/contas_cvm.py`) com a data de divulgação."""
    fim = referencia if ordem == "ultimo" else referencia - pd.DateOffset(years=1)
    demonstracao = "BPA" if conta.startswith("1") else "DRE"
    return {
        "cnpj": cnpj,
        "empresa": "EMPRESA A",
        "documento": "DFP",
        "referencia": referencia,
        "versao": versao,
        "demonstracao": demonstracao,
        "grupo": "con",
        "ordem": ordem,
        "inicio": pd.NaT
        if demonstracao == "BPA"
        else fim - pd.DateOffset(years=1) + pd.Timedelta(days=1),
        "fim": fim,
        "conta": conta,
        "descricao": "Lucro/Prejuízo Consolidado do Período",
        "conta_fixa": True,
        "valor": valor,
        "divulgado_em": pd.Timestamp(divulgado_em),
        "origem": origem,
    }


def _publicadas(*linhas):
    return pd.DataFrame(list(linhas))


def _lucro_de_2022(base_ou_foto):
    linhas = base_ou_foto[
        (base_ou_foto["conta"] == "3.11") & (base_ou_foto["fim"] == DFP_2022)
    ]
    return linhas


def test_versao_1_vale_ate_a_divulgacao_da_2():
    base = montar_base(
        _publicadas(
            _conta(512.0, "2023-03-17", versao=1, origem="enet"),
            _conta(12.0, "2023-05-02", versao=2),
        )
    )
    lucro = _lucro_de_2022(base).sort_values("divulgado_em")
    assert lucro["valor"].tolist() == [512.0, 12.0]
    assert lucro["ate"].tolist()[0] == pd.Timestamp("2023-05-02")
    assert pd.isna(lucro["ate"].tolist()[1])
    assert _lucro_de_2022(como_era_em(base, "2023-04-01"))["valor"].tolist() == [512.0]
    assert _lucro_de_2022(como_era_em(base, "2023-05-02"))["valor"].tolist() == [12.0]


def test_como_era_em_31_12_2020_nao_tem_nada_divulgado_depois():
    base = montar_base(
        _publicadas(
            _conta(100.0, "2021-03-20", referencia=pd.Timestamp("2020-12-31")),
            _conta(512.0, "2023-03-17"),
            _conta(90.0, "2024-03-25", referencia=DFP_2023, ordem="penultimo"),
        )
    )
    assert como_era_em(
        base, "2020-12-31"
    ).empty  # a DFP de 2020 só saiu em março de 2021
    for data in ("2021-03-20", "2022-06-30", "2023-12-31", "2024-12-31"):
        foto = como_era_em(base, data)
        assert (foto["divulgado_em"] <= pd.Timestamp(data)).all()
        assert (
            foto.groupby(
                ["cnpj", "grupo", "demonstracao", "conta", "inicio", "fim"],
                dropna=False,
            )
            .size()
            .max()
            == 1
        )


def test_refeito_no_seguinte_entra_como_versao_nova_da_conta():
    base = montar_base(
        _publicadas(
            _conta(512.0, "2023-03-17"),
            _conta(80.0, "2024-03-25", referencia=DFP_2023, ordem="penultimo"),
        )
    )
    lucro = _lucro_de_2022(base).sort_values("divulgado_em")
    assert lucro["valor"].tolist() == [512.0, 80.0]
    refeito = lucro.iloc[1]
    assert (refeito["referencia"], refeito["ordem"]) == (DFP_2023, "penultimo")
    assert refeito["divulgado_em"] == pd.Timestamp(
        "2024-03-25"
    )  # o "2022" da DFP 2023 vale daí
    assert _lucro_de_2022(como_era_em(base, "2024-01-01"))["valor"].tolist() == [512.0]


def test_numero_repetido_nao_vira_versao_nova():
    base = montar_base(
        _publicadas(
            _conta(512.0, "2023-03-17"),
            _conta(512.0, "2023-05-02", versao=2),  # reapresentou sem mudar este número
            _conta(512.0, "2024-03-25", referencia=DFP_2023, ordem="penultimo"),
        )
    )
    lucro = _lucro_de_2022(base)
    assert len(lucro) == 1
    assert lucro["divulgado_em"].tolist() == [
        pd.Timestamp("2023-03-17")
    ]  # vale desde a 1ª vez
    assert pd.isna(lucro["ate"].iloc[0])


def test_valor_que_some_vira_versao_em_branco():
    base = montar_base(
        _publicadas(
            _conta(512.0, "2023-03-17"), _conta(float("nan"), "2023-05-02", versao=2)
        )
    )
    assert pd.isna(_lucro_de_2022(como_era_em(base, "2023-06-01"))["valor"].iloc[0])


def test_no_mesmo_dia_vale_a_versao_mais_nova():
    base = montar_base(
        _publicadas(
            _conta(10.0, "2023-05-02", versao=3), _conta(20.0, "2023-05-02", versao=2)
        )
    )
    assert _lucro_de_2022(como_era_em(base, "2023-05-02"))["valor"].tolist() == [10.0]


def test_sem_data_de_divulgacao_e_recusado():
    linha = _conta(512.0, "2023-03-17") | {"divulgado_em": pd.NaT}
    with pytest.raises(ValueError, match="divulga"):
        montar_base(_publicadas(linha))


def test_colunas_da_base():
    base = montar_base(_publicadas(_conta(512.0, "2023-03-17")))
    assert list(base.columns) == list(COLUNAS_DA_BASE)


def test_com_divulgacao_usa_a_data_de_cada_versao():
    contas = pd.DataFrame(
        [
            {**_conta(512.0, "2000-01-01", versao=1), "divulgado_em": None},
            {**_conta(12.0, "2000-01-01", versao=2), "divulgado_em": None},
        ]
    )[list(COLUNAS)]
    indice = pd.DataFrame(
        {
            "cnpj": [A, A],
            "empresa": ["EMPRESA A"] * 2,
            "documento": ["DFP"] * 2,
            "referencia": [DFP_2022] * 2,
            "versao": pd.array([1, 2], dtype="Int64"),
            "recebido_em": [pd.Timestamp("2023-03-17"), pd.Timestamp("2023-05-02")],
        }
    )
    publicadas = com_divulgacao(contas.astype({"versao": "Int64"}), indice, "enet")
    assert publicadas.sort_values("versao")["divulgado_em"].tolist() == [
        pd.Timestamp("2023-03-17"),
        pd.Timestamp("2023-05-02"),
    ]
    assert set(publicadas["origem"]) == {"enet"}


def test_com_divulgacao_sem_a_versao_no_indice_e_recusado():
    contas = pd.DataFrame([_conta(512.0, "2000-01-01", versao=4)])[
        list(COLUNAS)
    ].astype({"versao": "Int64"})
    indice = pd.DataFrame(columns=["cnpj", "referencia", "versao", "recebido_em"])
    with pytest.raises(ValueError, match="divulga"):
        montar_base(com_divulgacao(contas, indice, "dados_abertos"))


def test_parquet_por_ano_volta_igual(tmp_path):
    base = montar_base(
        _publicadas(
            _conta(100.0, "2022-03-20", referencia=pd.Timestamp("2021-12-31")),
            _conta(512.0, "2023-03-17"),
            _conta(80.0, "2024-03-25", referencia=DFP_2023, ordem="penultimo"),
        )
    )
    arquivos = gravar_parquet(base, tmp_path / "base")
    assert sorted(a.name for a in arquivos) == [
        "2021.parquet",
        "2022.parquet",
    ]  # pelo ano do período
    volta = ler_parquet(tmp_path / "base")
    ordem = ["fim", "divulgado_em"]
    pd.testing.assert_frame_equal(
        volta.sort_values(ordem).reset_index(drop=True),
        base.sort_values(ordem).reset_index(drop=True),
        check_dtype=False,
    )


# --- juntando as fontes ---------------------------------------------------------------------------
BRB = "00.000.208/0001-00"


def _indice_do_brb():
    return pd.DataFrame(
        {
            "cnpj": [BRB] * 3,
            "empresa": ["BRB"] * 3,
            "documento": ["DFP"] * 3,
            "referencia": [DFP_2022] * 3,
            "versao": pd.array([1, 2, 3], dtype="Int64"),
            "recebido_em": pd.to_datetime(["2023-03-10", "2023-04-20", "2023-06-01"]),
            "link": ["http://enet/1", "http://enet/2", "http://enet/3"],
        }
    )


def test_versoes_antigas_sao_as_que_nao_estao_nos_dados_abertos():
    from base.ponto_no_tempo import versoes_antigas

    antigas = versoes_antigas(_indice_do_brb())
    assert antigas["versao"].tolist() == [1, 2]  # a 3 é a dos dados abertos
    assert antigas["link"].tolist() == ["http://enet/1", "http://enet/2"]


def test_publicadas_do_enet_usam_o_recorte_e_a_data_de_cada_versao():
    from base.enet import ler_xml_enet
    from base.ponto_no_tempo import publicadas_do_enet
    from tests.test_base_enet import _dfp

    documentos = [
        ler_xml_enet(_dfp(versao=1)),
        ler_xml_enet(_dfp(versao=2, lucro="12.345")),
    ]
    publicadas = publicadas_do_enet(documentos, _indice_do_brb())
    assert set(publicadas["origem"]) == {"enet"}
    assert "1.01" in set(publicadas["conta"])  # balanço inteiro
    assert set(publicadas.loc[publicadas["demonstracao"] == "DRE", "conta"]) == {
        "3.01",
        "3.11",
    }
    datas = publicadas.groupby("versao")["divulgado_em"].first()
    assert datas.to_dict() == {
        1: pd.Timestamp("2023-03-10"),
        2: pd.Timestamp("2023-04-20"),
    }


def test_montar_ano_fica_so_com_os_fatos_daquele_ano():
    from base.ponto_no_tempo import montar_ano

    publicadas = _publicadas(
        _conta(512.0, "2023-03-17"),
        _conta(80.0, "2024-03-25", referencia=DFP_2023, ordem="penultimo"),
        _conta(700.0, "2024-03-25", referencia=DFP_2023),
    )
    base = montar_ano(publicadas, 2022)
    assert set(base["fim"].dt.year) == {2022}
    assert base["valor"].tolist() == [512.0, 80.0]
