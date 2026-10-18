"""O arquivista guarda o COT Disaggregated da CFTC desde 2006 e a fonte tem destino (PR 5 do café)."""

from datetime import UTC, datetime

from base.arquivo import fontes
from base.arquivo.destinos import DESTINOS, TABELA
from tests.test_base_arquivo_fontes import Paginas

AGORA = datetime(2026, 10, 19, 5, tzinfo=UTC)
BASE = "https://www.cftc.gov/files/dea/history/"


def test_descobrir_arquivos_anuais_2006_ate_hoje():
    urls = [a.url for a in fontes.descobrir_cot(Paginas({}), AGORA)]

    assert urls[0] == BASE + "fut_disagg_txt_hist_2006_2016.zip"  # 2006 a 2016 juntos
    assert urls[1:] == [f"{BASE}fut_disagg_txt_{ano}.zip" for ano in range(2017, 2027)]


def test_ano_novo_entra_quando_o_calendario_vira():
    urls = [
        a.url
        for a in fontes.descobrir_cot(Paginas({}), datetime(2027, 1, 4, tzinfo=UTC))
    ]

    assert urls[-1] == f"{BASE}fut_disagg_txt_2027.zip"


def test_fonte_do_cot_e_semanal_e_vira_tabela():
    fonte = fontes.POR_ID["cftc-cot-disaggregated"]

    assert fonte.grupo == "semanal"
    assert DESTINOS[fonte.id].tipo == TABELA
    assert DESTINOS[fonte.id].tabelas == ("cftc_cot_agro",)
