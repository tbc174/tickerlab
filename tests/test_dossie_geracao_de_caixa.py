"""A seção de geração de caixa no dossiê (série T1 na ficha): EBITDA, capex e FCF de cada DFP.

As contas saem de `base/indicadores_de_caixa.py`; aqui se confere o que a ficha faz com elas: o consolidado
na frente do individual, só o que já era público no dia da ficha (a reapresentação conhecida entra, a
futura não), número vazio quando falta a linha (nada inventado) e a margem sobre a receita da mesma DRE.
"""

import pandas as pd

from base import dossie

D = pd.Timestamp
HOJE = D("2026-10-17")
CNPJ = "02.429.144/0001-93"
MILHAO = 1_000_000.0
RECEITA = ("DRE", "3.01", "Receita de Venda de Bens e/ou Serviços")
EBIT = ("DRE", "3.05", "Resultado Antes do Resultado Financeiro e dos Tributos")
DA = ("DVA", "7.04.01", "Depreciação, Amortização e Exaustão")
CAIXA = ("DFC_MI", "6.01", "Caixa Líquido Atividades Operacionais")
COMPRA = ("DFC_MI", "6.02.01", "Aquisição de Imobilizado")


def _linha(
    exercicio: int,
    conta: tuple[str, str, str],
    milhoes: float,
    divulgado_em: str,
    grupo: str = "con",
) -> dict[str, object]:
    demonstracao, numero, descricao = conta
    return {
        "cnpj": CNPJ,
        "grupo": grupo,
        "demonstracao": demonstracao,
        "documento": "DFP",
        "conta": numero,
        "descricao": descricao,
        "inicio": D(f"{exercicio}-01-01"),
        "fim": D(f"{exercicio}-12-31"),
        "valor": milhoes * MILHAO,
        "divulgado_em": D(divulgado_em),
    }


def _exercicio(
    ano: int, numeros: tuple[float, float, float, float, float], divulgado_em: str
) -> list[dict[str, object]]:
    contas = (RECEITA, EBIT, DA, CAIXA, COMPRA)
    return [
        _linha(ano, conta, valor, divulgado_em)
        for conta, valor in zip(contas, numeros, strict=True)
    ]


def _como_era() -> pd.DataFrame:
    linhas = [
        # receita, EBIT, D&A (negativa na DVA), caixa operacional, compra de imobilizado (saída)
        *_exercicio(2024, (9_000, 1_500, -400, 1_800, -700), "2025-03-20"),
        *_exercicio(2025, (10_000, 2_000, -500, 2_200, -900), "2026-03-20"),
        # a DFP de 2025 reapresentou o EBIT de 2024: vale o novo, já público no dia da ficha
        _linha(2024, EBIT, 1_600, "2026-03-20"),
        # o individual não entra quando há consolidado
        _linha(2025, EBIT, 99_999, "2026-03-20", grupo="ind"),
        # o que só sai depois do dia da ficha não entra (nem a DFP nova, nem a reapresentação de 2025)
        *_exercicio(2026, (11_000, 2_500, -600, 2_400, -1_000), "2027-03-19"),
        _linha(2025, EBIT, 3_000, "2027-03-19"),
    ]
    return pd.DataFrame(linhas)


def _itens(secao: dict) -> dict[str, dict]:
    return {item["chave"]: item for item in secao["itens"]}


def test_geracao_de_caixa_traz_ebitda_capex_e_fcf_da_ultima_dfp() -> None:
    secao = dossie.secao_geracao_de_caixa(_como_era(), HOJE)
    assert secao is not None
    itens = _itens(secao)
    assert itens["ebitda"]["valor"] == 2_500 * MILHAO
    assert itens["capex"]["valor"] == 900 * MILHAO
    assert itens["fcf"]["valor"] == 1_300 * MILHAO
    assert {i["base"] for i in itens.values()} == {"2025-12-31"}
    assert {i["unidade"] for i in itens.values()} == {"R$"}


def test_tabela_por_exercicio_usa_o_que_era_publico_no_dia() -> None:
    secao = dossie.secao_geracao_de_caixa(_como_era(), HOJE)
    assert secao is not None
    linhas = secao["tabelas"]["caixa_por_exercicio"]
    assert [linha["exercicio"] for linha in linhas] == [2025, 2024]
    ano_2025, ano_2024 = linhas
    # 2024 com o EBIT reapresentado (1.600 + 400 de D&A); 2025 sem a reapresentação futura
    assert ano_2024["ebitda"] == 2_000 * MILHAO
    assert ano_2025["ebitda"] == 2_500 * MILHAO
    assert ano_2025["margem_ebitda"] == 0.25
    assert ano_2024["fcf"] == 1_100 * MILHAO
    assert ano_2025["divulgado_em"] == "2026-03-20"


def test_cortar_o_futuro_nao_muda_o_passado() -> None:
    como_era = _como_era()
    passado = como_era[como_era["divulgado_em"] <= HOJE]
    assert dossie.secao_geracao_de_caixa(
        passado, HOJE
    ) == dossie.secao_geracao_de_caixa(como_era, HOJE)


def test_sem_a_linha_o_numero_fica_vazio_e_nao_vira_item() -> None:
    # num banco, a 3.05 é o resultado antes dos tributos: sem EBIT, sem EBITDA (nada inventado)
    como_era = _como_era()
    banco = como_era.assign(
        descricao=como_era["descricao"].where(
            como_era["conta"] != "3.05", "Resultado Antes dos Tributos sobre o Lucro"
        )
    )
    secao = dossie.secao_geracao_de_caixa(banco, HOJE)
    assert secao is not None
    assert "ebitda" not in _itens(secao)
    assert "fcf" in _itens(secao)
    assert secao["tabelas"]["caixa_por_exercicio"][0]["ebitda"] is None


def test_sem_dfc_a_secao_nao_sai() -> None:
    # a base de hoje ainda não tem a DFC (a T1 espera a remontagem): a ficha diz "ainda sem dado"
    so_a_dre = _como_era().query("demonstracao == 'DRE'")
    assert dossie.secao_geracao_de_caixa(so_a_dre, HOJE) is None
    assert dossie.secao_geracao_de_caixa(pd.DataFrame(), HOJE) is None


def test_geracao_de_caixa_esta_no_registro_com_limites() -> None:
    registro = {s.chave: s for s in dossie.SECOES}["geracao_de_caixa"]
    assert registro.tabelas == ("demonstracoes_como_era",)
    assert "EBITDA" in dossie.LIMITES["geracao_de_caixa"]
