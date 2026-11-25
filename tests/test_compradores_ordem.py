"""A ordem da lista de quem já se mexeu no setor (linha 1044): primeiro quem mais comprou de terceiros.

Antes a lista ordenava por número de sinais, depois por entradas, e desempatava pela prova mais nova. Isso botava no
topo a companhia aberta com uma controlada e uma entrada qualquer e empurrava para fora dos 50 quem comprou várias
vezes, e o desempate pela data mais recente fazia o negócio de ontem subir o comprador e tirar quem comprou há mais
tempo. Agora: mais entradas de terceiros (fundador e mesmo grupo já ficaram de fora delas), depois mais sinais, depois
mais provas, e a raiz no fim, sem olhar a data. Testa a `_Lista` direto, com tabelinhas de mentira.
"""

from datetime import date

import pandas as pd

from src.api_externa.conjuntos import compradores

DIA = date(2026, 11, 10)
MUITAS, UMA_E_CONTROLADA, UMA_VELHA, UMA_NOVA, SO_CONTROLADA = (
    "40000001",
    "40000002",
    "40000003",
    "40000004",
    "40000005",
)
ALVOS = [f"50{n:06d}" for n in range(6)]


def _lista() -> compradores._Lista:
    setor = pd.DataFrame({"raiz": ALVOS, "uf": ["SP"] * len(ALVOS)})
    lista = compradores._Lista(setor)
    linhas = [
        # comprador, alvo, data da entrada
        (MUITAS, ALVOS[0], "2023-06-01"),
        (MUITAS, ALVOS[1], "2023-07-01"),
        (MUITAS, ALVOS[2], "2023-08-01"),
        (UMA_E_CONTROLADA, ALVOS[3], "2026-09-01"),
        (UMA_VELHA, ALVOS[4], "2023-06-01"),
        (UMA_NOVA, ALVOS[5], "2026-10-01"),
    ]
    entradas = pd.DataFrame(
        {
            "alvo": [a for _, a, _ in linhas],
            "comprador": [c for c, _, _ in linhas],
            "data_entrada": pd.to_datetime([d for _, _, d in linhas]).date,
            "publico_em": [DIA] * len(linhas),
        }
    )
    lista.anotar_entradas(entradas, pd.DataFrame({"raiz": [], "socia": []}))
    controladas = pd.DataFrame(
        {
            "comprador": [UMA_E_CONTROLADA, SO_CONTROLADA],
            "alvo": [ALVOS[4], ALVOS[5]],
            "tipo": ["controlada", "controlada"],
            "participacao": [100.0, 100.0],
            "referencia": [date(2025, 12, 31)] * 2,
            "publico_em": [DIA] * 2,
        }
    )
    lista.anotar_controladas(controladas)
    return lista


def _nomes(lista: compradores._Lista) -> dict[str, tuple[str, date]]:
    return {raiz: (f"EMPRESA {raiz}", DIA) for raiz in lista.raizes()}


def _ordem(limite: int = 50) -> list[str]:
    lista = _lista()
    return [c["raiz_do_cnpj"] for c in lista.montar(_nomes(lista), limite)]


def test_quem_mais_comprou_de_terceiros_vem_primeiro_mesmo_com_um_sinal_so():
    ordem = _ordem()
    assert (
        ordem[0] == MUITAS
    )  # 3 entradas e 1 sinal, antes de quem tem 2 sinais e 1 entrada
    assert ordem.index(MUITAS) < ordem.index(UMA_E_CONTROLADA)


def test_a_controlada_nao_passa_a_frente_de_quem_tem_a_mesma_quantidade_de_entradas():
    """A companhia aberta com uma controlada e uma entrada fica atrás só no desempate de sinais: depois da mais comprada
    e antes de quem tem uma entrada só."""
    ordem = _ordem()
    assert ordem.index(UMA_E_CONTROLADA) < min(
        ordem.index(UMA_VELHA), ordem.index(UMA_NOVA)
    )


def test_comprador_so_com_controlada_vem_depois_de_todo_comprador_com_entrada():
    assert _ordem()[-1] == SO_CONTROLADA


def test_o_empate_nao_olha_a_data_a_entrada_de_ontem_nao_sobe_o_comprador():
    ordem = _ordem()
    # a mais velha e a mais nova têm uma entrada e um sinal: desempata a raiz, não a data
    assert ordem.index(UMA_VELHA) < ordem.index(UMA_NOVA)
    assert sorted([UMA_VELHA, UMA_NOVA]) == [UMA_VELHA, UMA_NOVA]


def test_o_corte_pega_os_primeiros_da_ordem():
    assert _ordem(limite=2) == [MUITAS, UMA_E_CONTROLADA]


def test_comprador_so_com_sinal_sem_data_continua_na_lista_e_vem_depois_de_quem_tem_entrada():
    """Controlada sem data de referência (a data vem vazia do FRE): o comprador não some nem derruba a ordem, e a
    falta de data não o põe na frente de ninguém que tenha entrada."""
    lista = _lista()
    sem_data = "40000006"
    lista.anotar_controladas(
        pd.DataFrame(
            {
                "comprador": [sem_data],
                "alvo": [ALVOS[0]],
                "tipo": ["controlada"],
                "participacao": [100.0],
                "referencia": [pd.NaT],
                "publico_em": [DIA],
            }
        )
    )
    ordem = [c["raiz_do_cnpj"] for c in lista.montar(_nomes(lista), 50)]
    assert sem_data in ordem
    assert ordem[-2:] == [SO_CONTROLADA, sem_data]  # só controlada: desempata a raiz
    assert ordem.index(sem_data) > ordem.index(UMA_NOVA)
