"""Contagem sem identificação: somente empresas e pessoas inventadas."""

from itertools import pairwise

import pandas as pd
import pytest

from base import receita_diff
from base.dicionario import TABELAS

TABELA = "movimento_de_socios_pf"
EMPRESA, OUTRA, FORA = "11111111", "22222222", "33333333"
MESES = ["2023-05", "2023-06", "2023-07", "2023-08"]
COLUNAS = [*receita_diff.CHAVE_DO_QSA, "qualificacao", "data_entrada"]


def retratos():
    # Máscaras deliberadamente fictícias, usadas só como chave de comparação em memória.
    def socio(raiz, pessoa, tipo="2", qualificacao="49"):
        return (raiz, tipo, "", pessoa, qualificacao, pd.Timestamp("2020-01-01"))

    a = socio(EMPRESA, "***111111**")
    b = socio(EMPRESA, "***222222**")
    c = socio(OUTRA, "***333333**")
    excluidos = [socio(FORA, "***444444**"), socio(EMPRESA, "estrangeiro", "3")]
    return {
        mes: pd.DataFrame(linhas + excluidos, columns=COLUNAS)
        for mes, linhas in zip(
            MESES,
            [[a, a, c], [a, b, c], [socio(EMPRESA, a[3], qualificacao="05")], [a, b]],
            strict=True,
        )
    }


def montar(ate=MESES[-1]):
    from base.socios_pf import contar_movimentos

    quadros = retratos()
    meses = [m for m in MESES if m <= ate]
    vazia = receita_diff.diff(
        quadros[meses[0]], quadros[meses[0]], receita_diff.CHAVE_DO_QSA, meses[0]
    )
    mudancas = pd.concat(
        [vazia]
        + [
            receita_diff.diff(quadros[a], quadros[b], receita_diff.CHAVE_DO_QSA, b)
            for a, b in pairwise(meses)
        ],
        ignore_index=True,
    )
    return contar_movimentos(quadros[ate], mudancas, meses, {EMPRESA, OUTRA})


def test_catalogo_tem_contagem_sem_identificacao():
    assert TABELA in TABELAS
    tabela = TABELAS[TABELA]
    assert not tabela.pessoa
    assert tabela.familia_da_fonte == "rfb-cnpj"


def test_conta_pessoas_distintas_e_nao_linhas_ou_mudancas_de_qualificacao():
    tabela = montar().set_index(["cnpj_basico", "mes_do_retrato"])
    contagens = ["socios_pf_entraram", "socios_pf_sairam", "socios_pf_no_fim"]
    assert tabela.loc[EMPRESA, contagens].values.tolist() == [
        [0, 0, 1],
        [1, 0, 2],
        [0, 1, 1],
        [1, 0, 2],
    ]
    assert tabela.loc[(OUTRA, "2023-07"), contagens].tolist() == [0, 1, 0]
    assert not tabela.loc[(EMPRESA, "2023-05"), "tem_retrato_anterior"]
    assert tabela.loc[(EMPRESA, "2023-06"), "tem_retrato_anterior"]


@pytest.mark.parametrize("corte", MESES)
def test_cortar_futuro_nao_muda_passado(corte):
    tudo = montar()
    pd.testing.assert_frame_equal(
        montar(corte), tudo[tudo.mes_do_retrato <= corte].reset_index(drop=True)
    )


def test_saida_so_tem_contagens_e_empresa_sem_pessoa():
    from base.pessoas.proibidas import procurar
    from base.socios_pf import COLUNAS as saida

    tabela = montar()
    assert list(tabela) == saida
    assert set(tabela.cnpj_basico) == {EMPRESA, OUTRA}
    assert (
        not tabela.astype(str)
        .apply(lambda c: c.str.contains(r"\*|estrangeiro"))
        .any()
        .any()
    )
    assert procurar(tabela, TABELA) == []
    for coluna in ("socios_pf_entraram", "socios_pf_sairam", "socios_pf_no_fim"):
        assert pd.api.types.is_integer_dtype(tabela[coluna])
    assert all(
        tabela.disponivel_em
        == tabela.mes_do_retrato.map(receita_diff.disponivel_em).astype(
            "datetime64[ns]"
        )
    )


def test_lacuna_entre_meses_nao_vira_movimento_mensal():
    from base.socios_pf import contar_movimentos

    with pytest.raises(ValueError, match="consecutivos"):
        contar_movimentos(
            retratos()[MESES[-1]], pd.DataFrame(), ["2023-05", "2023-08"], {EMPRESA}
        )


def test_chave_vazia_omite_so_empresa_e_comparacao_incompletas():
    """O QSA já tem chaves apagadas ou ausentes; não podem parar toda a base nem virar pessoa única."""
    from base.socios_pf import contar_movimentos

    maio = retratos()["2023-05"]
    junho = maio.copy()
    junho.loc[junho.cnpj_basico == EMPRESA, "id_pessoa"] = ""
    mudou = receita_diff.diff(maio, junho, receita_diff.CHAVE_DO_QSA, "2023-06")
    tabela = contar_movimentos(junho, mudou, MESES[:2], {EMPRESA, OUTRA})
    assert list(tabela[tabela.cnpj_basico == EMPRESA].mes_do_retrato) == ["2023-05"]
    assert list(tabela[tabela.cnpj_basico == OUTRA].socios_pf_no_fim) == [1, 1]


def test_tipo_pj_e_estrangeiro_ficam_fora_e_tabela_vazia_tem_esquema():
    from base.socios_pf import COLUNAS as saida
    from base.socios_pf import contar_movimentos

    quadro = retratos()["2023-05"].assign(tipo_socio="1")
    mudancas = receita_diff.diff(quadro, quadro, receita_diff.CHAVE_DO_QSA, MESES[0])
    tabela = contar_movimentos(quadro, mudancas, MESES[:1], {EMPRESA})
    assert tabela.empty and list(tabela) == saida


@pytest.mark.parametrize("problema", ["negativo", "mes", "tipo"])
def test_recusa_mudanca_inconsistente(problema):
    from base.socios_pf import contar_movimentos

    maio, junho = retratos()["2023-05"], retratos()["2023-06"]
    mudou = receita_diff.diff(maio, junho, receita_diff.CHAVE_DO_QSA, "2023-06")
    if problema == "negativo":
        mudou = pd.concat([mudou, mudou[mudou.tipo == "entrou"]], ignore_index=True)
        mensagem = "inconsistentes"
    elif problema == "mes":
        mudou["mes"] = "2024-01"
        mensagem = "fora dos meses"
    else:
        mudou["tipo"] = "desconhecido"
        mensagem = "desconhecido"
    with pytest.raises(ValueError, match=mensagem):
        contar_movimentos(junho, mudou, MESES[:2], {EMPRESA, OUTRA})


def _retrato_defeituoso(ate):
    from base.socios_pf import contar_movimentos

    quadros = retratos()
    meses = [m for m in MESES if m <= ate]
    quadros["2023-07"] = quadros["2023-05"].iloc[0:0]
    mudancas = pd.concat(
        [
            receita_diff.diff(quadros[a], quadros[b], receita_diff.CHAVE_DO_QSA, b)
            for a, b in pairwise(meses)
        ],
        ignore_index=True,
    )
    return contar_movimentos(
        quadros[ate], mudancas, meses, {EMPRESA, OUTRA}, {"2023-07": "2023-08"}
    )


def test_defeito_compara_mes_seguinte_com_anterior_ao_defeito():
    tabela = _retrato_defeituoso("2023-08")
    assert "2023-07" not in set(tabela.mes_do_retrato)
    agosto = tabela[tabela.mes_do_retrato == "2023-08"].set_index("cnpj_basico")
    assert agosto.loc[EMPRESA, ["socios_pf_entraram", "socios_pf_sairam"]].tolist() == [
        0,
        0,
    ]
    assert agosto.loc[OUTRA, ["socios_pf_entraram", "socios_pf_sairam"]].tolist() == [
        0,
        1,
    ]
    assert set(agosto.disponivel_em) == {
        pd.Timestamp(receita_diff.disponivel_em("2023-08"))
    }
    pd.testing.assert_frame_equal(
        _retrato_defeituoso("2023-06"),
        tabela[tabela.mes_do_retrato <= "2023-06"].reset_index(drop=True),
    )


def test_regra_do_retrato_defeituoso_e_herdada_do_molde_pj():
    from base import socios_pf, socios_pj

    assert (
        socios_pf.RETRATOS_COM_DEFEITO
        == socios_pj.RETRATOS_COM_DEFEITO
        == {"2024-09": "2024-10"}
    )
