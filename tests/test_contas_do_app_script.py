"""Script do admin para bloquear uma conta do app no incidente (linha 306; plano de incidente, passo 4).

Só quem está em `TICKERLAB_ADMINS` **e** é administrador no banco usa o script (a mesma conferência do
`chaves_da_api.py`). A conta vai pelo id; a saída não mostra e-mail nem nome.
"""

import uuid

import pytest

from scripts import contas_do_app as script
from src.banco import sessoes
from src.banco.usuarios import buscar_por_id, entrar

ADMIN = "admin-contas@exemplo.com"


@pytest.fixture
def admin(banco, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ADMINS", ADMIN)
    with banco.begin() as conexao:
        usuario = entrar(
            conexao,
            "g-admin-contas",
            ADMIN,
            emails_de_admin=(ADMIN,),
            email_confirmado=True,
        )[0]
    assert usuario.e_admin
    return usuario


@pytest.fixture
def ana(banco):
    with banco.begin() as conexao:
        usuario = entrar(conexao, "g-ana", "ana@exemplo.com", "Ana Souza")[0]
        sessoes.abrir(conexao, usuario.id, "google")
    return usuario


def _rodar(capsys, *argumentos, admin=ADMIN):
    prefixo = ["--admin", admin] if admin else []
    codigo = script.main([*prefixo, *argumentos])
    saida = capsys.readouterr()
    return codigo, saida.out, saida.err


def _conta(banco, usuario_id):
    with banco.connect() as conexao:
        return buscar_por_id(conexao, usuario_id)


def test_bloquear_e_desbloquear_pelo_id(banco, admin, ana, capsys):
    codigo, saida, erro = _rodar(
        capsys, "bloquear-conta", str(ana.id), "--motivo", "acesso_de_terceiro"
    )
    assert codigo == script.SAIDA_OK, erro
    assert str(ana.id) in saida and "1 sessão encerrada" in saida
    assert _conta(banco, ana.id).motivo_do_bloqueio == "acesso_de_terceiro"

    codigo, saida, _ = _rodar(capsys, "ver-conta", str(ana.id))
    assert codigo == script.SAIDA_OK
    assert "bloqueada desde" in saida and "acesso_de_terceiro" in saida

    codigo, saida, erro = _rodar(capsys, "desbloquear-conta", str(ana.id))
    assert codigo == script.SAIDA_OK, erro
    assert _conta(banco, ana.id).bloqueada_em is None
    codigo, saida, _ = _rodar(capsys, "ver-conta", str(ana.id))
    assert "não está bloqueada" in saida


def test_a_saida_nao_mostra_email_nem_nome(banco, admin, ana, capsys):
    for argumentos in (
        ("bloquear-conta", str(ana.id), "--motivo", "abuso"),
        ("ver-conta", str(ana.id)),
        ("desbloquear-conta", str(ana.id)),
    ):
        _, saida, erro = _rodar(capsys, *argumentos)
        assert "@" not in saida + erro and "Ana" not in saida + erro


def test_bloquear_de_novo_sai_com_erro_e_nao_muda_o_motivo(banco, admin, ana, capsys):
    _rodar(capsys, "bloquear-conta", str(ana.id), "--motivo", "abuso")
    codigo, _, erro = _rodar(
        capsys, "bloquear-conta", str(ana.id), "--motivo", "incidente"
    )
    assert codigo == script.SAIDA_ERRO and "já está bloqueada" in erro
    assert _conta(banco, ana.id).motivo_do_bloqueio == "abuso"


def test_conta_que_nao_existe_sai_com_erro(banco, admin, capsys):
    codigo, _, erro = _rodar(
        capsys, "bloquear-conta", str(uuid.uuid4()), "--motivo", "abuso"
    )
    assert codigo == script.SAIDA_ERRO and erro


def test_quem_nao_esta_na_lista_e_recusado(banco, admin, ana, capsys):
    codigo, _, erro = _rodar(
        capsys,
        "bloquear-conta",
        str(ana.id),
        "--motivo",
        "abuso",
        admin="ana@exemplo.com",
    )
    assert codigo == script.SAIDA_RECUSA and erro.startswith("Recusado")
    assert _conta(banco, ana.id).bloqueada_em is None


def test_motivo_fora_da_lista_e_recusado_pelos_argumentos(banco, admin, ana, capsys):
    with pytest.raises(SystemExit) as saida:
        _rodar(capsys, "bloquear-conta", str(ana.id), "--motivo", "porque_sim")
    assert saida.value.code == script.SAIDA_RECUSA
    assert _conta(banco, ana.id).bloqueada_em is None


def test_o_admin_nao_bloqueia_a_si_mesmo(banco, admin, capsys):
    codigo, _, erro = _rodar(
        capsys, "bloquear-conta", str(admin.id), "--motivo", "incidente"
    )
    assert codigo == script.SAIDA_ERRO and erro
    assert _conta(banco, admin.id).bloqueada_em is None
