"""Séries macro com safras (Radar, PR 5), sem internet: revisão não apaga a anterior, repetir o
dia não duplica, "como estava em D" e o Yahoo só para uso interno."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import requests

from scripts import atualizar_series_macro as coletor
from src import bcb
from src.banco import series as acervo_de_series
from src.banco.coletas import buscar_com_registro, licenca_da_fonte, ultimas
from src.banco.series import SerieDoAcervo

HOJE = date(2026, 10, 13)
IPCA = SerieDoAcervo("bcb-sgs-433", "IPCA", "% no mês", "mensal")


def _serie(**valores) -> pd.Series:
    return pd.Series({pd.Timestamp(d): v for d, v in valores.items()})


def _gravar(banco, valores: pd.Series, safra: date) -> int:
    with banco.begin() as conexao:
        acervo_de_series.garantir_serie(conexao, IPCA)
        return acervo_de_series.gravar(conexao, IPCA.codigo, valores, safra)


# --- acervo de séries ---------------------------------------------------------------------------
def test_repetir_o_dia_nao_duplica(banco):
    valores = pd.Series(
        [0.44, 0.48], index=pd.to_datetime(["2026-08-01", "2026-09-01"])
    )
    assert _gravar(banco, valores, date(2026, 10, 10)) == 2
    assert _gravar(banco, valores, date(2026, 10, 11)) == 0


def test_revisao_vira_safra_nova_sem_apagar_a_anterior(banco):
    agosto = pd.Timestamp("2026-08-01")
    _gravar(banco, pd.Series([0.44], index=[agosto]), date(2026, 9, 10))
    _gravar(banco, pd.Series([0.47], index=[agosto]), date(2026, 10, 10))
    with banco.connect() as conexao:
        assert acervo_de_series.safras(conexao, IPCA.codigo, agosto.date()) == [
            (date(2026, 9, 10), pytest.approx(0.44)),
            (date(2026, 10, 10), pytest.approx(0.47)),
        ]
        antes = acervo_de_series.como_estava_em(conexao, IPCA.codigo, date(2026, 9, 30))
        depois = acervo_de_series.como_estava_em(conexao, IPCA.codigo, HOJE)
        nada = acervo_de_series.como_estava_em(conexao, IPCA.codigo, date(2026, 9, 1))
    assert antes[agosto] == pytest.approx(0.44)
    assert depois[agosto] == pytest.approx(0.47)
    assert nada.empty


def test_valor_vazio_e_ignorado(banco):
    valores = pd.Series(
        [float("nan"), 0.5], index=pd.to_datetime(["2026-08-01", "2026-09-01"])
    )
    assert _gravar(banco, valores, HOJE) == 1


def test_yahoo_fica_so_para_uso_interno(banco):
    with banco.begin() as conexao:
        acervo_de_series.garantir_serie(conexao, IPCA)
        acervo_de_series.garantir_serie(conexao, coletor.serie_yahoo("bvsp"))
        acervo_de_series.garantir_serie(conexao, IPCA)  # de novo: atualiza, não duplica
        assert acervo_de_series.series_para_exportar(conexao) == ["bcb-sgs-433"]


def test_igpm_da_fgv_fica_so_para_uso_interno(banco):
    # o IGP-M é da FGV IBRE (uso comercial pede autorização), mesmo vindo pelo SGS do BC
    igpm = coletor.serie_sgs("igpm")
    assert igpm.uso_interno
    assert not coletor.serie_sgs("ipca").uso_interno
    assert "FGV" in licenca_da_fonte(igpm.codigo)
    with banco.begin() as conexao:
        acervo_de_series.garantir_serie(conexao, IPCA)
        acervo_de_series.garantir_serie(conexao, igpm)
        assert acervo_de_series.series_para_exportar(conexao) == ["bcb-sgs-433"]


def test_codigos_e_rotulos_das_series():
    assert coletor.serie_sgs("ipca").codigo == "bcb-sgs-433"
    assert coletor.serie_sgs("ipca").frequencia == "mensal"
    assert coletor.serie_sgs("dolar").frequencia == "diária"
    # IC-Br (índice de commodities do BC): mensal, em índice, ids conferidos em 18/10/2026
    assert coletor.serie_sgs("icbr").codigo == "bcb-sgs-27574"
    assert coletor.serie_sgs("icbr_agro").codigo == "bcb-sgs-27575"
    assert coletor.serie_sgs("icbr").frequencia == "mensal"
    assert coletor.rotulo_do_prazo(0.5) == "6m"
    assert coletor.rotulo_do_prazo(1.5 / 12) == "1.5m"
    assert coletor.rotulo_do_prazo(10.0) == "10a"
    assert coletor.serie_yahoo("gspc").uso_interno


# --- coleta (BC, Tesouro e Yahoo falsos) --------------------------------------------------------
class _Resposta:
    def __init__(
        self, url: str, corpo: object, status: int = 200, content: bytes | None = None
    ) -> None:
        self.url = url
        self.status_code = status
        self.ok = status < 400
        self.text = corpo if isinstance(corpo, str) else json.dumps(corpo)
        self.content = self.text.encode() if content is None else content
        self._corpo = corpo

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(str(self.status_code))

    def json(self) -> object:
        return self._corpo


_PASTA = Path(__file__).parent.parent / "dados_de_exemplo" / "commodities"
_PINK = (_PASTA / "pink_sheet_mensal.xlsx").read_bytes()
FMI_CSV = (_PASTA / "fmi_pcps_mensal.csv").read_text(encoding="utf-8")
_PAGINA_DO_PINK = (
    '<a href="https://thedocs.worldbank.org/en/doc/x-0050012026/related/'
    'CMO-Historical-Data-Monthly.xlsx">XLS</a>'
)


def _focus(data: str, mediana_2026: float) -> list[dict]:
    return [
        {"Indicador": "IPCA", "Data": data, "DataReferencia": "2026", "Mediana": mediana_2026,
         "Media": 5.0, "Minimo": 4.0, "Maximo": 6.0, "numeroRespondentes": 100},
        {"Indicador": "IPCA", "Data": data, "DataReferencia": "2027", "Mediana": 4.3,
         "Media": 4.3, "Minimo": 3.0, "Maximo": 6.0, "numeroRespondentes": 90},
    ]  # fmt: skip


CURVA = "Date,1 Mo,6 Mo,10 Yr\n10/09/2026,4.10,3.90,4.05\n10/08/2026,4.11,3.91,4.07\n"


def _fonte_falsa(pedidos: list, tesouro_fora: bool = False):
    def buscar(url, params=None, **_):
        pedidos.append(url)
        if "bcdata.sgs" in url:
            return _Resposta(url, [{"data": "01/09/2026", "valor": "0.48"}])
        if "PTAX" in url:
            cotacao = {"cotacaoCompra": 5.30, "cotacaoVenda": 5.31,
                       "dataHoraCotacao": "2026-10-09 13:00:00.0"}  # fmt: skip
            return _Resposta(url, {"value": [cotacao]})
        if "Expectativas" in url:
            assert "baseCalculo%20eq%200" in url  # só a conta do boletim
            return _Resposta(
                url, {"value": _focus("2026-10-02", 5.01) + _focus("2026-10-09", 5.05)}
            )
        if "treasury" in url:
            return (
                _Resposta(url, "erro", 503) if tesouro_fora else _Resposta(url, CURVA)
            )
        if "commodity-markets" in url:
            return _Resposta(url, _PAGINA_DO_PINK)
        if url.endswith("CMO-Historical-Data-Monthly.xlsx"):
            return _Resposta(url, "", content=_PINK)
        if "api.imf.org" in url:
            return _Resposta(url, FMI_CSV, content=FMI_CSV.encode())
        raise AssertionError(url)

    return buscar


def _yahoo(ticker: str, inicio: date) -> pd.Series:
    return _serie(**{"2026-10-08": 130_000.0, "2026-10-09": 131_000.0})


def test_coleta_grava_todas_as_fontes_com_safra(banco):
    pedidos: list = []
    assert coletor.coletar_tudo(banco, HOJE, _fonte_falsa(pedidos), _yahoo)
    with banco.connect() as conexao:
        focus = coletor.serie_focus("ipca").codigo
        # o Focus com duas pesquisas guarda as duas safras do mesmo ano
        assert acervo_de_series.safras(conexao, focus, date(2026, 12, 31)) == [
            (date(2026, 10, 2), pytest.approx(5.01)),
            (date(2026, 10, 9), pytest.approx(5.05)),
        ]
        como_em_5 = acervo_de_series.como_estava_em(conexao, focus, date(2026, 10, 5))
        assert como_em_5[pd.Timestamp("2026-12-31")] == pytest.approx(5.01)
        assert acervo_de_series.como_estava_em(
            conexao, "tesouro-eua-10a", HOJE
        ).tolist() == [
            pytest.approx(0.0407),
            pytest.approx(0.0405),
        ]
        assert (
            acervo_de_series.como_estava_em(conexao, "bcb-ptax-venda", HOJE).iloc[0]
            == 5.31
        )
        assert len(acervo_de_series.como_estava_em(conexao, "yahoo-bvsp", HOJE)) == 2
        registradas = {linha.fonte for linha in ultimas(conexao, quantas=100)}
    assert registradas == {
        "bcb-sgs", "bcb-ptax", "bcb-focus", "tesouro-eua", "bm-pink", "fmi-pcps",
    }  # fmt: skip
    with banco.connect() as conexao:
        assert acervo_de_series.tem_dados(conexao, "bm-pink-cafe-arabica")
        assert acervo_de_series.tem_dados(conexao, "fmi-cafe-arabica")


def test_segunda_coleta_do_dia_nao_grava_nada_e_pede_so_a_janela(banco):
    coletor.coletar_tudo(banco, HOJE, _fonte_falsa([]), _yahoo)
    with banco.connect() as conexao:
        total = conexao.exec_driver_sql("select count(*) from observacoes").scalar()
    pedidos: list = []
    assert coletor.coletar_tudo(banco, HOJE, _fonte_falsa(pedidos), _yahoo)
    with banco.connect() as conexao:
        assert (
            conexao.exec_driver_sql("select count(*) from observacoes").scalar()
            == total
        )
    # já tem dados: o Tesouro pede só os anos da janela de revisão, não desde 2010
    assert sum("treasury" in p for p in pedidos) == 2


def test_precos_de_referencia_so_voltam_na_janela_de_cada_fonte(banco):
    coletor.coletar_tudo(
        banco, HOJE, _fonte_falsa([]), _yahoo
    )  # 13/10: vazio, coleta tudo
    pedidos: list = []
    assert coletor.coletar_tudo(
        banco, date(2026, 10, 20), _fonte_falsa(pedidos), _yahoo
    )
    assert not any("worldbank" in p or "imf.org" in p for p in pedidos)
    pedidos = []
    assert coletor.coletar_tudo(banco, date(2026, 11, 3), _fonte_falsa(pedidos), _yahoo)
    assert any("CMO-Historical" in p for p in pedidos)
    assert not any("imf.org" in p for p in pedidos)
    pedidos = []
    assert coletor.coletar_tudo(
        banco, date(2026, 11, 10), _fonte_falsa(pedidos), _yahoo
    )
    assert any("imf.org" in p for p in pedidos)


def test_uma_fonte_fora_do_ar_nao_impede_as_outras(banco):
    assert not coletor.coletar_tudo(
        banco, HOJE, _fonte_falsa([], tesouro_fora=True), _yahoo
    )
    with banco.connect() as conexao:
        assert not acervo_de_series.tem_dados(conexao, "tesouro-eua-10a")
        assert acervo_de_series.tem_dados(conexao, "yahoo-gspc")
        falhas = [linha for linha in ultimas(conexao) if linha.situacao == "falhou"]
    assert falhas and falhas[0].detalhe == "HTTP 503"


def test_yahoo_vazio_e_falha(banco):
    assert not coletor.coletar_tudo(banco, HOJE, _fonte_falsa([]), lambda *_: None)


def test_registro_do_buscar_404_e_erro(banco):
    def buscar(url, **_):
        if "sumiu" in url:
            return _Resposta(url, "", 404)
        raise requests.ConnectionError("sem rede")

    registrar = buscar_com_registro("bcb-sgs", buscar)
    assert registrar("https://api.bcb.gov.br/sumiu").status_code == 404
    with pytest.raises(requests.ConnectionError):
        registrar("https://api.bcb.gov.br/x")
    with banco.connect() as conexao:
        situacoes = sorted((l.situacao, l.detalhe) for l in ultimas(conexao))
    assert situacoes == [("falhou", "ConnectionError"), ("nao_encontrado", "HTTP 404")]


def test_focus_sem_base_de_calculo_nao_filtra():
    pedidos: list = []

    def buscar(url, params=None, timeout=None):
        pedidos.append(url)
        return _Resposta(url, {"value": []})

    bcb.baixar_focus("IPCA", HOJE, buscar)
    assert "baseCalculo" not in pedidos[0]


def test_toda_serie_do_sgs_tem_frequencia_codigo_e_o_futuro_nao_entra():
    diarias = {c for c in bcb.SERIES if coletor.serie_sgs(c).frequencia == "diária"}
    assert diarias == coletor.SGS_DIARIAS  # as de SGS_DIARIAS existem em SERIES
    assert coletor.serie_sgs("credito_saldo").frequencia == "mensal"
    assert coletor.serie_sgs("selic_acumulada_mes_anualizada").frequencia == "mensal"
    assert coletor.serie_sgs("tr").frequencia == "diária"
    codigos = [coletor.serie_sgs(c).codigo for c in bcb.SERIES]
    assert len(codigos) == len(set(codigos))
    # só o IGP-M da FGV é de terceiros: as séries novas do BC seguem a licença do BC
    assert {"igpm"} == coletor.SGS_DE_TERCEIROS


def test_focus_novos_tem_serie_propria_e_nome_da_api():
    assert coletor.FOCUS["divida_liquida"] == "Dívida líquida do setor público"
    assert (
        coletor.serie_focus("resultado_primario").codigo
        == "bcb-focus-resultado_primario"
    )
    assert coletor.serie_focus("igpm").frequencia == "anual"
    assert len({coletor.serie_focus(c).codigo for c in coletor.FOCUS}) == len(
        coletor.FOCUS
    )
    assert "'" not in "".join(coletor.FOCUS.values())  # a consulta recusa aspas
