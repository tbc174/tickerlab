"""Entrar com e-mail e código na API v1 (plano do login, PR 2, tarefas 7 a 9) e o "sair de todos".

`POST /v1/entrada/codigo` responde igual com ou sem conta (não revela quem tem conta) e manda o código
pelo Resend (aqui, um dublê). `POST /v1/entrada/confirmar` confere o código, cria a conta no primeiro
acesso e abre a sessão de 30 dias. `POST /v1/sair-de-todos` encerra as sessões de todos os aparelhos.
"""

import logging

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src import api
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso, entrada, sessao
from src.banco import sessoes
from src.banco.modelo import identidades
from src.banco.usuarios import buscar_por_identidade, entrar
from src.conformidade import registrar_aceite

DO_SITE = {"X-TickerLab-Pedido": "1", "Origin": "http://testserver"}
EMAIL = "carla@exemplo.com"


@pytest.fixture
def enviados(monkeypatch):
    """Os e-mails que iriam para o Resend: lista de (para, código)."""
    lista: list[tuple[str, str]] = []
    monkeypatch.setattr(
        entrada, "enviar_o_codigo", lambda para, c: lista.append((para, c))
    )
    return lista


@pytest.fixture
def cliente(banco, monkeypatch, enviados):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    acesso.LIMITE.zerar()
    entrada.LIMITE_POR_IP.zerar()
    return TestClient(api.criar_app({VARIAVEL_DA_CHAVE: "1"}))


def _pedir(cliente, email=EMAIL, **extra):
    return cliente.post(
        "/api/v1/entrada/codigo", json={"email": email}, headers={**DO_SITE, **extra}
    )


def _confirmar(cliente, email, codigo, **extra):
    return cliente.post(
        "/api/v1/entrada/confirmar",
        json={"email": email, "codigo": codigo},
        headers={**DO_SITE, **extra},
    )


def _cookie_da_sessao(resposta) -> str:
    (posto,) = [
        c
        for c in resposta.headers.get_list("set-cookie")
        if c.startswith(sessao.NOME_DO_COOKIE)
    ]
    return posto.split(";")[0].split("=", 1)[1]


def _conta_google(banco, sub="g-ana", email="ana@exemplo.com", nome="Ana"):
    with banco.begin() as conexao:
        conta = entrar(conexao, sub, email, nome, email_confirmado=True)[0]
        registrar_aceite(conexao, conta.id)
    return conta


# --- pedir o código ------------------------------------------------------------------------


def test_pedir_codigo_envia_o_codigo_para_o_email(cliente, enviados):
    resposta = _pedir(cliente, "Carla@Exemplo.com")
    assert resposta.status_code == 202
    assert len(enviados) == 1 and enviados[0][0] == EMAIL
    assert len(enviados[0][1]) == 6


def test_pedir_codigo_responde_igual_com_ou_sem_conta(cliente, banco, enviados):
    _conta_google(banco)
    com_conta = _pedir(cliente, "ana@exemplo.com")
    sem_conta = _pedir(cliente, "ninguem@exemplo.com")
    assert (com_conta.status_code, com_conta.json()) == (
        sem_conta.status_code,
        sem_conta.json(),
    )
    assert len(enviados) == 2  # os dois recebem o código: quem espiona não distingue


def test_pedir_acima_do_limite_por_email_responde_igual_e_nao_envia(cliente, enviados):
    respostas = [_pedir(cliente) for _ in range(5)]
    assert {r.status_code for r in respostas} == {202}
    assert len({str(r.json()) for r in respostas}) == 1
    assert len(enviados) == 3  # PEDIDOS_POR_EMAIL


def test_pedir_acima_do_limite_por_ip_responde_429(cliente, enviados, monkeypatch):
    monkeypatch.setattr(entrada.LIMITE_POR_IP, "por_minuto", 2)  # o teto da janela
    assert _pedir(cliente, "a@exemplo.com").status_code == 202
    assert _pedir(cliente, "b@exemplo.com").status_code == 202
    assert _pedir(cliente, "c@exemplo.com").status_code == 429
    assert len(enviados) == 2


def test_o_limite_por_ip_olha_o_ip_de_quem_pediu(cliente, enviados, monkeypatch):
    monkeypatch.setattr(entrada.LIMITE_POR_IP, "por_minuto", 1)
    assert (
        _pedir(cliente, "a@exemplo.com", **{"CF-Connecting-IP": "1.1.1.1"}).status_code
        == 202
    )
    assert (
        _pedir(cliente, "b@exemplo.com", **{"CF-Connecting-IP": "2.2.2.2"}).status_code
        == 202
    )
    assert (
        _pedir(cliente, "c@exemplo.com", **{"CF-Connecting-IP": "1.1.1.1"}).status_code
        == 429
    )


def test_email_invalido_responde_igual_e_nao_envia(cliente, enviados):
    resposta = _pedir(cliente, "sem-arroba")
    assert resposta.status_code == 202 and enviados == []


def test_pedir_de_fora_do_site_403(cliente, enviados):
    resposta = cliente.post("/api/v1/entrada/codigo", json={"email": EMAIL})
    assert resposta.status_code == 403 and enviados == []


def test_resend_fora_do_ar_nao_muda_a_resposta(cliente, monkeypatch):
    def falhar(_para, _codigo):
        raise entrada.EnvioFalhouError("o Resend recusou (HTTP 500)")

    monkeypatch.setattr(entrada, "enviar_o_codigo", falhar)
    assert _pedir(cliente).status_code == 202


def test_log_nao_leva_o_email_nem_o_codigo(cliente, enviados, monkeypatch, caplog):
    def falhar(_para, _codigo):
        raise entrada.EnvioFalhouError("o Resend recusou (HTTP 500)")

    with caplog.at_level(logging.DEBUG):
        _pedir(cliente)
        codigo = enviados[0][1]
        monkeypatch.setattr(entrada, "enviar_o_codigo", falhar)
        _pedir(cliente, "outra@exemplo.com")
        _confirmar(cliente, EMAIL, "000000")
    assert EMAIL not in caplog.text and "outra@exemplo.com" not in caplog.text
    assert codigo not in caplog.text


def test_o_envio_usa_a_chave_do_resend_e_o_texto_do_codigo(monkeypatch):
    chamadas = {}

    def transporte(url, **kwargs):
        chamadas.update(url=url, **kwargs)

        class Resposta:
            ok = True

            def json(self):
                return {"id": "x"}

        return Resposta()

    monkeypatch.setenv("RESEND_API_KEY", "re_teste")
    monkeypatch.setattr(entrada, "TRANSPORTE", transporte)
    entrada.enviar_o_codigo(EMAIL, "123456")
    assert chamadas["headers"]["Authorization"] == "Bearer re_teste"
    assert chamadas["json"]["to"] == [EMAIL] and "123456" in chamadas["json"]["text"]
    assert (
        "headers" not in chamadas["json"]
    )  # sem cabeçalho de descadastro: não é newsletter


def test_sem_a_chave_do_resend_o_envio_falha_sem_vazar(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    with pytest.raises(entrada.EnvioFalhouError) as erro:
        entrada.enviar_o_codigo(EMAIL, "123456")
    assert EMAIL not in str(erro.value)


# --- confirmar -----------------------------------------------------------------------------


def test_confirmar_cria_a_conta_no_primeiro_acesso_e_abre_a_sessao(
    cliente, banco, enviados
):
    _pedir(cliente)
    resposta = _confirmar(cliente, EMAIL, enviados[0][1])
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["primeira_vez"] is True
    cookie = _cookie_da_sessao(resposta)
    with banco.begin() as conexao:
        conta = sessoes.conta_da_sessao(conexao, cookie)
        ident = conexao.execute(sa.select(identidades)).one()
    assert conta is not None and conta.email == EMAIL and conta.papel == "usuario"
    assert (ident.provedor, ident.sub, ident.email_confirmado) == ("email", EMAIL, True)


def test_segundo_acesso_entra_na_mesma_conta(cliente, banco, enviados):
    _pedir(cliente)
    primeira = _confirmar(cliente, EMAIL, enviados[0][1])
    _pedir(cliente)
    segunda = _confirmar(cliente, EMAIL, enviados[1][1])
    assert segunda.json()["primeira_vez"] is False
    with banco.begin() as conexao:
        a = sessoes.conta_da_sessao(conexao, _cookie_da_sessao(primeira))
        b = sessoes.conta_da_sessao(conexao, _cookie_da_sessao(segunda))
    assert a is not None and b is not None and a.id == b.id


def test_codigo_de_email_junta_com_a_conta_do_google_do_mesmo_email(
    cliente, banco, enviados
):
    ana = _conta_google(banco)
    _pedir(cliente, "ana@exemplo.com")
    resposta = _confirmar(cliente, "ana@exemplo.com", enviados[0][1])
    assert resposta.json()["primeira_vez"] is False
    with banco.connect() as conexao:
        dona = buscar_por_identidade(conexao, "email", "ana@exemplo.com")
    assert dona is not None and dona.id == ana.id


def test_codigo_errado_401_com_o_motivo(cliente, enviados):
    _pedir(cliente)
    errado = "000000" if enviados[0][1] != "000000" else "111111"
    resposta = _confirmar(cliente, EMAIL, errado)
    assert resposta.status_code == 401
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "codigo"
    assert not resposta.headers.get_list("set-cookie")


def test_confirmar_sem_pedir_codigo_401_igual_a_codigo_errado(cliente):
    resposta = _confirmar(cliente, "nunca@exemplo.com", "123456")
    assert resposta.status_code == 401
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "codigo"


def test_codigo_usado_nao_abre_outra_sessao(cliente, enviados):
    _pedir(cliente)
    codigo = enviados[0][1]
    assert _confirmar(cliente, EMAIL, codigo).status_code == 200
    assert _confirmar(cliente, EMAIL, codigo).status_code == 401


def test_cinco_erros_travam_o_codigo_mesmo_com_o_certo(cliente, enviados):
    _pedir(cliente)
    codigo = enviados[0][1]
    errado = "000000" if codigo != "000000" else "111111"
    for _ in range(5):
        assert _confirmar(cliente, EMAIL, errado).status_code == 401
    assert _confirmar(cliente, EMAIL, codigo).status_code == 401


def test_confirmar_de_fora_do_site_403(cliente, enviados):
    _pedir(cliente)
    resposta = cliente.post(
        "/api/v1/entrada/confirmar", json={"email": EMAIL, "codigo": enviados[0][1]}
    )
    assert resposta.status_code == 403


def test_confirmar_encerra_a_sessao_que_o_navegador_ja_tinha(cliente, banco, enviados):
    ana = _conta_google(banco)
    with banco.begin() as conexao:
        antiga = sessoes.abrir(conexao, ana.id, "google")
    _pedir(cliente, "ana@exemplo.com")
    resposta = _confirmar(
        cliente,
        "ana@exemplo.com",
        enviados[0][1],
        Cookie=f"{sessao.NOME_DO_COOKIE}={antiga}",
    )
    assert resposta.status_code == 200
    with banco.begin() as conexao:
        assert sessoes.conta_da_sessao(conexao, antiga) is None


def test_corpo_com_codigo_enorme_422(cliente):
    resposta = cliente.post(
        "/api/v1/entrada/confirmar",
        json={"email": EMAIL, "codigo": "1" * 5000},
        headers=DO_SITE,
    )
    assert resposta.status_code == 422


# --- sair de todos os aparelhos (R2) -------------------------------------------------------


def _com_cookie(valor: str, **extra: str) -> dict[str, str]:
    return {"Cookie": f"{sessao.NOME_DO_COOKIE}={valor}", **extra}


def _duas_contas(banco):
    ana = _conta_google(banco)
    bia = _conta_google(banco, "g-bia", "bia@exemplo.com", "Bia")
    with banco.begin() as conexao:
        return (
            sessoes.abrir(conexao, ana.id, "google"),
            sessoes.abrir(conexao, ana.id, "email"),
            sessoes.abrir(conexao, bia.id, "google"),
        )


def test_sair_de_todos_encerra_as_sessoes_da_conta_e_so_dela(cliente, banco):
    do_pc, do_celular, da_bia = _duas_contas(banco)
    resposta = cliente.post(
        "/api/v1/sair-de-todos", headers=_com_cookie(do_pc, **DO_SITE)
    )
    assert resposta.status_code == 200 and resposta.json() == {"encerradas": 2}
    assert "max-age=0" in resposta.headers["set-cookie"].lower()
    assert cliente.get("/api/v1/eu", headers=_com_cookie(do_pc)).status_code == 401
    assert cliente.get("/api/v1/eu", headers=_com_cookie(do_celular)).status_code == 401
    assert cliente.get("/api/v1/eu", headers=_com_cookie(da_bia)).status_code == 200


def test_sair_de_todos_sem_login_401(cliente):
    assert cliente.post("/api/v1/sair-de-todos", headers=DO_SITE).status_code == 401


def test_sair_de_todos_de_fora_do_site_403_e_nada_encerra(cliente, banco):
    do_pc, _, _ = _duas_contas(banco)
    resposta = cliente.post("/api/v1/sair-de-todos", headers=_com_cookie(do_pc))
    assert resposta.status_code == 403
    assert cliente.get("/api/v1/eu", headers=_com_cookie(do_pc)).status_code == 200
