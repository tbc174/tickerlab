"""Consulta de referência da rede, cronometrada (ADR 0077, item 1; plano da rede, PR 4, tarefa 4.4)."""

import json

import pandas as pd

from scripts import medir_rede
from tests.test_porta import _entidades, _gravar, _identificadores, _ligacoes


def _balancos(*empresas: tuple[str, float]) -> pd.DataFrame:
    linhas = []
    for cnpj, ativo in empresas:
        for fim, valor, ate in (
            ("2023-12-31", ativo / 2, None),
            ("2024-12-31", ativo, None),
        ):
            linhas.append(
                {"cnpj": cnpj, "empresa": f"Companhia {cnpj[:2]}", "grupo": "con",
                 "demonstracao": "BPA", "conta": "1", "fim": fim, "valor": valor,
                 "divulgado_em": "2025-03-31", "ate": ate}
            )  # fmt: skip
        # um valor antigo, trocado por reapresentação, não conta
        linhas.append(
            {"cnpj": cnpj, "empresa": "x", "grupo": "con", "demonstracao": "BPA", "conta": "1",
             "fim": "2024-12-31", "valor": 1e15, "divulgado_em": "2025-02-28", "ate": "2025-03-31"}
        )  # fmt: skip
    tabela = pd.DataFrame(linhas)
    for coluna in ("fim", "divulgado_em", "ate"):
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    return tabela


def test_medir_rede_escreve_o_tempo(tmp_path):
    pasta = tmp_path / "base"
    _gravar(pasta, "rede/entidades.parquet", _entidades("EA", "EB", "EC"))
    _gravar(
        pasta,
        "rede/identificadores.parquet",
        _identificadores(
            ("EA", "cnpj_raiz", "11222333", None, None, "2010-01-01"),
            ("EB", "cnpj_raiz", "44555666", None, None, "2010-01-01"),
        ),
    )
    _gravar(
        pasta,
        "rede/ligacoes.parquet",
        _ligacoes(
            {
                "de": "EB",
                "para": "EA",
                "tipo": "controlada_de",
                "publico_em": "2016-05-31",
            },
            {
                "de": "EC",
                "para": "EB",
                "tipo": "controlada_de",
                "publico_em": "2016-05-31",
            },
        ),
    )
    _gravar(
        pasta,
        "demonstracoes/2024.parquet",
        _balancos(
            ("11.222.333/0001-81", 500.0),
            ("44.555.666/0001-00", 900.0),
            ("77.888.999/0001-00", 100.0),  # sem entidade na rede
        ),
    )
    saida = tmp_path / "medida.json"
    assert (
        medir_rede.main(
            [
                "--pasta",
                str(pasta),
                "--saida",
                str(saida),
                "--quantas",
                "2",
                "--profundidade",
                "3",
            ]
        )
        == 0
    )
    medida = json.loads(saida.read_text(encoding="utf-8"))
    empresas = medida["empresas"]
    assert [e["cnpj"] for e in empresas] == ["44.555.666/0001-00", "11.222.333/0001-81"]
    assert all(
        isinstance(e["segundos"], float) and e["segundos"] >= 0 for e in empresas
    )
    assert [e["ligacoes"] for e in empresas] == [2, 2]
    assert medida["profundidade"] == 3
    assert medida["resumo"]["empresas"] == 2
    assert medida["resumo"]["segundos_no_total"] >= max(e["segundos"] for e in empresas)
    assert medida["resumo"]["memoria_maxima_mb"] > 0


def test_medir_rede_conta_quem_nao_esta_na_rede(tmp_path):
    pasta = tmp_path / "base"
    _gravar(pasta, "rede/entidades.parquet", _entidades("EA"))
    _gravar(
        pasta,
        "rede/identificadores.parquet",
        _identificadores(("EA", "cnpj_raiz", "11222333", None, None, "2010-01-01")),
    )
    _gravar(pasta, "rede/ligacoes.parquet", _ligacoes())
    saida = tmp_path / "medida.json"
    assert (
        medir_rede.main(
            [
                "--pasta",
                str(pasta),
                "--saida",
                str(saida),
                "--cnpjs",
                "77.888.999/0001-00",
            ]
        )
        == 0
    )
    medida = json.loads(saida.read_text(encoding="utf-8"))
    assert medida["empresas"][0]["erro"].startswith("77.888.999/0001-00")
    assert medida["resumo"]["sem_entidade"] == 1
