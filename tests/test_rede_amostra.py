"""Precisão da resolução medida por amostra conferida (ADR 0077, item 4; plano, tarefa 2.7).

200 identificadores por regra, sorteados com semente fixa; Claude confere os 200 contra os originais e o
Tiago confere 20 por regra da mesma amostra (Q2 do plano, 15/10/2026). Corte: ≥ 99% nas regras por
código. A cobertura por valor (meta 95%) diz quanto do valor das carteiras dos fundos chega a uma
entidade.
"""

import pandas as pd
import pytest

from base.rede import amostra, resolucao


def _identificadores(por_regra: int = 300) -> pd.DataFrame:
    linhas = [
        {
            "id_entidade": f"E{regra}{n:05d}",
            "sistema": f"s{regra}",
            "valor": f"{n:05d}",
            "desde": pd.NaT,
            "regra": regra,
        }
        for regra, _ in resolucao.REGRAS
        for n in range(por_regra)
    ]
    return pd.DataFrame(linhas)


def test_amostra_tem_semente_fixa():
    identificadores = _identificadores()
    primeira = amostra.sortear(identificadores)
    assert primeira.equals(
        amostra.sortear(identificadores.iloc[::-1])
    )  # nem a ordem muda
    assert primeira.groupby("regra").size().to_dict() == {
        regra: amostra.POR_REGRA for regra, _ in resolucao.REGRAS
    }


def test_regra_com_menos_de_200_entra_inteira():
    poucos = _identificadores(por_regra=30)
    assert len(amostra.sortear(poucos)) == 30 * len(resolucao.REGRAS)


def test_tiago_confere_20_por_regra_da_mesma_amostra():
    sorteada = amostra.sortear(_identificadores())
    do_tiago = amostra.para_o_tiago(sorteada)
    assert do_tiago.groupby("regra").size().eq(amostra.DO_TIAGO_POR_REGRA).all()
    chave = ["regra", "id_entidade", "sistema", "valor"]
    assert len(do_tiago.merge(sorteada, on=chave)) == len(do_tiago)


def _conferida(certos: int, errados: int, regra: int = 4) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "regra": [regra] * (certos + errados),
            "conferencia_claude": [amostra.CERTO] * certos + [amostra.ERRADO] * errados,
            "conferencia_tiago": [""] * (certos + errados),
        }
    )


def test_precisao_por_regra():
    assert amostra.precisao(_conferida(198, 2)) == {4: 0.99}
    # o Tiago desempata: o que ele marcou errado conta como errado
    tabela = _conferida(200, 0).assign(conferencia_tiago=[amostra.ERRADO] + [""] * 199)
    assert amostra.precisao(tabela) == {4: 0.995}


def test_corte_de_precisao():
    assert amostra.regras_abaixo_do_corte(_conferida(198, 2)) == []
    assert amostra.regras_abaixo_do_corte(_conferida(197, 3)) == [4]


def test_precisao_da_amostra_conferida():
    """A tabela conferida do repositório: toda regra conferida passa no corte (menos quebra)."""
    conferida = amostra.tabela_conferida()
    assert set(conferida.columns) >= set(amostra.COLUNAS_DA_CONFERIDA)
    assert set(conferida["conferencia_claude"]) <= {amostra.CERTO, amostra.ERRADO}
    assert amostra.regras_abaixo_do_corte(conferida) == []


def test_cobertura_por_valor_anotada():
    """Quanto do valor das carteiras tem emissor ligado a uma entidade (meta 95%)."""
    posicoes = pd.DataFrame(
        {"emissor": ["PETR", "VALE", "XPTO"], "valor": [60.0, 36.0, 4.0]}
    )
    identificadores = pd.DataFrame(
        {
            "sistema": ["emissor", "emissor", "ticker"],
            "valor": ["PETR", "VALE", "XPTO3"],
        }
    )
    assert amostra.cobertura_por_valor(posicoes, identificadores) == pytest.approx(0.96)
    assert amostra.META_DE_COBERTURA == 0.95
