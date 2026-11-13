"""CNPJ de verdade nas tabelas que só trazem o código da fonte (linha 904, lote 4).

Todos os dados são inventados; a ponte é um dublê com as colunas de `ans_operadoras`, `susep_cadastro` e
`ifdata_cadastro`."""

import pandas as pd

from base.cnpj_pela_ponte import com_cnpj_da_ponte

SAIDA = {"cnpj": "cnpj", "cnpj_basico": "cnpj_basico"}


def _ponte(*linhas: tuple) -> pd.DataFrame:
    """(id, cnpj, disponivel_em, consta, trata_como_pessoa)."""
    return pd.DataFrame(
        [
            {
                "id_na_fonte": i,
                "cnpj": c,
                "cnpj_basico": c.replace(".", "")[:8] if c else None,
                "disponivel_em": pd.Timestamp(d),
                "consta": consta,
                "trata_como_pessoa": pessoa,
            }
            for i, c, d, consta, pessoa in linhas
        ]
    )


def _fatos(*pares: tuple[str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cd_operadora": [c for c, _ in pares],
            "disponivel_em": [pd.Timestamp(d) for _, d in pares],
            "beneficiarios": range(len(pares)),
        }
    )


def test_liga_pelo_registro_com_e_sem_zeros_e_guarda_a_ordem():
    ponte = _ponte(("000123", "11.222.333/0001-81", "2020-01-31", True, False))
    fatos = _fatos(("123", "2026-01-31"), ("999", "2026-01-31"), ("0123", "2026-02-28"))
    saida, contagem = com_cnpj_da_ponte(fatos, "cd_operadora", ponte, SAIDA)
    assert list(saida["cnpj"].fillna("-")) == [
        "11.222.333/0001-81",
        "-",
        "11.222.333/0001-81",
    ]
    assert list(saida["cnpj_basico"].fillna("-")) == ["11222333", "-", "11222333"]
    assert list(saida["beneficiarios"]) == [0, 1, 2]
    assert contagem == {"linhas": 3, "ligadas": 2, "ponte_vazia": 0}
    assert "cnpj" not in fatos.columns  # a tabela de entrada não muda


def test_ponte_que_so_existe_depois_nao_liga_o_passado():
    ponte = _ponte(("5", "11.222.333/0001-81", "2026-06-30", True, False))
    saida, _ = com_cnpj_da_ponte(
        _fatos(("5", "2026-01-31"), ("5", "2026-07-31")), "cd_operadora", ponte, SAIDA
    )
    assert list(saida["cnpj"].isna()) == [True, False]


def test_vale_a_linha_da_ponte_que_ja_era_publica_no_dia():
    ponte = _ponte(
        ("5", "11.222.333/0001-81", "2020-01-31", True, False),
        ("5", "33.000.167/0001-01", "2026-06-30", True, False),
    )
    saida, _ = com_cnpj_da_ponte(
        _fatos(("5", "2026-01-31"), ("5", "2026-07-31")), "cd_operadora", ponte, SAIDA
    )
    assert list(saida["cnpj"]) == ["11.222.333/0001-81", "33.000.167/0001-01"]


def test_pessoa_e_registro_que_saiu_da_fonte_ficam_sem_cnpj():
    ponte = _ponte(
        ("1", "11.222.333/0001-81", "2020-01-31", True, True),  # MEI
        ("2", "33.000.167/0001-01", "2020-01-31", True, False),
        ("2", "33.000.167/0001-01", "2026-03-31", False, False),  # saiu da fonte
    )
    saida, contagem = com_cnpj_da_ponte(
        _fatos(("1", "2026-01-31"), ("2", "2026-01-31"), ("2", "2026-04-30")),
        "cd_operadora",
        ponte,
        SAIDA,
    )
    assert list(saida["cnpj"].isna()) == [True, False, True]
    assert contagem["ligadas"] == 1


def test_sem_ponte_as_colunas_saem_vazias_e_a_tabela_segue():
    saida, contagem = com_cnpj_da_ponte(
        _fatos(("1", "2026-01-31")), "cd_operadora", None, SAIDA
    )
    assert saida["cnpj"].isna().all()
    assert list(saida["beneficiarios"]) == [0]
    assert contagem["ponte_vazia"] == 1


def test_fato_sem_data_ou_sem_chave_nao_liga():
    ponte = _ponte(("1", "11.222.333/0001-81", "2020-01-31", True, False))
    fatos = pd.DataFrame(
        {
            "cd_operadora": ["1", None],
            "disponivel_em": [pd.NaT, pd.Timestamp("2026-01-31")],
        }
    )
    saida, contagem = com_cnpj_da_ponte(fatos, "cd_operadora", ponte, SAIDA)
    assert saida["cnpj"].isna().all()
    assert contagem["ligadas"] == 0


def test_ifdata_so_a_raiz_pelo_codigo_da_instituicao():
    cadastro = pd.DataFrame(
        {
            "cod_inst": ["00000001", "C0010001"],
            "cnpj_raiz": ["11222333", "33000167"],
            "disponivel_em": pd.to_datetime(["2026-01-01", "2026-01-01"]),
        }
    )
    valores = pd.DataFrame(
        {
            "cod_inst": ["C0010001", "00000001", "99999999"],
            "disponivel_em": pd.to_datetime(["2026-05-01"] * 3),
        }
    )
    saida, contagem = com_cnpj_da_ponte(
        valores,
        "cod_inst",
        cadastro,
        {"cnpj_basico": "cnpj_raiz"},
        chave_da_ponte="cod_inst",
    )
    assert list(saida["cnpj_basico"].fillna("-")) == ["33000167", "11222333", "-"]
    assert "cnpj" not in saida.columns
    assert contagem["ligadas"] == 2


def test_carga_ve_a_ponte_gravada_e_leva_a_origem_dela(tmp_path):
    from base.setoriais import ans
    from scripts import carga_setoriais as carga

    pasta = tmp_path / "ans_operadoras"
    pasta.mkdir()
    _ponte(("123", "11.222.333/0001-81", "2020-01-31", True, False)).to_parquet(
        pasta / "ativas.parquet"
    )
    montar, origens = carga._com_cnpj_da_ponte(
        lambda: _fatos(("123", "2026-01-31")),
        [{"url": "https://exemplo.invalido/ans.csv", "sha256": "a"}],
        carga.REVISADAS[ans.FONTE],
        tmp_path,
    )
    assert list(montar()["cnpj"]) == ["11.222.333/0001-81"]
    assert [o["url"] for o in origens] == [
        "https://exemplo.invalido/ans.csv",
        "ans_operadoras/ativas.parquet",
    ]


def test_carga_sem_ponte_na_base_deixa_as_colunas_vazias(tmp_path):
    from base.setoriais import ans
    from scripts import carga_setoriais as carga

    montar, origens = carga._com_cnpj_da_ponte(
        lambda: _fatos(("123", "2026-01-31")), [], carga.REVISADAS[ans.FONTE], tmp_path
    )
    assert montar()["cnpj"].isna().all()
    assert origens == []


def test_datas_em_unidades_diferentes_ligam_sem_erro():
    """A ponte gravada com data pura volta como datetime64[s]; os fatos vêm em [us] (revisão cruzada)."""
    ponte = _ponte(("123", "11.222.333/0001-81", "2020-01-31", True, False))
    ponte["disponivel_em"] = ponte["disponivel_em"].astype("datetime64[s]")
    fatos = _fatos(("123", "2026-01-31"))
    fatos["disponivel_em"] = fatos["disponivel_em"].astype("datetime64[us]")
    saida, contagem = com_cnpj_da_ponte(fatos, "cd_operadora", ponte, SAIDA)
    assert list(saida["cnpj"]) == ["11.222.333/0001-81"]
    assert contagem["ligadas"] == 1


def test_ifdata_individual_fica_com_a_propria_raiz_e_nao_a_do_lider(monkeypatch):
    from scripts import carga_bcb_credito as carga

    cadastro = pd.DataFrame(
        {
            "cod_inst": ["60701190", "C0080099"],
            "cnpj_raiz": [
                "60872504",
                "60872504",
            ],  # com líder, o cadastro dá a raiz do líder
            "disponivel_em": pd.to_datetime(["2026-01-01"] * 2),
        }
    )
    valores = pd.DataFrame(
        {
            "cod_inst": ["60701190", "C0080099"],
            "disponivel_em": pd.to_datetime(["2026-05-01"] * 2),
        }
    )
    monkeypatch.setattr(carga, "_valores_do_tipo", lambda _coletas: valores)
    saida = carga._valores_com_raiz({}, cadastro)
    assert list(saida["cnpj_basico"]) == ["60701190", "60872504"]


def test_ano_digitado_errado_na_ponte_nao_derruba_a_carga():
    ponte = _ponte(
        ("123", "11.222.333/0001-81", "2020-01-31", True, False),
        ("456", "33.000.167/0001-01", "2020-01-31", True, False),
    )
    ponte.loc[1, "disponivel_em"] = pd.Timestamp("0201-05-01")
    saida, _ = com_cnpj_da_ponte(
        _fatos(("123", "2026-01-31"), ("456", "2026-01-31")),
        "cd_operadora",
        ponte,
        SAIDA,
    )
    assert saida["cnpj"].notna().tolist() == [True, True]
