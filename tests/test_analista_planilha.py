"""A planilha da tela do analista (linha 798): `src/analista/planilha.py`.

A mesma planilha da CLI (linha 773, `cli/tickerlab/planilha.py`), com os nomes em português: a aba `campos`
com os campos soltos, uma aba por lista e a aba `fontes` com a atribuição e o aviso; em cada linha, a fonte e o
dia em que o dado ficou público. Risco 4: texto da base (a razão social) nunca vira fórmula no Excel.
"""

import io
import zipfile
from datetime import date

import openpyxl
import pytest

from src.analista import planilha
from src.api_externa.envelope import campo
from src.api_externa.nomes import para_fora, traduzir_chaves

AVISO = "Nada aqui é recomendação de investimento."


def _envelope(valor, fonte="rfb-cnpj", publico_em="2025-01-31"):
    return campo(valor, fonte=fonte, publico_em=_dia(publico_em), visto_em=None)


def _dia(texto):
    return date.fromisoformat(texto)


def _corpo(razao_social: str = "ALFA S.A.") -> dict:
    """Uma ficha como o leitor a monta, com as fontes que a rota acrescenta."""
    return {
        "cnpj": "11111111000191",
        "como_era_em": "2026-11-10",
        "cadastro_na_receita": {
            "situacao_cadastral": _envelope("02"),
            "razao_social": _envelope(razao_social, publico_em="2024-06-30"),
            "matriz": _envelope(True),
        },
        "entregas": [
            {
                "documento": _envelope("DFP", "cvm-hist-dfp", "2024-03-20"),
                "prazo": _envelope("2024-04-01", "cvm-hist-dfp", "2024-03-20"),
                "dias_uteis_de_atraso": _envelope(0, "cvm-hist-dfp", "2024-03-20"),
            },
            {
                "documento": _envelope("ITR", "cvm-hist-itr", "2024-05-17"),
                "prazo": _envelope("2024-05-15", "cvm-hist-itr", "2024-05-17"),
                "dias_uteis_de_atraso": _envelope(2, "cvm-hist-itr", "2024-05-17"),
            },
        ],
        "limites": ["Cada campo traz a fonte.", "Pessoa natural não é servida."],
        "fontes": [
            {"fonte": "rfb-cnpj", "licenca": "CC BY", "atribuicao": "Receita Federal"},
            {"fonte": "cvm-hist-dfp", "licenca": "ODbL", "atribuicao": "CVM"},
        ],
    }


def _abrir(conteudo: bytes) -> openpyxl.Workbook:
    return openpyxl.load_workbook(io.BytesIO(conteudo))


def _linhas(aba) -> list[list]:
    return [list(linha) for linha in aba.iter_rows(values_only=True)]


def test_abas_campos_listas_e_fontes_nesta_ordem():
    pasta = _abrir(planilha.xlsx(_corpo()))
    assert pasta.sheetnames == ["campos", "entregas", "limites", "fontes"]


def test_campos_soltos_com_valor_cru_fonte_e_data():
    linhas = _linhas(_abrir(planilha.xlsx(_corpo()))["campos"])
    assert linhas[0] == ["campo", "valor", "fonte", "publicado_em"]
    assert ["cnpj", "11111111000191", None, None] in linhas
    assert [
        "cadastro_na_receita › razao_social", "ALFA S.A.", "rfb-cnpj", "2024-06-30",
    ] in linhas  # fmt: skip
    assert ["cadastro_na_receita › matriz", True, "rfb-cnpj", "2025-01-31"] in linhas


def test_cada_lista_vira_uma_aba_com_a_fonte_e_a_data_por_linha():
    pasta = _abrir(planilha.xlsx(_corpo()))
    entregas = _linhas(pasta["entregas"])
    assert entregas[0] == [
        "documento", "prazo", "dias_uteis_de_atraso", "fonte", "publicado_em",
    ]  # fmt: skip
    assert entregas[2] == ["ITR", "2024-05-15", 2, "cvm-hist-itr", "2024-05-17"]
    assert _linhas(pasta["limites"]) == [
        ["texto"], ["Cada campo traz a fonte."], ["Pessoa natural não é servida."],
    ]  # fmt: skip


def test_aba_das_fontes_tem_a_atribuicao_a_licenca_e_o_aviso_no_fim():
    linhas = _linhas(_abrir(planilha.xlsx(_corpo()))["fontes"])
    assert linhas[0] == ["fonte", "atribuicao", "licenca"]
    assert ["rfb-cnpj", "Receita Federal", "CC BY"] in linhas
    assert linhas[-1] == ["aviso", AVISO, None]


@pytest.mark.parametrize(
    "perigoso", ['=HYPERLINK("http://x","clique")', "+1+1", "-2+3", "@SOMA(1)"]
)
def test_texto_da_base_nunca_vira_formula(perigoso):
    aba = _abrir(planilha.xlsx(_corpo(razao_social=perigoso)))["campos"]
    celula = next(
        c for (c,) in aba.iter_rows(min_col=2, max_col=2) if c.value == perigoso
    )
    assert celula.data_type == "s"


def test_mesma_resposta_da_o_mesmo_arquivo():
    assert planilha.xlsx(_corpo()) == planilha.xlsx(_corpo())


def test_toda_entrada_do_zip_tem_a_data_fixa():
    """O openpyxl grava a hora do relógio em cada entrada do zip: duas chamadas em segundos diferentes davam
    bytes diferentes (o teste acima falhou no CI da main em 10/11/2026)."""
    with zipfile.ZipFile(io.BytesIO(planilha.xlsx(_corpo()))) as arquivo:
        assert {info.date_time for info in arquivo.infolist()} == {
            planilha.DATA_FIXA_DO_ZIP
        }


def test_mesmas_abas_linhas_e_colunas_da_planilha_da_cli():
    """A planilha do app e a da CLI (773) dão a mesma forma para a mesma resposta: só os nomes mudam de
    língua (a CLI recebe a resposta da API, em inglês)."""
    cli = pytest.importorskip("tickerlab.planilha")
    corpo = _corpo()
    da_cli = [
        *cli.tabelas_da_resposta(traduzir_chaves(corpo)),
        cli.tabela_das_fontes(traduzir_chaves(corpo)),
    ]
    do_app = planilha.abas(corpo)
    assert len(do_app) == len(da_cli)
    comuns = {
        "campo",
        "valor",
        "fonte",
        "publicado_em",
        "texto",
        "atribuicao",
        "licenca",
        "campos",
        "fontes",
    }

    def fora(nome: str) -> str:
        return " › ".join(p if p in comuns else para_fora(p) for p in nome.split(" › "))

    for app, cli_ in zip(do_app, da_cli, strict=True):
        assert fora(app.nome) == cli_.nome
        assert [fora(c) for c in app.cabecalho] == cli_.cabecalho
        assert len(app.linhas) == len(cli_.linhas)
        assert [linha[1:] for linha in app.linhas] == [
            linha[1:] for linha in cli_.linhas
        ]
