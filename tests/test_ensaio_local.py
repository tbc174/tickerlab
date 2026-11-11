"""O preparo do ensaio local (linha 800): banco SQLite, organização, cinco direitos e a chave só em arquivo."""

from pathlib import Path

import sqlalchemy as sa

from scripts import ensaio_local


def test_prepara_banco_e_grava_a_chave_so_no_arquivo(
    tmp_path: Path, capsys, monkeypatch
):
    banco = tmp_path / "ensaio.db"
    chave = tmp_path / "chave.txt"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", f"sqlite:///{banco.as_posix()}")

    assert ensaio_local.main(["--saida-da-chave", str(chave)]) == 0

    valor = chave.read_text(encoding="utf-8")
    assert valor
    saida = capsys.readouterr()
    assert valor not in saida.out + saida.err
    motor = sa.create_engine(f"sqlite:///{banco.as_posix()}")
    with motor.connect() as conexao:
        direitos = conexao.execute(
            sa.text("select count(*) from direitos_da_organizacao")
        ).scalar()
    motor.dispose()
    assert direitos == len(ensaio_local.CONJUNTOS_DO_ENSAIO)


def test_recusa_banco_que_nao_e_sqlite(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", "postgresql://u:s@h/b")
    chave = tmp_path / "chave.txt"

    assert ensaio_local.main(["--saida-da-chave", str(chave)]) == 2
    assert not chave.exists()
