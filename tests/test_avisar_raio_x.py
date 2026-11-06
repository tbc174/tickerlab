"""O aviso do rascunho do Raio-X (plano `2026-10-28-raio-x-todo-dia`, PR 6c, Tarefa 11).

O servidor grava o rascunho no acervo; o PC, com a cópia do acervo, escreve uma nota em `esperando/` para o
Tiago, com a recomendação, e o início da sessão avisa. Uma nota por rascunho, nunca duas.
"""

import json
from datetime import date
from pathlib import Path

from scripts import avisar_raio_x as aviso
from scripts import gerar_pregao_do_dia as g

FOMC = date(2026, 10, 28)
CHOQUE = date(2026, 10, 26)


def _guardar(acervo: Path, dia: date, variacao: float, forte: bool) -> None:
    resumo = g.caminho_do_resumo(acervo, dia)
    resumo.parent.mkdir(parents=True, exist_ok=True)
    evento = {
        "calendario": [
            {"evento": "Decisão do Fed (FOMC)", "data": dia.isoformat(), "fonte": "x"}
        ]
        if not forte
        else [],
        "variacao_forte_do_ibovespa": forte,
        "variacao_minima": 0.03,
    }
    resumo.write_text(
        json.dumps({"pregao": dia.isoformat(), "evento": evento}), "utf-8"
    )
    rascunho = g.caminho_do_rascunho(acervo, dia, ".json")
    rascunho.parent.mkdir(parents=True, exist_ok=True)
    rascunho.write_text(
        json.dumps(
            {
                "pregao": dia.isoformat(),
                "ibovespa": {"variacao": variacao},
                "queda": {
                    "empresas": 120,
                    "mediana": variacao * 1.5,
                    "quedas_fortes": 35 if forte else 0,
                },
            }
        ),
        "utf-8",
    )


def test_nota_para_cada_rascunho_novo(tmp_path):
    acervo, esperando = tmp_path / "acervo", tmp_path / "esperando"
    _guardar(acervo, FOMC, -0.0268, forte=False)
    _guardar(acervo, CHOQUE, -0.1388, forte=True)
    assert aviso.rascunhos_sem_aviso(acervo, esperando) == [CHOQUE, FOMC]

    novas = aviso.avisar(acervo, esperando)
    assert [n.name for n in novas] == [
        "Produto · Raio-X de 26-10-2026 esperando o pode.md",
        "Produto · Raio-X de 28-10-2026 esperando o pode.md",
    ]
    assert aviso.rascunhos_sem_aviso(acervo, esperando) == []
    assert aviso.avisar(acervo, esperando) == []  # nunca duas notas do mesmo rascunho


def test_nota_tem_recomendacao_e_caminho_do_rascunho(tmp_path):
    acervo, esperando = tmp_path / "acervo", tmp_path / "esperando"
    _guardar(acervo, FOMC, -0.0268, forte=False)
    _guardar(acervo, CHOQUE, -0.1388, forte=True)
    aviso.avisar(acervo, esperando)
    fomc = (esperando / aviso.nome_da_nota(FOMC)).read_text("utf-8")
    choque = (esperando / aviso.nome_da_nota(CHOQUE)).read_text("utf-8")

    for nota in (fomc, choque):
        assert nota.startswith(
            "---\ntipo: espera\nmesa: Produto\nde-quem: você\nsituacao: aberta\n"
        )
        assert "**Recomendação:**" in nota
        assert "nível 1" in nota
    assert "Decisão do Fed (FOMC)" in fomc
    assert "−2,7%" in fomc
    assert "não publicar" in fomc
    assert "−13,9%" in choque
    assert "35 caíram 30% ou mais" in choque
    assert "ler e publicar" in choque
    assert str(g.caminho_do_rascunho(acervo, CHOQUE, ".html")) in choque


def test_rascunho_pela_metade_nao_avisa(tmp_path):
    """O JSON é gravado por último: sem ele o rascunho não saiu inteiro e não há o que ler."""
    acervo, esperando = tmp_path / "acervo", tmp_path / "esperando"
    _guardar(acervo, FOMC, -0.0268, forte=False)
    g.caminho_do_rascunho(acervo, FOMC, ".json").unlink()
    g.caminho_do_rascunho(acervo, FOMC, ".html").write_text("<html>", "utf-8")
    assert aviso.avisar(acervo, esperando) == []


def test_sem_pasta_de_rascunhos(tmp_path):
    assert aviso.avisar(tmp_path / "acervo", tmp_path / "esperando") == []


def test_linha_do_inicio_da_sessao(tmp_path, capsys):
    acervo, esperando = tmp_path / "acervo", tmp_path / "esperando"
    _guardar(acervo, CHOQUE, -0.1388, forte=True)
    assert aviso.main(["--acervo", str(acervo), "--esperando", str(esperando)]) == 0
    saida = capsys.readouterr().out
    assert "Raio-X" in saida and "26/10/2026" in saida and "Central" in saida
    assert aviso.main(["--acervo", str(acervo), "--esperando", str(esperando)]) == 0
    assert capsys.readouterr().out == ""
