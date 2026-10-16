"""Bloco "eventos e governança" da amostra integrada (PR 3): documentos e negociações nos 90 dias antes,
insolvência, auditor, conselho, remuneração e ofertas, como se sabia em cada fim de mês; e o corte da
base em cada data (nada público depois entra)."""

import pandas as pd
import pytest

from base.amostra import como_era, eventos

D = pd.Timestamp


def _entradas() -> dict[str, pd.DataFrame]:
    return {
        "eventos": pd.DataFrame(
            {
                "cnpj": ["A", "A", "A", "B"],
                "tema": ["eventos", "resultados", "eventos", "risco"],
                "rotulo": ["Fato relevante", "Resultados", "Assembleia", "Rating"],
                "publicado_em": [
                    D("2020-01-10"),
                    D("2020-02-20"),
                    D("2020-06-05"),
                    D("2020-03-03"),
                ],
            }
        ),
        "insolvencia": pd.DataFrame(
            {
                "cnpj": ["B", "B"],
                "rotulo": ["pedido_de_falencia", "recuperacao_judicial"],
                "conhecido_em": [D("2020-02-14"), D("2020-05-08")],
            }
        ),
        "auditores": pd.DataFrame(
            {
                "cnpj": ["A", "A"],
                "conhecido_em": [D("2019-05-31"), D("2020-05-30")],
                "inicio": [D("2015-01-01"), D("2020-01-01")],
                "auditor_id": ["rede:kpmg", "rede:ey"],
            }
        ),
        "trocas_de_auditor": pd.DataFrame(
            {
                "cnpj": ["A"],
                "conhecido_em": [D("2020-05-30")],
                "efetiva_em": [D("2020-01-01")],
            }
        ),
        "negociacoes": pd.DataFrame(
            {
                "cnpj": ["A", "A", "A"],
                "cargo": ["controlador", "diretoria", "conselho"],
                "operacao": ["venda", "compra", "compra"],
                "data": [D("2020-03-02"), D("2020-03-10"), D("2020-08-20")],
                "entregue_em": [D("2020-04-10"), D("2020-04-10"), D("2020-09-10")],
                "valor": [1000.0, 50.0, 70.0],
            }
        ),
        "fre_conselho": pd.DataFrame(
            {
                "cnpj": ["A"] * 4,
                "id_documento": ["1", "1", "1", "2"],
                "conhecido_em": [D("2020-05-29")] * 3 + [D("2021-05-28")],
                "orgao": [
                    "Pertence apenas ao Conselho de Administração",
                    "Pertence à Diretoria e ao Conselho de Administração",
                    "Conselho Fiscal",
                    "Pertence apenas ao Conselho de Administração",
                ],
                "membros": [6, 1, 3, 9],
                "independentes": [2, 0, 0, 4],
            }
        ),
        "fre_remuneracao": pd.DataFrame(
            {
                "cnpj": ["A", "A", "A"],
                "id_documento": ["1", "1", "1"],
                "conhecido_em": [D("2020-05-29")] * 3,
                "orgao": [
                    "Diretoria Estatutária",
                    "Diretoria Estatutária",
                    "Conselho Fiscal",
                ],
                "fim_do_exercicio": [D("2019-12-31"), D("2020-12-31"), D("2020-12-31")],
                "total_do_orgao": [10.0, 12.0, 1.0],
            }
        ),
        "ofertas": pd.DataFrame(
            {
                "cnpj_emissor": ["A", "A"],
                "anunciada_em": [D("2019-11-05"), D("2020-07-01")],
            }
        ),
    }


def _grade() -> pd.DataFrame:
    meses = como_era.fins_de_mes(D("2019-01-31"), D("2021-12-31"))
    return pd.DataFrame([(c, m) for c in "AB" for m in meses], columns=["cnpj", "data"])


@pytest.fixture(scope="module")
def painel():
    return eventos.montar(_entradas(), _grade())


def _em(painel, cnpj, data):
    return painel[(painel["cnpj"] == cnpj) & (painel["data"] == D(data))].iloc[0]


def test_documentos_dos_90_dias_antes(painel):
    linha = _em(painel, "A", "2020-02-29")
    assert (
        linha["fatos_relevantes_90d"],
        linha["documentos_eventos_90d"],
        linha["documentos_resultados_90d"],
    ) == (1, 1, 1)
    assert (
        _em(painel, "A", "2020-05-31")["fatos_relevantes_90d"] == 0
    )  # 10/01 saiu da janela
    assert _em(painel, "B", "2020-03-31")["documentos_risco_90d"] == 1


def test_insolvencia_so_depois_de_comunicada(painel):
    assert not _em(painel, "B", "2020-01-31")["insolvencia_conhecida"]
    linha = _em(painel, "B", "2020-03-31")
    assert (linha["insolvencia_rotulo"], linha["insolvencia_desde"]) == (
        "pedido_de_falencia",
        D("2020-02-14"),
    )
    assert (
        _em(painel, "B", "2020-06-30")["insolvencia_rotulo"] == "recuperacao_judicial"
    )
    assert _em(painel, "B", "2020-06-30")["insolvencia_desde"] == D("2020-02-14")


def test_auditor_e_troca_pelo_fca_ja_entregue(painel):
    antes = _em(painel, "A", "2020-04-30")
    assert antes["auditor_id"] == "rede:kpmg" and pd.isna(
        antes["meses_desde_a_troca_de_auditor"]
    )
    depois = _em(painel, "A", "2020-06-30")
    assert depois["auditor_id"] == "rede:ey"
    assert depois["meses_desde_a_troca_de_auditor"] == pytest.approx(6.0, abs=0.1)


def test_negociacoes_so_depois_de_entregues(painel):
    assert (
        _em(painel, "A", "2020-03-31")["vendas_controlador_90d"] == 0
    )  # entregue em 10/04
    linha = _em(painel, "A", "2020-04-30")
    assert (linha["vendas_controlador_90d"], linha["compras_administracao_90d"]) == (
        1000.0,
        50.0,
    )
    assert (
        _em(painel, "A", "2020-08-31")["compras_administracao_90d"] == 0
    )  # a de 20/08 só em setembro


def test_conselho_e_remuneracao_do_fre_mais_novo(painel):
    linha = _em(painel, "A", "2020-06-30")
    assert (
        linha["conselho_membros"],
        linha["conselho_independentes"],
        linha["conselho_fiscal_membros"],
    ) == (7, 2, 3)
    assert (linha["remuneracao_diretoria"], linha["remuneracao_exercicio"]) == (
        12.0,
        D("2020-12-31"),
    )
    assert _em(painel, "A", "2021-06-30")["conselho_membros"] == 9


def test_ofertas_dos_12_meses_antes(painel):
    assert _em(painel, "A", "2020-06-30")["ofertas_12m"] == 1
    assert _em(painel, "A", "2020-07-31")["ofertas_12m"] == 2
    assert _em(painel, "A", "2020-11-30")["ofertas_12m"] == 1  # a de 05/11/2019 saiu


@pytest.mark.parametrize(
    "data",
    [
        "2020-01-31",
        "2020-03-31",
        "2020-04-30",
        "2020-05-31",
        "2020-08-31",
        "2021-06-30",
    ],
)
def test_nenhum_bloco_olha_o_futuro(data):
    dia = D(data)
    inteira = eventos.montar(_entradas(), _grade())
    cortada = eventos.montar(
        como_era.cortar(_entradas(), eventos.ENTRADAS, dia), _grade()
    )
    pd.testing.assert_frame_equal(
        inteira[inteira["data"] == dia].reset_index(drop=True),
        cortada[cortada["data"] == dia].reset_index(drop=True),
        check_dtype=False,
    )
