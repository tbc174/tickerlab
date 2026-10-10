"""Testes dos dados por usuário: preferências, favoritos e simulações (com isolamento)."""

import uuid

import pytest
import sqlalchemy as sa

from src.banco import dados_do_usuario as repo
from src.banco.modelo import metadata
from src.banco.usuarios import entrar


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


@pytest.fixture
def ana(conexao):
    return entrar(conexao, "sub-ana", "ana@exemplo.com", "Ana")[0]


@pytest.fixture
def bia(conexao):
    return entrar(conexao, "sub-bia", "bia@exemplo.com", "Bia")[0]


# --- preferências ---
def test_sem_preferencias_devolve_vazio(conexao, ana):
    assert repo.carregar_preferencias(conexao, ana.id) == {}


def test_salvar_preferencias_cria_e_depois_substitui(conexao, ana):
    repo.salvar_preferencias(conexao, ana.id, {"periodo": "5y"})
    repo.salvar_preferencias(conexao, ana.id, {"periodo": "1y", "taxa": "Zero"})
    assert repo.carregar_preferencias(conexao, ana.id) == {
        "periodo": "1y",
        "taxa": "Zero",
    }


def test_preferencias_de_um_usuario_nao_aparecem_para_o_outro(conexao, ana, bia):
    repo.salvar_preferencias(conexao, ana.id, {"periodo": "5y"})
    assert repo.carregar_preferencias(conexao, bia.id) == {}


def test_preferencias_gigantes_sao_recusadas(conexao, ana):
    with pytest.raises(repo.DadosInvalidosError, match="grandes demais"):
        repo.salvar_preferencias(conexao, ana.id, {"x": "a" * 30_000})


# --- favoritos ---
def test_favoritos_mantem_a_ordem_e_tira_repetidos(conexao, ana):
    repo.salvar_favoritos(
        conexao, ana.id, ["VALE3.SA", "aapl", "VALE3.SA", " PETR4.SA "]
    )
    assert repo.listar_favoritos(conexao, ana.id) == ["VALE3.SA", "AAPL", "PETR4.SA"]


def test_salvar_favoritos_substitui_a_lista(conexao, ana):
    repo.salvar_favoritos(conexao, ana.id, ["AAPL", "VALE3.SA"])
    repo.salvar_favoritos(conexao, ana.id, ["PETR4.SA"])
    assert repo.listar_favoritos(conexao, ana.id) == ["PETR4.SA"]
    repo.salvar_favoritos(conexao, ana.id, [])
    assert repo.listar_favoritos(conexao, ana.id) == []


def test_favoritos_de_um_usuario_nao_mexem_nos_do_outro(conexao, ana, bia):
    repo.salvar_favoritos(conexao, ana.id, ["AAPL"])
    repo.salvar_favoritos(conexao, bia.id, ["VALE3.SA"])
    repo.salvar_favoritos(conexao, bia.id, [])
    assert repo.listar_favoritos(conexao, ana.id) == ["AAPL"]


@pytest.mark.parametrize("ruim", ["", " ", "A" * 21])
def test_ticker_invalido_nos_favoritos(conexao, ana, ruim):
    with pytest.raises(repo.DadosInvalidosError):
        repo.salvar_favoritos(conexao, ana.id, [ruim])


def test_favoritos_demais_sao_recusados(conexao, ana):
    muitos = [f"T{i}" for i in range(repo.MAX_FAVORITOS_NO_BANCO + 1)]
    with pytest.raises(repo.DadosInvalidosError, match="máximo"):
        repo.salvar_favoritos(conexao, ana.id, muitos)


# --- simulações ---
def _salvar(conexao, usuario, nome="Minha simulação", tipo="backtest"):
    return repo.salvar_simulacao(
        conexao,
        usuario.id,
        tipo,
        nome,
        {"ticker": "PETR4.SA"},
        {"Retorno total": "+10%"},
    )


def test_salvar_e_reabrir_uma_simulacao(conexao, ana):
    salva = _salvar(conexao, ana, "  Cruzamento   20/50 ")
    assert salva.nome == "Cruzamento 20/50"
    assert salva.parametros == {"ticker": "PETR4.SA"}
    de_novo = repo.buscar_simulacao(conexao, ana.id, salva.id)
    assert de_novo == salva


def test_listar_mostra_a_mais_nova_primeiro_e_filtra_por_tipo(conexao, ana):
    primeira = _salvar(conexao, ana, "primeira")
    segunda = _salvar(conexao, ana, "segunda", tipo="carteira")
    nomes = [s.nome for s in repo.listar_simulacoes(conexao, ana.id)]
    assert set(nomes) == {"primeira", "segunda"}
    assert [s.id for s in repo.listar_simulacoes(conexao, ana.id, "carteira")] == [
        segunda.id
    ]
    assert primeira.id not in [
        s.id for s in repo.listar_simulacoes(conexao, ana.id, "carteira")
    ]


def test_um_usuario_nao_ve_nem_reabre_a_simulacao_do_outro(conexao, ana, bia):
    da_ana = _salvar(conexao, ana)
    assert repo.listar_simulacoes(conexao, bia.id) == []
    assert repo.buscar_simulacao(conexao, bia.id, da_ana.id) is None


def test_um_usuario_nao_apaga_a_simulacao_do_outro(conexao, ana, bia):
    da_ana = _salvar(conexao, ana)
    assert repo.apagar_simulacao(conexao, bia.id, da_ana.id) is False
    assert repo.buscar_simulacao(conexao, ana.id, da_ana.id) is not None
    assert repo.apagar_simulacao(conexao, ana.id, da_ana.id) is True
    assert repo.buscar_simulacao(conexao, ana.id, da_ana.id) is None


def test_apagar_o_que_nao_existe_devolve_falso(conexao, ana):
    assert repo.apagar_simulacao(conexao, ana.id, uuid.uuid4()) is False


@pytest.mark.parametrize("nome", ["", "   ", "x" * 121])
def test_nome_invalido(conexao, ana, nome):
    with pytest.raises(repo.DadosInvalidosError):
        _salvar(conexao, ana, nome)


def test_tipo_desconhecido(conexao, ana):
    with pytest.raises(repo.DadosInvalidosError, match="Tipo"):
        _salvar(conexao, ana, tipo="outro")


def test_parametros_que_nao_sao_json(conexao, ana):
    with pytest.raises(repo.DadosInvalidosError, match="JSON"):
        repo.salvar_simulacao(conexao, ana.id, "backtest", "x", {"a": {1, 2}}, {})


def test_resultado_gigante_e_recusado(conexao, ana):
    with pytest.raises(repo.DadosInvalidosError, match="grandes demais"):
        repo.salvar_simulacao(conexao, ana.id, "backtest", "x", {}, {"a": "b" * 30_000})


def test_trava_de_seguranca_no_numero_de_simulacoes(conexao, ana, monkeypatch):
    monkeypatch.setattr(repo, "MAX_SIMULACOES_POR_USUARIO", 2)
    _salvar(conexao, ana, "1")
    _salvar(conexao, ana, "2")
    with pytest.raises(repo.DadosInvalidosError, match="máximo"):
        _salvar(conexao, ana, "3")


def test_apagar_a_conta_apaga_tudo_em_cascata(conexao, ana):
    from src.banco.usuarios import apagar_conta

    _salvar(conexao, ana)
    repo.salvar_favoritos(conexao, ana.id, ["AAPL"])
    repo.salvar_preferencias(conexao, ana.id, {"periodo": "1y"})
    assert apagar_conta(conexao, ana.id)
    assert repo.listar_simulacoes(conexao, ana.id) == []
    assert repo.listar_favoritos(conexao, ana.id) == []
    assert repo.carregar_preferencias(conexao, ana.id) == {}
