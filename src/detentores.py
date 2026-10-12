"""Quem tem cada ação (Research R3): o formato comum dos fundos da CVM e dos gestores da SEC.

- `src/fundos_cvm.py`: carteira mensal dos fundos brasileiros (CDA), com posições compradas,
  vendidas (aposta na queda) e emprestadas.
- `src/fundos_sec.py`: o 13F trimestral dos grandes gestores dos EUA (só posições compradas).

As duas viram um **resumo por competência e ação** (quantos detentores, quanto têm...) e a lista
dos **maiores detentores**. A comparação entre duas competências mostra quem chegou e quem saiu.

**Cobertura:** o número de fundos que aparecem com ações muda muito de um mês para o outro, sem
que ninguém tenha comprado ou vendido: na CVM, um fundo pode manter posições em sigilo por até 90
dias (em 2026, junho tinha 6.653 fundos com ações; julho e agosto, ~3.400) e o mês mais recente
ainda está chegando. Por isso guardamos quantos fundos informaram (`informantes`), mostramos a
**fatia** dos informantes que tem a ação e só comparamos competências de cobertura parecida.
"""

from datetime import date
from itertools import pairwise

import pandas as pd

COMPRADO, VENDIDO, EMPRESTADO = "comprado", "vendido", "emprestado"
MAIORES = 10  # quantos detentores guardar por ação, tipo e competência
COBERTURA_PARECIDA = (
    0.85  # duas competências são comparáveis se a menor cobertura for ≥ 85%
)
COLUNAS_DO_RESUMO = [
    "fonte", "competencia", "codigo", "detentores", "valor", "quantidade", "vendidos",
    "valor_vendido", "valor_emprestado", "compras_no_mes", "vendas_no_mes",
]  # fmt: skip
COLUNAS_DOS_MAIORES = [
    "fonte", "competencia", "codigo", "tipo", "posicao", "nome", "documento", "valor",
    "quantidade",
]  # fmt: skip


def comparar(resumo: pd.DataFrame, atual: date, anterior: date) -> pd.DataFrame:
    """Por ação: detentores e valores na competência atual e a variação desde a anterior.

    Colunas: codigo, detentores, detentores_antes, variacao, quantidade, quantidade_antes,
    variacao_quantidade (%), vendidos, valor_vendido, fatia_vendida (vendido ÷ comprado).
    A variação da **quantidade** de ações (e não do valor) separa compra e venda de verdade do
    efeito da alta ou da queda do preço.
    """
    agora = resumo[resumo["competencia"] == atual].set_index("codigo")
    antes = resumo[resumo["competencia"] == anterior].set_index("codigo")
    tabela = pd.DataFrame(
        {
            "detentores": agora["detentores"],
            "detentores_antes": antes["detentores"].reindex(agora.index),
            "quantidade": agora["quantidade"],
            "quantidade_antes": antes["quantidade"].reindex(agora.index),
            "vendidos": agora["vendidos"],
            "valor_vendido": agora["valor_vendido"],
            "valor": agora["valor"],
        }
    )
    tabela["variacao"] = tabela["detentores"] - tabela["detentores_antes"]
    tabela["variacao_quantidade"] = (
        tabela["quantidade"] / tabela["quantidade_antes"] - 1
    )
    tabela["fatia_vendida"] = (tabela["valor_vendido"] / tabela["valor"]).where(
        tabela["valor"] > 0
    )
    return tabela.reset_index()


def informantes(posicoes: pd.DataFrame) -> int:
    """Quantos fundos (ou gestores) aparecem com alguma posição na competência."""
    return int(posicoes["cnpj_fundo"].nunique()) if not posicoes.empty else 0


def _parecidas(uma: int, outra: int) -> bool:
    maior = max(uma, outra)
    return maior > 0 and min(uma, outra) / maior >= COBERTURA_PARECIDA


def competencias_utilizaveis(cobertura: dict[date, int]) -> list[date]:
    """As competências da mais nova para a mais velha, sem as recentes ainda incompletas (com
    cobertura bem menor que a da competência anterior)."""
    datas = sorted(cobertura, reverse=True)
    while (
        len(datas) > 1
        and cobertura[datas[0]] < COBERTURA_PARECIDA * cobertura[datas[1]]
    ):
        datas = datas[1:]
    return datas


def par_comparavel(cobertura: dict[date, int]) -> tuple[date, date] | None:
    """(atual, anterior): as duas competências seguidas mais recentes com cobertura parecida."""
    datas = competencias_utilizaveis(cobertura)
    for atual, anterior in pairwise(datas):
        if _parecidas(cobertura[atual], cobertura[anterior]):
            return atual, anterior
    return None


def aviso_de_cobertura(
    cobertura: dict[date, int], competencia: date, quem: str
) -> str | None:
    """Frase para quando a competência mostrada tem bem menos informantes que a mais completa
    guardada (sigilo de 90 dias ainda valendo): a contagem crua fica menor sem ninguém vender."""
    maior = max(cobertura.values())
    if cobertura[competencia] >= COBERTURA_PARECIDA * maior:
        return None
    mes_da_maior = max(d for d, v in cobertura.items() if v == maior)
    return (
        f"Base: {cobertura[competencia]} {quem} informaram posições em {competencia:%m/%Y}, "
        f"contra {maior} em {mes_da_maior:%m/%Y} (mês mais antigo, já sem sigilo). Muitos ainda "
        "mantêm as posições em sigilo: a contagem fica menor sem que ninguém tenha vendido. "
        "Compare pela fatia."
    )
