"""As planilhas de exemplo de `conteudo/` são as que `scripts/gerar_planilhas_de_exemplo.py` gera.

Se alguém mudar o gerador sem gerar de novo (ou a planilha sem mudar o gerador), este teste avisa.
"""

from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from scripts import gerar_planilhas_de_exemplo as gerador


@pytest.mark.parametrize("nome", sorted(gerador.PLANILHAS))
def test_planilha_rastreada_e_a_do_gerador(nome: str, tmp_path: Path) -> None:
    gerada = gerador.gerar(nome, tmp_path)
    _, arquivo, aba = gerador.PLANILHAS[nome]
    rastreada = gerador.CONTEUDO / arquivo
    assert_frame_equal(
        pd.read_excel(gerada, sheet_name=aba), pd.read_excel(rastreada, sheet_name=aba)
    )


def test_nome_desconhecido_avisa() -> None:
    with pytest.raises(SystemExit, match="Planilha desconhecida: inexistente"):
        gerador.main(["inexistente"])


def test_main_gera_so_a_planilha_pedida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gerador, "CONTEUDO", tmp_path)
    gerador.main(["negociacao"])
    assert [p.name for p in tmp_path.iterdir()] == ["negociacao_de_exemplo.xlsx"]
    assert "Gerado: " in capsys.readouterr().out
