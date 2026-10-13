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
