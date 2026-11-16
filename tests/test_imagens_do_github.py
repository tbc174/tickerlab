"""A peça de marca do GitHub (docs/banner.html) só mostra o que o TickerLab é hoje e o que a CLI tem."""

import html
import re
from pathlib import Path

from scripts.gerar_imagens_do_github import IMAGENS, PAGINA, PASTA

RAIZ = Path(__file__).resolve().parent.parent
COMANDOS_DA_CLI = (RAIZ / "cli" / "tickerlab" / "comandos.py").read_text(
    encoding="utf-8"
)
# a ideia antiga (laboratório de ações) e o que a marca não promete
FRASES_QUE_NAO_VOLTAM = (
    "Laboratório de ações",
    "Backtest",
    "Pesquisa com ML",
    "R$",
    "rentabilidade",
)


def _linhas_do_terminal() -> list[str]:
    pagina = PAGINA.read_text(encoding="utf-8")
    return [
        html.unescape(linha)
        for linha in re.findall(r'<div class="cmd">(.*?)</div>', pagina)
    ]


def test_o_terminal_so_mostra_comando_e_opcao_que_a_cli_tem():
    linhas = _linhas_do_terminal()
    assert linhas, "o terminal da peça ficou sem comandos"
    for linha in linhas:
        programa, comando, *_ = linha.split()
        assert programa == "tickerlab"
        assert re.search(rf"^def {comando}\($", COMANDOS_DA_CLI, flags=re.MULTILINE), (
            linha
        )
        for opcao in re.findall(r"--[a-z-]+", linha):
            assert f'"{opcao}"' in COMANDOS_DA_CLI, linha


def test_o_terminal_nao_mostra_cnpj_de_verdade():
    for linha in _linhas_do_terminal():
        assert not re.search(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}", linha), linha


def test_a_peca_nao_traz_a_ideia_antiga_nem_promessa():
    pagina = PAGINA.read_text(encoding="utf-8")
    for frase in FRASES_QUE_NAO_VOLTAM:
        assert frase not in pagina, frase


def test_as_imagens_geradas_estao_no_repositorio():
    for nome, *_ in IMAGENS:
        assert (PASTA / nome).is_file(), (
            f"rode python -m scripts.gerar_imagens_do_github ({nome})"
        )
