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


def _conjuntos_gravados(banco: Path) -> list[str]:
    motor = sa.create_engine(f"sqlite:///{banco.as_posix()}")
    with motor.connect() as conexao:
        conjuntos = conexao.execute(
            sa.text("select conjunto from direitos_da_organizacao")
        ).scalars()
        gravados = sorted(conjuntos)
    motor.dispose()
    return gravados


def test_sem_piloto_o_ensaio_nao_da_a_marca(tmp_path: Path, monkeypatch):
    banco = tmp_path / "ensaio.db"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", f"sqlite:///{banco.as_posix()}")

    assert ensaio_local.main(["--saida-da-chave", str(tmp_path / "chave.txt")]) == 0
    assert "prontidao_de_piloto" not in _conjuntos_gravados(banco)


def test_com_piloto_a_organizacao_de_ensaio_ganha_a_marca(tmp_path: Path, monkeypatch):
    """A marca de piloto do ensaio (linha 865): a linha `prontidao_de_piloto` além dos conjuntos de sempre."""
    banco = tmp_path / "ensaio.db"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", f"sqlite:///{banco.as_posix()}")

    argumentos = ["--saida-da-chave", str(tmp_path / "chave.txt"), "--piloto"]
    assert ensaio_local.main(argumentos) == 0
    assert _conjuntos_gravados(banco) == sorted(
        [*ensaio_local.CONJUNTOS_DO_ENSAIO, "prontidao_de_piloto"]
    )


def test_recusa_banco_que_nao_e_sqlite(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", "postgresql://u:s@h/b")
    chave = tmp_path / "chave.txt"

    assert ensaio_local.main(["--saida-da-chave", str(chave)]) == 2
    assert not chave.exists()
