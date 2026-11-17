"""As rotas de leitura da Administração no app novo (src/api_v1/administracao.py, linha 955, PR 1).
As de escrita (PR 3) têm os testes em `tests/test_api_v1_administracao_escrita.py`.

Banco SQLite com as migrações. O que estes testes travam: quem é administrador se confere no servidor,
em toda rota e a cada pedido (conta comum recebe o 404 de um endereço que não existe; visitante, 401;
quem deixou de ser administrador perde o acesso no pedido seguinte); o painel de uma organização não
traz nada da outra; o valor de uma chave nunca sai numa leitura; e nenhuma destas rotas entra no
contrato público.
"""

import importlib
import pkgutil
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src import administracao_das_chaves as adc
from src import api
from src.api_externa import conjuntos as conjuntos_da_api
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso
from src.api_v1 import administracao as rotas_da_administracao
from src.api_v1.rotas import openapi_v1
from src.banco import chaves_da_api as cb
from src.banco import membros_da_organizacao as membros
from src.banco.modelo import usuarios
from src.banco.usuarios import entrar, mudar_papel
from src.conformidade import registrar_aceite
from tests.ajudantes_da_api import AGORA, da_sessao

HOJE = datetime.now(UTC).date()
LISTA = "/v1/admin/organizacoes"
PAINEL = "/v1/admin/organizacao"
ID_QUE_NAO_EXISTE = "00000000-0000-4000-8000-000000000000"
# o que a lista leva para os formulários da tela (PR 3)
OPCOES_DOS_FORMULARIOS = {
    "planos_da_api": [{"plano_da_api": "piloto", "nome_do_plano": "Piloto"}],
    "motivos_da_suspensao": [
        "contrato",
        "pagamento",
        "abuso",
        "pedido_do_cliente",
        "fonte",
    ],
}


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


def _conceder(banco, chefe, organizacao, conjunto, finalidade="analise"):
    with banco.begin() as conexao:
        cb.conceder_direito(
            conexao,
            organizacao_id=organizacao.id,
            conjunto=conjunto,
            finalidade=finalidade,
            vigente_desde=HOJE,
            ator_id=chefe.id,
        )


def _emitir(banco, chefe, organizacao):
    with banco.begin() as conexao:
        return adc.emitir_chave(conexao, chefe.id, organizacao.id)


def _leituras(organizacao_id):
    """Cada rota de leitura da Administração, como (endereço, parâmetros)."""
    return [(LISTA, None), (PAINEL, {"id": str(organizacao_id)})]


# --- quem entra ---------------------------------------------------------------------------


def test_toda_rota_da_administracao_exige_conta_admin():
    """Rota nova na Administração sem a conferência de administrador falha aqui, antes da produção."""
    rotas = rotas_da_administracao.router.routes
    assert rotas, "o router da Administração ficou sem rotas"
    for rota in rotas:
        dependencias = {d.call for d in rota.dependant.dependencies}  # type: ignore[attr-defined]
        assert rotas_da_administracao.conta_admin in dependencias, rota.path  # type: ignore[attr-defined]


def test_os_testes_de_acesso_cobrem_todas_as_rotas():
    """Rota de leitura nova precisa entrar em `_leituras`: é a lista que os testes de acesso percorrem
    (as de escrita têm a lista delas no arquivo de testes da escrita, e as das contas do app, que
    moram noutro módulo, no arquivo de testes das contas)."""
    cobertas = {endereco for endereco, _ in _leituras(ID_QUE_NAO_EXISTE)}
    existentes = {
        rota.path  # type: ignore[attr-defined]
        for rota in rotas_da_administracao.router.routes
        if "GET" in rota.methods  # type: ignore[attr-defined]
        and rota.endpoint.__module__ == rotas_da_administracao.__name__  # type: ignore[attr-defined]
    }
    assert cobertas == existentes


def test_nenhuma_rota_da_administracao_esta_no_contrato_publico():
    assert not [rota for rota in openapi_v1()["paths"] if "/admin" in rota]


def test_sem_login_a_administracao_responde_401(banco, app, chefe):
    organizacao = _organizacao(banco, chefe, "Alfa Gestora")
    anonimo = TestClient(app)
    for endereco, parametros in _leituras(organizacao.id):
        assert anonimo.get(endereco, params=parametros).status_code == 401, endereco


def test_conta_comum_recebe_o_404_de_um_endereco_que_nao_existe(
    banco, app, chefe, carla
):
    organizacao = _organizacao(banco, chefe, "Alfa Gestora")
    cliente = _cliente(banco, app, carla)
    inexistente = cliente.get("/v1/admin/nao-existe")
    assert inexistente.status_code == 404
    for endereco, parametros in _leituras(organizacao.id):
        resposta = cliente.get(endereco, params=parametros)
        assert resposta.status_code == 404, endereco
        assert resposta.json() == inexistente.json(), endereco
        assert "Alfa" not in resposta.text
    # a recusa vem antes de olhar o que foi pedido: id torto ou de organização nenhuma dá o mesmo 404
    for torto in ("nao-e-um-id", ID_QUE_NAO_EXISTE, ""):
        resposta = cliente.get(PAINEL, params={"id": torto})
        assert resposta.status_code == 404, torto
        assert resposta.json() == inexistente.json(), torto


def test_as_rotas_valem_tambem_no_prefixo_api(banco, app, chefe, carla):
    _organizacao(banco, chefe, "Alfa Gestora")
    assert _cliente(banco, app, chefe).get(f"/api{LISTA}").status_code == 200
    assert _cliente(banco, app, carla).get(f"/api{LISTA}").status_code == 404
    assert TestClient(app).get(f"/api{LISTA}").status_code == 401


def test_quem_deixa_de_ser_admin_perde_o_acesso_no_pedido_seguinte(banco, app, chefe):
    organizacao = _organizacao(banco, chefe, "Alfa Gestora")
    cliente = _cliente(banco, app, chefe)  # a sessão continua aberta o teste inteiro
    for endereco, parametros in _leituras(organizacao.id):
        assert cliente.get(endereco, params=parametros).status_code == 200, endereco
    with banco.begin() as conexao:
        mudar_papel(conexao, chefe.id, "usuario")
    for endereco, parametros in _leituras(organizacao.id):
        assert cliente.get(endereco, params=parametros).status_code == 404, endereco


def test_admin_bloqueado_nao_administra(banco, app, chefe):
    organizacao = _organizacao(banco, chefe, "Alfa Gestora")
    cliente = _cliente(banco, app, chefe)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(usuarios)
            .where(usuarios.c.id == chefe.id)
            .values(bloqueada_em=datetime.now(UTC), motivo_do_bloqueio="incidente")
        )
    for endereco, parametros in _leituras(organizacao.id):
        resposta = cliente.get(endereco, params=parametros)
        assert resposta.status_code in (401, 404), endereco
        assert "Alfa" not in resposta.text


def test_a_regra_recusa_de_novo_mesmo_se_a_dependencia_deixar_passar(
    banco, app, chefe, carla
):
    """A segunda tranca: a regra em `src/` confere o administrador na conexão da leitura. Aqui a
    dependência é trocada por uma que deixa a conta comum passar; a resposta continua o 404."""
    organizacao = _organizacao(banco, chefe, "Alfa Gestora")
    app.dependency_overrides[rotas_da_administracao.conta_admin] = lambda: carla
    cliente = _cliente(banco, app, carla)
    inexistente = cliente.get("/v1/admin/nao-existe")
    for endereco, parametros in _leituras(organizacao.id):
        resposta = cliente.get(endereco, params=parametros)
        assert resposta.status_code == 404, endereco
        assert resposta.json() == inexistente.json(), endereco
        assert "Alfa" not in resposta.text


def test_a_conta_que_nao_aceitou_os_termos_nao_administra(banco, app):
    with banco.begin() as conexao:
        usuario = entrar(conexao, "novato", "novato@exemplo.com", "Novato")[0]
        mudar_papel(conexao, usuario.id, "admin")
    resposta = _cliente(banco, app, usuario).get(LISTA)
    assert resposta.status_code == 403
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "termos"


def test_a_api_desligada_nao_tem_administracao(monkeypatch, banco, chefe):
    monkeypatch.delenv(VARIAVEL_DA_CHAVE)
    desligada = TestClient(api.criar_app({}), headers=da_sessao(banco, chefe))
    assert desligada.get(LISTA).status_code == 404


# --- a lista ------------------------------------------------------------------------------


def test_admin_lista_as_organizacoes_com_plano_e_situacao(banco, app, chefe):
    alfa = _organizacao(banco, chefe, "Alfa Gestora")
    beta = _organizacao(banco, chefe, "Beta Capital")
    with banco.begin() as conexao:
        adc.suspender_organizacao(conexao, chefe.id, beta.id, "pagamento")
    resposta = _cliente(banco, app, chefe).get(LISTA)
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "no-store"
    assert resposta.json() == {
        "organizacoes": [
            {
                "id": str(alfa.id),
                "nome": "Alfa Gestora",
                "plano_da_api": "piloto",
                "nome_do_plano": "Piloto",
                "suspensa": False,
            },
            {
                "id": str(beta.id),
                "nome": "Beta Capital",
                "plano_da_api": "piloto",
                "nome_do_plano": "Piloto",
                "suspensa": True,
            },
        ],
        **OPCOES_DOS_FORMULARIOS,
    }


def test_sem_organizacao_a_lista_vem_vazia(banco, app, chefe):
    assert _cliente(banco, app, chefe).get(LISTA).json() == {
        "organizacoes": [],
        **OPCOES_DOS_FORMULARIOS,
    }


# --- o painel -----------------------------------------------------------------------------


def test_o_painel_mostra_a_organizacao_de_relance(banco, app, chefe, carla):
    organizacao = _organizacao(banco, chefe, "Alfa Gestora")
    _conceder(banco, chefe, organizacao, "profiles")
    _conceder(banco, chefe, organizacao, "events")
    nova = _emitir(banco, chefe, organizacao)
    with banco.begin() as conexao:
        membros.vincular_membro(
            conexao,
            organizacao_id=organizacao.id,
            usuario_id=carla.id,
            ator_id=chefe.id,
        )
    resposta = _cliente(banco, app, chefe).get(
        PAINEL, params={"id": str(organizacao.id)}
    )
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "no-store"
    painel = resposta.json()
    assert painel["id"] == str(organizacao.id)
    assert (painel["nome"], painel["nome_do_plano"]) == ("Alfa Gestora", "Piloto")
    assert painel["suspensa_em"] is None and painel["motivo_da_suspensao"] is None
    assert painel["limites"] == {
        "pedidos_por_minuto": 60,
        "pedidos_por_mes": 10_000,
        "linhas_por_resposta": 1_000,
        "chaves_ativas": 3,
    }
    assert painel["consumo"] == {"pedidos": 0, "linhas": 0, "negados": 0}
    assert painel["chaves_ativas"] == 1
    assert [(c["id"], c["prefixo"], c["estado"]) for c in painel["chaves"]] == [
        (str(nova.chave_id), nova.prefixo, "ativa")
    ]
    assert [(d["conjunto"], d["finalidade"]) for d in painel["direitos"]] == [
        ("events", "analise"),
        ("profiles", "analise"),
    ]
    desligados = {
        (d["conjunto"], d["finalidade"]): d["motivo"] for d in painel["ainda_desligado"]
    }
    assert desligados[("links", "analise")] == "sem_contrato"
    assert desligados[("credit", "credito")] == "sem_contrato"
    # `research` confere o contrato fora das linhas do portão, e entra aqui do mesmo jeito
    assert desligados[("research", "analise")] == "sem_contrato"
    assert ("profiles", "analise") not in desligados
    assert ("events", "analise") not in desligados
    assert painel["pessoa_na_tela"] is False
    assert painel["membros"] == 1


def test_as_ofertas_do_painel_cobrem_todo_conjunto_que_a_api_por_chave_serve():
    """Conjunto novo em `src/api_externa/conjuntos/` sem linha no portão (como o `research`) precisa
    entrar em `OFERTAS_FORA_DO_PORTAO`, ou o painel nunca o mostraria como desligado."""
    modulos = [
        importlib.import_module(modulo.name)
        for modulo in pkgutil.iter_modules(
            conjuntos_da_api.__path__, f"{conjuntos_da_api.__name__}."
        )
    ]
    servidos = {m.CONJUNTO for m in modulos if hasattr(m, "CONJUNTO")}
    assert len(servidos) >= 13
    ofertas = adc.ofertas_da_api()
    assert {conjunto for conjunto, _ in ofertas} == servidos


def test_o_contrato_com_a_finalidade_trocada_aparece_como_desligado(banco, app, chefe):
    """Regressão da revisão cruzada do PR 1194: a API por chave confere o par conjunto e finalidade."""
    organizacao = _organizacao(banco, chefe, "Alfa Gestora")
    _conceder(banco, chefe, organizacao, "companies", "credito")
    _conceder(banco, chefe, organizacao, "credit", "analise")
    painel = (
        _cliente(banco, app, chefe)
        .get(PAINEL, params={"id": str(organizacao.id)})
        .json()
    )
    desligados = {(d["conjunto"], d["finalidade"]) for d in painel["ainda_desligado"]}
    assert {("companies", "analise"), ("credit", "credito")} <= desligados
    # o contrato aparece como está, com a finalidade que tem
    assert [(d["conjunto"], d["finalidade"]) for d in painel["direitos"]] == [
        ("companies", "credito"),
        ("credit", "analise"),
    ]


def test_o_research_sai_de_desligado_quando_o_contrato_o_liga(banco, app, chefe):
    organizacao = _organizacao(banco, chefe, "Alfa Gestora")
    _conceder(banco, chefe, organizacao, "research")
    painel = (
        _cliente(banco, app, chefe)
        .get(PAINEL, params={"id": str(organizacao.id)})
        .json()
    )
    desligados = {(d["conjunto"], d["finalidade"]) for d in painel["ainda_desligado"]}
    assert ("research", "analise") not in desligados


def test_o_painel_nunca_traz_o_valor_nem_o_hash_da_chave(banco, app, chefe, carla):
    organizacao = _organizacao(banco, chefe, "Alfa Gestora")
    nova = _emitir(banco, chefe, organizacao)
    with banco.begin() as conexao:
        membros.vincular_membro(
            conexao,
            organizacao_id=organizacao.id,
            usuario_id=carla.id,
            ator_id=chefe.id,
        )
    cliente = _cliente(banco, app, chefe)
    for endereco, parametros in _leituras(organizacao.id):
        texto = cliente.get(endereco, params=parametros).text
        assert nova.valor not in texto, endereco
        assert "hash" not in texto and "valor" not in texto, endereco
        # dos membros sai só o número: nem o id nem o e-mail da conta vinculada
        assert str(carla.id) not in texto and "carla" not in texto, endereco


def test_o_painel_mostra_a_suspensao_e_a_pessoa_na_tela(banco, app, chefe):
    organizacao = _organizacao(banco, chefe, "Alfa Gestora")
    _conceder(banco, chefe, organizacao, membros.CONJUNTO_DE_PESSOA_NA_TELA)
    with banco.begin() as conexao:
        adc.suspender_organizacao(conexao, chefe.id, organizacao.id, "pagamento")
    painel = (
        _cliente(banco, app, chefe)
        .get(PAINEL, params={"id": str(organizacao.id)})
        .json()
    )
    assert painel["suspensa_em"] is not None
    assert painel["motivo_da_suspensao"] == "pagamento"
    assert painel["pessoa_na_tela"] is True


def test_o_painel_de_uma_organizacao_nao_traz_nada_da_outra(banco, app, chefe):
    alfa = _organizacao(banco, chefe, "Alfa Gestora")
    beta = _organizacao(banco, chefe, "Beta Capital")
    _conceder(banco, chefe, alfa, "profiles")
    _conceder(banco, chefe, beta, "events")
    chave_da_alfa = _emitir(banco, chefe, alfa)
    chave_da_beta = _emitir(banco, chefe, beta)
    resposta = _cliente(banco, app, chefe).get(PAINEL, params={"id": str(alfa.id)})
    painel = resposta.json()
    assert [c["prefixo"] for c in painel["chaves"]] == [chave_da_alfa.prefixo]
    assert [d["conjunto"] for d in painel["direitos"]] == ["profiles"]
    assert chave_da_beta.prefixo not in resposta.text
    assert str(beta.id) not in resposta.text and "Beta" not in resposta.text


def test_organizacao_inexistente_ou_id_torto(banco, app, chefe):
    cliente = _cliente(banco, app, chefe)
    assert cliente.get(PAINEL, params={"id": ID_QUE_NAO_EXISTE}).status_code == 404
    assert cliente.get(PAINEL, params={"id": "nao-e-um-id"}).status_code == 422
    assert cliente.get(PAINEL).status_code == 422
