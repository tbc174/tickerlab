"""Suspender um conjunto da API externa para todas as organizações de uma vez (B-32a, PR 6, tarefa 11).

É o botão de parar quando a fonte muda a licença ou o dado sai errado: uma linha em
`conjuntos_suspensos` e o conjunto para de sair para todo contrato, inclusive o que for concedido
depois. Riscos que estes testes pegam: (1) um contrato novo escapar da suspensão; (2) reativar o
conjunto religar um direito que foi suspenso sozinho; (3) apagar linha do contrato para suspender;
(4) a auditoria levar mais que códigos.
"""

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from src import auditoria
from src.banco import chaves_da_api as cb
from src.banco.modelo import auditoria as tabela_da_auditoria
from src.banco.modelo import conjuntos_suspensos, direitos_da_organizacao
from src.banco.usuarios import entrar

AGORA = datetime(2026, 11, 3, 18, tzinfo=UTC)
HOJE = AGORA.date()
DFP = "cvm-dfp-itr"
FUNDOS = "cvm-fundos"


@pytest.fixture
def conexao(banco):
    with banco.begin() as conexao:
        yield conexao


@pytest.fixture
def admin(conexao):
    return entrar(conexao, "g-admin-conjunto", "admin-conjunto@exemplo.com")[0]


def _organizacao(conexao, admin, nome):
    return cb.criar_organizacao(conexao, nome=nome, ator_id=admin.id, agora=AGORA)


def _conceder(conexao, admin, organizacao, conjunto=DFP):
    return cb.conceder_direito(
        conexao,
        organizacao_id=organizacao.id,
        conjunto=conjunto,
        finalidade="analise",
        vigente_desde=HOJE,
        ator_id=admin.id,
    )


def _suspender(conexao, admin, conjunto=DFP, motivo="fonte"):
    return cb.suspender_conjunto(
        conexao, conjunto=conjunto, motivo=motivo, ator_id=admin.id, agora=AGORA
    )


def _reativar(conexao, admin, conjunto=DFP):
    return cb.reativar_conjunto(conexao, conjunto=conjunto, ator_id=admin.id)


def _permite(conexao, organizacao, conjunto=DFP):
    return cb.contrato_permite(
        conexao, organizacao.id, conjunto=conjunto, finalidade="analise", dia=HOJE
    )


def _conjuntos_vigentes(conexao, organizacao):
    return [d.conjunto for d in cb.direitos_vigentes(conexao, organizacao.id, HOJE)]


def test_suspender_conjunto_vale_para_todas_as_organizacoes(conexao, admin):
    alfa = _organizacao(conexao, admin, "Alfa Gestora")
    beta = _organizacao(conexao, admin, "Beta Crédito")
    for organizacao in (alfa, beta):
        _conceder(conexao, admin, organizacao)
        _conceder(conexao, admin, organizacao, FUNDOS)

    assert _suspender(conexao, admin)

    for organizacao in (alfa, beta):
        assert not _permite(conexao, organizacao)
        assert _permite(conexao, organizacao, FUNDOS)  # o outro conjunto segue
        assert _conjuntos_vigentes(conexao, organizacao) == [FUNDOS]


def test_contrato_concedido_depois_da_suspensao_tambem_para(conexao, admin):
    _suspender(conexao, admin)
    gama = _organizacao(conexao, admin, "Gama Seguros")
    _conceder(conexao, admin, gama)
    assert not _permite(conexao, gama)


def test_reativar_conjunto_volta_a_liberar(conexao, admin):
    alfa = _organizacao(conexao, admin, "Alfa Gestora")
    _conceder(conexao, admin, alfa)
    _suspender(conexao, admin)
    assert _reativar(conexao, admin)
    assert _permite(conexao, alfa)


def test_reativar_conjunto_nao_religa_direito_suspenso_sozinho(conexao, admin):
    alfa = _organizacao(conexao, admin, "Alfa Gestora")
    beta = _organizacao(conexao, admin, "Beta Crédito")
    _conceder(conexao, admin, alfa)
    direito_de_beta = _conceder(conexao, admin, beta)
    cb.suspender_direito(
        conexao,
        organizacao_id=beta.id,
        direito_id=direito_de_beta.id,
        ator_id=admin.id,
        agora=AGORA,
    )
    _suspender(conexao, admin)
    _reativar(conexao, admin)
    assert _permite(conexao, alfa)
    assert not _permite(conexao, beta)


def test_suspender_ou_reativar_duas_vezes_nao_muda_nada(conexao, admin):
    assert _suspender(conexao, admin)
    assert not _suspender(conexao, admin, motivo="contrato")
    linha = conexao.execute(sa.select(conjuntos_suspensos)).one()
    assert linha.motivo_da_suspensao == "fonte"  # o motivo da primeira fica
    assert _reativar(conexao, admin)
    assert not _reativar(conexao, admin)
    assert not _reativar(conexao, admin, FUNDOS)  # nunca suspenso


def test_suspender_de_novo_depois_de_reativar(conexao, admin):
    alfa = _organizacao(conexao, admin, "Alfa Gestora")
    _conceder(conexao, admin, alfa)
    _suspender(conexao, admin)
    _reativar(conexao, admin)
    assert _suspender(conexao, admin, motivo="abuso")
    assert not _permite(conexao, alfa)
    linha = conexao.execute(sa.select(conjuntos_suspensos)).one()
    assert linha.motivo_da_suspensao == "abuso"


def test_motivo_fora_da_lista_e_recusado(conexao, admin):
    with pytest.raises(ValueError, match="Motivo"):
        _suspender(conexao, admin, motivo="porque sim")
    assert conexao.execute(sa.select(conjuntos_suspensos)).all() == []


def test_conjunto_invalido_e_recusado(conexao, admin):
    with pytest.raises(ValueError):
        _suspender(conexao, admin, conjunto="   ")


def test_suspender_conjunto_nao_apaga_nem_marca_o_contrato(conexao, admin):
    alfa = _organizacao(conexao, admin, "Alfa Gestora")
    _conceder(conexao, admin, alfa)
    _suspender(conexao, admin)
    linhas = conexao.execute(sa.select(direitos_da_organizacao)).all()
    assert [(linha.conjunto, linha.suspenso_em) for linha in linhas] == [(DFP, None)]
    _reativar(conexao, admin)
    assert conexao.execute(sa.select(conjuntos_suspensos)).one().suspenso_em is None


def test_auditoria_do_conjunto_leva_so_codigos(conexao, admin):
    _suspender(conexao, admin)
    _reativar(conexao, admin)
    registros = conexao.execute(
        sa.select(tabela_da_auditoria).where(
            tabela_da_auditoria.c.acao.in_(
                [auditoria.ACAO_CONJUNTO_SUSPENSO, auditoria.ACAO_CONJUNTO_REATIVADO]
            )
        )
    ).all()
    detalhes = {registro.acao: registro.detalhes for registro in registros}
    assert detalhes == {
        auditoria.ACAO_CONJUNTO_SUSPENSO: {"conjunto": DFP, "motivo": "fonte"},
        auditoria.ACAO_CONJUNTO_REATIVADO: {"conjunto": DFP},
    }
    assert all(registro.ator_id == admin.id for registro in registros)


def test_lista_dos_conjuntos_suspensos(conexao, admin):
    _suspender(conexao, admin, FUNDOS, motivo="contrato")
    _suspender(conexao, admin)
    _suspender(conexao, admin, "cvm-cadastro")
    _reativar(conexao, admin, "cvm-cadastro")
    assert [(s.conjunto, s.motivo) for s in cb.conjuntos_suspensos_agora(conexao)] == [
        (DFP, "fonte"),
        (FUNDOS, "contrato"),
    ]


def test_contratos_do_conjunto_conta_todas_as_organizacoes(conexao, admin):
    alfa = _organizacao(conexao, admin, "Alfa Gestora")
    beta = _organizacao(conexao, admin, "Beta Crédito")
    _conceder(conexao, admin, alfa)
    _conceder(conexao, admin, beta)
    _conceder(conexao, admin, beta, FUNDOS)
    assert cb.contratos_do_conjunto(conexao, DFP) == 2
    assert cb.contratos_do_conjunto(conexao, FUNDOS) == 1
    assert cb.contratos_do_conjunto(conexao, "dfp") == 0
