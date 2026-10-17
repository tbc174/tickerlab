"""Exportação controlada do acervo (Radar, PR 7): só admins, só fontes com licença que permite,
nunca o Yahoo, LEIA-ME com a licença e o pedido na auditoria."""

import io
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from src import auditoria
from src import exportacao_do_acervo as exp
from src.administracao import PermissaoNegadaError
from src.banco import series as acervo_de_series
from src.banco.modelo import demonstracoes_versoes
from src.banco.series import SerieDoAcervo
from src.banco.usuarios import entrar
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para

AGORA = datetime(2026, 10, 13, 9, tzinfo=UTC)
IPCA = SerieDoAcervo("bcb-sgs-433", "IPCA", "% no mês", "mensal")
IBOV = SerieDoAcervo("yahoo-bvsp", "Ibovespa", "pontos", "diária", uso_interno=True)
CURVA = SerieDoAcervo("tesouro-eua-10a", "10 anos", "fração ao ano", "diária")


@pytest.fixture
def pessoas(banco):
    with banco.begin() as c:
        chefe = entrar(
            c, "chefe", "chefe@exemplo.com", emails_de_admin=("chefe@exemplo.com",)
        )[0]
        ana = entrar(c, "ana", "ana@exemplo.com")[0]
        for serie, valor in ((IPCA, 0.44), (IBOV, 130_000.0), (CURVA, 0.041)):
            acervo_de_series.garantir_serie(c, serie)
            valores = pd.Series([valor], index=[pd.Timestamp("2026-09-01")])
            acervo_de_series.gravar(c, serie.codigo, valores, date(2026, 10, 10))
    return chefe, ana


def _abrir(conteudo: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
        return {nome: arquivo.read(nome) for nome in arquivo.namelist()}


def test_series_saem_sem_o_yahoo_com_licenca_e_auditoria(banco, pessoas):
    chefe, _ = pessoas
    with banco.begin() as c:
        nome, conteudo = exp.exportar(c, chefe.id, "series", "csv", AGORA)
        registro = auditoria.listar_recentes(c)[0]
    arquivos = _abrir(conteudo)
    assert nome == "tickerlab-series-20261013.zip"
    tabela = pd.read_csv(io.BytesIO(arquivos["tickerlab-series-20261013.csv"]))
    assert set(tabela["serie"]) == {"bcb-sgs-433", "tesouro-eua-10a"}
    assert not tabela["serie"].str.startswith("yahoo").any()
    leia_me = arquivos["LEIA-ME.txt"].decode("utf-8")
    assert "BCB: ODbL" in leia_me and "TESOURO" in leia_me and "ODbL 1.0" in leia_me
    assert "yahoo" not in leia_me.lower()
    assert registro.acao == exp.ACAO_ACERVO_EXPORTADO
    assert registro.ator_id == chefe.id
    assert registro.detalhes == {"base": "series", "formato": "csv", "linhas": 2}


def test_quem_nao_e_admin_nao_exporta_nem_deixa_rastro(banco, pessoas):
    _, ana = pessoas
    with banco.begin() as c:
        with pytest.raises(PermissaoNegadaError):
            exp.exportar(c, ana.id, "series", "csv", AGORA)
        with pytest.raises(PermissaoNegadaError):
            exp.exportar(c, None, "series", "csv", AGORA)
        assert auditoria.listar_recentes(c) == []


@pytest.mark.parametrize(("base", "formato"), [("precos", "csv"), ("series", "xlsx")])
def test_base_ou_formato_fora_da_lista(banco, pessoas, base, formato):
    chefe, _ = pessoas
    with banco.begin() as c, pytest.raises(exp.ExportacaoInvalidaError):
        exp.exportar(c, chefe.id, base, formato, AGORA)


def test_parquet_e_base_vazia(banco, pessoas):
    chefe, _ = pessoas
    with banco.begin() as c:
        _, conteudo = exp.exportar(c, chefe.id, "series", "parquet", AGORA)
        _, vazia = exp.exportar(c, chefe.id, "eventos", "csv", AGORA)
    tabela = pd.read_parquet(
        io.BytesIO(_abrir(conteudo)["tickerlab-series-20261013.parquet"])
    )
    assert len(tabela) == 2
    assert "0 linhas" in _abrir(vazia)["LEIA-ME.txt"].decode("utf-8")


def test_demonstracoes_dizem_a_fonte_de_cada_linha(banco, pessoas):
    linha = {
        "documento": "DFP", "referencia": date(2025, 12, 31), "periodo": "exercicio",
        "fim": date(2025, 12, 31), "conta": "receita", "versao": 1, "valor": 1.0,
        "registrado_em": AGORA,
    }  # fmt: skip
    with banco.begin() as c:
        c.execute(
            sa.insert(demonstracoes_versoes),
            [
                {**linha, "cnpj": "33.000.167/0001-01"},
                {**linha, "cnpj": "CIK0000320193"},
            ],
        )
        tabela = exp.ler_base(c, "demonstracoes")
        leia_me = exp.leia_me("demonstracoes", tabela, AGORA)
    assert sorted(tabela["fonte"]) == ["cvm", "sec"]
    assert "id_da_versao" not in tabela
    assert "CVM: ODbL" in leia_me and "SEC: " in leia_me


def test_admin_prepara_e_baixa_pela_tela(banco, monkeypatch, pessoas):
    entrar_como(monkeypatch, "chefe", "chefe@exemplo.com")
    app = abrir_app("admin")
    assert id_do_usuario(banco, "chefe") == pessoas[0].id
    app.selectbox(key="admin_exportar_base").select("series").run()
    app.button(key="admin_exportar").click().run()
    app = ir_para(app, "admin")
    assert not app.exception
    with banco.connect() as c:
        assert auditoria.listar_recentes(c)[0].acao == exp.ACAO_ACERVO_EXPORTADO


def test_serie_nao_comercial_sem_a_marca_de_uso_interno_da_erro(banco, pessoas):
    """A trava das licenças (ADR 0008, Emenda 1): o IGP-M é da FGV, mesmo vindo do SGS do BC. Se a
    série perder a marca `uso_interno`, a exportação dá erro em vez de sair."""
    from src.banco.coletas import LicencaNaoPermiteError

    chefe, _ = pessoas
    igpm = SerieDoAcervo("bcb-sgs-189", "IGP-M", "% no mês", "mensal")
    with banco.begin() as c:
        acervo_de_series.garantir_serie(c, igpm)
        valores = pd.Series([0.5], index=[pd.Timestamp("2026-09-01")])
        acervo_de_series.gravar(c, igpm.codigo, valores, date(2026, 10, 10))
    with banco.begin() as c, pytest.raises(LicencaNaoPermiteError, match="bcb-sgs-189"):
        exp.exportar(c, chefe.id, "series", "csv", AGORA)
