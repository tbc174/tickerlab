"""A conferência da Receita com `--par` olha parte dos pares: o JSON nunca diz `aprovado`."""

import json
from contextlib import nullcontext

import pandas as pd

from scripts import conferir_receita as cr

PAR_INFORMATIVO = "razao_social_ifdata_x_receita"
PAR_QUE_VALE = "uf_anatel_x_receita"


def _comparacao() -> pd.DataFrame:
    return pd.DataFrame({"concorda": [True, True, False], "causa": ["", "", "outra"]})


def _rodar(monkeypatch, tmp_path, argv: list[str]) -> tuple[int, dict]:
    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path))
    monkeypatch.setattr(cr.porta, "abrir", lambda: nullcontext(object()))
    monkeypatch.setattr(
        cr, "COMPARADORES", {par.nome: (lambda p, h: _comparacao()) for par in cr.PARES}
    )
    codigo = cr.main(argv)
    (arquivo,) = tmp_path.glob("placar/*/cruzada_receita.json")
    return codigo, json.loads(arquivo.read_text(encoding="utf-8"))


def test_rodada_parcial_so_com_par_informativo_nao_grava_aprovado(
    monkeypatch, tmp_path
):
    _, resultado = _rodar(monkeypatch, tmp_path, ["--par", PAR_INFORMATIVO])
    assert resultado["parcial"] is True
    assert "aprovado" not in resultado


def test_rodada_parcial_de_um_par_que_vale_tambem_nao_grava_aprovado(
    monkeypatch, tmp_path
):
    _, resultado = _rodar(monkeypatch, tmp_path, ["--par", PAR_QUE_VALE])
    assert resultado["parcial"] is True
    assert "aprovado" not in resultado


def test_rodada_completa_segue_gravando_aprovado(monkeypatch, tmp_path):
    _, resultado = _rodar(monkeypatch, tmp_path, [])
    assert "aprovado" in resultado
    assert "parcial" not in resultado
