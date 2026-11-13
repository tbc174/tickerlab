"""Registro que some do arquivo da fonte vira a linha `consta` falso no dia em que sumiu, e volta como `consta`
verdadeiro se reaparecer (linha 907). Sem `consta` nos valores comparados, a saída tinha a mesma assinatura da
última linha e era descartada: a empresa que saía da Lista Suja ou do embargo continuava constando.

Tabelas de mentira: só `id_na_fonte` e os valores comparados, com texto inventado e datas vazias."""

from pathlib import Path

import pandas as pd
import pytest

from base import ans_operadoras, ibama_embargos, mte_lista_suja, susep_cadastro
from base import retratos as motor

MODULOS = [ans_operadoras, ibama_embargos, mte_lista_suja, susep_cadastro]
REGISTROS = 10
DIAS = ("2026-10-14", "2026-10-15", "2026-10-16")


def _retrato(dia: str) -> motor.Retrato:
    return motor.Retrato(
        url="u", sha256=dia, caminho=Path("x"), baixado_em=pd.Timestamp(dia)
    )


def _tabela(modulo, ids: list[int]) -> pd.DataFrame:
    """Uma linha por id, com os valores comparados do módulo: data vazia nas colunas de data, texto no resto."""
    colunas = {"id_na_fonte": [str(i) for i in ids]}
    for coluna in modulo.VALORES:
        if coluna == "consta":
            continue
        if coluna.endswith("_em") or coluna in getattr(modulo, "DATAS", ()):
            colunas[coluna] = pd.Series([pd.NaT] * len(ids), dtype="datetime64[ns]")
        else:
            colunas[coluna] = [f"valor {coluna} {i}" for i in ids]
    return pd.DataFrame(colunas)


@pytest.mark.parametrize("modulo", MODULOS, ids=lambda m: m.__name__.split(".")[-1])
def test_valores_comparados_tem_o_consta(modulo):
    assert "consta" in modulo.VALORES


@pytest.mark.parametrize("modulo", MODULOS, ids=lambda m: m.__name__.split(".")[-1])
def test_registro_que_sai_ganha_consta_falso_e_o_que_volta_consta_verdadeiro(modulo):
    todos = list(range(REGISTROS))
    sem_o_ultimo = todos[:-1]
    lidos = [
        (_retrato(DIAS[0]), _tabela(modulo, todos)),
        (_retrato(DIAS[1]), _tabela(modulo, sem_o_ultimo)),
        (_retrato(DIAS[2]), _tabela(modulo, todos)),
    ]
    tabela, pulados = modulo.juntar_retratos(lidos)
    assert pulados == 0
    do_que_saiu = tabela[tabela["id_na_fonte"] == str(todos[-1])]
    assert list(do_que_saiu["consta"]) == [True, False, True]
    assert list(do_que_saiu["disponivel_em"].iloc[1:]) == [
        pd.Timestamp(d) for d in DIAS[1:]
    ]
    # os que ficaram iguais não ganham linha nova
    assert len(tabela) == REGISTROS + 2
