"""Migração 0041 (originação, B-33): sobe, desce e as chaves compostas valem no banco.

Rodam em SQLite por padrão e no PostgreSQL de verdade no CI (TICKERLAB_TEST_DATABASE_URL), como os
testes da sala (`test_sala_migracao.py`): o que importa é que o banco migrado, não só o código,
recuse uma conta trocada.
"""

import os
import uuid
from datetime import date

import pytest
import sqlalchemy as sa

from src.banco import originacao, sala
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import contatos_do_negocio, negocios_da_originacao, operacoes
from src.banco.usuarios import apagar_conta, entrar

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")
TABELAS = {"negocios_da_originacao", "contatos_do_negocio"}

pytestmark = pytest.mark.xdist_group("postgres")


@pytest.fixture
def motor(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'originacao.sqlite').as_posix()}"
    if URL_DE_TESTE:
        migrar_para("base", url)
    migrar_para("head", url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()
    if URL_DE_TESTE:
        migrar_para("base", url)


def _url(motor):
    return motor.url.render_as_string(hide_password=False)


def _tabelas(url):
    motor = criar_engine(url)
    try:
        return set(sa.inspect(motor).get_table_names())
    finally:
        motor.dispose()


def _contas(motor):
    with motor.begin() as conexao:
        ana = entrar(conexao, "sub-ana-orig", "ana-orig@exemplo.com", "Ana")[0]
        bia = entrar(conexao, "sub-bia-orig", "bia-orig@exemplo.com", "Bia")[0]
    return ana, bia


def _funil_da(motor, dono):
    with motor.begin() as conexao:
        operacao = sala.criar_operacao(
            conexao, usuario_id=dono.id, tipo="ma", nome="Aquisição da Alfa"
        )
        originacao.abrir_negocio(
            conexao, usuario_id=dono.id, operacao_id=operacao.id, origem="Indicação"
        )
        originacao.registrar_contato(
            conexao, usuario_id=dono.id, operacao_id=operacao.id, descricao="Oi"
        )
    return operacao


def test_migracao_0041_desce_para_a_0040_e_sobe_de_novo(motor):
    url = _url(motor)
    assert _tabelas(url) >= TABELAS
    desfazer_ate("0040", url)
    tabelas = _tabelas(url)
    assert not TABELAS & tabelas
    assert "operacoes" in tabelas  # a sala fica
    migrar_para("head", url)
    assert _tabelas(url) >= TABELAS


def test_toda_tabela_tem_dono_e_sai_com_a_conta_e_com_a_operacao(motor):
    inspecao = sa.inspect(motor)
    for tabela in TABELAS:
        colunas = {c["name"]: c for c in inspecao.get_columns(tabela)}
        assert colunas["usuario_id"]["nullable"] is False, tabela
        estrangeiras = inspecao.get_foreign_keys(tabela)
        assert any(e["referred_table"] == "usuarios" for e in estrangeiras), tabela
        for estrangeira in estrangeiras:
            assert estrangeira["options"].get("ondelete") == "CASCADE", tabela
    compostas = [
        e["constrained_columns"]
        for e in inspecao.get_foreign_keys("negocios_da_originacao")
        if e["referred_table"] == "operacoes"
    ]
    assert compostas == [["operacao_id", "usuario_id"]]


def test_so_um_negocio_por_operacao_no_banco_migrado(motor):
    ana, _ = _contas(motor)
    operacao = _funil_da(motor, ana)
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(
            sa.insert(negocios_da_originacao).values(
                usuario_id=ana.id,
                operacao_id=operacao.id,
                origem="De novo",
                fase_desde=date(2026, 10, 21),
            )
        )


def test_banco_recusa_conta_trocada_no_negocio_e_no_contato(motor):
    ana, bia = _contas(motor)
    operacao = _funil_da(motor, ana)
    linhas = {
        negocios_da_originacao: {
            "usuario_id": bia.id,
            "operacao_id": operacao.id,
            "origem": "Intruso",
            "fase_desde": date(2026, 10, 21),
        },
        contatos_do_negocio: {
            "id": uuid.uuid4(),
            "usuario_id": bia.id,
            "operacao_id": operacao.id,
            "descricao": "Intruso",
            "ocorreu_em": date(2026, 10, 21),
        },
    }
    for tabela, linha in linhas.items():
        with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
            conexao.execute(sa.insert(tabela).values(linha))


def test_banco_recusa_fase_fora_da_lista(motor):
    ana, _ = _contas(motor)
    operacao = _funil_da(motor, ana)
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(
            sa.update(negocios_da_originacao)
            .where(negocios_da_originacao.c.operacao_id == operacao.id)
            .values(fase="aprovado")
        )


def test_apagar_a_conta_no_banco_migrado_leva_o_funil_e_so_o_dela(motor):
    ana, bia = _contas(motor)
    _funil_da(motor, ana)
    _funil_da(motor, bia)
    with motor.begin() as conexao:
        assert apagar_conta(conexao, ana.id)
    with motor.connect() as conexao:
        for tabela in (operacoes, negocios_da_originacao, contatos_do_negocio):
            donos = set(conexao.execute(sa.select(tabela.c.usuario_id)).scalars())
            assert donos == {bia.id}, tabela.name


def test_apagar_a_operacao_no_banco_migrado_leva_o_negocio_e_os_contatos(motor):
    ana, _ = _contas(motor)
    operacao = _funil_da(motor, ana)
    with motor.begin() as conexao:
        assert sala.apagar_operacao(conexao, usuario_id=ana.id, operacao_id=operacao.id)
    with motor.connect() as conexao:
        for tabela in (negocios_da_originacao, contatos_do_negocio):
            assert conexao.execute(sa.select(tabela.c.usuario_id)).all() == []
