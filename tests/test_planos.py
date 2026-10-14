"""Testes dos planos: limites, conferências e a mudança de plano pela linha de comando."""

import pytest
import sqlalchemy as sa

from src.banco import dados_do_usuario as repo
from src.banco import mudar_plano
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import PLANOS
from src.banco.usuarios import buscar_por_email, entrar
from src.planos import (
    APRENDIZADO_DE_MAQUINA,
    CARTEIRA_NO_RESEARCH,
    LIMITES_DOS_PLANOS,
    PARES,
    LimiteDoPlanoError,
    conferir_favoritos,
    conferir_simulacoes,
    limites_do,
    motivo_sem_acesso,
    plano_que_libera,
    pode_usar,
    tabela_de_planos,
)


def test_todo_plano_do_banco_tem_limites():
    assert set(LIMITES_DOS_PLANOS) == set(PLANOS)


def test_o_pro_e_mais_amplo_que_o_gratuito():
    g, p = limites_do("gratuito"), limites_do("pro")
    assert p.simulacoes is None and g.simulacoes is not None
    assert p.favoritos > g.favoritos
    assert p.ativos_na_carteira > g.ativos_na_carteira
    assert g.recursos < p.recursos


@pytest.mark.parametrize("plano", [None, "", "desconhecido"])
def test_plano_desconhecido_vale_como_gratuito(plano):
    assert limites_do(plano) is limites_do("gratuito")
    assert not pode_usar(plano, APRENDIZADO_DE_MAQUINA)


def test_recursos_do_pro():
    assert pode_usar("pro", APRENDIZADO_DE_MAQUINA) and pode_usar("pro", PARES)
    assert not pode_usar("gratuito", PARES)


@pytest.mark.parametrize("recurso", [APRENDIZADO_DE_MAQUINA, PARES, CARTEIRA_NO_RESEARCH])
def test_plano_que_libera_e_o_primeiro_que_tem_o_recurso(recurso):
    assert plano_que_libera(recurso) == "pro"


def test_plano_que_libera_recusa_recurso_inexistente():
    with pytest.raises(ValueError):
        plano_que_libera("voar")


def test_motivo_sem_acesso_explica_o_plano_que_libera():
    assert motivo_sem_acesso("gratuito", PARES) == (
        "Pairs trading faz parte do plano Pro. Você está no plano Gratuito."
    )
    assert motivo_sem_acesso("plus", APRENDIZADO_DE_MAQUINA) == (
        "Aprendizado de máquina faz parte do plano Pro. Você está no plano Plus."
    )


@pytest.mark.parametrize("plano", [None, "", "PRO", "empresa"])
def test_motivo_sem_acesso_trata_plano_estranho_como_gratuito(plano):
    assert motivo_sem_acesso(plano, PARES) == motivo_sem_acesso("gratuito", PARES)


def test_motivo_sem_acesso_e_vazio_quando_o_plano_tem_o_recurso():
    assert motivo_sem_acesso("pro", PARES) is None


def test_limite_de_simulacoes():
    conferir_simulacoes("gratuito", 4)
    with pytest.raises(LimiteDoPlanoError, match="até 5"):
        conferir_simulacoes("gratuito", 5)
    conferir_simulacoes("pro", 10_000)


def test_favoritos_so_barram_o_que_cresce_alem_do_limite():
    conferir_favoritos("gratuito", 2, 3)
    with pytest.raises(LimiteDoPlanoError, match="até 3"):
        conferir_favoritos("gratuito", 3, 4)
    # quem veio do Pro com 10 favoritos mantém e pode tirar, mas não pode adicionar
    conferir_favoritos("gratuito", 10, 9)
    conferir_favoritos("gratuito", 10, 10)
    with pytest.raises(LimiteDoPlanoError):
        conferir_favoritos("gratuito", 10, 11)


def test_tabela_de_planos_cobre_todos_os_recursos():
    linhas = {l["Recurso"]: l for l in tabela_de_planos()}
    assert linhas["Simulações salvas"] == {
        "Recurso": "Simulações salvas",
        "Gratuito": "5",
        "Plus": "30",
        "Pro": "Ilimitadas",
    }
    assert linhas["Aprendizado de máquina"]["Gratuito"] == "Não"
    assert linhas["Aprendizado de máquina"]["Plus"] == "Não"  # ML e pares só no Pro
    assert linhas["Pairs trading"]["Pro"] == "Sim"
    assert linhas["Relatórios em PDF"]["Plus"] == "Todos os tipos, 20 por dia"


def test_plus_fica_entre_o_gratuito_e_o_pro():
    from src.planos import limites_do

    gratuito, plus, pro = (limites_do(p) for p in ("gratuito", "plus", "pro"))
    assert gratuito.simulacoes < plus.simulacoes and pro.simulacoes is None
    assert gratuito.favoritos < plus.favoritos < pro.favoritos
    assert (
        gratuito.ativos_na_carteira < plus.ativos_na_carteira < pro.ativos_na_carteira
    )
    assert (
        gratuito.tipos_de_relatorio < plus.tipos_de_relatorio == pro.tipos_de_relatorio
    )
    assert plus.recursos == frozenset()


# --- no banco ---
@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    from src.banco.modelo import metadata

    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


def _guardar(conexao, usuario, nome):
    return repo.salvar_simulacao(
        conexao, usuario.id, "backtest", nome, {}, {}, plano=usuario.plano
    )


def test_o_banco_recusa_a_sexta_simulacao_do_plano_gratuito(conexao):
    ana = entrar(conexao, "ana", "ana@exemplo.com")[0]
    for i in range(5):
        _guardar(conexao, ana, f"s{i}")
    with pytest.raises(LimiteDoPlanoError):
        _guardar(conexao, ana, "s6")
    assert repo.contar_simulacoes(conexao, ana.id) == 5


def test_apagar_libera_espaco_no_plano_gratuito(conexao):
    ana = entrar(conexao, "ana", "ana@exemplo.com")[0]
    primeira = _guardar(conexao, ana, "s0")
    for i in range(1, 5):
        _guardar(conexao, ana, f"s{i}")
    repo.apagar_simulacao(conexao, ana.id, primeira.id)
    _guardar(conexao, ana, "nova")


def test_o_limite_de_cada_usuario_e_so_dele(conexao):
    ana = entrar(conexao, "ana", "ana@exemplo.com")[0]
    bia = entrar(conexao, "bia", "bia@exemplo.com")[0]
    for i in range(5):
        _guardar(conexao, ana, f"s{i}")
    _guardar(conexao, bia, "primeira")  # o limite da Ana não afeta a Bia


def test_o_banco_recusa_o_quarto_favorito_do_gratuito(conexao):
    ana = entrar(conexao, "ana", "ana@exemplo.com")[0]
    repo.salvar_favoritos(conexao, ana.id, ["A", "B", "C"], plano="gratuito")
    with pytest.raises(LimiteDoPlanoError):
        repo.salvar_favoritos(conexao, ana.id, ["A", "B", "C", "D"], plano="gratuito")
    repo.salvar_favoritos(conexao, ana.id, ["A", "B"], plano="gratuito")  # tirar pode


def test_pro_guarda_mais(conexao):
    ana = entrar(conexao, "ana", "ana@exemplo.com")[0]
    repo.salvar_favoritos(conexao, ana.id, [f"T{i}" for i in range(20)], plano="pro")
    for i in range(8):
        repo.salvar_simulacao(conexao, ana.id, "backtest", f"s{i}", {}, {}, plano="pro")


# --- linha de comando ---
def test_mudar_plano_pela_linha_de_comando(tmp_path, monkeypatch, capsys):
    url = f"sqlite:///{(tmp_path / 'p.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    migrar_para("head", url=url)
    motor = criar_engine(url)
    with motor.begin() as conexao:
        entrar(conexao, "ana", "ana@exemplo.com")
    monkeypatch.setattr(mudar_plano, "obter_engine", lambda: motor)

    assert mudar_plano.main(["Ana@Exemplo.com", "pro"]) == 0
    with motor.connect() as conexao:
        assert buscar_por_email(conexao, "ana@exemplo.com").plano == "pro"
    assert mudar_plano.main(["ninguem@exemplo.com", "pro"]) == 1
    assert mudar_plano.main(["ana@exemplo.com", "ouro"]) == 2
    assert mudar_plano.main(["so-um-argumento"]) == 2
    capsys.readouterr()
