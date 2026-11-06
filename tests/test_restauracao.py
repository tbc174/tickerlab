"""Restaurar o backup não ressuscita a conta que a pessoa mandou apagar (privacidade v12).

Faz o que a restauração faz: guarda uma "foto" das contas e dos dados delas, apaga pelo caminho do
app (`conformidade.apagar_conta`), devolve a foto e roda `reaplicar_contas_apagadas`.
"""

from datetime import date

import pytest
import sqlalchemy as sa

from src import auditoria, conformidade, restauracao
from src.banco import dados_do_usuario as repo
from src.banco import sala
from src.banco.modelo import favoritos, metadata, operacoes, usuarios
from src.banco.usuarios import entrar
from src.sala import guarda

TABELAS = (usuarios, operacoes, favoritos)


@pytest.fixture
def motor():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    return motor


@pytest.fixture
def conexao(motor):
    with motor.begin() as conexao:
        yield conexao


@pytest.fixture(autouse=True)
def pasta_da_sala(tmp_path, monkeypatch):
    monkeypatch.setenv(guarda.VARIAVEL_DA_PASTA, str(tmp_path / "dados_sala"))


def _conta(conexao, nome):
    return entrar(conexao, nome, f"{nome}@exemplo.com", nome)[0]


def _foto(conexao):
    return {
        tabela.name: [dict(l._mapping) for l in conexao.execute(sa.select(tabela))]
        for tabela in TABELAS
    }


def _devolver(conexao, foto):
    """Restaura a foto por cima, só o que não existe mais (o dump traz só os dados)."""
    for tabela in TABELAS:
        for linha in foto[tabela.name]:
            existe = conexao.execute(
                sa.select(sa.literal(1)).where(
                    *[c == linha[c.name] for c in tabela.primary_key.columns]
                )
            ).first()
            if not existe:
                conexao.execute(sa.insert(tabela).values(**linha))


def _ids(conexao):
    return {l.id for l in conexao.execute(sa.select(usuarios.c.id))}


def _favoritos_de(conexao, usuario_id):
    return repo.listar_favoritos(conexao, usuario_id)


def test_conta_apagada_depois_da_copia_nao_volta(conexao):
    ana, bia = _conta(conexao, "ana"), _conta(conexao, "bia")
    repo.salvar_favoritos(conexao, ana.id, ["AAPL"])
    repo.salvar_favoritos(conexao, bia.id, ["PETR4"])
    foto = _foto(conexao)

    conformidade.apagar_conta(conexao, ana.id)
    _devolver(conexao, foto)
    assert ana.id in _ids(conexao)  # a restauração ressuscitou a conta

    resultado = restauracao.reaplicar_contas_apagadas(conexao)

    assert resultado.contas == 1
    assert _ids(conexao) == {bia.id}  # a Bia nunca apagou: fica
    assert _favoritos_de(conexao, ana.id) == []  # os dados dela (cascata) também somem
    assert _favoritos_de(conexao, bia.id) == ["PETR4"]  # isolamento por usuario_id


def test_rodar_duas_vezes_da_o_mesmo_resultado(conexao):
    ana, bia = _conta(conexao, "ana"), _conta(conexao, "bia")
    foto = _foto(conexao)
    conformidade.apagar_conta(conexao, ana.id)
    _devolver(conexao, foto)

    primeira = restauracao.reaplicar_contas_apagadas(conexao)
    antes = _ids(conexao)
    auditoria_antes = len(auditoria.listar_recentes(conexao, 100))
    segunda = restauracao.reaplicar_contas_apagadas(conexao)

    assert (primeira.contas, segunda.contas) == (1, 0)
    assert _ids(conexao) == antes == {bia.id}
    assert len(auditoria.listar_recentes(conexao, 100)) == auditoria_antes


def test_sem_conta_apagada_na_auditoria_nada_muda(conexao):
    ana = _conta(conexao, "ana")
    assert restauracao.reaplicar_contas_apagadas(conexao).contas == 0
    assert _ids(conexao) == {ana.id}


def test_pasta_da_sala_da_conta_apagada_sai_do_disco(conexao):
    ana = _conta(conexao, "ana")
    operacao = sala.criar_operacao(
        conexao, usuario_id=ana.id, tipo="ma", nome="X", hoje=date(2026, 10, 21)
    )
    pasta = guarda.pasta_da_operacao(guarda.pasta_da_sala(), operacao.id)
    foto = _foto(conexao)

    conformidade.apagar_conta(conexao, ana.id)
    _devolver(conexao, foto)
    pasta.mkdir(parents=True)  # a restauração do disco devolveu a pasta
    (pasta / "documento.bin").write_bytes(b"x")

    restauracao.reaplicar_contas_apagadas(conexao)

    assert not pasta.exists()
    assert _ids(conexao) == set()
