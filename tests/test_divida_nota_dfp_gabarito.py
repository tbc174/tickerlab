"""Aceite da B-21: a leitura da nota da dívida bate com o gabarito de 5 emissores (DFP de 2025).

Os trechos estão em `dados_de_exemplo/notas_da_divida/` (o LEIAME diz de onde veio cada um e qual
tabela e série conferir). Os números abaixo foram digitados à mão, olhando a nota, não copiados da
saída do leitor.
"""

from datetime import date
from pathlib import Path

import pytest

from src.divida.nota_dfp import (
    CronogramaDaNota,
    faixas_da_serie,
    ler_cronogramas,
    serie_do_total,
)
from src.rastro import DocumentoUsado

PASTA = Path(__file__).resolve().parent.parent / "dados_de_exemplo" / "notas_da_divida"
ENET = "http://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx"
MILHARES, MILHOES = 1_000.0, 1_000_000.0


def _cronogramas(
    arquivo: str, publicado_em: date, numero: int
) -> tuple[CronogramaDaNota, ...]:
    documento = DocumentoUsado(
        f"DFP de 31/12/2025, nota de endividamento ({arquivo})",
        publicado_em,
        f"{ENET}?CodigoInstituicao=1&NumeroSequencialDocumento={numero}",
    )
    texto = (PASTA / arquivo).read_text(encoding="utf-8")
    return ler_cronogramas(texto, documento)


def _faixas(
    cronograma: CronogramaDaNota, serie: int
) -> list[tuple[int, int | None, float]]:
    faixas = faixas_da_serie(cronograma, serie)
    assert all(f.rastro.o_que_falta() == [] for f in faixas)
    return [(f.ano_inicial, f.ano_final, f.valor_na_nota) for f in faixas]


def _serie(cronograma: CronogramaDaNota, rotulo: str) -> int:
    return next(j for j, s in enumerate(cronograma.series) if s.rotulo == rotulo)


def test_cpfl_emprestimos_e_debentures_pelo_ocr():
    emprestimos, debentures = _cronogramas(
        "cpfl-2025-ocr.txt", date(2026, 3, 5), 155108
    )
    assert emprestimos.escala == debentures.escala == MILHARES
    assert _faixas(emprestimos, 0) == [
        (2027, 2027, 3_060_533),
        (2028, 2028, 2_372_998),
        (2029, 2029, 286_171),
        (2030, 2030, 185_074),
        (2031, 2031, 114_494),
        (2032, 2036, 318_854),
        (2037, 2041, 133_811),
        (2042, 2046, 16_352),
    ]
    assert (
        emprestimos.series[0].total == 6_488_287
    )  # o Subtotal, antes da marcação a mercado
    assert _faixas(debentures, 0) == [
        (2027, 2027, 383_686),
        (2028, 2028, 1_152_796),
        (2029, 2029, 4_016_207),
        (2030, 2030, 2_311_754),
        (2031, 2031, 2_246_489),
        (2032, 2036, 7_463_467),
        (2037, 2041, 377_687),
    ]
    assert debentures.series[0].total == 17_952_086


def test_localiza_coluna_do_consolidado_em_2025():
    (cronograma,) = _cronogramas("localiza-2025.txt", date(2026, 2, 26), 154953)
    assert cronograma.escala == MILHARES
    assert cronograma.contexto[-2:] == (
        "Individual Consolidado",
        "31/12/25 31/12/24 31/12/25 31/12/24",
    )
    consolidado_2025 = 2  # a terceira coluna
    assert _faixas(cronograma, consolidado_2025) == [
        (2025, 2025, 0),  # "-": nada vence no ano que já passou
        (2026, 2026, 4_585_163),
        (2027, 2027, 3_633_403),
        (2028, 2028, 7_977_422),
        (2029, 2034, 27_399_350),
    ]
    assert cronograma.series[consolidado_2025].total == 43_595_338
    assert all(serie.confere for serie in cronograma.series)  # as 4 colunas conferem


def test_petrobras_total_da_nota_30_4():
    (cronograma,) = _cronogramas("petrobras-2025.txt", date(2026, 3, 5), 155122)
    assert cronograma.escala == MILHOES
    total = serie_do_total(cronograma)
    assert total is not None
    assert cronograma.series[total].rotulo == "Total em 31 de dezembro de 2025"
    assert _faixas(cronograma, total) == [
        (2026, 2026, 12_026),
        (2027, 2027, 11_841),
        (2028, 2028, 9_964),
        (2029, 2029, 11_537),
        (2030, 2030, 17_608),
        (2031, None, 82_513),
    ]
    assert (
        cronograma.series[total].total == 145_489
    )  # o valor justo (142.557) fica fora


def test_sabesp_cronograma_com_ano_repetido_fica_de_fora_e_vale_a_tabela_de_liquidez():
    cronogramas = _cronogramas("sabesp-2025.txt", date(2026, 3, 30), 155830)
    # o trecho tem três tabelas; o cronograma de liquidação (com "2031" e "2031 até 2048") não entra
    assert [c.contexto[-1] for c in cronogramas] == ["Controladora", "Consolidado"]
    consolidado = cronogramas[1]
    assert consolidado.escala == MILHARES
    emprestimos = _serie(consolidado, "Empréstimos e financiamentos")
    assert _faixas(consolidado, emprestimos) == [
        (2026, 2026, 5_092_816),
        (2027, 2027, 2_259_452),
        (2028, 2028, 1_794_449),
        (2029, 2029, 4_172_569),
        (2030, 2030, 7_336_464),
        (2031, 2048, 19_486_597),
    ]
    assert (
        consolidado.series[emprestimos].total == 40_142_347
    )  # o Total Geral do cronograma


def test_vale_principal_do_consolidado():
    (cronograma,) = _cronogramas("vale-2025.txt", date(2026, 3, 12), 155313)
    assert cronograma.escala == MILHOES
    principal_consolidado = 0
    assert _faixas(cronograma, principal_consolidado) == [
        (2026, 2026, 1_776),
        (2027, 2027, 9_352),
        (2028, 2028, 5_426),
        (2029, 2029, 19_024),
        (2030, 2032, 19_708),
        (2033, None, 43_420),
    ]
    assert cronograma.series[principal_consolidado].total == 98_706


@pytest.mark.parametrize(
    "arquivo",
    [
        "cpfl-2025-ocr.txt",
        "localiza-2025.txt",
        "petrobras-2025.txt",
        "sabesp-2025.txt",
        "vale-2025.txt",
    ],
)
def test_o_rastro_aponta_o_documento_da_cvm(arquivo):
    for cronograma in _cronogramas(arquivo, date(2026, 3, 1), 1):
        assert cronograma.rastro.documentos[0].url.startswith(ENET)
        assert cronograma.rastro.publicado_em == date(2026, 3, 1)
