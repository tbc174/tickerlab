"""Exigência 7 da prontidão: `Porta.perfil`, `base.qualidade_automatica` e o gerador do dia.
Base de mentira, sem nome de pessoa."""

import json

import pandas as pd
import pytest

from base import qualidade_automatica as qa
from base.porta import Porta
from base.qualidade_automatica import REGRAS, Regra, avaliar, sem_explicacao
from scripts import conferir_qualidade


def _perfil(**mudancas):
    base = {"linhas": 10, "vazios_na_chave": {"a": 0}, "repetidas": 0, "por_ano": {}}
    return {**base, **mudancas}


def _anos(**linhas_por_ano):
    return {int(a[1:]): (n, 100.0) for a, n in linhas_por_ano.items()}


@pytest.fixture
def pasta(tmp_path):
    tabela = pd.DataFrame(
        {
            "id": ["A", "A", "B", None, "C"],
            "dia": pd.to_datetime(
                ["2020-03-01", "2020-03-01", "2020-05-01", "2022-01-01", "2022-02-01"]
            ),
            "valor": [5.0, 5.0, 0.0, 7.0, 9.0],
        }
    )
    arquivo = tmp_path / "rede" / "entidades.parquet"
    arquivo.parent.mkdir(parents=True)
    tabela.to_parquet(arquivo, index=False)
    return tmp_path


def test_perfil_mede_vazio_repetida_e_ano(pasta):
    with Porta(pasta) as p:
        perfil = p.perfil("entidades", ("id", "dia"), "dia", "valor")
    assert perfil["linhas"] == 5
    assert perfil["vazios_na_chave"] == {"id": 1, "dia": 0}
    assert perfil["repetidas"] == 1
    assert perfil["por_ano"] == {
        2020: (3, 5.0),
        2022: (2, 8.0),
    }  # o zero não entra na mediana


def test_perfil_recusa_coluna_que_nao_existe(pasta):
    with Porta(pasta) as p, pytest.raises(ValueError, match="nada"):
        p.perfil("entidades", ("nada",))


def test_tabela_limpa_nao_tem_achado():
    assert avaliar(Regra(chave=("a",)), _perfil()) == []


def test_repetida_sem_explicacao_fica_vermelha_e_aceita_com_motivo():
    achados = avaliar(Regra(chave=("a",)), _perfil(repetidas=3))
    assert len(sem_explicacao(achados)) == 1
    aceita = Regra(
        chave=("a",), repetidas_aceitas=3, porque_repetidas="duplicada na fonte"
    )
    assert sem_explicacao(avaliar(aceita, _perfil(repetidas=3))) == []
    assert (
        len(sem_explicacao(avaliar(aceita, _perfil(repetidas=4)))) == 1
    )  # passou do aceito


def test_vazio_na_chave_so_com_explicacao_escrita():
    perfil = _perfil(vazios_na_chave={"a": 2})
    assert len(sem_explicacao(avaliar(Regra(chave=("a",)), perfil))) == 1
    assert (
        sem_explicacao(
            avaliar(Regra(chave=("a",), opcionais={"a": "foto do dia"}), perfil)
        )
        == []
    )


def test_ano_faltando_e_salto_de_linhas():
    regra = Regra(chave=("a",), periodo="d")
    faltando = avaliar(
        regra, _perfil(por_ano=_anos(a2019=10, a2021=10)), ano_em_curso=2030
    )
    assert [a.texto for a in faltando] == ["ano faltando: 2020"]
    salto = avaliar(
        regra, _perfil(por_ano=_anos(a2019=10, a2020=30)), ano_em_curso=2030
    )
    assert len(sem_explicacao(salto)) == 1
    explicada = Regra(
        chave=("a",), periodo="d", saltos_explicados={2020: "entrou a outra origem"}
    )
    assert (
        sem_explicacao(
            avaliar(
                explicada, _perfil(por_ano=_anos(a2019=10, a2020=30)), ano_em_curso=2030
            )
        )
        == []
    )


def test_mudanca_de_escala_do_valor():
    por_ano = {
        2019: (10, 100.0),
        2020: (10, 100_000.0),
    }  # reais virando milhares de reais
    achados = avaliar(
        Regra(chave=("a",), periodo="d"), _perfil(por_ano=por_ano), ano_em_curso=2030
    )
    assert len(sem_explicacao(achados)) == 1


def test_ano_em_curso_nao_e_comparado():
    regra = Regra(chave=("a",), periodo="d")
    assert (
        avaliar(regra, _perfil(por_ano=_anos(a2025=100, a2026=10)), ano_em_curso=2026)
        == []
    )
    assert (
        len(
            avaliar(
                regra, _perfil(por_ano=_anos(a2025=100, a2026=10)), ano_em_curso=2027
            )
        )
        == 1
    )


def test_toda_regra_aponta_colunas_distintas_e_explica_o_que_aceita():
    for tabela, regra in REGRAS.items():
        assert len(set(regra.chave)) == len(regra.chave), tabela
        assert set(regra.opcionais) <= set(regra.chave), tabela
        assert all(regra.opcionais.values()), tabela
        assert bool(regra.repetidas_aceitas) == bool(regra.porque_repetidas), tabela


def test_medir_e_gravar_nao_levam_linha_nenhuma(pasta, monkeypatch, tmp_path):
    regra = Regra(chave=("id",), periodo="dia", valor="valor")
    monkeypatch.setitem(qa.REGRAS, "entidades", regra)
    monkeypatch.setattr(conferir_qualidade, "REGRAS", qa.REGRAS)
    with Porta(pasta) as p:
        resultado = conferir_qualidade.medir(p, "entidades")
    assert resultado["vermelho"] is True  # vazio e repetida sem explicação
    acervo = tmp_path / "acervo"
    monkeypatch.setattr(conferir_qualidade.acervo, "pasta_do_acervo", lambda: acervo)
    destino = conferir_qualidade.gravar("2026-11-11", [resultado])
    assert destino == acervo / "placar" / "2026-11-11" / "qualidade.json"
    gravado = json.loads(destino.read_text(encoding="utf-8"))
    assert gravado["vermelho"] is True
    assert "A" not in json.dumps(gravado["tabelas"][0]["achados"])


def test_gravar_sem_acervo_para(monkeypatch):
    monkeypatch.setattr(conferir_qualidade.acervo, "pasta_do_acervo", lambda: None)
    with pytest.raises(SystemExit):
        conferir_qualidade.gravar("2026-11-11", [])
