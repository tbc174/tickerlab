"""Papel da v0.2: a conta de P1 a P3 sai só das linhas gravadas, com dados de exemplo."""

from datetime import date, datetime, timedelta

import numpy as np
import pytest

from trader.papel import julgamento as jg
from trader.papel import registro as rg
from trader.papel import series as sr

MERGE = date(2026, 11, 5)
INICIO = date(2026, 11, 6)  # o primeiro pregão depois do merge
CDI = 0.0004


def _agora(dia: date, hora: int) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, tzinfo=rg.BRASILIA)


def _papel(tmp_path) -> rg.RegistroDoPapel:
    papel = rg.RegistroDoPapel(tmp_path)
    papel.fixar_inicio(MERGE, "abc123", _agora(MERGE, 20))
    return papel


def _gravar_ano(
    papel: rg.RegistroDoPapel,
    serie: sr.Serie,
    retornos,
    pular=(),
    parar_antes: int = 0,
) -> list[date]:
    """Grava os dias da série com o patrimônio composto de `retornos`, pulando os de `pular`."""
    dias = jg.dias_esperados(INICIO, jg.fim_do_papel(INICIO), serie.mercado)
    dias = dias[: len(dias) - parar_antes]
    patrimonio = 100_000.0
    hora = 7 if serie.mercado == "b3" else 22
    for posicao, dia in enumerate(dias):
        patrimonio *= 1 + retornos[posicao]
        if posicao in pular:
            continue
        foto = {
            "fechamento": rg.vespera(dia, serie.mercado).isoformat(),
            "carteira": {"patrimonio": patrimonio},
            "cdi_do_dia": CDI,
        }
        quando = (
            _agora(dia, hora)
            if serie.mercado == "b3"
            else _agora(dia - timedelta(1), hora)
        )
        papel.gravar(serie.nome, serie.mercado, dia, foto, quando)
    return dias


def _criterios(resultado: dict) -> dict:
    return {c["nome"]: c for c in resultado["criterios"]}


def _bons(semente: int = 1, n: int = 400):
    return np.random.default_rng(semente).normal(0.001, 0.004, n)


P0_3 = sr.serie("p0_3")
FIM = jg.fim_do_papel(INICIO)


def test_o_papel_dura_12_meses_corridos():
    assert date(2027, 11, 6) == FIM
    dias = jg.dias_esperados(INICIO, FIM, "b3")
    assert dias[0] == INICIO and dias[-1] < FIM
    assert date(2026, 11, 20) not in dias  # feriado não é dia do papel
    assert len(jg.dias_esperados(INICIO, FIM, "cripto")) == 365


def test_serie_boa_passa_nos_tres(tmp_path):
    papel = _papel(tmp_path)
    _gravar_ano(papel, P0_3, _bons())
    resultado = jg.julgar(papel, P0_3, FIM)
    assert resultado["completo"] is True
    assert resultado["passou"] is True
    criterios = _criterios(resultado)
    assert criterios["P1"]["valor"] > 0.5 * P0_3.sharpe_de_referencia
    assert criterios["P3"]["valor"] == 0


def test_serie_que_perde_para_o_cdi_nao_passa_no_p1(tmp_path):
    papel = _papel(tmp_path)
    _gravar_ano(papel, P0_3, _bons() - 0.0012)  # abaixo do CDI do dia
    criterios = _criterios(jg.julgar(papel, P0_3, FIM))
    assert criterios["P1"]["valor"] < 0
    assert criterios["P1"]["passou"] is False


def test_queda_maior_que_1_5_vez_a_do_desenvolvimento_nao_passa_no_p2(tmp_path):
    papel = _papel(tmp_path)
    retornos = _bons()
    retornos[100:110] = -0.02  # ~18% de queda; o limite da P0-3 é 1,5 × 11,3% ≈ 17%
    _gravar_ano(papel, P0_3, retornos)
    criterios = _criterios(jg.julgar(papel, P0_3, FIM))
    assert criterios["P2"]["valor"] < 1.5 * P0_3.queda_do_desenvolvimento
    assert criterios["P2"]["passou"] is False


def test_a_queda_atravessando_uma_falta_conta_no_p2(tmp_path):
    papel = _papel(tmp_path)
    retornos = _bons()
    retornos[50] = -0.25  # a queda acontece no dia que não foi gravado
    _gravar_ano(papel, P0_3, retornos, pular={50})
    criterios = _criterios(jg.julgar(papel, P0_3, FIM))
    assert criterios["P2"]["valor"] <= -0.25 + 1e-9
    assert criterios["P2"]["passou"] is False


def test_o_retorno_que_atravessa_uma_falta_fica_fora_do_sharpe(tmp_path):
    papel = _papel(tmp_path)
    _gravar_ano(papel, P0_3, _bons(), pular={10})
    curva = jg.curva_do_papel(papel.linhas(P0_3.nome))
    assert curva["retorno"].isna().sum() == 2  # o primeiro dia e o dia depois da falta
    assert np.isnan(
        curva["retorno"].iloc[10]
    )  # a 11ª gravação é a do dia seguinte à falta


def test_cinco_faltas_passam_e_seis_nao(tmp_path):
    cinco = rg.RegistroDoPapel(tmp_path / "cinco")
    cinco.fixar_inicio(MERGE, "abc123", _agora(MERGE, 20))
    _gravar_ano(cinco, P0_3, _bons(), pular={3, 40, 41, 90, 200})
    assert _criterios(jg.julgar(cinco, P0_3, FIM))["P3"] == {
        "nome": "P3",
        "valor": 5,
        "limite": "no prazo, sem regravar e ≤ 5 faltas",
        "passou": True,
    }
    seis = rg.RegistroDoPapel(tmp_path / "seis")
    seis.fixar_inicio(MERGE, "abc123", _agora(MERGE, 20))
    _gravar_ano(seis, P0_3, _bons(), pular={3, 40, 41, 90, 200, 201})
    resultado = jg.julgar(seis, P0_3, FIM)
    assert _criterios(resultado)["P3"]["passou"] is False
    assert resultado["passou"] is False


def test_dias_que_nem_viraram_falta_contam_como_falta(tmp_path):
    papel = _papel(tmp_path)
    _gravar_ano(
        papel, P0_3, _bons(), parar_antes=6
    )  # o gravador parou na última semana
    assert _criterios(jg.julgar(papel, P0_3, FIM))["P3"]["valor"] == 6


def test_antes_dos_12_meses_sai_parcial_e_so_conta_ate_hoje(tmp_path):
    papel = _papel(tmp_path)
    _gravar_ano(papel, P0_3, _bons(), parar_antes=150)
    hoje = date.fromisoformat(papel.linhas(P0_3.nome)[-1]["dia"]) + timedelta(days=1)
    resultado = jg.julgar(papel, P0_3, hoje)
    assert resultado["completo"] is False
    assert _criterios(resultado)["P3"]["valor"] == 0


def test_cripto_grava_todo_dia_corrido_e_julga_com_o_sharpe_da_ficha(tmp_path):
    papel = _papel(tmp_path)
    cripto = sr.serie("p0_1")
    _gravar_ano(papel, cripto, _bons(semente=4))
    resultado = jg.julgar(papel, cripto, FIM)
    assert len(jg.curva_do_papel(papel.linhas("p0_1"))) == 365
    assert resultado["passou"] is True


def test_sem_inicio_nao_ha_julgamento(tmp_path):
    with pytest.raises(ValueError, match="início"):
        jg.julgar(rg.RegistroDoPapel(tmp_path), P0_3, FIM)


def test_cadeia_alterada_nao_e_julgada(tmp_path):
    papel = _papel(tmp_path)
    _gravar_ano(papel, P0_3, _bons(), parar_antes=200)
    arquivo = papel.arquivo(P0_3.nome)
    texto = arquivo.read_text(encoding="utf-8")
    arquivo.write_text(
        texto.replace('"patrimonio": 1', '"patrimonio": 2', 1), encoding="utf-8"
    )
    with pytest.raises(rg.RegistroAlteradoError):
        jg.julgar(papel, P0_3, FIM)


def test_gravacao_depois_do_prazo_reprova_o_p3():
    linha = {
        "registrado_em": "2026-11-10T09:46:00-03:00",
        "prazo": "2026-11-10T09:45:00-03:00",
    }
    assert jg._gravacao_no_prazo(linha) is False
    linha["registrado_em"] = "2026-11-10T09:44:59-03:00"
    assert jg._gravacao_no_prazo(linha) is True
