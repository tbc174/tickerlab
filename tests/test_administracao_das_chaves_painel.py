"""O painel da organização para a Administração do app novo (linha 955): a regra, sem a tela.

O que estes testes travam: só administrador lê o painel; o painel de uma organização não traz nada da
outra; o que "ainda está desligado" sai do que a API externa oferece menos o contrato; e a permissão
`pessoa_na_tela` e os membros aparecem só como estado e número.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src import administracao_das_chaves as adc
from src.administracao import PermissaoNegadaError
from src.banco import chaves_da_api as cb
from src.banco import membros_da_organizacao as membros
from src.banco.usuarios import entrar
from src.portao_externo import DIREITOS_DA_API_EXTERNA, Canal

AGORA = datetime.now(UTC)
HOJE = AGORA.date()
OFERECIDOS = frozenset({"events", "links", "profiles"})


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
    return _usuario(banco, "g-admin-painel", admin=True)


@pytest.fixture
def comum(banco):
    return _usuario(banco, "g-comum-painel", admin=False)


def _organizacao(banco, admin, nome):
    with banco.begin() as conexao:
        return adc.criar_organizacao(
            conexao, admin.id, nome=nome, cnpj=None, plano_da_api="piloto"
        )


def _conceder(banco, admin, organizacao, conjunto, finalidade="analise"):
    with banco.begin() as conexao:
        return cb.conceder_direito(
            conexao,
            organizacao_id=organizacao.id,
            conjunto=conjunto,
            finalidade=finalidade,
            vigente_desde=HOJE,
            ator_id=admin.id,
        )


def _painel(banco, ator_id, organizacao_id):
    with banco.connect() as conexao:
        return adc.painel_da_organizacao(
            conexao, ator_id, organizacao_id, HOJE, oferecidos=OFERECIDOS
        )


def _chave(**mudancas):
    campos = {
        "id": uuid.uuid4(),
        "prefixo": "tl_teste_0000",
        "criada_em": AGORA - timedelta(days=10),
        "expira_em": None,
        "revogada_em": None,
        "ultimo_uso": None,
    }
    return cb.ChaveListada(**{**campos, **mudancas})


# --- as regras puras ----------------------------------------------------------------------


def test_o_estado_da_chave_segue_a_revogacao_e_o_prazo_da_rotacao():
    assert adc.estado_da_chave(_chave(), AGORA) == adc.CHAVE_ATIVA
    de_saida = _chave(expira_em=AGORA + timedelta(days=3))
    assert adc.estado_da_chave(de_saida, AGORA) == adc.CHAVE_DE_SAIDA
    vencida = _chave(expira_em=AGORA - timedelta(seconds=1))
    assert adc.estado_da_chave(vencida, AGORA) == adc.CHAVE_EXPIRADA
    # revogada ganha de tudo, mesmo com o prazo da rotação ainda aberto
    revogada = _chave(revogada_em=AGORA, expira_em=AGORA + timedelta(days=3))
    assert adc.estado_da_chave(revogada, AGORA) == adc.CHAVE_REVOGADA


def test_so_a_chave_sem_prazo_e_sem_revogacao_ocupa_vaga():
    chaves = [
        _chave(),
        _chave(expira_em=AGORA + timedelta(days=3)),
        _chave(revogada_em=AGORA),
        _chave(),
    ]
    assert adc.chaves_que_ocupam_vaga(chaves) == 2


def test_desligado_e_o_que_a_api_oferece_menos_o_contrato():
    desligados = adc.conjuntos_desligados(
        OFERECIDOS, contratados={"profiles"}, suspensos_para_todos={"events"}
    )
    assert desligados == [
        adc.ConjuntoDesligado("events", adc.MOTIVO_SUSPENSO_PARA_TODOS),
        adc.ConjuntoDesligado("links", adc.MOTIVO_SEM_CONTRATO),
    ]
    # com tudo contratado e nada suspenso, não sobra nada
    assert adc.conjuntos_desligados(OFERECIDOS, OFERECIDOS, set()) == []


def test_os_conjuntos_oferecidos_saem_das_linhas_do_portao_da_api_externa():
    oferecidos = adc.conjuntos_da_api_externa(DIREITOS_DA_API_EXTERNA)
    esperados = {
        linha.conjunto
        for linha in DIREITOS_DA_API_EXTERNA
        if linha.canal == Canal.API_EXTERNA
    }
    assert oferecidos == esperados
    assert "links" in oferecidos and "profiles" in oferecidos
    # a permissão da tela e a marca de piloto não são conjuntos de dado: nunca entram aqui
    assert membros.CONJUNTO_DE_PESSOA_NA_TELA not in oferecidos
    assert cb.CONJUNTO_DO_PILOTO not in oferecidos


# --- o painel -----------------------------------------------------------------------------


def test_quem_nao_e_admin_nao_le_o_painel(banco, admin, comum):
    organizacao = _organizacao(banco, admin, "Alfa Gestora")
    for ator_id in (comum.id, uuid.uuid4(), None):
        with pytest.raises(PermissaoNegadaError):
            _painel(banco, ator_id, organizacao.id)


def test_o_painel_de_uma_organizacao_inexistente_e_recusado(banco, admin):
    with pytest.raises(cb.OrganizacaoInvalidaError):
        _painel(banco, admin.id, uuid.uuid4())


def test_o_painel_mostra_o_contrato_e_o_que_ainda_esta_desligado(banco, admin):
    organizacao = _organizacao(banco, admin, "Alfa Gestora")
    _conceder(banco, admin, organizacao, "profiles")
    with banco.begin() as conexao:
        nova = adc.emitir_chave(conexao, admin.id, organizacao.id)
    painel = _painel(banco, admin.id, organizacao.id)
    assert [d.conjunto for d in painel.visao.direitos] == ["profiles"]
    assert painel.desligados == [
        adc.ConjuntoDesligado("events", adc.MOTIVO_SEM_CONTRATO),
        adc.ConjuntoDesligado("links", adc.MOTIVO_SEM_CONTRATO),
    ]
    assert [c.prefixo for c in painel.visao.chaves] == [nova.prefixo]
    assert painel.chaves_ativas == 1
    assert painel.limites.chaves_ativas == 3  # o plano piloto
    assert painel.pessoa_na_tela is False
    assert painel.membros == 0


def test_o_conjunto_suspenso_para_todos_aparece_com_o_motivo(banco, admin):
    organizacao = _organizacao(banco, admin, "Alfa Gestora")
    _conceder(banco, admin, organizacao, "profiles")
    with banco.begin() as conexao:
        cb.suspender_conjunto(
            conexao, conjunto="profiles", motivo="fonte", ator_id=admin.id
        )
    painel = _painel(banco, admin.id, organizacao.id)
    assert painel.visao.direitos == []
    assert (
        adc.ConjuntoDesligado("profiles", adc.MOTIVO_SUSPENSO_PARA_TODOS)
        in painel.desligados
    )


def test_a_pessoa_na_tela_e_os_membros_saem_como_estado_e_numero(banco, admin, comum):
    organizacao = _organizacao(banco, admin, "Alfa Gestora")
    _conceder(banco, admin, organizacao, membros.CONJUNTO_DE_PESSOA_NA_TELA)
    with banco.begin() as conexao:
        membros.vincular_membro(
            conexao,
            organizacao_id=organizacao.id,
            usuario_id=comum.id,
            ator_id=admin.id,
        )
    painel = _painel(banco, admin.id, organizacao.id)
    assert painel.pessoa_na_tela is True
    assert painel.membros == 1
    # a permissão da tela não é um conjunto da API: não some de "desligados" nem entra lá
    assert {d.conjunto for d in painel.desligados} == set(OFERECIDOS)


def test_o_painel_de_uma_organizacao_nao_traz_nada_da_outra(banco, admin, comum):
    alfa = _organizacao(banco, admin, "Alfa Gestora")
    beta = _organizacao(banco, admin, "Beta Capital")
    _conceder(banco, admin, alfa, "profiles")
    _conceder(banco, admin, beta, "events")
    _conceder(banco, admin, beta, membros.CONJUNTO_DE_PESSOA_NA_TELA)
    with banco.begin() as conexao:
        chave_da_alfa = adc.emitir_chave(conexao, admin.id, alfa.id)
        chave_da_beta = adc.emitir_chave(conexao, admin.id, beta.id)
        membros.vincular_membro(
            conexao, organizacao_id=beta.id, usuario_id=comum.id, ator_id=admin.id
        )
    painel = _painel(banco, admin.id, alfa.id)
    assert painel.visao.organizacao.id == alfa.id
    assert [c.prefixo for c in painel.visao.chaves] == [chave_da_alfa.prefixo]
    assert chave_da_beta.prefixo not in [c.prefixo for c in painel.visao.chaves]
    assert [d.conjunto for d in painel.visao.direitos] == ["profiles"]
    assert painel.pessoa_na_tela is False
    assert painel.membros == 0
