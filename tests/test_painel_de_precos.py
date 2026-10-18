"""Painel de preços de referência mensais (Banco Mundial e FMI), lido do acervo de séries."""

from datetime import date

import pandas as pd
import pytest

from src import graficos
from src import precos_de_referencia as precos
from src.banco import series as acervo
from src.commodities import painel_de_precos as painel

MESES = pd.date_range("2025-01-01", "2026-09-01", freq="MS")


def _gravar(banco, codigo: str, valores, divulgado_em: date = date(2026, 10, 5)):
    serie = pd.Series(valores, index=MESES[-len(valores) :], dtype=float)
    with banco.begin() as conexao:
        acervo.garantir_serie(conexao, precos.serie_do_acervo(codigo))
        acervo.gravar(conexao, codigo, serie, divulgado_em)


def _montar(banco, dia: date = date(2026, 10, 18)) -> painel.PainelDePrecos:
    with banco.connect() as conexao:
        return painel.montar_painel(conexao, dia)


def _item(p: painel.PainelDePrecos, chave: str) -> painel.PrecoDeReferencia:
    return next(i for i in p.itens if i.chave == chave)


def _semear_tudo(banco):
    ate_setembro = [float(v) for v in range(1, len(MESES) + 1)]
    for chave in painel.CHAVES_DO_PAINEL:
        _gravar(banco, f"bm-pink-{chave}", ate_setembro)
    for chave in precos.COMPARAVEIS:
        _gravar(banco, f"fmi-{chave}", [v * 1.005 for v in ate_setembro])


def test_ultimo_valor_mes_e_variacao_em_12_meses(banco):
    _gravar(banco, "bm-pink-cafe-arabica", [v for v in range(100, 100 + len(MESES))])
    item = _item(_montar(banco), "cafe-arabica")
    assert item.ultimo_mes == date(2026, 9, 1)
    assert item.ultimo_valor == pytest.approx(100 + len(MESES) - 1)
    anterior = 100 + len(MESES) - 1 - 12
    assert item.variacao_12_meses == pytest.approx(
        (item.ultimo_valor / anterior - 1) * 100
    )
    assert item.unidade == "US$/kg"


def test_cafe_e_algodao_trazem_as_duas_fontes_e_o_resto_so_o_pink_sheet(banco):
    _semear_tudo(banco)
    p = _montar(banco)
    for chave in ("cafe-arabica", "cafe-robusta", "algodao"):
        assert _item(p, chave).historico[-1].fmi is not None
    for chave in ("ureia", "dap", "cloreto-de-potassio"):
        item = _item(p, chave)
        assert all(ponto.fmi is None for ponto in item.historico)
        assert item.nota_das_fontes == painel.NOTA_FONTES_DIFEREM


def test_o_fmi_gravado_para_fertilizante_nao_aparece(banco):
    _gravar(banco, "bm-pink-ureia", [400.0] * 5)
    _gravar(banco, "fmi-ureia", [999.0] * 5)
    assert all(ponto.fmi is None for ponto in _item(_montar(banco), "ureia").historico)


def test_spread_arabica_menos_robusta_do_pink_sheet(banco):
    _gravar(banco, "bm-pink-cafe-arabica", [7.0, 7.5])
    _gravar(banco, "bm-pink-cafe-robusta", [3.5, 3.0])
    spread = _montar(banco).spread
    assert [(s.mes, s.valor) for s in spread] == [
        (date(2026, 8, 1), pytest.approx(3.5)),
        (date(2026, 9, 1), pytest.approx(4.5)),
    ]


def test_spread_so_nos_meses_em_que_as_duas_pontas_existem(banco):
    _gravar(banco, "bm-pink-cafe-arabica", [7.0, 7.5])
    _gravar(banco, "bm-pink-cafe-robusta", [3.5])
    assert [s.mes for s in _montar(banco).spread] == [date(2026, 9, 1)]


def test_como_estava_em_d_nao_usa_revisao_posterior(banco):
    _gravar(banco, "bm-pink-ureia", [400.0, 410.0], divulgado_em=date(2026, 10, 5))
    _gravar(banco, "bm-pink-ureia", [400.0, 450.0], divulgado_em=date(2026, 10, 20))
    antes = _item(_montar(banco, date(2026, 10, 10)), "ureia")
    depois = _item(_montar(banco, date(2026, 10, 25)), "ureia")
    assert antes.ultimo_valor == pytest.approx(410.0)
    assert depois.ultimo_valor == pytest.approx(450.0)


def test_sem_dados_o_painel_vem_vazio_e_nao_quebra(banco):
    p = _montar(banco)
    assert p.itens == ()
    assert p.spread == ()


def test_item_sem_serie_fica_de_fora(banco):
    _gravar(banco, "bm-pink-ureia", [400.0])
    assert [i.chave for i in _montar(banco).itens] == ["ureia"]


def test_mes_sem_valor_nao_vira_zero(banco):
    _gravar(banco, "bm-pink-ureia", [400.0, float("nan"), 420.0])
    meses = [p.mes for p in _item(_montar(banco), "ureia").historico]
    assert date(2026, 8, 1) not in meses


def test_atribuicao_e_aviso_do_preco_diario_sao_os_decididos_pelo_tiago():
    assert painel.ATRIBUICAO == (
        "Fonte: Banco Mundial, Pink Sheet, CC BY 4.0; FMI PCPS."
    )
    assert painel.AVISO_DIARIO == (
        "Preço de referência mensal; o diário depende de licença."
    )


def test_cada_item_do_painel_existe_no_catalogo_de_precos():
    chaves = {item.chave for item in precos.ITENS}
    assert set(painel.CHAVES_DO_PAINEL) <= chaves


def test_grafico_tem_uma_linha_por_fonte_e_so_uma_quando_nao_ha_fmi(banco):
    _semear_tudo(banco)
    p = _montar(banco)
    com_duas = graficos.criar_grafico_preco_de_referencia(_item(p, "cafe-arabica"))
    com_uma = graficos.criar_grafico_preco_de_referencia(_item(p, "ureia"))
    assert len(com_duas.data) == 2
    assert len(com_uma.data) == 1


def test_grafico_do_spread(banco):
    _gravar(banco, "bm-pink-cafe-arabica", [7.0, 7.5])
    _gravar(banco, "bm-pink-cafe-robusta", [3.5, 3.0])
    figura = graficos.criar_grafico_spread_do_cafe(_montar(banco).spread)
    assert len(figura.data) == 1
    with pytest.raises(ValueError):
        graficos.criar_grafico_spread_do_cafe(())
