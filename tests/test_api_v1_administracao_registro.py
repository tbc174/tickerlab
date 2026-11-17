"""As leituras do registro de ações e dos eventos do Stripe na Administração do app novo
(src/api_v1/administracao_registro.py, linha 962, PR 5).

Banco SQLite com as migrações. O que estes testes travam: quem é administrador se confere no servidor, nas
duas rotas (conta comum recebe o 404 de um endereço que não existe; visitante, 401; quem deixou de ser
administrador não entra no pedido seguinte; a regra em `src/` recusa de novo se a dependência deixar
passar); as ações saem das mais novas para as mais antigas, com o fuso escrito; o e-mail aparece só na
resposta ao administrador, só de conta que ainda existe, e nunca no log; e ler não muda nada. Contas
inventadas, todas em `exemplo.com`; eventos do Stripe inventados.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src import administracao as adm
from src import api
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso
from src.api_v1 import administracao as rotas_da_administracao
from src.api_v1 import administracao_registro as rotas_do_registro
from src.autenticacao import VARIAVEL_DOS_ADMINS
from src.banco.modelo import auditoria, eventos_stripe, usuarios
from src.banco.usuarios import entrar, mudar_papel
from src.conformidade import registrar_aceite
from tests.ajudantes_da_api import AGORA, da_sessao

REGISTRO = "/v1/admin/registro"
EVENTOS = "/v1/admin/eventos-do-stripe"
ROTAS = [REGISTRO, EVENTOS]
# depois de tudo o que as contas de teste gravam ao nascer (o aceite dos termos), para as linhas
# inventadas aqui serem as mais novas
BEM_DEPOIS = datetime(2031, 5, 10, 12, 0, tzinfo=UTC)
ALVO_QUE_NAO_E_CONTA = uuid.UUID("00000000-0000-4000-8000-0000000000aa")


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.delenv(VARIAVEL_DOS_ADMINS, raising=False)
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    acesso.LIMITE.zerar()


@pytest.fixture
def app():
    return api.criar_app({VARIAVEL_DA_CHAVE: "1"})


def _conta(banco, sub, *, admin=False):
    with banco.begin() as conexao:
        usuario = entrar(conexao, sub, f"{sub}@exemplo.com", sub.title())[0]
        registrar_aceite(conexao, usuario.id)
        if admin:
            mudar_papel(conexao, usuario.id, "admin")
    return usuario


@pytest.fixture
def chefe(banco):
    """A conta administradora."""
    return _conta(banco, "chefe", admin=True)


@pytest.fixture
def carla(banco):
    """Uma conta que não é administradora."""
    return _conta(banco, "carla")


def _cliente(banco, app, usuario):
    return TestClient(app, headers=da_sessao(banco, usuario))


def _gravar(banco, acao, *, ator=None, alvo=None, detalhes=None, minutos=0):
    """Uma linha na auditoria, `minutos` depois de `BEM_DEPOIS`; devolve o id dela."""
    id_ = uuid.uuid4()
    with banco.begin() as conexao:
        conexao.execute(
            sa.insert(auditoria).values(
                id=id_,
                ator_id=ator,
                acao=acao,
                alvo_id=alvo,
                detalhes=detalhes or {},
                criado_em=BEM_DEPOIS + timedelta(minutes=minutos),
            )
        )
    return str(id_)


def _evento(banco, id_, tipo, minutos=0):
    with banco.begin() as conexao:
        conexao.execute(
            sa.insert(eventos_stripe).values(
                id=id_, tipo=tipo, processado_em=BEM_DEPOIS + timedelta(minutes=minutos)
            )
        )


def _retrato(banco):
    """Quantas linhas há no que estas rotas leem: ler não pode gravar nada."""
    with banco.connect() as conexao:
        return tuple(
            conexao.execute(sa.select(sa.func.count()).select_from(tabela)).scalar_one()
            for tabela in (auditoria, eventos_stripe, usuarios)
        )


def _do_registro(rota) -> bool:
    return rota.endpoint.__module__ == rotas_do_registro.__name__


# --- quem entra ---------------------------------------------------------------------------


def test_as_rotas_do_registro_estao_no_router_unico_da_administracao():
    """Sem a importação em `administracao`, as rotas daqui não chegariam ao app."""
    assert rotas_do_registro.router is rotas_da_administracao.router
    assert rotas_da_administracao.administracao_registro is rotas_do_registro


def test_toda_rota_do_registro_exige_conta_admin_e_so_le():
    rotas = [
        rota for rota in rotas_da_administracao.router.routes if _do_registro(rota)
    ]
    assert {rota.path for rota in rotas} == set(ROTAS)  # type: ignore[attr-defined]
    for rota in rotas:
        dependencias = {d.call for d in rota.dependant.dependencies}  # type: ignore[attr-defined]
        assert rotas_da_administracao.conta_admin in dependencias, rota.path  # type: ignore[attr-defined]
        assert rota.methods == {"GET"}, rota.path  # type: ignore[attr-defined]


def test_sem_login_nada_do_registro_passa(banco, app, chefe):
    _gravar(banco, "plano_alterado", ator=chefe.id)
    anonimo = TestClient(app)
    for endereco in ROTAS:
        resposta = anonimo.get(endereco)
        assert resposta.status_code == 401, endereco
        assert "exemplo.com" not in resposta.text


def test_conta_comum_recebe_o_404_de_um_endereco_que_nao_existe(
    banco, app, chefe, carla
):
    _gravar(banco, "plano_alterado", ator=chefe.id, alvo=carla.id)
    _evento(banco, "evt_inventado_1", "invoice.paid")
    cliente = _cliente(banco, app, carla)
    inexistente = cliente.get("/v1/admin/nao-existe")
    assert inexistente.status_code == 404
    antes = _retrato(banco)
    for endereco in ROTAS:
        resposta = cliente.get(endereco)
        assert resposta.status_code == 404, endereco
        assert resposta.json() == inexistente.json(), endereco
        assert "exemplo.com" not in resposta.text
        assert "evt_inventado_1" not in resposta.text
    assert _retrato(banco) == antes


def test_as_rotas_do_registro_valem_tambem_no_prefixo_api(banco, app, chefe, carla):
    for endereco in ROTAS:
        assert TestClient(app).get("/api" + endereco).status_code == 401
        assert _cliente(banco, app, carla).get("/api" + endereco).status_code == 404, (
            endereco
        )
        assert _cliente(banco, app, chefe).get("/api" + endereco).status_code == 200, (
            endereco
        )


def test_quem_deixa_de_ser_admin_nao_le_no_pedido_seguinte(banco, app, chefe):
    cliente = _cliente(banco, app, chefe)  # a sessão continua aberta o teste inteiro
    for endereco in ROTAS:
        assert cliente.get(endereco).status_code == 200
    with banco.begin() as conexao:
        mudar_papel(conexao, chefe.id, "usuario")
    for endereco in ROTAS:
        assert cliente.get(endereco).status_code == 404, endereco


def test_admin_bloqueado_nao_le(banco, app, chefe):
    cliente = _cliente(banco, app, chefe)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(usuarios)
            .where(usuarios.c.id == chefe.id)
            .values(bloqueada_em=datetime.now(UTC), motivo_do_bloqueio="incidente")
        )
    for endereco in ROTAS:
        resposta = cliente.get(endereco)
        assert resposta.status_code in (401, 404), endereco
        assert "exemplo.com" not in resposta.text


def test_a_regra_recusa_de_novo_mesmo_se_a_dependencia_deixar_passar(
    banco, app, chefe, carla
):
    """A segunda tranca: a regra em `src/` confere o administrador na mesma conexão. Aqui a dependência
    é trocada por uma que deixa a conta comum passar; a resposta continua o 404, sem dado nenhum."""
    _gravar(banco, "plano_alterado", ator=chefe.id, alvo=carla.id)
    _evento(banco, "evt_inventado_1", "invoice.paid")
    app.dependency_overrides[rotas_da_administracao.conta_admin] = lambda: carla
    cliente = _cliente(banco, app, carla)
    inexistente = cliente.get("/v1/admin/nao-existe")
    for endereco in ROTAS:
        resposta = cliente.get(endereco)
        assert resposta.status_code == 404, endereco
        assert resposta.json() == inexistente.json(), endereco
        assert "exemplo.com" not in resposta.text


def test_a_conta_que_nao_aceitou_os_termos_nao_le(banco, app):
    with banco.begin() as conexao:
        usuario = entrar(conexao, "novato", "novato@exemplo.com", "Novato")[0]
        mudar_papel(conexao, usuario.id, "admin")
    cliente = _cliente(banco, app, usuario)
    for endereco in ROTAS:
        resposta = cliente.get(endereco)
        assert resposta.status_code == 403, endereco
        assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "termos"


def test_a_api_desligada_nao_tem_as_rotas_do_registro(monkeypatch, banco, chefe):
    monkeypatch.delenv(VARIAVEL_DA_CHAVE)
    desligada = TestClient(api.criar_app({}), headers=da_sessao(banco, chefe))
    for endereco in ROTAS:
        assert desligada.get(endereco).status_code == 404, endereco


def test_os_emails_das_contas_sao_so_para_o_administrador(banco, chefe, carla):
    """A regra, sem a rota: conta comum não lê e-mail de ninguém por ela, nem o próprio."""
    with banco.connect() as conexao:
        with pytest.raises(adm.PermissaoNegadaError):
            adm.emails_das_contas(conexao, carla.id, {carla.id, chefe.id})
        assert adm.emails_das_contas(conexao, chefe.id, set()) == {}
        assert adm.emails_das_contas(
            conexao, chefe.id, {carla.id, ALVO_QUE_NAO_E_CONTA}
        ) == {carla.id: "carla@exemplo.com"}


# --- o registro de ações ------------------------------------------------------------------


def test_admin_le_as_acoes_das_mais_novas_para_as_mais_antigas(
    banco, app, chefe, carla
):
    antiga = _gravar(
        banco,
        "plano_alterado",
        ator=chefe.id,
        alvo=carla.id,
        detalhes={"de": "gratuito", "para": "pro"},
        minutos=1,
    )
    nova = _gravar(
        banco,
        "chave_emitida",
        ator=chefe.id,
        alvo=ALVO_QUE_NAO_E_CONTA,
        detalhes={"finalidade": "analise"},
        minutos=2,
    )
    antes = _retrato(banco)
    resposta = _cliente(banco, app, chefe).get(REGISTRO)
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "no-store"
    dados = resposta.json()
    assert dados["cortado"] is False
    acoes = dados["acoes"]
    assert [acao["id"] for acao in acoes[:2]] == [nova, antiga]
    momentos = [datetime.fromisoformat(acao["quando"]) for acao in acoes]
    assert momentos == sorted(momentos, reverse=True)
    assert all(momento.utcoffset() == timedelta(0) for momento in momentos)
    assert momentos[0] == BEM_DEPOIS + timedelta(minutes=2)
    assert acoes[1] == {
        "id": antiga,
        "quando": acoes[1]["quando"],
        "acao": "plano_alterado",
        "ator_id": str(chefe.id),
        "ator_email": "chefe@exemplo.com",
        "alvo_id": str(carla.id),
        "alvo_email": "carla@exemplo.com",
        "foi_voce": True,
        "detalhes": {"de": "gratuito", "para": "pro"},
    }
    # o alvo que não é uma conta (uma chave, uma organização) sai só como id
    assert acoes[0]["alvo_id"] == str(ALVO_QUE_NAO_E_CONTA)
    assert acoes[0]["alvo_email"] is None
    assert acoes[0]["detalhes"] == {"finalidade": "analise"}
    assert _retrato(banco) == antes


def test_a_acao_de_outra_conta_nao_vem_marcada_como_sua(banco, app, chefe, carla):
    """O aceite dos termos é gravado pela própria conta: a da Carla não é ação de quem lê."""
    da_carla = _gravar(banco, "termos_aceitos", ator=carla.id, alvo=carla.id)
    acoes = _cliente(banco, app, chefe).get(REGISTRO).json()["acoes"]
    linha = next(acao for acao in acoes if acao["id"] == da_carla)
    assert linha["foi_voce"] is False
    assert linha["ator_email"] == "carla@exemplo.com"


def test_acao_sem_ator_e_de_conta_apagada_saem_sem_email(banco, app, chefe):
    """A conta apagada deixa a linha com o ator nulo (ou, no alvo, com um id que não é mais de ninguém):
    a resposta não inventa e-mail."""
    sem_ator = _gravar(banco, "conta_excluida", alvo=ALVO_QUE_NAO_E_CONTA)
    acoes = _cliente(banco, app, chefe).get(REGISTRO).json()["acoes"]
    linha = next(acao for acao in acoes if acao["id"] == sem_ator)
    assert linha["ator_id"] is None and linha["ator_email"] is None
    assert linha["alvo_id"] == str(ALVO_QUE_NAO_E_CONTA)
    assert linha["alvo_email"] is None
    assert linha["foi_voce"] is False
    assert linha["detalhes"] == {}


def test_o_registro_cortado_avisa_que_ha_acoes_mais_antigas(
    monkeypatch, banco, app, chefe
):
    ids = [
        _gravar(banco, "plano_alterado", ator=chefe.id, minutos=m) for m in (1, 2, 3)
    ]
    monkeypatch.setattr(rotas_do_registro, "LIMITE_DO_REGISTRO", 2)
    cliente = _cliente(banco, app, chefe)
    dados = cliente.get(REGISTRO).json()
    assert [acao["id"] for acao in dados["acoes"]] == [ids[2], ids[1]]
    assert dados["cortado"] is True
    monkeypatch.setattr(rotas_do_registro, "LIMITE_DO_REGISTRO", 100)
    inteiro = cliente.get(REGISTRO).json()
    assert inteiro["cortado"] is False
    assert {acao["id"] for acao in inteiro["acoes"]} >= set(ids)


def test_o_que_a_administracao_faz_aparece_no_registro(banco, app, chefe, carla):
    """De ponta a ponta: a mudança de plano feita pela rota das contas é a primeira linha do registro."""
    cliente = _cliente(banco, app, chefe)
    mudou = cliente.post(
        "/v1/admin/conta/plano", json={"id": str(carla.id), "plano": "plus"}
    )
    assert mudou.status_code == 204
    primeira = cliente.get(REGISTRO).json()["acoes"][0]
    assert primeira["acao"] == "plano_alterado"
    assert (primeira["foi_voce"], primeira["alvo_email"]) == (True, "carla@exemplo.com")
    assert primeira["detalhes"] == {"de": "gratuito", "para": "plus"}


def test_os_emails_do_registro_nao_vao_ao_log(banco, app, chefe, carla, caplog):
    _gravar(banco, "plano_alterado", ator=chefe.id, alvo=carla.id)
    _evento(banco, "evt_inventado_1", "invoice.paid")
    cliente = _cliente(banco, app, chefe)
    with caplog.at_level(logging.DEBUG):
        lido = cliente.get(REGISTRO)
        cliente.get(EVENTOS)
    assert "carla@exemplo.com" in lido.text
    assert "exemplo.com" not in caplog.text
    assert "carla" not in caplog.text.lower()


# --- os eventos do Stripe -----------------------------------------------------------------


def test_admin_le_os_eventos_do_stripe_dos_mais_novos_para_os_mais_antigos(
    banco, app, chefe
):
    _evento(banco, "evt_inventado_1", "checkout.session.completed", minutos=1)
    _evento(banco, "evt_inventado_2", "invoice.paid", minutos=2)
    antes = _retrato(banco)
    resposta = _cliente(banco, app, chefe).get(EVENTOS)
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "no-store"
    dados = resposta.json()
    assert dados["cortado"] is False
    assert [(e["id"], e["tipo"]) for e in dados["eventos"]] == [
        ("evt_inventado_2", "invoice.paid"),
        ("evt_inventado_1", "checkout.session.completed"),
    ]
    assert all(set(e) == {"id", "tipo", "processado_em"} for e in dados["eventos"])
    quando = datetime.fromisoformat(dados["eventos"][0]["processado_em"])
    assert quando == BEM_DEPOIS + timedelta(minutes=2)
    assert quando.utcoffset() == timedelta(0)
    assert _retrato(banco) == antes


def test_sem_evento_a_lista_vem_vazia(banco, app, chefe):
    assert _cliente(banco, app, chefe).get(EVENTOS).json() == {
        "eventos": [],
        "cortado": False,
    }


def test_a_lista_de_eventos_cortada_avisa(monkeypatch, banco, app, chefe):
    for numero in (1, 2, 3):
        _evento(banco, f"evt_inventado_{numero}", "invoice.paid", minutos=numero)
    monkeypatch.setattr(rotas_do_registro, "LIMITE_DE_EVENTOS", 2)
    dados = _cliente(banco, app, chefe).get(EVENTOS).json()
    assert [e["id"] for e in dados["eventos"]] == ["evt_inventado_3", "evt_inventado_2"]
    assert dados["cortado"] is True
