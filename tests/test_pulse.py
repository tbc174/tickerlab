"""Testes de src/pulse.py: o que mudou nos ativos da pessoa desde a última visita."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from src import pulse
from src.banco.eventos import Evento
from src.diario_de_teses import Anotacao
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


@pytest.mark.parametrize(
    ("dias", "periodo"),
    [(1, "6mo"), (150, "6mo"), (200, "1y"), (500, "2y"), (900, "5y"), (4000, "5y")],
)
def test_periodo_de_precos_cobre_a_visita_com_folga(dias, periodo):
    janela = pulse.janela(AGORA - timedelta(days=dias), AGORA)
    assert pulse.periodo_de_precos(janela) == periodo


def test_ticker_estranho_de_simulacao_salva_fica_de_fora():
    """O retrato da simulação vem do banco: não confiável (não texto ou comprido demais)."""
    ativos, _ = pulse.ativos_da_pessoa([], [], [], ["PETR4", 42, None, "X" * 21])
    assert [a.ticker for a in ativos] == ["PETR4.SA"]


# --- vereditos das estratégias salvas (PR E2) ---------------------------------------------


@dataclass
class _Simulacao:
    id: str
    tipo: str = "backtest"
    nome: str = "Minha estratégia"
    parametros: dict = field(default_factory=lambda: {"ticker": "PETR4.SA"})
    resultado: dict = field(
        default_factory=lambda: {
            "ficha": {"pedido": {"versao": 1}, "veredito": "passou"}
        }
    )


def test_estrategias_salvas_so_backtests_com_ficha_ate_o_limite():
    simulacoes = [
        _Simulacao("a"),
        _Simulacao("carteira", tipo="carteira"),
        _Simulacao("antiga", resultado={"numeros": {}}),
        _Simulacao("b"),
        _Simulacao("c"),
    ]
    salvas, sem_ficha, fora = pulse.estrategias_salvas(simulacoes, maximo=2)
    assert [e.id for e in salvas] == ["a", "b"]
    assert (sem_ficha, fora) == (1, 1)
    assert salvas[0].veredito_ao_salvar == "passou"


def test_estrategia_salva_com_ficha_estranha_conta_como_sem_ficha():
    simulacoes = [
        _Simulacao("x", resultado={"ficha": "texto"}),
        _Simulacao("y", resultado=None),  # type: ignore[arg-type]
    ]
    assert pulse.estrategias_salvas(simulacoes) == ((), 2, 0)


def test_veredito_ao_salvar_estranho_vira_desconhecido():
    sim = _Simulacao("a", resultado={"ficha": {"pedido": {}, "veredito": "ótimo"}})
    (salva,), _, _ = pulse.estrategias_salvas([sim])
    assert salva.veredito_ao_salvar is None


def test_antes_e_o_visto_no_pulse_ou_o_da_hora_de_salvar():
    (salva,), _, _ = pulse.estrategias_salvas([_Simulacao("a")])
    assert pulse.comparar(salva, {}, "não passou").antes == "passou"
    assert (
        pulse.comparar(salva, {"a": "inconclusivo"}, "passou").antes == "inconclusivo"
    )
    assert pulse.comparar(salva, {"a": "estranho"}, "passou").antes == "passou"


def test_mudou_so_quando_os_dois_vereditos_existem_e_diferem():
    (salva,), _, _ = pulse.estrategias_salvas([_Simulacao("a")])
    assert pulse.comparar(salva, {}, "não passou").mudou
    assert not pulse.comparar(salva, {}, "passou").mudou
    assert not pulse.comparar(salva, {}, None).mudou  # não deu para conferir agora


def test_vereditos_para_guardar_juntam_os_novos_e_esquecem_as_apagadas():
    (a, b), _, _ = pulse.estrategias_salvas([_Simulacao("a"), _Simulacao("b")])
    conferidos = [pulse.comparar(a, {}, "não passou"), pulse.comparar(b, {}, None)]
    vistos = {"b": "passou", "apagada": "passou"}
    assert pulse.vereditos_para_guardar(vistos, conferidos, {"a", "b"}) == {
        "a": "não passou",
        "b": "passou",  # não deu para conferir: fica o que ela já tinha visto
    }


def test_texto_do_veredito_que_mudou():
    (salva,), _, _ = pulse.estrategias_salvas([_Simulacao("a")])
    assert pulse.texto_do_veredito(pulse.comparar(salva, {}, "não passou")) == (
        '**Minha estratégia**: o veredito da ficha "Foi sorte?" mudou de **passou** para '
        "**não passou** com os dados de hoje."
    )


@pytest.mark.parametrize(
    ("pedido", "precisa"),
    [
        ({"usa_cdi": True}, True),
        ({"usa_cdi": False}, False),
        ({"usa_cdi": "sim"}, False),
        (None, False),
    ],
)
def test_precisa_do_cdi_so_com_o_sim_de_verdade(pedido, precisa):
    assert pulse.precisa_do_cdi(pedido) is precisa


# --- a tese do Diário ligada à estratégia (PR F2) ---------------------------------------------


def _tese(dia, estrategias, texto="Comprei pelo dividendo."):
    return Anotacao(
        uuid.uuid4(), "PETR4.SA", texto, AGORA.replace(day=dia), tuple(estrategias)
    )


def test_cada_estrategia_fica_com_a_tese_ligada_mais_nova():
    a, b = uuid.uuid4(), uuid.uuid4()
    velha, nova, so_b = _tese(1, [a]), _tese(10, [a]), _tese(5, [b])
    assert pulse.teses_por_estrategia([velha, so_b, nova]) == {
        str(a): nova,
        str(b): so_b,
    }
    assert pulse.teses_por_estrategia([]) == {}


def test_texto_da_tese_ligada_traz_a_data_e_um_trecho_curto():
    tese = _tese(10, [], "palavra " * 100)
    texto = pulse.texto_da_tese_ligada(tese)
    assert texto.startswith("Sua tese sobre PETR4 em 10/10/2026 às 18h00: “palavra")
    assert texto.endswith("…”") and len(texto) < 280


# --- o Pulse pela API (Workspace, PR 2): a janela da aba e o selo da mudança ------------------


def test_janela_da_aba_sem_desde_e_a_de_sempre():
    visita = AGORA - timedelta(days=2)
    assert pulse.janela_da_aba(visita, AGORA, None) == pulse.janela(visita, AGORA)
    assert pulse.janela_da_aba(None, AGORA, None) == pulse.janela(None, AGORA)


def test_janela_da_aba_com_desde_so_amplia():
    """O F5 reenvia o início que a aba mostrava: a janela volta a ele, nunca encolhe."""
    visita = AGORA - timedelta(minutes=10)
    inicio_da_aba = AGORA - timedelta(days=7, minutes=10)
    j = pulse.janela_da_aba(visita, AGORA, inicio_da_aba)
    assert (j.desde, j.ate) == (inicio_da_aba, AGORA)
    assert j.guardada_na_aba and not j.primeira_vez
    assert pulse.texto_da_janela(j) == (
        "O que mudou desde 06/10/2026 às 17h50 (a janela que esta aba já mostrava)."
    )
    # um `desde` depois da última visita não encurta a janela
    tarde = pulse.janela_da_aba(visita, AGORA, AGORA - timedelta(minutes=1))
    assert tarde == pulse.janela(visita, AGORA)


def test_janela_da_aba_corta_em_30_dias_e_recusa_sem_fuso():
    j = pulse.janela_da_aba(AGORA, AGORA, AGORA - timedelta(days=400))
    assert j.desde == AGORA - pulse.JANELA_MAXIMA_DA_ABA
    assert timedelta(days=30) == pulse.JANELA_MAXIMA_DA_ABA
    with pytest.raises(ValueError, match="fuso"):
        pulse.janela_da_aba(None, AGORA, datetime(2026, 10, 1))  # noqa: DTZ001 (sem fuso de propósito)


def _conferidos(agora_de: dict[str, str | None], vistos: dict[str, str] | None = None):
    simulacoes = [_Simulacao(i, nome=i) for i in agora_de]
    salvas, _, _ = pulse.estrategias_salvas(simulacoes, maximo=len(simulacoes))
    return [pulse.comparar(e, vistos or {}, agora_de[e.id]) for e in salvas]


def test_acompanhar_poe_o_que_mudou_primeiro_e_as_nao_conferidas_por_ultimo():
    j = pulse.janela(AGORA - timedelta(days=1), AGORA)
    conferidos = _conferidos({"falhou": None, "igual": "passou", "mudou": "não passou"})
    acompanhadas, mudancas = pulse.acompanhar(conferidos, {}, j)
    assert [a.estrategia.id for a in acompanhadas] == ["mudou", "igual", "falhou"]
    mudou, igual, falhou = acompanhadas
    assert (mudou.antes, mudou.agora, mudou.mudou, mudou.conferido_em) == (
        "passou",
        "não passou",
        True,
        AGORA,
    )
    assert (igual.mudou, igual.conferido_em) == (False, AGORA)
    assert (falhou.agora, falhou.mudou, falhou.conferido_em) == (None, False, None)
    assert mudancas == {"mudou": pulse.Mudanca("passou", "não passou", AGORA)}


def test_acompanhar_mantem_o_selo_da_mudanca_vista_dentro_da_janela():
    """No F5 o visto já é o veredito novo; a mudança guardada (dentro da janela) segura o selo."""
    vista_em = AGORA - timedelta(minutes=30)
    guardadas = {"a": pulse.Mudanca("passou", "não passou", vista_em)}
    conferidos = _conferidos({"a": "não passou"}, vistos={"a": "não passou"})
    dentro = pulse.janela_da_aba(vista_em, AGORA, AGORA - timedelta(days=7))
    [a], mudancas = pulse.acompanhar(conferidos, guardadas, dentro)
    assert (a.antes, a.agora, a.mudou, a.conferido_em) == (
        "passou",
        "não passou",
        True,
        vista_em,
    )
    assert mudancas == guardadas
    # a visita seguinte começa depois da mudança: sem selo (a mudança fica guardada um tempo)
    [a], _ = pulse.acompanhar(conferidos, guardadas, pulse.janela(vista_em, AGORA))
    assert (a.antes, a.mudou, a.conferido_em) == ("não passou", False, AGORA)


def test_acompanhar_esquece_mudanca_velha_desfeita_ou_de_estrategia_apagada():
    velha = pulse.Mudanca("passou", "não passou", AGORA - timedelta(days=31))
    desfeita = pulse.Mudanca("passou", "não passou", AGORA - timedelta(hours=1))
    apagada = pulse.Mudanca("passou", "não passou", AGORA - timedelta(hours=1))
    conferidos = _conferidos(
        {"velha": "não passou", "desfeita": "passou"},
        vistos={"velha": "não passou", "desfeita": "passou"},
    )
    j = pulse.janela_da_aba(AGORA, AGORA, AGORA - timedelta(days=30))
    acompanhadas, mudancas = pulse.acompanhar(
        conferidos, {"velha": velha, "desfeita": desfeita, "apagada": apagada}, j
    )
    assert [a.mudou for a in acompanhadas] == [False, False]
    assert mudancas == {}


def test_mudancas_vao_e_voltam_do_banco_e_o_estranho_fica_de_fora():
    mudancas = {"a": pulse.Mudanca("passou", "não passou", AGORA)}
    guardadas = pulse.mudancas_para_guardar(mudancas)
    assert guardadas == {
        "a": {"antes": "passou", "agora": "não passou", "em": AGORA.isoformat()}
    }
    assert pulse.ler_mudancas(guardadas) == mudancas
    estranhas = {
        "sem_fuso": {
            "antes": "passou",
            "agora": "não passou",
            "em": "2026-10-01T10:00",
        },
        "igual": {"antes": "passou", "agora": "passou", "em": AGORA.isoformat()},
        "inventado": {"antes": "ótimo", "agora": "passou", "em": AGORA.isoformat()},
        "data_ruim": {"antes": "passou", "agora": "não passou", "em": "ontem"},
        "texto": "passou",
        "x" * 100: {"antes": "passou", "agora": "não passou", "em": AGORA.isoformat()},
    }
    assert pulse.ler_mudancas(estranhas) == {}
    assert pulse.ler_mudancas(None) == {}


def _estrategia(retrato=None, pedido=None):
    salva = _Simulacao(
        "a", parametros=retrato or {"ticker": "PETR4.SA", "periodo": "2y"}
    )
    if pedido is not None:
        salva.resultado = {"ficha": {"pedido": pedido, "veredito": "passou"}}
    (estrategia,), _, _ = pulse.estrategias_salvas([salva])
    return estrategia


def _sem_cdi(*_args):
    raise AssertionError("este pedido não usa o CDI")


def test_veredito_de_hoje_e_o_da_ficha_com_os_precos_de_hoje():
    """A tela e a API passam cada uma o seu jeito de baixar os preços; o cálculo é um só."""
    from src import ficha
    from src.dados import baixar_dados

    precos = baixar_dados("PETR4.SA", "2y", forcar_exemplo=True)
    pedido = ficha.PedidoDaFicha(
        dados=precos,
        estrategia="Cruzamento de médias",
        parametros={"curta": 10, "longa": 40},
        custo_por_operacao=0.001,
        capital_inicial=10_000,
        livres=("curta", "longa"),
    )
    esperado = ficha.montar_ficha(pedido).veredito.resultado.value
    pedidos = []

    def carregar(ticker, periodo, em_reais):
        pedidos.append((ticker, periodo, em_reais))
        return precos

    estrategia = _estrategia(pedido=ficha.pedido_para_guardar(pedido))
    assert pulse.veredito_de_hoje(estrategia, carregar, _sem_cdi) == esperado
    assert pedidos == [("PETR4.SA", "2y", False)]


def test_veredito_de_hoje_sem_dar_para_conferir_e_none():
    from src.dados import DadosIndisponiveisError

    def sem_dados(*_args):
        raise DadosIndisponiveisError("fora do ar")

    def cambio_falhou(*_args):
        dados = pd.DataFrame({"Close": [1.0]}, index=pd.to_datetime(["2026-10-09"]))
        dados.attrs = {"cambio_falhou": True}
        return dados

    def quebrou(*_args):
        raise RuntimeError("inesperado")

    sem_ticker = _estrategia(retrato={"periodo": "2y"})
    assert pulse.veredito_de_hoje(sem_ticker, sem_dados, _sem_cdi) is None
    assert pulse.veredito_de_hoje(_estrategia(), sem_dados, _sem_cdi) is None
    assert pulse.veredito_de_hoje(_estrategia(), cambio_falhou, _sem_cdi) is None
    assert pulse.veredito_de_hoje(_estrategia(), quebrou, _sem_cdi) is None

    def precos(*_args):
        return pd.DataFrame(
            {"Close": [1.0, 2.0]}, index=pd.to_datetime(["2026-10-08", "2026-10-09"])
        )

    estragado = _estrategia(pedido={"versao": 99})
    assert pulse.veredito_de_hoje(estragado, precos, _sem_cdi) is None
