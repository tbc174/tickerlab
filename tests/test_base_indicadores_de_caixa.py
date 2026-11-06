"""Contas da ficha tiradas da DFC, da DVA e da DRE (série T1, PR 2): EBITDA, capex, FCF e dividendos
recebidos, cada um com as contas de onde veio e o dia em que ficou público."""

import pandas as pd
import pytest

from base.contas_cvm import ler_contas
from base.indicadores_de_caixa import COLUNAS, indicadores_de_caixa
from base.ponto_no_tempo import como_era_em, montar_base
from tests.test_base_contas_cvm import ZIP_REAL

A = "11.111.111/0001-11"
M = 1_000_000.0  # valores em milhões de reais
INICIO, FIM = pd.Timestamp("2023-01-01"), pd.Timestamp("2023-12-31")
DIVULGADO = pd.Timestamp("2024-03-01")


def _linha(demonstracao, conta, descricao, valor, **outros):
    linha = {
        "cnpj": A,
        "empresa": "EMPRESA A",
        "documento": "DFP",
        "referencia": FIM,
        "versao": 1,
        "demonstracao": demonstracao,
        "grupo": "con",
        "ordem": "ultimo",
        "inicio": INICIO,
        "fim": FIM,
        "conta": conta,
        "descricao": descricao,
        "conta_fixa": True,
        "valor": valor * M,
        "divulgado_em": DIVULGADO,
        "origem": "dados_abertos",
    }
    return linha | outros


def _empresa(
    *extras, dva=True, ebit="Resultado Antes do Resultado Financeiro e dos Tributos"
):
    linhas = [
        _linha("DRE", "3.05", ebit, 500.0),
        _linha("DFC_MI", "6.01", "Caixa Líquido Atividades Operacionais", 900.0),
        _linha("DFC_MI", "6.01.01.02", "Depreciação e Amortização", 180.0),
        _linha("DFC_MI", "6.02", "Caixa Líquido Atividades de Investimento", -350.0),
        _linha("DFC_MI", "6.02.01", "Aquisição de Imobilizado", -300.0),
        _linha("DFC_MI", "6.02.02", "Aquisição de Intangível", -50.0),
        _linha("DFC_MI", "6.02.03", "Venda de Imobilizado", 20.0),
        _linha("DFC_MI", "6.02.04", "Dividendos Recebidos", 30.0),
        _linha("DFC_MI", "6.03.01", "Dividendos Pagos", -100.0),
    ]
    if dva:
        linhas.append(
            _linha("DVA", "7.04.01", "Depreciação, Amortização e Exaustão", -200.0)
        )
    return pd.DataFrame([*linhas, *extras])


def _um(tabela):
    assert len(tabela) == 1
    return tabela.iloc[0]


def test_ebitda_e_o_ebit_mais_a_depreciacao_da_dva():
    linha = _um(indicadores_de_caixa(_empresa()))
    assert linha["ebit"] == 500.0 * M
    assert (
        linha["depreciacao_amortizacao"] == 200.0 * M
    )  # a DVA traz a retenção com sinal
    assert linha["fonte_da_depreciacao"] == "DVA 7.04.01"
    assert linha["ebitda"] == 700.0 * M
    assert list(indicadores_de_caixa(_empresa()).columns) == list(COLUNAS)


def test_sem_dva_a_depreciacao_vem_das_linhas_da_dfc():
    direito_de_uso = _linha(
        "DFC_MI", "6.01.01.03", "Depreciação de Direito de Uso", 15.0
    )
    linha = _um(indicadores_de_caixa(_empresa(direito_de_uso, dva=False)))
    assert linha["depreciacao_amortizacao"] == 195.0 * M
    assert linha["fonte_da_depreciacao"] == "DFC_MI 6.01.01.02 + 6.01.01.03"
    assert linha["ebitda"] == 695.0 * M


def test_amortizacao_que_nao_e_depreciacao_nao_entra():
    """'Amortização do custo de captação' é despesa financeira, não D&A."""
    captacao = _linha("DFC_MI", "6.01.01.04", "Amortização do Custo de Captação", 9.0)
    linha = _um(indicadores_de_caixa(_empresa(captacao, dva=False)))
    assert linha["depreciacao_amortizacao"] == 180.0 * M


def test_banco_fica_sem_ebit_e_sem_ebitda():
    """No plano dos bancos, a 3.05 é o resultado antes dos tributos: fica vazio, não errado."""
    linha = _um(
        indicadores_de_caixa(
            _empresa(ebit="Resultado Antes dos Tributos sobre o Lucro")
        )
    )
    assert pd.isna(linha["ebit"]) and pd.isna(linha["ebitda"])
    assert linha["capex"] == 350.0 * M  # o resto continua


def test_capex_soma_as_aquisicoes_e_ignora_vendas_e_entradas():
    distrato = _linha("DFC_MI", "6.02.05", "Distrato de Contratos do Intangível", 7.0)
    alienacao = _linha("DFC_MI", "6.02.06", "Alienação de Ativo Imobilizado", 3.0)
    linha = _um(indicadores_de_caixa(_empresa(distrato, alienacao)))
    assert linha["capex"] == 350.0 * M
    assert linha["contas_do_capex"] == "DFC_MI 6.02.01 + 6.02.02"


def test_capex_nao_conta_duas_vezes_a_mae_e_as_filhas():
    filhas = [
        _linha("DFC_MI", "6.02.01.01", "Aquisição de Imobilizado - Máquinas", -200.0),
        _linha("DFC_MI", "6.02.01.02", "Aquisição de Imobilizado - Prédios", -100.0),
    ]
    linha = _um(indicadores_de_caixa(_empresa(*filhas)))
    assert linha["capex"] == 350.0 * M
    assert linha["contas_do_capex"] == "DFC_MI 6.02.01 + 6.02.02"


def test_fcf_e_o_caixa_operacional_menos_o_capex():
    linha = _um(indicadores_de_caixa(_empresa()))
    assert linha["caixa_operacional"] == 900.0 * M
    assert linha["fcf"] == 550.0 * M


def test_sem_linha_de_capex_o_capex_e_o_fcf_ficam_vazios():
    sem = _empresa()
    sem = sem[~sem["descricao"].str.startswith("Aquisição")]
    linha = _um(indicadores_de_caixa(sem))
    assert pd.isna(linha["capex"]) and pd.isna(linha["fcf"])
    assert linha["contas_do_capex"] is None


def test_dividendos_recebidos_na_operacao_ou_no_investimento():
    na_operacao = _linha(
        "DFC_MI", "6.01.02.09", "Recebimento de Juros sobre o Capital Próprio", 12.0
    )
    a_receber = _linha("DFC_MI", "6.01.02.10", "Dividendos a Receber", 40.0)
    linha = _um(indicadores_de_caixa(_empresa(na_operacao, a_receber)))
    assert linha["dividendos_recebidos"] == 42.0 * M  # 30 + 12; pagos e a receber fora
    assert linha["contas_dos_dividendos"] == "DFC_MI 6.01.02.09 + 6.02.04"


def test_no_itr_vale_o_acumulado_do_ano_como_a_dfc():
    """A DFC do ITR é do começo do ano ao fim do trimestre: o EBIT do trimestre sozinho não entra."""
    itr = {
        "documento": "ITR",
        "referencia": pd.Timestamp("2023-06-30"),
        "fim": pd.Timestamp("2023-06-30"),
    }
    linhas = [
        _linha("DRE", "3.05", "Resultado Antes do Resultado Financeiro e dos Tributos", 120.0, **itr, inicio=pd.Timestamp("2023-04-01")),
        _linha("DRE", "3.05", "Resultado Antes do Resultado Financeiro e dos Tributos", 230.0, **itr),
        _linha("DVA", "7.04.01", "Depreciação, Amortização e Exaustão", -40.0, **itr),
        _linha("DFC_MI", "6.01", "Caixa Líquido Atividades Operacionais", 300.0, **itr),
    ]  # fmt: skip
    linha = _um(indicadores_de_caixa(pd.DataFrame(linhas)))
    assert (linha["inicio"], linha["fim"]) == (INICIO, pd.Timestamp("2023-06-30"))
    assert linha["ebitda"] == 270.0 * M


def test_publico_desde_o_mais_novo_dos_numeros_usados():
    tardia = _linha(
        "DVA",
        "7.04.01",
        "Depreciação, Amortização e Exaustão",
        -200.0,
        divulgado_em=pd.Timestamp("2024-04-10"),
    )
    empresa = _empresa(dva=False)
    linha = _um(indicadores_de_caixa(pd.concat([empresa, pd.DataFrame([tardia])])))
    assert linha["divulgado_em"] == pd.Timestamp("2024-04-10")


def test_sem_olhar_o_futuro_a_reapresentacao_so_vale_depois_de_publicada():
    v1 = _empresa()
    v2 = v1.assign(versao=2, divulgado_em=pd.Timestamp("2024-08-01"))
    v2.loc[v2["conta"] == "6.02.01", "valor"] = -400.0 * M
    base = montar_base(pd.concat([v1, v2], ignore_index=True))
    antes = _um(indicadores_de_caixa(como_era_em(base, "2024-07-31")))
    depois = _um(indicadores_de_caixa(como_era_em(base, "2024-08-01")))
    assert antes["capex"] == 350.0 * M
    assert depois["capex"] == 450.0 * M
    assert depois["divulgado_em"] == pd.Timestamp("2024-08-01")


def test_sem_dfc_devolve_tabela_vazia_com_as_colunas():
    so_dre = _empresa().query("demonstracao == 'DRE'")
    tabela = indicadores_de_caixa(so_dre)
    assert tabela.empty and list(tabela.columns) == list(COLUNAS)


@pytest.fixture(scope="module")
def reais():
    contas = ler_contas(ZIP_REAL.read_bytes(), "DFP").contas
    tabela = indicadores_de_caixa(contas)
    return tabela[tabela["fim"] == pd.Timestamp("2024-12-31")].set_index("cnpj")


PETROBRAS, WEG = "33.000.167/0001-01", "84.429.695/0001-11"
ITAU, BB = "60.872.504/0001-23", "00.000.000/0001-91"


def test_zip_real_capex_e_dividendos(reais):
    assert reais.loc[PETROBRAS, "capex"] == 79_856_000_000.0
    assert reais.loc[PETROBRAS, "dividendos_recebidos"] == 787_000_000.0
    assert reais.loc[WEG, "capex"] == pytest.approx(1_850_322_000.0)
    assert reais.loc[WEG, "dividendos_recebidos"] == 0.0
    assert (
        reais.loc[ITAU, "capex"] == 7_368_000_000.0
    )  # o distrato do intangível (+270) fica fora


def test_zip_real_ebitda_so_fora_dos_bancos(reais):
    """O zip de teste não tem a DVA: a D&A vem da DFC (Petrobras 6.01.01.04)."""
    petrobras = reais.loc[PETROBRAS]
    assert petrobras["depreciacao_amortizacao"] == 67_033_000_000.0
    assert petrobras["fonte_da_depreciacao"] == "DFC_MI 6.01.01.04"
    assert petrobras["ebitda"] == petrobras["ebit"] + 67_033_000_000.0
    assert pd.isna(reais.loc[BB, "ebitda"]) and pd.isna(reais.loc[ITAU, "ebitda"])
