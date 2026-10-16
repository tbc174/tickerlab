"""Relatório de qualidade de cada montagem das tabelas do modelo 8 (ADR 0027, exigência 7;
critério de pronto, PR D). Sem internet e sem banco: só a regra que compara duas montagens."""

from base.qualidade_da_montagem import Resumo, alertas


def _resumo(linhas, duplicadas=0, escala=None) -> Resumo:
    return Resumo("rotulos_atraso", linhas, duplicadas, escala or {})


def test_montagem_igual_a_anterior_nao_alerta():
    resumo = _resumo({2020: 100, 2021: 110})
    assert alertas(resumo, resumo) == []


def test_primeira_montagem_so_confere_o_que_nao_depende_da_anterior():
    assert alertas(_resumo({2020: 100, 2022: 90}, duplicadas=3), None) == [
        "rotulos_atraso: 3 chaves duplicadas",
        "rotulos_atraso: ano faltando: 2021",
    ]


def test_ano_que_perdeu_linhas_ou_sumiu_alerta():
    anterior = _resumo({2020: 100, 2021: 100, 2022: 100})
    atual = _resumo({2020: 95, 2021: 80})
    assert alertas(atual, anterior) == [
        "rotulos_atraso: 2021 caiu de 100 para 80 linhas (-20%)",
        "rotulos_atraso: 2022 sumiu (tinha 100 linhas)",
    ]


def test_ano_novo_e_crescimento_nao_alertam():
    anterior = _resumo({2020: 100})
    assert alertas(_resumo({2020: 150, 2021: 10}), anterior) == []


def test_escala_que_muda_10_vezes_alerta():
    """Valores em reais que viram milhares (ou o contrário) mudam a mediana mil vezes."""
    anterior = _resumo({2020: 1, 2021: 1}, escala={2020: 5e8, 2021: 6e8})
    atual = _resumo({2020: 1, 2021: 1}, escala={2020: 5.1e8, 2021: 6e5})
    assert alertas(atual, anterior) == [
        "rotulos_atraso: escala de 2021 mudou 1000 vezes (mediana 6e+08 → 6e+05)"
    ]


def test_resumo_vai_e_volta_do_json():
    resumo = _resumo({2020: 100}, duplicadas=1, escala={2020: 2.5})
    assert Resumo.do_json(resumo.para_json()) == resumo
