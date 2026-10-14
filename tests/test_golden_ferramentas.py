"""Os casos golden das ferramentas (`web/testes/golden_ferramentas.json`) estão em dia com o Python.

O mesmo arquivo é lido pelo vitest, que confere as contas em TypeScript. Se este teste falhar,
uma conta de `src/ferramentas/` mudou (ou ganhou caso novo): rode
`python -m scripts.gerar_golden_ferramentas`, mude a cópia em TS e explique no PR.
"""

import json

import pytest

from scripts import gerar_golden_ferramentas as golden

TOLERANCIA_RELATIVA = 1e-12  # o último dígito pode variar entre máquinas


def _comparar(antes, agora, onde: str) -> None:
    if isinstance(antes, dict):
        assert isinstance(agora, dict), onde
        assert set(antes) == set(agora), onde
        for chave in antes:
            _comparar(antes[chave], agora[chave], f"{onde}.{chave}")
    elif isinstance(antes, list):
        assert isinstance(agora, list), onde
        assert len(antes) == len(agora), onde
        for posicao, (a, b) in enumerate(zip(antes, agora, strict=True)):
            _comparar(a, b, f"{onde}[{posicao}]")
    elif isinstance(antes, float) or isinstance(agora, float):
        assert agora == pytest.approx(antes, rel=TOLERANCIA_RELATIVA, abs=1e-12), onde
    else:
        assert agora == antes, onde


def test_golden_das_ferramentas_esta_em_dia():
    guardado = json.loads(golden.ARQUIVO.read_text(encoding="utf-8"))
    calculado = json.loads(json.dumps(golden.calcular()))
    _comparar(guardado, calculado, "casos")


def test_toda_conta_tem_caso_que_passa_e_caso_recusado_quando_valida():
    contas_com_caso = {conta for conta, _ in golden.CASOS}
    assert contas_com_caso == set(golden.CONTAS)
    recusados = {caso["conta"] for caso in golden.calcular() if caso.get("erro")}
    # as contas que validam a entrada têm pelo menos um caso recusado no golden
    for conta in ("juros.montante", "juros.taxa_equivalente", "aportes.valor_futuro"):
        assert conta in recusados
