"""QEDS do Banco Mundial (base/qeds_banco_mundial.py): dívida externa bruta trimestral do Brasil.
Nada vai à internet: a resposta é o dublê de `dados_de_exemplo/mercados/` (retrato de 03/11/2026)."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import qeds_banco_mundial as qeds
from base.arquivo import fontes
from base.arquivo import lote_organismos as lote
from base.arquivo.coleta import Resposta
from src.banco.coletas import (
    SEM_LICENCA_CONHECIDA,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
)

AMOSTRA = (
    Path(__file__).parent.parent
    / "dados_de_exemplo"
    / "mercados"
    / "qeds_divida_externa_bra.json"
).read_bytes()
COLETA_1, COLETA_2 = date(2026, 11, 3), date(2027, 2, 1)
AGORA = datetime(2026, 11, 3, 22, tzinfo=UTC)


def _com_valor(valor_novo: float, periodo: str, extra: dict | None = None) -> bytes:
    """A amostra com o valor de um trimestre trocado (revisão) e, se pedido, um trimestre a mais."""
    resposta = json.loads(AMOSTRA)
    for linha in resposta[1]:
        if linha["date"] == periodo:
            linha["value"] = valor_novo
    if extra:
        resposta[1].insert(0, {**resposta[1][0], **extra})
    return json.dumps(resposta).encode()


def test_a_serie_do_brasil_cobre_de_1998q1_ate_o_ultimo_trimestre_publicado():
    tabela = qeds.ler([AMOSTRA], COLETA_1)
    assert len(tabela) == 114
    assert tabela["periodo"].iloc[0] == "1998Q1"
    assert tabela["periodo"].iloc[-1] == "2026Q2"
    assert tabela["fim_do_trimestre"].iloc[0] == pd.Timestamp("1998-03-31")
    assert tabela["fim_do_trimestre"].iloc[-1] == pd.Timestamp("2026-06-30")
    assert set(tabela["pais"]) == {"BRA"}
    assert tabela["periodo"].is_unique


def test_os_22_nulos_iniciais_ficam_nulos_sem_preencher():
    tabela = qeds.ler([AMOSTRA], COLETA_1)
    assert tabela["valor"].isna().sum() == 22
    assert tabela["valor"].iloc[:22].isna().all()
    assert tabela["valor"].iloc[22:].notna().all()
    assert tabela["periodo"].iloc[22] == "2003Q3"


def test_a_unidade_vem_do_nome_do_indicador_e_vai_para_uma_coluna():
    tabela = qeds.ler([AMOSTRA], COLETA_1)
    assert set(tabela["unidade"]) == {"USD"}
    assert (
        qeds.unidade_do_nome(
            "Gross Ext. Debt Pos., All Sectors, All maturities, All instruments, USD"
        )
        == "USD"
    )
    with pytest.raises(ValueError, match="unidade"):
        qeds.unidade_do_nome("Nome sem unidade")


def test_disponivel_em_e_a_data_da_coleta_nunca_o_fim_do_trimestre():
    tabela = qeds.ler([AMOSTRA], COLETA_1)
    assert (tabela["disponivel_em"] == pd.Timestamp(COLETA_1)).all()
    assert (tabela["disponivel_em"] > tabela["fim_do_trimestre"]).all()


def test_coleta_nova_nao_reescreve_o_disponivel_em_dos_pontos_antigos():
    primeira = qeds.ler([AMOSTRA], COLETA_1)
    segunda = qeds.ler(
        [_com_valor(9.0e11, "2026Q3", {"date": "2026Q3", "value": 9.0e11})], COLETA_2
    )
    historico = qeds.acumular(primeira, segunda)
    antigos = historico[historico["periodo"] != "2026Q3"]
    assert len(antigos) == 114
    assert (antigos["disponivel_em"] == pd.Timestamp(COLETA_1)).all()
    novo = historico[historico["periodo"] == "2026Q3"]
    assert list(novo["disponivel_em"]) == [pd.Timestamp(COLETA_2)]


def test_a_mesma_coleta_de_novo_nao_acumula_nada():
    primeira = qeds.ler([AMOSTRA], COLETA_1)
    de_novo = qeds.acumular(primeira, qeds.ler([AMOSTRA], COLETA_2))
    pd.testing.assert_frame_equal(de_novo, primeira)


def test_revisao_vira_versao_nova_e_como_estava_em_nao_olha_o_futuro():
    primeira = qeds.ler([AMOSTRA], COLETA_1)
    revisada = qeds.ler([_com_valor(1.0, "2025Q4")], COLETA_2)
    historico = qeds.acumular(primeira, revisada)
    versoes = historico[historico["periodo"] == "2025Q4"].sort_values("disponivel_em")
    assert len(versoes) == 2 and versoes["valor"].iloc[-1] == 1.0
    antes = qeds.como_estava_em(historico, date(2026, 12, 31))
    depois = qeds.como_estava_em(historico, COLETA_2)
    assert antes.loc[antes["periodo"] == "2025Q4", "valor"].iloc[0] != 1.0
    assert depois.loc[depois["periodo"] == "2025Q4", "valor"].iloc[0] == 1.0
    assert qeds.como_estava_em(historico, date(2026, 11, 2)).empty


@pytest.mark.parametrize(
    "corpo",
    [
        json.dumps([{"message": [{"id": "120", "key": "Invalid value"}]}]),
        json.dumps({"erro": 1}),
        "<html>400</html>",
    ],
)
def test_resposta_de_erro_ou_de_outro_formato_e_falha(corpo):
    with pytest.raises(ValueError, match="QEDS"):
        qeds.ler([corpo.encode()], COLETA_1)


def test_periodo_fora_do_formato_trimestral_e_falha():
    resposta = json.loads(AMOSTRA)
    resposta[1][0]["date"] = "2026"
    with pytest.raises(ValueError, match="QEDS"):
        qeds.ler([json.dumps(resposta).encode()], COLETA_1)


# ---- a coleta (base/arquivo/lote_organismos.py) ----------------------------------------------------
class Paginas:
    def __init__(self, paginas):
        self.paginas, self.pedidos = paginas, []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, self.paginas[url], {})


def test_a_coleta_pede_a_fonte_22_do_brasil_com_o_indicador_da_posicao_bruta():
    fonte = fontes.POR_ID["worldbank-qeds-brasil"]
    url = lote.endereco_do_qeds(1)
    assert "source=22" in url and "/country/BRA/" in url and qeds.INDICADOR in url
    alvos = fonte.descobrir(Paginas({url: AMOSTRA}), AGORA)
    assert [a.url for a in alvos] == [url] and alvos[0].extensao == ".json"


def test_a_coleta_do_qeds_tem_licenca_cc_by_com_atribuicao_e_data_de_termos():
    assert licenca_da_fonte("worldbank-qeds-brasil") != SEM_LICENCA_CONHECIDA
    assert marca_da_fonte("worldbank-qeds-brasil") == marca_da_fonte("worldbank-brasil")
    assert marca_da_fonte("worldbank-qeds-brasil") is not Marca.NAO_COMERCIAL


def test_a_atribuicao_cita_o_banco_mundial_e_a_licenca():
    assert "Banco Mundial" in qeds.ATRIBUICAO and "CC BY 4.0" in qeds.ATRIBUICAO
