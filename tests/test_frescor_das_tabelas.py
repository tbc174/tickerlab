"""Frescor de cada tabela do conector, pelo mapa tabela -> fontes de coleta (foco "base em dia", parte 2).

O frescor de uma tabela é o da fonte mais atrasada que a alimenta: uma fonte parada esconde-se atrás
das outras se a conta for pela mais nova.
"""

import json
from datetime import UTC, datetime, timedelta

from scripts import frescor_das_fontes as script
from src import frescor_das_tabelas as modulo
from src.banco.coletas import registrar
from src.frescor_das_tabelas import (
    frequencias_do_conector,
    frescor_das_tabelas,
    periodo_do_rotulo,
)

AGORA = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def _registrar(motor, fonte: str, situacao: str, ha: timedelta) -> None:
    with motor.begin() as conexao:
        registrar(
            conexao,
            fonte,
            f"https://dados.exemplo.gov.br/{fonte}",
            b"x" if situacao == "ok" else None,
            situacao,
            agora=AGORA - ha,
        )


def _frescor(motor, tabelas: dict[str, str], mapa: dict[str, tuple[str, ...]]):
    with motor.connect() as conexao:
        return {
            f.tabela: f
            for f in frescor_das_tabelas(conexao, tabelas, AGORA, fontes_de=mapa.get)
        }


def test_rotulos_da_frequencia_viram_periodos():
    assert periodo_do_rotulo("Diária") == timedelta(days=1)
    assert periodo_do_rotulo("Semanal") == timedelta(days=7)
    assert periodo_do_rotulo("Mensal") == timedelta(days=31)
    assert periodo_do_rotulo("Trimestral") == timedelta(days=92)
    assert periodo_do_rotulo("Anual") == timedelta(days=366)
    assert periodo_do_rotulo("Sem calendário fixo") is None


def test_tabela_mensal_com_coleta_recente_esta_fresca(banco):
    _registrar(banco, "anac-estatistico", "ok", timedelta(days=10))

    f = _frescor(
        banco,
        {"anac_estatistico": "Mensal"},
        {"anac_estatistico": ("anac-estatistico",)},
    )["anac_estatistico"]

    assert f.situacao == "fresca"
    assert f.ultima_ok == AGORA - timedelta(days=10)
    assert f.fontes == ("anac-estatistico",)


def test_tabela_mensal_parada_ha_40_dias_esta_velha(banco):
    _registrar(banco, "anac-estatistico", "ok", timedelta(days=40))

    f = _frescor(
        banco,
        {"anac_estatistico": "Mensal"},
        {"anac_estatistico": ("anac-estatistico",)},
    )["anac_estatistico"]

    assert f.situacao == "velha"


def test_vale_a_fonte_mais_atrasada_e_o_resultado_diz_qual(banco):
    _registrar(banco, "cvm-hist-dfp", "ok", timedelta(hours=3))
    _registrar(banco, "cvm-dfp-itr", "ok", timedelta(days=9))

    f = _frescor(
        banco,
        {"demonstracoes_como_era": "Diária"},
        {"demonstracoes_como_era": ("cvm-hist-dfp", "cvm-dfp-itr")},
    )["demonstracoes_como_era"]

    assert f.situacao == "velha"
    assert f.fonte_mais_atrasada == "cvm-dfp-itr"
    assert f.ultima_ok == AGORA - timedelta(days=9)


def test_fonte_que_nunca_trouxe_dado_deixa_a_tabela_como_nunca(banco):
    _registrar(banco, "cvm-hist-dfp", "ok", timedelta(hours=3))
    _registrar(banco, "cvm-dfp-itr", "falhou", timedelta(hours=3))

    f = _frescor(
        banco,
        {"demonstracoes_como_era": "Diária"},
        {"demonstracoes_como_era": ("cvm-hist-dfp", "cvm-dfp-itr")},
    )["demonstracoes_como_era"]

    assert f.situacao == "nunca"
    assert f.fonte_mais_atrasada == "cvm-dfp-itr"


def test_tabela_sem_calendario_mostra_a_data_sem_ficar_vermelha(banco):
    _registrar(banco, "ans-beneficiarios-operadora", "ok", timedelta(days=200))

    f = _frescor(
        banco,
        {"ans_beneficiarios": "Sem calendário fixo"},
        {"ans_beneficiarios": ("ans-beneficiarios-operadora",)},
    )["ans_beneficiarios"]

    assert f.situacao == "sem_prazo"
    assert f.ultima_ok == AGORA - timedelta(days=200)
    assert f.vence_em is None


def test_tabela_sem_fonte_no_mapa_aparece_como_sem_fonte(banco):
    f = _frescor(banco, {"rotulos_atraso": "Sem calendário fixo"}, {})["rotulos_atraso"]

    assert f.situacao == "sem_fonte"
    assert f.fontes == ()


def test_tentativa_que_falhou_depois_nao_renova_a_tabela(banco):
    _registrar(banco, "anac-estatistico", "ok", timedelta(days=40))
    _registrar(banco, "anac-estatistico", "nao_encontrado", timedelta(hours=1))

    f = _frescor(
        banco,
        {"anac_estatistico": "Mensal"},
        {"anac_estatistico": ("anac-estatistico",)},
    )["anac_estatistico"]

    assert f.situacao == "velha"


def test_dicionario_vai_para_json(banco):
    _registrar(banco, "anac-estatistico", "ok", timedelta(days=10))

    f = _frescor(
        banco,
        {"anac_estatistico": "Mensal"},
        {"anac_estatistico": ("anac-estatistico",)},
    )["anac_estatistico"]

    assert f.como_dicionario() == {
        "tabela": "anac_estatistico",
        "situacao": "fresca",
        "frequencia": "Mensal",
        "fontes": ["anac-estatistico"],
        "fonte_mais_atrasada": "anac-estatistico",
        "ultima_ok": "2026-11-15T12:00:00+00:00",
        "vence_em": "2026-12-20T12:00:00+00:00",
    }


def test_frequencias_do_conector_cobrem_toda_tabela_consultavel():
    from base import dossie as regras
    from base.dicionario import TABELAS

    frequencias = frequencias_do_conector()

    assert set(frequencias) == {n for n in TABELAS if regras.pode_consultar(n)}
    assert set(frequencias.values()) <= {
        "Diária",
        "Semanal",
        "Mensal",
        "Trimestral",
        "Anual",
        "Sem calendário fixo",
    }


def test_script_escreve_tambem_o_frescor_das_tabelas(banco, tmp_path):
    _registrar(banco, "anac-estatistico", "ok", timedelta(days=40))
    saida = tmp_path / "frescor.json"

    codigo = script.main(["--saida", str(saida), "--agora", AGORA.isoformat()])

    assert codigo == 0
    conteudo = json.loads(saida.read_text(encoding="utf-8"))
    assert "fontes" in conteudo  # o painel do Kuma segue lendo as fontes
    por_tabela = {t["tabela"]: t for t in conteudo["tabelas"]}
    assert por_tabela["anac_estatistico"]["situacao"] == "velha"
    assert por_tabela["rotulos_atraso"]["situacao"] == "sem_fonte"
    assert modulo.SITUACOES_DA_TABELA  # o painel conhece as situações possíveis
