"""O roteador `/data/v1` da API externa (B-32a, PR 1): desligado por padrão, catálogo e consumo.

Riscos do plano que estes testes pegam: a API servir antes do pen test (desligada por padrão); o
catálogo mostrar o que a chave não pode ver ou o que é de outra organização; o consumo vazar entre
organizações (risco 3); nome em português escapar para fora.
"""

from fastapi.testclient import TestClient

from src import api
from src.api_externa import nomes, rotas
from src.banco import chaves_da_api as cb
from src.chaves_da_api import ContextoDaChave
from tests import ajudantes_da_api_externa as aj

ROTAS = ("/data/v1/catalog", "/data/v1/usage")


# ---------------------------------------------------------------- desligada por padrão


def test_sem_a_variavel_a_api_externa_nao_existe(banco):
    cliente = TestClient(api.criar_app({}))
    for rota in ROTAS:
        assert cliente.get(rota).status_code == 404


def test_ligada_sem_chave_da_401(banco, monkeypatch):
    cliente = aj.cliente_da_api(monkeypatch)
    for rota in ROTAS:
        resposta = cliente.get(rota)
        assert resposta.status_code == 401
        assert resposta.json() == {"detail": "invalid_api_key"}


def test_chave_na_url_da_400(banco, monkeypatch):
    ator = aj.admin(banco)
    chave = aj.chave(banco, ator, aj.organizacao(banco, ator))
    cliente = aj.cliente_da_api(monkeypatch)
    resposta = cliente.get(
        "/data/v1/usage",
        params={"api_key": chave.valor},
        headers=aj.bearer(chave.valor),
    )
    assert resposta.status_code == 400
    assert chave.valor not in resposta.text


def test_tambem_responde_com_o_prefixo_api(banco, monkeypatch):
    # o mesmo molde das outras rotas: o proxy pode repassar ou tirar o /api
    cliente = aj.cliente_da_api(monkeypatch)
    assert cliente.get("/api/data/v1/usage").status_code == 401


# ---------------------------------------------------------------- catálogo


def _catalogo(cliente, chave):
    resposta = cliente.get("/data/v1/catalog", headers=aj.bearer(chave.valor))
    assert resposta.status_code == 200
    return resposta.json()


def test_catalogo_mostra_so_o_que_contrato_e_portao_deixam(banco, monkeypatch):
    ator = aj.admin(banco)
    alfa = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, alfa)
    aj.contrato(banco, ator, alfa)  # dfp para análise
    monkeypatch.setattr(
        rotas,
        "regras_da_api",
        lambda: aj.portao_liberando(
            aj.linha_do_portao(),  # dfp: o contrato e o portão deixam
            aj.linha_do_portao(conjunto="itr"),  # sem contrato: não aparece
            aj.linha_do_portao(campo="cpf_do_socio"),  # o portão nega: não aparece
        ),
    )
    corpo = _catalogo(aj.cliente_da_api(monkeypatch), chave)
    assert corpo["datasets"] == [
        {
            "dataset": "dfp",
            "purpose": "analysis",
            "fields": [{"field": "value", "source": "cvm-dfp"}],
        }
    ]
    assert [fonte["source"] for fonte in corpo["sources"]] == ["cvm-dfp"]
    assert corpo["sources"][0]["attribution"].startswith("Fonte: ")
    assert "cpf" not in str(corpo)


def test_catalogo_vazio_com_o_portao_de_hoje(banco, monkeypatch):
    # nenhuma linha de direito escrita ainda: nada sai, mesmo com contrato
    ator = aj.admin(banco)
    alfa = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, alfa)
    aj.contrato(banco, ator, alfa)
    corpo = _catalogo(aj.cliente_da_api(monkeypatch), chave)
    assert corpo == {"datasets": [], "sources": []}


def test_catalogo_e_o_da_propria_organizacao(banco, monkeypatch):
    ator = aj.admin(banco)
    alfa = aj.organizacao(banco, ator)
    beta = aj.organizacao(banco, ator, nome="Beta Wealth")
    aj.contrato(banco, ator, alfa)
    chave_da_beta = aj.chave(banco, ator, beta)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: aj.portao_liberando())
    assert _catalogo(aj.cliente_da_api(monkeypatch), chave_da_beta)["datasets"] == []


def test_contrato_suspenso_some_do_catalogo(banco, monkeypatch):
    ator = aj.admin(banco)
    alfa = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, alfa)
    direito = aj.contrato(banco, ator, alfa)
    with banco.begin() as conexao:
        cb.suspender_direito(
            conexao,
            organizacao_id=alfa.id,
            direito_id=direito.id,
            ator_id=ator.id,
            agora=aj.AGORA,
        )
    monkeypatch.setattr(rotas, "regras_da_api", lambda: aj.portao_liberando())
    assert _catalogo(aj.cliente_da_api(monkeypatch), chave)["datasets"] == []


# ---------------------------------------------------------------- consumo


def _consumo(cliente, chave):
    resposta = cliente.get("/data/v1/usage", headers=aj.bearer(chave.valor))
    assert resposta.status_code == 200
    return resposta.json()


def _gastar(banco, chave, pedidos: int, linhas: int = 0):
    with banco.begin() as conexao:
        contexto = cb.conferir_chave(conexao, chave.valor, agora=aj.AGORA)
        assert isinstance(contexto, ContextoDaChave)
        cb.registrar_consumo(
            conexao,
            contexto,
            conjunto=aj.CONJUNTO,
            finalidade="analise",
            linhas=linhas,
            pedidos=pedidos,
            agora=aj.AGORA,
        )


def test_consumo_e_so_da_propria_organizacao(banco, monkeypatch):
    ator = aj.admin(banco)
    alfa = aj.organizacao(banco, ator)
    beta = aj.organizacao(banco, ator, nome="Beta Wealth")
    chave_alfa = aj.chave(banco, ator, alfa)
    chave_beta = aj.chave(banco, ator, beta)
    _gastar(banco, chave_alfa, pedidos=7, linhas=70)
    _gastar(banco, chave_beta, pedidos=2, linhas=5)
    cliente = aj.cliente_da_api(monkeypatch)
    assert _consumo(cliente, chave_alfa) == {
        "month": "2026-10",
        "requests": 7,
        "rows": 70,
        "denied": 0,
        "plan": "piloto",
        "limits": {
            "requests_per_minute": 60,
            "requests_per_month": 10_000,
            "rows_per_response": 1_000,
        },
        "remaining_requests": 10_000 - 7,
    }
    assert _consumo(cliente, chave_beta)["requests"] == 2


def test_consumo_responde_mesmo_com_a_quota_do_mes_gasta(banco, monkeypatch):
    # quem estourou a quota precisa ver que estourou; o limite do minuto continua valendo
    ator = aj.admin(banco)
    alfa = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, alfa)
    _gastar(banco, chave, pedidos=10_000)
    corpo = _consumo(aj.cliente_da_api(monkeypatch), chave)
    assert corpo["remaining_requests"] == 0


def test_consultar_consumo_e_catalogo_nao_gasta_quota(banco, monkeypatch):
    ator = aj.admin(banco)
    alfa = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, alfa)
    cliente = aj.cliente_da_api(monkeypatch)
    _catalogo(cliente, chave)
    _consumo(cliente, chave)
    assert _consumo(cliente, chave)["requests"] == 0


def test_limite_do_minuto_vale_no_consumo(banco, monkeypatch):
    ator = aj.admin(banco)
    chave = aj.chave(banco, ator, aj.organizacao(banco, ator))
    cliente = aj.cliente_da_api(monkeypatch)
    for _ in range(60):
        assert (
            cliente.get("/data/v1/usage", headers=aj.bearer(chave.valor)).status_code
            == 200
        )
    resposta = cliente.get("/data/v1/usage", headers=aj.bearer(chave.valor))
    assert resposta.status_code == 429
    assert resposta.json() == {"detail": "rate_limited"}


def test_nenhuma_chave_em_portugues_sai(banco, monkeypatch):
    ator = aj.admin(banco)
    alfa = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, alfa)
    aj.contrato(banco, ator, alfa)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: aj.portao_liberando())
    cliente = aj.cliente_da_api(monkeypatch)
    de_fora = set(nomes.NOMES_DE_FORA.values()) | nomes.IDENTIFICADORES
    for corpo in (_catalogo(cliente, chave), _consumo(cliente, chave)):
        assert aj.chaves_de(corpo) <= de_fora
