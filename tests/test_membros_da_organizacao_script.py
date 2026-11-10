"""Vincular e desvincular membro pelo script de administração (ADR 0128, Emenda 1; linha 808, PR 1).

Só administrador vincula; a saída, o erro e a auditoria levam o id da conta, nunca o e-mail. O
vínculo sozinho não mostra pessoa: falta o direito `pessoa_na_tela`. Todo dado aqui é fictício.
"""

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from scripts import chaves_da_api as script
from src.banco import membros_da_organizacao as mb
from src.banco.modelo import auditoria
from src.banco.usuarios import entrar

ADMIN = "admin-808@exemplo.com"
MEMBRO = "analista-808@exemplo.com"
HOJE = datetime.now(UTC).date()


@pytest.fixture
def admin(banco, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ADMINS", ADMIN)
    with banco.begin() as conexao:
        return entrar(
            conexao,
            "g-admin-808",
            ADMIN,
            emails_de_admin=(ADMIN,),
            email_confirmado=True,
        )[0]


@pytest.fixture
def analista(banco):
    with banco.begin() as conexao:
        return entrar(conexao, "g-analista-808", MEMBRO, "Analista Exemplo")[0]


def _rodar(capsys, *argumentos, admin=ADMIN):
    codigo = script.main(["--admin", admin, *argumentos])
    saida = capsys.readouterr()
    return codigo, saida.out, saida.err


def _id_na_saida(saida):
    for palavra in saida.split():
        try:
            return uuid.UUID(palavra)
        except ValueError:
            continue
    raise AssertionError(f"nenhum id na saída: {saida!r}")


@pytest.fixture
def casa(capsys, admin):
    codigo, saida, _ = _rodar(capsys, "criar-organizacao", "--nome", "Casa Exemplo")
    assert codigo == 0
    return _id_na_saida(saida)


def _vincular(capsys, casa, email=MEMBRO, **outros):
    return _rodar(capsys, "vincular-membro", str(casa), "--email", email, **outros)


def _desvincular(capsys, casa):
    return _rodar(capsys, "desvincular-membro", str(casa), "--email", MEMBRO)


def _ve(banco, conta) -> bool:
    with banco.connect() as conexao:
        return mb.pode_ver_pessoa(conexao, conta.id, HOJE)


def test_vincular_sozinho_nao_mostra_e_com_o_direito_mostra(
    banco, capsys, casa, analista
):
    codigo, saida, erro = _vincular(capsys, casa)
    assert codigo == 0, erro
    assert _id_na_saida(saida) == analista.id
    assert not _ve(banco, analista)

    codigo, saida, erro = _rodar(
        capsys,
        "conceder-direito",
        str(casa),
        "--conjunto",
        mb.CONJUNTO_DE_PESSOA_NA_TELA,
        "--finalidade",
        mb.FINALIDADE_DA_TELA,
        "--desde",
        HOJE.isoformat(),
    )
    assert codigo == 0, erro
    assert _ve(banco, analista)

    codigo, _, erro = _rodar(
        capsys, "suspender-direito", str(casa), str(_id_na_saida(saida))
    )
    assert codigo == 0, erro
    assert not _ve(banco, analista)


def test_a_saida_e_a_auditoria_nao_levam_o_email(banco, capsys, casa, analista):
    codigo, saida, erro = _vincular(capsys, casa)
    assert codigo == 0
    _, visao, _ = _rodar(capsys, "ver", str(casa))
    assert "Membros (contas com login): 1" in visao and str(analista.id) in visao
    with banco.connect() as conexao:
        registros = conexao.execute(sa.select(auditoria.c.detalhes)).scalars().all()
    for texto in (saida, erro, visao, str(registros)):
        assert MEMBRO not in texto and "Analista" not in texto


def test_desvincular_e_de_novo_nada_muda(capsys, casa, analista):
    _vincular(capsys, casa)
    codigo, saida, _ = _desvincular(capsys, casa)
    assert codigo == 0 and _id_na_saida(saida) == analista.id
    codigo, _, erro = _desvincular(capsys, casa)
    assert codigo == 1 and "Nada mudou" in erro


def test_email_sem_conta_e_vinculo_repetido_dao_erro_sem_eco(capsys, casa, analista):
    codigo, saida, erro = _vincular(capsys, casa, email="ninguem-808@exemplo.com")
    assert codigo == 1 and "ninguem-808" not in saida + erro
    _vincular(capsys, casa)
    codigo, saida, erro = _vincular(capsys, casa)
    assert codigo == 1 and MEMBRO not in saida + erro


def test_quem_nao_e_admin_nao_vincula(banco, capsys, casa, analista):
    codigo, _, erro = _vincular(capsys, casa, admin=MEMBRO)
    assert codigo == 2 and "Recusado" in erro
    with banco.connect() as conexao:
        assert mb.listar_membros(conexao, casa) == []
