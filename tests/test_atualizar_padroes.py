"""Padrões por setor no banco e a tarefa que os recalcula (série 2 da base de ML, PR 4): migração de
ida e volta, gravar de novo não duplica, a leitura pega o corte mais recente até a data, e a tarefa
roda com as amostras reais da CVM. Sem internet."""

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from scripts import atualizar_padroes
from src import demonstracoes as dm
from src.banco import demonstracoes as repo
from src.banco import padroes as repo_padroes
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import padroes_setoriais
from src.setores import MERCADO

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
AGORA = datetime(2026, 10, 13, 12, tzinfo=UTC)


@pytest.fixture
def url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'p.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    migrar_para("head", url=url)
    return url


def _padroes(grupo="energia", indicador="roe", mediana=0.1):
    return pd.DataFrame(
        [
            {
                "grupo": grupo,
                "indicador": indicador,
                "empresas": 10,
                "percentis": {"50": mediana},
            }
        ]
    )


def test_migracao_sobe_e_desce(url):
    motor = criar_engine(url)
    try:
        assert "padroes_setoriais" in sa.inspect(motor).get_table_names()
        desfazer_ate("0027", url=url)
        assert "padroes_setoriais" not in sa.inspect(motor).get_table_names()
        migrar_para("head", url=url)
        assert "padroes_setoriais" in sa.inspect(motor).get_table_names()
    finally:
        motor.dispose()


def test_gravar_de_novo_substitui_o_corte_e_le_o_mais_recente(url):
    motor = criar_engine(url)
    try:
        with motor.begin() as c:
            repo_padroes.gravar_padroes(
                c, _padroes(mediana=0.1), date(2025, 12, 31), AGORA
            )
            repo_padroes.gravar_padroes(
                c, _padroes(mediana=0.2), date(2025, 12, 31), AGORA
            )
            repo_padroes.gravar_padroes(
                c, _padroes(mediana=0.3), date(2026, 6, 30), AGORA
            )
        with motor.connect() as c:
            assert (
                c.execute(
                    sa.select(sa.func.count()).select_from(padroes_setoriais)
                ).scalar()
                == 2
            )
            corte, tabela = repo_padroes.padroes_em(c, date(2026, 3, 1))
            assert corte == date(2025, 12, 31)
            assert tabela.iloc[0]["percentis"]["50"] == pytest.approx(0.2)
            assert repo_padroes.padroes_em(c, date(2025, 1, 1)) == (None, None)
    finally:
        motor.dispose()


def test_atualizar_padroes_com_as_amostras_reais(url):
    motor = criar_engine(url)
    try:
        with motor.begin() as c:
            repo.gravar_setores(
                c, dm.ler_setores((PASTA / "cad_cia_aberta.csv").read_bytes())
            )
            for arquivo, documento in (
                ("dfp_cia_aberta_2024.zip", "DFP"),
                ("dfp_cia_aberta_2025.zip", "DFP"),
            ):
                repo.gravar_demonstracoes(
                    c, *dm.ler_demonstracoes((PASTA / arquivo).read_bytes(), documento)
                )
        assert atualizar_padroes.main(["--datas", "2026-06-30", "2025-01-31"]) == 0
        with motor.connect() as c:
            corte, tabela = repo_padroes.padroes_em(c, date(2026, 7, 1))
            antes, nada = repo_padroes.padroes_em(c, date(2025, 2, 1))
        assert corte == date(2026, 6, 30)
        mercado = tabela[
            (tabela["grupo"] == MERCADO) & (tabela["indicador"] == "margem_liquida")
        ]
        assert (
            mercado["empresas"].iloc[0] >= 2
        )  # Petrobras e WEG (os bancos ficam fora)
        assert (
            antes is None or nada.empty
        )  # em janeiro de 2025 nenhuma DFP 2024 tinha saído
    finally:
        motor.dispose()


def test_preco_no_corte_e_o_ultimo_pregao_ate_a_data_e_descarta_exemplo():
    fechamentos = pd.DataFrame(
        {"Close": [10.0, 11.0, 12.0]},
        index=pd.to_datetime(["2025-12-29", "2025-12-30", "2026-01-02"]),
    )
    exemplo = fechamentos.copy()
    exemplo.attrs["origem"] = "exemplo"
    historicos = {"AAAA3.SA": fechamentos, "BBBB3.SA": exemplo}
    precos = atualizar_padroes.precos_nos_cortes(
        {"A": ["AAAA3.SA"], "B": ["BBBB3.SA"]},
        [date(2025, 12, 31)],
        buscar=lambda ticker: historicos[ticker],
    )
    assert precos[date(2025, 12, 31)] == {"A": 11.0}  # B só tinha dado de exemplo


def test_atualizar_padroes_com_precos_grava_os_multiplos(url, monkeypatch):
    motor = criar_engine(url)
    try:
        with motor.begin() as c:
            repo.gravar_setores(
                c, dm.ler_setores((PASTA / "cad_cia_aberta.csv").read_bytes())
            )
            repo.gravar_demonstracoes(
                c,
                *dm.ler_demonstracoes(
                    (PASTA / "dfp_cia_aberta_2025.zip").read_bytes(), "DFP"
                ),
            )
        monkeypatch.setattr(
            atualizar_padroes,
            "precos_nos_cortes",
            lambda tickers, cortes, buscar=None: {
                corte: {
                    cnpj: 30.0 for cnpj in ("33.000.167/0001-01", "84.429.695/0001-11")
                }
                for corte in cortes
            },
        )
        assert atualizar_padroes.main(["--datas", "2026-06-30", "--com-precos"]) == 0
        with motor.connect() as c:
            _, tabela = repo_padroes.padroes_em(c, date(2026, 7, 1))
        assert {"p_l", "p_vp"} <= set(tabela["indicador"])
    finally:
        motor.dispose()


def test_uma_empresa_que_quebra_nao_derruba_o_corte(monkeypatch):
    from src.banco import padroes as modulo

    contas = pd.DataFrame(
        [
            {"cnpj": c, "documento": "DFP", "referencia": date(2024, 12, 31), "versao": 1,
             "periodo": dm.EXERCICIO, "inicio": date(2024, 1, 1), "fim": date(2024, 12, 31),
             "conta": "receita", "valor": 100.0}
            for c in ("A", "B")
        ]
    )  # fmt: skip
    documentos = pd.DataFrame(
        [{"cnpj": c, "documento": "DFP", "referencia": date(2024, 12, 31), "versao": 1,
          "recebido_em": pd.Timestamp("2025-03-01")} for c in ("A", "B")]
    )  # fmt: skip
    entradas = modulo.Entradas(
        contas,
        documentos,
        {"A": "Energia Elétrica", "B": "Energia Elétrica"},
        pd.DataFrame(),
    )
    chamadas = []

    def indicadores(parte, setor, preco=None):
        chamadas.append(setor)
        if len(chamadas) == 1:
            raise ZeroDivisionError("dado estranho")
        return {"roe": 0.1}

    monkeypatch.setattr(modulo, "indicadores_da_empresa", indicadores)
    padroes = modulo.calcular_corte(entradas, date(2025, 6, 30))
    assert len(chamadas) == 2 and not padroes.empty


def test_so_o_que_falta_pula_o_corte_ja_gravado(url, monkeypatch):
    motor = criar_engine(url)
    try:
        with motor.begin() as c:
            repo_padroes.gravar_padroes(c, _padroes(), date(2026, 6, 30), AGORA)
        calculados = []
        monkeypatch.setattr(
            atualizar_padroes, "calcular_corte",
            lambda entradas, corte, precos=None: calculados.append(corte) or _padroes(),
        )  # fmt: skip
        assert (
            atualizar_padroes.main(
                ["--datas", "2026-05-31", "2026-06-30", "--so-o-que-falta"]
            )
            == 0
        )
        assert calculados == [date(2026, 5, 31)]
    finally:
        motor.dispose()


def test_tickers_so_das_empresas_da_cvm(url):
    from src.banco.modelo import tickers_dos_emissores

    motor = criar_engine(url)
    try:
        with motor.begin() as c:
            c.execute(
                sa.insert(tickers_dos_emissores),
                [
                    {
                        "ticker": "PETR4.SA",
                        "codigo": "PETR4",
                        "cnpj": "33.000.167/0001-01",
                        "empresa": "P",
                    },
                    {
                        "ticker": "AAPL",
                        "codigo": "AAPL",
                        "cnpj": "CIK0000320193",
                        "empresa": "Apple",
                    },
                ],
            )
        with motor.connect() as c:
            assert repo_padroes.tickers_por_empresa(c) == {
                "33.000.167/0001-01": ["PETR4.SA"]
            }
    finally:
        motor.dispose()
