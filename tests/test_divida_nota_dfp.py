"""Leitura por regra do cronograma de vencimentos da nota de endividamento (B-21, PR 2)."""

import json
from datetime import date

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.divida.nota_dfp import (
    ANOS_NAS_COLUNAS,
    ANOS_NAS_LINHAS,
    FONTE_DA_NOTA,
    CronogramaDaNota,
    faixas_da_serie,
    ler_cronogramas,
    serie_do_total,
)
from src.rastro import DocumentoUsado

DOCUMENTO = DocumentoUsado(
    "DFP de 31/12/2024 da Exemplo S.A., versão 1, nota 18",
    date(2025, 3, 20),
    "https://x",
)

NOTA = """18. Empréstimos, financiamentos e debêntures
(Em milhares de reais)
As parcelas do não circulante têm o seguinte cronograma de vencimentos:
Controladora Consolidado
2024 2024
2026 100.000 250.000
2027 200.000 300.500
2028 a 2029 50.000 -
2030 em diante 1.000 (500)
Total 351.000 550.000
As debêntures têm cláusulas restritivas (covenants).
"""

COLUNAS = """(Em milhões de reais)
30.4. Informações resumidas sobre os financiamentos
Consolidado
Vencimento em 2026 2027 2028 2029
2030
em diante Total (1) Valor justo (2)

Financiamentos em Dólares : 10 20 − 30 40 100 98
Indexados a taxas flutuantes (1) 10 20 − 30 40 100
Taxa média a.a. 6,3% 6,0% − 6,1% 6,2%
Financiamentos em Reais : 5 5 5 5 5 25 24
Total em 31 de dezembro de 2025 15 25 5 35 45 125 122
Taxa média a.a. (2) 7,3% 6,8% 6,8% 7,1% 7,2%
(1) O prazo médio é de 11,70 anos.
"""


def _um(texto: str, **kwargs) -> CronogramaDaNota:
    cronogramas = ler_cronogramas(texto, DOCUMENTO, **kwargs)
    assert len(cronogramas) == 1
    return cronogramas[0]


def _anos(cronograma: CronogramaDaNota) -> list[tuple[int, int | None]]:
    return [(p.ano_inicial, p.ano_final) for p in cronograma.periodos]


def test_anos_nas_linhas_com_rotulos_colunas_e_total():
    cronograma = _um(NOTA)
    assert cronograma.orientacao == ANOS_NAS_LINHAS
    assert _anos(cronograma) == [(2026, 2026), (2027, 2027), (2028, 2029), (2030, None)]
    assert [p.rotulo for p in cronograma.periodos] == [
        "2026",
        "2027",
        "2028 a 2029",
        "2030 em diante",
    ]
    consolidado = cronograma.series[1]
    assert consolidado.valores == (
        250_000.0,
        300_500.0,
        0.0,
        -500.0,
    )  # "-" zero, "(500)"
    assert [s.total for s in cronograma.series] == [351_000.0, 550_000.0]
    assert [s.confere for s in cronograma.series] == [True, True]
    assert cronograma.escala == 1_000.0
    assert cronograma.contexto[-2:] == ("Controladora Consolidado", "2024 2024")
    assert "cronograma de vencimentos" in " ".join(cronograma.contexto)


def test_faixas_da_serie_em_reais_e_com_rastro():
    faixas = faixas_da_serie(_um(NOTA), serie=1)
    assert [(f.ano_inicial, f.ano_final, f.valor_em_reais) for f in faixas] == [
        (2026, 2026, 250_000_000.0),
        (2027, 2027, 300_500_000.0),
        (2028, 2029, 0.0),
        (2030, None, -500_000.0),
    ]
    for faixa in faixas:
        assert faixa.rastro.o_que_falta() == []
        assert faixa.rastro.fonte_id == FONTE_DA_NOTA
        assert faixa.rastro.documentos == (DOCUMENTO,)
        assert faixa.rastro.publicado_em == date(2025, 3, 20)


def test_serie_que_nao_bate_com_o_total_fica_nao_observada():
    cronograma = _um(NOTA.replace("Total 351.000 550.000", "Total 351.000 999.999"))
    assert [s.confere for s in cronograma.series] == [True, False]
    assert {f.valor_na_nota for f in faixas_da_serie(cronograma, 1)} == {None}
    assert {f.valor_em_reais for f in faixas_da_serie(cronograma, 1)} == {None}
    assert faixas_da_serie(cronograma, 0)[0].valor_na_nota == 100_000.0


def test_tabela_sem_nenhuma_serie_que_confere_fica_de_fora():
    errada = NOTA.replace("Total 351.000 550.000", "Total 1 2")
    assert ler_cronogramas(errada, DOCUMENTO) == ()


def test_arredondamento_de_uma_unidade_por_periodo_ainda_confere():
    assert (
        _um(NOTA.replace("351.000", "351.003")).series[0].confere
    )  # 4 períodos, folga 4
    assert not _um(NOTA.replace("351.000 550", "351.005 550")).series[0].confere


def test_sem_linha_total_nao_ha_tabela():
    assert ler_cronogramas(NOTA.replace("Total 351.000 550.000\n", ""), DOCUMENTO) == ()


def test_subtotal_fecha_a_tabela_antes_da_marcacao_a_mercado():
    texto = (
        "2027 100\n2028 a 2032 50\nSubtotal 150\nMarcação a mercado (7)\nTotal 143\n"
    )
    cronograma = _um(texto)
    assert cronograma.series[0].total == 150.0
    assert cronograma.series[0].confere


def test_linhas_com_tamanhos_diferentes_nao_conferem():
    torta = NOTA.replace("2027 200.000 300.500", "2027 300.500")
    assert ler_cronogramas(torta, DOCUMENTO) == ()


def test_sem_escala_o_valor_em_reais_nao_e_observado():
    sem_escala = NOTA.replace("(Em milhares de reais)\n", "")
    cronograma = _um(sem_escala)
    assert cronograma.escala is None
    faixa = faixas_da_serie(cronograma, 0)[0]
    assert faixa.valor_na_nota == 100_000.0
    assert faixa.valor_em_reais is None
    # a escala da capa do documento vale quando a nota não diz
    assert _um(sem_escala, escala=1_000.0).escala == 1_000.0


def test_cada_tabela_tem_a_escala_da_frase_mais_proxima_antes_dela():
    texto = (
        "Valores em R$ mil\n2026 1\n2027 2\nTotal 3\n"
        "(Em milhões de reais, exceto se indicado de outra forma)\n2026 4\n2027 5\nTotal 9\n"
        "em milhares de reais ... em milhões de reais\n2026 6\n2027 7\nTotal 13\n"
    )
    assert [c.escala for c in ler_cronogramas(texto, DOCUMENTO)] == [
        1_000.0,
        1_000_000.0,
        1_000_000.0,  # a frase com as duas escalas não decide nada: fica a anterior
    ]


def test_outros_rotulos_de_periodo_e_tracos():
    texto = """2026 1
2027–2028 2
2029 a 2030 3
Entre 2031 e 2032 4
Após 2032 5
Total 15
2026 1
2027 e seguintes 2
Total 3
2026 1
A partir de 2027 2
Total 3
2026 1
2027 adiante 2
Total 3
"""
    cronogramas = ler_cronogramas(texto, DOCUMENTO)
    assert [_anos(c) for c in cronogramas] == [
        [(2026, 2026), (2027, 2028), (2029, 2030), (2031, 2032), (2033, None)],
        [(2026, 2026), (2027, None)],
        [(2026, 2026), (2027, None)],
        [(2026, 2026), (2027, None)],
    ]


def test_numero_com_decimais():
    cronograma = _um("2026 1.234,50\n2027 765,50\nTotal 2.000,00\n")
    assert cronograma.series[0].valores == (1_234.5, 765.5)
    assert cronograma.series[0].confere


def test_duas_tabelas_no_mesmo_texto():
    texto = NOTA + "\nVencimentos das debêntures\n2026 10\n2027 20\nTotal 30\n"
    cronogramas = ler_cronogramas(texto, DOCUMENTO)
    assert len(cronogramas) == 2
    assert cronogramas[1].series[0].total == 30.0


def test_texto_corrido_e_comparativo_de_exercicios_nao_viram_tabela():
    texto = (
        "O vencimento antecipado não ocorreu.\n"
        "Em 2026 a companhia pagou juros.\n"
        "2025 2024\n"
        "Receita 10 9\n"
        "2025 10\n"  # um período só
        "Total 10\n"
        "2027 10\n"
        "2026 20\n"  # anos fora de ordem
        "Total 30\n"
    )
    assert ler_cronogramas(texto, DOCUMENTO) == ()


def test_anos_nas_colunas_com_cabecalho_quebrado_e_rodapes():
    cronograma = _um(COLUNAS)
    assert cronograma.orientacao == ANOS_NAS_COLUNAS
    assert _anos(cronograma) == [
        (2026, 2026),
        (2027, 2027),
        (2028, 2028),
        (2029, 2029),
        (2030, None),
    ]
    assert cronograma.periodos[-1].rotulo == "2030 em diante"
    assert [s.rotulo for s in cronograma.series] == [
        "Financiamentos em Dólares",
        "Indexados a taxas flutuantes (1)",
        "Financiamentos em Reais",
        "Total em 31 de dezembro de 2025",
    ]
    assert all(serie.confere for serie in cronograma.series)
    assert cronograma.escala == 1_000_000.0


def test_anos_nas_colunas_o_total_vem_depois_do_ultimo_periodo():
    cronograma = _um(COLUNAS)
    dolares = cronograma.series[0]
    assert dolares.valores == (10.0, 20.0, 0.0, 30.0, 40.0)  # "−" é zero
    assert dolares.total == 100.0  # o valor justo, depois do total, fica fora
    total = cronograma.series[serie_do_total(cronograma)]
    assert total.rotulo == "Total em 31 de dezembro de 2025"
    faixas = faixas_da_serie(cronograma, serie_do_total(cronograma))
    assert [f.valor_em_reais for f in faixas] == [15e6, 25e6, 5e6, 35e6, 45e6]


def test_anos_nas_colunas_que_nao_bate_fica_nao_observada():
    cronograma = _um(COLUNAS.replace("5 5 5 5 5 25 24", "5 5 5 5 5 35 24"))
    reais = cronograma.series[2]
    assert not reais.confere
    assert {f.valor_na_nota for f in faixas_da_serie(cronograma, 2)} == {None}


def test_serie_do_total_pega_a_ultima_linha_total_que_confere():
    texto = (
        "2026 2027 2028 Total\n"
        "Principal 1 2 3 6\n"
        "Total 1 2 3 6\n"
        "Juros 1 1 1 3\n"
        "Total geral 2 3 4 9\n"
    )
    cronograma = _um(texto)
    assert serie_do_total(cronograma) == 3
    assert (
        serie_do_total(_um(NOTA)) is None
    )  # anos nas linhas: quem escolhe lê o contexto


def test_cabecalho_com_ano_repetido_fica_nao_observado():
    # a Sabesp de 2025 escreve "2031" e "2031 até 2048": não dá para saber o que é cada coluna
    texto = (
        "2026 2027 2028 2029 2030 2031\n"
        "2031 até\n"
        "2048 Total\n"
        "Debêntures 1 1 1 1 1 1 1 7\n"
        "Total Geral 1 1 1 1 1 1 1 7\n"
    )
    assert ler_cronogramas(texto, DOCUMENTO) == ()


def test_como_dict_vira_json():
    json.dumps(_um(NOTA).como_dict())
    json.dumps(_um(COLUNAS).como_dict())


def _brasileiro(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


VALORES = st.lists(st.integers(min_value=0, max_value=10**9), min_size=2, max_size=12)
PRIMEIRO_ANO = st.integers(min_value=2025, max_value=2040)
CONFIGURACAO = settings(
    max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)


@CONFIGURACAO
@given(PRIMEIRO_ANO, VALORES)
def test_le_de_volta_qualquer_tabela_de_anos_nas_linhas(primeiro_ano, valores):
    linhas = "\n".join(
        f"{primeiro_ano + i} {_brasileiro(v)}" for i, v in enumerate(valores)
    )
    texto = f"Cronograma de vencimentos\n{linhas}\nTotal {_brasileiro(sum(valores))}\n"
    cronograma = _um(texto)
    assert cronograma.series[0].valores == tuple(float(v) for v in valores)
    assert cronograma.series[0].confere


@CONFIGURACAO
@given(PRIMEIRO_ANO, VALORES.filter(lambda v: len(v) >= 3))
def test_le_de_volta_qualquer_tabela_de_anos_nas_colunas(primeiro_ano, valores):
    anos = " ".join(str(primeiro_ano + i) for i in range(len(valores)))
    numeros = " ".join(_brasileiro(v) for v in valores)
    texto = f"{anos} Total\nDívida {numeros} {_brasileiro(sum(valores))}\n"
    cronograma = _um(texto)
    assert cronograma.series[0].valores == tuple(float(v) for v in valores)
    assert cronograma.series[0].confere
