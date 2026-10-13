"""Testes da leitura do setor da CVM de cada ticker (Raio-X da carteira)."""

import pytest
import sqlalchemy as sa

from src.banco.demonstracoes import setores_dos_tickers
from src.banco.modelo import metadata, setores_cvm, tickers_dos_emissores


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    metadata.create_all(motor)
    with motor.begin() as conexao:
        conexao.execute(
            sa.insert(tickers_dos_emissores),
            [
                {
                    "ticker": "PETR4.SA",
                    "codigo": "PETR4",
                    "cnpj": "33.000.167/0001-01",
                    "empresa": "Petrobras",
                },
                {
                    "ticker": "VALE3.SA",
                    "codigo": "VALE3",
                    "cnpj": "33.592.510/0001-54",
                    "empresa": "Vale",
                },
            ],
        )
        conexao.execute(
            sa.insert(setores_cvm),
            [{"cnpj": "33.000.167/0001-01", "setor": "Petróleo e Gás"}],
        )
        yield conexao


def test_setor_vem_da_empresa_do_ticker(conexao):
    assert setores_dos_tickers(conexao, ["PETR4.SA", "VALE3.SA", "HGLG11.SA"]) == {
        "PETR4.SA": "Petróleo e Gás"
    }


def test_sem_tickers_nao_consulta(conexao):
    assert setores_dos_tickers(conexao, []) == {}
