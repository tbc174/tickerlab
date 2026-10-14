"""Testes de src/banco/teses.py: as anotações do Diário de Teses de cada pessoa."""

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from src import diario_de_teses as diario
from src.banco import teses as repo
from src.banco.dados_do_usuario import apagar_simulacao, salvar_simulacao
from src.banco.modelo import metadata, teses, teses_estrategias
from src.banco.usuarios import apagar_conta, entrar


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


@pytest.fixture
def ana(conexao):
    return entrar(conexao, "sub-ana", "ana@exemplo.com", "Ana")[0]


@pytest.fixture
def bia(conexao):
    return entrar(conexao, "sub-bia", "bia@exemplo.com", "Bia")[0]


def _backtest(conexao, usuario, ticker="PETR4.SA", tipo="backtest"):
    return salvar_simulacao(
        conexao, usuario.id, tipo, f"{tipo} {ticker}", {"ticker": ticker}, {}
    )


def test_escrever_e_listar(conexao, ana):
    anotacao = repo.escrever(conexao, ana.id, "petr4", "  Comprei pelo dividendo.  ")
    assert anotacao.ticker == "PETR4.SA"
    assert anotacao.texto == "Comprei pelo dividendo."
    assert anotacao.criada_em.tzinfo is not None
    assert repo.listar(conexao, ana.id) == [anotacao]


def _mudar_hora(conexao, anotacao, hora):
    conexao.execute(
        sa.update(teses).where(teses.c.id == anotacao.id).values(criada_em=hora)
    )


def test_lista_vem_da_mais_nova_para_a_mais_antiga(conexao, ana):
    primeira = repo.escrever(conexao, ana.id, "PETR4", "primeira")
    segunda = repo.escrever(conexao, ana.id, "VALE3", "segunda")
    # horas fixas: no Windows o relógio anda de 15,6 em 15,6 ms e as duas podiam sair com a
    # mesma hora; aí quem desempata é o id (aleatório) e a ordem virava cara ou coroa
    _mudar_hora(conexao, primeira, datetime(2026, 10, 13, 9, tzinfo=UTC))
    _mudar_hora(conexao, segunda, datetime(2026, 10, 14, 9, tzinfo=UTC))
    assert [a.id for a in repo.listar(conexao, ana.id)] == [segunda.id, primeira.id]


def test_texto_e_ativo_invalidos_sao_recusados(conexao, ana):
    with pytest.raises(diario.TeseInvalidaError):
        repo.escrever(conexao, ana.id, "PETR4", "   ")
    with pytest.raises(diario.TeseInvalidaError):
        repo.escrever(conexao, ana.id, "<b>", "tese")
    assert repo.listar(conexao, ana.id) == []


def test_tetos_do_diario(conexao, ana, monkeypatch):
    monkeypatch.setattr(diario, "MAXIMO_DE_ANOTACOES", 2)
    repo.escrever(conexao, ana.id, "PETR4", "1")
    repo.escrever(conexao, ana.id, "PETR4", "2")
    with pytest.raises(diario.TeseInvalidaError, match="2 anotações"):
        repo.escrever(conexao, ana.id, "PETR4", "3")


def test_diario_de_uma_conta_nao_ve_nem_apaga_o_da_outra(conexao, ana, bia):
    da_ana = repo.escrever(conexao, ana.id, "PETR4", "da Ana")
    assert repo.listar(conexao, bia.id) == []
    assert repo.apagar(conexao, bia.id, da_ana.id) is False
    assert repo.listar(conexao, ana.id) == [da_ana]
    assert repo.dados_para_exportar(conexao, bia.id) == []


def test_apagar_a_propria_anotacao(conexao, ana):
    anotacao = repo.escrever(conexao, ana.id, "PETR4", "tese")
    assert repo.apagar(conexao, ana.id, anotacao.id) is True
    assert repo.listar(conexao, ana.id) == []
    assert repo.apagar(conexao, ana.id, anotacao.id) is False


# --- a ligação com os backtests salvos -------------------------------------------------------


def test_ligar_backtests_do_mesmo_ativo(conexao, ana):
    um, dois = _backtest(conexao, ana), _backtest(conexao, ana, "petr4")
    anotacao = repo.escrever(conexao, ana.id, "PETR4", "tese", [um.id, dois.id, um.id])
    assert set(anotacao.estrategias) == {um.id, dois.id}
    assert repo.listar(conexao, ana.id)[0].estrategias == anotacao.estrategias


@pytest.mark.parametrize(
    "outro", [{"ticker": "VALE3.SA"}, {"tipo": "carteira"}], ids=["ativo", "tipo"]
)
def test_so_liga_backtest_do_mesmo_ativo(conexao, ana, outro):
    errado = _backtest(conexao, ana, **outro)
    with pytest.raises(diario.TeseInvalidaError, match="PETR4"):
        repo.escrever(conexao, ana.id, "PETR4", "tese", [errado.id])
    assert repo.listar(conexao, ana.id) == []


def test_nao_liga_backtest_de_outra_conta(conexao, ana, bia):
    da_bia = _backtest(conexao, bia)
    with pytest.raises(diario.TeseInvalidaError):
        repo.escrever(conexao, ana.id, "PETR4", "tese", [da_bia.id])
    with pytest.raises(diario.TeseInvalidaError):
        repo.escrever(conexao, ana.id, "PETR4", "tese", [uuid.uuid4()])
    assert conexao.execute(sa.select(sa.func.count()).select_from(teses)).scalar() == 0


def test_no_maximo_dez_backtests_por_anotacao(conexao, ana):
    ids = [_backtest(conexao, ana).id for _ in range(diario.MAXIMO_DE_ESTRATEGIAS + 1)]
    with pytest.raises(diario.TeseInvalidaError, match="10"):
        repo.escrever(conexao, ana.id, "PETR4", "tese", ids)


def test_apagar_o_backtest_mantem_a_anotacao_e_tira_a_ligacao(conexao, ana):
    backtest = _backtest(conexao, ana)
    anotacao = repo.escrever(conexao, ana.id, "PETR4", "tese", [backtest.id])
    apagar_simulacao(conexao, ana.id, backtest.id)
    (restante,) = repo.listar(conexao, ana.id)
    assert restante.id == anotacao.id and restante.estrategias == ()


def test_apagar_a_conta_apaga_o_diario(conexao, ana, bia):
    backtest = _backtest(conexao, ana)
    repo.escrever(conexao, ana.id, "PETR4", "tese", [backtest.id])
    da_bia = repo.escrever(conexao, bia.id, "PETR4", "da Bia")
    apagar_conta(conexao, ana.id)
    assert conexao.execute(sa.select(teses.c.id)).scalars().all() == [da_bia.id]
    assert conexao.execute(sa.select(teses_estrategias)).all() == []


# --- exportação -----------------------------------------------------------------------------


def test_exportar_traz_o_texto_a_data_e_os_backtests_ligados(conexao, ana):
    backtest = _backtest(conexao, ana)
    anotacao = repo.escrever(conexao, ana.id, "PETR4", "tese", [backtest.id])
    assert repo.dados_para_exportar(conexao, ana.id) == [
        {
            "ticker": "PETR4.SA",
            "texto": "tese",
            "criada_em": anotacao.criada_em.isoformat(),
            "estrategias": [backtest.nome],
        }
    ]
