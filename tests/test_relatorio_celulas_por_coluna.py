"""`escrever_celula` olha a coluna: ano e contagem não são dinheiro (linha 371 da fila)."""

import pytest

from src import relatorio_empresa as re_


@pytest.mark.parametrize("coluna", ["ano", "exercicio", "exercicio_do_caixa"])
def test_o_ano_sai_sem_separador_e_sem_reais(coluna):
    assert re_.escrever_celula(2024, coluna) == "2024"
    assert re_.escrever_celula(2024.0, coluna) == "2024"


@pytest.mark.parametrize("coluna", ["acoes", "acoes_ajustadas", "acoes_em_circulacao"])
def test_a_quantidade_de_acoes_sai_com_pontos_e_sem_reais(coluna):
    assert re_.escrever_celula(1_152_254_440.0, coluna) == "1.152.254.440"


def test_dinheiro_acima_de_mil_continua_em_reais():
    assert re_.escrever_celula(1_200_000_000.0, "receita").startswith("R$ 1,2")
    assert re_.escrever_celula(2_000.0).startswith("R$ 2,0")  # sem coluna, como antes


def test_fracoes_e_vazios_nao_mudam():
    assert re_.escrever_celula(0.351, "margem") == "0,35"
    assert re_.escrever_celula(None, "ano") == "—"
    assert re_.escrever_celula(True, "ano") == "sim"


def test_o_rotulo_de_acoes_leva_acento():
    assert re_.rotulo_da_coluna("acoes") == "Ações"
    assert re_.rotulo_da_coluna("acoes_ajustadas") == "Ações ajustadas"


LINHAS = [{"ano": 2023, "acoes": 1_152_254_440.0, "receita": 1_200_000_000.0}]


def test_a_tabela_do_pdf_passa_a_coluna():
    from src.relatorio_empresa_pdf import _cabecalho_e_linhas

    cabecalho, corpo = _cabecalho_e_linhas(LINHAS)
    assert cabecalho[:2] == ["Ano", "Ações"]
    assert corpo[0][:2] == ["2023", "1.152.254.440"]
    assert corpo[0][2].startswith("R$")


def test_a_tabela_da_api_passa_a_coluna():
    from src.api_v1.esquemas import _tabela_do_relatorio

    tabela = _tabela_do_relatorio("historico", LINHAS)
    assert tabela.linhas[0][:2] == ["2023", "1.152.254.440"]
