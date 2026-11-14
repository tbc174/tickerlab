"""Histórico datado do CNPJ (`base/cnpj_historico.py`, linha 686): versões com desde quando eram públicas."""

import io
import zipfile
from datetime import date

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import cnpj_historico as historico
from base.receita_diff import diff, disponivel_em
from base.receita_retrato import ErroDeLayout
from tests.ajudantes_de_cpf import CPF_DE_TESTE, OUTRO_CPF_DE_TESTE

CHAVE = ["cnpj_basico"]
CAMPOS = ["natureza_juridica", "optante"]
MESES = ("2023-05", "2023-06", "2023-07", "2023-08", "2023-09")


def _retrato(linhas: dict[str, tuple[str, bool]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"cnpj_basico": raiz, "natureza_juridica": natureza, "optante": optante}
            for raiz, (natureza, optante) in sorted(linhas.items())
        ],
        columns=[*CHAVE, *CAMPOS],
    )


def _pelas_mudancas(retratos: list[pd.DataFrame], meses=MESES) -> pd.DataFrame:
    """Como a base guarda: o vigente (último retrato) e as mudanças de cada mês sobre o anterior."""
    mudancas = [
        diff(antes, depois, CHAVE, mes)
        for antes, depois, mes in zip(retratos, retratos[1:], meses[1:], strict=False)
    ]
    juntas = pd.concat(mudancas, ignore_index=True) if mudancas else pd.DataFrame()
    return historico.versoes_das_mudancas(retratos[-1], juntas, CHAVE, CAMPOS, meses[0])


def _mes_a_mes(retratos: list[pd.DataFrame], meses=MESES) -> pd.DataFrame:
    versoes = None
    for retrato, mes in zip(retratos, meses, strict=False):
        novas = historico.acrescentar_retrato(versoes, retrato, CHAVE, CAMPOS, mes)
        versoes = novas if versoes is None else pd.concat([versoes, novas])
    assert versoes is not None
    return historico._ordenar(versoes, CHAVE)


def _comparavel(versoes: pd.DataFrame) -> list[tuple]:
    colunas = [
        *CHAVE,
        historico.MES,
        historico.DISPONIVEL_EM,
        historico.CONSTA,
        *CAMPOS,
    ]
    tabela = versoes[colunas].astype(object).where(versoes[colunas].notna(), None)
    return sorted(tuple(linha) for linha in tabela.itertuples(index=False))


EXEMPLO = [
    _retrato({"11111111": ("2062", True), "22222222": ("2135", True)}),
    _retrato({"11111111": ("2062", False), "22222222": ("2135", True)}),
    _retrato({"11111111": ("2062", False), "33333333": ("2240", False)}),
]


def test_cada_mudanca_vira_uma_versao_com_a_data_em_que_ficou_publica():
    versoes = _pelas_mudancas(EXEMPLO)
    da_11 = versoes[versoes["cnpj_basico"] == "11111111"]
    assert list(da_11[historico.MES]) == ["2023-05", "2023-06"]
    assert list(da_11["optante"]) == [True, False]
    assert list(da_11[historico.DISPONIVEL_EM]) == [
        disponivel_em("2023-05"),
        disponivel_em("2023-06"),
    ]
    da_22 = versoes[versoes["cnpj_basico"] == "22222222"]
    assert list(da_22[historico.CONSTA]) == [True, False]  # saiu em 2023-07
    assert da_22[CAMPOS].iloc[-1].isna().all()
    da_33 = versoes[versoes["cnpj_basico"] == "33333333"]
    assert list(da_33[historico.MES]) == ["2023-07"]  # entrou: não existia antes


def test_chave_que_nunca_mudou_vale_desde_o_primeiro_mes():
    retratos = [_retrato({"44444444": ("2062", True)})] * 3
    versoes = _pelas_mudancas(retratos)
    assert len(versoes) == 1
    assert versoes[historico.MES].iloc[0] == "2023-05"


def test_as_duas_montagens_dao_o_mesmo_historico():
    assert _comparavel(_pelas_mudancas(EXEMPLO)) == _comparavel(_mes_a_mes(EXEMPLO))


def test_repetir_um_mes_nao_acrescenta_nada_e_voltar_no_tempo_e_erro():
    versoes = _mes_a_mes(EXEMPLO)
    repetido = historico.acrescentar_retrato(
        versoes, EXEMPLO[-1], CHAVE, CAMPOS, MESES[2]
    )
    assert repetido.empty
    with pytest.raises(ValueError, match="já vai até"):
        historico.acrescentar_retrato(versoes, EXEMPLO[0], CHAVE, CAMPOS, MESES[0])


def test_mudanca_no_mes_do_retrato_inicial_e_erro():
    mudancas = diff(EXEMPLO[0], EXEMPLO[1], CHAVE, MESES[0])
    with pytest.raises(ValueError, match="retrato inicial"):
        historico.versoes_das_mudancas(EXEMPLO[1], mudancas, CHAVE, CAMPOS, MESES[0])


def test_a_ultima_versao_confere_com_o_vigente():
    versoes = _pelas_mudancas(EXEMPLO)
    historico.conferir_com_o_vigente(versoes, EXEMPLO[-1], CHAVE, CAMPOS)
    outro = EXEMPLO[-1].assign(optante=True)
    with pytest.raises(historico.HistoricoNaoConfere):
        historico.conferir_com_o_vigente(versoes, outro, CHAVE, CAMPOS)
    with pytest.raises(historico.HistoricoNaoConfere):
        historico.conferir_com_o_vigente(versoes, EXEMPLO[-1].iloc[:1], CHAVE, CAMPOS)


def test_como_era_em_nao_ve_o_mes_antes_de_ele_ser_publico():
    versoes = _pelas_mudancas(EXEMPLO)
    vespera = date(2023, 6, 20)  # o retrato de 2023-06 só vale a partir do dia 21
    antes = historico.como_era_em(versoes, CHAVE, vespera)
    assert bool(antes.set_index("cnpj_basico").loc["11111111", "optante"]) is True
    depois = historico.como_era_em(versoes, CHAVE, disponivel_em("2023-06"))
    assert bool(depois.set_index("cnpj_basico").loc["11111111", "optante"]) is False
    assert historico.como_era_em(versoes, CHAVE, date(2023, 5, 1)).empty


# --- propriedade: sem olhar o futuro ---------------------------------------------------------------
_RAIZES = st.sampled_from(["10000000", "20000000", "30000000", "40000000"])
_VALOR = st.tuples(st.sampled_from(["2062", "2135", "2240"]), st.booleans())
_RETRATO = st.dictionaries(_RAIZES, _VALOR, max_size=4).map(_retrato)


@settings(max_examples=25, deadline=None)  # cada exemplo monta até 5 históricos
@given(st.lists(_RETRATO, min_size=1, max_size=len(MESES)))
def test_sem_olhar_o_futuro(retratos):
    """Cortar os meses futuros não muda nenhuma versão passada, e em cada data vale o retrato publicado."""
    meses = MESES[: len(retratos)]
    completo = _pelas_mudancas(retratos, meses)
    assert _comparavel(completo) == _comparavel(_mes_a_mes(retratos, meses))
    historico.conferir_com_o_vigente(completo, retratos[-1], CHAVE, CAMPOS)
    for corte in range(1, len(retratos) + 1):
        cortado = _pelas_mudancas(retratos[:corte], meses[:corte])
        ate_o_corte = completo[completo[historico.MES] <= meses[corte - 1]]
        assert _comparavel(cortado) == _comparavel(ate_o_corte)
        valendo = historico.como_era_em(
            completo, CHAVE, disponivel_em(meses[corte - 1])
        )
        esperado = retratos[corte - 1].sort_values(CHAVE).reset_index(drop=True)
        assert historico._iguais(valendo[[*CHAVE, *CAMPOS]], esperado)


# --- leitor dos Empresas*.zip ----------------------------------------------------------------------
def _zip_de_empresas(linhas: list[str]) -> io.BytesIO:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as zipado:
        zipado.writestr(
            "K3241.K03200Y0.D41011.EMPRECSV", "\n".join(linhas).encode("latin-1")
        )
    memoria.seek(0)
    return memoria


def _linha(raiz: str, razao: str, natureza: str) -> str:
    return f'"{raiz}";"{razao}";"{natureza}";"49";"1000,00";"01";""'


def test_leitor_guarda_a_razao_social_so_de_quem_nao_e_pessoa():
    arquivo = _zip_de_empresas(
        [
            _linha("11111111", "INDUSTRIA EXEMPLO S.A.", "2054"),
            _linha(
                "22222222", f"FULANO DE TAL {CPF_DE_TESTE}", "2135"
            ),  # MEI / empresário individual
            _linha(
                "33333333", "CONTRIBUINTE INDIVIDUAL", "4014"
            ),  # grupo 4: pessoa física
            _linha("44444444", f"BELTRANO {OUTRO_CPF_DE_TESTE} LTDA", "2062"),
        ]
    )
    (tabela,) = list(historico.ler_empresas(arquivo))
    por_raiz = tabela.set_index("cnpj_basico")
    assert list(tabela.columns) == ["cnpj_basico", "natureza_juridica", "razao_social"]
    assert por_raiz.loc["11111111", "razao_social"] == "INDUSTRIA EXEMPLO S.A."
    assert pd.isna(por_raiz.loc["22222222", "razao_social"])
    assert pd.isna(por_raiz.loc["33333333", "razao_social"])
    assert OUTRO_CPF_DE_TESTE not in por_raiz.loc["44444444", "razao_social"]
    assert por_raiz.loc["22222222", "natureza_juridica"] == "2135"
    assert "1000,00" not in tabela.to_string()  # capital e porte nem são lidos


def test_leitor_quebra_se_a_receita_mudar_o_layout():
    arquivo = _zip_de_empresas([_linha("11111111", "X S.A.", "2054") + ';"a mais"'])
    with pytest.raises(ErroDeLayout):
        list(historico.ler_empresas(arquivo))


def test_data_vazia_no_vigente_confere_consigo_mesma():
    """Regressão (linha 841): no pandas 3 a data vazia virava `nan` no texto e `nan != nan`."""
    campos = ["data"]
    vigente = pd.DataFrame(
        {
            "cnpj_basico": ["11111111", "22222222"],
            "data": pd.to_datetime(["2020-01-02", None]),
        }
    )
    versoes = historico.versoes_das_mudancas(
        vigente, pd.DataFrame(), CHAVE, campos, MESES[-1]
    )
    historico.conferir_com_o_vigente(versoes, vigente, CHAVE, campos)
    preenchida = vigente.assign(data=pd.to_datetime(["2020-01-02", "2021-03-04"]))
    with pytest.raises(historico.HistoricoNaoConfere):
        historico.conferir_com_o_vigente(versoes, preenchida, CHAVE, campos)
    with pytest.raises(historico.HistoricoNaoConfere):
        historico.conferir_com_o_vigente(
            historico.versoes_das_mudancas(
                preenchida, pd.DataFrame(), CHAVE, campos, MESES[-1]
            ),
            vigente,
            CHAVE,
            campos,
        )
