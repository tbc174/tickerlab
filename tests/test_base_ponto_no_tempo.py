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
    divulgacao_publica,
    gravar_parquet,
    ler_parquet,
    montar_base,
)

A = "11.111.111/0001-11"
DFP_2022 = pd.Timestamp("2022-12-31")
DFP_2023 = pd.Timestamp("2023-12-31")
SEM_CADASTRO = pd.DataFrame(columns=["cnpj", "registro", "cancelamento"])


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
    publicadas = com_divulgacao(
        contas.astype({"versao": "Int64"}), indice, "enet", cadastro=SEM_CADASTRO
    )
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
        montar_base(
            com_divulgacao(contas, indice, "dados_abertos", cadastro=SEM_CADASTRO)
        )


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
    publicadas = publicadas_do_enet(documentos, _indice_do_brb(), cadastro=SEM_CADASTRO)
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


# --- reprodutibilidade (ADR 0027, exigência 9) ----------------------------------------------------
def _tres_publicacoes():
    return _publicadas(
        _conta(100.0, "2022-03-20", referencia=pd.Timestamp("2021-12-31")),
        _conta(512.0, "2023-03-17"),
        _conta(80.0, "2024-03-25", referencia=DFP_2023, ordem="penultimo"),
    )


def test_refazer_a_base_dos_originais_da_os_mesmos_hashes(tmp_path):
    from base.ponto_no_tempo import conferir_pasta, hash_da_base

    publicadas = _tres_publicacoes()
    uma = montar_base(publicadas)
    outra = montar_base(
        publicadas.sample(frac=1, random_state=7)
    )  # outra ordem de chegada
    assert hash_da_base(uma) == hash_da_base(outra)
    origens = [{"url": "https://dados.cvm.gov.br/x.zip", "sha256": "ab" * 32}]
    gravar_parquet(uma, tmp_path / "base", origens=origens)
    import json

    manifesto = json.loads(
        (tmp_path / "base" / "2022.json").read_text(encoding="utf-8")
    )
    assert manifesto["linhas"] == 2 and manifesto["origens"] == origens
    assert manifesto["sha256_da_base"] == hash_da_base(uma[uma["fim"].dt.year == 2022])
    assert conferir_pasta(tmp_path / "base") == {"2021": True, "2022": True}
    # a âncora no Bitcoin aceita o manifesto (ADR 0078): tem o hash da tabela inteira
    from base.ancoragem import folhas_da_base, parquets_sem_manifesto
    from base.parquet import conferir_tabela

    assert parquets_sem_manifesto(tmp_path / "base") == []
    assert list(folhas_da_base(tmp_path / "base")) == ["2021", "2022"]
    assert conferir_tabela(tmp_path / "base" / "2022.parquet")


def test_hash_muda_quando_um_numero_muda(tmp_path):
    from base.ponto_no_tempo import conferir_pasta, hash_da_base

    base = montar_base(_tres_publicacoes())
    mexida = base.copy()
    de_2021 = mexida["fim"].dt.year == 2021
    mexida.loc[de_2021, "valor"] = mexida.loc[de_2021, "valor"] + 0.01  # um centavo
    assert hash_da_base(base) != hash_da_base(mexida)
    gravar_parquet(base, tmp_path / "base")
    mexida[mexida["fim"].dt.year == 2021].to_parquet(
        tmp_path / "base" / "2021.parquet", index=False
    )
    assert conferir_pasta(tmp_path / "base")["2021"] is False


# --- entregas do pedido de registro (conferência da data de entrega da CVM, 15/10/2026) ----------
# Com a empresa ainda sem registro, o DT_RECEB é o dia em que o documento chegou à CVM, não o dia em
# que o público o viu (3 semanas a 3 meses depois, perto do registro). A base usa o registro seguinte.
MANAUS = "09.584.854/0001-37"
TURBI = "26.982.634/0001-80"
NATURA_CO = "32.785.497/0001-97"
B = "22.222.222/0001-22"
CADASTRO = pd.DataFrame(
    {
        "cnpj": [MANAUS, TURBI, NATURA_CO, B, B, A],
        "registro": pd.to_datetime(
            [
                "2022-03-29",
                "2023-05-11",
                "2019-09-25",
                "1995-01-01",
                "2021-06-01",
                "2001-01-01",
            ]
        ),
        "cancelamento": pd.to_datetime(
            [None, None, None, "2021-01-10", None, "2020-06-30"]
        ),
    }
)


@pytest.mark.parametrize(
    ("cnpj", "recebido_em", "esperado"),
    [
        (MANAUS, "2021-12-21", "2022-03-29"),  # ITR de 31/03/2021, ID_DOC 110848
        (TURBI, "2023-04-13", "2023-05-11"),  # DFP de 2022, ID_DOC 125242
        (NATURA_CO, "2019-07-26", "2019-09-25"),  # ITR de 31/03/2019
        (TURBI, "2023-05-15", "2023-05-15"),  # já registrada: o DT_RECEB vale
        (MANAUS, "2022-03-29", "2022-03-29"),  # no próprio dia do registro
        (B, "2021-03-01", "2021-06-01"),  # entre dois registros: o seguinte
        (A, "2020-08-10", "2020-08-10"),  # cancelada, sem registro depois: fica
        ("99.999.999/0001-99", "2021-03-01", "2021-03-01"),  # fora do cadastro: fica
    ],
)
def test_entrega_fora_do_registro_vale_a_partir_do_registro_seguinte(
    cnpj, recebido_em, esperado
):
    datas = divulgacao_publica(
        pd.Series([cnpj]), pd.Series([pd.Timestamp(recebido_em)]), CADASTRO
    )
    assert datas.tolist() == [pd.Timestamp(esperado)]


def test_com_divulgacao_usa_o_registro_seguinte_na_entrega_do_pedido_de_registro():
    itr = pd.Timestamp("2021-03-31")
    contas = pd.DataFrame([_conta(7.0, "2000-01-01", referencia=itr, cnpj=MANAUS)])[
        list(COLUNAS)
    ].astype({"versao": "Int64"})
    indice = pd.DataFrame(
        {
            "cnpj": [MANAUS],
            "referencia": [itr],
            "versao": pd.array([1], dtype="Int64"),
            "recebido_em": [pd.Timestamp("2021-12-21")],
        }
    )
    publicadas = com_divulgacao(contas, indice, "dados_abertos", cadastro=CADASTRO)
    assert publicadas["divulgado_em"].tolist() == [pd.Timestamp("2022-03-29")]
