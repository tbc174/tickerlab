"""Posições nos futuros de Bitcoin da CME, do relatório TFF da CFTC (base de cripto, série 1, PR 3).

A amostra (`tests/arquivos/cripto/cftc/FinFutYY_amostra.txt`) é o cabeçalho e 5 linhas reais do
arquivo de 2026 (`fut_fin_txt_2026.zip`), baixado em 13/10/2026: Bitcoin e Micro Bitcoin em duas
semanas, e um contrato que não é de cripto.
"""

import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

from base.cripto.cftc import divulgado_em, endereco_do_ano, ler_tff

AMOSTRA = (
    Path(__file__).parent / "arquivos" / "cripto" / "cftc" / "FinFutYY_amostra.txt"
)


def _zip_da_amostra() -> bytes:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as arquivo:
        arquivo.writestr("FinFutYY.txt", AMOSTRA.read_bytes())
    return memoria.getvalue()


def test_le_so_os_futuros_de_bitcoin_da_cme():
    tabela = ler_tff(_zip_da_amostra())

    assert sorted(tabela["contrato"].unique()) == ["bitcoin", "micro_bitcoin"]
    assert len(tabela) == 4


def test_posicoes_da_semana():
    tabela = ler_tff(_zip_da_amostra()).set_index(["relatorio", "contrato"])

    linha = tabela.loc[(date(2026, 10, 6), "bitcoin")]
    assert linha["contratos_em_aberto"] == 21_432
    assert linha["gestores_comprados"] == 5_174
    assert linha["gestores_vendidos"] == 1_642
    assert linha["alavancados_comprados"] == 5_731
    assert linha["alavancados_vendidos"] == 12_583


def test_relatorio_so_vale_na_segunda_seguinte_as_15h30_de_nova_york():
    # terça 06/10/2026 → segunda 12/10/2026, 15h30 de Nova York (horário de verão, UTC-4)
    assert divulgado_em(date(2026, 10, 6)) == datetime(2026, 10, 12, 19, 30, tzinfo=UTC)
    # no inverno, UTC-5
    assert divulgado_em(date(2026, 1, 20)) == datetime(2026, 1, 26, 20, 30, tzinfo=UTC)


def test_excecao_de_divulgacao_vale_mais_que_a_regra():
    atrasado = datetime(2025, 11, 19, 20, 30, tzinfo=UTC)

    assert divulgado_em(date(2025, 9, 30), {date(2025, 9, 30): atrasado}) == atrasado


def test_tabela_traz_divulgado_em_de_cada_linha():
    tabela = ler_tff(_zip_da_amostra())

    assert (tabela["divulgado_em"] == tabela["relatorio"].map(divulgado_em)).all()


def test_endereco_do_arquivo_anual():
    assert (
        endereco_do_ano(2026)
        == "https://www.cftc.gov/files/dea/history/fut_fin_txt_2026.zip"
    )
