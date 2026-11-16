"""As rotas das contas do app na Administração do app novo (src/api_v1/administracao_contas.py, linha
955, PR 4): os números do serviço, a busca de contas e mudar plano, mudar papel, bloquear e desbloquear.

Banco SQLite com as migrações. O que estes testes travam: quem é administrador se confere no servidor, em
toda rota e antes de ler o corpo (conta comum recebe o 404 de um endereço que não existe e nada muda;
visitante, 401; pedido sem a prova de origem, 403); as travas da regra chegam com a frase dela (ninguém
tira o próprio acesso nem bloqueia a si mesmo, e quem está na lista de administradores do servidor não é
rebaixado nem bloqueado por aqui); mexer numa conta não toca na outra; e o termo da busca, o e-mail e o
nome não vão para o endereço nem para o log. Contas inventadas, todas em `exemplo.com`.
"""

import logging
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src import api
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso
from src.api_v1 import administracao as rotas_da_administracao
from src.api_v1 import administracao_contas as rotas_das_contas
from src.autenticacao import VARIAVEL_DOS_ADMINS
from src.banco.modelo import (
    MOTIVOS_DO_BLOQUEIO,
    PAPEIS,
    PLANOS,
    auditoria,
    sessoes_de_login,
    usuarios,
)
from src.banco.usuarios import entrar, mudar_papel
from src.conformidade import registrar_aceite
from tests.ajudantes_da_api import AGORA, da_sessao

RESUMO = "/v1/admin/resumo"
BUSCAR = "/v1/admin/contas/buscar"
PLANO = "/v1/admin/conta/plano"
PAPEL = "/v1/admin/conta/papel"
BLOQUEAR = "/v1/admin/conta/bloquear"
DESBLOQUEAR = "/v1/admin/conta/desbloquear"
ID_QUE_NAO_EXISTE = "00000000-0000-4000-8000-000000000000"
JSON_QUEBRADO = b'{"id": '
CONTA_INEXISTENTE = "Usuário não encontrado."
A_MINHA_CONTA = (
    "/v1/eu"  # uma leitura qualquer da conta logada: diz se a sessão ainda vale
)


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


@pytest.fixture
def bia(banco):
    """Outra conta comum: o que se faz com a Carla não pode tocar nela."""
    return _conta(banco, "bia")


def _cliente(banco, app, usuario):
    return TestClient(app, headers=da_sessao(banco, usuario))


def _pedidos(alvo_id):
    """Cada rota das contas, como (método, endereço, corpo que valeria para um administrador)."""
    alvo = str(alvo_id)
    return [
        ("GET", RESUMO, None),
        ("POST", BUSCAR, {"busca": ""}),
        ("POST", PLANO, {"id": alvo, "plano": "pro"}),
        ("POST", PAPEL, {"id": alvo, "papel": "admin"}),
        ("POST", BLOQUEAR, {"id": alvo, "motivo": "incidente"}),
        ("POST", DESBLOQUEAR, {"id": alvo}),
    ]


def _escritas(alvo_id):
    return [pedido for pedido in _pedidos(alvo_id) if pedido[0] == "POST"]


def _pedir(cliente, metodo, endereco, corpo, prefixo=""):
    if metodo == "GET":
        return cliente.get(prefixo + endereco)
    return cliente.post(prefixo + endereco, json=corpo)


def _retrato(banco):
    """O que as rotas das contas mudam, para conferir que uma recusa não mudou nada."""
    with banco.connect() as conexao:
        return {
            "contas": conexao.execute(
                sa.select(
                    usuarios.c.id,
                    usuarios.c.plano,
                    usuarios.c.papel,
                    usuarios.c.bloqueada_em,
                    usuarios.c.motivo_do_bloqueio,
                ).order_by(usuarios.c.id)
            ).all(),
            "sessoes": conexao.execute(
                sa.select(
                    sessoes_de_login.c.id, sessoes_de_login.c.encerrada_em
                ).order_by(sessoes_de_login.c.id)
            ).all(),
            "auditoria": conexao.execute(
                sa.select(sa.func.count()).select_from(auditoria)
            ).scalar_one(),
        }


def _da_conta(banco, usuario):
    with banco.connect() as conexao:
        return conexao.execute(
            sa.select(
                usuarios.c.plano,
                usuarios.c.papel,
                usuarios.c.bloqueada_em,
                usuarios.c.motivo_do_bloqueio,
            ).where(usuarios.c.id == usuario.id)
        ).one()


def _registro(banco, acao):
    """A linha da auditoria com esta ação: tem de ser uma só."""
    with banco.connect() as conexao:
        return conexao.execute(
            sa.select(
                auditoria.c.ator_id,
                auditoria.c.acao,
                auditoria.c.alvo_id,
                auditoria.c.detalhes,
            ).where(auditoria.c.acao == acao)
        ).one()


def _das_contas(rota) -> bool:
    return rota.endpoint.__module__ == rotas_das_contas.__name__


# --- quem entra ---------------------------------------------------------------------------


def test_as_rotas_das_contas_estao_no_router_unico_da_administracao():
    """As contas não têm router próprio: usam o da Administração, que o app recebe de `administracao`
    (é esse módulo que importa o das contas; sem a importação, as rotas não chegariam ao app)."""
    assert rotas_das_contas.router is rotas_da_administracao.router
    assert rotas_da_administracao.administracao_contas is rotas_das_contas


def test_toda_rota_das_contas_exige_conta_admin():
    rotas = [rota for rota in rotas_da_administracao.router.routes if _das_contas(rota)]
    assert rotas, "a Administração ficou sem as rotas das contas"
    for rota in rotas:
        dependencias = {d.call for d in rota.dependant.dependencies}  # type: ignore[attr-defined]
        assert rotas_da_administracao.conta_admin in dependencias, rota.path  # type: ignore[attr-defined]


def test_os_testes_de_acesso_cobrem_todas_as_rotas_das_contas():
    """Rota nova das contas precisa entrar em `_pedidos`: é a lista que os testes de acesso percorrem."""
    cobertas = {
        (metodo, endereco) for metodo, endereco, _ in _pedidos(ID_QUE_NAO_EXISTE)
    }
    existentes = {
        (metodo, rota.path)  # type: ignore[attr-defined]
        for rota in rotas_da_administracao.router.routes
        if _das_contas(rota)
        for metodo in rota.methods  # type: ignore[attr-defined]
    }
    assert cobertas == existentes


def test_toda_rota_da_administracao_e_de_um_modulo_com_testes_de_acesso():
    """Um terceiro módulo de rotas não entra no router da Administração sem os testes de acesso dele."""
    conhecidos = {rotas_da_administracao.__name__, rotas_das_contas.__name__}
    for rota in rotas_da_administracao.router.routes:
        assert rota.endpoint.__module__ in conhecidos, rota.path  # type: ignore[attr-defined]


def test_sem_login_nada_das_contas_passa(banco, app, carla):
    antes = _retrato(banco)
    anonimo = TestClient(app)
    for metodo, endereco, corpo in _pedidos(carla.id):
        assert _pedir(anonimo, metodo, endereco, corpo).status_code == 401, endereco
    assert _retrato(banco) == antes


def test_conta_comum_recebe_o_404_de_um_endereco_que_nao_existe_e_nada_muda(
    banco, app, carla, bia
):
    cliente = _cliente(banco, app, carla)
    antes = _retrato(banco)
    for metodo, endereco, corpo in _pedidos(bia.id):
        inexistente = _pedir(cliente, metodo, "/v1/admin/nao-existe", corpo)
        assert inexistente.status_code == 404
        resposta = _pedir(cliente, metodo, endereco, corpo)
        assert resposta.status_code == 404, endereco
        assert resposta.json() == inexistente.json(), endereco
        assert "exemplo.com" not in resposta.text
    assert _retrato(banco) == antes


def test_a_conta_comum_nao_muda_nem_a_propria_conta(banco, app, carla):
    cliente = _cliente(banco, app, carla)
    antes = _retrato(banco)
    for _, endereco, corpo in _escritas(carla.id):
        assert cliente.post(endereco, json=corpo).status_code == 404, endereco
    assert _retrato(banco) == antes


def test_a_recusa_vem_antes_de_ler_o_corpo(banco, app, carla, bia):
    """Corpo torto, de conta nenhuma ou que nem é JSON: a conta comum recebe o mesmo 404."""
    cliente = _cliente(banco, app, carla)
    inexistente = cliente.post("/v1/admin/nao-existe", json={})
    for _, endereco, _corpo in _escritas(bia.id):
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


def test_as_rotas_das_contas_valem_tambem_no_prefixo_api(banco, app, chefe, carla):
    for metodo, endereco, corpo in _pedidos(carla.id)[:2]:
        assert (
            _pedir(TestClient(app), metodo, endereco, corpo, "/api").status_code == 401
        )
        comum = _pedir(_cliente(banco, app, carla), metodo, endereco, corpo, "/api")
        assert comum.status_code == 404, endereco
        admin = _pedir(_cliente(banco, app, chefe), metodo, endereco, corpo, "/api")
        assert admin.status_code == 200, endereco


def test_quem_deixa_de_ser_admin_nao_entra_no_pedido_seguinte(banco, app, chefe, carla):
    cliente = _cliente(banco, app, chefe)  # a sessão continua aberta o teste inteiro
    assert cliente.get(RESUMO).status_code == 200
    with banco.begin() as conexao:
        mudar_papel(conexao, chefe.id, "usuario")
    antes = _retrato(banco)
    for metodo, endereco, corpo in _pedidos(carla.id):
        assert _pedir(cliente, metodo, endereco, corpo).status_code == 404, endereco
    assert _retrato(banco) == antes


def test_admin_bloqueado_nao_entra(banco, app, chefe, carla):
    cliente = _cliente(banco, app, chefe)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(usuarios)
            .where(usuarios.c.id == chefe.id)
            .values(bloqueada_em=datetime.now(UTC), motivo_do_bloqueio="incidente")
        )
    antes = _retrato(banco)
    for metodo, endereco, corpo in _pedidos(carla.id):
        resposta = _pedir(cliente, metodo, endereco, corpo)
        assert resposta.status_code in (401, 404), endereco
    assert _retrato(banco) == antes


def test_a_regra_recusa_de_novo_mesmo_se_a_dependencia_deixar_passar(
    banco, app, carla, bia
):
    """A segunda tranca: a regra em `src/` confere o administrador na mesma conexão. Aqui a dependência
    é trocada por uma que deixa a conta comum passar; a resposta continua o 404 e nada muda."""
    app.dependency_overrides[rotas_da_administracao.conta_admin] = lambda: carla
    cliente = _cliente(banco, app, carla)
    antes = _retrato(banco)
    for metodo, endereco, corpo in _pedidos(bia.id):
        inexistente = _pedir(cliente, metodo, "/v1/admin/nao-existe", corpo)
        resposta = _pedir(cliente, metodo, endereco, corpo)
        assert resposta.status_code == 404, endereco
        assert resposta.json() == inexistente.json(), endereco
        assert "exemplo.com" not in resposta.text
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
    banco, app, chefe, carla, troca
):
    """CSRF: o cookie da sessão sozinho não basta para mudar uma conta nem para buscar contas."""
    cabecalhos = {
        nome: valor
        for nome, valor in {**da_sessao(banco, chefe), **troca}.items()
        if valor is not None
    }
    cliente = TestClient(app, headers=cabecalhos)
    antes = _retrato(banco)
    for _, endereco, corpo in _escritas(carla.id):
        resposta = cliente.post(endereco, json=corpo)
        assert resposta.status_code == 403, endereco
        assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "pedido-de-fora"
        assert "exemplo.com" not in resposta.text
    assert _retrato(banco) == antes


def test_a_conta_que_nao_aceitou_os_termos_nao_entra(banco, app, carla):
    with banco.begin() as conexao:
        usuario = entrar(conexao, "novato", "novato@exemplo.com", "Novato")[0]
        mudar_papel(conexao, usuario.id, "admin")
    cliente = _cliente(banco, app, usuario)
    antes = _retrato(banco)
    for metodo, endereco, corpo in _pedidos(carla.id):
        resposta = _pedir(cliente, metodo, endereco, corpo)
        assert resposta.status_code == 403, endereco
        assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "termos"
    assert _retrato(banco) == antes


def test_a_api_desligada_nao_tem_as_rotas_das_contas(monkeypatch, banco, chefe, carla):
    monkeypatch.delenv(VARIAVEL_DA_CHAVE)
    desligada = TestClient(api.criar_app({}), headers=da_sessao(banco, chefe))
    for metodo, endereco, corpo in _pedidos(carla.id):
        assert _pedir(desligada, metodo, endereco, corpo).status_code == 404, endereco


# --- os números do serviço ----------------------------------------------------------------


def test_admin_ve_os_numeros_do_servico(banco, app, chefe, carla, bia):
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(usuarios).where(usuarios.c.id == bia.id).values(plano="pro")
        )
    resposta = _cliente(banco, app, chefe).get(RESUMO)
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "no-store"
    assert resposta.json() == {
        "usuarios": 3,
        "gratuito": 2,
        "plus": 0,
        "pro": 1,
        "administradores": 1,
        "novos_na_semana": 3,
        "ativos_na_semana": 3,
        "simulacoes": 0,
        "assinaturas_ativas": 0,
        "eventos_do_stripe": 0,
    }


# --- buscar contas ------------------------------------------------------------------------


def _buscar(cliente, busca=""):
    resposta = cliente.post(BUSCAR, json={"busca": busca})
    assert resposta.status_code == 200
    return resposta.json()


def test_admin_lista_as_contas_com_o_que_a_tela_mostra(banco, app, chefe, carla):
    resposta = _cliente(banco, app, chefe).post(BUSCAR, json={})
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "no-store"
    dados = resposta.json()
    assert dados["cortada"] is False
    assert dados["planos"] == list(PLANOS)
    assert dados["papeis"] == list(PAPEIS)
    assert dados["motivos_do_bloqueio"] == list(MOTIVOS_DO_BLOQUEIO)
    por_email = {conta["email"]: conta for conta in dados["contas"]}
    assert set(por_email) == {"chefe@exemplo.com", "carla@exemplo.com"}
    da_carla = por_email["carla@exemplo.com"]
    assert set(da_carla) == {
        "id",
        "email",
        "nome",
        "papel",
        "plano",
        "criado_em",
        "ultimo_acesso",
        "status_da_assinatura",
        "simulacoes",
        "bloqueada_em",
        "motivo_do_bloqueio",
        "e_voce",
    }
    assert da_carla["id"] == str(carla.id)
    assert (da_carla["nome"], da_carla["papel"], da_carla["plano"]) == (
        "Carla",
        "usuario",
        "gratuito",
    )
    assert da_carla["status_da_assinatura"] is None and da_carla["simulacoes"] == 0
    assert da_carla["bloqueada_em"] is None and da_carla["motivo_do_bloqueio"] is None
    # a própria linha vem marcada: a tela não oferece a quem a vê tirar o próprio acesso
    assert da_carla["e_voce"] is False
    assert por_email["chefe@exemplo.com"]["e_voce"] is True
    assert por_email["chefe@exemplo.com"]["papel"] == "admin"


def test_a_busca_acha_por_parte_do_email_ou_do_nome_sem_diferenca_de_maiusculas(
    banco, app, chefe, carla, bia
):
    cliente = _cliente(banco, app, chefe)
    assert [c["email"] for c in _buscar(cliente, "CARLA@")["contas"]] == [
        "carla@exemplo.com"
    ]
    assert [c["email"] for c in _buscar(cliente, "  bia ")["contas"]] == [
        "bia@exemplo.com"
    ]
    assert len(_buscar(cliente, "exemplo.com")["contas"]) == 3
    assert _buscar(cliente, "ninguem")["contas"] == []


def test_os_curingas_da_busca_valem_como_texto(banco, app, chefe, carla):
    cliente = _cliente(banco, app, chefe)
    assert _buscar(cliente, "%")["contas"] == []
    assert _buscar(cliente, "c_rla")["contas"] == []


def test_a_lista_cortada_avisa_que_ha_mais(monkeypatch, banco, app, chefe, carla, bia):
    monkeypatch.setattr(rotas_das_contas, "LIMITE_DE_CONTAS", 2)
    dados = _buscar(_cliente(banco, app, chefe))
    assert len(dados["contas"]) == 2
    assert dados["cortada"] is True
    monkeypatch.setattr(rotas_das_contas, "LIMITE_DE_CONTAS", 3)
    inteira = _buscar(_cliente(banco, app, chefe))
    assert len(inteira["contas"]) == 3
    assert inteira["cortada"] is False


def test_a_conta_bloqueada_aparece_com_a_data_e_o_motivo(banco, app, chefe, carla):
    cliente = _cliente(banco, app, chefe)
    assert (
        cliente.post(
            BLOQUEAR, json={"id": str(carla.id), "motivo": "abuso"}
        ).status_code
        == 200
    )
    da_carla = _buscar(cliente, "carla")["contas"][0]
    assert da_carla["bloqueada_em"] is not None
    assert da_carla["motivo_do_bloqueio"] == "abuso"


@pytest.mark.parametrize(
    "corpo",
    [
        {"busca": "carla", "limite": 100000},  # campo a mais
        {"busca": 7},
        {"busca": "x" * 201},
        ["lista"],
    ],
    ids=["campo-a-mais", "busca-que-nao-e-texto", "busca-longa-demais", "lista"],
)
def test_busca_torta_do_admin_da_422_sem_repetir_o_que_veio(banco, app, chefe, corpo):
    resposta = _cliente(banco, app, chefe).post(BUSCAR, json=corpo)
    assert resposta.status_code == 422
    assert isinstance(resposta.json()["detail"], str)
    assert "carla" not in resposta.text and "100000" not in resposta.text


def test_json_quebrado_do_admin_da_422(banco, app, chefe):
    resposta = _cliente(banco, app, chefe).post(
        BUSCAR, content=JSON_QUEBRADO, headers={"Content-Type": "application/json"}
    )
    assert resposta.status_code == 422
    assert isinstance(resposta.json()["detail"], str)


def test_o_termo_da_busca_o_email_e_o_nome_nao_vao_ao_log(
    banco, app, chefe, carla, caplog
):
    cliente = _cliente(banco, app, chefe)
    with caplog.at_level(logging.DEBUG):
        achadas = _buscar(cliente, "carla@exemplo")["contas"]
        assert (
            cliente.post(PLANO, json={"id": str(carla.id), "plano": "plus"}).status_code
            == 204
        )
        cliente.post(BLOQUEAR, json={"id": str(carla.id), "motivo": "abuso"})
        cliente.post(BLOQUEAR, json={"id": str(carla.id), "motivo": "abuso"})  # 409
    assert [conta["email"] for conta in achadas] == ["carla@exemplo.com"]
    assert "carla" not in caplog.text.lower()
    assert "exemplo.com" not in caplog.text


# --- mudar o plano ------------------------------------------------------------------------


def test_admin_muda_o_plano_e_fica_no_registro(banco, app, chefe, carla, bia):
    resposta = _cliente(banco, app, chefe).post(
        PLANO, json={"id": str(carla.id), "plano": "pro"}
    )
    assert resposta.status_code == 204
    assert resposta.headers["Cache-Control"] == "no-store"
    assert resposta.content == b""
    assert _da_conta(banco, carla).plano == "pro"
    assert _da_conta(banco, bia).plano == "gratuito"
    registro = _registro(banco, "plano_alterado")
    assert (registro.ator_id, registro.acao, registro.alvo_id) == (
        chefe.id,
        "plano_alterado",
        carla.id,
    )
    assert registro.detalhes == {"de": "gratuito", "para": "pro"}


@pytest.mark.parametrize(
    "corpo",
    [
        {"id": "{carla}", "plano": "diamante"},
        {"id": "{carla}"},
        {"id": "torto", "plano": "pro"},
        {"id": "{carla}", "plano": "pro", "papel": "admin"},  # campo a mais
    ],
    ids=["plano-fora-da-lista", "sem-plano", "id-torto", "campo-a-mais"],
)
def test_pedido_torto_de_plano_da_422_e_nada_muda(banco, app, chefe, carla, corpo):
    cliente = _cliente(banco, app, chefe)
    antes = _retrato(banco)
    corpo = {
        campo: str(carla.id) if valor == "{carla}" else valor
        for campo, valor in corpo.items()
    }
    resposta = cliente.post(PLANO, json=corpo)
    assert resposta.status_code == 422
    assert isinstance(resposta.json()["detail"], str)
    assert "diamante" not in resposta.text
    assert _retrato(banco) == antes


def test_conta_que_nao_existe_da_404_com_a_frase_em_toda_mudanca(banco, app, chefe):
    cliente = _cliente(banco, app, chefe)
    antes = _retrato(banco)
    for _, endereco, corpo in _escritas(ID_QUE_NAO_EXISTE):
        if endereco == BUSCAR:
            continue
        resposta = cliente.post(endereco, json=corpo)
        assert resposta.status_code == 404, endereco
        assert resposta.json()["detail"] == CONTA_INEXISTENTE, endereco
    assert _retrato(banco) == antes


# --- mudar o papel ------------------------------------------------------------------------


def test_admin_promove_e_rebaixa_outra_conta(banco, app, chefe, carla, bia):
    cliente = _cliente(banco, app, chefe)
    promovida = cliente.post(PAPEL, json={"id": str(carla.id), "papel": "admin"})
    assert promovida.status_code == 204
    assert promovida.headers["Cache-Control"] == "no-store"
    assert _da_conta(banco, carla).papel == "admin"
    assert _da_conta(banco, bia).papel == "usuario"
    registro = _registro(banco, "papel_alterado")
    assert (registro.ator_id, registro.acao, registro.alvo_id) == (
        chefe.id,
        "papel_alterado",
        carla.id,
    )
    assert registro.detalhes == {"de": "usuario", "para": "admin"}
    assert (
        cliente.post(PAPEL, json={"id": str(carla.id), "papel": "usuario"}).status_code
        == 204
    )
    assert _da_conta(banco, carla).papel == "usuario"


def test_ninguem_tira_o_proprio_acesso_de_administrador(banco, app, chefe, carla):
    cliente = _cliente(banco, app, chefe)
    antes = _retrato(banco)
    resposta = cliente.post(PAPEL, json={"id": str(chefe.id), "papel": "usuario"})
    assert resposta.status_code == 409
    assert "próprio acesso" in resposta.json()["detail"]
    assert _retrato(banco) == antes
    assert cliente.get(RESUMO).status_code == 200


def test_quem_esta_na_lista_do_servidor_nao_e_rebaixado_por_aqui(
    monkeypatch, banco, app, chefe, bia
):
    with banco.begin() as conexao:
        mudar_papel(conexao, bia.id, "admin")
    monkeypatch.setenv(VARIAVEL_DOS_ADMINS, "Bia@Exemplo.com")
    cliente = _cliente(banco, app, chefe)
    antes = _retrato(banco)
    resposta = cliente.post(PAPEL, json={"id": str(bia.id), "papel": "usuario"})
    assert resposta.status_code == 409
    assert VARIAVEL_DOS_ADMINS in resposta.json()["detail"]
    assert "exemplo.com" not in resposta.text.lower()
    assert _retrato(banco) == antes


def test_papel_fora_da_lista_da_422_e_nada_muda(banco, app, chefe, carla):
    cliente = _cliente(banco, app, chefe)
    antes = _retrato(banco)
    resposta = cliente.post(PAPEL, json={"id": str(carla.id), "papel": "dono"})
    assert resposta.status_code == 422
    assert "dono" not in resposta.text
    assert _retrato(banco) == antes


# --- bloquear e desbloquear ---------------------------------------------------------------


def test_admin_bloqueia_a_conta_e_as_sessoes_dela_caem_na_hora(
    banco, app, chefe, carla, bia
):
    da_carla = _cliente(banco, app, carla)
    da_bia = _cliente(banco, app, bia)
    assert da_carla.get(A_MINHA_CONTA).status_code == 200
    resposta = _cliente(banco, app, chefe).post(
        BLOQUEAR, json={"id": str(carla.id), "motivo": "acesso_de_terceiro"}
    )
    assert resposta.status_code == 200
    assert resposta.headers["Cache-Control"] == "no-store"
    assert resposta.json() == {"sessoes_encerradas": 1}
    bloqueada = _da_conta(banco, carla)
    assert bloqueada.bloqueada_em is not None
    assert bloqueada.motivo_do_bloqueio == "acesso_de_terceiro"
    assert da_carla.get(A_MINHA_CONTA).status_code == 401
    # a outra conta segue como estava
    assert _da_conta(banco, bia).bloqueada_em is None
    assert da_bia.get(A_MINHA_CONTA).status_code == 200
    registro = _registro(banco, "conta_bloqueada")
    assert (registro.ator_id, registro.acao, registro.alvo_id) == (
        chefe.id,
        "conta_bloqueada",
        carla.id,
    )
    assert registro.detalhes == {
        "motivo": "acesso_de_terceiro",
        "sessoes_encerradas": 1,
    }


def test_ninguem_bloqueia_a_propria_conta(banco, app, chefe):
    cliente = _cliente(banco, app, chefe)
    antes = _retrato(banco)
    resposta = cliente.post(BLOQUEAR, json={"id": str(chefe.id), "motivo": "incidente"})
    assert resposta.status_code == 409
    assert "própria conta" in resposta.json()["detail"]
    assert _retrato(banco) == antes


def test_bloquear_duas_vezes_da_409_e_o_primeiro_motivo_fica(banco, app, chefe, carla):
    cliente = _cliente(banco, app, chefe)
    assert (
        cliente.post(
            BLOQUEAR, json={"id": str(carla.id), "motivo": "abuso"}
        ).status_code
        == 200
    )
    antes = _retrato(banco)
    de_novo = cliente.post(BLOQUEAR, json={"id": str(carla.id), "motivo": "incidente"})
    assert de_novo.status_code == 409
    assert "já está bloqueada" in de_novo.json()["detail"]
    assert _retrato(banco) == antes


def test_quem_esta_na_lista_do_servidor_nao_e_bloqueado_por_aqui(
    monkeypatch, banco, app, chefe, carla
):
    monkeypatch.setenv(VARIAVEL_DOS_ADMINS, "carla@exemplo.com")
    cliente = _cliente(banco, app, chefe)
    antes = _retrato(banco)
    resposta = cliente.post(BLOQUEAR, json={"id": str(carla.id), "motivo": "incidente"})
    assert resposta.status_code == 409
    assert "lista de administradores do servidor" in resposta.json()["detail"]
    assert "exemplo.com" not in resposta.text
    assert _retrato(banco) == antes


def test_motivo_fora_da_lista_nao_bloqueia(banco, app, chefe, carla):
    cliente = _cliente(banco, app, chefe)
    antes = _retrato(banco)
    resposta = cliente.post(BLOQUEAR, json={"id": str(carla.id), "motivo": "birra"})
    assert resposta.status_code == 422
    assert "birra" not in resposta.text
    assert _retrato(banco) == antes


def test_admin_desbloqueia_a_conta_e_o_login_volta(banco, app, chefe, carla):
    cliente = _cliente(banco, app, chefe)
    cliente.post(BLOQUEAR, json={"id": str(carla.id), "motivo": "incidente"})
    resposta = cliente.post(DESBLOQUEAR, json={"id": str(carla.id)})
    assert resposta.status_code == 204
    assert resposta.headers["Cache-Control"] == "no-store"
    desbloqueada = _da_conta(banco, carla)
    assert desbloqueada.bloqueada_em is None
    assert desbloqueada.motivo_do_bloqueio is None
    registro = _registro(banco, "conta_desbloqueada")
    assert (registro.ator_id, registro.acao, registro.alvo_id) == (
        chefe.id,
        "conta_desbloqueada",
        carla.id,
    )
    # a pessoa entra de novo: uma sessão aberta depois do desbloqueio vale
    assert _cliente(banco, app, carla).get(A_MINHA_CONTA).status_code == 200


def test_desbloquear_quem_nao_esta_bloqueada_da_409(banco, app, chefe, carla):
    cliente = _cliente(banco, app, chefe)
    antes = _retrato(banco)
    resposta = cliente.post(DESBLOQUEAR, json={"id": str(carla.id)})
    assert resposta.status_code == 409
    assert "não está bloqueada" in resposta.json()["detail"]
    assert _retrato(banco) == antes
