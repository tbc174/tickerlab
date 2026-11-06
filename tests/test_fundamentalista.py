"""Cálculos fundamentalistas do relatório completo de empresa (série 2 da base de ML, PR 2; ADR 0032,
item 1): DuPont, ciclo de caixa, caixa livre, capex contra depreciação, cobertura de juros e o
histórico de 10 anos. Números sintéticos fáceis de conferir à mão, e a WEG real para o DuPont fechar
com o ROE que a tela Fundamentos já mostra."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src import demonstracoes as dm
from src import fundamentalista as fa
from src import fundamentos as fu
from src.banco.demonstracoes import DadosDaEmpresa

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
WEG = "84.429.695/0001-11"


def _linhas(ano: int, fluxos: dict, saldos: dict) -> list[dict]:
    referencia = date(ano, 12, 31)
    comum = {
        "documento": "DFP",
        "referencia": referencia,
        "versao": 1,
        "fim": referencia,
    }
    linhas = [
        {
            **comum,
            "periodo": dm.EXERCICIO,
            "inicio": date(ano, 1, 1),
            "conta": c,
            "valor": v,
        }
        for c, v in fluxos.items()
    ]
    linhas += [
        {**comum, "periodo": dm.POSICAO, "inicio": None, "conta": c, "valor": v}
        for c, v in saldos.items()
    ]
    return linhas


FLUXOS = {
    "receita": 3650.0,
    "custo": -1825.0,
    "ebit": 500.0,
    "lucro_liquido": 300.0,
    "despesas_financeiras": -100.0,
    "fco": 600.0,
    "capex": -250.0,
    "depreciacao": 125.0,
}
SALDOS = {
    "ativo_total": 3000.0,
    "patrimonio_liquido": 1500.0,
    "contas_a_receber": 300.0,
    "estoques": 200.0,
    "fornecedores": 100.0,
}


def _empresa(
    anos=(2024, 2025), fluxos=FLUXOS, saldos=SALDOS, setor="Máquinas"
) -> DadosDaEmpresa:
    linhas = [l for ano in anos for l in _linhas(ano, fluxos, saldos)]
    return DadosDaEmpresa(
        contas=pd.DataFrame(linhas), documentos=pd.DataFrame(), setor=setor
    )


def test_dupont_fecha_com_o_roe():
    resultado = fa.calcular(_empresa())
    margem, giro, alavancagem = (
        resultado["dupont_margem"].valor,
        resultado["dupont_giro"].valor,
        resultado["dupont_alavancagem"].valor,
    )
    assert margem == pytest.approx(300 / 3650)
    assert giro == pytest.approx(3650 / 3000)
    assert alavancagem == pytest.approx(3000 / 1500)
    assert margem * giro * alavancagem == pytest.approx(300 / 1500)
    assert resultado["dupont_roe"].valor == pytest.approx(0.2)


def test_dupont_da_weg_bate_com_o_roe_da_tela():
    contas, documentos = dm.ler_demonstracoes(
        (PASTA / "dfp_cia_aberta_2025.zip").read_bytes(), "DFP"
    )
    dados = DadosDaEmpresa(
        contas=contas[contas["cnpj"] == WEG].drop(columns="cnpj"),
        documentos=documentos[documentos["cnpj"] == WEG],
        setor="Máquinas, Equipamentos, Veículos e Peças",
    )
    roe_da_tela = fu.calcular(dados, None)["roe"].valor
    assert fa.calcular(dados)["dupont_roe"].valor == pytest.approx(roe_da_tela)


def test_ciclo_de_caixa_em_dias_com_saldo_medio():
    resultado = fa.calcular(_empresa())
    assert resultado["pmr"].valor == pytest.approx(300 / 3650 * 365)  # 30 dias
    assert resultado["pme"].valor == pytest.approx(200 / 1825 * 365)  # 40 dias
    assert resultado["pmp"].valor == pytest.approx(100 / 1825 * 365)  # 20 dias
    assert resultado["ciclo_de_caixa"].valor == pytest.approx(30 + 40 - 20)
    assert "saldo médio" in resultado["pmr"].base  # de hoje e de um ano antes


def test_ciclo_sem_o_ano_anterior_usa_o_saldo_do_fim_e_diz():
    resultado = fa.calcular(_empresa(anos=(2025,)))
    assert resultado["pmr"].valor == pytest.approx(30.0)
    assert "fim" in resultado["pmr"].base


def test_caixa_livre_e_capex_contra_depreciacao():
    resultado = fa.calcular(_empresa())
    assert resultado["caixa_livre"].valor == pytest.approx(600 - 250)
    assert resultado["capex_sobre_depreciacao"].valor == pytest.approx(250 / 125)


def test_cobertura_de_juros_e_sem_despesa_financeira_nao_se_aplica():
    assert fa.calcular(_empresa())["cobertura_de_juros"].valor == pytest.approx(5.0)
    sem_divida = {k: v for k, v in FLUXOS.items() if k != "despesas_financeiras"}
    cobertura = fa.calcular(_empresa(fluxos=sem_divida))["cobertura_de_juros"]
    assert cobertura.valor is None and "despesa financeira" in cobertura.motivo


def test_banco_nao_tem_ciclo_nem_caixa_livre():
    resultado = fa.calcular(_empresa(setor="Bancos"))
    for chave in (
        "ciclo_de_caixa",
        "caixa_livre",
        "cobertura_de_juros",
        "dupont_margem",
    ):
        assert resultado[chave].valor is None
        assert resultado[chave].motivo == fu.NAO_SE_APLICA_A_FINANCEIRAS


def test_historico_de_10_anos_com_falta_vertical_horizontal_e_consistencia():
    anos = (2015, 2016, 2018, 2019)  # 2017 faltando
    historico = fa.calcular(_empresa(anos=anos)).historico
    assert list(historico.contas.index) == [2015, 2016, 2017, 2018, 2019]
    assert (
        historico.contas.loc[2017].isna().all()
    )  # falta aparece como falta, não como zero
    assert historico.vertical.loc[2019, "lucro_liquido"] == pytest.approx(300 / 3650)
    assert historico.vertical.loc[2019, "estoques"] == pytest.approx(200 / 3000)
    assert historico.horizontal.loc[2016, "receita"] == pytest.approx(0.0)
    assert pd.isna(
        historico.horizontal.loc[2018, "receita"]
    )  # sem 2017, não há variação
    assert historico.consistencia["anos_com_lucro"] == 4
    assert historico.consistencia["anos_com_dado"] == 4


def test_historico_fica_nos_ultimos_10_anos():
    historico = fa.calcular(_empresa(anos=tuple(range(2010, 2026)))).historico
    assert list(historico.contas.index) == list(range(2016, 2026))


# --- dividendos e diluição (série 2, PR 6) -----------------------------------------------------------
def _com_acoes(
    acoes_por_ano: dict[int, float], dividendos: float = -50.0
) -> DadosDaEmpresa:
    linhas = []
    for ano, acoes in acoes_por_ano.items():
        fluxos = {**FLUXOS, "lucro_liquido": 100.0, "dividendos_pagos": dividendos}
        linhas += _linhas(ano, fluxos, {**SALDOS, "acoes_total": acoes})
    return DadosDaEmpresa(
        contas=pd.DataFrame(linhas), documentos=pd.DataFrame(), setor="Máquinas"
    )


def test_payout_pelo_caixa_e_proventos_do_fre_lado_a_lado():
    proventos = pd.DataFrame(
        {
            "exercicio": [pd.Timestamp("2021-12-31")],
            "dividendo_total": [40.0],
            "payout": [0.4],
        }
    )
    resultado = fa.dividendos_e_diluicao(
        _com_acoes({2021: 100.0, 2022: 100.0}), proventos
    )
    tabela = resultado.historico
    assert tabela.loc[2022, "payout_caixa"] == pytest.approx(
        0.5
    )  # 50 pagos sobre 100 de lucro
    assert tabela.loc[2021, "payout_fre"] == pytest.approx(0.4)
    assert resultado.anos_pagando == 2


def test_dois_exercicios_do_fre_no_mesmo_ano_valem_pelo_mais_tarde():
    """Regressão (lote das 412, 18/10/2026): o FRE do Banco do Brasil tem um exercício parcial
    (31/03/2010) ao lado do cheio (31/12/2010), e o `reindex` por ano quebrava em 45 empresas."""
    proventos = pd.DataFrame(
        {
            "exercicio": [
                pd.Timestamp("2010-03-31"),
                pd.Timestamp("2010-12-31"),
                pd.Timestamp("2010-12-31"),
            ],
            "versao": [11, 19, 20],
            "dividendo_total": [9.0, 40.0, 47.0],
            "payout": [0.4, 0.37, 0.371],
        }
    )
    resultado = fa.dividendos_e_diluicao(
        _com_acoes({2010: 100.0, 2011: 100.0}), proventos
    )
    assert resultado.historico.loc[2010, "dividendo_fre"] == pytest.approx(47.0)
    assert resultado.historico.loc[2010, "payout_fre"] == pytest.approx(0.371)


def test_desdobramento_do_fre_nao_conta_como_diluicao():
    eventos = pd.DataFrame(
        {
            "tipo": ["desdobramento"],
            "data": [pd.Timestamp("2020-08-03")],
            "fator": [10.0],
        }
    )
    resultado = fa.dividendos_e_diluicao(
        _com_acoes({2019: 100.0, 2020: 1000.0, 2021: 1000.0}), eventos=eventos
    )
    assert resultado.historico.loc[2019, "acoes_ajustadas"] == pytest.approx(1000.0)
    assert resultado.diluicao_anual == pytest.approx(0.0)


def test_salto_exato_sem_evento_vira_provavel_desdobramento_e_avisa():
    resultado = fa.dividendos_e_diluicao(_com_acoes({2023: 100.0, 2024: 300.0}))
    assert resultado.diluicao_anual == pytest.approx(0.0)
    assert any("provável desdobramento" in aviso for aviso in resultado.avisos)


def test_aviso_do_salto_escreve_o_numero_em_portugues():
    resultado = fa.dividendos_e_diluicao(_com_acoes({2023: 100.0, 2024: 301.0}))
    assert resultado.avisos == [
        (
            "Entre 2023 e 2024 as ações mudaram 3,01 vezes sem evento no FRE: tratado como "
            "provável desdobramento, não como diluição."
        )
    ]


def test_salto_de_mil_vezes_e_troca_de_unidade_na_cvm():
    """Regressão (fim da série 2): a Petrobras passou de 13.044.201 (milhares) a 13.044.201.261
    ações entre 2020 e 2021, e o aviso dizia "1000.00 vezes ... provável desdobramento"."""
    resultado = fa.dividendos_e_diluicao(
        _com_acoes({2020: 13_044_201.0, 2021: 13_044_201_261.0})
    )
    assert resultado.diluicao_anual == pytest.approx(0.0, abs=1e-4)
    assert resultado.avisos == [
        (
            "Entre 2020 e 2021 a quantidade de ações passou de milhares para unidades na CVM "
            "(mil vezes maior, sem evento no FRE): tratado como troca de unidade, não como "
            "diluição."
        )
    ]


def test_emissao_de_acoes_conta_como_diluicao():
    # antes do fim das tabelas do FRE (2022): emissão sem evento é diluição
    resultado = fa.dividendos_e_diluicao(_com_acoes({2020: 100.0, 2021: 110.0}))
    assert resultado.diluicao_anual == pytest.approx(0.10)
    assert resultado.avisos == []


def test_salto_nas_acoes_depois_de_2022_avisa_sem_fre():
    """Fim da série 2: as ações do Itaú subiram 13% de 2024 para 2025 sem evento (o FRE aberto parou
    em 2022) e o relatório mostrava "diluição de 2,5% ao ano"; pode ter sido bonificação."""
    resultado = fa.dividendos_e_diluicao(
        _com_acoes({2023: 9_803_699.0, 2024: 9_748_073.0, 2025: 11_026_524.0})
    )
    assert resultado.diluicao_anual is None
    [aviso] = resultado.avisos
    assert "Entre 2024 e 2025" in aviso and "13,11%" in aviso
    assert "depois de 2022" in aviso and "bonificação" in aviso


def test_mudanca_pequena_depois_de_2022_continua_diluicao():
    resultado = fa.dividendos_e_diluicao(_com_acoes({2024: 100.0, 2025: 103.0}))
    assert resultado.diluicao_anual == pytest.approx(0.03)
    assert resultado.avisos == []


# --- indicadores sem preço (linha 54 da fila: alavancagem, estrutura, ROA, liquidez, EBITDA) -------
COM_DIVIDA = {
    **SALDOS,
    "patrimonio_liquido": 1200.0,
    "divida_cp": 200.0,
    "divida_lp": 800.0,
    "caixa": 300.0,
    "ativo_circulante": 900.0,
    "passivo_circulante": 600.0,
}


def test_margem_ebitda_soma_a_depreciacao_ao_ebit():
    resultado = fa.calcular(_empresa(saldos=COM_DIVIDA))
    assert resultado["margem_ebitda"].valor == pytest.approx((500 + 125) / 3650)
    assert resultado["margem_ebitda"].base == resultado["cobertura_de_juros"].base


def test_divida_liquida_sobre_ebitda_e_sobre_ebit():
    resultado = fa.calcular(_empresa(saldos=COM_DIVIDA))
    assert resultado["divida_liquida_sobre_ebitda"].valor == pytest.approx(700 / 625)
    assert resultado["divida_liquida_sobre_ebit"].valor == pytest.approx(700 / 500)
    assert "balanço de 31/12/2025" in resultado["divida_liquida_sobre_ebitda"].base


def test_caixa_maior_que_a_divida_da_razao_negativa():
    saldos = {**COM_DIVIDA, "caixa": 1500.0}  # caixa líquido de 500
    resultado = fa.calcular(_empresa(saldos=saldos))
    assert resultado["divida_liquida_sobre_ebitda"].valor == pytest.approx(-500 / 625)


def test_ebitda_negativo_fica_sem_numero_e_diz_por_que():
    fluxos = {**FLUXOS, "ebit": -300.0, "depreciacao": 100.0}
    resultado = fa.calcular(_empresa(fluxos=fluxos, saldos=COM_DIVIDA))
    for chave, motivo in (
        ("divida_liquida_sobre_ebitda", "EBITDA negativo ou zero"),
        ("divida_liquida_sobre_ebit", "EBIT negativo ou zero"),
    ):
        assert resultado[chave].valor is None
        assert motivo in resultado[chave].motivo


def test_sem_divida_no_balanco_a_alavancagem_diz_por_que():
    resultado = fa.calcular(_empresa())  # SALDOS não tem dívida nem caixa
    alavancagem = resultado["divida_liquida_sobre_ebitda"]
    assert alavancagem.valor is None and alavancagem.motivo


def test_passivos_e_patrimonio_sobre_ativos_somam_um():
    resultado = fa.calcular(_empresa(saldos=COM_DIVIDA))
    assert resultado["passivos_sobre_ativos"].valor == pytest.approx(1800 / 3000)
    assert resultado["pl_sobre_ativos"].valor == pytest.approx(1200 / 3000)


def test_roa_e_o_lucro_consolidado_sobre_o_ativo():
    resultado = fa.calcular(_empresa(saldos=COM_DIVIDA))
    assert resultado["roa"].valor == pytest.approx(300 / 3000)


def test_liquidez_corrente_e_sem_passivo_circulante():
    liquidez = fa.calcular(_empresa(saldos=COM_DIVIDA))["liquidez_corrente"]
    assert liquidez.valor == pytest.approx(1.5)
    sem = {k: v for k, v in COM_DIVIDA.items() if k != "passivo_circulante"}
    liquidez = fa.calcular(_empresa(saldos=sem))["liquidez_corrente"]
    assert liquidez.valor is None and "circulante" in liquidez.motivo


def test_banco_tem_roa_e_patrimonio_sobre_ativos_mas_nao_ebitda_nem_liquidez():
    resultado = fa.calcular(_empresa(saldos=COM_DIVIDA, setor="Bancos"))
    assert resultado["roa"].valor == pytest.approx(0.1)
    assert resultado["pl_sobre_ativos"].valor == pytest.approx(0.4)
    for chave in (
        "margem_ebitda",
        "divida_liquida_sobre_ebitda",
        "divida_liquida_sobre_ebit",
        "liquidez_corrente",
    ):
        assert resultado[chave].motivo == fu.NAO_SE_APLICA_A_FINANCEIRAS


# --- dividendo por ação, payout e crescimento do dividendo (linha 54 da fila) ------------------------
def _pagando(pagos_por_ano: dict[int, float], acoes: float = 100.0) -> DadosDaEmpresa:
    linhas = []
    for ano, pagos in pagos_por_ano.items():
        fluxos = {**FLUXOS, "lucro_liquido": 100.0, "dividendos_pagos": -pagos}
        linhas += _linhas(ano, fluxos, {**SALDOS, "acoes_total": acoes})
    return DadosDaEmpresa(pd.DataFrame(linhas), pd.DataFrame(), "Máquinas")


def test_dividendo_por_acao_de_cada_ano_pelo_fluxo_de_caixa():
    resultado = fa.dividendos_e_diluicao(_com_acoes({2020: 100.0, 2021: 125.0}))
    assert resultado.historico.loc[2020, "dividendo_por_acao"] == pytest.approx(0.5)
    assert resultado.historico.loc[2021, "dividendo_por_acao"] == pytest.approx(0.4)


def test_dividendo_por_acao_usa_as_acoes_ajustadas_pelo_desdobramento():
    eventos = pd.DataFrame(
        {
            "tipo": ["desdobramento"],
            "data": [pd.Timestamp("2020-08-03")],
            "fator": [10.0],
        }
    )
    resultado = fa.dividendos_e_diluicao(
        _com_acoes({2019: 100.0, 2020: 1000.0}), eventos=eventos
    )
    # 50 pagos sobre as 100 ações de 2019, que são 1.000 de hoje: R$ 0,05 por ação de hoje
    assert resultado.historico.loc[2019, "dividendo_por_acao"] == pytest.approx(0.05)


def test_dividendos_e_jcp_por_acao_do_fre():
    proventos = pd.DataFrame(
        {
            "exercicio": [pd.Timestamp("2021-12-31")],
            "dividendo_total": [40.0],
            "payout": [0.4],
            "dividendos": [30.0],
            "jcp": [10.0],
        }
    )
    tabela = fa.dividendos_e_diluicao(
        _com_acoes({2021: 100.0, 2022: 100.0}), proventos
    ).historico
    assert tabela.loc[2021, "dividendos_fre_por_acao"] == pytest.approx(0.3)
    assert tabela.loc[2021, "jcp_fre_por_acao"] == pytest.approx(0.1)
    assert pd.isna(tabela.loc[2022, "jcp_fre_por_acao"])  # sem o FRE daquele ano


def test_indicadores_do_ultimo_ano_dos_dividendos():
    dados = _pagando({ano: 50.0 * 1.1 ** (ano - 2020) for ano in range(2020, 2026)})
    indicadores = fa.indicadores_dos_dividendos(fa.dividendos_e_diluicao(dados))
    dpa = indicadores["dividendo_por_acao"]
    assert dpa.valor == pytest.approx(0.5 * 1.1**5)
    assert dpa.base == "DFP de 2025"
    assert indicadores["payout"].valor == pytest.approx(0.5 * 1.1**5)
    crescimento = indicadores["crescimento_do_dividendo"]
    assert crescimento.valor == pytest.approx(0.1)
    assert crescimento.base == "DFP de 2020 e de 2025"


def test_crescimento_do_dividendo_pede_seis_exercicios():
    dados = _pagando({2023: 50.0, 2024: 50.0, 2025: 50.0})
    indicadores = fa.indicadores_dos_dividendos(fa.dividendos_e_diluicao(dados))
    crescimento = indicadores["crescimento_do_dividendo"]
    assert crescimento.valor is None and "6" in crescimento.motivo


def test_crescimento_do_dividendo_sem_numero_com_salto_sem_evento():
    acoes = {ano: 100.0 for ano in range(2020, 2025)} | {2025: 113.0}
    resultado = fa.dividendos_e_diluicao(_com_acoes(acoes))
    crescimento = fa.indicadores_dos_dividendos(resultado)["crescimento_do_dividendo"]
    assert crescimento.valor is None and "sem evento" in crescimento.motivo


def test_ano_sem_dividendo_no_inicio_fica_sem_crescimento():
    dados = _pagando({ano: 0.0 if ano == 2020 else 50.0 for ano in range(2020, 2026)})
    indicadores = fa.indicadores_dos_dividendos(fa.dividendos_e_diluicao(dados))
    crescimento = indicadores["crescimento_do_dividendo"]
    assert crescimento.valor is None and crescimento.motivo


def test_sem_lucro_o_payout_diz_por_que():
    linhas = _linhas(
        2025,
        {**FLUXOS, "lucro_liquido": -10.0, "dividendos_pagos": -5.0},
        {**SALDOS, "acoes_total": 100.0},
    )
    dados = DadosDaEmpresa(pd.DataFrame(linhas), pd.DataFrame(), "Máquinas")
    payout = fa.indicadores_dos_dividendos(fa.dividendos_e_diluicao(dados))["payout"]
    assert payout.valor is None and "lucro" in payout.motivo


def test_sem_demonstracoes_os_dividendos_dizem_por_que():
    vazio = fa.DividendosEDiluicao(pd.DataFrame(), None, 0)  # o que sai sem DFP
    indicadores = fa.indicadores_dos_dividendos(vazio)
    assert set(indicadores) == {
        "dividendo_por_acao",
        "payout",
        "crescimento_do_dividendo",
    }
    assert all(i.valor is None and i.motivo for i in indicadores.values())


@settings(max_examples=60, deadline=None)
@given(
    mudancas=st.lists(st.floats(-0.04, 0.04), min_size=6, max_size=6),
    pagos=st.lists(st.floats(1.0, 1e6), min_size=7, max_size=7),
    corte=st.integers(2020, 2025),
)
def test_dividendo_por_acao_nao_olha_o_futuro(mudancas, pagos, corte):
    """Cortar os anos depois de `corte` não muda o dividendo por ação nem o payout até ele (sem
    desdobramento: um evento depois do corte reescreve o passado na unidade de hoje, de propósito)."""
    acoes, linhas = 1_000.0, []
    for i, ano in enumerate(range(2019, 2026)):
        acoes *= 1 + (mudancas[i - 1] if i else 0.0)
        fluxos = {**FLUXOS, "lucro_liquido": 100.0, "dividendos_pagos": -pagos[i]}
        linhas += _linhas(ano, fluxos, {**SALDOS, "acoes_total": acoes})
    tudo = pd.DataFrame(linhas)
    cortado = tudo[tudo["referencia"] <= date(corte, 12, 31)]
    colunas = ["dividendo_por_acao", "payout_caixa"]
    completo = fa.dividendos_e_diluicao(
        DadosDaEmpresa(tudo, pd.DataFrame(), "Máquinas")
    )
    ate_o_corte = fa.dividendos_e_diluicao(
        DadosDaEmpresa(cortado, pd.DataFrame(), "Máquinas")
    )
    pd.testing.assert_frame_equal(
        completo.historico.loc[:corte, colunas], ate_o_corte.historico[colunas]
    )


# --- ações por espécie (ON e PN) para a ficha técnica ----------------------------------------------
def test_acoes_por_especie_tira_a_tesouraria():
    saldos = {
        **SALDOS,
        "acoes_total": 300.0,
        "acoes_tesouraria": 10.0,
        "acoes_ordinarias": 100.0,
        "acoes_preferenciais": 200.0,
        "acoes_ordinarias_tesouraria": 4.0,
        "acoes_preferenciais_tesouraria": 6.0,
    }
    acoes = fa.acoes_por_especie(_empresa(saldos=saldos))
    assert acoes.total.valor == pytest.approx(290.0)
    assert (acoes.ordinarias, acoes.preferenciais) == (96.0, 194.0)
    assert acoes.total.base == "balanço de 31/12/2025"


def test_acoes_por_especie_sem_as_especies_mostra_so_o_total():
    acoes = fa.acoes_por_especie(_empresa(saldos={**SALDOS, "acoes_total": 300.0}))
    assert acoes.total.valor == pytest.approx(300.0)
    assert acoes.ordinarias is None and acoes.preferenciais is None


def test_acoes_por_especie_em_milhares_corrige_como_a_tela():
    fluxos = {**FLUXOS, "lpa_basico": 0.001}  # 300 de lucro ÷ 0,001 = 300 mil ações
    saldos = {**SALDOS, "acoes_total": 300.0, "acoes_ordinarias": 300.0}
    acoes = fa.acoes_por_especie(_empresa(fluxos=fluxos, saldos=saldos))
    assert acoes.total.valor == pytest.approx(300_000.0)
    assert acoes.ordinarias == pytest.approx(300_000.0)
    assert "milhares" in acoes.nota


def test_sem_acoes_no_documento_diz_por_que():
    acoes = fa.acoes_por_especie(_empresa())
    assert acoes.total.valor is None and acoes.total.motivo
