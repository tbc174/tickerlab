"""Sessões de login do app novo (plano do login com Microsoft e e-mail, PR 1, tarefa 3).

O cookie leva um código aleatório; o banco guarda só o hash dele. A sessão vale 30 dias a contar de
quando abriu, e acaba antes se a pessoa sai, se todas as sessões da conta são encerradas ou se a conta
é apagada.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from src.banco import sessoes
from src.banco.modelo import sessoes_de_login
from src.banco.usuarios import apagar_conta, entrar

AGORA = datetime(2026, 10, 18, 12, tzinfo=UTC)


def _conta(conexao, sub="g-ana", email="ana@exemplo.com"):
    return entrar(conexao, sub, email)[0]


def test_abrir_devolve_o_token_e_grava_so_o_hash(banco):
    with banco.begin() as conexao:
        ana = _conta(conexao)
        token = sessoes.abrir(conexao, ana.id, "google", agora=AGORA)
        linha = conexao.execute(sa.select(sessoes_de_login)).one()
    assert len(token) >= 43  # 32 bytes aleatórios em base64
    assert token not in str(tuple(linha))
    assert linha.hash_do_token == hashlib.sha256(token.encode()).hexdigest()
    assert linha.provedor == "google" and linha.usuario_id == ana.id
    assert linha.expira_em.replace(tzinfo=UTC) == AGORA + timedelta(days=30)


def test_token_abre_a_conta_dele(banco):
    with banco.begin() as conexao:
        ana = _conta(conexao)
        token = sessoes.abrir(conexao, ana.id, "google", agora=AGORA)
        conta = sessoes.conta_da_sessao(conexao, token, agora=AGORA + timedelta(days=1))
    assert conta is not None and conta.id == ana.id


def test_sessao_vencida(banco):
    with banco.begin() as conexao:
        token = sessoes.abrir(conexao, _conta(conexao).id, "google", agora=AGORA)
        no_ultimo_minuto = AGORA + timedelta(days=30) - timedelta(minutes=1)
        assert sessoes.conta_da_sessao(conexao, token, agora=no_ultimo_minuto)
        vencida = sessoes.conta_da_sessao(
            conexao, token, agora=AGORA + timedelta(days=30)
        )
    assert vencida is None


def test_sair_encerra_a_sessao(banco):
    with banco.begin() as conexao:
        ana = _conta(conexao)
        token = sessoes.abrir(conexao, ana.id, "google", agora=AGORA)
        outra = sessoes.abrir(conexao, ana.id, "google", agora=AGORA)  # o celular
        assert sessoes.encerrar(conexao, token, agora=AGORA) is True
        assert sessoes.conta_da_sessao(conexao, token, agora=AGORA) is None
        # sair num aparelho não tira a pessoa do outro
        assert sessoes.conta_da_sessao(conexao, outra, agora=AGORA) is not None
        # sair de novo (ou com um token que não existe) não é erro
        assert sessoes.encerrar(conexao, token, agora=AGORA) is False
        assert sessoes.encerrar(conexao, "nao-existe", agora=AGORA) is False


def test_encerrar_todas(banco):
    with banco.begin() as conexao:
        ana, bia = _conta(conexao), _conta(conexao, "g-bia", "bia@exemplo.com")
        da_ana = [
            sessoes.abrir(conexao, ana.id, "google", agora=AGORA) for _ in range(2)
        ]
        da_bia = sessoes.abrir(conexao, bia.id, "google", agora=AGORA)
        assert sessoes.encerrar_todas(conexao, ana.id, agora=AGORA) == 2
        assert all(
            sessoes.conta_da_sessao(conexao, t, agora=AGORA) is None for t in da_ana
        )
        assert sessoes.conta_da_sessao(conexao, da_bia, agora=AGORA) is not None


def test_sessao_de_uma_conta_nao_abre_outra(banco):
    with banco.begin() as conexao:
        ana, bia = _conta(conexao), _conta(conexao, "g-bia", "bia@exemplo.com")
        da_ana = sessoes.abrir(conexao, ana.id, "google", agora=AGORA)
        da_bia = sessoes.abrir(conexao, bia.id, "google", agora=AGORA)
        assert sessoes.conta_da_sessao(conexao, da_ana, agora=AGORA).id == ana.id
        assert sessoes.conta_da_sessao(conexao, da_bia, agora=AGORA).id == bia.id
        assert da_ana != da_bia


def test_token_vazio_ou_estranho_nao_abre_nada(banco):
    with banco.begin() as conexao:
        sessoes.abrir(conexao, _conta(conexao).id, "google", agora=AGORA)
        for token in ("", " ", "x" * 5000):
            assert sessoes.conta_da_sessao(conexao, token, agora=AGORA) is None


def test_apagar_a_conta_apaga_as_sessoes(banco):
    with banco.begin() as conexao:
        ana = _conta(conexao)
        token = sessoes.abrir(conexao, ana.id, "google", agora=AGORA)
        apagar_conta(conexao, ana.id)
        assert sessoes.conta_da_sessao(conexao, token, agora=AGORA) is None
        assert (
            conexao.execute(
                sa.select(sa.func.count()).select_from(sessoes_de_login)
            ).scalar()
            == 0
        )


def test_uso_da_sessao_fica_registrado(banco):
    """O último uso aparece na exportação dos dados (LGPD) e mostra sessões esquecidas."""
    with banco.begin() as conexao:
        token = sessoes.abrir(conexao, _conta(conexao).id, "google", agora=AGORA)
        depois = AGORA + timedelta(days=2)
        sessoes.conta_da_sessao(conexao, token, agora=depois)
        ultimo_uso = conexao.execute(sa.select(sessoes_de_login.c.ultimo_uso)).scalar()
    assert ultimo_uso.replace(tzinfo=UTC) == depois
