"""Restaurar o backup da sala não ressuscita o que foi apagado (B-20, PR 6, decisão D4).

O teste faz o que a restauração faz: guarda uma "foto" da sala (linhas do banco e pastas do disco),
apaga de verdade pelos caminhos do app (apagar documento, apagar operação, expurgo e apagar conta),
devolve a foto e roda `reaplicar_exclusoes`. O que ficou na foto e foi apagado depois tem de sumir
de novo; o que nunca foi apagado tem de continuar lá.
"""

import shutil
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from src import conformidade
from src.banco import sala
from src.banco.modelo import (
    documentos_da_sala,
    metadata,
    operacoes,
)
from src.banco.usuarios import entrar
from src.sala import cofre, documentos, expurgo, guarda, restauracao
from tests import ajudantes_da_sala as gerar

HOJE = date(2026, 10, 21)
TABELAS = (operacoes, documentos_da_sala)


@pytest.fixture(autouse=True)
def chave_mestra(monkeypatch):
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, cofre.gerar_chave_mestra())


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    pasta = tmp_path / "dados_sala"
    monkeypatch.setenv(guarda.VARIAVEL_DA_PASTA, str(pasta))
    return pasta


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


def _conta(conexao, nome):
    return entrar(conexao, nome, f"{nome}@exemplo.com", nome)[0]


def _operacao(conexao, dono, nome, *, documentos_enviados=1):
    operacao = sala.criar_operacao(
        conexao, usuario_id=dono.id, tipo="ma", nome=nome, hoje=HOJE
    )
    enviados = [
        documentos.receber_documento(
            conexao,
            usuario_id=dono.id,
            operacao_id=operacao.id,
            nome_original=f"{nome}-{numero}.pdf",
            conteudo=gerar.pdf(f"{nome} {numero}"),
        ).documento
        for numero in range(documentos_enviados)
    ]
    return operacao, enviados


def _foto(conexao, raiz, destino):
    """As linhas da sala e uma cópia do disco: o que o backup da sala leva."""
    linhas = {
        tabela.name: [dict(l._mapping) for l in conexao.execute(sa.select(tabela))]
        for tabela in TABELAS
    }
    shutil.copytree(raiz, destino)
    return linhas


def _devolver(conexao, raiz, linhas, copia):
    """Restaura a foto por cima, sem conferir as chaves estrangeiras (o dump é só de dados)."""
    conexao.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
    for tabela in TABELAS:
        for linha in linhas[tabela.name]:
            existe = conexao.execute(
                sa.select(tabela.c.id).where(tabela.c.id == linha["id"])
            ).first()
            if not existe:
                conexao.execute(sa.insert(tabela).values(**linha))
    shutil.rmtree(raiz, ignore_errors=True)
    shutil.copytree(copia, raiz)


def _ids(conexao, tabela):
    return {l.id for l in conexao.execute(sa.select(tabela.c.id))}


def test_o_que_foi_apagado_depois_do_backup_nao_volta(conexao, raiz, tmp_path):
    ana, bia, cai = (
        _conta(conexao, "ana"),
        _conta(conexao, "bia"),
        _conta(conexao, "cai"),
    )
    mantida, (doc_mantido,) = _operacao(conexao, ana, "Mantida")
    sem_um, (doc_que_fica, doc_apagado) = _operacao(
        conexao, ana, "SemUm", documentos_enviados=2
    )
    apagada, _ = _operacao(conexao, bia, "Apagada")
    vencida, _ = _operacao(conexao, bia, "Vencida")
    da_conta, _ = _operacao(conexao, cai, "DaConta")
    foto = _foto(conexao, raiz, tmp_path / "copia")

    documentos.apagar_documento(
        conexao, usuario_id=ana.id, operacao_id=sem_um.id, documento_id=doc_apagado.id
    )
    documentos.apagar_operacao(conexao, usuario_id=bia.id, operacao_id=apagada.id)
    conexao.execute(
        sa.update(operacoes)
        .where(operacoes.c.id == vencida.id)
        .values(retencao_ate=HOJE - timedelta(days=1))
    )
    expurgo.expurgar(conexao, hoje=HOJE, raiz=raiz)
    conformidade.apagar_conta(conexao, cai.id)

    _devolver(conexao, raiz, foto, tmp_path / "copia")
    assert apagada.id in _ids(conexao, operacoes)  # a restauração ressuscitou tudo

    resultado = restauracao.reaplicar_exclusoes(conexao, raiz=raiz)

    assert _ids(conexao, operacoes) == {mantida.id, sem_um.id}
    assert _ids(conexao, documentos_da_sala) == {doc_mantido.id, doc_que_fica.id}
    assert resultado.operacoes == 3  # apagada, vencida e a da conta apagada
    assert resultado.documentos == 1
    for sumida in (apagada, vencida, da_conta):
        assert not guarda.pasta_da_operacao(raiz, sumida.id).exists()
    for viva in (mantida, sem_um):
        assert guarda.pasta_da_operacao(raiz, viva.id).is_dir()
    arquivos_de_sem_um = {
        p.name for p in guarda.pasta_da_operacao(raiz, sem_um.id).iterdir()
    }
    assert not any(str(doc_apagado.id) in nome for nome in arquivos_de_sem_um)
    assert any(str(doc_que_fica.id) in nome for nome in arquivos_de_sem_um)


def test_sem_nada_excluido_a_restauracao_fica_como_veio(conexao, raiz):
    ana = _conta(conexao, "ana")
    viva, _ = _operacao(conexao, ana, "Viva")
    antes = sorted(p.name for p in guarda.pasta_da_operacao(raiz, viva.id).iterdir())

    resultado = restauracao.reaplicar_exclusoes(conexao, raiz=raiz)

    assert (resultado.operacoes, resultado.documentos, resultado.pastas) == (0, 0, 0)
    assert _ids(conexao, operacoes) == {viva.id}
    assert antes == sorted(
        p.name for p in guarda.pasta_da_operacao(raiz, viva.id).iterdir()
    )
