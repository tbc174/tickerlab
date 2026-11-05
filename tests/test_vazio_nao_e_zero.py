"""Ausência nunca vira zero (linha 171 da fila): o que a CVM deixa em branco ou que não foi
identificado não pode aparecer como R$ 0 nem como 0,0% (achado pelo lado a lado do setor elétrico)."""

from datetime import date

import pandas as pd

from src import demonstracoes as dm
from src import fundamentos as fu

REFERENCIA = date(2025, 12, 31)


def _contas(**valores: float) -> pd.DataFrame:
    """Uma empresa, um exercício da DFP, no formato que sai da leitura da CVM."""
    return pd.DataFrame(
        [
            {
                "cnpj": "03.378.521/0001-75",
                "documento": "DFP",
                "referencia": REFERENCIA,
                "versao": 1,
                "periodo": dm.EXERCICIO,
                "conta": conta,
                "valor": valor,
            }
            for conta, valor in valores.items()
        ]
    )


def _contas_que_ficam(contas: pd.DataFrame) -> set[str]:
    return set(dm.tirar_zeros_de_ausencia(contas)["conta"])


def test_lucro_dos_controladores_zerado_com_lucro_consolidado_e_ausencia():
    """Light, Renova e CEEE-G: a CVM traz o consolidado (213 mi) e "atribuído aos controladores" 0
    (campo não preenchido). O 0 não é lucro do acionista: sai, e o lucro volta a ser o consolidado."""
    contas = _contas(lucro_liquido=213e6, lucro_controladores=0.0, receita=15e9)
    assert _contas_que_ficam(contas) == {"lucro_liquido", "receita"}


def test_lucro_dos_controladores_zero_com_consolidado_zero_continua_zero():
    contas = _contas(lucro_liquido=0.0, lucro_controladores=0.0)
    assert "lucro_controladores" in _contas_que_ficam(contas)


def test_lucro_dos_controladores_negativo_ou_positivo_nao_e_tocado():
    contas = _contas(lucro_liquido=-5.0, lucro_controladores=-4.0)
    assert _contas_que_ficam(contas) == {"lucro_liquido", "lucro_controladores"}


def test_capex_zero_com_investimento_nao_identificado_e_ausencia():
    """COELBA: "Aquisição de Imobilizado" 0, mas o caixa de investimento é −3 bi (a obra está em
    "Concessão Serviço Público (Ativo Contratual)", que não é reconhecida como capex)."""
    contas = _contas(capex=0.0, investimento_total=-3e9, fco=1.7e9)
    assert _contas_que_ficam(contas) == {"fco"}


def test_capex_zero_com_investimento_zero_continua_zero():
    contas = _contas(capex=0.0, investimento_total=0.0)
    assert _contas_que_ficam(contas) == {"capex"}


def test_capex_sem_a_linha_do_total_nao_e_tocado():
    contas = _contas(capex=0.0)
    assert _contas_que_ficam(contas) == {"capex"}


def test_o_zero_de_uma_empresa_nao_apaga_o_de_outra():
    a = _contas(lucro_liquido=10.0, lucro_controladores=0.0)
    b = _contas(lucro_liquido=0.0, lucro_controladores=0.0).assign(cnpj="outra")
    feito = dm.tirar_zeros_de_ausencia(pd.concat([a, b], ignore_index=True))
    assert set(feito.loc[feito["cnpj"] == "outra", "conta"]) == {
        "lucro_liquido",
        "lucro_controladores",
    }
    assert set(feito.loc[feito["cnpj"] != "outra", "conta"]) == {"lucro_liquido"}


def test_receita_negativa_nos_12_meses_nao_e_mostrada():
    """CELGPAR: DFP 2025 com receita 0 e ITR com receita maior no ano anterior: a conta dos 12 meses
    dá −9,6 mi. Receita negativa vem de períodos não comparáveis, não de venda: fica sem valor."""
    lista = fu._Lista()
    fu._resultado(
        lista, {"receita": -9.6e6, "lucro_liquido": -20.9e6}, "12 meses", False
    )
    receita = lista.itens["receita"]
    assert receita.valor is None
    assert "negativa" in receita.motivo.lower()
