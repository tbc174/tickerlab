"""Migração 0044 (cadastro completo da CVM): sobe, desce e a coleta preenche as colunas novas.

Roda em SQLite por padrão e no PostgreSQL de verdade no CI (TICKERLAB_TEST_DATABASE_URL): o que
importa é que o banco migrado, não só o modelo, tenha as cinco colunas, e que o `downgrade` as tire
sem levar o setor junto.
"""

import os
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from src.banco import demonstracoes as repo
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import setores_cvm

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")
COLUNAS_NOVAS = {"situacao", "situacao_desde", "categoria", "registro", "atualizado_em"}
AGORA = datetime(2026, 10, 22, 10, 10, tzinfo=UTC)

pytestmark = pytest.mark.xdist_group("postgres")


@pytest.fixture
def url(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'cadastro.sqlite').as_posix()}"
    if URL_DE_TESTE:
        migrar_para("base", url)
    migrar_para("head", url)
    yield url
    if URL_DE_TESTE:
        migrar_para("base", url)


def _colunas(url: str) -> set[str]:
    motor = criar_engine(url)
    try:
        return {c["name"] for c in sa.inspect(motor).get_columns("setores_cvm")}
    finally:
        motor.dispose()


def test_sobe_e_desce_sem_perder_o_setor(url) -> None:
    assert _colunas(url) >= COLUNAS_NOVAS
    desfazer_ate("0043", url)
    assert _colunas(url) == {"cnpj", "setor"}
    migrar_para("head", url)
    assert _colunas(url) >= COLUNAS_NOVAS


def test_coleta_preenche_o_cadastro_e_a_sec_fica_so_com_o_setor(url) -> None:
    cadastro = pd.DataFrame(
        {
            "cnpj": ["33.000.167/0001-01"],
            "setor": ["Petróleo e Gás"],
            "situacao": ["ATIVO"],
            "situacao_desde": [date(2000, 1, 1)],
            "categoria": ["Categoria A"],
            "registro": [date(1977, 7, 20)],
        }
    )
    motor = criar_engine(url)
    try:
        with motor.begin() as conexao:
            repo.gravar_setor(conexao, "CIK0000320193", "Electronic Computers")
            repo.gravar_setores(conexao, cadastro, AGORA)
            linhas = {
                linha.cnpj: linha
                for linha in conexao.execute(sa.select(setores_cvm)).all()
            }
    finally:
        motor.dispose()
    petrobras = linhas["33.000.167/0001-01"]
    assert (petrobras.situacao, petrobras.categoria) == ("ATIVO", "Categoria A")
    assert (petrobras.situacao_desde, petrobras.registro) == (
        date(2000, 1, 1),
        date(1977, 7, 20),
    )
    assert petrobras.atualizado_em.replace(tzinfo=UTC) == AGORA
    apple = linhas["CIK0000320193"]
    assert apple.setor == "Electronic Computers" and apple.situacao is None
