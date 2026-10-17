"""O roteiro do boletim diário (`scripts/enviar_boletim_da_base.py`): ensaio sem envio, envio uma
vez por dia, e falha com a linha `FALHAS:` para o Kuma. Resend e API são dublês."""

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from base.parquet import gravar_tabela
from scripts import enviar_boletim_da_base as eb
from src import versao_do_codigo as vc

DIA = "2026-10-17"


class Resend:
    def __init__(self, ok=True):
        self.pedidos, self._ok = [], ok

    def __call__(self, url, **pedido):
        self.pedidos.append(pedido)
        return SimpleNamespace(
            ok=self._ok,
            status_code=200 if self._ok else 422,
            json=lambda: {"id": "msg_9"},
        )


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv(vc.VARIAVEL, "587cb6c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7")
    base = tmp_path / "base"
    gravar_tabela(
        pd.DataFrame({"cnpj": ["1", "2"]}), base / "fca" / "emissores", [], ["cnpj"]
    )
    tarefas = tmp_path / "estado"
    tarefas.mkdir()
    (tarefas / "rede.falha").write_text(
        "2026-10-17T06:10:00-03:00 saída 1\nFALHAS: rede: x\n", encoding="utf-8"
    )
    monkeypatch.setenv(eb.VARIAVEL_DAS_TAREFAS, str(tarefas))
    monkeypatch.setenv(eb.VARIAVEL_DAS_DIARIAS, "rede")
    monkeypatch.setenv(eb.em.VARIAVEL_DO_DESTINATARIO, "autor@exemplo.com.br")
    monkeypatch.setenv(eb.VARIAVEL_DA_CHAVE, "re_teste")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return SimpleNamespace(base=base, boletins=tmp_path / "boletim")


def _rodar(a, *extra, transporte=None):
    return eb.main(["--hoje", DIA, "--base", str(a.base), "--boletins", str(a.boletins), *extra], transporte or Resend())  # fmt: skip


def test_ensaio_grava_o_html_e_nao_envia_nem_guarda(ambiente):
    resend = Resend()
    assert _rodar(ambiente, "--ensaio", transporte=resend) == 0
    assert resend.pedidos == []
    assert (ambiente.boletins / f"ensaio-{DIA}.html").exists()
    assert not (ambiente.boletins / "fotos").exists()


def test_envia_uma_vez_por_dia(ambiente):
    resend = Resend()
    assert _rodar(ambiente, transporte=resend) == 0
    assert len(resend.pedidos) == 1
    assert "rede: x" in resend.pedidos[0]["json"]["html"]
    assert (ambiente.boletins / "fotos" / f"{DIA}.json").exists()
    assert "msg_9" in (ambiente.boletins / "enviados" / DIA).read_text(encoding="utf-8")
    assert _rodar(ambiente, transporte=resend) == 0
    assert len(resend.pedidos) == 1  # já enviado hoje
    assert _rodar(ambiente, "--forcar", transporte=resend) == 0
    assert len(resend.pedidos) == 2


def test_sem_chave_da_api_sai_sem_paragrafo_mas_envia(ambiente):
    resend = Resend()
    assert _rodar(ambiente, transporte=resend) == 0
    assert "sem a chave da API" in resend.pedidos[0]["json"]["html"]


def test_sem_chave_do_resend_ou_destinatario_errado_falha(
    ambiente, monkeypatch, capsys
):
    monkeypatch.delenv(eb.VARIAVEL_DA_CHAVE)
    assert _rodar(ambiente) == 1
    assert "FALHAS: boletim-base: sem RESEND_API_KEY" in capsys.readouterr().out
    monkeypatch.setenv(eb.VARIAVEL_DA_CHAVE, "re_teste")
    monkeypatch.setenv(eb.em.VARIAVEL_DO_DESTINATARIO, "a@b.com, c@d.com")
    assert _rodar(ambiente) == 1
    assert "FALHAS: boletim-base:" in capsys.readouterr().out


def test_resend_recusou_falha_e_nao_marca_enviado(ambiente, capsys):
    assert _rodar(ambiente, transporte=Resend(ok=False)) == 1
    assert "FALHAS: boletim-base: o Resend recusou" in capsys.readouterr().out
    assert not (ambiente.boletins / "enviados" / DIA).exists()


def test_compara_com_a_fotografia_de_ontem(ambiente):
    eb.main(["--hoje", "2026-10-16", "--base", str(ambiente.base), "--boletins", str(ambiente.boletins)], Resend())  # fmt: skip
    gravar_tabela(
        pd.DataFrame({"cnpj": ["1", "2", "3"]}),
        ambiente.base / "fca" / "emissores",
        [],
        ["cnpj"],
    )
    resend = Resend()
    assert _rodar(ambiente, transporte=resend) == 0
    corpo = resend.pedidos[0]["json"]
    assert "A base desde 16/10/2026" in corpo["html"]
    assert "+1 linhas" in corpo["subject"]
    assert date.fromisoformat(DIA)  # o dia do teste é válido
