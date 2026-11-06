"""Exportação das entradas da análise escrita (ADR 0100) a partir do banco do app e das fichas do dossiê.

SQLite migrado com as demonstrações da CPFL e a ficha de exemplo do dossiê; sem rede.
"""

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from scripts import exportar_entradas_da_analise as ex
from src import demonstracoes as dm
from src.banco.conexao import criar_engine, migrar_para
from src.banco.demonstracoes import gravar_demonstracoes, gravar_setor
from src.banco.eventos import gravar_tickers
from tests import test_relatorio_empresa_v2 as ficha_v2
from tests.ajudantes_da_ficha import FICHA_DE_17_10

CPFL = ficha_v2.CPFL
CPFL_DIGITOS = "02429144000193"
SEM_TICKER = "11111111000191"  # tem ficha, mas ninguém negocia
AGORA = datetime(2026, 10, 17, 9, tzinfo=UTC)
CORTE = date(2026, 10, 17)


@pytest.fixture
def conexao(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}"
    migrar_para("head", url=url)
    motor = criar_engine(url)
    with motor.begin() as c:
        for arquivo, tipo in ficha_v2.ARQUIVOS:
            contas, documentos = dm.ler_demonstracoes(
                (ficha_v2.PASTA / arquivo).read_bytes(), tipo
            )
            gravar_demonstracoes(c, contas, documentos, AGORA)
        gravar_setor(c, CPFL, ficha_v2.SETOR)
        gravar_tickers(
            c,
            pd.DataFrame(
                {
                    "ticker": ["CPFE3.SA"],
                    "codigo": ["CPFE3"],
                    "cnpj": [CPFL],
                    "empresa": ["CPFL ENERGIA S.A."],
                    "valor_mobiliario": ["Ações Ordinárias"],
                }
            ),
            AGORA,
        )
    with motor.connect() as c:
        yield c
    motor.dispose()


@pytest.fixture
def dossies(tmp_path, monkeypatch) -> Path:
    """`atual/` com a ficha da CPFL, uma ficha de empresa sem ticker e o manifesto do dossiê."""
    atual = tmp_path / "dossies" / "atual"
    atual.mkdir(parents=True)
    shutil.copy(FICHA_DE_17_10, atual / f"{CPFL_DIGITOS}.json")
    outra = json.loads(FICHA_DE_17_10.read_text(encoding="utf-8"))
    outra["cnpj"] = SEM_TICKER
    (atual / f"{SEM_TICKER}.json").write_text(json.dumps(outra), encoding="utf-8")
    (atual / "manifesto.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(tmp_path / "dossies"))
    return tmp_path / "dossies"


def test_lista_so_os_cnpjs_das_fichas(dossies):
    assert ex.cnpjs_com_ficha(dossies) == [CPFL_DIGITOS, SEM_TICKER]


def test_cnpj_com_mascara():
    assert ex.cnpj_com_mascara(CPFL_DIGITOS) == CPFL


def test_exporta_a_entrada_da_cpfl_e_anota_quem_ficou_de_fora(
    conexao, dossies, tmp_path
):
    saida = tmp_path / "entradas"

    manifesto = ex.exportar(conexao, dossies, saida, CORTE)

    entrada = json.loads((saida / f"{CPFL_DIGITOS}.json").read_text(encoding="utf-8"))
    assert entrada["cnpj"] == CPFL
    assert entrada["ticker"] == "CPFE3.SA"
    assert entrada["corte"] == CORTE.isoformat()
    assert entrada["linhas"], "a entrada tem as linhas da ficha"
    assert any(linha.get("so_pro") for linha in entrada["linhas"]), "o dossiê entrou"
    assert manifesto["fichas"] == 2
    assert manifesto["exportadas"] == 1
    assert manifesto["empresas"][CPFL_DIGITOS]["setor"] == ficha_v2.SETOR
    assert manifesto["de_fora"] == {SEM_TICKER: "sem ticker no cadastro"}
    gravado = json.loads((saida / ex.MANIFESTO).read_text(encoding="utf-8"))
    assert gravado["de_fora"] == manifesto["de_fora"]


def test_empresa_dos_eua_e_sem_demonstracoes_ficam_de_fora(conexao):
    with pytest.raises(ex.SemEntradaError, match="CIK"):
        ex.entrada_da_empresa(conexao, "CIK0000320193", CORTE)
    with conexao.begin_nested():
        gravar_tickers(
            conexao,
            pd.DataFrame(
                {
                    "ticker": ["XXXX3.SA"],
                    "codigo": ["XXXX3"],
                    "cnpj": [ex.cnpj_com_mascara(SEM_TICKER)],
                    "empresa": ["SEM CONTAS S.A."],
                    "valor_mobiliario": ["Ações Ordinárias"],
                }
            ),
            AGORA,
        )
        with pytest.raises(ex.SemEntradaError, match="sem demonstrações"):
            ex.entrada_da_empresa(conexao, ex.cnpj_com_mascara(SEM_TICKER), CORTE)


def test_erro_inesperado_numa_empresa_nao_para_as_outras(
    conexao, dossies, tmp_path, monkeypatch
):
    def explode(_conexao, cnpj, _corte):
        if cnpj == CPFL:
            raise RuntimeError("quebrou")
        raise ex.SemEntradaError("sem ticker no cadastro")

    monkeypatch.setattr(ex, "entrada_da_empresa", explode)

    manifesto = ex.exportar(conexao, dossies, tmp_path / "entradas", CORTE)

    assert manifesto["exportadas"] == 0
    assert manifesto["de_fora"][CPFL_DIGITOS] == "erro inesperado: RuntimeError"
    assert manifesto["de_fora"][SEM_TICKER] == "sem ticker no cadastro"


def test_linha_de_comando_grava_na_pasta_pedida(
    conexao, dossies, tmp_path, monkeypatch
):
    class Motor:
        def connect(self):
            return conexao

    monkeypatch.setattr(ex, "obter_engine", lambda: Motor())
    saida = tmp_path / "saida"

    assert (
        ex.main(
            ["--saida", str(saida), "--dossies", str(dossies), "--corte", "2026-10-17"]
        )
        == 0
    )

    assert (saida / f"{CPFL_DIGITOS}.json").exists()
    assert (
        json.loads((saida / ex.MANIFESTO).read_text(encoding="utf-8"))["corte"]
        == "2026-10-17"
    )
