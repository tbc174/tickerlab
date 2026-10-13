"""Testes de src/pulse.py: o que mudou nos ativos da pessoa desde a última visita."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from src import pulse
from src.banco.eventos import Evento
from src.research import COMPONENTES

PESOS_PADRAO = {c: 100 / len(COMPONENTES) for c in COMPONENTES}

AGORA = datetime(2026, 10, 13, 21, 0, tzinfo=UTC)  # 18h em São Paulo


def _evento(ticker: str, publicado_em: date, protocolo: str = "p1") -> Evento:
    return Evento(
        ticker=ticker,
        empresa="EMPRESA",
        rotulo="Fato relevante",
        tema="eventos",
        materialidade=90,
        assunto="Assunto",
        referencia=None,
        publicado_em=publicado_em,
        link="https://www.rad.cvm.gov.br/x",
        fonte="cvm_ipe",
        protocolo=protocolo,
        versao=1,
    )


def _fechamentos(datas_e_precos: dict[str, float]) -> pd.Series:
    return pd.Series(
        list(datas_e_precos.values()), index=pd.to_datetime(list(datas_e_precos))
    )


# --- janela ---------------------------------------------------------------------------------


def test_primeira_visita_mostra_os_ultimos_sete_dias():
    janela = pulse.janela(None, AGORA)
    assert janela.primeira_vez
    assert janela.desde == AGORA - timedelta(days=7)
    assert janela.ate == AGORA


def test_janela_vai_da_ultima_visita_ate_agora():
    visita = AGORA - timedelta(days=2)
    janela = pulse.janela(visita, AGORA)
    assert not janela.primeira_vez
    assert (janela.desde, janela.ate) == (visita, AGORA)


def test_publicados_ate_trinta_dias_antes_da_visita():
    janela = pulse.janela(AGORA - timedelta(days=2), AGORA)
    assert janela.publicados_desde == date(2026, 9, 11)


def test_visita_no_futuro_vira_janela_vazia_e_nao_quebra():
    """Relógio adiantado em outra máquina: nada de janela invertida."""
    janela = pulse.janela(AGORA + timedelta(hours=1), AGORA)
    assert janela.desde == janela.ate == AGORA


def test_janela_sem_fuso_e_recusada():
    with pytest.raises(ValueError, match="fuso"):
        pulse.janela(None, datetime(2026, 10, 13, 18, 0))  # noqa: DTZ001


def test_texto_da_janela_em_portugues_no_fuso_de_sao_paulo():
    assert pulse.texto_da_janela(pulse.janela(AGORA - timedelta(days=1), AGORA)) == (
        "Desde a sua última visita, em 12/10/2026 às 18h00."
    )
    assert pulse.texto_da_janela(pulse.janela(None, AGORA)) == (
        "Primeira visita: o que aconteceu nos últimos 7 dias."
    )


# --- ativos da pessoa -----------------------------------------------------------------------


def test_ativos_juntam_tudo_sem_repetir_e_guardam_de_onde_vieram():
    ativos, fora = pulse.ativos_da_pessoa(
        favoritos=["petr4", "AAPL"],
        carteira=["PETR4.SA", "VALE3.SA"],
        listas=[("Bancos", ["ITUB4.SA", "AAPL"])],
        estrategias=["vale3", "BTC-USD"],
    )
    assert fora == 0
    assert [(a.ticker, a.origens) for a in ativos] == [
        ("PETR4.SA", ("favoritos", "Minha carteira")),
        ("AAPL", ("favoritos", "lista Bancos")),
        ("VALE3.SA", ("Minha carteira", "estratégias salvas")),
        ("ITUB4.SA", ("lista Bancos",)),
        ("BTC-USD", ("estratégias salvas",)),
    ]


def test_ativos_vazios_e_ticker_em_branco_ficam_de_fora():
    ativos, fora = pulse.ativos_da_pessoa([" "], [], [("Vazia", [])], [""])
    assert (ativos, fora) == ((), 0)


def test_ativos_alem_do_limite_sao_contados_e_ficam_de_fora():
    tickers = [f"T{i}" for i in range(pulse.MAXIMO_DE_ATIVOS + 5)]
    ativos, fora = pulse.ativos_da_pessoa(tickers, [], [], [])
    assert len(ativos) == pulse.MAXIMO_DE_ATIVOS
    assert fora == 5
    assert ativos[0].ticker == "T0"  # a ordem de quem a pessoa escolheu primeiro vale


# --- variação -------------------------------------------------------------------------------


def test_variacao_do_ultimo_pregao_antes_da_visita_ate_o_ultimo():
    precos = _fechamentos(
        {"2026-10-08": 10.0, "2026-10-09": 11.0, "2026-10-12": 12.0, "2026-10-13": 13.2}
    )
    # visita no sábado (10/10): a base é o fechamento de sexta (09/10)
    visita = datetime(2026, 10, 10, 15, 0, tzinfo=UTC)
    v = pulse.variacao("PETR4.SA", precos, visita)
    assert v is not None
    assert (v.de, v.preco_de, v.ate, v.preco_ate) == (
        date(2026, 10, 9),
        11.0,
        date(2026, 10, 13),
        13.2,
    )
    assert v.retorno == pytest.approx(0.2)


def test_visita_antes_do_fechamento_nao_usa_o_preco_do_mesmo_dia():
    """Às 11h de 12/10 o fechamento de 12/10 ainda não existia: a base é 09/10."""
    precos = _fechamentos({"2026-10-09": 11.0, "2026-10-12": 12.0, "2026-10-13": 13.0})
    visita = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)  # 11h em São Paulo
    v = pulse.variacao("PETR4.SA", precos, visita)
    assert v is not None and v.de == date(2026, 10, 9)


def test_visita_depois_do_fechamento_usa_o_preco_do_mesmo_dia():
    precos = _fechamentos({"2026-10-09": 11.0, "2026-10-12": 12.0, "2026-10-13": 13.0})
    visita = datetime(2026, 10, 12, 22, 0, tzinfo=UTC)  # 19h em São Paulo
    v = pulse.variacao("PETR4.SA", precos, visita)
    assert v is not None and v.de == date(2026, 10, 12)


def test_sem_pregao_novo_depois_da_visita_nao_tem_variacao():
    precos = _fechamentos({"2026-10-09": 11.0, "2026-10-12": 12.0})
    visita = datetime(2026, 10, 12, 22, 0, tzinfo=UTC)
    assert pulse.variacao("PETR4.SA", precos, visita) is None


def test_sem_preco_antes_da_visita_nao_tem_variacao():
    precos = _fechamentos({"2026-10-12": 12.0, "2026-10-13": 13.0})
    visita = datetime(2026, 10, 1, 22, 0, tzinfo=UTC)
    assert pulse.variacao("NOVO3.SA", precos, visita) is None


@given(
    precos=st.lists(
        st.floats(min_value=0.01, max_value=1e6, allow_nan=False),
        min_size=2,
        max_size=40,
    ),
    corte=st.integers(min_value=0, max_value=39),
    horas=st.integers(min_value=0, max_value=23),
)
def test_preco_depois_da_visita_nunca_vira_a_base(precos, corte, horas):
    """Sem olhar o futuro: a base é sempre de um dia já fechado na hora da visita."""
    datas = pd.bdate_range("2026-01-01", periods=len(precos))
    serie = pd.Series(precos, index=datas)
    dia = datas[min(corte, len(datas) - 1)]
    visita = datetime(dia.year, dia.month, dia.day, horas, 0, tzinfo=UTC)
    v = pulse.variacao("X", serie, visita)
    if v is not None:
        fechamento = datetime(
            v.de.year, v.de.month, v.de.day, 21, 0, tzinfo=UTC
        )  # 18h em São Paulo
        assert fechamento <= visita
        assert v.ate > v.de


def test_variacoes_em_ordem_da_maior_mudanca():
    a = pulse.Variacao("A", date(2026, 10, 9), 10, date(2026, 10, 13), 10.5)
    b = pulse.Variacao("B", date(2026, 10, 9), 10, date(2026, 10, 13), 8.0)
    assert [v.ticker for v in pulse.ordenar_variacoes([a, b])] == ["B", "A"]


def test_texto_da_variacao():
    v = pulse.Variacao("PETR4.SA", date(2026, 10, 9), 11.0, date(2026, 10, 13), 13.2)
    assert pulse.texto_da_variacao(v) == "PETR4: +20,0% (de 09/10 a 13/10)"


# --- acontecimentos -------------------------------------------------------------------------


def test_acontecimentos_explicam_de_onde_vem_o_ativo():
    ativos, _ = pulse.ativos_da_pessoa(
        ["PETR4.SA"], [], [("Energia", ["PETR4.SA"])], []
    )
    janela = pulse.janela(AGORA - timedelta(days=1), AGORA)
    itens = pulse.acontecimentos(
        [_evento("PETR4.SA", date(2026, 10, 13))],
        ativos,
        janela,
        PESOS_PADRAO,
        ["eventos"],
    )
    assert len(itens) == 1
    assert itens[0].razoes[0] == "Você acompanha PETR4 em: favoritos, lista Energia."


def test_acontecimentos_vazios():
    janela = pulse.janela(None, AGORA)
    assert pulse.acontecimentos([], (), janela, PESOS_PADRAO, []) == []
