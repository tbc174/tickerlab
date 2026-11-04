"""F-B3: a rodada completa com dados sintéticos e um registro temporário, e o carregador da base."""

import zipfile

import pandas as pd
import pytest

from tests.ajudantes_f_b3 import (
    CNPJS,
    DESLISTADA,
    dados_sinteticos,
    variar_balancos_por_ano,
)
from trader import criterio_quant
from trader.estrategias import dados_f_b3
from trader.estrategias import rodar_f_b3 as rodar

# A rodada do fixture de módulo demora; num processo só ela roda uma vez (CI com --dist loadgroup).
pytestmark = pytest.mark.xdist_group("f_b3")
# Quatro anos bastam para 12 meses de pregão e de balanço antes da primeira decisão (2017).
DATAS_CURTAS = pd.bdate_range("2016-01-04", "2019-12-30")


def _dados(com_deslistada=True):
    return variar_balancos_por_ano(
        dados_sinteticos(com_deslistada=com_deslistada, datas=DATAS_CURTAS)
    )


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    registro = rodar.abrir_registro(tmp_path_factory.mktemp("f_b3") / "registro.db")
    dados = _dados()
    saida = rodar.executar(dados, registro)
    return dados, registro, saida


def test_registra_uma_tentativa_na_familia_f_b3(rodada):
    _, registro, saida = rodada
    assert registro.contar() == 1
    guardado = registro.obter(saida["id"])
    assert guardado["familia"] == "F-B3"
    assert guardado["spec"]["pre_registro"] == criterio_quant.HASH_DO_CRITERIO
    assert guardado["spec"]["quintil"] == 0.2
    assert guardado["resultado"]["veredito"]["itens"]
    assert guardado["resultado"]["vizinhos"]  # o platô fica dentro da tentativa
    assert guardado["resultado"]["sobrevivencia"]["deslistadas"] == 1


def test_rodar_de_novo_nao_conta_tentativa_nova(rodada):
    dados, registro, _ = rodada
    rodar.executar(dados, registro)
    assert registro.contar() == 1


def test_veredito_tem_os_itens_do_pre_registro(rodada):
    veredito = rodada[2]["veredito"]
    itens = {i.codigo: i for i in veredito.itens}
    assert list(itens) == ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "F1", "V"]
    assert itens["A2"].passou and itens["A2"].valor is None
    assert itens["V"].passou  # futuro infla, reexecução idêntica, dados conforme, corte


def test_teste_do_brasil_tem_as_tres_partes(rodada):
    brasil = rodada[2]["brasil"]
    assert set(brasil) == {"deslistadas", "carteiras", "balanco"}
    assert set(brasil["carteiras"]) == set(rodar.CARTEIRAS_DO_BRASIL)
    assert set(brasil["deslistadas"]) == {"com as deslistadas", "só sobreviventes"}
    assert all(
        {"sharpe", "retorno_anual", "maior_queda", "imposto"} <= set(v)
        for parte in brasil.values()
        for v in parte.values()
    )


def test_reguas_vizinhos_e_tentativas(rodada):
    saida = rodada[2]
    assert set(saida["reguas"]) == {"CDI"}  # sem BOVA11 nos dados sintéticos
    assert set(saida["vizinhos"]) == set(rodar.VIZINHOS)
    assert saida["tentativas_totais"] >= criterio_quant.tentativas_anteriores() + 1


def test_sem_deslistadas_o_veredito_reprova_por_dados(tmp_path):
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    saida = rodar.executar(_dados(com_deslistada=False), registro)
    assert saida["sobrevivencia"]["vies"]
    assert "sobrevivência" in saida["sobrevivencia"]["aviso"]
    assert not saida["veredito"].aprovado
    assert not {i.codigo: i for i in saida["veredito"].itens}["V"].passou
    texto = rodar.escrever_relatorio(saida, tmp_path).read_text(encoding="utf-8")
    assert "Viés de sobrevivência" in texto


def test_pre_registro_alterado_nao_roda_nem_registra(tmp_path, monkeypatch):
    def recusar(*_, **__):
        raise criterio_quant.PreRegistroAlteradoError("mudou")

    monkeypatch.setattr(rodar.criterio_quant, "conferir", recusar)
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    with pytest.raises(criterio_quant.PreRegistroAlteradoError):
        rodar.executar(_dados(), registro)
    assert registro.contar() == 0


def test_relatorio_e_escrito_com_limites_e_cuidados(rodada, tmp_path):
    caminho = rodar.escrever_relatorio(rodada[2], tmp_path)
    texto = caminho.read_text(encoding="utf-8")
    assert "Veredito dos fatores na B3" in texto
    assert "| F1 |" in texto and "| V |" in texto
    assert "teste do Brasil" in texto
    assert "isenção de R$ 20 mil" in texto
    assert "## Limites e cuidados" in texto
    assert "recomendação de investimento" in texto


# --- a base ---------------------------------------------------------------------------------------


def test_conferir_base_lista_tudo_o_que_falta(tmp_path):
    faltas = dados_f_b3.conferir_base(tmp_path)
    assert faltas[0] == "COTAHIST_A2009.ZIP"
    assert "COTAHIST_A2023.ZIP" in faltas
    assert {"precos_ajustados.parquet", "acoes_em_circulacao.parquet"} <= set(faltas)
    assert len(faltas) == 15 + 2
    (tmp_path / "COTAHIST_A2009.ZIP").write_bytes(b"")
    assert "COTAHIST_A2009.ZIP" not in dados_f_b3.conferir_base(tmp_path)


def test_main_sem_base_e_inconclusiva_e_nao_abre_o_registro(
    tmp_path, monkeypatch, capsys
):
    def nao_abrir(*_, **__):
        raise AssertionError("o registro não pode ser aberto sem a base")

    monkeypatch.setattr(rodar, "abrir_registro", nao_abrir)
    assert rodar.main(tmp_path) == rodar.SAIDA_SEM_BASE
    saida = capsys.readouterr().out
    assert saida.startswith("INCONCLUSIVA")
    assert "COTAHIST_A2009.ZIP" in saida


def _registro_cotahist(
    data, ticker, mercado, especificacao, abertura, fechamento, volume, isin
):
    linha = [" "] * 245
    campos = {
        "tipo": "01",
        "data": data,
        "ticker": f"{ticker:<12}",
        "mercado": mercado,
        "especificacao": f"{especificacao:<10}",
        "abertura": f"{abertura:013d}",
        "fechamento": f"{fechamento:013d}",
        "volume": f"{volume:018d}",
        "isin": isin,
    }
    for nome, valor in campos.items():
        inicio, fim = dados_f_b3.CAMPOS[nome]
        linha[inicio:fim] = list(valor)
    return "".join(linha)


def _zip_cotahist(tmp_path, linhas):
    caminho = tmp_path / "COTAHIST_A2020.ZIP"
    conteudo = "\n".join(
        ["00COTAHIST.2020BOVESPA".ljust(245), *linhas, "99".ljust(245)]
    )
    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.writestr("COTAHIST_A2020.TXT", conteudo.encode("latin-1"))
    return caminho


def test_ler_cotahist_anual_so_pega_o_mercado_a_vista_e_converte_centavos(tmp_path):
    linhas = [
        _registro_cotahist(
            "20200102", "AAA3", "010", "ON", 1000, 1050, 25_000_000, "BRAAAACNOR0"
        ),
        _registro_cotahist(
            "20200102", "AAA3F", "020", "ON", 1000, 1050, 100, "BRAAAACNOR0"
        ),
        _registro_cotahist(
            "20200103", "BBB4", "010", "PN N2", 2000, 1900, 50_000_000, "BRBBBBACNPR7"
        ),
    ]
    longo = dados_f_b3.ler_cotahist_anual(_zip_cotahist(tmp_path, linhas))
    assert list(longo["ticker"]) == ["AAA3", "BBB4"]
    assert longo.loc[0, "fechamento"] == 10.5
    assert longo.loc[0, "volume"] == 250_000.0
    assert longo.loc[1, "data"] == pd.Timestamp("2020-01-03")
    assert longo.loc[1, "especificacao"] == "PN N2"


def test_ler_cotahist_anual_divide_pelo_fator_de_cotacao(tmp_path):
    """Papel cotado por lote de mil (FATCOT 1000) vira preço por ação; o volume já vem em reais."""
    linha = list(
        _registro_cotahist(
            "20200102", "CCC3", "010", "ON", 250_000, 260_000, 500_000, "BRCCCCACNOR0"
        )
    )
    inicio, fim = dados_f_b3.CAMPOS["fator_de_cotacao"]
    linha[inicio:fim] = list("0001000")
    sem_fator = _registro_cotahist(
        "20200102", "DDD3", "010", "ON", 1000, 1050, 100, "BRDDDDACNOR0"
    )
    longo = dados_f_b3.ler_cotahist_anual(
        _zip_cotahist(tmp_path, ["".join(linha), sem_fator])
    )
    assert longo.loc[0, "abertura"] == 2.5
    assert longo.loc[0, "fechamento"] == 2.6
    assert longo.loc[0, "volume"] == 5_000.0
    assert longo.loc[1, "fechamento"] == 10.5  # campo vazio vale 1


def test_paineis_e_cadastro_pelo_isin(tmp_path):
    linhas = [
        _registro_cotahist(
            "20200102", "AAA3", "010", "ON", 1000, 1050, 1, "BRAAAACNOR0"
        ),
        _registro_cotahist(
            "20200103", "AAA3", "010", "ON", 1050, 1100, 1, "BRAAAACNOR0"
        ),
        _registro_cotahist(
            "20200102", "BBB4", "010", "PN N2", 2000, 1900, 1, "BRBBBBACNPR7"
        ),
    ]
    longo = dados_f_b3.ler_cotahist_anual(_zip_cotahist(tmp_path, linhas))
    fechamento, abertura, volume = dados_f_b3.paineis(longo)
    assert fechamento.shape == abertura.shape == volume.shape == (2, 2)
    assert pd.isna(fechamento.loc["2020-01-03", "BBB4"])
    emissores = pd.DataFrame(
        {"emissor": ["AAAA", "BBBB"], "cnpj": [CNPJS["AAA3"], CNPJS["BBB3"]]}
    )
    cadastro = dados_f_b3.cadastro_dos_tickers(longo, emissores)
    assert list(cadastro.columns) == list(dados_f_b3.COLUNAS_DO_CADASTRO)
    assert cadastro.loc["AAA3", "cnpj"] == CNPJS["AAA3"]
    assert cadastro.loc["BBB4", "classe"] == "PN"
    assert pd.isna(cadastro.loc["AAA3", "fim_negociacao"])  # negociava no último dia
    assert cadastro.loc["BBB4", "fim_negociacao"] == pd.Timestamp("2020-01-02")


def test_classe_da_especificacao():
    assert dados_f_b3.classe_da_especificacao("UNT N2") == "UNT"
    assert dados_f_b3.classe_da_especificacao("ON NM") == "ON"
    assert dados_f_b3.classe_da_especificacao("DIR PRE") == "outro"


def test_fundamentos_do_acervo_so_consolidado_e_contas_usadas():
    demonstracoes = pd.DataFrame(
        {
            "cnpj": [CNPJS[DESLISTADA]] * 3,
            "grupo": ["con", "ind", "con"],
            "demonstracao": ["DRE", "DRE", "DRE"],
            "conta": ["3.05", "3.05", "3.99"],
            "inicio": [pd.Timestamp("2020-01-01")] * 3,
            "fim": [pd.Timestamp("2020-12-31")] * 3,
            "valor": [1.0, 2.0, 3.0],
            "divulgado_em": [pd.Timestamp("2021-03-31")] * 3,
            "ate": [pd.NaT] * 3,
            "versao": [1, 1, 1],
        }
    )
    tabela = dados_f_b3.fundamentos_do_acervo(demonstracoes)
    assert len(tabela) == 1
    assert tabela.loc[0, "valor"] == 1.0
    assert list(tabela.columns) == list(dados_f_b3.COLUNAS_DOS_FUNDAMENTOS)


def test_ler_cotahist_anual_traz_o_numero_de_distribuicao(tmp_path):
    linha = list(
        _registro_cotahist(
            "20200102", "AAA3", "010", "ON", 1000, 1050, 100, "BRAAAACNOR0"
        )
    )
    inicio, fim = dados_f_b3.CAMPOS["distribuicao"]
    linha[inicio:fim] = list("107")
    longo = dados_f_b3.ler_cotahist_anual(_zip_cotahist(tmp_path, ["".join(linha)]))
    assert longo.loc[0, "distribuicao"] == "107"


def test_trocas_de_distribuicao_marcam_o_dia_em_que_o_numero_muda():
    longo = pd.DataFrame(
        {
            "data": pd.to_datetime(
                ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-02", "2020-01-06"]
            ),
            "ticker": ["AAA3", "AAA3", "AAA3", "BBB4", "BBB4"],
            "distribuicao": ["101", "101", "102", "200", "200"],
        }
    )
    trocas = dados_f_b3.trocas_de_distribuicao(longo)
    assert trocas.dtypes.eq(bool).all()
    assert trocas["AAA3"].tolist() == [False, False, True]
    assert not trocas["BBB4"].any()  # o primeiro dia de um papel não é troca


def test_emissores_antigos_completam_o_fca_sem_trocar_o_que_o_fca_diz():
    emissores = pd.DataFrame({"emissor": ["AAAA"], "cnpj": [CNPJS["AAA3"]]})
    antigos = pd.DataFrame(
        {
            "emissor": ["AAAA", "OLDD", "VAZI"],
            "cnpj": ["00.000.000/0000-00", CNPJS["BBB3"], None],
        }
    )
    juntos = dados_f_b3.emissores_com_antigos(emissores, antigos)
    por_emissor = juntos.set_index("emissor")["cnpj"]
    assert por_emissor["AAAA"] == CNPJS["AAA3"]
    assert por_emissor["OLDD"] == CNPJS["BBB3"]
    assert "VAZI" not in por_emissor.index


def test_tabela_dos_emissores_antigos():
    """Ligação pelo nome conferida por dois modelos: quem discordou fica sem CNPJ."""
    antigos = pd.read_csv(dados_f_b3.ARQUIVO_DOS_EMISSORES_ANTIGOS, dtype=str)
    assert list(antigos.columns) == list(dados_f_b3.COLUNAS_DOS_EMISSORES_ANTIGOS)
    assert antigos["emissor"].is_unique
    assert antigos["emissor"].str.fullmatch(r"[A-Z0-9]{4}").all()
    ligados = antigos["conferencia"] == "os dois modelos"
    assert (
        antigos.loc[ligados, "cnpj"]
        .str.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
        .all()
    )
    assert antigos.loc[~ligados, "cnpj"].isna().all()
    assert set(antigos["conferencia"]) <= {
        "os dois modelos",
        "discordaram",
        "nenhum achou",
    }
