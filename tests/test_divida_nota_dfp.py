"""Leitura por regra do cronograma de vencimentos da nota de endividamento (B-21, PR 2)."""

import json
from datetime import date

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.divida.nota_dfp import (
    FONTE_DA_NOTA,
    CronogramaDaNota,
    escala_do_texto,
    faixas_da_coluna,
    ler_cronogramas,
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


def _um(texto: str, **kwargs) -> CronogramaDaNota:
    cronogramas = ler_cronogramas(texto, DOCUMENTO, **kwargs)
    assert len(cronogramas) == 1
    return cronogramas[0]


def test_le_a_tabela_com_rotulos_colunas_e_total():
    cronograma = _um(NOTA)
    assert [(lin.ano_inicial, lin.ano_final) for lin in cronograma.linhas] == [
        (2026, 2026),
        (2027, 2027),
        (2028, 2029),
        (2030, None),
    ]
    assert [lin.rotulo for lin in cronograma.linhas] == [
        "2026",
        "2027",
        "2028 a 2029",
        "2030 em diante",
    ]
    assert cronograma.linhas[2].valores == (50_000.0, 0.0)  # "-" é zero
    assert cronograma.linhas[3].valores == (1_000.0, -500.0)  # "(500)" é negativo
    assert cronograma.total == (351_000.0, 550_000.0)
    assert cronograma.confere == (True, True)
    assert cronograma.escala == 1_000.0
    assert cronograma.cabecalho == ("Controladora Consolidado", "2024 2024")
    assert "cronograma de vencimentos" in cronograma.titulo


def test_faixas_da_coluna_em_reais_e_com_rastro():
    faixas = faixas_da_coluna(_um(NOTA), coluna=1)
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


def test_coluna_que_nao_bate_com_o_total_fica_nao_observada():
    errada = NOTA.replace("Total 351.000 550.000", "Total 351.000 999.999")
    cronograma = _um(errada)
    assert cronograma.confere == (True, False)
    assert {f.valor_na_nota for f in faixas_da_coluna(cronograma, 1)} == {None}
    assert faixas_da_coluna(cronograma, 0)[0].valor_na_nota == 100_000.0


def test_arredondamento_de_uma_unidade_por_linha_ainda_confere():
    assert _um(NOTA.replace("351.000", "351.003")).confere[0]  # 4 linhas, folga de 4
    assert not _um(NOTA.replace("351.000", "351.005")).confere[0]


def test_sem_linha_total_nada_confere():
    sem_total = NOTA.replace("Total 351.000 550.000\n", "")
    cronograma = _um(sem_total)
    assert cronograma.total == ()
    assert cronograma.confere == ()
    assert {f.valor_na_nota for f in faixas_da_coluna(cronograma, 0)} == {None}


def test_linhas_com_tamanhos_diferentes_nao_conferem():
    torta = NOTA.replace("2027 200.000 300.500", "2027 300.500")
    assert _um(torta).confere == (False, False)


def test_sem_escala_o_valor_em_reais_nao_e_observado():
    sem_escala = NOTA.replace("(Em milhares de reais)\n", "")
    cronograma = _um(sem_escala)
    assert cronograma.escala is None
    faixa = faixas_da_coluna(cronograma, 0)[0]
    assert faixa.valor_na_nota == 100_000.0
    assert faixa.valor_em_reais is None
    # a escala da capa do documento vale quando a nota não diz
    assert _um(sem_escala, escala=1_000.0).escala == 1_000.0


def test_escala_pela_frase():
    assert escala_do_texto("Valores em R$ mil") == 1_000.0
    assert escala_do_texto("(Em milhões de reais)") == 1_000_000.0
    assert escala_do_texto("em milhares de reais ... em milhões de reais") is None
    assert escala_do_texto("sem frase de escala") is None


def test_outros_rotulos_de_periodo_e_traco_longo():
    texto = """Cronograma de amortização
Após 2030 10
A partir de 2031 20
2028–2029 30
2030 e seguintes 40
Total 100
"""
    linhas = _um(texto).linhas
    assert [(lin.ano_inicial, lin.ano_final) for lin in linhas] == [
        (2031, None),
        (2031, None),
        (2028, 2029),
        (2030, None),
    ]


def test_numero_com_decimais():
    texto = "Vencimentos\n2026 1.234,50\n2027 765,50\nTotal 2.000,00\n"
    cronograma = _um(texto)
    assert cronograma.linhas[0].valores == (1_234.5,)
    assert cronograma.confere == (True,)


def test_duas_tabelas_no_mesmo_texto():
    texto = NOTA + "\nVencimentos das debêntures\n2026 10\n2027 20\nTotal 30\n"
    cronogramas = ler_cronogramas(texto, DOCUMENTO)
    assert len(cronogramas) == 2
    assert cronogramas[1].total == (30.0,)


def test_titulo_sem_tabela_e_linha_com_texto_nao_viram_tabela():
    texto = (
        "O vencimento antecipado não ocorreu.\n"
        "Em 2026 a companhia pagou juros.\n"
        "Nenhuma tabela aqui.\n"
    )
    assert ler_cronogramas(texto, DOCUMENTO) == ()


def test_cabecalho_comprido_demais_nao_abre_tabela():
    texto = "Cronograma\n" + "linha de texto\n" * 9 + "2026 10\nTotal 10\n"
    assert ler_cronogramas(texto, DOCUMENTO) == ()


def test_como_dict_vira_json():
    json.dumps(_um(NOTA).como_dict())


def _brasileiro(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.integers(min_value=2025, max_value=2040),
    st.lists(st.integers(min_value=0, max_value=10**9), min_size=1, max_size=12),
)
def test_le_de_volta_qualquer_tabela_bem_escrita(primeiro_ano, valores):
    linhas = "\n".join(
        f"{primeiro_ano + i} {_brasileiro(v)}" for i, v in enumerate(valores)
    )
    texto = f"Cronograma de vencimentos\n{linhas}\nTotal {_brasileiro(sum(valores))}\n"
    cronograma = _um(texto)
    assert [lin.valores[0] for lin in cronograma.linhas] == [float(v) for v in valores]
    assert cronograma.confere == (True,)
