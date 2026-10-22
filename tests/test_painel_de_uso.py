"""Painel de uso: ativos por semana, relatórios e PDFs; só contagens, só para administradores."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa

from src import painel_de_uso as painel
from src.administracao import PermissaoNegadaError
from src.banco.modelo import metadata, relatorios, sessoes_de_login, simulacoes
from src.banco.usuarios import entrar

SEGUNDA = date(2026, 10, 19)


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


@pytest.fixture
def chefe(conexao):
    return entrar(
        conexao,
        "chefe",
        "chefe@exemplo.com",
        "Chefe",
        emails_de_admin=("chefe@exemplo.com",),
        email_confirmado=True,
    )[0]


def _pessoa(conexao, nome):
    return entrar(conexao, nome, f"{nome}@exemplo.com", nome)[0].id


def _em(dias=0):
    """Meio-dia (UTC) da segunda de referência, deslocado em `dias`."""
    base = datetime(SEGUNDA.year, SEGUNDA.month, SEGUNDA.day, 12, tzinfo=UTC)
    return base + timedelta(days=dias)


def _simulacao(conexao, usuario_id, quando):
    conexao.execute(
        sa.insert(simulacoes).values(
            id=uuid.uuid4(),
            usuario_id=usuario_id,
            tipo="backtest",
            nome="x",
            parametros={},
            resultado={},
            criada_em=quando,
        )
    )


def _relatorio(conexao, usuario_id, quando, tipo="ativo"):
    conexao.execute(
        sa.insert(relatorios).values(
            id=uuid.uuid4(), usuario_id=usuario_id, tipo=tipo, criado_em=quando
        )
    )


def test_segunda_da_semana():
    assert painel.segunda_da_semana(date(2026, 10, 25)) == SEGUNDA  # domingo
    assert painel.segunda_da_semana(SEGUNDA) == SEGUNDA


def test_ativo_precisa_de_duas_semanas_na_janela(conexao):
    ana, bia = _pessoa(conexao, "ana"), _pessoa(conexao, "bia")
    _simulacao(conexao, ana, _em())
    _simulacao(conexao, ana, _em(-7))
    _simulacao(conexao, bia, _em())  # só uma semana
    n = painel.numeros_da_semana(conexao, SEGUNDA)
    assert n["ativos_na_semana"] == 2
    assert n["ativos"] == 1


def test_uso_antes_da_janela_nao_conta(conexao):
    ana = _pessoa(conexao, "ana")
    _simulacao(conexao, ana, _em())
    _simulacao(conexao, ana, _em(-7 * painel.SEMANAS_DA_JANELA))
    assert painel.numeros_da_semana(conexao, SEGUNDA)["ativos"] == 0


def test_login_conta_como_uso(conexao):
    ana = _pessoa(conexao, "ana")
    for dias in (0, -7):
        conexao.execute(
            sa.insert(sessoes_de_login).values(
                id=uuid.uuid4(),
                usuario_id=ana,
                hash_do_token=uuid.uuid4().hex * 2,
                provedor="email",
                criada_em=_em(dias),
                expira_em=_em(30),
            )
        )
    assert painel.numeros_da_semana(conexao, SEGUNDA)["ativos"] == 1


def test_relatorios_por_tipo_so_da_semana(conexao):
    ana = _pessoa(conexao, "ana")
    _relatorio(conexao, ana, _em())
    _relatorio(conexao, ana, _em(2), "backtest")
    _relatorio(conexao, ana, _em(-1))  # semana anterior
    n = painel.numeros_da_semana(conexao, SEGUNDA)
    assert n["relatorios_gerados"] == 2
    assert n["pdfs_entregues"] == 2
    assert n["relatorios_por_tipo"] == {"ativo": 1, "backtest": 1}


def test_semana_fechada_nao_muda_com_dado_novo(conexao):
    ana = _pessoa(conexao, "ana")
    _simulacao(conexao, ana, _em())
    _relatorio(conexao, ana, _em())
    antes = painel.numeros_da_semana(conexao, SEGUNDA)
    _simulacao(conexao, ana, _em(8))
    _relatorio(conexao, ana, _em(9))
    assert painel.numeros_da_semana(conexao, SEGUNDA) == antes


def test_historico_so_para_administrador(conexao, chefe):
    ana = _pessoa(conexao, "ana")
    with pytest.raises(PermissaoNegadaError):
        painel.historico_semanal(conexao, ana)
    linhas = painel.historico_semanal(
        conexao, chefe.id, hoje=date(2026, 10, 22), semanas=3
    )
    assert [l["semana"] for l in linhas] == ["2026-10-05", "2026-10-12", "2026-10-19"]


def test_nada_de_pessoa_na_saida(conexao, chefe):
    texto = str(painel.historico_semanal(conexao, chefe.id, hoje=date(2026, 10, 22)))
    assert "@" not in texto and "chefe" not in texto


def test_historico_sem_checagem_para_scripts(conexao):
    ana = _pessoa(conexao, "ana")
    _relatorio(conexao, ana, _em())
    linhas = painel.historico(conexao, hoje=date(2026, 10, 22), semanas=1)
    assert linhas[0]["relatorios_gerados"] == 1
