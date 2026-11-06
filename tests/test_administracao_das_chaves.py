"""A administração das chaves da API para a tela do admin (N7, linha 169): só admin, isolada e sem segredo."""

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from src import administracao_das_chaves as adc
from src.administracao import PermissaoNegadaError
from src.banco import chaves_da_api as cb
from src.banco.modelo import auditoria
from src.banco.usuarios import entrar
from src.chaves_da_api import FORMATO, hash_da_chave

HOJE = datetime.now(UTC).date()


def _usuario(banco, sub, *, admin):
    email = f"{sub}@exemplo.com"
    with banco.begin() as conexao:
        return entrar(
            conexao,
            sub,
            email,
            emails_de_admin=(email,) if admin else (),
            email_confirmado=True,
        )[0]


@pytest.fixture
def admin(banco):
    return _usuario(banco, "g-admin-chaves", admin=True)


@pytest.fixture
def comum(banco):
    return _usuario(banco, "g-comum-chaves", admin=False)


def _organizacao(banco, admin, nome="Alfa Gestora"):
    with banco.begin() as conexao:
        return adc.criar_organizacao(
            conexao, admin.id, nome=nome, cnpj=None, plano_da_api="piloto"
        )


def _tentativas(organizacao_id, chave_id):
    """Cada função da administração, com os argumentos de uma chamada qualquer."""
    return [
        lambda c, a: adc.listar_organizacoes(c, a),
        lambda c, a: adc.ver_organizacao(c, a, organizacao_id, HOJE),
        lambda c, a: adc.criar_organizacao(
            c, a, nome="Beta", cnpj=None, plano_da_api="piloto"
        ),
        lambda c, a: adc.emitir_chave(c, a, organizacao_id),
        lambda c, a: adc.rotacionar_chave(c, a, organizacao_id, chave_id),
        lambda c, a: adc.revogar_chave(c, a, organizacao_id, chave_id),
        lambda c, a: adc.suspender_organizacao(c, a, organizacao_id, "pagamento"),
        lambda c, a: adc.reativar_organizacao(c, a, organizacao_id),
    ]


def test_quem_nao_e_admin_e_recusado_em_toda_funcao(banco, admin, comum):
    organizacao = _organizacao(banco, admin)
    with banco.begin() as conexao:
        nova = adc.emitir_chave(conexao, admin.id, organizacao.id)
    antes = _estado(banco)
    for tentativa in _tentativas(organizacao.id, nova.chave_id):
        with banco.begin() as conexao, pytest.raises(PermissaoNegadaError):
            tentativa(conexao, comum.id)
    # ator inexistente (sessão velha, id inventado) também não passa
    for tentativa in _tentativas(organizacao.id, nova.chave_id):
        with banco.begin() as conexao, pytest.raises(PermissaoNegadaError):
            tentativa(conexao, uuid.uuid4())
    assert _estado(banco) == antes


def _estado(banco):
    with banco.connect() as conexao:
        tabelas = ("organizacoes", "chaves_da_api", "auditoria")
        return [
            conexao.execute(sa.text(f"select count(*) from {t}")).scalar_one()
            for t in tabelas
        ]


def test_admin_cria_emite_rotaciona_revoga_suspende_e_ve_o_consumo(banco, admin):
    organizacao = _organizacao(banco, admin)
    with banco.begin() as conexao:
        primeira = adc.emitir_chave(conexao, admin.id, organizacao.id)
        segunda = adc.rotacionar_chave(
            conexao, admin.id, organizacao.id, primeira.chave_id
        )
    with banco.connect() as conexao:
        visao = adc.ver_organizacao(conexao, admin.id, organizacao.id, HOJE)
    prefixos = {c.prefixo: c for c in visao.chaves}
    assert prefixos[primeira.prefixo].expira_em is not None  # de saída
    assert prefixos[segunda.prefixo].expira_em is None
    assert (visao.consumo.pedidos, visao.consumo.negados) == (0, 0)

    with banco.begin() as conexao:
        assert adc.revogar_chave(conexao, admin.id, organizacao.id, segunda.chave_id)
        assert adc.suspender_organizacao(conexao, admin.id, organizacao.id, "pagamento")
        assert adc.listar_organizacoes(conexao, admin.id)[0].suspensa_em is not None
        with pytest.raises(cb.OrganizacaoSuspensaError):
            adc.emitir_chave(conexao, admin.id, organizacao.id)
        assert adc.reativar_organizacao(conexao, admin.id, organizacao.id)


def test_chave_de_outra_organizacao_nao_se_mexe_pela_organizacao_errada(banco, admin):
    alfa = _organizacao(banco, admin, "Alfa")
    beta = _organizacao(banco, admin, "Beta")
    with banco.begin() as conexao:
        da_beta = adc.emitir_chave(conexao, admin.id, beta.id)
    with banco.begin() as conexao:
        assert not adc.revogar_chave(conexao, admin.id, alfa.id, da_beta.chave_id)
    with banco.begin() as conexao, pytest.raises(cb.ChaveInexistenteError):
        adc.rotacionar_chave(conexao, admin.id, alfa.id, da_beta.chave_id)
    with banco.connect() as conexao:
        assert adc.ver_organizacao(conexao, admin.id, alfa.id, HOJE).chaves == []
        beta_depois = adc.ver_organizacao(conexao, admin.id, beta.id, HOJE)
    assert [c.revogada_em for c in beta_depois.chaves] == [None]


def test_a_chave_nova_nao_vai_para_a_auditoria_nem_a_visao_mostra_o_hash(banco, admin):
    organizacao = _organizacao(banco, admin)
    with banco.begin() as conexao:
        nova = adc.emitir_chave(conexao, admin.id, organizacao.id)
    assert FORMATO.fullmatch(nova.valor)
    assert nova.valor not in repr(nova)
    with banco.connect() as conexao:
        visao = adc.ver_organizacao(conexao, admin.id, organizacao.id, HOJE)
        registros = conexao.execute(sa.select(auditoria)).fetchall()
    texto = repr(visao) + repr(registros)
    assert nova.valor not in texto
    assert hash_da_chave(nova.valor) not in texto
    assert nova.valor.split("_", 2)[2] not in texto  # nem o segredo sozinho
