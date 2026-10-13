"""Testes de src/linha_do_tempo.py: o preço em base 100 e os acontecimentos no mesmo eixo."""

from datetime import date

import pandas as pd
import pytest

from src import linha_do_tempo as ldt
from src.banco.eventos import Evento

PALAVRAS_DE_CAUSA = (
    "por causa",
    "causou",
    "provocou",
    "fez o preço",
    "fez a ação",
    "derrubou",
    "impulsionou",
)


def _fechamento():
    dias = pd.bdate_range("2026-01-02", periods=60)
    return pd.Series([20.0 + i * 0.1 for i in range(60)], index=dias)


def _evento(publicado_em, materialidade=80, rotulo="Fato relevante", assunto="Assunto"):
    return Evento(
        ticker="PETR4.SA",
        empresa="Petrobras",
        rotulo=rotulo,
        tema="eventos",
        materialidade=materialidade,
        assunto=assunto,
        referencia=None,
        publicado_em=publicado_em,
        link="https://www.rad.cvm.gov.br/doc",
        fonte="cvm_ipe",
        protocolo=f"p-{publicado_em}-{materialidade}",
        versao=1,
    )


def test_curva_da_linha_do_tempo_comeca_em_100():
    linha = ldt.montar_linha_do_tempo(_fechamento(), [])
    assert linha.curva[0].valor == 100.0
    assert linha.curva[-1].valor == pytest.approx(25.9 / 20.0 * 100)
    assert not hasattr(
        linha.curva[0], "preco"
    )  # preço bruto não sai daqui (ADR 0048, item 6)


def test_marcos_respeitam_a_materialidade_minima():
    eventos = [_evento(date(2026, 1, 5), 80), _evento(date(2026, 1, 6), 20)]
    linha = ldt.montar_linha_do_tempo(_fechamento(), eventos, materialidade_minima=50)
    assert [m.data for m in linha.marcos] == [date(2026, 1, 5)]
    assert linha.fora_do_grafico == 1


def test_marcos_fora_do_periodo_saem():
    eventos = [
        _evento(date(2025, 12, 1)),
        _evento(date(2026, 2, 2)),
        _evento(date(2026, 9, 1)),
    ]
    linha = ldt.montar_linha_do_tempo(_fechamento(), eventos)
    assert [m.data for m in linha.marcos] == [date(2026, 2, 2)]


def test_marco_em_dia_sem_pregao_fica_no_proximo_pregao():
    sabado = date(2026, 1, 10)
    linha = ldt.montar_linha_do_tempo(_fechamento(), [_evento(sabado)])
    marco = linha.marcos[0]
    assert marco.data == sabado  # a data do fato não muda
    assert marco.dia_no_grafico == date(2026, 1, 12)  # o ponto fica na segunda-feira


def test_limite_de_marcos_guarda_os_mais_relevantes_em_ordem_de_data():
    eventos = [_evento(date(2026, 1, 5 + i), 50 + i) for i in range(10)]
    linha = ldt.montar_linha_do_tempo(_fechamento(), eventos, maximo=3)
    assert [m.materialidade for m in linha.marcos] == [57, 58, 59]
    assert [m.data for m in linha.marcos] == sorted(m.data for m in linha.marcos)
    assert linha.fora_do_grafico == 7


def test_textos_da_linha_do_tempo_nao_dizem_que_um_fato_causou_o_preco():
    linha = ldt.montar_linha_do_tempo(_fechamento(), [_evento(date(2026, 1, 5))])
    textos = [ldt.descricao_do_marco(m) for m in linha.marcos]
    assert all(not any(p in t.lower() for p in PALAVRAS_DE_CAUSA) for t in textos)
    assert "não diz se um fato" in ldt.AVISO_DA_LINHA


def test_descricao_do_marco_tem_data_rotulo_e_assunto():
    linha = ldt.montar_linha_do_tempo(
        _fechamento(), [_evento(date(2026, 1, 5), assunto="Pagamento de dividendos")]
    )
    assert ldt.descricao_do_marco(linha.marcos[0]) == (
        "05/01/2026 · Fato relevante: Pagamento de dividendos"
    )


def test_sem_preco_nao_monta():
    with pytest.raises(ValueError, match="preço"):
        ldt.montar_linha_do_tempo(pd.Series(dtype=float), [])
