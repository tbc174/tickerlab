"""Mudanças mensais do CNPJ (ADR 0106, PR 5): diff, reconstrução e o QSA com `id_pessoa`."""

from datetime import date

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import receita_diff as rd
from base.receita_retrato import ParteDoQsa

CHAVE = ["cnpj"]


def _retrato(*linhas: tuple) -> pd.DataFrame:
    return pd.DataFrame(list(linhas), columns=["cnpj", "situacao", "cnae"])


def _igual(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    ordem = list(a.columns)
    a = a.sort_values(ordem).reset_index(drop=True)
    b = b[ordem].sort_values(ordem).reset_index(drop=True)
    return a.equals(b)


def test_diff_do_retrato():
    antes = _retrato(
        ("A", "ativa", "111"), ("B", "ativa", "222"), ("C", "ativa", "333")
    )
    depois = _retrato(
        ("A", "baixada", "111"), ("B", "ativa", "999"), ("D", "ativa", "444")
    )
    m = rd.diff(antes, depois, CHAVE, "2026-10").set_index("cnpj")
    assert m.loc["A", "tipo"] == rd.MUDOU
    assert (m.loc["A", "situacao_antes"], m.loc["A", "situacao_depois"]) == (
        "ativa",
        "baixada",
    )
    assert (m.loc["B", "cnae_antes"], m.loc["B", "cnae_depois"]) == ("222", "999")
    assert m.loc["C", "tipo"] == rd.SAIU and m.loc["C", "situacao_antes"] == "ativa"
    assert m.loc["D", "tipo"] == rd.ENTROU and m.loc["D", "cnae_depois"] == "444"
    assert set(m["mes"]) == {"2026-10"}


def test_sem_mudanca_nao_gera_linha():
    r = _retrato(("A", "ativa", "111"))
    assert rd.diff(r, r.copy(), CHAVE, "2026-10").empty


def test_vazio_igual_a_vazio_nao_e_mudanca():
    r = _retrato(("A", None, "111"))
    assert rd.diff(r, r.copy(), CHAVE, "2026-10").empty


def test_data_vazia_nao_e_mudanca():
    antes = pd.DataFrame({"cnpj": ["A"], "quando": [pd.NaT]})
    assert rd.diff(antes, antes.copy(), CHAVE, "2026-10").empty


def test_diff_mais_retrato_reconstroi_a_ancora():
    m0 = _retrato(("A", "ativa", "1"), ("B", "ativa", "2"), ("C", "ativa", "3"))
    m1 = _retrato(("A", "baixada", "1"), ("B", "ativa", "2"), ("D", "ativa", "4"))
    m2 = _retrato(("A", "baixada", "9"), ("D", "ativa", "4"), ("E", "ativa", "5"))
    mudancas = pd.concat(
        [rd.diff(m0, m1, CHAVE, "2026-02"), rd.diff(m1, m2, CHAVE, "2026-03")]
    )
    assert _igual(rd.reconstruir(m0, mudancas, CHAVE, "2026-03"), m2)
    assert _igual(rd.reconstruir(m0, mudancas, CHAVE, "2026-02"), m1)
    assert _igual(rd.reconstruir(m0, mudancas, CHAVE, "2026-01"), m0)


def test_chave_repetida_nao_perde_linha():
    antes = pd.DataFrame({"k": ["A", "A"], "v": ["x", "y"]})
    depois = pd.DataFrame({"k": ["A", "A", "A"], "v": ["x", "y", "z"]})
    mudancas = rd.diff(antes, depois, ["k"], "2026-02")
    assert _igual(rd.reconstruir(antes, mudancas, ["k"], "2026-02"), depois)


def _qsa(socios: list[dict], pessoas: list[dict]) -> ParteDoQsa:
    return ParteDoQsa(pd.DataFrame(socios), pd.DataFrame(pessoas))


def test_diff_do_qsa_com_pessoa():
    chave = b"k" * 32
    pj = {"cnpj_basico": "11111111", "tipo_socio": "1", "raiz_socio_pj": "22222222"}
    pf = {"cnpj_basico": "11111111", "tipo_socio": "2", "raiz_socio_pj": None}

    def parte(qualificacao, nome="MARIA SILVA"):
        socios = [
            {**pj, "qualificacao": "22", "data_entrada": pd.NaT, "pais": ""},
            {**pf, "qualificacao": qualificacao, "data_entrada": pd.NaT, "pais": ""},
        ]
        pessoas = [
            {
                "cnpj_basico": "11111111",
                "tipo_socio": "2",
                "nome_socio": nome,
                "qualificacao": qualificacao,
                "data_entrada": pd.NaT,
                "cpf_mascarado": "***982247**",
            }
        ]
        return rd.qsa_para_diff(_qsa(socios, pessoas), chave)

    antes, depois = parte("49"), parte("22")
    assert "id_pessoa" in antes.columns
    assert not {"nome_socio", "nome", "cpf_mascarado"} & set(antes.columns)
    m = rd.diff(antes, depois, rd.CHAVE_DO_QSA, "2026-10")
    assert len(m) == 1 and m.iloc[0]["tipo"] == rd.MUDOU
    assert (m.iloc[0]["qualificacao_antes"], m.iloc[0]["qualificacao_depois"]) == (
        "49",
        "22",
    )
    # mesma pessoa, outro nome grafado com sufixo: o id é o mesmo
    assert parte("49", "Maria Silva Junior")["id_pessoa"].equals(antes["id_pessoa"])
    # pessoa saiu: a linha do histórico guarda o id, nunca o nome
    saiu = rd.diff(antes, antes.iloc[:1], rd.CHAVE_DO_QSA, "2026-11")
    assert saiu.iloc[0]["tipo"] == rd.SAIU and saiu.iloc[0]["id_pessoa"]
    assert "nome" not in saiu.columns


def test_qsa_desalinhado_recusa():
    socios = [{"cnpj_basico": "1", "tipo_socio": "2", "qualificacao": "49"}]
    with pytest.raises(ValueError, match="alinhad"):
        rd.qsa_para_diff(_qsa(socios, []), b"k" * 32)


def test_socio_pj_normalizado_para_a_raiz():
    """Mês antigo (14 posições) e mês novo (8) do mesmo sócio não geram mudança falsa."""
    import zipfile
    from io import BytesIO

    from base.receita_retrato import ler_qsa

    def zip_com(documento):
        linha = f'"11111111";"1";"EMPRESA SOCIA";"{documento}";"22";"20200101";"";"";"";"0";"0"\n'
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("K.SOCIOCSV", linha.encode("latin-1"))
        buffer.seek(0)
        return buffer

    antigo = next(ler_qsa([zip_com("22222222000191")])).socios
    novo = next(ler_qsa([zip_com("22222222")])).socios
    chave = ["cnpj_basico", "tipo_socio", "raiz_socio_pj", "qualificacao"]
    assert rd.diff(antigo, novo, chave, "2026-08").empty


def test_disponivel_em_respeita_o_prazo_da_fonte():
    assert rd.disponivel_em("2026-10") == date(
        2026, 10, rd.DIA_DA_PUBLICACAO + rd.FOLGA
    )
    assert rd.disponivel_em("2026-12") > date(2026, 12, 1)
    with pytest.raises(ValueError):
        rd.disponivel_em("2026-13")


@settings(max_examples=60, deadline=None)
@given(
    st.dictionaries(
        st.sampled_from(list("abcdefgh")), st.sampled_from(["x", "y", "z"]), max_size=8
    ),
    st.dictionaries(
        st.sampled_from(list("abcdefgh")), st.sampled_from(["x", "y", "z"]), max_size=8
    ),
)
def test_diff_por_particao_igual_ao_diff_inteiro(a, b):
    def quadro(d):
        return pd.DataFrame({"k": list(d), "v": list(d.values())}, dtype=object)

    antes, depois = quadro(a), quadro(b)
    inteiro = rd.diff(antes, depois, ["k"], "m")
    partes = [
        rd.diff(antes[antes["k"] <= "d"], depois[depois["k"] <= "d"], ["k"], "m"),
        rd.diff(antes[antes["k"] > "d"], depois[depois["k"] > "d"], ["k"], "m"),
    ]
    juntas = pd.concat(partes, ignore_index=True)
    assert len(inteiro) == len(juntas)
    colunas = list(inteiro.columns)
    assert (
        _igual(inteiro.fillna(""), juntas[colunas].fillna("")) if len(inteiro) else True
    )
