"""Migração 0048 (perguntas do chat, linha 903): sobe, desce e o banco guarda só números e ids.

Roda em SQLite por padrão e no PostgreSQL de verdade no CI (TICKERLAB_TEST_DATABASE_URL). A migração só
acrescenta uma tabela; o `downgrade` tira só ela. Apagar a conta ou a organização não apaga a linha (o gasto
do mês continua somando): só solta o id.
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import organizacoes, perguntas_do_chat, usuarios

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")
TABELA = "perguntas_do_chat"
ANTERIOR = "0047"
AGORA = datetime(2026, 11, 13, 12, tzinfo=UTC)

pytestmark = pytest.mark.xdist_group("postgres")


@pytest.fixture
def url(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'chat.sqlite').as_posix()}"
    if URL_DE_TESTE:
        migrar_para("base", url)
    migrar_para("head", url)
    yield url
    if URL_DE_TESTE:
        _gravar(url, sa.delete(perguntas_do_chat))
        _gravar(url, sa.delete(usuarios))
        _gravar(url, sa.delete(organizacoes))
        migrar_para("base", url)


def _tabelas(url: str) -> set[str]:
    motor = criar_engine(url)
    try:
        return set(sa.inspect(motor).get_table_names())
    finally:
        motor.dispose()


def _colunas(url: str) -> set[str]:
    motor = criar_engine(url)
    try:
        return {c["name"] for c in sa.inspect(motor).get_columns(TABELA)}
    finally:
        motor.dispose()


def _gravar(url: str, comando: sa.Executable) -> None:
    motor = criar_engine(url)
    try:
        with motor.begin() as conexao:
            conexao.execute(comando)
    finally:
        motor.dispose()


def _linhas(url: str) -> list[sa.Row]:
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            return list(conexao.execute(sa.select(perguntas_do_chat)))
    finally:
        motor.dispose()


def _conta(url: str) -> uuid.UUID:
    conta = uuid.uuid4()
    _gravar(url, sa.insert(usuarios).values(id=conta, email=f"{conta.hex}@exemplo.com"))
    return conta


def _organizacao(url: str) -> uuid.UUID:
    organizacao = uuid.uuid4()
    _gravar(
        url,
        sa.insert(organizacoes).values(
            id=organizacao, nome=f"Exemplo {organizacao.hex[:6]}"
        ),
    )
    return organizacao


def _pergunta(url: str, conta, organizacao, estado: str = "respondida") -> None:
    _gravar(
        url,
        sa.insert(perguntas_do_chat).values(
            id=uuid.uuid4(),
            usuario_id=conta,
            organizacao_id=organizacao,
            feita_em=AGORA,
            modelo="claude-opus-5-5",
            estado=estado,
        ),
    )


def test_sobe_e_desce_sem_tocar_no_resto(url) -> None:
    assert TABELA in _tabelas(url)
    _pergunta(url, _conta(url), _organizacao(url))
    desfazer_ate(ANTERIOR, url)
    tabelas = _tabelas(url)
    assert TABELA not in tabelas
    assert {"organizacoes", "membros_da_organizacao", "usuarios"} <= tabelas
    migrar_para("head", url)
    assert TABELA in _tabelas(url)
    assert _linhas(url) == []


def test_a_tabela_nao_tem_coluna_de_texto_da_pergunta_nem_da_resposta(url) -> None:
    colunas = _colunas(url)
    assert not {
        c for c in colunas if "texto" in c or "pergunta" in c or "resposta" in c
    }
    assert "email" not in colunas and "nome" not in colunas


def test_contadores_comecam_em_zero(url) -> None:
    _pergunta(url, _conta(url), _organizacao(url), estado="em_curso")
    (linha,) = _linhas(url)
    assert linha.tokens_de_entrada == linha.tokens_de_saida == 0
    assert linha.custo_em_microdolares == linha.chamadas_de_ferramenta == 0
    assert linha.latencia_ms is None


def test_banco_recusa_estado_desconhecido(url) -> None:
    with pytest.raises(sa.exc.IntegrityError):
        _pergunta(url, _conta(url), _organizacao(url), estado="qualquer")


def test_apagar_a_conta_ou_a_organizacao_solta_o_id_e_guarda_o_gasto(url) -> None:
    conta, organizacao = _conta(url), _organizacao(url)
    _pergunta(url, conta, organizacao)
    _gravar(url, sa.delete(usuarios).where(usuarios.c.id == conta))
    _gravar(url, sa.delete(organizacoes).where(organizacoes.c.id == organizacao))
    (linha,) = _linhas(url)
    assert linha.usuario_id is None and linha.organizacao_id is None
