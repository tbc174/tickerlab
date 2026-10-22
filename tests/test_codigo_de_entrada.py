"""Código de entrada por e-mail (plano do login, PR 2, tarefa 7): 6 dígitos, 10 minutos, 5 tentativas.

O banco guarda só hashes (do e-mail e do código). Pedir um código novo não derruba o anterior que
ainda vale (um estranho que sabe o e-mail não tranca a dona); há um limite de pedidos por e-mail. O expurgo apaga o que venceu há tempo (LGPD: guardar só o necessário).
"""

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from src import codigo_de_entrada as cod
from src.banco import sessoes
from src.banco.modelo import codigos_de_entrada, sessoes_de_login
from src.banco.usuarios import entrar

AGORA = datetime(2026, 10, 19, 12, tzinfo=UTC)
EMAIL = "Ana@Exemplo.com"


def _pedir(conexao, quando=AGORA, email=EMAIL):
    return cod.pedir_codigo(conexao, email, agora=quando)


def test_codigo_tem_seis_digitos_e_o_banco_guarda_so_hash(banco):
    with banco.begin() as conexao:
        codigo = _pedir(conexao)
        linha = conexao.execute(sa.select(codigos_de_entrada)).one()
    assert codigo is not None and len(codigo) == 6 and codigo.isdigit()
    assert codigo not in str(tuple(linha)) and "ana@exemplo.com" not in str(
        tuple(linha)
    )
    assert linha.expira_em.replace(tzinfo=UTC) == AGORA + timedelta(minutes=10)


def test_codigo_certo_confirma_sem_diferenciar_a_caixa_do_email(banco):
    with banco.begin() as conexao:
        codigo = _pedir(conexao)
        assert cod.conferir_codigo(conexao, "ana@exemplo.com", codigo, agora=AGORA)


def test_codigo_errado_recusado(banco):
    with banco.begin() as conexao:
        codigo = _pedir(conexao)
        errado = "000000" if codigo != "000000" else "111111"
        assert not cod.conferir_codigo(conexao, EMAIL, errado, agora=AGORA)


def test_sexta_tentativa_recusada_mesmo_com_o_codigo_certo(banco):
    with banco.begin() as conexao:
        codigo = _pedir(conexao)
        errado = "000000" if codigo != "000000" else "111111"
        for _ in range(5):
            assert not cod.conferir_codigo(conexao, EMAIL, errado, agora=AGORA)
        assert not cod.conferir_codigo(conexao, EMAIL, codigo, agora=AGORA)


def test_codigo_vencido_recusado(banco):
    with banco.begin() as conexao:
        codigo = _pedir(conexao)
        no_limite = AGORA + timedelta(minutes=10)
        assert not cod.conferir_codigo(conexao, EMAIL, codigo, agora=no_limite)


def test_codigo_usado_nao_vale_de_novo(banco):
    with banco.begin() as conexao:
        codigo = _pedir(conexao)
        assert cod.conferir_codigo(conexao, EMAIL, codigo, agora=AGORA)
        assert not cod.conferir_codigo(conexao, EMAIL, codigo, agora=AGORA)


def _errado(*codigos):
    return next(c for c in ("000000", "111111", "222222", "333333") if c not in codigos)


def test_codigo_novo_nao_derruba_o_anterior_que_ainda_vale(banco):
    # quem pede o código é quem digita o e-mail, não quem é dono dele: se o pedido novo derrubasse o
    # anterior, um estranho que sabe o e-mail invalidaria o código que a dona acabou de receber
    with banco.begin() as conexao:
        primeiro = _pedir(conexao)
        _pedir(conexao, AGORA + timedelta(minutes=1))
        assert cod.conferir_codigo(
            conexao, EMAIL, primeiro, agora=AGORA + timedelta(minutes=2)
        )


def test_estranho_que_esgota_os_pedidos_nao_tranca_a_dona_do_email(banco):
    # os 3 pedidos do estranho caem na caixa da dona: qualquer um deles a deixa entrar
    with banco.begin() as conexao:
        recebidos = [_pedir(conexao, AGORA + timedelta(minutes=i)) for i in range(3)]
        assert _pedir(conexao, AGORA + timedelta(minutes=3)) is None
        assert cod.conferir_codigo(
            conexao, EMAIL, recebidos[0], agora=AGORA + timedelta(minutes=4)
        )


def test_entrar_gasta_todos_os_codigos_vivos_do_email(banco):
    with banco.begin() as conexao:
        primeiro = _pedir(conexao)
        segundo = _pedir(conexao, AGORA + timedelta(minutes=1))
        agora = AGORA + timedelta(minutes=2)
        assert cod.conferir_codigo(conexao, EMAIL, segundo, agora=agora)
        assert not cod.conferir_codigo(conexao, EMAIL, primeiro, agora=agora)


def test_cada_tentativa_conta_em_todos_os_codigos_vivos(banco):
    # com vários códigos vivos, o chute é comparado com todos; para o limite de chutes não crescer,
    # a tentativa gasta uma de cada um (5 erros esgotam os 3 códigos)
    with banco.begin() as conexao:
        codigos = [_pedir(conexao, AGORA + timedelta(minutes=i)) for i in range(3)]
        agora = AGORA + timedelta(minutes=4)
        for _ in range(cod.TENTATIVAS):
            assert not cod.conferir_codigo(
                conexao, EMAIL, _errado(*codigos), agora=agora
            )
        for codigo in codigos:
            assert not cod.conferir_codigo(conexao, EMAIL, codigo, agora=agora)


def test_codigo_esgotado_nao_atrapalha_o_novo(banco):
    with banco.begin() as conexao:
        primeiro = _pedir(conexao)
        for _ in range(cod.TENTATIVAS):
            cod.conferir_codigo(conexao, EMAIL, _errado(primeiro), agora=AGORA)
        segundo = _pedir(conexao, AGORA + timedelta(minutes=1))
        assert cod.conferir_codigo(
            conexao, EMAIL, segundo, agora=AGORA + timedelta(minutes=2)
        )


def test_codigo_de_um_email_nao_abre_outro(banco):
    with banco.begin() as conexao:
        codigo = _pedir(conexao)
        assert not cod.conferir_codigo(conexao, "bia@exemplo.com", codigo, agora=AGORA)


def test_quarto_pedido_em_quinze_minutos_nao_gera_codigo(banco):
    with banco.begin() as conexao:
        for i in range(3):
            assert _pedir(conexao, AGORA + timedelta(minutes=i)) is not None
        assert _pedir(conexao, AGORA + timedelta(minutes=4)) is None
        # passada a janela, volta a valer
        assert _pedir(conexao, AGORA + timedelta(minutes=16)) is not None


def test_pedido_barrado_nao_invalida_o_codigo_que_vale(banco):
    with banco.begin() as conexao:
        codigos = [_pedir(conexao, AGORA + timedelta(minutes=i)) for i in range(3)]
        assert _pedir(conexao, AGORA + timedelta(minutes=4)) is None
        assert cod.conferir_codigo(
            conexao, EMAIL, codigos[-1], agora=AGORA + timedelta(minutes=5)
        )


def test_email_invalido_nao_gera_codigo(banco):
    with banco.begin() as conexao:
        for ruim in ("", "sem-arroba", "a" * 400 + "@x.com"):
            assert cod.pedir_codigo(conexao, ruim, agora=AGORA) is None
    assert cod.email_valido("ana@exemplo.com") and not cod.email_valido("ana")


def test_texto_do_email_leva_o_codigo_e_a_validade():
    email = cod.montar_email("123456")
    assert "123456" in email.texto and "123456" in email.html
    assert "10 minutos" in email.texto


def test_expurgo_apaga_o_que_venceu_ha_tempo_e_guarda_o_recente(banco):
    with banco.begin() as conexao:
        ana = entrar(conexao, "g-ana", "ana@exemplo.com")[0]
        velha = sessoes.abrir(
            conexao, ana.id, "google", agora=AGORA - timedelta(days=200)
        )
        encerrada = sessoes.abrir(
            conexao, ana.id, "google", agora=AGORA - timedelta(days=100)
        )
        sessoes.encerrar(conexao, encerrada, agora=AGORA - timedelta(days=95))
        viva = sessoes.abrir(conexao, ana.id, "google", agora=AGORA - timedelta(days=5))
        recente = sessoes.abrir(
            conexao, ana.id, "google", agora=AGORA - timedelta(days=40)
        )
        sessoes.encerrar(conexao, recente, agora=AGORA - timedelta(days=10))
        _pedir(conexao, AGORA - timedelta(days=3))  # vencido há ~3 dias
        _pedir(
            conexao, AGORA - timedelta(hours=2), email="bia@exemplo.com"
        )  # vencido há < 1 dia
        _pedir(
            conexao, AGORA - timedelta(minutes=1), email="cai@exemplo.com"
        )  # ainda vale
        apagados = cod.expurgar(conexao, agora=AGORA)
        restantes = {
            s.hash_do_token for s in conexao.execute(sa.select(sessoes_de_login))
        }
        codigos = conexao.execute(sa.select(codigos_de_entrada)).all()
    assert apagados == {"sessoes": 2, "codigos": 1}
    assert len(restantes) == 2 and len(codigos) == 2
    assert sessoes._hash(viva) in restantes and sessoes._hash(recente) in restantes
    assert sessoes._hash(velha) not in restantes
