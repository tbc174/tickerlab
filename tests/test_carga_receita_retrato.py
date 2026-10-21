"""O script da carga do CNPJ: ensaio lista sem baixar, sem chave não roda."""

from pathlib import Path

from scripts import carga_receita_retrato as script


class _Cliente:
    pass


def test_ensaio_so_lista_os_meses(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(script, "ClienteHttp", _Cliente)
    monkeypatch.setattr(script, "meses_do_cnpj", lambda c: ["2026-09", "2026-10"])
    caplog.set_level("INFO")
    codigo = script.main(
        ["--base", str(tmp_path / "b"), "--restrita", str(tmp_path / "r"), "--ensaio"]
    )
    assert codigo == 0
    assert "2026-09, 2026-10" in caplog.text
    assert not (tmp_path / "b").exists()


def test_sem_chave_nao_carrega(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(script, "ClienteHttp", _Cliente)
    monkeypatch.setattr(script, "meses_do_cnpj", lambda c: ["2026-09"])
    monkeypatch.setenv("TICKERLAB_PESSOAS_CHAVE", str(tmp_path / "nao-existe"))
    codigo = script.main(
        ["--base", str(tmp_path / "b"), "--restrita", str(tmp_path / "r")]
    )
    assert codigo == 1
    assert capsys.readouterr().out.startswith("FALHAS:")


def test_mes_ancora_guarda_o_zip_no_acervo(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path / "acervo"))
    zip_falso = tmp_path / "Simples.zip"
    zip_falso.write_bytes(b"PK" + b"x" * 20)
    script._guardar_ancora("2026-01", {"Simples": [zip_falso]})
    guardados = list((tmp_path / "acervo" / "restrito" / "rfb-cnpj").rglob("*.zip"))
    assert len(guardados) == 1 and zip_falso.exists()
    assert isinstance(Path(guardados[0]), Path)
