"""Troca da chave-mestra da sala (RIPD da sala, R-S2): toda operação abre, a antiga sai com zero."""

import base64
from datetime import date

import pytest
import sqlalchemy as sa

from src.banco import sala
from src.banco.modelo import metadata, operacoes
from src.banco.usuarios import entrar
from src.sala import cofre, documentos, guarda, troca_de_chave
from tests import ajudantes_da_sala as gerar

HOJE = date(2026, 10, 22)
V2 = "v2:" + base64.b64encode(bytes(range(32))).decode()  # chave de teste


@pytest.fixture(autouse=True)
def mestras(monkeypatch):
    """A variável com a v1; os testes acrescentam a v2 na frente, como o script faz."""
    v1 = cofre.gerar_chave_mestra()
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, v1)
    return v1


@pytest.fixture(autouse=True)
def raiz(tmp_path, monkeypatch):
    pasta = tmp_path / "dados_sala"
    monkeypatch.setenv(guarda.VARIAVEL_DA_PASTA, str(pasta))
    return pasta


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


def _acrescentar_v2(monkeypatch, v1):
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, f"{V2},{v1}")


def _sala(conexao, nome):
    dono = entrar(conexao, nome, f"{nome}@exemplo.com", nome)[0]
    operacao = sala.criar_operacao(
        conexao, usuario_id=dono.id, tipo="ma", nome=nome, hoje=HOJE
    )
    enviado = documentos.receber_documento(
        conexao,
        usuario_id=dono.id,
        operacao_id=operacao.id,
        nome_original=f"{nome}.pdf",
        conteudo=gerar.pdf(nome),
    ).documento
    return dono, operacao, enviado


def _abre(conexao, dono, operacao, documento):
    return documentos.abrir_documento(
        conexao,
        usuario_id=dono.id,
        operacao_id=operacao.id,
        documento_id=documento.id,
    )


def _salas(conexao):
    return [_sala(conexao, nome) for nome in ("ana", "beto", "carla")]


def test_depois_da_troca_toda_operacao_abre_e_a_antiga_nao_e_mais_usada(
    conexao, mestras, monkeypatch
):
    salas = _salas(conexao)
    assert troca_de_chave.uso_por_versao(conexao) == {1: 3}
    _acrescentar_v2(monkeypatch, mestras)

    resultado = troca_de_chave.reembrulhar(conexao)

    assert (resultado.versao_nova, resultado.reembrulhadas) == (2, 3)
    assert troca_de_chave.uso_por_versao(conexao) == {2: 3}
    troca_de_chave.pode_retirar(conexao, 1)
    # sem a v1 na variável, tudo continua abrindo: a antiga não abre mais nada
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, V2)
    for dono, operacao, documento in salas:
        assert _abre(conexao, dono, operacao, documento) is not None


def test_rodar_duas_vezes_da_o_mesmo_resultado(conexao, mestras, monkeypatch):
    _salas(conexao)
    _acrescentar_v2(monkeypatch, mestras)
    troca_de_chave.reembrulhar(conexao)
    antes = conexao.execute(sa.select(operacoes.c.chave_cifrada)).all()

    segunda = troca_de_chave.reembrulhar(conexao)

    assert (segunda.reembrulhadas, segunda.ja_na_versao_nova) == (0, 3)
    assert conexao.execute(sa.select(operacoes.c.chave_cifrada)).all() == antes


def test_versao_em_uso_nao_pode_sair_e_a_mais_nova_tambem_nao(
    conexao, mestras, monkeypatch
):
    _salas(conexao)
    _acrescentar_v2(monkeypatch, mestras)
    with pytest.raises(troca_de_chave.VersaoEmUsoError, match="3 operação"):
        troca_de_chave.pode_retirar(conexao, 1)
    with pytest.raises(troca_de_chave.VersaoEmUsoError):
        troca_de_chave.pode_retirar(conexao, 2)


def test_sem_a_versao_antiga_na_variavel_nada_e_gravado(conexao, mestras, monkeypatch):
    _salas(conexao)
    antes = conexao.execute(sa.select(operacoes.c.chave_cifrada)).all()
    # só a v2 na variável: a v1 que embrulha as operações sumiu cedo demais
    monkeypatch.setenv(cofre.VARIAVEL_DA_CHAVE_MESTRA, V2)
    with pytest.raises(cofre.ChaveDaSalaAusenteError):
        troca_de_chave.reembrulhar(conexao)
    assert conexao.execute(sa.select(operacoes.c.chave_cifrada)).all() == antes
    assert troca_de_chave.uso_por_versao(conexao) == {1: 3}


def test_operacao_sem_chave_fica_como_esta(conexao, mestras, monkeypatch):
    dono = entrar(conexao, "z", "z@exemplo.com", "z")[0]
    sala.criar_operacao(conexao, usuario_id=dono.id, tipo="ma", nome="vazia", hoje=HOJE)
    _acrescentar_v2(monkeypatch, mestras)
    resultado = troca_de_chave.reembrulhar(conexao)
    assert (resultado.reembrulhadas, resultado.ja_na_versao_nova) == (0, 0)
    assert troca_de_chave.uso_por_versao(conexao) == {}


def test_operacao_nova_depois_da_troca_ja_usa_a_versao_nova(
    conexao, mestras, monkeypatch
):
    _salas(conexao)
    _acrescentar_v2(monkeypatch, mestras)
    troca_de_chave.reembrulhar(conexao)
    _sala(conexao, "dora")
    assert troca_de_chave.uso_por_versao(conexao) == {2: 4}


def test_o_script_reembrulha_e_so_libera_a_versao_sem_uso(
    tmp_path, mestras, monkeypatch
):
    from scripts import trocar_chave_da_sala as script
    from src.configuracao import VARIAVEL_DO_BANCO

    url = f"sqlite:///{tmp_path / 'sala.db'}"
    monkeypatch.setenv(VARIAVEL_DO_BANCO, url)
    motor = sa.create_engine(url)
    metadata.create_all(motor)
    with motor.begin() as conexao:
        _sala(conexao, "ana")
    motor.dispose()
    _acrescentar_v2(monkeypatch, mestras)

    assert script.main(["pode-retirar", "1"]) == 1  # ainda em uso
    assert script.main(["situacao"]) == 0
    assert script.main(["reembrulhar"]) == 0
    assert script.main(["pode-retirar", "1"]) == 0
    assert script.main(["pode-retirar", "2"]) == 1  # a mais nova nunca sai
