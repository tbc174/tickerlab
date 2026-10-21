"""O expurgo diário da sala (B-20, PR 6): nada vencido sobra e nada dentro do prazo some.

Banco em SQLite, disco numa pasta temporária e a chave-mestra gerada no teste. O risco que estes
testes travam: dado de terceiros ficar além do prazo prometido (ou, ao contrário, sumir antes).
"""

import json
import logging
import os
import uuid
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from scripts import expurgar_salas
from src.banco import sala
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.modelo import documentos_da_sala, metadata, operacoes
from src.banco.usuarios import entrar
from src.sala import cofre, documentos, expurgo, guarda
from tests import ajudantes_da_sala as gerar

HOJE = date(2026, 10, 21)
NOME_SENSIVEL = "Laudo da Fulana de Tal.pdf"
UM_DIA = 86_400


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


@pytest.fixture
def ana(conexao):
    return entrar(conexao, "ana", "ana@exemplo.com", "Ana")[0]


def _operacao_com_documento(conexao, dono, *, retencao_ate, nome="Alfa"):
    operacao = sala.criar_operacao(
        conexao, usuario_id=dono.id, tipo="ma", nome=nome, hoje=HOJE
    )
    conexao.execute(
        sa.update(operacoes)
        .where(operacoes.c.id == operacao.id)
        .values(retencao_ate=retencao_ate)
    )
    documentos.receber_documento(
        conexao,
        usuario_id=dono.id,
        operacao_id=operacao.id,
        nome_original=NOME_SENSIVEL,
        conteudo=gerar.pdf(f"Balanço da {nome}"),
    )
    return operacao


def _arquivos_da_operacao(raiz, operacao):
    return list(guarda.pasta_da_operacao(raiz, operacao.id).glob("*.bin"))


def _envelhecer(pasta, dias):
    antiga = pasta.stat().st_mtime - dias * UM_DIA
    os.utime(pasta, (antiga, antiga))


def test_apaga_a_vencida_inteira_e_deixa_a_que_esta_no_prazo(conexao, ana, raiz):
    vencida = _operacao_com_documento(
        conexao, ana, retencao_ate=HOJE - timedelta(days=1), nome="Vencida"
    )
    no_dia = _operacao_com_documento(conexao, ana, retencao_ate=HOJE, nome="NoDia")
    futura = _operacao_com_documento(
        conexao, ana, retencao_ate=HOJE + timedelta(days=30), nome="Futura"
    )

    resultado = expurgo.expurgar(conexao, hoje=HOJE, raiz=raiz)

    assert resultado.operacoes_vencidas == 1
    ficam = {linha.id for linha in conexao.execute(sa.select(operacoes.c.id))}
    assert ficam == {no_dia.id, futura.id}
    assert not guarda.pasta_da_operacao(raiz, vencida.id).exists()
    assert (
        len(_arquivos_da_operacao(raiz, no_dia)) == 1
    )  # só o original: o texto sai depois, na leitura
    assert len(_arquivos_da_operacao(raiz, futura)) == 1


def test_leva_junto_os_documentos_da_operacao_vencida(conexao, ana, raiz):
    _operacao_com_documento(conexao, ana, retencao_ate=HOJE - timedelta(days=5))
    expurgo.expurgar(conexao, hoje=HOJE, raiz=raiz)
    assert conexao.execute(sa.select(documentos_da_sala.c.id)).all() == []


def test_auditoria_so_com_ids(conexao, ana, raiz):
    vencida = _operacao_com_documento(
        conexao, ana, retencao_ate=HOJE - timedelta(days=1), nome="Segredo da Alfa"
    )
    expurgo.expurgar(conexao, hoje=HOJE, raiz=raiz)
    expiradas = conexao.execute(
        sa.select(tabela_da_auditoria).where(
            tabela_da_auditoria.c.acao == "operacao_expirada"
        )
    ).all()
    assert [(a.alvo_id, a.ator_id, a.detalhes) for a in expiradas] == [
        (vencida.id, ana.id, {})
    ]
    tudo = json.dumps(
        [str(c) for a in conexao.execute(sa.select(tabela_da_auditoria)) for c in a]
    )
    assert "Segredo" not in tudo and "Laudo" not in tudo


def test_pasta_orfa_velha_e_apagada_e_a_recente_fica(conexao, raiz):
    velha, recente = uuid.uuid4(), uuid.uuid4()
    for operacao_id in (velha, recente):
        guarda.gravar(guarda.pasta_da_operacao(raiz, operacao_id) / "x.bin", b"dado")
    _envelhecer(guarda.pasta_da_operacao(raiz, velha), 2)

    resultado = expurgo.expurgar(conexao, hoje=HOJE, raiz=raiz)

    assert resultado.pastas_orfas == 1
    assert not guarda.pasta_da_operacao(raiz, velha).exists()
    assert guarda.pasta_da_operacao(raiz, recente).exists()


def test_a_varredura_nao_mexe_no_que_nao_e_pasta_de_operacao(conexao, raiz):
    raiz.mkdir()
    (raiz / "LEIA-ME.txt").write_text("fica")
    (raiz / "pasta-qualquer").mkdir()
    expurgo.expurgar(conexao, hoje=HOJE, raiz=raiz)
    assert (raiz / "LEIA-ME.txt").exists() and (raiz / "pasta-qualquer").exists()


def test_a_pasta_de_operacao_viva_nao_e_orfa_mesmo_velha(conexao, ana, raiz):
    viva = _operacao_com_documento(conexao, ana, retencao_ate=HOJE + timedelta(days=9))
    _envelhecer(guarda.pasta_da_operacao(raiz, viva.id), 30)
    expurgo.expurgar(conexao, hoje=HOJE, raiz=raiz)
    assert len(_arquivos_da_operacao(raiz, viva)) == 1


def test_falha_no_disco_conta_mas_a_chave_ja_foi(conexao, ana, raiz, monkeypatch):
    _operacao_com_documento(conexao, ana, retencao_ate=HOJE - timedelta(days=1))

    def falhar(*_):
        raise PermissionError("sem permissão")

    monkeypatch.setattr(guarda, "apagar_operacao", falhar)
    resultado = expurgo.expurgar(conexao, hoje=HOJE, raiz=raiz)
    assert resultado.operacoes_vencidas == 1 and resultado.falhas_no_disco >= 1
    # a linha (e com ela a chave) já saiu: o arquivo que sobrou não abre mais
    assert conexao.execute(sa.select(operacoes.c.id)).all() == []


def test_o_script_roda_no_banco_da_configuracao(banco, raiz, caplog):
    with banco.begin() as conexao:
        dono = entrar(conexao, "bia", "bia@exemplo.com", "Bia")[0]
        vencida = sala.criar_operacao(
            conexao, usuario_id=dono.id, tipo="ma", nome="Sigilo da Beta", hoje=HOJE
        )
        conexao.execute(sa.update(operacoes).values(retencao_ate=date(2020, 1, 1)))
        guarda.gravar(guarda.pasta_da_operacao(raiz, vencida.id) / "x.bin", b"dado")
    with caplog.at_level(logging.INFO, logger="tickerlab.expurgo"):
        assert expurgar_salas.main() == 0
    with banco.connect() as conexao:
        assert conexao.execute(sa.select(operacoes.c.id)).all() == []
    assert not guarda.pasta_da_operacao(raiz, vencida.id).exists()
    assert "1 operações vencidas" in caplog.text
    assert "Sigilo" not in caplog.text and "bia@" not in caplog.text


def test_o_script_sai_com_erro_se_o_disco_falhar(banco, monkeypatch):
    with banco.begin() as conexao:
        dono = entrar(conexao, "bia", "bia@exemplo.com", "Bia")[0]
        sala.criar_operacao(conexao, usuario_id=dono.id, tipo="ma", nome="B", hoje=HOJE)
        conexao.execute(sa.update(operacoes).values(retencao_ate=date(2020, 1, 1)))

    def falhar(*_):
        raise PermissionError

    monkeypatch.setattr(guarda, "apagar_operacao", falhar)
    assert expurgar_salas.main() == 1
