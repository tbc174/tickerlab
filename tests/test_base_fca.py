"""Código permanente da ação (série 3 da base de ML, PR 3): FCA da CVM e o emissor do ISIN.

Amostras reais recortadas (`tests/arquivos/cvm/fca/`: Petrobras, Via, CSN, Itaú e BTG nos FCA de
2010, 2018, 2021 e 2026, com o arquivo de valores mobiliários e o principal, que traz a data de entrega
de cada versão). Achados do inventário de 14/10/2026: até 2017 o FCA não traz ticker; a troca de
ticker regrava a mesma linha (a Via foi VVAR3, VIIA3 e BHIA3 com a mesma data de início); a CSN
informa "4030" no lugar do ticker. Série 4, PR 1: a CVM publica os valores mobiliários só da versão
mais nova de cada formulário, e a data que vale é a entrega dessa versão (`DT_RECEB`).
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import fca
from base.cadastro import tickers_dos_valores, tickers_no_tempo

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fca"
PETROBRAS, VIA, CSN, ITAU, BTG = (
    "33.000.167/0001-01",
    "33.041.260/0652-90",
    "33.042.730/0001-04",
    "60.872.504/0001-23",
    "30.306.294/0001-45",
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
    assert set(tabela["cnpj"]) <= {PETROBRAS, VIA, CSN, ITAU, BTG}


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


def _tickers_das_amostras() -> pd.DataFrame:
    return tickers_no_tempo(
        [
            (PASTA / f"fca_cia_aberta_{a}.zip").read_bytes()
            for a in (2010, 2018, 2021, 2026)
        ]
    )


def test_ticker_trocado_resolve_pela_data():
    """A Via foi VVAR3 (FCA de 2018), VIIA3 (2021) e BHIA3 (2026): cada um vale depois da entrega do
    formulário que o trouxe, sempre para o mesmo CNPJ."""
    tickers = _tickers_das_amostras()
    assert fca.resolver_ticker(tickers, "VVAR3", date(2019, 6, 30)) == VIA
    assert fca.resolver_ticker(tickers, "VIIA3", date(2022, 6, 30)) == VIA
    assert fca.resolver_ticker(tickers, "BHIA3", date(2026, 6, 30)) == VIA
    assert fca.resolver_ticker(tickers, "VVAR3", date(2026, 6, 30)) is None
    assert fca.resolver_ticker(tickers, "BHIA3", date(2019, 6, 30)) is None


# --- data de entrega do FCA (série 4, PR 1): o FCA de um ano chega meses depois da data de
# referência (mediana de 138 dias de 2010 a 2026); valer pelo ano olhava o futuro
def test_cada_linha_tem_a_data_de_entrega(valores):
    """`recebido_em` é o `DT_RECEB` do documento da linha (`ID_Documento` = `ID_DOC`)."""
    assert valores["recebido_em"].notna().all()
    por_documento = valores.drop_duplicates("id_documento").set_index("id_documento")
    assert por_documento.loc["156276", "recebido_em"] == pd.Timestamp("2026-04-17")
    # o Itaú entregou duas versões do FCA de 2026; a CVM publica os valores só da 2ª (08/05), e
    # é a data dela que vale, não a da 1ª (09/04)
    itau = valores.query("cnpj == @ITAU and referencia.dt.year == 2026")
    assert set(itau["id_documento"]) == {"156921"}
    assert set(itau["recebido_em"]) == {pd.Timestamp("2026-05-08")}


def test_ticker_so_vale_depois_da_entrega_do_fca():
    """O VIIA3 veio no FCA de 2021 da Via, versão 4, entregue em 30/12/2021: antes disso, quem valia
    era o VVAR3. E o VVAR3 só vale da entrega da versão 5 do FCA de 2018 (28/02/2019), a única cujo
    conteúdo a CVM publica: pelo ano, valeria em 2018 inteiro, com o que só se soube em 2019."""
    tickers = _tickers_das_amostras()
    assert fca.resolver_ticker(tickers, "VIIA3", date(2021, 12, 29)) is None
    assert fca.resolver_ticker(tickers, "VVAR3", date(2021, 12, 29)) == VIA
    assert fca.resolver_ticker(tickers, "VIIA3", date(2021, 12, 30)) == VIA
    assert fca.resolver_ticker(tickers, "VVAR3", date(2021, 12, 30)) is None
    assert fca.resolver_ticker(tickers, "VVAR3", date(2019, 2, 27)) is None
    assert fca.resolver_ticker(tickers, "VVAR3", date(2019, 2, 28)) == VIA
    via = tickers[tickers["cnpj"] == VIA].set_index("codigo")
    assert via.loc["VVAR3", "primeiro_visto"] == pd.Timestamp("2019-02-28")
    assert via.loc["VVAR3", "valido_ate"] == pd.Timestamp("2021-12-30")
    assert pd.isna(via.loc["BHIA3", "valido_ate"])  # ainda no FCA mais recente


def test_fca_sem_o_arquivo_principal_e_erro():
    """Sem a data de entrega não há "como era na data": melhor parar do que valer pelo ano."""
    import io
    import zipfile

    with zipfile.ZipFile(PASTA / "fca_cia_aberta_2026.zip") as original:
        nome = "fca_cia_aberta_valor_mobiliario_2026.csv"
        conteudo = original.read(nome)
    so_valores = io.BytesIO()
    with zipfile.ZipFile(so_valores, "w") as arquivo:
        arquivo.writestr(nome, conteudo)
    with pytest.raises(ValueError, match="principal"):
        fca.ler_valores_mobiliarios(so_valores.getvalue())


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


# --- versões antigas do FCA (achado da série 4): a CVM publica os valores mobiliários só da versão
# mais nova de cada formulário; as anteriores vêm do documento de cada versão no sistema de documentos
# da CVM (RAD). Amostras: as versões 1 (20/05/2021, VVAR3) e 3 (01/10/2021, VIIA3) do FCA 2021 da Via,
# só com o XML de valores mobiliários
VERSOES = PASTA / "versoes"


def _documentos_de_2021() -> pd.DataFrame:
    zip_2021 = (PASTA / "fca_cia_aberta_2021.zip").read_bytes()
    return fca.documentos(zip_2021).set_index("id_documento", drop=False)


def _versao(id_documento: str) -> pd.DataFrame:
    conteudo = (VERSOES / f"fca_versao_{id_documento}.zip").read_bytes()
    return fca.ler_documento_da_versao(
        conteudo, _documentos_de_2021().loc[id_documento]
    )


def test_documentos_do_arquivo_principal_tem_todas_as_versoes():
    via = _documentos_de_2021().query("cnpj == @VIA")
    assert via["versao"].tolist() == [1, 2, 3, 4]
    assert via.loc["108846", "recebido_em"] == pd.Timestamp("2021-10-01")


def test_le_o_documento_da_versao():
    linhas = _versao("104636")
    assert list(linhas.columns) == list(fca.COLUNAS)
    acao = linhas[linhas["ticker"].notna()].iloc[0]
    assert [acao[c] for c in ("ticker", "mercado", "administradora", "segmento")] == [
        "VVAR3",
        "Bolsa",
        "B3",
        "Novo Mercado",
    ]
    assert acao["valor_mobiliario"] == "Ações Ordinárias"
    assert acao["inicio_negociacao"] == pd.Timestamp("2018-11-26")
    assert pd.isna(acao["fim_negociacao"])  # 0001-01-01 no XML é vazio
    assert set(linhas["recebido_em"]) == {pd.Timestamp("2021-05-20")}
    assert set(linhas["versao"]) == {1} and set(linhas["cnpj"]) == {VIA}
    assert set(linhas["origem"]) == {fca.PELO_DOCUMENTO_DA_VERSAO}


def test_versao_antiga_antecipa_a_troca_de_ticker(valores):
    """A Via passou a informar VIIA3 na versão 3 do FCA de 2021 (01/10/2021). Só com a versão que a
    CVM publica (a 4, de 30/12/2021), a troca valia três meses depois."""
    todas = fca.juntar_versoes(
        valores, pd.concat([_versao("104636"), _versao("108846")])
    )
    tickers = tickers_dos_valores(todas)
    assert fca.resolver_ticker(tickers, "VVAR3", date(2021, 9, 30)) == VIA
    assert fca.resolver_ticker(tickers, "VIIA3", date(2021, 9, 30)) is None
    assert fca.resolver_ticker(tickers, "VIIA3", date(2021, 10, 1)) == VIA
    assert fca.resolver_ticker(tickers, "VVAR3", date(2021, 10, 1)) is None


def test_versao_que_os_dados_abertos_ja_tem_nao_entra_duas_vezes(valores):
    publicada = valores[valores["id_documento"] == "111029"].assign(
        origem=fca.PELO_DOCUMENTO_DA_VERSAO
    )
    todas = fca.juntar_versoes(valores, publicada)
    assert len(todas) == len(valores)
    assert set(todas["origem"]) == {fca.PELOS_DADOS_ABERTOS}


def test_versoes_a_buscar_so_nos_anos_com_troca_de_codigo(valores):
    """Só vale buscar (a CVM limita os downloads) as versões substituídas de anos em que o código
    da empresa mudou: a Via trocou de código de 2018 para 2021 e de 2021 para 2026; a Petrobras não."""
    zips = [
        (PASTA / f"fca_cia_aberta_{a}.zip").read_bytes() for a in (2018, 2021, 2026)
    ]
    documentos = pd.concat([fca.documentos(z) for z in zips], ignore_index=True)
    alvo = fca.versoes_a_buscar(documentos, valores)
    via = set(alvo.loc[alvo["cnpj"] == VIA, "id_documento"])
    assert {"104636", "108298", "108846"} <= via  # versões 1 a 3 de 2021
    assert "111029" not in via  # a versão 4 já está nos dados abertos
    assert PETROBRAS not in set(alvo["cnpj"])
    assert (alvo["referencia"].dt.year >= fca.PRIMEIRO_ANO_COM_TICKER).all()
    assert fca.URL_DA_VERSAO.format(id_documento="108846", versao=3) in set(alvo["url"])


def test_linhas_iguais_do_mesmo_documento_continuam(valores):
    """Duas séries de debêntures iguais no mesmo documento são duas linhas: juntar as versões e as
    baixadas não pode apagá-las (achado ao recarregar no servidor: 13.066 viraram 12.982 linhas)."""
    repetida = valores.iloc[[0]]
    abertos = pd.concat([valores, repetida], ignore_index=True)
    assert len(fca.juntar_versoes(abertos, valores.iloc[0:0])) == len(abertos)
    mais_nova, mais_antiga = abertos, abertos.iloc[: len(valores) // 2]
    juntas = fca.sem_documento_repetido([mais_nova, mais_antiga])
    assert len(juntas) == len(
        abertos
    )  # cada documento vem de uma baixada só, com todas as linhas
