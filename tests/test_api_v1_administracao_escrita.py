"""As rotas de escrita da Administração no app novo (src/api_v1/administracao.py, linha 955, PR 3):
criar, suspender e reativar organização; emitir, rotacionar e revogar chave.

Banco SQLite com as migrações. O que estes testes travam: quem é administrador se confere no servidor,
em toda rota de escrita e antes de ler o corpo (conta comum recebe o 404 de um endereço que não existe e
nada muda; visitante, 401; pedido sem a prova de origem, 403); a chave de uma organização não se troca
nem se revoga pelo id de outra; e o valor de uma chave sai uma única vez, na resposta de quem emitiu ou
rotacionou: nunca numa leitura, num log ou na auditoria. Chaves, contas e organizações são inventadas.
"""

import logging
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src import administracao_das_chaves as adc
from src import api
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso
from src.api_v1 import administracao as rotas_da_administracao
from src.banco import chaves_da_api as cb
from src.banco.modelo import auditoria, chaves_da_api, organizacoes, usuarios
from src.banco.usuarios import entrar, mudar_papel
from src.chaves_da_api import hash_da_chave
from src.conformidade import registrar_aceite
from src.planos import limites_da_api
from tests.ajudantes_da_api import AGORA, da_sessao

LISTA = "/v1/admin/organizacoes"
PAINEL = "/v1/admin/organizacao"
CRIAR = "/v1/admin/organizacoes"
SUSPENDER = "/v1/admin/organizacao/suspender"
REATIVAR = "/v1/admin/organizacao/reativar"
EMITIR = "/v1/admin/chaves/emitir"
ROTACIONAR = "/v1/admin/chaves/rotacionar"
REVOGAR = "/v1/admin/chaves/revogar"
ID_QUE_NAO_EXISTE = "00000000-0000-4000-8000-000000000000"
CNPJ_INVENTADO = "11.222.333/0001-81"  # dígitos verificadores certos, empresa nenhuma
JSON_QUEBRADO = b'{"nome": '


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    acesso.LIMITE.zerar()


@pytest.fixture
def app():
    return api.criar_app({VARIAVEL_DA_CHAVE: "1"})


def _conta(banco, sub, *, admin):
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
    return _conta(banco, "carla", admin=False)


def _cliente(banco, app, usuario):
    return TestClient(app, headers=da_sessao(banco, usuario))


def _organizacao(banco, chefe, nome):
    with banco.begin() as conexao:
        return adc.criar_organizacao(
            conexao, chefe.id, nome=nome, cnpj=None, plano_da_api="piloto"
        )


def _emitir(banco, chefe, organizacao):
    with banco.begin() as conexao:
        return adc.emitir_chave(conexao, chefe.id, organizacao.id)


@pytest.fixture
def alfa(banco, chefe):
    return _organizacao(banco, chefe, "Alfa Gestora")


@pytest.fixture
def chave_da_alfa(banco, chefe, alfa):
    return _emitir(banco, chefe, alfa)


def _escritas(organizacao_id, chave_id):
    """Cada rota de escrita da Administração, como (endereço, corpo que valeria para um administrador)."""
    organizacao, chave = str(organizacao_id), str(chave_id)
    return [
        (CRIAR, {"nome": "Gama Partners", "cnpj": None, "plano_da_api": "piloto"}),
        (SUSPENDER, {"id": organizacao, "motivo": "pagamento"}),
        (REATIVAR, {"id": organizacao}),
        (EMITIR, {"organizacao_id": organizacao}),
        (ROTACIONAR, {"organizacao_id": organizacao, "chave_id": chave}),
        (REVOGAR, {"organizacao_id": organizacao, "chave_id": chave}),
    ]


def _retrato(banco):
    """O que as rotas de escrita mudam, para conferir que uma recusa não mudou nada."""
    with banco.connect() as conexao:
        return {
            "organizacoes": conexao.execute(
                sa.select(
                    organizacoes.c.id,
                    organizacoes.c.nome,
                    organizacoes.c.suspensa_em,
                    organizacoes.c.motivo_da_suspensao,
                ).order_by(organizacoes.c.id)
            ).all(),
            "chaves": conexao.execute(
                sa.select(
                    chaves_da_api.c.id,
                    chaves_da_api.c.organizacao_id,
                    chaves_da_api.c.revogada_em,
                    chaves_da_api.c.expira_em,
                ).order_by(chaves_da_api.c.id)
            ).all(),
            "auditoria": conexao.execute(
                sa.select(sa.func.count()).select_from(auditoria)
            ).scalar_one(),
        }


def _painel(cliente, organizacao_id):
    resposta = cliente.get(PAINEL, params={"id": str(organizacao_id)})
    assert resposta.status_code == 200
    return resposta.json()


def _estados(cliente, organizacao_id):
    return {
        chave["id"]: chave["estado"]
        for chave in _painel(cliente, organizacao_id)["chaves"]
    }


# --- quem entra ---------------------------------------------------------------------------


def test_os_testes_de_acesso_cobrem_todas_as_rotas_de_escrita():
    """Rota de escrita nova precisa entrar em `_escritas`: é a lista que os testes de acesso percorrem."""
    cobertas = {
        endereco for endereco, _ in _escritas(ID_QUE_NAO_EXISTE, ID_QUE_NAO_EXISTE)
    }
    existentes = {
        rota.path  # type: ignore[attr-defined]
        for rota in rotas_da_administracao.router.routes
        if "GET" not in rota.methods  # type: ignore[attr-defined]
    }
    assert cobertas == existentes


def test_toda_rota_de_escrita_e_post():
    for rota in rotas_da_administracao.router.routes:
        assert rota.methods in ({"GET"}, {"POST"}), rota.path  # type: ignore[attr-defined]


def test_sem_login_nenhuma_escrita_passa(banco, app, alfa, chave_da_alfa):
    antes = _retrato(banco)
    anonimo = TestClient(app)
    for endereco, corpo in _escritas(alfa.id, chave_da_alfa.chave_id):
        assert anonimo.post(endereco, json=corpo).status_code == 401, endereco
    assert _retrato(banco) == antes


def test_conta_comum_recebe_o_404_de_um_endereco_que_nao_existe_e_nada_muda(
    banco, app, carla, alfa, chave_da_alfa
):
    antes = _retrato(banco)
    cliente = _cliente(banco, app, carla)
    inexistente = cliente.post("/v1/admin/nao-existe", json={})
    assert inexistente.status_code == 404
    for endereco, corpo in _escritas(alfa.id, chave_da_alfa.chave_id):
        resposta = cliente.post(endereco, json=corpo)
        assert resposta.status_code == 404, endereco
        assert resposta.json() == inexistente.json(), endereco
        assert "Alfa" not in resposta.text
    assert _retrato(banco) == antes


def test_a_recusa_vem_antes_de_ler_o_corpo(banco, app, carla, alfa, chave_da_alfa):
    """Corpo torto, de organização nenhuma ou que nem é JSON: a conta comum recebe o mesmo 404."""
    cliente = _cliente(banco, app, carla)
    inexistente = cliente.post("/v1/admin/nao-existe", json={})
    for endereco, _ in _escritas(alfa.id, chave_da_alfa.chave_id):
        tortos = [
            cliente.post(endereco, json={"qualquer": "coisa"}),
            cliente.post(endereco, json={"id": ID_QUE_NAO_EXISTE}),
            cliente.post(endereco, json=["lista"]),
            cliente.post(
                endereco,
                content=JSON_QUEBRADO,
                headers={"Content-Type": "application/json"},
            ),
            cliente.post(endereco),
        ]
        for resposta in tortos:
            assert resposta.status_code == 404, endereco
            assert resposta.json() == inexistente.json(), endereco


def test_as_escritas_valem_tambem_no_prefixo_api(banco, app, chefe, carla, alfa):
    corpo = {"organizacao_id": str(alfa.id)}
    assert TestClient(app).post(f"/api{EMITIR}", json=corpo).status_code == 401
    assert (
        _cliente(banco, app, carla).post(f"/api{EMITIR}", json=corpo).status_code == 404
    )
    assert (
        _cliente(banco, app, chefe).post(f"/api{EMITIR}", json=corpo).status_code == 200
    )


def test_quem_deixa_de_ser_admin_nao_escreve_no_pedido_seguinte(
    banco, app, chefe, alfa, chave_da_alfa
):
    cliente = _cliente(banco, app, chefe)  # a sessão continua aberta o teste inteiro
    assert (
        cliente.post(EMITIR, json={"organizacao_id": str(alfa.id)}).status_code == 200
    )
    with banco.begin() as conexao:
        mudar_papel(conexao, chefe.id, "usuario")
    antes = _retrato(banco)
    for endereco, corpo in _escritas(alfa.id, chave_da_alfa.chave_id):
        assert cliente.post(endereco, json=corpo).status_code == 404, endereco
    assert _retrato(banco) == antes


def test_admin_bloqueado_nao_escreve(banco, app, chefe, alfa, chave_da_alfa):
    cliente = _cliente(banco, app, chefe)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(usuarios)
            .where(usuarios.c.id == chefe.id)
            .values(bloqueada_em=datetime.now(UTC), motivo_do_bloqueio="incidente")
        )
    antes = _retrato(banco)
    for endereco, corpo in _escritas(alfa.id, chave_da_alfa.chave_id):
        resposta = cliente.post(endereco, json=corpo)
        assert resposta.status_code in (401, 404), endereco
    assert _retrato(banco) == antes


def test_a_regra_recusa_de_novo_mesmo_se_a_dependencia_deixar_passar(
    banco, app, carla, alfa, chave_da_alfa
):
    """A segunda tranca: a regra em `src/` confere o administrador na transação da escrita. Aqui a
    dependência é trocada por uma que deixa a conta comum passar; a resposta continua o 404 e nada muda."""
    app.dependency_overrides[rotas_da_administracao.conta_admin] = lambda: carla
    cliente = _cliente(banco, app, carla)
    inexistente = cliente.post("/v1/admin/nao-existe", json={})
    antes = _retrato(banco)
    for endereco, corpo in _escritas(alfa.id, chave_da_alfa.chave_id):
        resposta = cliente.post(endereco, json=corpo)
        assert resposta.status_code == 404, endereco
        assert resposta.json() == inexistente.json(), endereco
    assert _retrato(banco) == antes


@pytest.mark.parametrize(
    "troca",
    [
        {"X-TickerLab-Pedido": None},  # sem o cabeçalho do app
        {"Origin": "https://outro-site.exemplo"},  # saiu de outro site
    ],
    ids=["sem-o-cabecalho-do-app", "de-outra-origem"],
)
def test_o_pedido_que_nao_saiu_do_app_e_recusado_mesmo_para_o_admin(
    banco, app, chefe, alfa, chave_da_alfa, troca
):
    """CSRF: o cookie da sessão sozinho não basta para escrever."""
    cabecalhos = {
        nome: valor
        for nome, valor in {**da_sessao(banco, chefe), **troca}.items()
        if valor is not None
    }
    cliente = TestClient(app, headers=cabecalhos)
    antes = _retrato(banco)
    for endereco, corpo in _escritas(alfa.id, chave_da_alfa.chave_id):
        resposta = cliente.post(endereco, json=corpo)
        assert resposta.status_code == 403, endereco
        assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "pedido-de-fora"
    assert _retrato(banco) == antes


def test_a_conta_que_nao_aceitou_os_termos_nao_escreve(banco, app, alfa):
    with banco.begin() as conexao:
        usuario = entrar(conexao, "novato", "novato@exemplo.com", "Novato")[0]
        mudar_papel(conexao, usuario.id, "admin")
    antes = _retrato(banco)
    resposta = _cliente(banco, app, usuario).post(
        EMITIR, json={"organizacao_id": str(alfa.id)}
    )
    assert resposta.status_code == 403
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "termos"
    assert _retrato(banco) == antes


def test_a_api_desligada_nao_tem_escrita(monkeypatch, banco, chefe, alfa):
    monkeypatch.delenv(VARIAVEL_DA_CHAVE)
    desligada = TestClient(api.criar_app({}), headers=da_sessao(banco, chefe))
    resposta = desligada.post(EMITIR, json={"organizacao_id": str(alfa.id)})
    assert resposta.status_code == 404


# --- criar organização --------------------------------------------------------------------


def test_admin_cria_a_organizacao(banco, app, chefe):
    cliente = _cliente(banco, app, chefe)
    resposta = cliente.post(
        CRIAR,
        json={
            "nome": "  Alfa Gestora  ",
            "cnpj": CNPJ_INVENTADO,
            "plano_da_api": "piloto",
        },
    )
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "no-store"
    criada = resposta.json()
    assert criada == {
        "id": criada["id"],
        "nome": "Alfa Gestora",
        "plano_da_api": "piloto",
        "nome_do_plano": "Piloto",
        "suspensa": False,
    }
    assert [o["id"] for o in cliente.get(LISTA).json()["organizacoes"]] == [
        criada["id"]
    ]
    painel = _painel(cliente, criada["id"])
    assert painel["cnpj"] == "11222333000181"
    assert painel["chaves"] == []
    with banco.connect() as conexao:
        registro = conexao.execute(
            sa.select(auditoria.c.ator_id).where(
                auditoria.c.alvo_id == uuid.UUID(criada["id"])
            )
        ).scalar_one()
    assert registro == chefe.id


def test_cnpj_vazio_ou_ausente_cria_a_organizacao_sem_cnpj(banco, app, chefe):
    cliente = _cliente(banco, app, chefe)
    for corpo in (
        {"nome": "Alfa Gestora", "cnpj": "", "plano_da_api": "piloto"},
        {"nome": "Beta Capital", "plano_da_api": "piloto"},
    ):
        resposta = cliente.post(CRIAR, json=corpo)
        assert resposta.status_code == 200, corpo
        assert _painel(cliente, resposta.json()["id"])["cnpj"] is None


@pytest.mark.parametrize(
    ("corpo", "status"),
    [
        ({"nome": "   ", "cnpj": None, "plano_da_api": "piloto"}, 422),
        ({"nome": "x" * 121, "cnpj": None, "plano_da_api": "piloto"}, 422),
        ({"nome": "Alfa", "cnpj": "11.222.333/0001-00", "plano_da_api": "piloto"}, 422),
        ({"nome": "Alfa", "cnpj": None, "plano_da_api": "ouro"}, 422),
        ({"nome": "Alfa", "cnpj": None}, 422),
        ({"cnpj": None, "plano_da_api": "piloto"}, 422),
        ({"nome": "Alfa", "plano_da_api": "piloto", "suspensa": True}, 422),
        (["lista"], 422),
    ],
)
def test_organizacao_invalida_nao_e_criada_e_o_erro_vem_em_frase(
    banco, app, chefe, corpo, status
):
    resposta = _cliente(banco, app, chefe).post(CRIAR, json=corpo)
    assert resposta.status_code == status
    assert isinstance(resposta.json()["detail"], str)  # o app novo mostra a frase
    assert _retrato(banco)["organizacoes"] == []


def test_json_quebrado_do_admin_da_422(banco, app, chefe):
    resposta = _cliente(banco, app, chefe).post(
        CRIAR, content=JSON_QUEBRADO, headers={"Content-Type": "application/json"}
    )
    assert resposta.status_code == 422
    assert isinstance(resposta.json()["detail"], str)


def test_cnpj_repetido_da_409_e_nao_cria(banco, app, chefe):
    cliente = _cliente(banco, app, chefe)
    corpo = {"nome": "Alfa Gestora", "cnpj": CNPJ_INVENTADO, "plano_da_api": "piloto"}
    assert cliente.post(CRIAR, json=corpo).status_code == 200
    repetida = cliente.post(CRIAR, json={**corpo, "nome": "Outra"})
    assert repetida.status_code == 409
    assert isinstance(repetida.json()["detail"], str)
    assert CNPJ_INVENTADO not in repetida.text and "11222333000181" not in repetida.text
    assert len(_retrato(banco)["organizacoes"]) == 1


def test_a_lista_traz_os_planos_e_os_motivos_para_os_formularios(banco, app, chefe):
    resposta = _cliente(banco, app, chefe).get(LISTA).json()
    assert resposta["planos_da_api"] == [
        {"plano_da_api": plano, "nome_do_plano": limites_da_api(plano).nome}
        for plano in cb.PLANOS_DA_API
    ]
    assert resposta["motivos_da_suspensao"] == list(cb.MOTIVOS_DA_SUSPENSAO)


# --- suspender e reativar -----------------------------------------------------------------


def test_admin_suspende_e_reativa_a_organizacao(banco, app, chefe, alfa):
    cliente = _cliente(banco, app, chefe)
    corpo = {"id": str(alfa.id), "motivo": "pagamento"}
    suspensa = cliente.post(SUSPENDER, json=corpo)
    assert suspensa.status_code == 200
    assert suspensa.json() == {"mudou": True}
    painel = _painel(cliente, alfa.id)
    assert painel["suspensa_em"] is not None
    assert painel["motivo_da_suspensao"] == "pagamento"
    # de novo: nada muda, e o motivo da primeira fica
    assert cliente.post(SUSPENDER, json={**corpo, "motivo": "abuso"}).json() == {
        "mudou": False
    }
    assert _painel(cliente, alfa.id)["motivo_da_suspensao"] == "pagamento"

    reativada = cliente.post(REATIVAR, json={"id": str(alfa.id)})
    assert reativada.status_code == 200
    assert reativada.json() == {"mudou": True}
    assert _painel(cliente, alfa.id)["suspensa_em"] is None
    assert cliente.post(REATIVAR, json={"id": str(alfa.id)}).json() == {"mudou": False}


def test_suspender_uma_organizacao_nao_toca_na_outra(banco, app, chefe, alfa):
    beta = _organizacao(banco, chefe, "Beta Capital")
    cliente = _cliente(banco, app, chefe)
    assert cliente.post(
        SUSPENDER, json={"id": str(alfa.id), "motivo": "contrato"}
    ).json() == {"mudou": True}
    assert _painel(cliente, beta.id)["suspensa_em"] is None


def test_motivo_fora_da_lista_nao_suspende(banco, app, chefe, alfa):
    cliente = _cliente(banco, app, chefe)
    for corpo in (
        {"id": str(alfa.id), "motivo": "porque sim"},
        {"id": str(alfa.id), "motivo": ""},
        {"id": str(alfa.id)},
    ):
        resposta = cliente.post(SUSPENDER, json=corpo)
        assert resposta.status_code == 422, corpo
        assert isinstance(resposta.json()["detail"], str)
    assert _painel(cliente, alfa.id)["suspensa_em"] is None


def test_suspender_ou_reativar_organizacao_inexistente_ou_de_id_torto(
    banco, app, chefe
):
    cliente = _cliente(banco, app, chefe)
    for endereco, extra in ((SUSPENDER, {"motivo": "contrato"}), (REATIVAR, {})):
        inexistente = cliente.post(endereco, json={"id": ID_QUE_NAO_EXISTE, **extra})
        assert inexistente.status_code == 404, endereco
        assert inexistente.json()["detail"] == "Organização inexistente."
        torto = cliente.post(endereco, json={"id": "nao-e-um-id", **extra})
        assert torto.status_code == 422, endereco


# --- emitir, rotacionar e revogar chave ---------------------------------------------------


def test_admin_emite_a_chave_e_o_valor_vem_so_nessa_resposta(banco, app, chefe, alfa):
    cliente = _cliente(banco, app, chefe)
    resposta = cliente.post(EMITIR, json={"organizacao_id": str(alfa.id)})
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "no-store"
    nova = resposta.json()
    assert set(nova) == {"id", "prefixo", "valor", "antiga_vale_por_dias"}
    assert nova["antiga_vale_por_dias"] is None
    assert nova["prefixo"] in nova["valor"]
    with banco.connect() as conexao:
        guardado = conexao.execute(
            sa.select(chaves_da_api.c.hash_da_chave).where(
                chaves_da_api.c.id == uuid.UUID(nova["id"])
            )
        ).scalar_one()
    assert guardado == hash_da_chave(
        nova["valor"]
    )  # o banco guarda o hash, não o valor
    # depois da emissão, nenhuma leitura traz o valor
    for leitura in (
        cliente.get(LISTA),
        cliente.get(PAINEL, params={"id": str(alfa.id)}),
    ):
        assert nova["valor"] not in leitura.text
        assert guardado not in leitura.text
    assert _estados(cliente, alfa.id) == {nova["id"]: "ativa"}


def test_o_valor_da_chave_nao_vai_ao_log_nem_a_auditoria(
    banco, app, chefe, alfa, caplog
):
    cliente = _cliente(banco, app, chefe)
    with caplog.at_level(logging.DEBUG):
        emitida = cliente.post(EMITIR, json={"organizacao_id": str(alfa.id)}).json()
        rotacionada = cliente.post(
            ROTACIONAR,
            json={"organizacao_id": str(alfa.id), "chave_id": emitida["id"]},
        ).json()
    with banco.connect() as conexao:
        registros = conexao.execute(sa.select(auditoria.c.detalhes)).all()
    gravado = caplog.text + repr(registros)
    for nova in (emitida, rotacionada):
        assert nova["valor"] not in gravado
        segredo = nova["valor"].split(nova["prefixo"] + "_", 1)[1]
        assert segredo and segredo not in gravado


def test_emitir_respeita_a_suspensao_e_o_limite_do_plano(banco, app, chefe, alfa):
    cliente = _cliente(banco, app, chefe)
    corpo = {"organizacao_id": str(alfa.id)}
    limite = limites_da_api("piloto").chaves_ativas
    for _ in range(limite):
        assert cliente.post(EMITIR, json=corpo).status_code == 200
    alem = cliente.post(EMITIR, json=corpo)
    assert alem.status_code == 409
    assert "chaves ativas" in alem.json()["detail"]
    assert "valor" not in alem.json()
    assert len(_retrato(banco)["chaves"]) == limite

    beta = _organizacao(banco, chefe, "Beta Capital")
    cliente.post(SUSPENDER, json={"id": str(beta.id), "motivo": "contrato"})
    suspensa = cliente.post(EMITIR, json={"organizacao_id": str(beta.id)})
    assert suspensa.status_code == 409
    assert suspensa.json()["detail"] == "A organização está suspensa."
    assert len(_retrato(banco)["chaves"]) == limite


def test_emitir_para_organizacao_inexistente_ou_de_id_torto(banco, app, chefe):
    cliente = _cliente(banco, app, chefe)
    inexistente = cliente.post(EMITIR, json={"organizacao_id": ID_QUE_NAO_EXISTE})
    assert inexistente.status_code == 404
    assert inexistente.json()["detail"] == "Organização inexistente."
    assert cliente.post(EMITIR, json={"organizacao_id": "torto"}).status_code == 422
    assert cliente.post(EMITIR, json={}).status_code == 422
    assert _retrato(banco)["chaves"] == []


def test_admin_rotaciona_a_chave_e_a_antiga_fica_de_saida(
    banco, app, chefe, alfa, chave_da_alfa
):
    cliente = _cliente(banco, app, chefe)
    corpo = {"organizacao_id": str(alfa.id), "chave_id": str(chave_da_alfa.chave_id)}
    resposta = cliente.post(ROTACIONAR, json=corpo)
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "no-store"
    nova = resposta.json()
    assert nova["antiga_vale_por_dias"] == cb.PRAZO_DA_ROTACAO.days
    assert nova["prefixo"] in nova["valor"]
    assert nova["valor"] != chave_da_alfa.valor
    assert _estados(cliente, alfa.id) == {
        str(chave_da_alfa.chave_id): "de_saida",
        nova["id"]: "ativa",
    }
    # a que já está de saída não gira de novo
    de_novo = cliente.post(ROTACIONAR, json=corpo)
    assert de_novo.status_code == 404
    assert "valor" not in de_novo.json()


def test_admin_revoga_a_chave(banco, app, chefe, alfa, chave_da_alfa):
    cliente = _cliente(banco, app, chefe)
    corpo = {"organizacao_id": str(alfa.id), "chave_id": str(chave_da_alfa.chave_id)}
    resposta = cliente.post(REVOGAR, json=corpo)
    assert resposta.status_code == 200
    assert resposta.json() == {"mudou": True}
    assert _estados(cliente, alfa.id) == {str(chave_da_alfa.chave_id): "revogada"}
    assert cliente.post(REVOGAR, json=corpo).status_code == 404  # já estava revogada


def test_a_chave_de_uma_organizacao_nao_se_troca_nem_se_revoga_pelo_id_de_outra(
    banco, app, chefe, alfa, chave_da_alfa
):
    """Duas organizações: com o id da Beta e a chave da Alfa, nada acontece, e a resposta é a mesma de
    uma chave que não existe."""
    beta = _organizacao(banco, chefe, "Beta Capital")
    chave_da_beta = _emitir(banco, chefe, beta)
    cliente = _cliente(banco, app, chefe)
    antes = _retrato(banco)
    cruzado = {"organizacao_id": str(beta.id), "chave_id": str(chave_da_alfa.chave_id)}
    fantasma = {"organizacao_id": str(beta.id), "chave_id": ID_QUE_NAO_EXISTE}
    for endereco in (ROTACIONAR, REVOGAR):
        resposta = cliente.post(endereco, json=cruzado)
        assert resposta.status_code == 404, endereco
        assert resposta.json() == cliente.post(endereco, json=fantasma).json()
        assert "valor" not in resposta.json()
    assert _retrato(banco) == antes
    assert _estados(cliente, alfa.id) == {str(chave_da_alfa.chave_id): "ativa"}
    assert _estados(cliente, beta.id) == {str(chave_da_beta.chave_id): "ativa"}


def test_rotacionar_ou_revogar_com_id_torto_ou_faltando(
    banco, app, chefe, alfa, chave_da_alfa
):
    cliente = _cliente(banco, app, chefe)
    antes = _retrato(banco)
    for endereco in (ROTACIONAR, REVOGAR):
        for corpo in (
            {"organizacao_id": str(alfa.id)},
            {"chave_id": str(chave_da_alfa.chave_id)},
            {"organizacao_id": str(alfa.id), "chave_id": "torta"},
        ):
            resposta = cliente.post(endereco, json=corpo)
            assert resposta.status_code == 422, (endereco, corpo)
            assert isinstance(resposta.json()["detail"], str)
        inexistente = cliente.post(
            endereco,
            json={
                "organizacao_id": ID_QUE_NAO_EXISTE,
                "chave_id": str(chave_da_alfa.chave_id),
            },
        )
        assert inexistente.status_code == 404, endereco
    assert _retrato(banco) == antes


def test_rotacionar_numa_organizacao_suspensa_da_409(
    banco, app, chefe, alfa, chave_da_alfa
):
    cliente = _cliente(banco, app, chefe)
    cliente.post(SUSPENDER, json={"id": str(alfa.id), "motivo": "contrato"})
    resposta = cliente.post(
        ROTACIONAR,
        json={"organizacao_id": str(alfa.id), "chave_id": str(chave_da_alfa.chave_id)},
    )
    assert resposta.status_code == 409
    assert "valor" not in resposta.json()
    # revogar continua valendo com a organização suspensa
    assert cliente.post(
        REVOGAR,
        json={"organizacao_id": str(alfa.id), "chave_id": str(chave_da_alfa.chave_id)},
    ).json() == {"mudou": True}
