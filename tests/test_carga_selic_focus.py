"""Meta da Selic e Focus Selic anual guardados pelo arquivista e levados à tabela `bcb_selic_focus`
(linha 225): coleta (endereços), leitores e carga de ponta a ponta. Sem internet."""

import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base import bcb_selic_focus
from base.arquivo import lote_selic
from base.arquivo.coleta import SemArquivo
from base.arquivo.destinos import DESTINOS
from base.arquivo.fontes import POR_ID
from base.parquet import conferir_tabela
from scripts import carga_selic_focus
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para

AGORA = datetime(2026, 11, 3, 12, tzinfo=UTC)
META = [
    {"data": "17/06/2026", "valor": "14.50"},
    {"data": "18/06/2026", "valor": "14.50"},
    {"data": "19/06/2026", "valor": "14.25"},
]
FOCUS = {
    "value": [
        {
            "Indicador": "Selic",
            "Data": "2026-10-30",
            "DataReferencia": "2026",
            "Mediana": 14.25,
        },
        {
            "Indicador": "Selic",
            "Data": "2026-10-30",
            "DataReferencia": "2027",
            "Mediana": 12.5,
        },
    ]
}


class _SemRede:
    """Cliente que só devolve um JSON do Olinda vazio ao baixar (a descoberta nunca o usa)."""

    def baixar(self, url, destino):
        destino.write_bytes(b'{"value": []}')
        return {}


def test_as_duas_fontes_estao_no_arquivista_com_destino_na_tabela():
    for fonte in lote_selic.fontes():
        assert POR_ID[fonte.id] == fonte
        assert DESTINOS[fonte.id].tabelas == ("bcb_selic_focus",)


def test_a_meta_pede_janelas_de_dez_anos_ate_o_fim_do_ano():
    alvos = lote_selic.descobrir_meta(_SemRede(), AGORA)
    assert [a.url.split("dataInicial=")[1] for a in alvos] == [
        "01/01/2000&dataFinal=31/12/2009",
        "01/01/2010&dataFinal=31/12/2019",
        "01/01/2020&dataFinal=31/12/2026",
    ]
    assert all("sgs.432" in a.url for a in alvos)


def test_o_focus_pede_um_ano_de_pesquisas_com_espaco_codificado():
    alvos = lote_selic.descobrir_focus(_SemRede(), AGORA)
    assert len(alvos) == 2026 - 2001 + 1
    url = alvos[-1].url
    assert "Data%20ge%20'2026-01-01'%20and%20Data%20le%20'2026-12-31'" in url
    assert "baseCalculo%20eq%200" in url and "+" not in url


def test_focus_vazio_nao_e_ok(tmp_path):
    alvo = lote_selic.descobrir_focus(_SemRede(), AGORA)[-1]
    with pytest.raises(SemArquivo):
        alvo.obter(_SemRede(), tmp_path / "x.json")


def test_le_a_meta_como_o_banco_de_producao_a_guarda():
    obs = bcb_selic_focus.observacoes_da_meta(json.dumps(META).encode(), AGORA)
    assert list(obs["valor"]) == [14.5, 14.5, 14.25]
    assert obs["divulgado_em"].equals(obs["referencia"])
    assert set(obs["serie"]) == {"bcb-sgs-432"}


def test_a_meta_nao_guarda_dias_depois_da_coleta():
    """O SGS 432 devolve as semanas seguintes ao dia da coleta: valem só a partir do dia em que
    aparecem (sem olhar o futuro)."""
    futuro = META + [{"data": "04/11/2026", "valor": "14.25"}]
    obs = bcb_selic_focus.observacoes_da_meta(json.dumps(futuro).encode(), AGORA)
    assert len(obs) == len(META)
    assert (obs["divulgado_em"] <= pd.Timestamp(AGORA.date())).all()


def test_le_o_focus_com_a_safra_na_data_da_pesquisa():
    obs = bcb_selic_focus.observacoes_do_focus(json.dumps(FOCUS).encode(), AGORA)
    assert list(obs["referencia"]) == [
        pd.Timestamp("2026-12-31"),
        pd.Timestamp("2027-12-31"),
    ]
    assert set(obs["divulgado_em"]) == {pd.Timestamp("2026-10-30")}
    assert list(obs["valor"]) == [14.25, 12.5]


def test_carga_grava_a_tabela_com_as_duas_series(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, "a" * 40)
    migrar_para("head", url=url)
    quando = datetime(2026, 11, 3, 12, tzinfo=UTC)
    originais = {
        "bcb-sgs-selic-meta": ("https://x/meta", json.dumps(META).encode()),
        "bcb-focus-selic-anual": ("https://x/focus", json.dumps(FOCUS).encode()),
    }
    with criar_engine(url).begin() as c:
        for fonte, (endereco, conteudo) in originais.items():
            caminho = acervo.guardar_original(fonte, endereco, conteudo, quando)
            registrar(
                c,
                fonte,
                endereco,
                conteudo,
                "ok",
                agora=quando,
                caminho_do_original=caminho,
            )
    base = tmp_path / "acervo" / "base"

    assert carga_selic_focus.main(["--base", str(base)]) == 0

    tabela = pd.read_parquet(base / "bcb_selic_focus" / "bcb_selic_focus.parquet")
    assert set(tabela["serie"]) == {"bcb-sgs-432", "focus-selic-anual"}
    assert len(tabela) == len(META) + len(FOCUS["value"])
    assert conferir_tabela(base / "bcb_selic_focus" / "bcb_selic_focus.parquet")
    assert date(2026, 10, 30) in set(tabela["divulgado_em"].dt.date)
