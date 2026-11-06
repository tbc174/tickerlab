"""Ficha da tentativa (run card): tudo o que identifica uma rodada, lido do registro."""

import json
from datetime import UTC, datetime

import pytest

from trader import ficha as fc
from trader import holdout
from trader.registro import Registro, hash_da_especificacao

SPEC = {"modelo": "logistica", "c": 1.0, "hash_dos_dados": "d" * 64}


@pytest.fixture
def r(tmp_path):
    return Registro(
        tmp_path / "registro.db",
        commit_fn=lambda: "abc1234",
        agora_fn=lambda: datetime(2026, 10, 11, 12, 0, tzinfo=UTC),
    )


def _resultado(dsr: float, aprovado: bool) -> dict:
    return {
        "aprovado": aprovado,
        "inconclusivo": False,
        "motivo_inconclusivo": "",
        "reprovados": [] if aprovado else ["A1"],
        "itens": [
            {
                "codigo": "A1",
                "descricao": "Sharpe deflacionado (todas as tentativas)",
                "valor": dsr,
                "limite": ">= 0.95",
                "passou": aprovado,
            }
        ],
    }


def test_ficha_tem_os_campos(r):
    r.registrar("H0", "b1", {"regra": "tendencia"})
    tid = r.registrar("H1", "logistica_v1", SPEC)
    r.salvar_resultado(tid, _resultado(0.42, aprovado=False))
    r.registrar_proveniencia(tid, autor="Tiago", modelo="claude-opus-5-5")
    f = fc.montar_ficha(r, tid)
    assert f["hipotese"] == "H1 · logistica_v1"
    assert f["numero_da_tentativa"] == 2
    assert f["total_para_o_dsr"] == 2
    assert f["versao_do_criterio"] == holdout.HASH_DO_CRITERIO
    assert f["hash_da_especificacao"] == hash_da_especificacao(SPEC)
    assert f["hash_dos_dados"] == "d" * 64
    assert f["parametros"] == SPEC
    assert f["dsr"] == pytest.approx(0.42)
    assert f["veredito"] == "reprovado"
    assert f["reprovados"] == ["A1"]
    assert f["proveniencia"]["modelo"] == "claude-opus-5-5"
    assert f["commit_do_codigo"] == "abc1234"
    json.dumps(f)  # tipos simples: a ficha vira JSON sem conversão


def test_ficha_sem_resultado_diz_sem_veredito(r):
    tid = r.registrar("H1", "logistica_v1", {"modelo": "logistica"})
    f = fc.montar_ficha(r, tid)
    assert f["veredito"] == "sem veredito"
    assert f["dsr"] is None
    assert f["hash_dos_dados"] is None
    assert f["proveniencia"] is None


def test_veredito_aprovado_e_inconclusivo(r):
    a = r.registrar("H1", "a", {"x": 1})
    r.salvar_resultado(a, _resultado(0.97, aprovado=True))
    b = r.registrar("H1", "b", {"x": 2})
    r.salvar_resultado(b, {**_resultado(0.97, aprovado=True), "inconclusivo": True})
    assert fc.montar_ficha(r, a)["veredito"] == "aprovado"
    assert fc.montar_ficha(r, b)["veredito"] == "inconclusivo"


def test_resultado_de_baseline_sem_itens_nao_vira_aprovado(r):
    """As baselines guardam só a carteira: sem itens do critério, não há veredito."""
    tid = r.registrar("H0", "b1", {"regra": "tendencia"})
    r.salvar_resultado(tid, {"carteira": {"Sharpe": 0.3}})
    f = fc.montar_ficha(r, tid)
    assert f["veredito"] == "sem veredito"
    assert f["dsr"] is None


def test_numero_da_tentativa_conta_so_a_fase(r):
    r.registrar("H1", "a", {"x": 1})
    h = r.registrar("H1", "a", {"x": 1}, fase="holdout")
    assert fc.montar_ficha(r, h)["numero_da_tentativa"] == 1


def test_markdown_da_ficha(r):
    tid = r.registrar("H1", "logistica_v1", {"modelo": "logistica"})
    r.salvar_resultado(tid, _resultado(0.42, aprovado=False))
    texto = fc.ficha_em_markdown(fc.montar_ficha(r, tid))
    assert "# Ficha da tentativa #1: H1 · logistica_v1" in texto
    assert "| Sharpe deflacionado (A1) | 0.420 |" in texto
    assert "| Hash dos dados | não registrado |" in texto
    assert "| Quem escreveu | não anotado |" in texto
    assert "## Limites e cuidados" in texto
    assert "não é recomendação de investimento" in texto
