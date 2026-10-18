"""Séries do IBGE pelo SIDRA, sem internet: a URL de cada série, a leitura da resposta (com os
símbolos do SIDRA), o tipo do café no id, o total derivado e o corte do futuro."""

import json
from datetime import date
from pathlib import Path

import pytest

from src import ibge_sidra
from src.ibge_sidra import Valor

EXEMPLOS = Path(__file__).resolve().parent.parent / "dados_de_exemplo" / "ibge"


def _resposta(nome: str) -> list[dict]:
    return json.loads((EXEMPLOS / nome).read_text(encoding="utf-8"))


def _linha(valor: str, **campos: str) -> dict:
    base = {
        "NC": "1", "NN": "Brasil", "MC": "2", "MN": "%", "V": valor,
        "D1C": "1", "D1N": "Brasil", "D2C": "63", "D2N": "IPCA - Variação mensal",
        "D3C": "202607", "D3N": "julho 2026", "D4C": "7169", "D4N": "Índice geral",
    }  # fmt: skip
    return {**base, **campos}


CABECALHO = {"NC": "Nível Territorial (Código)", "V": "Valor"}


# --- URL de cada série ----------------------------------------------------------------------------
def test_url_da_lspa_do_cafe_por_uf():
    url = ibge_sidra.montar_url(
        6588, [35, 109], {48: [39454, 39455]}, "202601-202608", "n3/all"
    )
    assert url == (
        "https://apisidra.ibge.gov.br/values/t/6588/n3/all/v/35,109/p/202601-202608"
        "/c48/39454,39455"
    )


def test_url_da_pam_por_municipio_de_uma_uf():
    url = ibge_sidra.montar_url(
        1613, [216, 214], {82: [31619, 31620, 2723]}, "2020-2024", "n6/in n3 31"
    )
    assert url == (
        "https://apisidra.ibge.gov.br/values/t/1613/n6/in%20n3%2031/v/216,214/p/2020-2024"
        "/c82/31619,31620,2723"
    )


def test_url_sem_classificacao_e_com_varias():
    assert ibge_sidra.montar_url(8886, [1], {}, "last 3").endswith(
        "/t/8886/n1/all/v/1/p/last%203"
    )
    url = ibge_sidra.montar_url(8882, [7169], {11046: [56734], 85: [1, 2]}, "202601")
    assert url.endswith("/c11046/56734/c85/1,2")


@pytest.mark.parametrize("coleta", ibge_sidra.COLETAS, ids=lambda c: c.nome)
def test_cada_coleta_gera_url_com_a_tabela_e_as_variaveis(coleta):
    urls = coleta.urls("202601-202608")
    assert urls
    for url in urls:
        assert f"/t/{coleta.tabela}/" in url
        assert all(str(v) in url for v in coleta.variaveis)
        assert " " not in url  # espaços vão como %20


def test_as_tabelas_da_primeira_leva():
    assert {c.tabela for c in ibge_sidra.COLETAS} == {
        6588, 1613, 8880, 8881, 8888, 8887, 7060,
    }  # fmt: skip
    por_nome = ibge_sidra.COLETAS_POR_NOME
    assert por_nome["lspa"].tabela == 6588
    assert por_nome["pam-municipal"].frequencia == "anual"
    assert por_nome["pmc-restrito"].tabela == 8880
    assert por_nome["pmc-ampliado"].tabela == 8881


def test_pam_municipal_vai_uf_por_uf_para_caber_no_limite_do_sidra():
    urls = ibge_sidra.COLETAS_POR_NOME["pam-municipal"].urls("2020-2024")
    assert len(urls) >= 27
    assert all("n6/in%20n3%20" in u for u in urls)


# --- leitura da resposta ---------------------------------------------------------------------------
def test_le_a_resposta_real_do_ipca():
    valores = ibge_sidra.ler_resposta(_resposta("ipca_cafe.json"))
    assert len(valores) == 8
    cafe = [v for v in valores if v.categorias == (7392,) and v.variavel == 63]
    assert {v.periodo for v in cafe} == {"202607", "202608"}
    assert all(v.unidade == "%" and v.nivel == "1" for v in cafe)
    assert all(v.referencia in (date(2026, 7, 1), date(2026, 8, 1)) for v in cafe)


def test_cabecalho_da_resposta_nao_vira_valor():
    assert ibge_sidra.ler_resposta([CABECALHO]) == []
    assert ibge_sidra.ler_resposta([]) == []


def test_traco_e_zero_mesmo():
    # "-" é "zero absoluto, não resultante de arredondamento" (nota do SIDRA)
    [v] = ibge_sidra.ler_resposta([CABECALHO, _linha("-")])
    assert v.valor == 0.0


@pytest.mark.parametrize("simbolo", ["...", "..", "X", "", " "])
def test_sigilo_e_dado_nao_disponivel_nao_viram_numero(simbolo):
    # "X" (omitido por sigilo), ".." (não se aplica) e "..." (não disponível) nunca são zero
    [v] = ibge_sidra.ler_resposta([CABECALHO, _linha(simbolo)])
    assert v.valor is None


def test_numero_decimal_com_ponto():
    [v] = ibge_sidra.ler_resposta([CABECALHO, _linha("-2.45")])
    assert v.valor == pytest.approx(-2.45)


def test_simbolo_desconhecido_para_a_leitura_em_vez_de_chutar():
    with pytest.raises(ibge_sidra.RespostaInesperada):
        ibge_sidra.ler_resposta([CABECALHO, _linha("talvez")])


def test_resposta_de_erro_do_sidra_nao_e_lista():
    with pytest.raises(ibge_sidra.RespostaInesperada):
        ibge_sidra.ler_resposta({"status": "Error", "message": "Parâmetro inválido"})  # type: ignore[arg-type]


def test_data_de_referencia_mensal_e_anual():
    assert ibge_sidra.data_de_referencia("202607") == date(2026, 7, 1)
    assert ibge_sidra.data_de_referencia("2024") == date(2024, 12, 31)
    with pytest.raises(ibge_sidra.RespostaInesperada):
        ibge_sidra.data_de_referencia("2024T1")


def test_pmc_tem_brasil_e_uf():
    valores = ibge_sidra.ler_resposta(_resposta("pmc_volume.json"))
    assert {v.nivel for v in valores} == {"1", "3"}
    assert {v.local for v in valores} == {"1", "31"}


# --- id da série (tipo do café) ---------------------------------------------------------------------
def test_lspa_e_pam_gravam_o_tipo_do_cafe_no_id():
    lspa = ibge_sidra.ler_resposta(_resposta("lspa_cafe.json"))
    ids = {ibge_sidra.codigo_da_serie(6588, v) for v in lspa}
    assert "ibge-sidra-6588-35-arabica-uf31" in ids
    assert "ibge-sidra-6588-35-conilon-uf32" in ids  # canephora → conilon
    pam = ibge_sidra.ler_resposta(_resposta("pam_cafe_municipios.json"))
    ids = {ibge_sidra.codigo_da_serie(1613, v) for v in pam}
    assert "ibge-sidra-1613-216-arabica-mun3136702" in ids
    assert any("-total-mun" in i for i in ids)
    assert not any("canephora" in i for i in ids)


def test_serie_fora_do_cafe_usa_o_codigo_da_categoria():
    [v] = ibge_sidra.ler_resposta([CABECALHO, _linha("0.07")])
    assert ibge_sidra.codigo_da_serie(7060, v) == "ibge-sidra-7060-63-7169-br"


def test_todo_id_de_cafe_termina_com_tipo_e_local():
    # risco 4 do plano: nunca misturar arábica e conilon
    for nome, tabela in (("lspa_cafe.json", 6588), ("pam_cafe_municipios.json", 1613)):
        for v in ibge_sidra.ler_resposta(_resposta(nome)):
            partes = ibge_sidra.codigo_da_serie(tabela, v).split("-")
            assert partes[4] in {"arabica", "conilon", "total"}


# --- total do café na LSPA ---------------------------------------------------------------------------
def test_total_do_cafe_da_lspa_e_a_soma_dos_dois_tipos():
    valores = ibge_sidra.ler_resposta(_resposta("lspa_cafe.json"))
    com_total = ibge_sidra.somar_total_do_cafe(valores)
    total_es = [
        v for v in com_total
        if v.local == "32" and v.variavel == 35 and v.periodo == "202608"
        and ibge_sidra.rotulo_da_categoria(6588, v.categorias[0]) == "total"
    ]  # fmt: skip
    assert [v.valor for v in total_es] == [227174 + 848503]


def test_total_nao_inventa_numero_quando_um_tipo_esta_em_sigilo():
    base = {
        "nivel": "3",
        "local": "99",
        "variavel": 35,
        "periodo": "202607",
        "unidade": "t",
    }
    valores = [
        Valor(categorias=(39454,), valor=10.0, **base),
        Valor(categorias=(39455,), valor=None, **base),
    ]
    totais = [
        v for v in ibge_sidra.somar_total_do_cafe(valores)
        if ibge_sidra.rotulo_da_categoria(6588, v.categorias[0]) == "total"
    ]  # fmt: skip
    assert totais and all(v.valor is None for v in totais)


def test_rendimento_nao_tem_total_somado():
    base = {"nivel": "3", "local": "99", "periodo": "202607", "unidade": "kg/ha"}
    valores = [
        Valor(variavel=36, categorias=(39454,), valor=1500.0, **base),
        Valor(variavel=36, categorias=(39455,), valor=2500.0, **base),
    ]
    assert len(ibge_sidra.somar_total_do_cafe(valores)) == 2


# --- sem olhar o futuro e séries vazias ---------------------------------------------------------------
def test_corte_do_futuro_tira_o_que_ainda_nao_aconteceu():
    valores = ibge_sidra.ler_resposta(_resposta("ipca_cafe.json"))
    assert len(ibge_sidra.cortar_futuro(valores, date(2026, 7, 31))) == 4
    assert len(ibge_sidra.cortar_futuro(valores, date(2026, 6, 30))) == 0
    assert len(ibge_sidra.cortar_futuro(valores, date(2026, 8, 1))) == 8


def test_cortar_o_futuro_nao_muda_o_passado():
    valores = ibge_sidra.ler_resposta(_resposta("ipca_cafe.json"))
    corte = date(2026, 7, 31)
    tudo = ibge_sidra.cortar_futuro(valores, date(2026, 12, 31))
    assert [v for v in tudo if v.referencia <= corte] == ibge_sidra.cortar_futuro(
        valores, corte
    )


def test_descartar_series_sem_nenhum_valor_diferente_de_zero():
    base = {"nivel": "6", "variavel": 216, "unidade": "ha", "categorias": (31619,)}
    valores = [
        Valor(local="1", periodo="2023", valor=0.0, **base),
        Valor(local="1", periodo="2024", valor=None, **base),
        Valor(local="2", periodo="2023", valor=0.0, **base),
        Valor(local="2", periodo="2024", valor=7.0, **base),
    ]
    sobra = ibge_sidra.descartar_series_vazias(valores)
    assert {v.local for v in sobra} == {"2"}
    assert len(sobra) == 2  # a série que tem número guarda também os zeros dela


# --- séries do acervo -----------------------------------------------------------------------------------
def test_serie_do_acervo_tem_nome_unidade_e_frequencia():
    valores = ibge_sidra.ler_resposta(_resposta("pimpf_secoes.json"))
    serie = ibge_sidra.serie_do_acervo(8888, valores[0], "mensal")
    assert serie.codigo.startswith("ibge-sidra-8888-")
    assert serie.frequencia == "mensal"
    assert "Indústria geral" in serie.nome and "Brasil" in serie.nome
    assert not serie.uso_interno
