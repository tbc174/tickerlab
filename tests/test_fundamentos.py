"""Fundamentos da CVM (Research, etapa 3): leitura das demonstrações, cálculo dos indicadores,
banco e coleta, sem internet (amostras reais de 4 empresas em `tests/arquivos/cvm/fundamentos/`)."""

import io
import zipfile
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from scripts import atualizar_fundamentos
from src import demonstracoes as dm
from src import fundamentos as fu
from src.banco import demonstracoes as repo
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
PETROBRAS, ITAU, BB, WEG = (
    "33.000.167/0001-01",
    "60.872.504/0001-23",
    "00.000.000/0001-91",
    "84.429.695/0001-11",
)
BILHAO = 1e9


def _ler(arquivo: str, documento: str):
    return dm.ler_demonstracoes((PASTA / arquivo).read_bytes(), documento)


@pytest.fixture(scope="module")
def banco(tmp_path_factory):
    """Um SQLite com as amostras gravadas (DFP 2024 e 2025, ITR 2026 e o cadastro)."""
    url = f"sqlite:///{(tmp_path_factory.mktemp('f') / 'f.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    with motor.begin() as c:
        repo.gravar_setores(
            c, dm.ler_setores((PASTA / "cad_cia_aberta.csv").read_bytes())
        )
        for arquivo, documento in (
            ("dfp_cia_aberta_2024.zip", "DFP"),
            ("dfp_cia_aberta_2025.zip", "DFP"),
            ("itr_cia_aberta_2026.zip", "ITR"),
        ):
            repo.gravar_demonstracoes(c, *_ler(arquivo, documento))
    yield motor
    motor.dispose()


def _empresa(banco, cnpj):
    with banco.connect() as c:
        return repo.dados_da_empresa(c, cnpj)


# --- leitura ---------------------------------------------------------------------------------------
MIL = 1_000


def test_dfp_traz_as_contas_do_relatorio_completo():
    """Série 2 da base de ML, PR 1: as contas do relatório completo de empresa (WEG, DFP 2025,
    números do arquivo da CVM em milhares). As que a empresa divide em várias linhas são somadas."""
    contas, _ = _ler("dfp_cia_aberta_2025.zip", "DFP")
    weg = contas[contas["cnpj"] == WEG]
    saldos = weg[weg["periodo"] == dm.POSICAO].set_index("conta")["valor"]
    fluxos = weg[weg["periodo"] == dm.EXERCICIO].set_index("conta")["valor"]
    assert saldos["contas_a_receber"] == 7_837_018 * MIL
    assert saldos["estoques"] == 9_911_053 * MIL
    assert saldos["imobilizado"] == 11_511_802 * MIL
    assert saldos["intangivel"] == 2_784_989 * MIL
    assert saldos["fornecedores"] == 2_789_346 * MIL
    assert {"ativo_circulante", "passivo_circulante"} <= set(saldos.index)
    assert fluxos["custo"] == -27_122_477 * MIL
    assert fluxos["despesas_financeiras"] == -2_173_378 * MIL
    assert fluxos["depreciacao"] == 1_001_296 * MIL
    assert fluxos["capex"] == -(2_563_450 + 127_871) * MIL  # imobilizado + intangível
    assert fluxos["dividendos_pagos"] == -5_384_769 * MIL


def test_dfp_traz_as_contas_das_notas_classicas():
    """Série 2, PR 3: lucros retidos (Altman) e despesas com vendas e administrativas (Beneish)."""
    contas, _ = _ler("dfp_cia_aberta_2025.zip", "DFP")
    weg = contas[contas["cnpj"] == WEG]
    saldos = weg[weg["periodo"] == dm.POSICAO].set_index("conta")["valor"]
    fluxos = weg[weg["periodo"] == dm.EXERCICIO].set_index("conta")["valor"]
    assert saldos["reservas_de_lucro"] == 2_575_748 * MIL
    assert saldos["lucros_acumulados"] == 0
    assert fluxos["despesas_com_vendas"] == -3_353_431 * MIL
    assert fluxos["despesas_administrativas"] == -1_513_882 * MIL


def test_composicao_do_capital_traz_as_ordinarias_e_as_preferenciais():
    """Linha 54 da fila: as ações por espécie para a ficha técnica (Petrobras tem ON e PN; a WEG,
    só ON, com ações em tesouraria). Números do arquivo de composição do capital da CVM."""
    contas, _ = _ler("dfp_cia_aberta_2025.zip", "DFP")
    saldos = contas[contas["periodo"] == dm.POSICAO]
    petr = saldos[saldos["cnpj"] == PETROBRAS].set_index("conta")["valor"]
    weg = saldos[saldos["cnpj"] == WEG].set_index("conta")["valor"]
    assert petr["acoes_ordinarias"] == 7_442_231_382
    assert petr["acoes_preferenciais"] == 5_446_501_379
    assert petr["acoes_ordinarias"] + petr["acoes_preferenciais"] == petr["acoes_total"]
    assert weg["acoes_ordinarias_tesouraria"] == 1_622_025
    assert (
        weg["acoes_preferenciais"] == 0 and weg["acoes_preferenciais_tesouraria"] == 0
    )


def test_depreciacao_do_banco_nao_soma_juros_ao_custo_amortizado():
    """Regressão (fim da série 2): no Itaú, "Resultado de Juros ... ao Custo Amortizado" (−39,1 bi)
    entrava na depreciação, que saía −31,7 bi em vez dos 7,4 bi do PDF da DFP 2025."""
    contas, _ = _ler("dfp_cia_aberta_2025.zip", "DFP")
    itau = contas[(contas["cnpj"] == ITAU) & (contas["periodo"] == dm.EXERCICIO)]
    assert itau.set_index("conta")["valor"]["depreciacao"] == 7_386_000 * MIL


@pytest.mark.parametrize(
    ("descricao", "e_depreciacao"),
    [
        ("Depreciação, Amortização e Exaustão", True),
        ("Amortização de ativos de direito de uso", True),
        ("Amortização de arrendamentos", True),
        ("Amortização de ágio", True),
        ("Amortização de custos com captação de novos clientes", True),
        (
            "Resultado de Juros e Variação Cambial de Ativos Financeiros ao Custo Amortizado",
            False,
        ),
        ("Atualização dos ativos financeiros ao custo amortizado", False),
        (
            "Encargos fin. sobre empréstimos, financiamentos, debêntures e amortização de custos",
            False,
        ),
        ("Juros, amortização de captação e variações cambiais líquidas", False),
        ("Amortização dos custos de transação sobre debêntures", False),
        ("Receitas diferidas amortizadas", False),
        ("Linearização de receitas amortizadas", False),
    ],
)
def test_depreciacao_pela_descricao_da_linha(descricao, e_depreciacao):
    """Linhas reais da DFP 2025 (Serena, PetroRecôncavo, BB Seguridade, Vulcabras, Iguatemi...)."""
    descricoes = pd.Series([descricao]).map(dm._sem_acento)
    assert dm.e_depreciacao(descricoes).iloc[0] == e_depreciacao


# linhas reais da DRE consolidada da Vale na DFP 2025 (v2): a 1ª classe do lucro por ação é a PNA,
# que a Vale não tem (0); o da ON está na 3.99.01.02
DRE_DA_VALE = """CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA
33.592.510/0001-54;2025-12-31;2;VALE S.A.;004170;DF Consolidado - Demonstração do Resultado;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.01;Receita de Venda de Bens e/ou Serviços;213595000.0000000000;S
33.592.510/0001-54;2025-12-31;2;VALE S.A.;004170;DF Consolidado - Demonstração do Resultado;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.11;Lucro/Prejuízo Consolidado do Período;11811000.0000000000;S
33.592.510/0001-54;2025-12-31;2;VALE S.A.;004170;DF Consolidado - Demonstração do Resultado;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.11.01;Atribuído a Sócios da Empresa Controladora;13814000.0000000000;S
33.592.510/0001-54;2025-12-31;2;VALE S.A.;004170;DF Consolidado - Demonstração do Resultado;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.99.01;Lucro Básico por Ação;0.0000000000;N
33.592.510/0001-54;2025-12-31;2;VALE S.A.;004170;DF Consolidado - Demonstração do Resultado;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.99.01.01;PNA;0.0000000000;N
33.592.510/0001-54;2025-12-31;2;VALE S.A.;004170;DF Consolidado - Demonstração do Resultado;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.99.01.02;ON;3.2400000000;N
"""


def _zip_so_com_a_dre(csv: str) -> bytes:
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        arquivo.writestr(
            "dfp_cia_aberta_DRE_con_2025.csv", csv.encode(dm.CODIFICACAO_DA_CVM)
        )
    return conteudo.getvalue()


def test_lpa_e_o_da_primeira_classe_com_valor():
    """Regressão (fim da série 2): com o LPA 0 da PNA, a escala das ações da Vale não era corrigida
    e o P/L saía 0,03×. O LPA passa a ser o da 1ª classe diferente de zero (ON, R$ 3,24)."""
    contas, _ = dm.ler_demonstracoes(_zip_so_com_a_dre(DRE_DA_VALE), "DFP")
    lpa = contas[contas["conta"] == "lpa_basico"]
    assert lpa["valor"].tolist() == [pytest.approx(3.24)]


def test_lpa_todo_zerado_fica_uma_linha_com_zero():
    so_zeros = DRE_DA_VALE.replace(";3.2400000000;", ";0.0000000000;")
    contas, _ = dm.ler_demonstracoes(_zip_so_com_a_dre(so_zeros), "DFP")
    assert contas.loc[contas["conta"] == "lpa_basico", "valor"].tolist() == [0]


def test_banco_le_caixa_imobilizado_e_intangivel():
    """Fim da série 2: no plano dos bancos o caixa é a 1.01 e o imobilizado e o intangível são a 1.06
    e a 1.07 (Itaú, DFP 2025, conferidos no PDF)."""
    contas, _ = _ler("dfp_cia_aberta_2025.zip", "DFP")
    itau = contas[(contas["cnpj"] == ITAU) & (contas["periodo"] == dm.POSICAO)]
    saldos = itau.set_index("conta")["valor"]
    assert saldos["caixa"] == 37_144_000 * MIL
    assert saldos["imobilizado"] == 12_635_000 * MIL
    assert saldos["intangivel"] == 24_099_000 * MIL


def test_banco_nao_ganha_estoques_nem_fornecedores():
    contas, _ = _ler("dfp_cia_aberta_2025.zip", "DFP")
    do_banco = set(contas.loc[contas["cnpj"] == BB, "conta"])
    assert not {"estoques", "fornecedores", "custo"} & do_banco


def test_dfp_traz_as_contas_chave_em_reais():
    contas, documentos = _ler("dfp_cia_aberta_2025.zip", "DFP")
    petr = contas[(contas["cnpj"] == PETROBRAS) & (contas["periodo"] == dm.EXERCICIO)]
    valores = dict(zip(petr["conta"], petr["valor"], strict=True))
    assert valores["receita"] == pytest.approx(497.549 * BILHAO)
    assert valores["lucro_liquido"] == pytest.approx(110.605 * BILHAO)
    assert valores["lucro_controladores"] == pytest.approx(110.129 * BILHAO)
    assert valores["lpa_basico"] == pytest.approx(
        8.54
    )  # reais por ação: sem a escala "MIL"
    doc = documentos.set_index("cnpj").loc[PETROBRAS]
    assert doc["link"].startswith("https://www.rad.cvm.gov.br/") and doc["recebido_em"]


def test_banco_usa_outro_plano_de_contas_e_e_reconhecido():
    contas, _ = _ler("dfp_cia_aberta_2025.zip", "DFP")
    itau = set(contas.loc[contas["cnpj"] == ITAU, "conta"])
    assert (
        "ebit" not in itau
        and {"receita", "lucro_liquido", "lucro_controladores"} <= itau
    )
    setores = dm.ler_setores((PASTA / "cad_cia_aberta.csv").read_bytes()).set_index(
        "cnpj"
    )
    assert setores.loc[ITAU, "setor"] == "Bancos"
    assert dm.e_financeira("Bancos") and not dm.e_financeira(
        "Petróleo e Gás", ["receita", "ebit"]
    )
    assert dm.e_financeira(
        "", ["receita", "lucro_liquido"]
    )  # sem EBIT: plano financeiro


def test_cadastro_traz_situacao_categoria_e_registro():
    """O registro ativo vence o cancelado; as datas viram `date` e a data torta vira nulo."""
    setores = dm.ler_setores((PASTA / "cad_cia_aberta.csv").read_bytes()).set_index(
        "cnpj"
    )
    itau = setores.loc[ITAU]
    assert (itau["situacao"], itau["categoria"]) == ("ATIVO", "Categoria A")
    assert itau["situacao_desde"] == date(2024, 2, 15)
    assert itau["registro"] == date(1991, 5, 21)
    torto = (
        "CNPJ_CIA;DENOM_SOCIAL;DT_REG;SIT;DT_INI_SIT;SETOR_ATIV;CATEG_REG\n"
        "11.111.111/0001-11;EMPRESA A;;CANCELADA;31/12/1999;Têxtil;\n"
    ).encode("cp1252")
    linha = dm.ler_setores(torto).iloc[0]
    assert linha["situacao"] == "CANCELADA" and linha["categoria"] == ""
    assert linha["situacao_desde"] is None and linha["registro"] is None


def test_cadastro_so_com_o_setor_da_as_outras_colunas_vazias():
    """Um arquivo antigo, só com SIT e SETOR_ATIV, ainda serve: o setor vem, o resto fica vazio."""
    antigo = (
        "CNPJ_CIA;DENOM_SOCIAL;SIT;SETOR_ATIV\n00.000.000/0001-91;BANCO DO BRASIL;ATIVO;Bancos\n"
    ).encode("cp1252")
    linha = dm.ler_setores(antigo).iloc[0]
    assert (linha["setor"], linha["situacao"], linha["categoria"]) == (
        "Bancos",
        "ATIVO",
        "",
    )
    assert linha["situacao_desde"] is None and linha["registro"] is None


def test_itr_fica_com_a_versao_mais_nova_e_separa_os_acumulados():
    contas, documentos = _ler("itr_cia_aberta_2026.zip", "ITR")
    petr = contas[contas["cnpj"] == PETROBRAS]
    primeiro_tri = petr[petr["referencia"] == date(2026, 3, 31)]
    assert set(primeiro_tri["versao"]) == {2}  # havia versões 1 e 2
    assert {dm.ACUMULADO, dm.ACUMULADO_ANTERIOR, dm.POSICAO} <= set(petr["periodo"])
    assert (
        petr.loc[petr["periodo"] == dm.ACUMULADO, "inicio"] == date(2026, 1, 1)
    ).all()
    assert documentos.groupby(["cnpj", "referencia"]).size().max() == 1


# --- cálculo ---------------------------------------------------------------------------------------
def test_doze_meses_somam_o_ano_e_o_acumulado(banco):
    contas = _empresa(banco, PETROBRAS).contas
    ttm, base, usados = fu.doze_meses(contas)
    dfp = fu._contas_em(contas, "DFP", date(2025, 12, 31), dm.EXERCICIO)
    acumulado = fu._contas_em(contas, "ITR", date(2026, 6, 30), dm.ACUMULADO)
    anterior = fu._contas_em(contas, "ITR", date(2026, 6, 30), dm.ACUMULADO_ANTERIOR)
    assert ttm["receita"] == pytest.approx(
        dfp["receita"] + acumulado["receita"] - anterior["receita"]
    )
    assert base == "12 meses até 30/06/2026"
    assert usados == [("DFP", date(2025, 12, 31)), ("ITR", date(2026, 6, 30))]


def test_indicadores_da_petrobras_pelas_formulas(banco):
    f = fu.calcular(
        _empresa(banco, PETROBRAS), preco=37.5, anos=1, roic_minimo=8, pl_maximo=30
    )
    ttm, _, _ = fu.doze_meses(_empresa(banco, PETROBRAS).contas)
    assert f["margem_ebit"].valor == pytest.approx(ttm["ebit"] / ttm["receita"])
    assert f["margem_liquida"].valor == pytest.approx(
        ttm["lucro_liquido"] / ttm["receita"]
    )
    assert f["p_l"].valor == pytest.approx(37.5 / f["lpa"].valor)
    assert not f.financeira and f.notas == []  # ações conferidas com o lucro por ação
    assert (
        f["roic"].base.startswith("12 meses até")
        and "balanço de 30/06/2026" in f["roic"].base
    )
    assert any("ROIC" in frase and "filtro de 8%" in frase for frase in f.filtros)
    assert set(f.documentos["documento"]) == {"DFP", "ITR"}


def test_banco_tem_nao_se_aplica_com_motivo_e_acoes_corrigidas(banco):
    f = fu.calcular(_empresa(banco, ITAU), preco=38.0)
    assert f.financeira
    for chave in ("margem_bruta", "margem_ebit", "roic", "divida_liquida"):
        assert not f[chave].disponivel and "bancos" in f[chave].motivo
    assert f["roe"].disponivel and f["lpa"].valor == pytest.approx(4.25, rel=0.02)
    assert any(
        "milhares" in nota for nota in f.notas
    )  # a CVM traz as ações do Itaú em milhares


def test_sem_preco_e_com_prejuizo_os_multiplos_explicam(banco):
    dados = _empresa(banco, WEG)
    assert "preço" in fu.calcular(dados, preco=None)["p_l"].motivo
    contas = dados.contas.copy()
    lucro = contas["conta"].isin(["lucro_liquido", "lucro_controladores"])
    contas.loc[lucro, "valor"] = -contas.loc[lucro, "valor"].abs()
    f = fu.calcular(replace(dados, contas=contas), preco=50.0)
    assert not f["p_l"].disponivel and "Prejuízo" in f["p_l"].motivo
    assert not f["conversao_de_caixa"].disponivel


def test_dy_valor_de_mercado_e_multiplos_da_firma_pelas_formulas(banco):
    """D3 mudada em 20/10/2026: DY e múltiplos de mercado com o preço do Yahoo."""
    dados = _empresa(banco, PETROBRAS)
    f = fu.calcular(dados, preco=37.5)
    ttm, base_12m, _ = fu.doze_meses(dados.contas)
    acoes = f["lucro"].valor / f["lpa"].valor
    mercado = 37.5 * acoes
    firma = mercado + f["divida_liquida"].valor
    assert f["valor_de_mercado"].valor == pytest.approx(mercado)
    assert f["valor_da_firma"].valor == pytest.approx(firma)
    assert f["dividend_yield"].valor == pytest.approx(
        abs(ttm["dividendos_pagos"]) / mercado
    )
    assert f["dividend_yield"].unidade == fu.FRACAO
    assert f["dividend_yield"].base == base_12m
    ebitda = ttm["ebit"] + ttm["depreciacao"]
    assert f["ev_ebitda"].valor == pytest.approx(firma / ebitda)
    assert f["ev_ebit"].valor == pytest.approx(firma / ttm["ebit"])
    assert f["p_receita"].valor == pytest.approx(mercado / ttm["receita"])


def test_multiplos_do_preco_sobre_resultado_caixa_e_ativo_pelas_formulas(banco):
    """P/EBITDA, P/EBIT, P/FCF e P/Ativo: valor de mercado ÷ a conta (linha 55 da fila)."""
    dados = _empresa(banco, PETROBRAS)
    f = fu.calcular(dados, preco=37.5)
    ttm, base_12m, _ = fu.doze_meses(dados.contas)
    saldo, _, _ = fu.balanco_mais_recente(dados.contas)
    mercado = f["valor_de_mercado"].valor
    assert f["p_ebitda"].valor == pytest.approx(
        mercado / (ttm["ebit"] + ttm["depreciacao"])
    )
    assert f["p_ebit"].valor == pytest.approx(mercado / ttm["ebit"])
    assert f["p_fcf"].valor == pytest.approx(mercado / (ttm["fco"] - abs(ttm["capex"])))
    assert f["p_ativo"].valor == pytest.approx(mercado / saldo["ativo_total"])
    assert f["p_ativo"].base == f["valor_de_mercado"].base  # só o balanço
    assert f["p_fcf"].base.startswith(base_12m)
    for chave in ("p_ebitda", "p_ebit", "p_fcf", "p_ativo"):
        assert f[chave].unidade == fu.VEZES and chave in fu.FORMULAS


def test_dy_de_5_anos_e_a_media_dos_pagos_nos_exercicios_sobre_o_mercado_de_hoje(banco):
    dados = _empresa(banco, WEG)
    tabela = fu.anuais(dados.contas)
    f = fu.calcular(dados, preco=50.0, anos=2)  # a amostra tem só 2 exercícios
    media = tabela["dividendos_pagos"].abs().iloc[-2:].mean()
    assert f["dividend_yield_medio"].valor == pytest.approx(
        media / f["valor_de_mercado"].valor
    )
    assert f["dividend_yield_medio"].unidade == fu.FRACAO
    assert f["dividend_yield_medio"].base == "DFP de 2024 a 2025"
    curto = fu.calcular(dados, preco=50.0)["dividend_yield_medio"]
    assert not curto.disponivel and "Só há 2 exercícios" in curto.motivo


def test_dy_de_5_anos_sem_a_linha_num_ano_explica(banco):
    dados = _empresa(banco, WEG)
    contas = dados.contas
    sem_2024 = ~(
        (contas["conta"] == "dividendos_pagos")
        & (contas["documento"] == "DFP")
        & (contas["referencia"].map(lambda d: d.year) == 2024)
    )
    f = fu.calcular(replace(dados, contas=contas[sem_2024]), preco=50.0, anos=2)
    medio = f["dividend_yield_medio"]
    assert not medio.disponivel and "2024" in medio.motivo


def test_dy_de_5_anos_nao_olha_o_futuro(banco):
    """Cortar o último exercício não muda a média dos anteriores: só entram DFPs já publicadas."""
    dados = _empresa(banco, WEG)
    contas = dados.contas
    ate_2024 = contas[contas["referencia"].map(lambda d: d.year) <= 2024]
    f = fu.calcular(replace(dados, contas=ate_2024), preco=50.0, anos=1)
    pagos_2024 = abs(fu.anuais(ate_2024)["dividendos_pagos"].iloc[-1])
    assert f["dividend_yield_medio"].valor == pytest.approx(
        pagos_2024 / f["valor_de_mercado"].valor
    )
    assert f["dividend_yield_medio"].base == "DFP de 2024"


def test_banco_tem_dy_mas_nao_os_multiplos_da_firma(banco):
    f = fu.calcular(_empresa(banco, ITAU), preco=38.0)
    assert f["dividend_yield"].disponivel and f["valor_de_mercado"].disponivel
    for chave in (
        "valor_da_firma", "ev_ebitda", "ev_ebit", "p_receita", "p_ebitda", "p_ebit", "p_fcf",
    ):  # fmt: skip
        assert not f[chave].disponivel and "bancos" in f[chave].motivo
    assert f["p_ativo"].disponivel  # o ativo total existe em qualquer balanço


def test_sem_preco_os_de_mercado_explicam(banco):
    f = fu.calcular(_empresa(banco, WEG), preco=None)
    for chave in fu.DE_MERCADO:
        assert not f[chave].disponivel and "preço" in f[chave].motivo


def test_ebitda_negativo_ou_sem_dividendos_explicam(banco):
    dados = _empresa(banco, WEG)
    contas = dados.contas.copy()
    contas.loc[contas["conta"] == "ebit", "valor"] = -1e12
    contas = contas[contas["conta"] != "dividendos_pagos"]
    f = fu.calcular(replace(dados, contas=contas), preco=50.0)
    assert not f["ev_ebitda"].disponivel and "EBITDA" in f["ev_ebitda"].motivo
    assert not f["ev_ebit"].disponivel and "EBIT" in f["ev_ebit"].motivo
    assert not f["p_ebitda"].disponivel and "EBITDA" in f["p_ebitda"].motivo
    assert not f["p_ebit"].disponivel and "EBIT" in f["p_ebit"].motivo
    # sem a linha no caixa não dá para saber se não pagou ou se a linha tem outro nome
    assert not f["dividend_yield"].disponivel
    assert "dividendos" in f["dividend_yield"].motivo


def test_caixa_livre_negativo_explica_o_p_fcf(banco):
    dados = _empresa(banco, WEG)
    contas = dados.contas.copy()
    contas.loc[contas["conta"] == "capex", "valor"] = -1e13
    f = fu.calcular(replace(dados, contas=contas), preco=50.0)
    assert not f["p_fcf"].disponivel and "Caixa livre" in f["p_fcf"].motivo


def test_crescimento_pede_anos_suficientes(banco):
    dados = _empresa(banco, WEG)
    curto = fu.calcular(dados, preco=50.0, anos=5)["crescimento_receita"]
    assert not curto.disponivel and "Só há 2 anos" in curto.motivo
    um_ano = fu.calcular(dados, preco=50.0, anos=1)["crescimento_receita"]
    tabela = fu.anuais(dados.contas)
    assert um_ano.valor == pytest.approx(
        tabela["receita"].iloc[-1] / tabela["receita"].iloc[-2] - 1
    )


def test_quantidade_de_acoes_que_nao_bate_fica_indisponivel(banco):
    dados = _empresa(banco, PETROBRAS)
    contas = dados.contas.copy()
    contas.loc[contas["conta"] == "acoes_total", "valor"] *= 37  # nem 1×, nem 1.000×
    f = fu.calcular(replace(dados, contas=contas), preco=37.5)
    assert not f["lpa"].disponivel and "não bate" in f["lpa"].motivo


# --- banco e coleta ----------------------------------------------------------------------------------
def test_gravar_de_novo_nao_muda_nada_e_versao_nova_substitui(banco):
    contas, documentos = _ler("itr_cia_aberta_2026.zip", "ITR")
    with banco.begin() as c:
        assert repo.gravar_demonstracoes(c, contas, documentos) == 0
        so_um = documentos[(documentos["cnpj"] == WEG)].head(1).assign(versao=9)
        contas_dele = contas[
            (contas["cnpj"] == WEG)
            & (contas["referencia"] == so_um["referencia"].iloc[0])
        ]
        assert repo.gravar_demonstracoes(c, contas_dele.assign(valor=1.0), so_um) == 1
        valores = (
            c.execute(
                sa.text(
                    "select distinct valor from demonstracoes where cnpj = :c and referencia = :r"
                ),
                {"c": WEG, "r": str(so_um["referencia"].iloc[0])},
            )
            .scalars()
            .all()
        )
        assert valores == [1.0]  # o documento foi trocado inteiro
        c.rollback()


def test_coleta_sem_internet_e_arquivo_que_ainda_nao_existe(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 's.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)

    def baixar_falso(endereco: str) -> bytes | None:
        if endereco.endswith("cad_cia_aberta.csv"):
            return (PASTA / "cad_cia_aberta.csv").read_bytes()
        nome = endereco.rsplit("/", 1)[-1]
        return (PASTA / nome).read_bytes() if (PASTA / nome).exists() else None  # 404

    monkeypatch.setattr(atualizar_fundamentos, "baixar", baixar_falso)
    assert atualizar_fundamentos.main(["--anos", "3"]) == 0
    with criar_engine(url).connect() as c:
        assert (
            c.execute(
                sa.text("select count(distinct cnpj) from documentos_financeiros")
            ).scalar()
            == 4
        )
        assert c.execute(sa.text("select count(*) from setores_cvm")).scalar() == 4


def test_migracao_0010_vai_e_volta(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}"
    migrar_para("head", url=url)
    assert "demonstracoes" in sa.inspect(criar_engine(url)).get_table_names()
    desfazer_ate("0009", url=url)
    assert "demonstracoes" not in sa.inspect(criar_engine(url)).get_table_names()
    migrar_para("head", url=url)


@pytest.mark.parametrize(
    ("descricao", "capex"),
    [
        ("Imobilizado", True),
        ("Intangível", True),
        ("Aquisição de ativo imobilizado", True),
        ("Aquisição de bens do ativo imobilizado", True),
        ("Aquisições de bens do ativo imobilizado e intangível", True),
        ("Compras de imobilizado", True),
        ("Adições ao ativo imobilizado", True),
        ("No intangível", True),
        ("Venda de imobilizado", False),
        ("Recebimento pela venda de ativo imobilizado", False),
        ("Alienação de imobilizado e intangível", False),
        ("Baixa de imobilizado", False),
        ("Aplicação financeira de longo prazo", False),
    ],
)
def test_capex_pela_descricao_real_das_empresas(descricao, capex):
    """Descrições do DFP 2025 real: a mesma compra de imobilizado aparece escrita de vários jeitos."""
    assert dm.e_capex(pd.Series([dm._sem_acento(descricao)])).iloc[0] == capex


def test_coleta_acrescenta_contas_novas_sem_reapresentacao(tmp_path, monkeypatch):
    """Documento guardado antes das contas novas: a coleta seguinte acrescenta, sem versão falsa."""
    from src.banco.modelo import demonstracoes_versoes

    url = f"sqlite:///{(tmp_path / 'n.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)

    def baixar_falso(endereco: str) -> bytes | None:
        nome = endereco.rsplit("/", 1)[-1]
        return (PASTA / nome).read_bytes() if (PASTA / nome).exists() else None

    monkeypatch.setattr(atualizar_fundamentos, "baixar", baixar_falso)
    ler_de_verdade = dm.ler_demonstracoes

    def leitor_antigo(conteudo, documento):
        contas, documentos = ler_de_verdade(conteudo, documento)
        return contas[~contas["conta"].isin({"estoques", "capex"})], documentos

    monkeypatch.setattr(dm, "ler_demonstracoes", leitor_antigo)
    assert atualizar_fundamentos.main(["--anos", "2"]) == 0
    monkeypatch.setattr(dm, "ler_demonstracoes", ler_de_verdade)
    assert atualizar_fundamentos.main(["--anos", "2"]) == 0
    with criar_engine(url).connect() as c:
        contas = {
            r[0] for r in c.execute(sa.text("select distinct conta from demonstracoes"))
        }
        substituidas = c.execute(
            sa.select(sa.func.count()).where(
                demonstracoes_versoes.c.substituido_em.is_not(None)
            )
        ).scalar()
    assert {"estoques", "capex"} <= contas
    assert substituidas == 0


def test_acoes_zeradas_no_documento_nao_derrubam_o_calculo():
    """Regressão (13/10/2026): ações em circulação iguais a zero davam divisão por zero no LPA."""
    from src.banco.demonstracoes import DadosDaEmpresa

    referencia = date(2025, 12, 31)
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
            "inicio": date(2025, 1, 1),
            "conta": c,
            "valor": v,
        }
        for c, v in (("receita", 1000.0), ("ebit", 150.0), ("lucro_liquido", 100.0))
    ] + [
        {**comum, "periodo": dm.POSICAO, "inicio": None, "conta": c, "valor": v}
        for c, v in (("patrimonio_liquido", 500.0), ("acoes_total", 0.0))
    ]
    dados = DadosDaEmpresa(pd.DataFrame(linhas), pd.DataFrame(), "Energia Elétrica")
    resultado = fu.calcular(dados, 10.0)
    assert resultado["lpa"].valor is None and "zerada" in resultado["lpa"].motivo
