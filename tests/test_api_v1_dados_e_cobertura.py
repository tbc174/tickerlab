"""A rota da página "Dados e cobertura" (linha 832): `GET /v1/dados-e-cobertura`.

Livre para toda conta logada; sem login, 401. O corpo repete o catálogo público (`GET /v1/base/tabelas`)
sem as colunas: mesmas tabelas, mesma ordem, mesma fonte e licença, e nada que o catálogo não declare.
"""

from src.api_v1.base_tabelas import tabelas_abertas
from src.banco.usuarios import mudar_plano
from tests import test_api_v1_rotas as rotas

chave = rotas.chave  # as fixtures da conta logada, as mesmas dos outros testes da API
cliente = rotas.cliente
ROTA = "/api/v1/dados-e-cobertura"
CAMPOS = {
    "tabela",
    "modulo",
    "frase",
    "fonte",
    "orgao",
    "licenca",
    "historico_desde",
    "frequencia",
    "situacao_da_licenca",
    "n_colunas",
}


def test_conta_gratuita_ve_as_tabelas_do_catalogo(cliente, banco):
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "gratuito")
    resposta = cliente.get(ROTA)
    assert resposta.status_code == 200, resposta.text
    tabelas = resposta.json()["tabelas"]
    assert [t["tabela"] for t in tabelas] == [t["tabela"] for t in tabelas_abertas()]
    assert tabelas
    for tabela in tabelas:
        assert set(tabela) == CAMPOS


def test_cada_linha_confere_com_o_catalogo_publico(cliente):
    catalogo = {str(t["tabela"]): t for t in tabelas_abertas()}
    for tabela in cliente.get(ROTA).json()["tabelas"]:
        original = catalogo[tabela["tabela"]]
        for campo in CAMPOS - {"n_colunas"}:
            assert tabela[campo] == original[campo], campo
        assert tabela["n_colunas"] == len(original["colunas"])  # type: ignore[arg-type]


def test_nenhuma_coluna_de_pessoa_nem_numero_de_cobertura_inventado(cliente):
    """A rota não traz colunas (só a contagem) nem número de cobertura: só o que o catálogo declara."""
    for tabela in cliente.get(ROTA).json()["tabelas"]:
        assert "colunas" not in tabela
        assert "cobertura" not in tabela


def test_sem_login_401(cliente):
    cliente.headers.pop("Cookie")
    assert cliente.get(ROTA).status_code == 401
