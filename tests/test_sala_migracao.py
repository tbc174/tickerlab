"""Migração 0040 (sala de dados, B-20 PR 1): sobe, desce e as chaves compostas valem no banco.

Rodam em SQLite por padrão e no PostgreSQL de verdade no CI (TICKERLAB_TEST_DATABASE_URL), como os
testes de `test_banco.py`: o que importa aqui é que o banco migrado, não só o código, recuse uma
conta trocada.
"""

import os
import uuid

import pytest
import sqlalchemy as sa

from src.banco import sala
from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import (
    checklist_da_sala,
    contradicoes_da_sala,
    documentos_da_sala,
    evidencias_da_sala,
    operacoes,
)
from src.banco.usuarios import apagar_conta, entrar

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")
TABELAS_DA_SALA = {
    "operacoes",
    "documentos_da_sala",
    "evidencias_da_sala",
    "contradicoes_da_sala",
    "checklist_da_sala",
}

SO_APONTA = ("checklist_da_sala", "documentos_da_sala")

pytestmark = pytest.mark.xdist_group("postgres")


@pytest.fixture
def motor(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'sala.sqlite').as_posix()}"
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


def test_migracao_0040_desce_para_a_0039_e_sobe_de_novo(motor):
    url = _url(motor)
    assert _tabelas(url) >= TABELAS_DA_SALA
    desfazer_ate("0039", url)
    tabelas = _tabelas(url)
    assert not TABELAS_DA_SALA & tabelas
    assert "usuarios" in tabelas  # o resto do banco fica
    migrar_para("head", url)
    assert _tabelas(url) >= TABELAS_DA_SALA


def test_toda_tabela_da_sala_tem_dono_e_sai_com_a_conta(motor):
    inspecao = sa.inspect(motor)
    for tabela in TABELAS_DA_SALA:
        colunas = {c["name"]: c for c in inspecao.get_columns(tabela)}
        assert colunas["usuario_id"]["nullable"] is False, tabela
        estrangeiras = inspecao.get_foreign_keys(tabela)
        assert any(e["referred_table"] == "usuarios" for e in estrangeiras), tabela
        for estrangeira in estrangeiras:
            # o item do checklist só aponta o documento: apagar o documento solta o item
            # (src/banco/sala.py), não apaga o item
            if (tabela, estrangeira["referred_table"]) == SO_APONTA:
                continue
            assert estrangeira["options"].get("ondelete") == "CASCADE", tabela


def test_chaves_compostas_ligam_cada_tabela_a_operacao_da_mesma_conta(motor):
    inspecao = sa.inspect(motor)
    for tabela in TABELAS_DA_SALA - {"operacoes"}:
        compostas = [
            e["constrained_columns"]
            for e in inspecao.get_foreign_keys(tabela)
            if e["referred_table"] == "operacoes"
        ]
        assert compostas == [["operacao_id", "usuario_id"]], tabela


def _contas(motor):
    with motor.begin() as conexao:
        ana = entrar(conexao, "sub-ana-sala", "ana-sala@exemplo.com", "Ana")[0]
        bia = entrar(conexao, "sub-bia-sala", "bia-sala@exemplo.com", "Bia")[0]
    return ana, bia


def _sala_da(motor, dono, sha="a" * 64):
    with motor.begin() as conexao:
        operacao = sala.criar_operacao(
            conexao, usuario_id=dono.id, tipo="fidc", nome="FIDC Gama"
        )
        documento = sala.registrar_documento(
            conexao,
            usuario_id=dono.id,
            operacao_id=operacao.id,
            nome_original="regulamento.pdf",
            tipo="pdf",
            tamanho_bytes=10,
            sha256=sha,
        )
    return operacao, documento


def _evidencia(dono_id, operacao_id, documento_id):
    return {
        "id": uuid.uuid4(),
        "usuario_id": dono_id,
        "operacao_id": operacao_id,
        "documento_id": documento_id,
        "metrica": "pl",
        "periodo": "2025-12",
        "valor_numero": "1",
        "extraido_por": "pessoa",
    }


def test_banco_recusa_conta_trocada_em_cada_tabela(motor):
    """Com os ids da Ana, nenhuma linha da Bia entra na sala dela (FK composta)."""
    ana, bia = _contas(motor)
    operacao, documento = _sala_da(motor, ana)
    with motor.begin() as conexao:
        evidencia_da_ana = _evidencia(ana.id, operacao.id, documento.id)
        conexao.execute(sa.insert(evidencias_da_sala).values(evidencia_da_ana))
    trocadas = {
        documentos_da_sala: {
            "id": uuid.uuid4(),
            "usuario_id": bia.id,
            "operacao_id": operacao.id,
            "nome_original": "x.pdf",
            "tipo": "pdf",
            "tamanho_bytes": 1,
            "sha256": "c" * 64,
        },
        evidencias_da_sala: _evidencia(bia.id, operacao.id, documento.id),
        contradicoes_da_sala: {
            "id": uuid.uuid4(),
            "usuario_id": bia.id,
            "operacao_id": operacao.id,
            "evidencia_a": evidencia_da_ana["id"],
            "evidencia_b": evidencia_da_ana["id"],
        },
        checklist_da_sala: {
            "id": uuid.uuid4(),
            "usuario_id": bia.id,
            "operacao_id": operacao.id,
            "codigo": "balanco",
        },
    }
    for tabela, linha in trocadas.items():
        with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
            conexao.execute(sa.insert(tabela).values(linha))


def test_banco_recusa_evidencia_que_aponta_documento_de_outra_sala(motor):
    ana, _ = _contas(motor)
    _, documento_da_alfa = _sala_da(motor, ana)
    beta, _ = _sala_da(motor, ana, sha="d" * 64)
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(
            sa.insert(evidencias_da_sala).values(
                _evidencia(ana.id, beta.id, documento_da_alfa.id)
            )
        )


def test_apagar_a_conta_no_banco_migrado_leva_a_sala_e_so_a_dela(motor):
    ana, bia = _contas(motor)
    for dono in (ana, bia):
        operacao, documento = _sala_da(motor, dono)
        with motor.begin() as conexao:
            conexao.execute(
                sa.insert(evidencias_da_sala).values(
                    _evidencia(dono.id, operacao.id, documento.id)
                )
            )
            conexao.execute(
                sa.insert(checklist_da_sala).values(
                    id=uuid.uuid4(),
                    usuario_id=dono.id,
                    operacao_id=operacao.id,
                    codigo="balanco",
                    estado="recebido",
                    documento_id=documento.id,
                )
            )
    with motor.begin() as conexao:
        assert apagar_conta(conexao, ana.id)
    with motor.connect() as conexao:
        for tabela in (operacoes, documentos_da_sala, evidencias_da_sala):
            donos = set(conexao.execute(sa.select(tabela.c.usuario_id)).scalars())
            assert donos == {bia.id}, tabela.name
        assert conexao.execute(sa.select(checklist_da_sala.c.usuario_id)).all() == [
            (bia.id,)
        ]


def _ligar_ao_checklist(motor, dono, operacao, documento):
    with motor.begin() as conexao:
        conexao.execute(
            sa.insert(checklist_da_sala).values(
                id=uuid.uuid4(),
                usuario_id=dono.id,
                operacao_id=operacao.id,
                codigo="balanco",
                estado="recebido",
                documento_id=documento.id,
            )
        )


def test_apagar_documento_ligado_ao_checklist_no_banco_migrado(motor):
    # A chave do checklist para o documento não tem cascata: o código solta o item antes.
    ana, _ = _contas(motor)
    operacao, documento = _sala_da(motor, ana)
    _ligar_ao_checklist(motor, ana, operacao, documento)
    with motor.begin() as conexao:
        assert sala.apagar_documento(
            conexao,
            usuario_id=ana.id,
            operacao_id=operacao.id,
            documento_id=documento.id,
        )
    with motor.connect() as conexao:
        item = conexao.execute(sa.select(checklist_da_sala)).one()
    assert (item.documento_id, item.estado) == (None, "pendente")


def test_apagar_operacao_com_checklist_ligado_no_banco_migrado(motor):
    ana, _ = _contas(motor)
    operacao, documento = _sala_da(motor, ana)
    _ligar_ao_checklist(motor, ana, operacao, documento)
    with motor.begin() as conexao:
        assert sala.apagar_operacao(conexao, usuario_id=ana.id, operacao_id=operacao.id)
    with motor.connect() as conexao:
        for tabela in (operacoes, documentos_da_sala, checklist_da_sala):
            assert conexao.execute(sa.select(tabela.c.id)).all() == [], tabela.name
