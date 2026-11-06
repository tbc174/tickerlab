"""Painel de uso: ativos por semana, relatórios e PDFs; só contagens, só para administradores."""

import json
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa

from src import painel_de_uso as painel
from src.administracao import PermissaoNegadaError
from src.banco.modelo import (
    metadata,
    relatorios,
    sessoes_de_login,
    simulacoes,
    usuarios,
)
from src.banco.origens import gravar_origem
from src.banco.usuarios import entrar
from src.origem import Origem

SEGUNDA = date(2026, 10, 19)


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


@pytest.fixture
def chefe(conexao):
    return entrar(
        conexao,
        "chefe",
        "chefe@exemplo.com",
        "Chefe",
        emails_de_admin=("chefe@exemplo.com",),
        email_confirmado=True,
    )[0]


def _pessoa(conexao, nome):
    return entrar(conexao, nome, f"{nome}@exemplo.com", nome)[0].id


def _em(dias=0):
    """Meio-dia (UTC) da segunda de referência, deslocado em `dias`."""
    base = datetime(SEGUNDA.year, SEGUNDA.month, SEGUNDA.day, 12, tzinfo=UTC)
    return base + timedelta(days=dias)


def _simulacao(conexao, usuario_id, quando):
    conexao.execute(
        sa.insert(simulacoes).values(
            id=uuid.uuid4(),
            usuario_id=usuario_id,
            tipo="backtest",
            nome="x",
            parametros={},
            resultado={},
            criada_em=quando,
        )
    )


def _relatorio(conexao, usuario_id, quando, tipo="ativo"):
    conexao.execute(
        sa.insert(relatorios).values(
            id=uuid.uuid4(), usuario_id=usuario_id, tipo=tipo, criado_em=quando
        )
    )


def test_segunda_da_semana():
    assert painel.segunda_da_semana(date(2026, 10, 25)) == SEGUNDA  # domingo
    assert painel.segunda_da_semana(SEGUNDA) == SEGUNDA


def test_ativo_precisa_de_duas_semanas_na_janela(conexao):
    ana, bia = _pessoa(conexao, "ana"), _pessoa(conexao, "bia")
    _simulacao(conexao, ana, _em())
    _simulacao(conexao, ana, _em(-7))
    _simulacao(conexao, bia, _em())  # só uma semana
    n = painel.numeros_da_semana(conexao, SEGUNDA)
    assert n["ativos_na_semana"] == 2
    assert n["ativos"] == 1


def test_uso_antes_da_janela_nao_conta(conexao):
    ana = _pessoa(conexao, "ana")
    _simulacao(conexao, ana, _em())
    _simulacao(conexao, ana, _em(-7 * painel.SEMANAS_DA_JANELA))
    assert painel.numeros_da_semana(conexao, SEGUNDA)["ativos"] == 0


def test_login_conta_como_uso(conexao):
    ana = _pessoa(conexao, "ana")
    for dias in (0, -7):
        conexao.execute(
            sa.insert(sessoes_de_login).values(
                id=uuid.uuid4(),
                usuario_id=ana,
                hash_do_token=uuid.uuid4().hex * 2,
                provedor="email",
                criada_em=_em(dias),
                expira_em=_em(30),
            )
        )
    assert painel.numeros_da_semana(conexao, SEGUNDA)["ativos"] == 1


def test_relatorios_por_tipo_so_da_semana(conexao):
    ana = _pessoa(conexao, "ana")
    _relatorio(conexao, ana, _em())
    _relatorio(conexao, ana, _em(2), "backtest")
    _relatorio(conexao, ana, _em(-1))  # semana anterior
    n = painel.numeros_da_semana(conexao, SEGUNDA)
    assert n["relatorios_gerados"] == 2
    assert n["pdfs_entregues"] == 2
    assert n["relatorios_por_tipo"] == {"ativo": 1, "backtest": 1}


def test_semana_fechada_nao_muda_com_dado_novo(conexao):
    ana = _pessoa(conexao, "ana")
    _simulacao(conexao, ana, _em())
    _relatorio(conexao, ana, _em())
    antes = painel.numeros_da_semana(conexao, SEGUNDA)
    _simulacao(conexao, ana, _em(8))
    _relatorio(conexao, ana, _em(9))
    assert painel.numeros_da_semana(conexao, SEGUNDA) == antes


def test_historico_so_para_administrador(conexao, chefe):
    ana = _pessoa(conexao, "ana")
    with pytest.raises(PermissaoNegadaError):
        painel.historico_semanal(conexao, ana)
    linhas = painel.historico_semanal(
        conexao, chefe.id, hoje=date(2026, 10, 22), semanas=3
    )
    assert [l["semana"] for l in linhas] == ["2026-10-05", "2026-10-12", "2026-10-19"]


def test_nada_de_pessoa_na_saida(conexao, chefe):
    texto = str(painel.historico_semanal(conexao, chefe.id, hoje=date(2026, 10, 22)))
    assert "@" not in texto and "chefe" not in texto


def test_historico_sem_checagem_para_scripts(conexao):
    ana = _pessoa(conexao, "ana")
    _relatorio(conexao, ana, _em())
    linhas = painel.historico(conexao, hoje=date(2026, 10, 22), semanas=1)
    assert linhas[0]["relatorios_gerados"] == 1


# --- ativos por origem do cadastro (linha 280; plano da campanha, seção 5) ---

LINKEDIN = Origem(source="linkedin", medium="organico", campaign="relatorio-eletricas")
IBMEC = Origem(source="ibmec", medium="oficina", campaign="beta", ref="liga-ibmec")


def _cadastro(conexao, nome, origem=None, quando=None):
    """Uma conta criada em `quando` (padrão: uma semana antes da segunda de referência)."""
    usuario_id = _pessoa(conexao, nome)
    conexao.execute(
        sa.update(usuarios)
        .where(usuarios.c.id == usuario_id)
        .values(criado_em=quando or _em(-7))
    )
    if origem is not None:
        gravar_origem(conexao, usuario_id, origem)
    return usuario_id


def _linha(linhas, origem):
    chave = (origem.source, origem.medium, origem.campaign, origem.ref)
    for linha in linhas:
        if (
            linha["utm_source"],
            linha["utm_medium"],
            linha["utm_campaign"],
            linha["ref"],
        ) == chave:
            return linha
    return None


def test_ativos_por_origem_conta_cadastros_e_ativos_de_cada_canal(conexao):
    ana = _cadastro(conexao, "ana", LINKEDIN)
    bia = _cadastro(conexao, "bia", LINKEDIN)
    caio = _cadastro(conexao, "caio")  # chegou sem link de campanha
    _cadastro(conexao, "dani", IBMEC)  # cadastrou e não voltou
    for pessoa in (ana, caio):
        _simulacao(conexao, pessoa, _em())
        _simulacao(conexao, pessoa, _em(-7))
    _simulacao(conexao, bia, _em())  # só uma semana: não é ativa

    linhas = painel.ativos_por_origem(conexao, SEGUNDA)

    assert _linha(linhas, LINKEDIN) == {
        "utm_source": "linkedin",
        "utm_medium": "organico",
        "utm_campaign": "relatorio-eletricas",
        "ref": None,
        "cadastros": 2,
        "cadastros_na_semana": 0,
        "ativos": 1,
    }
    assert _linha(linhas, IBMEC)["cadastros"] == 1
    assert _linha(linhas, IBMEC)["ativos"] == 0
    assert _linha(linhas, Origem())["cadastros"] == 1  # "sem origem"
    assert _linha(linhas, Origem())["ativos"] == 1
    assert linhas[0]["ativos"] >= linhas[-1]["ativos"]  # quem traz ativos vem primeiro


def test_a_origem_de_uma_conta_nao_vai_para_a_outra(conexao):
    ana = _cadastro(conexao, "ana", LINKEDIN)
    bia = _cadastro(conexao, "bia", IBMEC)
    for pessoa in (ana, bia):
        _simulacao(conexao, pessoa, _em())
        _simulacao(conexao, pessoa, _em(-7))
    gravar_origem(conexao, ana, IBMEC)  # a 2ª origem não troca a 1ª

    linhas = painel.ativos_por_origem(conexao, SEGUNDA)

    assert _linha(linhas, LINKEDIN)["cadastros"] == 1
    assert _linha(linhas, IBMEC)["cadastros"] == 1
    assert sum(linha["cadastros"] for linha in linhas) == 2


def test_cadastro_na_semana_e_conta_apagada(conexao):
    _cadastro(conexao, "ana", LINKEDIN, quando=_em(1))
    bia = _cadastro(conexao, "bia", LINKEDIN)
    conexao.execute(
        sa.update(usuarios).where(usuarios.c.id == bia).values(excluido_em=_em())
    )
    linha = _linha(painel.ativos_por_origem(conexao, SEGUNDA), LINKEDIN)
    assert linha["cadastros"] == 1
    assert linha["cadastros_na_semana"] == 1


def test_ativos_por_origem_nao_olha_o_futuro(conexao):
    ana = _cadastro(conexao, "ana", LINKEDIN)
    _simulacao(conexao, ana, _em())
    antes = painel.ativos_por_origem(conexao, SEGUNDA)
    _cadastro(conexao, "bia", IBMEC, quando=_em(8))  # cadastro na semana seguinte
    _simulacao(conexao, ana, _em(9))  # uso na semana seguinte
    assert painel.ativos_por_origem(conexao, SEGUNDA) == antes


def test_ativos_por_origem_so_para_administrador(conexao, chefe):
    ana = _cadastro(conexao, "ana", LINKEDIN)
    with pytest.raises(PermissaoNegadaError):
        painel.ativos_por_origem_do_admin(conexao, ana)
    linhas = painel.ativos_por_origem_do_admin(
        conexao, chefe.id, hoje=date(2026, 10, 22)
    )
    assert _linha(linhas, LINKEDIN)["cadastros"] == 1


def test_ativos_por_origem_sem_pessoa_na_saida(conexao, chefe):
    ana = _cadastro(conexao, "ana", LINKEDIN)
    texto = str(painel.ativos_por_origem(conexao, SEGUNDA))
    assert "@" not in texto and "'ana'" not in texto and str(ana) not in texto


def test_script_mostra_os_ativos_por_origem(tmp_path, monkeypatch, capsys):
    from scripts import painel_de_uso as script

    url = f"sqlite:///{tmp_path / 'banco.db'}"
    motor = sa.create_engine(url)
    metadata.create_all(motor)
    with motor.begin() as conexao:
        _cadastro(conexao, "ana", LINKEDIN)
    motor.dispose()
    monkeypatch.setattr(script, "url_do_banco", lambda: url)
    monkeypatch.setattr("sys.argv", ["painel_de_uso", "--por-origem"])

    assert script.main() == 0
    saida = json.loads(capsys.readouterr().out)
    assert _linha(saida, LINKEDIN)["cadastros"] == 1
