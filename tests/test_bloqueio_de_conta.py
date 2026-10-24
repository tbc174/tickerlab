"""Bloquear uma conta só durante um incidente (linha 306 da fila; desenho aprovado pelo Tiago em 24/10).

O bloqueio encerra as sessões na hora, recusa o login novo por qualquer caminho (antes de juntar uma
forma de entrar nova à conta), tira o poder de administrador e para os links públicos da conta. Não
apaga nada: desbloquear devolve o login e os dados (as sessões encerradas não voltam). Exportar e
apagar a conta continuam funcionando (LGPD, pelo canal do encarregado). A auditoria leva só ids.
"""

import uuid

import pytest
import sqlalchemy as sa

from src import administracao as adm
from src import auditoria
from src.banco import compartilhamentos as links
from src.banco import dados_do_usuario as repo
from src.banco import sessoes
from src.banco.modelo import identidades, metadata, usuarios
from src.banco.usuarios import (
    TEXTO_DA_CONTA_BLOQUEADA,
    ContaBloqueadaError,
    IdentidadeDoProvedor,
    buscar_por_id,
    entrar,
    entrar_por_identidade,
)
from src.conformidade import apagar_conta, exportar_meus_dados
from tests.test_banco_compartilhamentos import AGORA, _ficha, _pdf

CHEFE = "chefe@exemplo.com"
VICE = "vice@exemplo.com"


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


def _admin(conexao, sub, email):
    return entrar(
        conexao, sub, email, emails_de_admin=(CHEFE, VICE), email_confirmado=True
    )[0]


@pytest.fixture
def chefe(conexao):
    return _admin(conexao, "chefe", CHEFE)


@pytest.fixture
def ana(conexao):
    return entrar(
        conexao, "ana", "ana@exemplo.com", "Ana Souza", email_confirmado=True
    )[0]


@pytest.fixture
def bia(conexao):
    return entrar(conexao, "bia", "bia@exemplo.com", "Bia", email_confirmado=True)[0]


def _bloquear(conexao, chefe, alvo, motivo="acesso_de_terceiro"):
    return adm.bloquear_conta(conexao, chefe.id, alvo.id, motivo)


# --- o que o bloqueio faz ----------------------------------------------------------------


def test_bloquear_encerra_na_hora_as_sessoes_que_ja_existiam(conexao, chefe, ana):
    do_pc = sessoes.abrir(conexao, ana.id, "google")
    do_celular = sessoes.abrir(conexao, ana.id, "email")
    assert sessoes.conta_da_sessao(conexao, do_pc) is not None

    assert _bloquear(conexao, chefe, ana) == 2

    assert sessoes.conta_da_sessao(conexao, do_pc) is None
    assert sessoes.conta_da_sessao(conexao, do_celular) is None


def test_sessao_aberta_depois_do_bloqueio_nao_vale(conexao, chefe, ana):
    """Corrida: um login que já tinha passado da conferência abre a sessão depois do bloqueio."""
    _bloquear(conexao, chefe, ana)
    atrasada = sessoes.abrir(conexao, ana.id, "google")
    assert sessoes.conta_da_sessao(conexao, atrasada) is None


def test_conta_antiga_bloqueada_nao_entra_nem_ganha_a_identidade(conexao, chefe, ana):
    """Conta da versão clássica achada só pelo `google_sub` (sem linha em `identidades`)."""
    conexao.execute(sa.delete(identidades).where(identidades.c.usuario_id == ana.id))
    _bloquear(conexao, chefe, ana)
    with pytest.raises(ContaBloqueadaError):
        entrar(conexao, "ana", "ana@exemplo.com", "Ana Souza", email_confirmado=True)
    assert not conexao.execute(
        sa.select(identidades).where(identidades.c.usuario_id == ana.id)
    ).first()


def test_conta_bloqueada_nao_entra_pelo_google(conexao, chefe, ana):
    _bloquear(conexao, chefe, ana)
    with pytest.raises(ContaBloqueadaError) as erro:
        entrar(conexao, "ana", "ana@exemplo.com", "Ana Souza", email_confirmado=True)
    assert str(erro.value) == TEXTO_DA_CONTA_BLOQUEADA


def test_conta_bloqueada_nao_entra_pelo_codigo_nem_junta_forma_de_entrar_nova(
    conexao, chefe, ana
):
    """Entrar por outro provedor com o mesmo e-mail juntaria a forma nova à conta: recusa antes."""
    _bloquear(conexao, chefe, ana)
    antes = conexao.execute(
        sa.select(sa.func.count()).select_from(identidades)
    ).scalar()
    pelo_email = IdentidadeDoProvedor(
        "email", "ana@exemplo.com", "ana@exemplo.com", email_confirmado=True
    )
    with pytest.raises(ContaBloqueadaError):
        entrar_por_identidade(conexao, pelo_email)
    depois = conexao.execute(
        sa.select(sa.func.count()).select_from(identidades)
    ).scalar()
    assert depois == antes
    assert (
        conexao.execute(sa.select(sa.func.count()).select_from(usuarios)).scalar() == 2
    )


def test_texto_da_conta_bloqueada_e_o_aprovado():
    assert TEXTO_DA_CONTA_BLOQUEADA == (
        "Esta conta está bloqueada. Se ela é sua, escreva para privacidade@tickerlab.com.br: "
        "por lá você também pode pedir uma cópia dos seus dados ou a exclusão da conta."
    )


def test_bloquear_uma_conta_nao_toca_a_outra(conexao, chefe, ana, bia):
    da_bia = sessoes.abrir(conexao, bia.id, "google")
    _bloquear(conexao, chefe, ana)
    assert sessoes.conta_da_sessao(conexao, da_bia).id == bia.id
    assert entrar(conexao, "bia", "bia@exemplo.com", "Bia")[0].id == bia.id
    assert buscar_por_id(conexao, bia.id).bloqueada_em is None


def test_bloquear_nao_apaga_nada_e_desbloquear_devolve_o_login(conexao, chefe, ana):
    repo.salvar_favoritos(conexao, ana.id, ["PETR4.SA"])
    antiga = sessoes.abrir(conexao, ana.id, "google")
    _bloquear(conexao, chefe, ana)
    assert repo.listar_favoritos(conexao, ana.id) == ["PETR4.SA"]

    adm.desbloquear_conta(conexao, chefe.id, ana.id)

    de_volta = entrar(conexao, "ana", "ana@exemplo.com", "Ana Souza")[0]
    assert de_volta.id == ana.id and de_volta.bloqueada_em is None
    assert repo.listar_favoritos(conexao, ana.id) == ["PETR4.SA"]
    # a sessão encerrada não ressuscita (num roubo, seria a do outro lado)
    assert sessoes.conta_da_sessao(conexao, antiga) is None


def test_a_conta_lida_diz_que_esta_bloqueada_e_por_que(conexao, chefe, ana):
    _bloquear(conexao, chefe, ana, "abuso")
    lida = buscar_por_id(conexao, ana.id)
    assert lida.bloqueada_em is not None
    assert lida.motivo_do_bloqueio == "abuso"


# --- administradores ---------------------------------------------------------------------


def test_admin_bloqueado_nao_administra_nem_volta_pelo_login(conexao, chefe):
    vice = _admin(conexao, "vice", VICE)
    _bloquear(conexao, chefe, vice)
    with pytest.raises(adm.PermissaoNegadaError):
        adm.exigir_admin(conexao, vice.id)
    with pytest.raises(adm.PermissaoNegadaError):
        adm.listar_usuarios(conexao, vice.id)
    # o e-mail ainda está na lista do servidor: o login daria o papel de novo, mas não entra
    with pytest.raises(ContaBloqueadaError):
        _admin(conexao, "vice", VICE)


def test_so_administrador_bloqueia(conexao, ana, bia):
    with pytest.raises(adm.PermissaoNegadaError):
        adm.bloquear_conta(conexao, ana.id, bia.id, "abuso")
    with pytest.raises(adm.PermissaoNegadaError):
        adm.desbloquear_conta(conexao, ana.id, bia.id)
    assert buscar_por_id(conexao, bia.id).bloqueada_em is None


def test_ninguem_bloqueia_a_si_mesmo(conexao, chefe):
    """Assim o serviço fica sempre com um administrador desbloqueado: quem bloqueia é um."""
    with pytest.raises(adm.OperacaoInvalidaError):
        _bloquear(conexao, chefe, chefe)
    adm.exigir_admin(conexao, chefe.id)


def test_motivo_desconhecido_e_recusado(conexao, chefe, ana):
    with pytest.raises(adm.OperacaoInvalidaError):
        _bloquear(conexao, chefe, ana, "porque_sim")
    assert buscar_por_id(conexao, ana.id).bloqueada_em is None


def test_bloquear_de_novo_ou_desbloquear_quem_nao_esta_bloqueado_avisa(
    conexao, chefe, ana
):
    with pytest.raises(adm.OperacaoInvalidaError):
        adm.desbloquear_conta(conexao, chefe.id, ana.id)
    _bloquear(conexao, chefe, ana)
    with pytest.raises(adm.OperacaoInvalidaError):
        _bloquear(conexao, chefe, ana, "abuso")
    assert buscar_por_id(conexao, ana.id).motivo_do_bloqueio == "acesso_de_terceiro"


def test_conta_que_nao_existe_nao_se_bloqueia(conexao, chefe):
    with pytest.raises(adm.OperacaoInvalidaError):
        adm.bloquear_conta(conexao, chefe.id, uuid.uuid4(), "abuso")


def test_o_banco_recusa_bloqueio_sem_motivo_ou_com_motivo_desconhecido(conexao, ana):
    for valores in (
        {"bloqueada_em": AGORA, "motivo_do_bloqueio": None},
        {"bloqueada_em": None, "motivo_do_bloqueio": "abuso"},
        {"bloqueada_em": AGORA, "motivo_do_bloqueio": "porque_sim"},
    ):
        with pytest.raises(sa.exc.IntegrityError), conexao.begin_nested():
            conexao.execute(
                sa.update(usuarios).where(usuarios.c.id == ana.id).values(**valores)
            )


# --- auditoria ---------------------------------------------------------------------------


def test_auditoria_do_bloqueio_leva_so_ids(conexao, chefe, ana):
    sessoes.abrir(conexao, ana.id, "google")
    _bloquear(conexao, chefe, ana, "abuso")
    adm.desbloquear_conta(conexao, chefe.id, ana.id)
    bloqueio, desbloqueio = sorted(
        (
            r
            for r in auditoria.listar_recentes(conexao)
            if r.acao
            in (auditoria.ACAO_CONTA_BLOQUEADA, auditoria.ACAO_CONTA_DESBLOQUEADA)
        ),
        key=lambda r: r.acao,
    )
    assert bloqueio.acao == auditoria.ACAO_CONTA_BLOQUEADA
    assert (bloqueio.ator_id, bloqueio.alvo_id) == (chefe.id, ana.id)
    assert bloqueio.detalhes == {"motivo": "abuso", "sessoes_encerradas": 1}
    assert (desbloqueio.ator_id, desbloqueio.alvo_id) == (chefe.id, ana.id)
    assert desbloqueio.detalhes == {"motivo": "abuso"}
    for registro in (bloqueio, desbloqueio):
        assert "@" not in str(registro.detalhes)
        assert "Ana" not in str(registro.detalhes)


# --- LGPD --------------------------------------------------------------------------------


def test_exportar_e_apagar_funcionam_com_a_conta_bloqueada(conexao, chefe, ana, bia):
    repo.salvar_favoritos(conexao, ana.id, ["PETR4.SA"])
    _bloquear(conexao, chefe, ana)
    exportados = exportar_meus_dados(conexao, ana.id)
    assert "PETR4.SA" in str(exportados)
    assert exportados["perfil"]["bloqueio"]["motivo"] == "acesso_de_terceiro"
    assert exportados["perfil"]["bloqueio"]["em"] is not None
    assert apagar_conta(conexao, ana.id)
    assert buscar_por_id(conexao, ana.id) is None
    assert buscar_por_id(conexao, bia.id) is not None


# --- links públicos ----------------------------------------------------------------------


def test_links_publicos_param_enquanto_bloqueada_e_voltam_no_desbloqueio(
    conexao, chefe, ana, bia
):
    da_ana = _ficha(conexao, ana.id)
    da_bia = _ficha(conexao, bia.id)
    assert links.abrir_link(conexao, da_ana, agora=AGORA) is not None

    _bloquear(conexao, chefe, ana)
    assert links.abrir_link(conexao, da_ana, agora=AGORA) is None
    assert links.abrir_link(conexao, da_bia, agora=AGORA) is not None

    adm.desbloquear_conta(conexao, chefe.id, ana.id)
    assert links.abrir_link(conexao, da_ana, agora=AGORA) is not None


def test_pdf_do_link_para_enquanto_bloqueada(conexao, chefe, ana):
    relatorio = _pdf(conexao, ana.id)
    codigo = links.criar_link_do_pdf(conexao, ana.id, "pro", relatorio, 30, agora=AGORA)
    assert links.pdf_do_link(conexao, codigo, agora=AGORA) is not None
    _bloquear(conexao, chefe, ana)
    assert links.pdf_do_link(conexao, codigo, agora=AGORA) is None
