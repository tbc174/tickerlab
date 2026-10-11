"""O script de carga leve calcula os números certos (sem rede)."""

import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "carga_leve", RAIZ / "scripts" / "carga_leve.py"
)
carga_leve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carga_leve)


def test_percentil_pega_o_valor_certo():
    valores = [float(i) for i in range(1, 101)]
    assert carga_leve.percentil(valores, 50) in (50.0, 51.0)
    assert carga_leve.percentil(valores, 95) in (95.0, 96.0)
    assert carga_leve.percentil([3.0], 95) == 3.0


def test_resumo_conta_erros_e_converte_para_milissegundos():
    resultados = [(True, 0.010), (True, 0.020), (False, 0.500)]
    resumo = carga_leve.resumir(resultados, duracao=1.0)
    assert resumo["requisicoes"] == 3 and resumo["erros"] == 1
    assert resumo["por_segundo"] == 3.0
    assert resumo["p50_ms"] == 20.0 and resumo["maximo_ms"] == 500.0


def test_limites_de_uso_protegem_contra_enganos():
    assert carga_leve.main(["http://localhost:1", "--total", "0"]) == 2
    assert carga_leve.main(["http://localhost:1", "--simultaneas", "1000"]) == 2
