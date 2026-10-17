"""Achado 5b do Codex: o índice da comparação vem na mesma moeda do ativo ("Converter para reais")."""

from types import SimpleNamespace

import pandas as pd

from telas.research import parametros


def test_cache_do_indice_separa_dolar_de_reais(monkeypatch):
    def falso(ticker, periodo, em_reais):
        return pd.DataFrame({"Close": [5.0 if em_reais else 1.0]})

    monkeypatch.setattr(parametros, "carregar_dados_de", falso)
    monkeypatch.setattr(
        parametros.st, "session_state", {"usar_exemplo": True, "em_reais": False}
    )
    parametros._fechamento_do_indice.clear()
    vistos = []
    monkeypatch.setattr(
        parametros.research_analise,
        "analisar_ativo",
        lambda ticker, dados, resolucao, cdi, benchmark: vistos.append(
            benchmark.iloc[0]
        ),
    )
    c = SimpleNamespace(ticker="AAPL", dados=None, periodo="1y")
    resolucao = {"quant.benchmark": "^GSPC", "quant.taxa_livre_de_risco": "zero"}
    parametros._analisar_com(c, resolucao)
    parametros.st.session_state["em_reais"] = (
        True  # a pessoa marca "Converter para reais"
    )
    parametros._analisar_com(c, resolucao)
    assert vistos == [1.0, 5.0]
