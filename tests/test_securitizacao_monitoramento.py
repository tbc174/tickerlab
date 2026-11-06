"""Monitoramento mensal de FIDC (src/securitizacao/monitoramento.py, B-15).

O gabarito dos 20 maiores fundos de um mês foi feito à mão (contas nos comentários). Tudo sintético,
menos o teste com a amostra real da CVM (`tests/arquivos/cvm/fidc/`).
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import cnpj as cnpj_base
from base import fidc
from src.securitizacao.monitoramento import (
    REGRAS,
    como_era_em,
    eventos_do_mes,
    leituras_dos_informes,
    maiores_por_pl,
)

MES, ANTES = pd.Timestamp("2026-08-31"), pd.Timestamp("2026-07-31")


def _cnpj(k: int) -> str:
    base12 = f"{k:08d}0001"
    return cnpj_base.formatar(base12 + cnpj_base.digitos_verificadores(base12))


# fundo: (PL sênior, PL subordinado, carteira, inadimplente, maior cedente em %); cotas = 1, valor = PL.
# O PL do quadro IV é 10000 - 100×fundo: os fundos 1 a 20 são os 20 maiores, o 21 e o 22 ficam fora.
FUNDOS = {
    1: (
        900,
        100,
        1000,
        40,
        40,
    ),  # sub 100/1000 = 10% (não é abaixo de 10%); inad 4%; cedente 40%: nada
    2: (960, 40, 1000, 0, 10),  # sub 40/1000 = 4% < 5%: quebra
    3: (
        920,
        80,
        1000,
        51,
        55,
    ),  # sub 8%: atenção; inad 5,1%: atenção; cedente 55%: atenção
    4: (
        800,
        200,
        1000,
        100,
        80,
    ),  # inad 10% (não passa de 10%): atenção; cedente 80%: atenção
    5: (800, 200, 1000, 101, 81),  # inad 10,1%: quebra; cedente 81%: quebra
    7: (800, 200, 1000, 30, 20),  # inad 3% contra 1% em julho: +2 pontos, subiu
    8: (800, 200, 1000, 29, 20),  # inad 2,9% contra 1%: +1,9 ponto, nada
    21: (990, 10, 1000, 0, 10),  # sub 1%: quebra, mas fora dos 20 maiores
    22: (800, 200, 1000, 0, 10),
}
for _k in (6, *range(9, 21)):
    FUNDOS[_k] = (800, 200, 1000, 0, 20)  # saudável


def _tabelas(fundos: dict, mes: pd.Timestamp) -> dict:
    quadro_i, quadro_iv, quadro_x2 = [], [], []
    for k, (sen, sub, carteira, inad, ced) in fundos.items():
        cn = _cnpj(k)
        quadro_i.append(
            {
                "competencia": mes,
                "cnpj_fundo": cn,
                "DENOM_SOCIAL": f"FIDC {k}",
                "TAB_I2_VL_CARTEIRA": str(carteira),
                "TAB_I2A3_VL_CRED_INAD": str(inad),
                "TAB_I2A12_PR_CEDENTE_1": str(ced),
                "TAB_I2A12_PR_CEDENTE_2": "1.5",
            }
        )
        quadro_iv.append(
            {
                "competencia": mes,
                "cnpj_fundo": cn,
                "TAB_IV_A_VL_PL": str(10000 - 100 * k),
            }
        )
        for nome, valor in (
            ("Subclasse Senior Série 1", sen),
            ("Subclasse Subordinada 1", sub),
        ):
            quadro_x2.append(
                {
                    "competencia": mes,
                    "cnpj_fundo": cn,
                    "TAB_X_CLASSE_SERIE": nome,
                    "TAB_X_QT_COTA": "1",
                    "TAB_X_VL_COTA": str(valor),
                }
            )
    return {
        "tab_I": pd.DataFrame(quadro_i),
        "tab_IV": pd.DataFrame(quadro_iv),
        "tab_X_2": pd.DataFrame(quadro_x2),
    }


@pytest.fixture(scope="module")
def leituras() -> pd.DataFrame:
    julho = _tabelas({7: (800, 200, 1000, 10, 20), 8: (800, 200, 1000, 10, 20)}, ANTES)
    agosto = _tabelas(FUNDOS, MES)
    juntas = {q: pd.concat([julho[q], agosto[q]], ignore_index=True) for q in agosto}
    return leituras_dos_informes(juntas)


# (fundo, regra, valor), na ordem do relatório: gravidade, fundo (CNPJ), regra
ESPERADO_DOS_20_MAIORES = [
    (2, "fidc_subordinacao_minima_quebra", 0.04),
    (5, "fidc_concentracao_cedente_quebra", 0.81),
    (5, "fidc_inadimplencia_limite_quebra", 0.101),
    (3, "fidc_concentracao_cedente_atencao", 0.55),
    (3, "fidc_inadimplencia_limite_atencao", 0.051),
    (3, "fidc_subordinacao_minima_atencao", 0.08),
    (4, "fidc_concentracao_cedente_atencao", 0.80),
    (4, "fidc_inadimplencia_limite_atencao", 0.10),
    (7, "fidc_inadimplencia_subindo", 0.03),
]


def _resumo(eventos):
    return [(e.objeto_id, e.regra_id, e.valor) for e in eventos]


def test_os_20_maiores_batem_com_a_conta_a_mao(leituras):
    maiores = maiores_por_pl(leituras, MES, 20)
    assert maiores == [_cnpj(k) for k in range(1, 21)]
    resumo = _resumo(eventos_do_mes(leituras, MES, cnpjs=maiores))
    assert [(c, r) for c, r, _ in resumo] == [
        (_cnpj(k), r) for k, r, _ in ESPERADO_DOS_20_MAIORES
    ]
    assert [v for _, _, v in resumo] == pytest.approx(
        [v for _, _, v in ESPERADO_DOS_20_MAIORES]
    )


def test_sem_filtro_o_fundo_pequeno_aparece(leituras):
    achados = [(c, r) for c, r, _ in _resumo(eventos_do_mes(leituras, MES))]
    assert (_cnpj(21), "fidc_subordinacao_minima_quebra") in achados


def test_so_a_regra_mais_grave_de_cada_medida_dispara(leituras):
    eventos = eventos_do_mes(leituras, MES, cnpjs=[_cnpj(5)])
    assert sorted(e.regra_id for e in eventos) == [
        "fidc_concentracao_cedente_quebra",
        "fidc_inadimplencia_limite_quebra",
    ]


def test_evento_publico_sem_pessoa_com_evidencia_e_rastro(leituras):
    (evento,) = eventos_do_mes(leituras, MES, cnpjs=[_cnpj(2)])
    assert evento.usuario_id is None
    assert evento.objeto_id == _cnpj(2) and evento.nome_do_fundo == "FIDC 2"
    assert evento.ocorrido_em == date(2026, 8, 31)
    assert evento.publico_em == date(2026, 10, 15)  # competência + 45 dias
    assert [(e.quadro, e.valor) for e in evento.evidencia] == [
        ("tab_X_2", 40.0),
        ("tab_X_2", 1000.0),
    ]
    assert evento.rastro.o_que_falta() == []
    texto = json.dumps(evento.como_dict(), ensure_ascii=False)
    assert "4.00%" in texto and "cpf" not in texto.lower()


def test_mesmo_calculo_mesmo_evento(leituras):
    um = eventos_do_mes(leituras, MES)
    outro = eventos_do_mes(leituras.sample(frac=1, random_state=1), MES)
    assert [e.como_dict() for e in um] == [e.como_dict() for e in outro]
    assert len({e.evento_id for e in um}) == len(um)


def test_fundo_sem_campo_nao_gera_evento_da_regra():
    t = _tabelas({1: (900, 100, 1000, 0, 10)}, MES)
    t["tab_I"]["TAB_I2A3_VL_CRED_INAD"] = None
    t["tab_X_2"] = t["tab_X_2"].iloc[0:0]
    assert eventos_do_mes(leituras_dos_informes(t), MES) == []


def test_regras_sao_dados_simples_que_viram_json():
    ids = [r.regra_id for r in REGRAS]
    assert len(ids) == len(set(ids))
    json.dumps([r.__dict__ for r in REGRAS])


def test_como_era_em_nao_ve_informe_ainda_nao_publicado(leituras):
    # julho saiu em 14/09 (31/07 + 45 dias); agosto só em 15/10
    assert set(como_era_em(leituras, "2026-09-30")["competencia"]) == {ANTES}
    assert eventos_do_mes(leituras, MES, como_em="2026-09-30") == []


@settings(max_examples=40, deadline=None)
@given(corte=st.dates(min_value=date(2026, 9, 1), max_value=date(2026, 11, 30)))
def test_cortar_o_futuro_nao_muda_o_passado(leituras, corte):
    com_tudo = eventos_do_mes(leituras, MES, como_em=corte)
    publico = leituras[pd.to_datetime(leituras["disponivel_em"]) <= pd.Timestamp(corte)]
    assert [e.como_dict() for e in eventos_do_mes(publico, MES)] == [
        e.como_dict() for e in com_tudo
    ]


ORDEM = {"info": 0, "atencao": 1, "quebra": 2}


def _pior_gravidade(fundo: tuple) -> int:
    t = _tabelas({1: fundo}, MES)
    eventos = eventos_do_mes(leituras_dos_informes(t), MES)
    return max((ORDEM[e.gravidade] for e in eventos), default=-1)


@settings(max_examples=40, deadline=None)
@given(
    sub=st.integers(0, 500),
    sen=st.integers(1, 500),
    inad=st.integers(0, 900),
    ced=st.integers(0, 80),
)
def test_gravidade_nunca_cai_quando_o_numero_piora(sub, sen, inad, ced):
    """Menos subordinação, mais inadimplência e cedente maior nunca deixam o alerta mais leve."""
    melhor = (sen, sub, 1000, inad, ced)
    pior = (sen + sub, 0, 1000, inad + 100, ced + 20)
    assert _pior_gravidade(pior) >= _pior_gravidade(melhor)


def test_amostra_real_da_cvm_agosto_de_2026():
    pasta = Path(__file__).parent / "arquivos" / "cvm" / "fidc"
    tabelas = fidc.ler_informe((pasta / "inf_mensal_fidc_202608.zip").read_bytes())
    leituras = leituras_dos_informes(tabelas)
    eventos = eventos_do_mes(leituras, "2026-08-31")
    # 05.754.060/0001-13: classe subordinada com 0 cotas (subordinação 0%, quebra) e o maior cedente
    # com 69,48% da carteira (> 50%, atenção); os outros dois fundos não passam em nenhuma regra
    assert [(e.objeto_id, e.regra_id) for e in eventos] == [
        ("05.754.060/0001-13", "fidc_subordinacao_minima_quebra"),
        ("05.754.060/0001-13", "fidc_concentracao_cedente_atencao"),
    ]
    assert eventos[0].valor == 0.0 and eventos[1].valor == pytest.approx(0.6948)
    # subordinação do 07.383.363/0001-00 à mão: Σ subordinadas e mezanino ÷ Σ de todas as classes
    sub = 4.81657918 * 1441940.58904685 + 527.40947935 * 66020.91422952
    total = sub + 8.70918428 * 9115845.10530072
    linha = leituras[leituras["cnpj_fundo"] == "07.383.363/0001-00"].iloc[0]
    assert linha["pl_subordinado"] / linha["pl_das_classes"] == pytest.approx(
        sub / total
    )
