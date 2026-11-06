"""Simulador de trava do café (linha 340): a conta, só com o preço mensal e só na memória."""

import dataclasses
import re
from datetime import date

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src import precos_de_referencia as precos
from src.banco import series as acervo
from src.commodities.cafe import textos_da_trava as textos
from src.commodities.cafe import trava
from src.commodities.cafe.trava import EntradaDaTrava

KG_POR_SACA = 60
PTAX_NO_ACERVO = acervo.SerieDoAcervo(
    trava.PTAX, "PTAX (venda)", "R$ por US$", "diária"
)


def _entrada(**mudancas: object) -> EntradaDaTrava:
    base = EntradaDaTrava(
        tipo="arabica",
        sacas=1_000,
        custo_por_saca=900.0,
        mes_da_colheita=6,
        meses_de_antecedencia=3,
        fracao_travada=1.0,
        premio_da_opcao=0.05,
    )
    return dataclasses.replace(base, **mudancas)  # type: ignore[arg-type]


def _precos(linhas: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """Mês → (US$/kg, PTAX), já no formato de `precos_por_saca`."""
    meses = pd.to_datetime(list(linhas))
    usd = pd.Series([v[0] for v in linhas.values()], index=meses)
    ptax = pd.Series([v[1] for v in linhas.values()], index=meses)
    return trava.precos_por_saca(usd, ptax)


# Safra 2020: trava em março (3 meses antes de junho), o preço sobe em abril (chamada de margem),
# e na colheita o dólar cai e o câmbio sobe.
SAFRA_2020 = {
    "2020-03-01": (4.0, 5.0),  # trava: 4 × 60 × 5 = R$ 1.200
    "2020-04-01": (5.0, 5.0),  # sobe 1 US$/kg: chamada de 60 US$ × 5 = R$ 300 por saca
    "2020-05-01": (4.5, 5.0),
    "2020-06-01": (3.0, 6.0),  # colheita: 3 × 60 × 6 = R$ 1.080
}


# --- Tarefa 1: entrada e preço por saca ---


def test_preco_por_saca_converte_dolar_por_kg_em_reais():
    tabela = _precos({"2024-01-01": (4.0, 5.0)})
    assert tabela.loc["2024-01-01", "usd_por_saca"] == pytest.approx(4.0 * KG_POR_SACA)
    assert tabela.loc["2024-01-01", "reais_por_saca"] == pytest.approx(1_200.0)


def test_ptax_diaria_vira_media_do_mes():
    usd = pd.Series([4.0], index=pd.to_datetime(["2024-01-01"]))
    ptax = pd.Series([4.0, 6.0], index=pd.to_datetime(["2024-01-02", "2024-01-31"]))
    tabela = trava.precos_por_saca(usd, ptax)
    assert tabela.loc["2024-01-01", "ptax"] == pytest.approx(5.0)


def test_mes_sem_preco_ou_sem_cambio_fica_de_fora():
    usd = pd.Series([4.0, None], index=pd.to_datetime(["2024-01-01", "2024-02-01"]))
    ptax = pd.Series([5.0], index=pd.to_datetime(["2024-01-10"]))
    tabela = trava.precos_por_saca(usd, ptax)
    assert list(tabela.index) == [pd.Timestamp("2024-01-01")]


@pytest.mark.parametrize(
    "mudanca",
    [
        {"tipo": "soja"},
        {"sacas": 0},
        {"custo_por_saca": -1.0},
        {"mes_da_colheita": 13},
        {"meses_de_antecedencia": 0},
        {"meses_de_antecedencia": trava.ANTECEDENCIA_MAXIMA + 1},
        {"fracao_travada": 1.5},
        {"premio_da_opcao": trava.PREMIO_MAXIMO + 0.01},
    ],
)
def test_entrada_recusa_valores_fora_do_intervalo(mudanca):
    with pytest.raises(ValueError):
        trava.validar(_entrada(**mudanca))


# --- Tarefa 2: as safras ---


def _instrumento(
    safra: trava.SafraSimulada, chave: str
) -> trava.ResultadoDoInstrumento:
    return next(i for i in safra.instrumentos if i.chave == chave)


def test_uma_safra_conferida_a_mao():
    [safra] = trava.simular_safras(_entrada(), _precos(SAFRA_2020))
    assert safra.safra == 2020
    assert safra.mes_da_trava == date(2020, 3, 1)
    assert safra.mes_da_colheita == date(2020, 6, 1)
    assert safra.preco_da_trava == pytest.approx(1_200.0)
    assert safra.preco_na_colheita == pytest.approx(1_080.0)
    nao = _instrumento(safra, trava.NAO_TRAVAR)
    termo = _instrumento(safra, trava.TERMO)
    futuro = _instrumento(safra, trava.FUTURO)
    opcao = _instrumento(safra, trava.OPCAO)
    assert nao.receita_por_saca == pytest.approx(1_080.0)
    assert termo.receita_por_saca == pytest.approx(1_200.0)
    # dólar da trava (240 US$/saca) no câmbio da colheita (6): R$ 1.440
    assert futuro.receita_por_saca == pytest.approx(1_440.0)
    assert futuro.pior_chamada_por_saca == pytest.approx(300.0)
    # piso no dólar da trava, no câmbio da colheita, menos 5% do preço da trava (R$ 60)
    assert opcao.receita_por_saca == pytest.approx(1_440.0 - 60.0)
    assert termo.contra_nao_travar_por_saca == pytest.approx(120.0)
    assert nao.pior_chamada_por_saca is None


def test_sem_nada_travado_todo_instrumento_e_igual_a_nao_travar():
    [safra] = trava.simular_safras(_entrada(fracao_travada=0.0), _precos(SAFRA_2020))
    assert all(i.receita_por_saca == pytest.approx(1_080.0) for i in safra.instrumentos)


def test_metade_travada_mistura_as_receitas():
    [safra] = trava.simular_safras(_entrada(fracao_travada=0.5), _precos(SAFRA_2020))
    assert _instrumento(safra, trava.TERMO).receita_por_saca == pytest.approx(1_140.0)


def test_safra_sem_preco_na_colheita_fica_de_fora():
    sem_junho = {m: v for m, v in SAFRA_2020.items() if m != "2020-06-01"}
    assert trava.simular_safras(_entrada(), _precos(sem_junho)) == ()


def test_safras_antes_do_cambio_flutuante_ficam_de_fora():
    antigas = {"1998-03-01": (4.0, 1.1), "1998-06-01": (3.0, 1.1)}
    assert trava.simular_safras(_entrada(), _precos(antigas)) == ()


def test_trava_no_ano_anterior_quando_a_antecedencia_passa_de_janeiro():
    linhas = {"2019-11-01": (4.0, 5.0), "2020-02-01": (4.0, 5.0)}
    entrada = _entrada(mes_da_colheita=2, meses_de_antecedencia=3)
    [safra] = trava.simular_safras(entrada, _precos(linhas))
    assert safra.mes_da_trava == date(2019, 11, 1)


# --- Tarefa 3: cenários com o preço de hoje e o resumo ---


def test_margem_no_cenario_aplica_o_movimento_ao_preco_de_hoje():
    linhas = dict(SAFRA_2020) | {"2026-09-01": (5.0, 5.0)}  # hoje: R$ 1.500 por saca
    simulacao = trava.simular_trava(_entrada(), _precos(linhas))
    assert simulacao.preco_de_hoje == pytest.approx(1_500.0)
    assert simulacao.mes_do_preco_de_hoje == date(2026, 9, 1)
    [safra] = simulacao.safras
    # não travar: 1.500 × (1.080 ÷ 1.200) − 900 = 450
    assert _instrumento(safra, trava.NAO_TRAVAR).margem_no_cenario == pytest.approx(
        450.0
    )
    # termo: 1.500 × 1 − 900 = 600
    assert _instrumento(safra, trava.TERMO).margem_no_cenario == pytest.approx(600.0)


def test_resumo_por_instrumento_sem_ranking():
    linhas = dict(SAFRA_2020) | {
        "2021-03-01": (4.0, 5.0),
        "2021-06-01": (2.0, 5.0),  # colheita a R$ 600: metade do preço da trava
        "2026-09-01": (4.0, 5.0),  # hoje: R$ 1.200
    }
    simulacao = trava.simular_trava(_entrada(), _precos(linhas))
    assert [r.chave for r in simulacao.resumos] == list(trava.ORDEM_DOS_INSTRUMENTOS)
    nao = next(r for r in simulacao.resumos if r.chave == trava.NAO_TRAVAR)
    # cenários: 1.200 × 0,9 − 900 = 180 e 1.200 × 0,5 − 900 = −300
    assert nao.safras == 2
    assert nao.menor_margem == pytest.approx(-300.0)
    assert nao.maior_margem == pytest.approx(180.0)
    assert nao.mediana_da_margem == pytest.approx(-60.0)
    assert nao.safras_abaixo_do_custo == 1


def test_sem_safras_simulacao_vazia_nao_quebra():
    simulacao = trava.simular_trava(_entrada(), _precos({"2026-09-01": (4.0, 5.0)}))
    assert simulacao.safras == ()
    assert all(r.safras == 0 and r.menor_margem is None for r in simulacao.resumos)


def test_sem_preco_nenhum_avisa():
    with pytest.raises(trava.SemPrecosError):
        trava.simular_trava(_entrada(), _precos({}))


# --- Tarefa 4: propriedades ---

precos_mensais = st.lists(
    st.tuples(
        st.floats(min_value=0.5, max_value=12.0),
        st.floats(min_value=1.5, max_value=7.0),
    ),
    min_size=24,
    max_size=60,
)
entradas = st.builds(
    EntradaDaTrava,
    tipo=st.sampled_from(trava.TIPOS),
    sacas=st.floats(min_value=1, max_value=100_000),
    custo_por_saca=st.floats(min_value=1, max_value=5_000),
    mes_da_colheita=st.integers(min_value=1, max_value=12),
    meses_de_antecedencia=st.integers(min_value=1, max_value=trava.ANTECEDENCIA_MAXIMA),
    fracao_travada=st.floats(min_value=0, max_value=1),
    premio_da_opcao=st.floats(min_value=0, max_value=trava.PREMIO_MAXIMO),
)


def _tabela(valores: list[tuple[float, float]]) -> pd.DataFrame:
    meses = pd.date_range("2018-01-01", periods=len(valores), freq="MS")
    return trava.precos_por_saca(
        pd.Series([v[0] for v in valores], index=meses),
        pd.Series([v[1] for v in valores], index=meses),
    )


@settings(max_examples=80, deadline=None)
@given(
    valores=precos_mensais,
    entrada=entradas,
    corte=st.integers(min_value=1, max_value=59),
)
def test_cortar_o_futuro_nao_muda_as_safras_ja_colhidas(valores, entrada, corte):
    tabela = _tabela(valores)
    inteira = trava.simular_safras(entrada, tabela)
    cortada = trava.simular_safras(entrada, tabela.iloc[:corte])
    ultimo_mes = tabela.index[:corte][-1].date()
    ja_colhidas = tuple(s for s in inteira if s.mes_da_colheita <= ultimo_mes)
    assert cortada == ja_colhidas


@settings(max_examples=80, deadline=None)
@given(valores=precos_mensais, entrada=entradas)
def test_regras_de_cada_instrumento_valem_em_qualquer_safra(valores, entrada):
    for safra in trava.simular_safras(entrada, _tabela(valores)):
        assert (
            tuple(i.chave for i in safra.instrumentos) == trava.ORDEM_DOS_INSTRUMENTOS
        )
        f = entrada.fracao_travada
        nao = _instrumento(safra, trava.NAO_TRAVAR).receita_por_saca
        termo = _instrumento(safra, trava.TERMO).receita_por_saca
        futuro = _instrumento(safra, trava.FUTURO).receita_por_saca
        opcao = _instrumento(safra, trava.OPCAO).receita_por_saca
        assert nao == pytest.approx(safra.preco_na_colheita)
        # o termo não depende do preço da colheita na parte travada
        assert termo == pytest.approx(f * safra.preco_da_trava + (1 - f) * nao)
        # a opção nunca dá menos que o futuro, descontado o prêmio pago
        premio = f * entrada.premio_da_opcao * safra.preco_da_trava
        assert opcao >= futuro - premio - 1e-6
        assert _instrumento(safra, trava.FUTURO).pior_chamada_por_saca >= 0


# --- Tarefa 5: leitura do acervo, sem olhar o futuro ---


def test_ler_precos_nao_usa_o_que_foi_divulgado_depois_do_dia(banco):
    codigo = "bm-pink-cafe-arabica"
    meses = pd.to_datetime(["2026-08-01", "2026-09-01"])
    with banco.begin() as conexao:
        acervo.garantir_serie(conexao, precos.serie_do_acervo(codigo))
        acervo.garantir_serie(conexao, PTAX_NO_ACERVO)
        acervo.gravar(
            conexao, codigo, pd.Series([4.0, 4.0], index=meses), date(2026, 10, 3)
        )
        acervo.gravar(
            conexao, codigo, pd.Series([9.0, 9.0], index=meses), date(2026, 11, 3)
        )
        acervo.gravar(
            conexao, trava.PTAX, pd.Series([5.0, 5.0], index=meses), date(2026, 10, 1)
        )
    with banco.connect() as conexao:
        antes = trava.ler_precos(conexao, "arabica", date(2026, 10, 10))
    assert list(antes["usd_por_saca"]) == [pytest.approx(240.0)] * 2


# --- Tarefa 6: nenhuma frase diz o que fazer ---

CONSELHO = re.compile(
    r"\b(recomend\w*|suger\w*|aconselh\w*|dever\w*|deve|devem|trave|travem|compre|venda já|"
    r"vale a pena|compensa\w*|melhor|ideal|o certo)\b",
    re.IGNORECASE,
)


NEGACAO = "não é recomendação"


def _todos_os_textos() -> list[str]:
    soltos = [v for v in vars(textos).values() if isinstance(v, str)]
    em_tuplas = [
        t
        for v in vars(textos).values()
        if isinstance(v, (tuple, dict))
        for t in (v.values() if isinstance(v, dict) else v)
        if isinstance(t, str)
    ]
    riscos = [
        frase
        for instrumento in textos.INSTRUMENTOS
        for frase in dataclasses.astuple(instrumento)
    ]
    return [t for t in soltos + em_tuplas + riscos if isinstance(t, str)]


def test_nenhum_texto_diz_o_que_fazer():
    textos_soltos = _todos_os_textos()
    assert len(textos_soltos) > 10
    # a negação explícita ("não é recomendação") é o próprio aviso, não um conselho
    achados = [t for t in textos_soltos if CONSELHO.search(t.replace(NEGACAO, ""))]
    assert achados == []


def test_avisos_obrigatorios_estao_nos_textos():
    assert (
        textos.AVISO_DIARIO
        == "Preço de referência mensal; o diário depende de licença."
    )
    assert "não é recomendação" in textos.AVISO_SEM_RECOMENDACAO
    assert "nada do que você digitar é guardado" in textos.AVISO_SO_NA_MEMORIA.lower()


def test_cada_instrumento_da_conta_tem_texto_de_risco():
    chaves_com_texto = {i.chave for i in textos.INSTRUMENTOS}
    assert set(trava.ORDEM_DOS_INSTRUMENTOS) <= chaves_com_texto
