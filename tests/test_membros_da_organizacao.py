"""Quem é da organização e se ela vê pessoa física na tela (ADR 0128, Emenda 1; linha 808, PR 1).

Riscos que estes testes pegam: (1) a conta de uma organização ver o que só a outra pode; (2) conta
sem organização ver; (3) a permissão valer depois de vencida, suspensa ou com a organização suspensa;
(4) a permissão da tela abrir algo na API por chave; (5) nome ou e-mail ir para a auditoria.
Todo dado aqui é fictício.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa

from src import auditoria, conformidade
from src.api_externa import acesso
from src.api_externa.catalogo import catalogo_da_organizacao
from src.banco import chaves_da_api as cb
from src.banco import membros_da_organizacao as mb
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.modelo import membros_da_organizacao, usuarios
from src.banco.usuarios import apagar_conta, entrar
from src.chaves_da_api import ContextoDaChave

AGORA = datetime(2026, 11, 10, 16, tzinfo=UTC)
HOJE = AGORA.date()
ONTEM = HOJE - timedelta(days=1)
AMANHA = HOJE + timedelta(days=1)


@pytest.fixture
def conexao(banco):
    with banco.begin() as conexao:
        yield conexao


@pytest.fixture
def admin(conexao):
    return entrar(conexao, "g-admin-808", "admin-808@exemplo.com")[0]


@pytest.fixture
def ana(conexao):
    return entrar(conexao, "g-ana-808", "ana-808@exemplo.com", "Ana Exemplo")[0]


@pytest.fixture
def bia(conexao):
    return entrar(conexao, "g-bia-808", "bia-808@exemplo.com", "Bia Exemplo")[0]


def _organizacao(conexao, admin, nome):
    return cb.criar_organizacao(conexao, nome=nome, ator_id=admin.id, agora=AGORA)


@pytest.fixture
def casa(conexao, admin):
    return _organizacao(conexao, admin, "Casa Exemplo")


@pytest.fixture
def outra(conexao, admin):
    return _organizacao(conexao, admin, "Outra Exemplo")


def _vincular(conexao, admin, organizacao, conta):
    return mb.vincular_membro(
        conexao,
        organizacao_id=organizacao.id,
        usuario_id=conta.id,
        ator_id=admin.id,
        agora=AGORA,
    )


def _ligar(conexao, admin, organizacao, desde=ONTEM, ate=None, finalidade=None):
    return cb.conceder_direito(
        conexao,
        organizacao_id=organizacao.id,
        conjunto=mb.CONJUNTO_DE_PESSOA_NA_TELA,
        finalidade=finalidade or mb.FINALIDADE_DA_TELA,
        vigente_desde=desde,
        vigente_ate=ate,
        ator_id=admin.id,
        agora=AGORA,
    )


# ---------------------------------------------------------------- desligada por padrão


def test_conta_sem_organizacao_nao_ve(conexao, ana):
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is False
    assert mb.organizacao_que_ve_pessoa(conexao, ana.id, HOJE) is None


def test_membro_de_organizacao_sem_a_permissao_nao_ve(conexao, admin, casa, ana):
    _vincular(conexao, admin, casa, ana)
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is False


def test_permissao_sem_ser_membro_nao_ve(conexao, admin, casa, ana):
    _ligar(conexao, admin, casa)
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is False


def test_conta_que_nao_existe_nao_ve(conexao, admin, casa):
    _ligar(conexao, admin, casa)
    assert mb.pode_ver_pessoa(conexao, uuid.UUID(int=1), HOJE) is False


# ---------------------------------------------------------------- duas organizações


def test_uma_organizacao_ve_e_a_outra_nao(conexao, admin, casa, outra, ana, bia):
    _vincular(conexao, admin, casa, ana)
    _vincular(conexao, admin, outra, bia)
    _ligar(conexao, admin, casa)
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is True
    assert mb.organizacao_que_ve_pessoa(conexao, ana.id, HOJE) == casa.id
    assert mb.pode_ver_pessoa(conexao, bia.id, HOJE) is False
    # o admin que ligou não é membro: também não vê
    assert mb.pode_ver_pessoa(conexao, admin.id, HOJE) is False


def test_outro_direito_da_organizacao_nao_liga_a_pessoa(conexao, admin, casa, ana):
    _vincular(conexao, admin, casa, ana)
    cb.conceder_direito(
        conexao,
        organizacao_id=casa.id,
        conjunto="cnpj_empresas_pj",
        finalidade="analise",
        vigente_desde=ONTEM,
        ator_id=admin.id,
        agora=AGORA,
    )
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is False


def test_a_permissao_e_so_da_finalidade_de_analise(conexao, admin, casa, ana):
    _vincular(conexao, admin, casa, ana)
    _ligar(conexao, admin, casa, finalidade="credito")
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is False


# ---------------------------------------------------------------- desligar


def test_antes_e_depois_da_vigencia_nao_ve(conexao, admin, casa, ana):
    _vincular(conexao, admin, casa, ana)
    _ligar(conexao, admin, casa, desde=HOJE, ate=HOJE)
    assert mb.pode_ver_pessoa(conexao, ana.id, ONTEM) is False
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is True
    assert mb.pode_ver_pessoa(conexao, ana.id, AMANHA) is False


def test_direito_suspenso_para_de_valer_e_reativado_volta(conexao, admin, casa, ana):
    _vincular(conexao, admin, casa, ana)
    direito = _ligar(conexao, admin, casa)
    cb.suspender_direito(
        conexao, organizacao_id=casa.id, direito_id=direito.id, ator_id=admin.id
    )
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is False
    cb.reativar_direito(
        conexao, organizacao_id=casa.id, direito_id=direito.id, ator_id=admin.id
    )
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is True


def test_organizacao_suspensa_nao_ve(conexao, admin, casa, ana):
    _vincular(conexao, admin, casa, ana)
    _ligar(conexao, admin, casa)
    cb.suspender_organizacao(
        conexao, organizacao_id=casa.id, motivo="contrato", ator_id=admin.id
    )
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is False


def test_conjunto_parado_para_todos_desliga_todas(conexao, admin, casa, ana):
    _vincular(conexao, admin, casa, ana)
    _ligar(conexao, admin, casa)
    cb.suspender_conjunto(
        conexao,
        conjunto=mb.CONJUNTO_DE_PESSOA_NA_TELA,
        motivo="fonte",
        ator_id=admin.id,
    )
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is False


def test_conta_bloqueada_nao_ve(conexao, admin, casa, ana):
    _vincular(conexao, admin, casa, ana)
    _ligar(conexao, admin, casa)
    conexao.execute(
        sa.update(usuarios)
        .where(usuarios.c.id == ana.id)
        .values(bloqueada_em=AGORA, motivo_do_bloqueio="incidente")
    )
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is False


def test_desvincular_tira_a_visao(conexao, admin, casa, ana):
    _vincular(conexao, admin, casa, ana)
    _ligar(conexao, admin, casa)
    assert mb.desvincular_membro(
        conexao, organizacao_id=casa.id, usuario_id=ana.id, ator_id=admin.id
    )
    assert mb.pode_ver_pessoa(conexao, ana.id, HOJE) is False
    assert mb.listar_membros(conexao, casa.id) == []


# ---------------------------------------------------------------- vínculo


def test_vincular_grava_e_lista_so_os_da_organizacao(
    conexao, admin, casa, outra, ana, bia
):
    membro = _vincular(conexao, admin, casa, ana)
    _vincular(conexao, admin, outra, bia)
    assert membro == mb.Membro(ana.id, casa.id, AGORA)
    assert mb.listar_membros(conexao, casa.id) == [membro]
    assert [m.usuario_id for m in mb.listar_membros(conexao, outra.id)] == [bia.id]


def test_conta_e_de_uma_organizacao_so(conexao, admin, casa, outra, ana):
    _vincular(conexao, admin, casa, ana)
    with pytest.raises(mb.JaEMembroError):
        _vincular(conexao, admin, outra, ana)
    with pytest.raises(mb.JaEMembroError):
        _vincular(conexao, admin, casa, ana)
    assert len(mb.listar_membros(conexao, casa.id)) == 1


def test_vincular_recusa_organizacao_ou_conta_inexistente(conexao, admin, casa, ana):
    ninguem = uuid.UUID(int=7)
    with pytest.raises(cb.OrganizacaoInvalidaError):
        mb.vincular_membro(
            conexao, organizacao_id=ninguem, usuario_id=ana.id, ator_id=admin.id
        )
    with pytest.raises(mb.ContaInexistenteError):
        mb.vincular_membro(
            conexao, organizacao_id=casa.id, usuario_id=ninguem, ator_id=admin.id
        )


def test_desvincular_de_outra_organizacao_nao_muda_nada(
    conexao, admin, casa, outra, ana
):
    _vincular(conexao, admin, casa, ana)
    assert not mb.desvincular_membro(
        conexao, organizacao_id=outra.id, usuario_id=ana.id, ator_id=admin.id
    )
    assert len(mb.listar_membros(conexao, casa.id)) == 1


def test_apagar_a_conta_apaga_o_vinculo(conexao, admin, casa, ana):
    _vincular(conexao, admin, casa, ana)
    apagar_conta(conexao, ana.id)
    assert conexao.execute(sa.select(membros_da_organizacao)).all() == []


def test_apagar_o_admin_que_vinculou_deixa_o_vinculo(conexao, admin, casa, ana):
    _vincular(conexao, admin, casa, ana)
    apagar_conta(conexao, admin.id)
    linha = conexao.execute(sa.select(membros_da_organizacao)).one()
    assert linha.usuario_id == ana.id and linha.vinculado_por is None


# ---------------------------------------------------------------- auditoria só com ids


def _registros(conexao, acao):
    return conexao.execute(
        sa.select(tabela_da_auditoria).where(tabela_da_auditoria.c.acao == acao)
    ).all()


def test_vincular_e_desvincular_ficam_na_auditoria_sem_nome_nem_email(
    conexao, admin, casa, ana
):
    _vincular(conexao, admin, casa, ana)
    mb.desvincular_membro(
        conexao, organizacao_id=casa.id, usuario_id=ana.id, ator_id=admin.id
    )
    for acao in (auditoria.ACAO_MEMBRO_VINCULADO, auditoria.ACAO_MEMBRO_DESVINCULADO):
        (registro,) = _registros(conexao, acao)
        assert registro.ator_id == admin.id
        assert registro.alvo_id == ana.id
        assert registro.detalhes == {"organizacao_id": str(casa.id)}
        assert "exemplo" not in str(registro.detalhes).lower()


def test_vinculo_recusado_nao_vai_para_a_auditoria(conexao, admin, casa, outra, ana):
    _vincular(conexao, admin, casa, ana)
    with pytest.raises(mb.JaEMembroError):
        _vincular(conexao, admin, outra, ana)
    assert len(_registros(conexao, auditoria.ACAO_MEMBRO_VINCULADO)) == 1


# ---------------------------------------------------------------- LGPD: exportar


def test_exportar_traz_a_organizacao_da_pessoa_e_so_a_dela(
    conexao, admin, casa, ana, bia
):
    _vincular(conexao, admin, casa, ana)
    assert mb.dados_para_exportar(conexao, usuario_id=ana.id) == {
        "nome": "Casa Exemplo",
        "membro_desde": AGORA.isoformat(),
    }
    assert mb.dados_para_exportar(conexao, usuario_id=bia.id) is None
    assert conformidade.exportar_meus_dados(conexao, ana.id)["organizacao"] == {
        "nome": "Casa Exemplo",
        "membro_desde": AGORA.isoformat(),
    }
    assert conformidade.exportar_meus_dados(conexao, bia.id)["organizacao"] is None


# ---------------------------------------------------------------- a API por chave não muda


def test_a_permissao_da_tela_nao_abre_nada_na_api_por_chave(conexao, admin, casa):
    """A mesma organização, com a permissão ligada, continua sem pessoa pela chave: o portão não
    tem linha para `pessoa_na_tela`, então o catálogo não o mostra e o pedido é negado."""
    _ligar(conexao, admin, casa)
    chave = cb.emitir_chave(
        conexao, organizacao_id=casa.id, ator_id=admin.id, agora=AGORA
    )
    contexto = ContextoDaChave(casa.id, chave.chave_id, chave.prefixo, "piloto")
    catalogo = catalogo_da_organizacao(conexao, contexto, HOJE)
    assert mb.CONJUNTO_DE_PESSOA_NA_TELA not in str(catalogo)
    for fonte, campo in (("rfb-cnpj", "nome_socio"), ("rfb-cnpj", "telefone")):
        decisao = acesso.autorizar(
            conexao,
            contexto,
            fonte=fonte,
            conjunto=mb.CONJUNTO_DE_PESSOA_NA_TELA,
            campo=campo,
            finalidade=mb.FINALIDADE_DA_TELA,
            hoje=HOJE,
        )
        assert decisao.libera is False


def test_o_dia_e_uma_data(conexao, ana):
    # o dia vem de quem chama (a rota usa o dia em UTC, como o contrato da API)
    assert mb.pode_ver_pessoa(conexao, ana.id, date(2026, 11, 20)) is False
