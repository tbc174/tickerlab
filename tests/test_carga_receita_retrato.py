"""O script da carga do CNPJ: ensaio lista sem baixar, sem chave não roda."""

import zipfile
from pathlib import Path

import pytest

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


class _ClienteQueEntregaPaginaDepoisZip:
    """Na 1ª vez grava uma página de erro no lugar do ZIP; na 2ª, um ZIP de verdade."""

    def __init__(self):
        self.chamadas = 0

    def baixar(self, url, destino):
        self.chamadas += 1
        if self.chamadas == 1:
            destino.write_bytes(b"<html>Just a moment...</html>")
        else:
            with zipfile.ZipFile(destino, "w") as zipado:
                zipado.writestr("a.csv", "x")
        return {}


def test_zip_que_veio_como_pagina_e_baixado_de_novo(tmp_path, monkeypatch):
    monkeypatch.setattr(script.time, "sleep", lambda _s: None)
    cliente = _ClienteQueEntregaPaginaDepoisZip()
    script._baixar_zip_inteiro(
        cliente, "https://x/Socios0.zip", tmp_path / "Socios0.zip"
    )
    assert cliente.chamadas == 2
    assert zipfile.is_zipfile(tmp_path / "Socios0.zip")


def test_zip_que_nunca_vem_inteiro_para_com_erro_claro(tmp_path, monkeypatch):
    monkeypatch.setattr(script.time, "sleep", lambda _s: None)

    class Sempre:
        def baixar(self, url, destino):
            destino.write_bytes(b"nao e zip")
            return {}

    with pytest.raises(RuntimeError, match="Socios0.zip"):
        script._baixar_zip_inteiro(
            Sempre(), "https://x/Socios0.zip", tmp_path / "Socios0.zip"
        )


def test_peca_cortada_some_quando_ha_copia_inteira_com_sufixo():
    class Alvo:
        def __init__(self, nome):
            self.url = f"https://x/CNPJ/2023-08/{nome}"

    alvos = [
        Alvo(n)
        for n in (
            "Estabelecimentos5.zip",
            "Estabelecimentos6.zip",
            "Estabelecimentos6-RF0819000032530.zip",
        )
    ]
    nomes = [a.url.rsplit("/", 1)[-1] for a in script._sem_os_cortados(alvos)]
    assert nomes == ["Estabelecimentos5.zip", "Estabelecimentos6-RF0819000032530.zip"]
