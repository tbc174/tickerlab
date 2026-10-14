"""Código permanente da ação (série 3 da base de ML, PR 3): FCA da CVM e o emissor do ISIN.

Amostras reais recortadas (`tests/arquivos/cvm/fca/`: Petrobras, Via, CSN e Itaú nos FCA de 2010,
2018, 2021 e 2026). Achados do inventário de 14/10/2026: até 2017 o FCA não traz ticker; a troca de
ticker regrava a mesma linha (a Via foi VVAR3, VIIA3 e BHIA3 com a mesma data de início); a CSN
informa "4030" no lugar do ticker.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import fca
from base.cadastro import tickers_no_tempo

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fca"
PETROBRAS, VIA, CSN, ITAU = (
    "33.000.167/0001-01",
    "33.041.260/0652-90",
    "33.042.730/0001-04",
    "60.872.504/0001-23",
)


def _ler(ano: int) -> pd.DataFrame:
    return fca.ler_valores_mobiliarios(
        (PASTA / f"fca_cia_aberta_{ano}.zip").read_bytes()
    )


@pytest.fixture(scope="module")
def valores():
    return pd.concat([_ler(a) for a in (2010, 2018, 2021, 2026)], ignore_index=True)


@pytest.mark.parametrize("ano", [2010, 2018, 2021, 2026])
def test_le_valores_mobiliarios_de_cada_layout(ano):
    tabela = _ler(ano)
    assert list(tabela.columns) == list(fca.COLUNAS)
    assert set(tabela["referencia"].dt.year) == {ano}
    assert set(tabela["cnpj"]) <= {PETROBRAS, VIA, CSN, ITAU}


def test_ate_2017_o_fca_nao_traz_ticker():
    assert _ler(2010)["ticker"].isna().all()


def test_acoes_da_petrobras_com_ticker_e_especie():
    petrobras = _ler(2026).query("cnpj == @PETROBRAS and ticker.notna()")
    assert set(petrobras["ticker"]) == {"PETR3", "PETR4"}
    assert set(petrobras["emissor"]) == {"PETR"}


def test_codigo_fora_do_formato_nao_e_ticker(valores):
    """A CSN informa "4030": não vira ticker e vai para a lista de códigos inválidos."""
    assert valores.query("cnpj == @CSN")["ticker"].isna().all()
    invalidos = fca.codigos_invalidos(valores)
    assert {"4030"} <= set(invalidos.loc[invalidos["cnpj"] == CSN, "codigo_informado"])


@pytest.mark.parametrize(
    ("isin", "emissor"),
    [
        ("BRMAGSACNPC8", "MAGS"),  # Magnesita PN, CDA de 2005
        ("BRPETRACNPR6", "PETR"),
        ("BRITUBACNPR1", "ITUB"),
        ("PETR4", None),
        ("", None),
        (None, None),
    ],
)
def test_emissor_do_isin(isin, emissor):
    assert fca.emissor_do_isin(isin) == emissor


def test_emissor_resolve_o_cnpj(valores):
    emissores = fca.emissores(valores)
    assert fca.resolver_emissor(emissores, "PETR") == PETROBRAS
    assert fca.resolver_emissor(emissores, "ITUB") == ITAU
    assert {fca.resolver_emissor(emissores, e) for e in ("VVAR", "VIIA", "BHIA")} == {
        VIA
    }
    assert fca.resolver_emissor(emissores, "CSNA") is None  # sem ticker válido no FCA


def test_emissor_de_duas_empresas_e_conflito_e_nao_resolve(valores):
    """Nada é casado no escuro: um emissor com dois CNPJs fica sem resposta e é listado."""
    outra = valores.query("cnpj == @PETROBRAS").assign(cnpj="11.111.111/0001-11")
    emissores = fca.emissores(pd.concat([valores, outra], ignore_index=True))
    assert fca.resolver_emissor(emissores, "PETR") is None
    assert emissores.loc[emissores["emissor"] == "PETR", "conflito"].all()


def test_ticker_trocado_resolve_pela_data(valores):
    """A Via foi VVAR3 (FCA de 2018), VIIA3 (2021) e BHIA3 (2026): cada um vale nos anos em que foi
    informado, sempre para o mesmo CNPJ."""
    zips = [
        (PASTA / f"fca_cia_aberta_{a}.zip").read_bytes()
        for a in (2010, 2018, 2021, 2026)
    ]
    tickers = tickers_no_tempo(zips)
    assert fca.resolver_ticker(tickers, "VVAR3", date(2018, 6, 30)) == VIA
    assert fca.resolver_ticker(tickers, "VIIA3", date(2021, 6, 30)) == VIA
    assert fca.resolver_ticker(tickers, "BHIA3", date(2026, 6, 30)) == VIA
    assert fca.resolver_ticker(tickers, "VVAR3", date(2026, 6, 30)) is None
    assert fca.resolver_ticker(tickers, "BHIA3", date(2018, 6, 30)) is None


def test_fica_a_versao_mais_nova_de_cada_documento():
    tabela = _ler(2026)
    repetida = pd.concat(
        [tabela.assign(versao=1, segmento="antigo"), tabela.assign(versao=2)],
        ignore_index=True,
    )
    assert "antigo" not in set(fca.mais_novas(repetida)["segmento"])


# --- formato do código (série 3, PR 5): o emissor pode ter número (B3SA) e o código pode vir sem
# o número da classe (NEOE) ou com o sufixo de balcão (LTEL3B), como no FCA real
@pytest.mark.parametrize(
    ("codigo", "ticker", "emissor"),
    [
        ("PETR4", "PETR4", "PETR"),
        ("TAEE11", "TAEE11", "TAEE"),
        ("B3SA3", "B3SA3", "B3SA"),  # a própria B3 ficava de fora
        ("NEOE", None, "NEOE"),  # Neoenergia, FCA de 2019
        ("LTEL3B", None, "LTEL"),  # Litel, balcão
        ("4030", None, None),  # CSN
        ("NÃO HÁ", None, None),
        ("007424", None, None),
    ],
)
def test_ticker_e_emissor_pelo_codigo_informado(codigo, ticker, emissor):
    assert fca.ticker_do_codigo(codigo) == ticker
    assert fca.emissor_do_codigo(codigo) == emissor
