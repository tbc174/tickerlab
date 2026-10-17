"""Painel de administração: só administradores, mudanças auditadas, último administrador protegido."""

import uuid

import pytest
import sqlalchemy as sa

from src import administracao as adm
from src import auditoria
from src.banco import dados_do_usuario as repo
from src.banco.modelo import assinaturas, eventos_stripe, metadata
from src.banco.usuarios import buscar_por_id, entrar


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
    )[0]


@pytest.fixture
def ana(conexao):
    return entrar(conexao, "ana", "ana@exemplo.com", "Ana Souza")[0]


@pytest.fixture
def bia(conexao):
    return entrar(conexao, "bia", "bia@exemplo.com", "Bia")[0]


# --- permissão ---
def test_usuario_comum_nao_faz_nada_de_administrador(conexao, ana, bia):
    for chamada in (
        lambda: adm.resumo_geral(conexao, ana.id),
        lambda: adm.listar_usuarios(conexao, ana.id),
        lambda: adm.alterar_plano(conexao, ana.id, bia.id, "pro"),
        lambda: adm.alterar_papel(conexao, ana.id, bia.id, "admin"),
        lambda: adm.eventos_recentes_do_stripe(conexao, ana.id),
        lambda: adm.auditoria_recente(conexao, ana.id),
    ):
        with pytest.raises(adm.PermissaoNegadaError):
            chamada()
    assert buscar_por_id(conexao, bia.id).plano == "gratuito"


def test_ator_inexistente_ou_nulo_nao_passa(conexao):
    for ator in (None, uuid.uuid4()):
        with pytest.raises(adm.PermissaoNegadaError):
            adm.resumo_geral(conexao, ator)


def test_a_permissao_vem_do_banco_e_nao_do_que_a_tela_diz(conexao, chefe):
    """Se o administrador perde o papel, o próximo pedido dele já falha."""
    outro = entrar(
        conexao, "outro", "outro@exemplo.com", emails_de_admin=("outro@exemplo.com",)
    )[0]
    adm.alterar_papel(conexao, chefe.id, outro.id, "usuario")
    with pytest.raises(adm.PermissaoNegadaError):
        adm.listar_usuarios(conexao, outro.id)


# --- números e lista ---
def test_resumo_conta_usuarios_planos_e_simulacoes(conexao, chefe, ana, bia):
    adm.alterar_plano(conexao, chefe.id, ana.id, "pro")
    repo.salvar_simulacao(conexao, ana.id, "backtest", "s", {}, {})
    conexao.execute(
        sa.insert(assinaturas).values(
            usuario_id=ana.id,
            stripe_customer_id="cus_1",
            status="active",
            cancela_no_fim=False,
            evento_em=1,
        )
    )
    conexao.execute(sa.insert(eventos_stripe).values(id="evt_1", tipo="x"))
    resumo = adm.resumo_geral(conexao, chefe.id)
    assert resumo["usuarios"] == 3 and resumo["pro"] == 1 and resumo["gratuito"] == 2
    assert resumo["administradores"] == 1 and resumo["simulacoes"] == 1
    assert resumo["assinaturas_por_status"] == {"active": 1}
    assert resumo["eventos_do_stripe"] == 1
    assert resumo["novos_na_semana"] == 3 and resumo["ativos_na_semana"] == 3


def test_lista_de_usuarios_com_assinatura_e_simulacoes(conexao, chefe, ana):
    repo.salvar_simulacao(conexao, ana.id, "backtest", "s1", {}, {})
    repo.salvar_simulacao(conexao, ana.id, "carteira", "s2", {}, {})
    conexao.execute(
        sa.insert(assinaturas).values(
            usuario_id=ana.id,
            stripe_customer_id="cus_1",
            status="past_due",
            cancela_no_fim=False,
            evento_em=1,
        )
    )
    linhas = {l.email: l for l in adm.listar_usuarios(conexao, chefe.id)}
    assert set(linhas) == {"chefe@exemplo.com", "ana@exemplo.com"}
    assert linhas["ana@exemplo.com"].simulacoes == 2
    assert linhas["ana@exemplo.com"].status_da_assinatura == "past_due"
    assert linhas["chefe@exemplo.com"].status_da_assinatura is None
    assert linhas["chefe@exemplo.com"].papel == "admin"


def test_busca_por_email_ou_nome_sem_distinguir_maiusculas(conexao, chefe, ana, bia):
    assert [l.email for l in adm.listar_usuarios(conexao, chefe.id, "SOUZA")] == [
        "ana@exemplo.com"
    ]
    assert [l.email for l in adm.listar_usuarios(conexao, chefe.id, "bia@")] == [
        "bia@exemplo.com"
    ]
    assert adm.listar_usuarios(conexao, chefe.id, "ninguem") == []


def test_busca_trata_curingas_como_texto(conexao, chefe, ana):
    assert adm.listar_usuarios(conexao, chefe.id, "%") == []
    assert adm.listar_usuarios(conexao, chefe.id, "_") == []


# --- mudanças ---
def test_alterar_plano_grava_na_auditoria(conexao, chefe, ana):
    adm.alterar_plano(conexao, chefe.id, ana.id, "pro")
    assert buscar_por_id(conexao, ana.id).plano == "pro"
    registro = adm.auditoria_recente(conexao, chefe.id)[0]
    assert registro.acao == auditoria.ACAO_PLANO_ALTERADO
    assert registro.ator_id == chefe.id and registro.alvo_id == ana.id
    assert registro.detalhes == {"de": "gratuito", "para": "pro"}


def test_a_auditoria_nao_guarda_email_nem_nome(conexao, chefe, ana):
    adm.alterar_plano(conexao, chefe.id, ana.id, "pro")
    adm.alterar_papel(conexao, chefe.id, ana.id, "admin")
    texto = str(
        [(r.detalhes, r.acao) for r in adm.auditoria_recente(conexao, chefe.id)]
    )
    assert "ana@exemplo.com" not in texto and "Souza" not in texto


@pytest.mark.parametrize("plano", ["ouro", "", "PRO"])
def test_plano_invalido(conexao, chefe, ana, plano):
    with pytest.raises(adm.OperacaoInvalidaError):
        adm.alterar_plano(conexao, chefe.id, ana.id, plano)


def test_usuario_inexistente(conexao, chefe):
    with pytest.raises(adm.OperacaoInvalidaError):
        adm.alterar_plano(conexao, chefe.id, uuid.uuid4(), "pro")
    with pytest.raises(adm.OperacaoInvalidaError):
        adm.alterar_papel(conexao, chefe.id, uuid.uuid4(), "admin")


def test_promover_e_rebaixar_administrador(conexao, chefe, ana):
    adm.alterar_papel(conexao, chefe.id, ana.id, "admin")
    assert buscar_por_id(conexao, ana.id).e_admin
    adm.alterar_papel(conexao, chefe.id, ana.id, "usuario")
    assert not buscar_por_id(conexao, ana.id).e_admin


def test_quem_esta_na_lista_de_admins_nao_e_rebaixado_pelo_painel(conexao, chefe):
    """Achado 4a do Codex (ADR 0091): o login devolvia o papel que o painel tirou.

    A lista `TICKERLAB_ADMINS` manda: o painel recusa e explica que é preciso tirar o e-mail
    da lista no servidor; assim o rebaixamento nunca parece feito sem estar.
    """
    lista = ("chefe@exemplo.com", "outro@exemplo.com")
    outro = entrar(conexao, "outro", "outro@exemplo.com", emails_de_admin=lista)[0]
    with pytest.raises(adm.OperacaoInvalidaError, match="TICKERLAB_ADMINS"):
        adm.alterar_papel(conexao, chefe.id, outro.id, "usuario", emails_de_admin=lista)
    assert buscar_por_id(conexao, outro.id).e_admin
    # quem não está na lista continua podendo ser rebaixado, e o login não o promove de novo
    adm.alterar_papel(conexao, chefe.id, outro.id, "usuario", emails_de_admin=lista[:1])
    de_novo = entrar(conexao, "outro", "outro@exemplo.com", emails_de_admin=lista[:1])[
        0
    ]
    assert not de_novo.e_admin


def test_sem_a_lista_explicita_o_painel_le_a_do_servidor(conexao, chefe, monkeypatch):
    outro = entrar(
        conexao, "outro", "outro@exemplo.com", emails_de_admin=("outro@exemplo.com",)
    )[0]
    monkeypatch.setenv("TICKERLAB_ADMINS", "Outro@Exemplo.com")
    with pytest.raises(adm.OperacaoInvalidaError, match="TICKERLAB_ADMINS"):
        adm.alterar_papel(conexao, chefe.id, outro.id, "usuario")
    assert buscar_por_id(conexao, outro.id).e_admin


def test_ninguem_tira_o_proprio_acesso(conexao, chefe, ana):
    adm.alterar_papel(conexao, chefe.id, ana.id, "admin")
    with pytest.raises(adm.OperacaoInvalidaError, match="próprio"):
        adm.alterar_papel(conexao, chefe.id, chefe.id, "usuario")


def test_o_ultimo_administrador_nao_pode_ser_rebaixado(conexao, chefe, ana):
    adm.alterar_papel(conexao, chefe.id, ana.id, "admin")
    adm.alterar_papel(conexao, ana.id, chefe.id, "usuario")  # sobra a Ana
    with pytest.raises(adm.OperacaoInvalidaError):
        adm.alterar_papel(conexao, ana.id, ana.id, "usuario")
    assert buscar_por_id(conexao, ana.id).e_admin


def test_eventos_do_stripe_recentes(conexao, chefe):
    conexao.execute(sa.insert(eventos_stripe).values(id="evt_9", tipo="invoice.paid"))
    eventos = adm.eventos_recentes_do_stripe(conexao, chefe.id)
    assert [(e[0], e[1]) for e in eventos] == [("evt_9", "invoice.paid")]
