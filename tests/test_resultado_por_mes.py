"""O resultado realizado por mês a partir da negociação da B3: day trade, operações comuns,
FIIs e futuros. Valores inventados; as regras do day trade são as usuais da Receita."""

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.dividendos_e_custo import Lancamento
from src.negociacao_b3 import NegociacaoB3, Negocio
from src.resultado_por_mes import resultado_por_mes

DIA = date(2026, 3, 10)


def _n(lado, quantidade, preco, codigo="PETR4", classe="acao", data=DIA, valor=None):
    valor = quantidade * preco if valor is None else valor
    return Negocio(data, codigo, classe, lado == "c", quantidade, preco, valor)


def _neg(*negocios):
    return NegociacaoB3(tuple(negocios), 0, (), DIA, DIA)


def _mes(resultado, ano=2026, mes=3):
    (achado,) = [m for m in resultado.meses if (m.ano, m.mes) == (ano, mes)]
    return achado


def test_compra_e_venda_em_dias_diferentes_e_operacao_comum():
    resultado = resultado_por_mes(
        _neg(_n("c", 100, 10.0), _n("v", 100, 12.0, data=date(2026, 3, 20))), eventos=()
    )
    mes = _mes(resultado)
    assert mes.acoes_comum == pytest.approx(200)
    assert mes.acoes_day_trade == 0
    assert mes.vendas_de_acoes == pytest.approx(1200)


def test_day_trade_separado_da_operacao_comum():
    # compra 200 a 10 e vende 100 a 12 no mesmo dia: 100 em day trade (+200) e 100 ficam
    # na carteira ao custo de 10; vendidas a 11 no dia 20, dão +100 em operação comum
    resultado = resultado_por_mes(
        _neg(
            _n("c", 200, 10.0),
            _n("v", 100, 12.0),
            _n("v", 100, 11.0, data=date(2026, 3, 20)),
        ),
        eventos=(),
    )
    mes = _mes(resultado)
    assert mes.acoes_day_trade == pytest.approx(200)
    assert mes.acoes_comum == pytest.approx(100)
    assert mes.vendas_de_acoes == pytest.approx(1100)  # o day trade não entra


def test_day_trade_usa_os_precos_medios_do_dia():
    resultado = resultado_por_mes(
        _neg(
            _n("c", 100, 10.0),
            _n("c", 100, 12.0),
            _n("v", 200, 12.0),
        ),
        eventos=(),
    )
    assert _mes(resultado).acoes_day_trade == pytest.approx(200)  # vende 12, médio 11


def test_venda_sem_compra_no_periodo_fica_sem_resultado_e_fora_do_total():
    resultado = resultado_por_mes(_neg(_n("v", 100, 12.0)), eventos=())
    mes = _mes(resultado)
    assert mes.acoes_comum == 0
    assert mes.vendas_de_acoes == pytest.approx(1200)  # o total vendido se sabe
    ((codigo, motivo),) = resultado.sem_resultado
    assert codigo == "PETR4" and "negociação" in motivo


def test_day_trade_de_ativo_sem_historico_continua_valendo():
    resultado = resultado_por_mes(
        _neg(_n("c", 100, 10.0), _n("v", 200, 11.0)), eventos=()
    )
    assert _mes(resultado).acoes_day_trade == pytest.approx(100)
    assert [c for c, _ in resultado.sem_resultado] == ["PETR4"]


def test_futuro_que_zera_no_dia_da_vendas_menos_compras():
    resultado = resultado_por_mes(
        _neg(
            _n("c", 2, 130000, "WINJ26", "futuro", valor=52000.0),
            _n("v", 2, 130500, "WINJ26", "futuro", valor=52200.0),
        ),
        eventos=(),
    )
    assert _mes(resultado).futuros == pytest.approx(200)
    assert not resultado.avisos


def test_futuro_que_passa_de_um_dia_para_outro_fica_de_fora_com_aviso():
    resultado = resultado_por_mes(
        _neg(
            _n("c", 1, 130000, "WINJ26", "futuro", valor=26000.0),
            _n(
                "v",
                1,
                131000,
                "WINJ26",
                "futuro",
                valor=26200.0,
                data=date(2026, 3, 11),
            ),
        ),
        eventos=(),
    )
    assert all(m.futuros == 0 for m in resultado.meses)
    assert any("ajuste diário" in aviso for aviso in resultado.avisos)


def test_fii_vai_para_a_coluna_dos_fiis():
    resultado = resultado_por_mes(
        _neg(
            _n("c", 10, 100.0, "HGLG11", "fii"),
            _n("v", 10, 110.0, "HGLG11", "fii", data=date(2026, 3, 20)),
        ),
        eventos=(),
    )
    mes = _mes(resultado)
    assert mes.fiis == pytest.approx(100)
    assert mes.acoes_comum == 0 and mes.vendas_de_acoes == 0


def test_outros_vao_para_a_coluna_outros():
    resultado = resultado_por_mes(
        _neg(
            _n("c", 10, 100.0, "KNCR11", "outros"),
            _n("v", 10, 105.0, "KNCR11", "outros", data=date(2026, 3, 20)),
        ),
        eventos=(),
    )
    assert _mes(resultado).outros == pytest.approx(50)


def test_meses_separados_e_em_ordem():
    resultado = resultado_por_mes(
        _neg(
            _n("c", 100, 10.0, data=date(2026, 1, 5)),
            _n("v", 50, 12.0, data=date(2026, 1, 20)),
            _n("v", 50, 9.0, data=date(2026, 3, 2)),
        ),
        eventos=(),
    )
    assert [(m.ano, m.mes) for m in resultado.meses] == [(2026, 1), (2026, 3)]
    assert _mes(resultado, mes=1).acoes_comum == pytest.approx(100)
    assert _mes(resultado, mes=3).acoes_comum == pytest.approx(-50)


def test_desdobro_da_movimentacao_entra_na_sequencia_do_custo():
    resultado = resultado_por_mes(
        _neg(
            _n("c", 100, 10.0, data=date(2026, 1, 5)),
            _n("v", 200, 6.0, data=date(2026, 3, 2)),
        ),
        eventos=[Lancamento(date(2026, 2, 1), "PETR4", "desdobro", 100)],
    )
    assert _mes(resultado).acoes_comum == pytest.approx(200)  # 1200 − 1000
    assert not resultado.sem_resultado


def test_proventos_da_movimentacao_nao_entram():
    resultado = resultado_por_mes(
        _neg(
            _n("c", 100, 10.0, data=date(2026, 1, 5)),
            _n("v", 100, 10.0, data=date(2026, 3, 2)),
        ),
        eventos=[Lancamento(date(2026, 2, 1), "PETR4", "dividendo", 100, 50.0)],
    )
    assert _mes(resultado).acoes_comum == pytest.approx(0)


def test_sem_a_movimentacao_avisa_dos_desdobros():
    resultado = resultado_por_mes(_neg(_n("c", 100, 10.0)))
    assert any("desdobro" in aviso for aviso in resultado.avisos)


def test_negociacao_vazia_nao_tem_meses():
    resultado = resultado_por_mes(NegociacaoB3((), 0, (), None, None), eventos=())
    assert resultado.meses == ()


# ---- propriedade: quando a posição começa e termina zerada, a soma dos resultados (day trade
# e operações comuns) é o que entrou com as vendas menos o que saiu com as compras ----

dias_de_negocio = st.lists(
    st.tuples(
        st.integers(0, 300),  # quantidade comprada no dia
        st.floats(1, 100, allow_nan=False),  # preço da compra
        st.floats(0, 1),  # parte da posição (com a compra do dia) vendida no dia
        st.floats(1, 100, allow_nan=False),  # preço da venda
    ),
    min_size=1,
    max_size=12,
)


@given(dias_de_negocio, st.floats(1, 100, allow_nan=False))
def test_soma_dos_resultados_e_vendas_menos_compras(dias, preco_final):
    negocios, posicao = [], 0
    for i, (comprada, preco_compra, parte, preco_venda) in enumerate(dias):
        dia = date(2026, 1, 1 + 2 * i)
        if comprada:
            negocios.append(_n("c", comprada, preco_compra, data=dia))
        vendida = int(parte * (posicao + comprada))
        if vendida:
            negocios.append(_n("v", vendida, preco_venda, data=dia))
        posicao += comprada - vendida
    if posicao:
        negocios.append(_n("v", posicao, preco_final, data=date(2026, 2, 28)))
    resultado = resultado_por_mes(_neg(*negocios), eventos=())
    total = sum(m.acoes_comum + m.acoes_day_trade for m in resultado.meses)
    esperado = sum(n.valor for n in negocios if not n.compra) - sum(
        n.valor for n in negocios if n.compra
    )
    assert not resultado.sem_resultado
    assert total == pytest.approx(esperado, abs=1e-6, rel=1e-9)
