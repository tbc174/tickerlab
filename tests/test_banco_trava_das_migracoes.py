"""Migrações ao mesmo tempo esperam a vez (trava do PostgreSQL).

No servidor de casa várias tarefas abrem na mesma hora e cada uma migra o banco antes de começar.
Em 22/10/2026, às 00h30, a `ma-textos` e a `carga-enet` aplicaram a 0043 juntas: a primeira criou
as tabelas e a segunda quebrou com `DuplicateTable`. Com a trava, a segunda espera a primeira
terminar e encontra o banco já na última versão.

Os testes da espera só rodam no PostgreSQL de verdade (TICKERLAB_TEST_DATABASE_URL, como no CI);
no SQLite a trava não existe e a migração segue igual.
"""

import os
import subprocess
import sys
import threading
import time

import pytest
import sqlalchemy as sa

from src.banco.conexao import (
    CHAVE_DA_TRAVA_DAS_MIGRACOES,
    criar_engine,
    migrar_para,
    travar_migracoes,
)
from src.configuracao import PASTA_RAIZ

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")
# o processo filho lê a URL do ambiente herdado (a senha não vai na linha de comando)
MIGRAR_NUM_PROCESSO = (
    "import os; from src.banco.conexao import migrar_para; "
    "migrar_para('head', os.environ['TICKERLAB_TEST_DATABASE_URL'])"
)
SEGUNDOS_PARA_COMECAR_A_ESPERAR = 30
SEGUNDOS_PARA_A_MIGRACAO = 120
INTERVALO_DE_CONFERENCIA = 0.1

# a chave de 64 bits fica em duas metades no pg_locks: classid (alta) e objid (baixa)
METADE_ALTA, METADE_BAIXA = divmod(CHAVE_DA_TRAVA_DAS_MIGRACOES, 2**32)
QUEM_ESPERA_A_TRAVA = sa.text(
    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
    " AND classid = :alta AND objid = :baixa"
)

pytestmark = pytest.mark.xdist_group("postgres")

so_no_postgres = pytest.mark.skipif(
    not URL_DE_TESTE,
    reason="a trava é do PostgreSQL (defina TICKERLAB_TEST_DATABASE_URL)",
)


def test_no_sqlite_a_trava_nao_faz_nada_e_a_migracao_segue(tmp_path):
    url = f"sqlite:///{(tmp_path / 'trava.sqlite').as_posix()}"
    migrar_para("head", url)
    motor = criar_engine(url)
    with motor.begin() as conexao:
        travar_migracoes(conexao)
        versao = conexao.execute(sa.text("SELECT version_num FROM alembic_version"))
        assert versao.scalar()
    motor.dispose()


def _alguem_esperando_a_trava(conexao: sa.Connection) -> bool:
    prazo = time.monotonic() + SEGUNDOS_PARA_COMECAR_A_ESPERAR
    while time.monotonic() < prazo:
        esperando = conexao.execute(
            QUEM_ESPERA_A_TRAVA, {"alta": METADE_ALTA, "baixa": METADE_BAIXA}
        ).scalar()
        if esperando:
            return True
        time.sleep(INTERVALO_DE_CONFERENCIA)
    return False


@so_no_postgres
def test_migracao_espera_quem_segura_a_trava():
    migrar_para("base", URL_DE_TESTE)
    motor = criar_engine(URL_DE_TESTE)
    terminou = threading.Event()
    erros: list[Exception] = []

    def migrar() -> None:
        try:
            migrar_para("head", URL_DE_TESTE)
        except Exception as erro:  # noqa: BLE001 (o erro tem de aparecer no teste, não na thread)
            erros.append(erro)
        finally:
            terminou.set()

    try:
        with motor.connect() as outra_tarefa:
            outra_tarefa.execute(
                sa.text("SELECT pg_advisory_lock(:chave)"),
                {"chave": CHAVE_DA_TRAVA_DAS_MIGRACOES},
            )
            outra_tarefa.commit()  # a trava é da sessão: sobrevive ao commit
            linha = threading.Thread(target=migrar)
            linha.start()
            assert _alguem_esperando_a_trava(outra_tarefa), "migrou sem esperar a trava"
            assert not terminou.is_set()
            outra_tarefa.execute(
                sa.text("SELECT pg_advisory_unlock(:chave)"),
                {"chave": CHAVE_DA_TRAVA_DAS_MIGRACOES},
            )
            outra_tarefa.commit()
        assert terminou.wait(SEGUNDOS_PARA_A_MIGRACAO), "não migrou depois da trava"
        linha.join()
        assert not erros
    finally:
        motor.dispose()
        migrar_para("base", URL_DE_TESTE)


@so_no_postgres
def test_duas_tarefas_migrando_juntas_nao_quebram():
    # Processos, não threads, como as tarefas do servidor: o Alembic guarda o contexto num objeto
    # global do processo, e duas migrações em threads do mesmo processo se atrapalham.
    migrar_para("base", URL_DE_TESTE)
    try:
        tarefas = [
            subprocess.Popen(
                [sys.executable, "-c", MIGRAR_NUM_PROCESSO],
                cwd=PASTA_RAIZ,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for _ in range(2)
        ]
        saidas = [
            tarefa.communicate(timeout=SEGUNDOS_PARA_A_MIGRACAO)[0]
            for tarefa in tarefas
        ]
        quebradas = [
            saida
            for tarefa, saida in zip(tarefas, saidas, strict=True)
            if tarefa.returncode
        ]
        assert not quebradas, f"uma das migrações quebrou:\n{quebradas[0][-2000:]}"
    finally:
        migrar_para("base", URL_DE_TESTE)
