"""A conta nova pela API v1 (ADR 0062, tela 2, PR 1): o primeiro login pelo app novo.

Até aqui, quem nunca tinha entrado recebia 401 "conta-nova" e precisava passar pelo Streamlit. Agora
`POST /v1/conta` cria a conta com o mesmo token do Google e as mesmas regras do Streamlit
(`src/autenticacao.registrar_login`): admin só pelo e-mail confirmado, origem do cookie só na primeira vez.
"""

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from src import api
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso, conta
from src.auditoria import ACAO_TERMOS_ACEITOS
from src.autenticacao import VARIAVEL_DOS_ADMINS
from src.banco import novidades_por_email
from src.banco.modelo import auditoria as auditoria_tabela
from src.banco.origens import buscar_origem
from src.banco.usuarios import TEXTO_DA_CONTA_BLOQUEADA, buscar_por_google_sub, entrar
from src.conformidade import VERSAO_DOS_TERMOS, registrar_aceite
from src.envio_novidades import VERSAO_DO_CONSENTIMENTO
from tests.ajudantes_da_api import (
    AGORA,
    CLIENT_ID,
    chaves_publicas,
    com_token,
    da_sessao,
    gerar_chave,
    token,
)
from tests.ajudantes_da_conta import bloquear_pelo_admin

DA_CARLA = {"sub": "carla", "email": "carla@exemplo.com", "name": "Carla"}


@pytest.fixture(scope="module")
def chave():
    return gerar_chave()


@pytest.fixture
def cliente(banco, monkeypatch, chave):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setenv(acesso.VARIAVEL_DO_CLIENT_ID, CLIENT_ID)
    monkeypatch.delenv(VARIAVEL_DOS_ADMINS, raising=False)
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    app = api.criar_app({VARIAVEL_DA_CHAVE: "1"})
    app.dependency_overrides[acesso.chaves_do_google] = lambda: chaves_publicas(chave)
    acesso.LIMITE.zerar()
    return TestClient(app)


def _criar(cliente, chave, cookies=None, **claims):
    cliente.cookies.clear()
    for nome, valor in (cookies or {}).items():
        cliente.cookies.set(nome, valor)
    return cliente.post(
        "/api/v1/conta", headers=com_token(token(chave, **{**DA_CARLA, **claims}))
    )


def _da_carla(banco):
    with banco.connect() as conexao:
        return buscar_por_google_sub(conexao, "carla")


def test_o_primeiro_login_cria_a_conta(cliente, banco, chave):
    resposta = _criar(cliente, chave)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["primeira_vez"] is True
    assert dados["plano"] == "gratuito"
    assert dados["administrador"] is False
    assert dados["nome"] == "Carla"
    assert "email" not in dados  # como no /v1/eu: nada de e-mail na resposta
    carla = _da_carla(banco)
    assert carla is not None and carla.email == "carla@exemplo.com"


def test_entrar_de_novo_nao_cria_outra_conta(cliente, banco, chave):
    _criar(cliente, chave)
    primeira = _da_carla(banco)
    resposta = _criar(cliente, chave, name="Carla Souza")
    assert resposta.status_code == 200
    assert resposta.json()["primeira_vez"] is False
    depois = _da_carla(banco)
    assert depois is not None and primeira is not None
    assert depois.id == primeira.id
    assert depois.nome == "Carla Souza"  # o login atualiza o nome, como no Streamlit


def test_conta_bloqueada_nao_entra_pelo_google_nem_abre_sessao(cliente, banco, chave):
    _criar(cliente, chave)
    bloquear_pelo_admin(banco, _da_carla(banco).id)
    resposta = _criar(cliente, chave)
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == TEXTO_DA_CONTA_BLOQUEADA
    assert "set-cookie" not in resposta.headers


def test_admin_pelo_email_da_lista(cliente, banco, chave, monkeypatch):
    monkeypatch.setenv(VARIAVEL_DOS_ADMINS, "outra@exemplo.com, CARLA@exemplo.com")
    assert _criar(cliente, chave).json()["administrador"] is True


def test_email_nao_confirmado_nao_cria_conta(cliente, banco, chave, monkeypatch):
    monkeypatch.setenv(VARIAVEL_DOS_ADMINS, "carla@exemplo.com")
    resposta = _criar(cliente, chave, email_verified=False)
    assert resposta.status_code == 401
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "token-invalido"
    assert _da_carla(banco) is None


@pytest.mark.parametrize("cabecalho", [{}, {"Authorization": "Bearer lixo"}])
def test_sem_token_valido_401(cliente, banco, cabecalho):
    resposta = cliente.post("/api/v1/conta", headers=cabecalho)
    assert resposta.status_code == 401
    assert _da_carla(banco) is None


def test_token_de_outro_aplicativo_401(cliente, banco, chave):
    assert _criar(cliente, chave, aud="outro-app").status_code == 401


def test_conta_nova_ainda_precisa_aceitar_os_termos(cliente, banco, chave):
    _criar(cliente, chave)
    eu = cliente.get("/api/v1/eu", headers=da_sessao(banco, _da_carla(banco)))
    assert eu.status_code == 403
    assert eu.headers[acesso.CABECALHO_DO_MOTIVO] == "termos"
    carla = _da_carla(banco)
    assert carla is not None
    with banco.begin() as conexao:
        registrar_aceite(conexao, carla.id)
    eu = cliente.get("/api/v1/eu", headers=da_sessao(banco, _da_carla(banco)))
    assert eu.status_code == 200


def test_a_origem_do_cookie_fica_so_na_primeira_vez(cliente, banco, chave):
    _criar(cliente, chave, cookies={"tl_origem": "s=instagram|m=publi|r=clube"})
    _criar(cliente, chave, cookies={"tl_origem": "s=google|m=cpc"})
    carla = _da_carla(banco)
    assert carla is not None
    with banco.connect() as conexao:
        origem = buscar_origem(conexao, carla.id)
    assert origem is not None
    assert (origem.source, origem.medium, origem.ref) == ("instagram", "publi", "clube")


def test_cookie_de_origem_estragado_e_ignorado(cliente, banco, chave):
    assert _criar(cliente, chave, cookies={"tl_origem": "x" * 900}).status_code == 200
    carla = _da_carla(banco)
    assert carla is not None
    with banco.connect() as conexao:
        assert buscar_origem(conexao, carla.id) is None


def test_criar_conta_respeita_o_limite_de_pedidos(cliente, chave, monkeypatch):
    monkeypatch.setattr(acesso.LIMITE, "por_minuto", 2)
    assert _criar(cliente, chave).status_code == 200
    assert _criar(cliente, chave).status_code == 200
    assert _criar(cliente, chave).status_code == 429


def test_dois_pedidos_ao_mesmo_tempo_criam_uma_conta_so(
    cliente, banco, chave, monkeypatch
):
    """Duas abas abrindo juntas: a segunda bate na chave única e entra na conta que a primeira criou."""
    original = conta.registrar_login
    chamadas = []

    def concorrente(identidade, **kwargs):
        chamadas.append(1)
        if len(chamadas) == 1:
            original(
                identidade, **kwargs
            )  # a outra aba criou a conta antes desta gravar
            raise IntegrityError("INSERT INTO usuarios", {}, Exception("chave única"))
        return original(identidade, **kwargs)

    monkeypatch.setattr(conta, "registrar_login", concorrente)
    resposta = _criar(cliente, chave)
    assert resposta.status_code == 200
    assert resposta.json()["primeira_vez"] is False
    assert len(chamadas) == 2


def test_api_desligada_404(banco, monkeypatch, chave):
    monkeypatch.delenv(VARIAVEL_DA_CHAVE, raising=False)
    app = api.criar_app({})
    resposta = TestClient(app).post(
        "/api/v1/conta", headers=com_token(token(chave, **DA_CARLA))
    )
    assert resposta.status_code == 404


# --- O aceite dos termos pela API (conta e planos, PR 2) --------------------------------------


def _aceitar(cliente, banco, versao=VERSAO_DOS_TERMOS):
    return cliente.post(
        "/api/v1/aceite-dos-termos",
        headers=da_sessao(banco, _da_carla(banco)),
        json={"versao": versao},
    )


def test_aceitar_os_termos_libera_a_conta(cliente, banco, chave):
    _criar(cliente, chave)
    resposta = _aceitar(cliente, banco)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["plano"] == "gratuito"
    carla = _da_carla(banco)
    assert carla is not None and carla.termos_versao == VERSAO_DOS_TERMOS
    eu = cliente.get("/api/v1/eu", headers=da_sessao(banco, _da_carla(banco)))
    assert eu.status_code == 200


def test_o_aceite_fica_na_auditoria(cliente, banco, chave):
    _criar(cliente, chave)
    _aceitar(cliente, banco)
    carla = _da_carla(banco)
    assert carla is not None
    with banco.connect() as conexao:
        acoes = conexao.execute(
            sa.select(auditoria_tabela.c.acao).where(
                auditoria_tabela.c.ator_id == carla.id
            )
        ).scalars()
        assert ACAO_TERMOS_ACEITOS in list(acoes)


def test_versao_velha_dos_termos_e_recusada(cliente, banco, chave):
    """Uma aba aberta antes da troca dos termos mostra o texto velho: não vale como aceite do novo."""
    _criar(cliente, chave)
    resposta = _aceitar(cliente, banco, versao="2020-01-01.1")
    assert resposta.status_code == 409
    carla = _da_carla(banco)
    assert carla is not None and carla.termos_versao != VERSAO_DOS_TERMOS


@pytest.mark.parametrize("corpo", [{}, {"versao": 7}, {"versao": "x" * 100}])
def test_aceite_sem_versao_valida_422(cliente, banco, chave, corpo):
    _criar(cliente, chave)
    resposta = cliente.post(
        "/api/v1/aceite-dos-termos",
        headers=da_sessao(banco, _da_carla(banco)),
        json=corpo,
    )
    assert resposta.status_code == 422


def test_aceite_sem_sessao_401(cliente, banco, chave):
    """Sem conta não há sessão: o pedido chega sem o cookie e a API pede para entrar."""
    resposta = cliente.post(
        "/api/v1/aceite-dos-termos",
        headers={"X-TickerLab-Pedido": "1"},
        json={"versao": VERSAO_DOS_TERMOS},
    )
    assert resposta.status_code == 401
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "sem-token"


def test_aceite_sem_token_401(cliente, banco):
    resposta = cliente.post(
        "/api/v1/aceite-dos-termos", json={"versao": VERSAO_DOS_TERMOS}
    )
    assert resposta.status_code == 401


def test_o_aceite_vale_so_para_a_conta_do_token(cliente, banco, chave):
    _criar(cliente, chave)
    with banco.begin() as conexao:
        entrar(conexao, "davi", "davi@exemplo.com")
    _aceitar(cliente, banco)
    with banco.connect() as conexao:
        davi = buscar_por_google_sub(conexao, "davi")
    assert davi is not None and davi.termos_versao != VERSAO_DOS_TERMOS


def test_novidades_por_email_so_com_a_caixa_marcada(cliente, banco, chave):
    _criar(cliente, chave)
    _aceitar(cliente, banco)
    carla = _da_carla(banco)
    assert carla is not None
    with banco.connect() as conexao:
        assert novidades_por_email.inscricao(conexao, carla.id) is None


def test_caixa_das_novidades_marcada_inscreve(cliente, banco, chave):
    _criar(cliente, chave)
    resposta = cliente.post(
        "/api/v1/aceite-dos-termos",
        headers=da_sessao(banco, _da_carla(banco)),
        json={
            "versao": VERSAO_DOS_TERMOS,
            "novidades": True,
            "versao_das_novidades": VERSAO_DO_CONSENTIMENTO,
        },
    )
    assert resposta.status_code == 200, resposta.text
    carla = _da_carla(banco)
    assert carla is not None
    with banco.connect() as conexao:
        inscrita = novidades_por_email.inscricao(conexao, carla.id)
    assert inscrita is not None
    assert inscrita.versao_do_consentimento == VERSAO_DO_CONSENTIMENTO


def test_texto_velho_das_novidades_nao_vale_como_consentimento(cliente, banco, chave):
    _criar(cliente, chave)
    resposta = cliente.post(
        "/api/v1/aceite-dos-termos",
        headers=da_sessao(banco, _da_carla(banco)),
        json={
            "versao": VERSAO_DOS_TERMOS,
            "novidades": True,
            "versao_das_novidades": "2000-01-01",
        },
    )
    assert resposta.status_code == 409
    carla = _da_carla(banco)
    assert carla is not None and carla.termos_versao != VERSAO_DOS_TERMOS
    with banco.connect() as conexao:
        assert novidades_por_email.inscricao(conexao, carla.id) is None
