"""Coletor das séries do IBGE (SIDRA), sem internet: cada versão da LSPA fica guardada, "como
estava em D" não traz revisão posterior, símbolos do SIDRA não viram número errado e uma tabela
fora do ar não derruba as outras."""

import json
from datetime import date
from pathlib import Path

import pytest
import requests

from scripts import atualizar_series_ibge as coletor
from src import ibge_sidra
from src.banco import series as acervo_de_series
from src.banco.coletas import licenca_da_fonte, ultimas

EXEMPLOS = Path(__file__).resolve().parent.parent / "dados_de_exemplo" / "ibge"
CABECALHO = [{"NC": "Nível Territorial (Código)", "V": "Valor"}]
ARQUIVO_DA_TABELA = {
    6588: "lspa_cafe.json",
    1613: "pam_cafe_municipios.json",
    8880: "pmc_volume.json",
    8888: "pimpf_secoes.json",
    7060: "ipca_cafe.json",
}
LSPA_MG_ARABICA_PRODUCAO = "ibge-sidra-6588-35-arabica-uf31"


class _Resposta:
    def __init__(self, url: str, corpo: object, status: int = 200) -> None:
        self.url = url
        self.status_code = status
        self.ok = status < 400
        self.text = json.dumps(corpo)
        self.content = self.text.encode()
        self._corpo = corpo

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(str(self.status_code))

    def json(self) -> object:
        return self._corpo


def _exemplo(tabela: int) -> list[dict]:
    arquivo = ARQUIVO_DA_TABELA.get(tabela)
    if arquivo is None:
        return CABECALHO
    return json.loads((EXEMPLOS / arquivo).read_text(encoding="utf-8"))


def _fonte_falsa(pedidos: list[str], fora: set[int] = frozenset(), ajuste=None):
    """O SIDRA de mentira: devolve o exemplo da tabela pedida; `ajuste(tabela, linhas)` mexe nele."""

    def buscar(url, **_):
        pedidos.append(url)
        tabela = int(url.split("/t/")[1].split("/")[0])
        if tabela in fora:
            return _Resposta(url, "erro", 503)
        linhas = [dict(linha) for linha in _exemplo(tabela)]
        if ajuste:
            linhas = ajuste(tabela, linhas)
        return _Resposta(url, linhas)

    return buscar


def _revisar_mg(valor: str):
    def ajuste(tabela, linhas):
        if tabela == 6588:
            for linha in linhas[1:]:
                if (
                    linha["D1C"] == "31"
                    and linha["D2C"] == "35"
                    and linha["D4C"] == "39454"
                ):
                    linha["V"] = valor
        return linhas

    return ajuste


HOJE = date(2026, 10, 18)


def _coletar(banco, hoje, **kwargs) -> tuple[bool, list[str]]:
    pedidos: list[str] = []
    buscar = _fonte_falsa(pedidos, **kwargs)
    return coletor.coletar_tudo(banco, hoje, buscar), pedidos


def test_coleta_grava_lspa_por_tipo_e_uf(banco):
    ok, _ = _coletar(banco, HOJE)
    assert ok
    with banco.connect() as conexao:
        serie = acervo_de_series.como_estava_em(conexao, LSPA_MG_ARABICA_PRODUCAO, HOJE)
        total = acervo_de_series.como_estava_em(
            conexao, "ibge-sidra-6588-35-total-uf32", HOJE
        )
        ipca = acervo_de_series.como_estava_em(
            conexao, "ibge-sidra-7060-63-7392-br", HOJE
        )
    assert serie.iloc[-1] == pytest.approx(1941297)
    assert total.iloc[-1] == pytest.approx(227174 + 848503)
    assert len(ipca) == 2


def test_revisao_da_lspa_vira_versao_nova_e_a_anterior_fica(banco):
    _coletar(banco, date(2026, 9, 10))
    _coletar(banco, date(2026, 10, 10), ajuste=_revisar_mg("2000000"))
    agosto = date(2026, 8, 1)
    with banco.connect() as conexao:
        versoes = acervo_de_series.safras(conexao, LSPA_MG_ARABICA_PRODUCAO, agosto)
    assert versoes == [
        (date(2026, 9, 10), pytest.approx(1941297)),
        (date(2026, 10, 10), pytest.approx(2000000)),
    ]


def test_como_era_em_d_nao_traz_revisao_publicada_depois_de_d(banco):
    _coletar(banco, date(2026, 9, 10))
    _coletar(banco, date(2026, 10, 10), ajuste=_revisar_mg("2000000"))
    with banco.connect() as conexao:
        antes = acervo_de_series.como_estava_em(
            conexao, LSPA_MG_ARABICA_PRODUCAO, date(2026, 9, 30)
        )
        depois = acervo_de_series.como_estava_em(
            conexao, LSPA_MG_ARABICA_PRODUCAO, date(2026, 10, 10)
        )
        antes_de_tudo = acervo_de_series.como_estava_em(
            conexao, LSPA_MG_ARABICA_PRODUCAO, date(2026, 9, 1)
        )
    assert antes.iloc[-1] == pytest.approx(1941297)
    assert depois.iloc[-1] == pytest.approx(2000000)
    assert antes_de_tudo.empty


def test_repetir_a_coleta_nao_duplica(banco):
    _coletar(banco, date(2026, 10, 10))
    with banco.connect() as conexao:
        antes = len(
            acervo_de_series.safras(conexao, LSPA_MG_ARABICA_PRODUCAO, date(2026, 8, 1))
        )
    _coletar(banco, date(2026, 10, 11))
    with banco.connect() as conexao:
        depois = len(
            acervo_de_series.safras(conexao, LSPA_MG_ARABICA_PRODUCAO, date(2026, 8, 1))
        )
    assert antes == depois == 1


@pytest.mark.parametrize("simbolo", ["...", "X", ".."])
def test_sigilo_nao_vira_zero_no_acervo(banco, simbolo):
    _coletar(banco, HOJE, ajuste=_revisar_mg(simbolo))
    with banco.connect() as conexao:
        serie = acervo_de_series.como_estava_em(conexao, LSPA_MG_ARABICA_PRODUCAO, HOJE)
    assert (
        serie.empty
    )  # nenhum mês de MG arábica; nem zero, nem o valor do mês anterior


def test_traco_do_sidra_e_zero_no_acervo(banco):
    _coletar(banco, HOJE, ajuste=_revisar_mg("-"))
    with banco.connect() as conexao:
        serie = acervo_de_series.como_estava_em(conexao, LSPA_MG_ARABICA_PRODUCAO, HOJE)
    assert list(serie) == [0.0, 0.0]


def test_periodo_no_futuro_nao_entra(banco):
    # coletar "em 31/07" não pode gravar agosto
    _coletar(banco, date(2026, 7, 31))
    with banco.connect() as conexao:
        serie = acervo_de_series.como_estava_em(
            conexao, "ibge-sidra-7060-63-7392-br", date(2026, 12, 31)
        )
    assert list(serie.index.strftime("%Y-%m")) == ["2026-07"]


def test_pam_municipal_so_guarda_municipio_que_tem_cafe(banco):
    _coletar(banco, HOJE)
    with banco.connect() as conexao:
        codigos = [
            c for c in acervo_de_series.series_para_exportar(conexao) if "-mun" in c
        ]
    assert codigos
    assert all("-1613-" in c for c in codigos)
    assert any(c.startswith("ibge-sidra-1613-216-arabica-mun") for c in codigos)


def test_primeira_coleta_vai_desde_2010_e_as_seguintes_pegam_so_a_janela_recente(banco):
    _, primeira = _coletar(banco, HOJE)
    lspa = next(u for u in primeira if "/t/6588/" in u)
    assert "/p/201001-202610" in lspa
    pam = [u for u in primeira if "/t/1613/" in u and "n3%2031/" in u]
    assert [u.split("/p/")[1].split("/")[0] for u in pam] == [
        "2010-2013",
        "2014-2017",
        "2018-2021",
        "2022-2025",
        "2026-2026",
    ]
    _, segunda = _coletar(banco, date(2026, 10, 19))
    lspa = next(u for u in segunda if "/t/6588/" in u)
    assert "/p/202410-202610" in lspa
    pam = next(u for u in segunda if "/t/1613/" in u)
    assert "/p/2024-2026" in pam


def test_tabela_fora_do_ar_nao_derruba_as_outras(banco):
    ok, _ = _coletar(banco, HOJE, fora={8888})
    assert not ok
    with banco.connect() as conexao:
        assert acervo_de_series.tem_dados(conexao, LSPA_MG_ARABICA_PRODUCAO)
        assert not any(
            "-8888-" in c for c in acervo_de_series.series_para_exportar(conexao)
        )


def test_resposta_de_erro_com_status_200_conta_como_falha(banco):
    def buscar(url, **_):
        return _Resposta(url, {"status": "Error", "message": "Tabela inexistente"})

    assert coletor.coletar_tudo(banco, HOJE, buscar) is False


def test_so_a_pam_municipal_busca_so_a_tabela_1613(banco):
    pedidos: list[str] = []
    assert coletor.coletar_tudo(banco, HOJE, _fonte_falsa(pedidos), so="pam-municipal")
    assert pedidos and all("/t/1613/" in pedido for pedido in pedidos)


def test_series_do_ibge_levam_a_licenca_do_ibge_e_podem_sair(banco):
    _coletar(banco, HOJE)
    assert "IBGE" in licenca_da_fonte(LSPA_MG_ARABICA_PRODUCAO)
    with banco.connect() as conexao:
        assert LSPA_MG_ARABICA_PRODUCAO in acervo_de_series.series_para_exportar(
            conexao
        )


def test_cada_pedido_ao_sidra_fica_no_registro_de_coletas(banco):
    pedidos: list[str] = []
    assert coletor.coletar_tudo(banco, HOJE, _fonte_falsa(pedidos))
    with banco.connect() as conexao:
        registradas = ultimas(conexao, "ibge-sidra", quantas=1000)
    assert len(registradas) == len(pedidos)


def test_o_codigo_do_ibge_nao_importa_streamlit():
    # src/ não importa o Streamlit (regra do repositório)
    codigo = Path(ibge_sidra.__file__).read_text(encoding="utf-8")
    assert "streamlit" not in codigo


def test_pedido_da_pam_municipal_cabe_no_limite_do_sidra():
    """Regressão (19/10/2026): 6 anos de MG somavam 61.344 valores e o SIDRA respondia 400."""
    coleta = ibge_sidra.COLETAS_POR_NOME["pam-municipal"]
    classes = sum(len(c) for c in coleta.classificacoes.values())
    por_ano = ibge_sidra.MUNICIPIOS_DE_MG * len(coleta.variaveis) * classes
    blocos = coleta._blocos("2010-2026")
    maior = max(int(b.split("-")[1]) - int(b.split("-")[0]) + 1 for b in blocos)
    assert maior * por_ano <= ibge_sidra.VALORES_POR_PEDIDO_NO_SIDRA
