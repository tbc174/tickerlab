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


# --- códigos fora do formato no FCA, conferidos um a um (série 3, PR 8): o BTG informa "000000" nas
# units e por isso ficava sem ticker, sem emissor e sem ligação com o IF.data e com os fundos
BTG = "30.306.294/0001-45"


def test_tabela_de_codigos_conferidos_e_valida():
    from base.fidc import documento_de_empresa

    tabela = fca.codigos_conferidos()
    assert tabela["codigo"].is_unique
    assert tabela["codigo"].map(fca.ticker_do_codigo).eq(tabela["codigo"]).all()
    assert (tabela["cnpj"].map(documento_de_empresa) == tabela["cnpj"]).all()
    # o ISIN do CDA é a prova: o emissor dele é o mesmo do código
    assert (
        tabela["isin"].map(fca.emissor_do_isin)
        == tabela["codigo"].map(fca.emissor_do_codigo)
    ).all()
    assert (tabela["primeiro_no_cda"] <= tabela["ultimo_no_cda"]).all()
    for coluna in (
        "empresa",
        "valor_mobiliario",
        "codigo_no_fca",
        "observacao",
        "fonte",
    ):
        assert tabela[coluna].str.len().gt(0).all(), coluna
    assert tabela["conferido_em"].notna().all()


def test_btg_entra_pelos_codigos_conferidos(valores):
    tickers, emissores = fca.com_codigos_conferidos(
        tickers_no_tempo([(PASTA / "fca_cia_aberta_2026.zip").read_bytes()]),
        fca.emissores(valores),
        fca.codigos_conferidos(),
    )
    assert fca.resolver_ticker(tickers, "BPAC11", date(2025, 6, 30)) == BTG
    assert (
        fca.resolver_ticker(tickers, "BPAC11", date(2018, 6, 30)) is None
    )  # antes do 1º no CDA
    assert fca.resolver_emissor(emissores, "BPAC") == BTG
    origem = emissores.set_index("emissor")["origem"]
    assert origem["BPAC"] == fca.PELOS_CODIGOS_CONFERIDOS
    assert origem["PETR"] == fca.PELO_FCA
    assert set(tickers.loc[tickers["cnpj"] == BTG, "codigo"]) == {
        "BPAC11",
        "BPAC3",
        "BPAC5",
    }
    # o que o FCA já trazia não muda
    assert fca.resolver_emissor(emissores, "PETR") == PETROBRAS


def test_codigo_conferido_que_o_fca_ja_tem_fica_uma_linha_so(valores):
    tickers = tickers_no_tempo([(PASTA / "fca_cia_aberta_2026.zip").read_bytes()])
    petr4 = tickers[tickers["codigo"] == "PETR4"].iloc[0]
    repetido = pd.DataFrame(
        [
            {
                "codigo": "PETR4", "cnpj": PETROBRAS, "empresa": "PETROBRAS",
                "valor_mobiliario": "Ações Preferenciais",
                "primeiro_no_cda": pd.Timestamp("2005-01-31"),
                "ultimo_no_cda": pd.Timestamp("2026-09-30"),
            }
        ]
    )  # fmt: skip
    juntos, emissores = fca.com_codigos_conferidos(
        tickers, fca.emissores(valores), repetido
    )
    linhas = juntos[juntos["codigo"] == "PETR4"]
    assert len(linhas) == 1 and linhas["origem"].iloc[0] == fca.PELO_FCA
    assert linhas["primeiro_visto"].iloc[0] == petr4["primeiro_visto"]
    assert len(emissores[emissores["emissor"] == "PETR"]) == 1


def test_codigo_conferido_com_outro_cnpj_no_fca_e_conflito(valores):
    """Nada é casado no escuro: se a tabela conferida e o FCA discordam, ninguém fica com o código."""
    tickers = tickers_no_tempo([(PASTA / "fca_cia_aberta_2026.zip").read_bytes()])
    errado = pd.DataFrame(
        [
            {
                "codigo": "PETR4", "cnpj": "11.111.111/0001-11", "empresa": "OUTRA",
                "valor_mobiliario": "Ações Preferenciais",
                "primeiro_no_cda": pd.Timestamp("2025-01-31"),
                "ultimo_no_cda": pd.Timestamp("2026-09-30"),
            }
        ]
    )  # fmt: skip
    juntos, emissores = fca.com_codigos_conferidos(
        tickers, fca.emissores(valores), errado
    )
    assert fca.resolver_ticker(juntos, "PETR4", date(2026, 6, 30)) is None
    assert fca.resolver_emissor(emissores, "PETR") is None
