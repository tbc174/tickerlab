"""A página Carteira da B3 dentro do app (modo local): a planilha lida só na memória."""

import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from src import analise_da_carteira as ac
from src import dividendos_e_custo as dc
from src import proventos_a_receber as par
from src import resultado_por_mes as rpm
from src.banco.modelo import metadata
from tests.ajudantes_da_conta import ir_para


def _abrir_com_o_exemplo() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    # o exemplo já ligado na primeira vez: o AppTest não aceita reenviar um campo de arquivo
    # que já apareceu (e a página tem dois)
    app.session_state["carteira_b3_exemplo"] = True
    return ir_para(app, "carteira_b3")


def _linhas_no_banco(banco) -> int:
    with banco.connect() as conexao:
        return sum(
            conexao.execute(sa.select(sa.func.count()).select_from(t)).scalar_one()
            for t in metadata.sorted_tables
            if sa.inspect(banco).has_table(t.name)
        )


def test_sem_planilha_explica_como_baixar():
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "carteira_b3")
    assert not app.exception
    assert "Área do Investidor" in " ".join(m.value for m in app.markdown)


def test_carteira_de_exemplo_mostra_concentracao_raio_x_e_rebalanceamento():
    app = _abrir_com_o_exemplo()
    assert not app.exception and not app.error
    rotulos = {m.label for m in app.metric}
    assert {"Maior posição", "3 maiores juntas", "Número efetivo de ativos"} <= rotulos
    textos = " ".join(c.value for c in app.caption)
    assert ac.NOTA_DA_MOEDA in textos
    assert (
        ac.AVISO_DO_REBALANCEAMENTO in " ".join(w.value for w in app.warning) + textos
    )
    assert app.get("plotly_chart")  # a carteira no passado contra o Ibovespa


def test_pagina_nao_guarda_nada_da_planilha(banco):
    antes = _linhas_no_banco(banco)
    app = _abrir_com_o_exemplo()
    assert not app.exception
    assert _linhas_no_banco(banco) == antes


def _abrir_com_a_movimentacao_de_exemplo(com_a_posicao: bool) -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    app.session_state["carteira_b3_exemplo"] = com_a_posicao
    app.session_state["carteira_b3_movimentacao_exemplo"] = True
    return ir_para(app, "carteira_b3")


def _tabela_com(app: AppTest, coluna: str):
    (tabela,) = [d.value for d in app.dataframe if coluna in d.value.columns]
    return tabela.set_index("Ativo")


def test_movimentacao_de_exemplo_mostra_proventos_e_custo_medio():
    app = _abrir_com_a_movimentacao_de_exemplo(com_a_posicao=False)
    assert not app.exception and not app.error
    assert {"Proventos no período", "Últimos 12 meses"} <= {m.label for m in app.metric}
    textos = " ".join(c.value for c in app.caption)
    assert dc.NOTA_DOS_PROVENTOS in textos and dc.NOTA_DO_CUSTO in textos
    assert dc.SEM_A_POSICAO in " ".join(i.value for i in app.info)
    custo = _tabela_com(app, "Preço médio (R$)")
    assert custo.loc["PETR4", "Preço médio (R$)"] == 33.0
    assert "começa depois" in custo.loc["WEGE3", "Observação"]
    assert "HGLG11" not in custo.index  # vendido inteiro: não tem custo hoje
    proventos = _tabela_com(app, "Total (R$)")
    # 505 de proventos + 3,50 da taxa do aluguel (linha "Empréstimo" com valor)
    assert proventos.loc["PETR4", "Total (R$)"] == 508.5
    assert proventos.loc["PETR4", "Aluguel (R$)"] == 3.5


def test_movimentacao_com_a_posicao_mostra_o_ganho_ou_a_perda():
    app = _abrir_com_a_movimentacao_de_exemplo(com_a_posicao=True)
    assert not app.exception and not app.error
    tabela = _tabela_com(app, "Ganho ou perda (R$)")
    # PETR4: 150 ações valem R$ 8.400 na posição de exemplo; custaram 150 × R$ 33
    assert tabela.loc["PETR4", "Ganho ou perda (R$)"] == 8400 - 150 * 33
    assert tabela.loc["WEGE3", "Ganho ou perda (R$)"] is None or (
        tabela.loc["WEGE3", "Ganho ou perda (R$)"]
        != tabela.loc["WEGE3", "Ganho ou perda (R$)"]
    )  # sem número (None ou NaN)


def test_pagina_nao_guarda_nada_da_movimentacao(banco):
    antes = _linhas_no_banco(banco)
    app = _abrir_com_a_movimentacao_de_exemplo(com_a_posicao=True)
    assert not app.exception
    assert _linhas_no_banco(banco) == antes


def _abrir_com_os_proventos_de_exemplo() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    app.session_state["carteira_b3_proventos_exemplo"] = True
    return ir_para(app, "carteira_b3")


def test_proventos_a_receber_de_exemplo_mostram_data_valor_e_total():
    app = _abrir_com_os_proventos_de_exemplo()
    assert not app.exception and not app.error
    assert "Total a receber" in {m.label for m in app.metric}
    tabela = _tabela_com(app, "Data prevista")
    assert list(tabela.columns) == [
        "Provento",
        "Data prevista",
        "Quantidade",
        "Valor (R$)",
    ]
    assert "sem data" in set(tabela["Data prevista"])  # o JCP da PETR4 ainda sem dia
    assert par.NOTA_DOS_PROVENTOS_A_RECEBER in " ".join(c.value for c in app.caption)


def test_sem_os_proventos_a_receber_explica_como_baixar():
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "carteira_b3")
    assert not app.exception
    textos = " ".join(m.value for m in app.markdown)
    assert "Proventos a receber" in textos


def test_pagina_nao_guarda_nada_dos_proventos_a_receber(banco):
    antes = _linhas_no_banco(banco)
    app = _abrir_com_os_proventos_de_exemplo()
    assert not app.exception
    assert _linhas_no_banco(banco) == antes


def _abrir_com_a_negociacao_de_exemplo(com_a_movimentacao: bool) -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    app.session_state["carteira_b3_movimentacao_exemplo"] = com_a_movimentacao
    app.session_state["carteira_b3_negociacao_exemplo"] = True
    return ir_para(app, "carteira_b3")


def test_negociacao_de_exemplo_mostra_o_resultado_por_mes():
    app = _abrir_com_a_negociacao_de_exemplo(com_a_movimentacao=True)
    assert not app.exception and not app.error
    assert "Resultado no período" in {m.label for m in app.metric}
    (tabela,) = [d.value for d in app.dataframe if "Mês" in d.value.columns]
    assert list(tabela["Mês"]) == ["04/2026", "03/2026", "02/2026", "01/2026"]
    assert {
        "Ações (R$)",
        "Day trade (R$)",
        "FIIs (R$)",
        "Futuros (R$)",
        "Total (R$)",
        "Vendas de ações (R$)",
    } <= set(tabela.columns)
    assert rpm.NOTA_DO_RESULTADO in " ".join(c.value for c in app.caption)
    (sem,) = [d.value for d in app.dataframe if "Por quê" in d.value.columns]
    assert list(sem["Ativo"]) == ["WEGE3"]


def test_negociacao_sem_a_movimentacao_avisa_e_poe_o_fii_em_outros():
    app = _abrir_com_a_negociacao_de_exemplo(com_a_movimentacao=False)
    assert not app.exception
    avisos = " ".join(w.value for w in app.warning)
    assert rpm.AVISO_SEM_A_MOVIMENTACAO in avisos
    assert "HGLG11" in avisos  # sem o nome, não dá para saber se é FII


def test_pagina_nao_guarda_nada_da_negociacao(banco):
    antes = _linhas_no_banco(banco)
    app = _abrir_com_a_negociacao_de_exemplo(com_a_movimentacao=True)
    assert not app.exception
    assert _linhas_no_banco(banco) == antes
