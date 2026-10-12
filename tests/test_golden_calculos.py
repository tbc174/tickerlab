"""Valores de referência ("golden") dos cálculos de Estratégias, Carteira, acaso e aprendizado.

Com os dados de exemplo do projeto e as mesmas funções que a tela chama, os números de hoje ficam
guardados em `tests/arquivos/golden_calculos.json`. Este teste recalcula e compara: um número que
muda sem querer (numa refatoração do `app.py`, numa troca de biblioteca) faz o teste falhar.
Mudou um cálculo de propósito? Rode `python -m scripts.gerar_golden_calculos` e explique no PR.
"""

import json
from pathlib import Path

import pytest

from scripts import gerar_golden_calculos as golden
from src.carteiras import ESTRATEGIAS_DE_CARTEIRA
from src.estrategias import ESTRATEGIAS

ARQUIVO_GOLDEN = Path(__file__).parent / "arquivos" / "golden_calculos.json"
TOLERANCIA_RELATIVA = (
    1e-9  # pega qualquer mudança real; tolera o último dígito entre máquinas
)
TOLERANCIA_ABSOLUTA = 1e-12


@pytest.fixture(scope="module")
def guardado():
    return json.loads(ARQUIVO_GOLDEN.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def calculado():
    # passa pelo JSON para comparar os mesmos tipos (NaN vira None, como no arquivo)
    return json.loads(json.dumps(golden.calcular()))


def _comparar(grupo: str, guardado: dict, calculado: dict) -> None:
    assert set(calculado) == set(guardado), (
        f"Cenários de {grupo} mudaram: rode python -m scripts.gerar_golden_calculos"
    )
    for cenario, metricas in guardado.items():
        assert set(calculado[cenario]) == set(metricas), (grupo, cenario)
        for nome, antes in metricas.items():
            agora = calculado[cenario][nome]
            if antes is None or agora is None:
                assert antes == agora, (
                    f"{grupo} / {cenario} / {nome}: {antes} → {agora}"
                )
            else:
                assert agora == pytest.approx(
                    antes, rel=TOLERANCIA_RELATIVA, abs=TOLERANCIA_ABSOLUTA
                ), f"{grupo} / {cenario} / {nome} mudou de {antes} para {agora}"


@pytest.mark.parametrize("grupo", ["estrategias", "carteiras", "acaso", "aprendizado"])
def test_calculos_iguais_aos_de_referencia(grupo, guardado, calculado):
    _comparar(grupo, guardado[grupo], calculado[grupo])


def test_toda_estrategia_e_toda_carteira_tem_referencia(guardado):
    """Estratégia ou carteira nova entra na referência (rode o gerador)."""
    esperadas = {
        f"{ticker} | {nome}"
        for ticker in golden.ATIVOS_DAS_ESTRATEGIAS
        for nome in ESTRATEGIAS
    }
    assert set(guardado["estrategias"]) == esperadas
    assert set(guardado["carteiras"]) == set(ESTRATEGIAS_DE_CARTEIRA)


def test_a_referencia_tem_numeros_de_verdade(guardado):
    """Uma referência vazia ou toda zerada não protegeria nada."""
    sharpes = [m["Índice de Sharpe"] for m in guardado["estrategias"].values()]
    assert all(s is not None for s in sharpes)
    assert (
        len({round(s, 6) for s in sharpes}) > len(sharpes) // 2
    )  # estratégias diferem
    assert guardado["aprendizado"]["avaliacao"]["Previsões"] > 100
