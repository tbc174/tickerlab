"""Notas clássicas do relatório completo de empresa (série 2 da base de ML, PR 3; ADR 0032, item 1):
Piotroski F, Altman Z'' e Beneish M, com as parcelas à vista. Números sintéticos calculados à mão."""

from datetime import date

import pandas as pd
import pytest

from src import demonstracoes as dm
from src import notas_classicas as nc
from src.banco.demonstracoes import DadosDaEmpresa
from src.fundamentos import NAO_SE_APLICA_A_FINANCEIRAS

BASE = {
    # resultado
    "receita": 3650.0,
    "custo": -1825.0,
    "resultado_bruto": 1825.0,
    "ebit": 300.0,
    "lucro_liquido": 300.0,
    "despesas_com_vendas": -365.0,
    "despesas_administrativas": -365.0,
    "fco": 600.0,
    "depreciacao": 100.0,
    # balanço
    "ativo_total": 3000.0,
    "ativo_circulante": 1000.0,
    "passivo_circulante": 600.0,
    "imobilizado": 900.0,
    "contas_a_receber": 300.0,
    "divida_lp": 400.0,
    "patrimonio_liquido": 1500.0,
    "reservas_de_lucro": 600.0,
    "lucros_acumulados": 0.0,
    "acoes_total": 1000.0,
}
SALDOS = {
    "ativo_total", "ativo_circulante", "passivo_circulante", "imobilizado", "contas_a_receber",
    "divida_lp", "patrimonio_liquido", "reservas_de_lucro", "lucros_acumulados", "acoes_total",
}  # fmt: skip


def _ano(ano: int, valores: dict) -> list[dict]:
    referencia = date(ano, 12, 31)
    return [
        {
            "documento": "DFP",
            "referencia": referencia,
            "versao": 1,
            "periodo": dm.POSICAO if conta in SALDOS else dm.EXERCICIO,
            "inicio": None if conta in SALDOS else date(ano, 1, 1),
            "fim": referencia,
            "conta": conta,
            "valor": valor,
        }
        for conta, valor in valores.items()
    ]


def _empresa(
    atual: dict, anterior: dict | None = None, setor: str = "Máquinas"
) -> DadosDaEmpresa:
    linhas = _ano(2025, atual) + (_ano(2024, anterior) if anterior else [])
    return DadosDaEmpresa(
        contas=pd.DataFrame(linhas), documentos=pd.DataFrame(), setor=setor
    )


def test_altman_z_emergentes_com_as_parcelas():
    altman = nc.calcular(_empresa(BASE, BASE))["altman"]
    parcelas = {p.nome: p.valor for p in altman.parcelas}
    assert parcelas["Capital de giro / ativo"] == pytest.approx(400 / 3000)
    assert parcelas["Lucros retidos / ativo"] == pytest.approx(600 / 3000)
    assert parcelas["EBIT / ativo"] == pytest.approx(300 / 3000)
    assert parcelas["Patrimônio / passivo"] == pytest.approx(1500 / 1500)
    esperado = 6.56 * 400 / 3000 + 3.26 * 0.2 + 6.72 * 0.1 + 1.05 * 1.0  # 3,25
    assert altman.valor == pytest.approx(esperado)
    assert altman.faixa == "segura"


def test_beneish_m_com_os_8_indices():
    beneish = nc.calcular(_empresa(BASE, BASE))["beneish"]
    indices = {p.nome: p.valor for p in beneish.parcelas}
    assert len(indices) == 8
    for nome in ("DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "LVGI"):
        assert indices[nome] == pytest.approx(1.0)  # ano igual ao anterior
    assert indices["TATA"] == pytest.approx((300 - 600) / 3000)
    assert beneish.valor == pytest.approx(-2.48 + 4.679 * -0.1)
    assert beneish.faixa == "abaixo do limite do artigo"


def test_piotroski_com_as_9_parcelas():
    anterior = {**BASE, "lucro_liquido": 200.0, "receita": 3000.0, "resultado_bruto": 1350.0,
                "divida_lp": 500.0, "ativo_circulante": 900.0, "acoes_total": 1000.0}  # fmt: skip
    piotroski = nc.calcular(_empresa(BASE, anterior))["piotroski"]
    passou = {p.nome: p.passou for p in piotroski.parcelas}
    assert len(passou) == 9
    assert passou["ROA positivo"] and passou["Caixa operacional positivo"]
    assert passou["ROA subiu"]  # 300/3000 contra 200/3000
    assert passou["Caixa operacional maior que o lucro"]
    assert passou["Alavancagem caiu"]  # dívida de longo prazo / ativo: 400 contra 500
    assert passou["Liquidez corrente subiu"]  # 1000/600 contra 900/600
    assert passou["Não emitiu ações"]
    assert passou["Margem bruta subiu"]  # 50% contra 45%
    assert passou["Giro do ativo subiu"]  # 3650/3000 contra 3000/3000
    assert piotroski.valor == 9


def test_falta_de_conta_vira_parcela_sem_dado_e_nao_zero():
    sem_acoes = {k: v for k, v in BASE.items() if k != "acoes_total"}
    piotroski = nc.calcular(_empresa(sem_acoes, sem_acoes))["piotroski"]
    emissao = next(p for p in piotroski.parcelas if p.nome == "Não emitiu ações")
    assert emissao.passou is None
    assert "8 de 9" in piotroski.base  # avaliou 8 critérios
    sem_reservas = {k: v for k, v in BASE.items() if k != "reservas_de_lucro"}
    altman = nc.calcular(_empresa(sem_reservas, sem_reservas))["altman"]
    assert altman.valor is None and "lucros retidos" in altman.motivo.lower()


def test_sem_o_ano_anterior_piotroski_e_beneish_nao_saem():
    notas = nc.calcular(_empresa(BASE))
    assert notas["piotroski"].valor is None and notas["beneish"].valor is None
    assert notas["altman"].valor is not None  # só precisa do ano atual


def test_banco_nao_tem_notas_classicas():
    notas = nc.calcular(_empresa(BASE, BASE, setor="Bancos"))
    assert all(
        n.valor is None and n.motivo == NAO_SE_APLICA_A_FINANCEIRAS
        for n in notas.values()
    )


def test_toda_nota_traz_a_referencia_do_artigo():
    for nota in nc.calcular(_empresa(BASE, BASE)).values():
        assert nota.referencia and nota.formula
