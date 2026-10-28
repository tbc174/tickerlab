"""O pregão do dia (linha 444 da fila): os números do relatório curto, a partir do fechamento da B3."""

from datetime import date

import pandas as pd
import pytest

from src import pregao_do_dia as pregao

VESPERA = date(2026, 10, 23)
DIA = date(2026, 10, 26)
MILHAO = 1_000_000


def _fechamento(precos: dict[str, tuple[float, int]]) -> pd.DataFrame:
    """Um dia do COTAHIST como `base.intradiario_b3.ler_cotahist` devolve: código → fechamento e volume."""
    tabela = pd.DataFrame(
        [(s, p, v) for s, (p, v) in precos.items()],
        columns=["simbolo", "fechamento", "volume"],
    )
    return tabela.set_index("simbolo")


PAPEIS = pd.DataFrame(
    [
        ("PETR3", "33000167000101", "Petrobras", "Petróleo"),
        ("PETR4", "33000167000101", "Petrobras", "Petróleo"),
        ("PRIO3", "10629105000168", "PRIO", "Petróleo"),
        ("RECV3", "03342704000130", "PetroReconcavo", "Petróleo"),
        ("ITUB4", "60872504000123", "Itaú", "Bancos"),
        ("BBDC4", "60746948000112", "Bradesco", "Bancos"),
        ("BBAS3", "00000000000191", "Banco do Brasil", "Bancos"),
        ("MGLU3", "47960950000121", "Magalu", "Comércio"),
        ("TINY3", "11111111000111", "Pequena", "Comércio"),
        ("DESD3", "22222222000122", "Desdobrou", "Comércio"),
    ],
    columns=["simbolo", "cnpj", "empresa", "setor"],
)

VESPERA_B3 = _fechamento(
    {
        "PETR3": (40.0, 300 * MILHAO),
        "PETR4": (38.0, 900 * MILHAO),
        "PRIO3": (45.0, 200 * MILHAO),
        "RECV3": (12.0, 30 * MILHAO),
        "ITUB4": (35.0, 800 * MILHAO),
        "BBDC4": (15.0, 400 * MILHAO),
        "BBAS3": (25.0, 500 * MILHAO),
        "MGLU3": (10.0, 100 * MILHAO),
        "TINY3": (5.0, 1 * MILHAO),
        "DESD3": (100.0, 50 * MILHAO),
        "BOVA11": (120.0, 2000 * MILHAO),
    }
)
DIA_B3 = _fechamento(
    {
        "PETR3": (36.0, 500 * MILHAO),
        "PETR4": (34.2, 1500 * MILHAO),  # −10%
        "PRIO3": (40.5, 300 * MILHAO),  # −10%
        "RECV3": (12.6, 40 * MILHAO),  # +5%
        "ITUB4": (31.5, 900 * MILHAO),  # −10%
        "BBDC4": (12.0, 500 * MILHAO),  # −20%
        "BBAS3": (20.0, 600 * MILHAO),  # −20%
        "MGLU3": (10.0, 150 * MILHAO),  # 0%
        "TINY3": (10.0, 2 * MILHAO),  # +100%, mas sem liquidez
        "DESD3": (50.0, 60 * MILHAO),  # −50%: desdobramento não ajustado
        "BOVA11": (108.0, 3000 * MILHAO),
    }
)


@pytest.fixture
def tabela() -> pd.DataFrame:
    return pregao.variacoes_das_empresas(
        VESPERA_B3, DIA_B3, PAPEIS, com_evento_no_dia={"DESD3"}
    )


# --- Tarefa 1: o fechamento de dois pregões ------------------------------------------------------


def test_um_papel_por_empresa_o_mais_negociado_na_vespera(tabela: pd.DataFrame) -> None:
    petrobras = tabela[tabela["cnpj"] == "33000167000101"]
    assert len(petrobras) == 1
    assert petrobras.iloc[0]["simbolo"] == "PETR4"


def test_variacao_e_fracao_do_fechamento_da_vespera(tabela: pd.DataFrame) -> None:
    linha = tabela.set_index("simbolo").loc["PETR4"]
    assert linha["variacao"] == pytest.approx(-0.10)
    assert linha["fechamento_vespera"] == 38.0
    assert linha["volume_vespera"] == 900 * MILHAO


def test_so_entram_papeis_da_tabela_de_empresas(tabela: pd.DataFrame) -> None:
    assert "BOVA11" not in set(tabela["simbolo"])


def test_papel_sem_preco_num_dos_dias_fica_de_fora() -> None:
    sem_dia = DIA_B3.drop(index="MGLU3")
    tabela = pregao.variacoes_das_empresas(VESPERA_B3, sem_dia, PAPEIS)
    assert "MGLU3" not in set(tabela["simbolo"])


def test_papel_com_desdobramento_no_dia_fica_a_conferir(tabela: pd.DataFrame) -> None:
    """Desdobramento sem ajuste parece queda de 50%: não pode virar a maior queda."""
    por_simbolo = tabela.set_index("simbolo")
    assert bool(por_simbolo.loc["DESD3", "a_conferir"])
    assert not bool(por_simbolo.loc["PETR4", "a_conferir"])


def test_queda_grande_sem_evento_entra_nas_contas() -> None:
    """Regressão (conferência com 26/10/2026): um corte por tamanho escondia quedas reais do circuit
    breaker (MGLU3 −58%, VAMO3 −57%). Sem evento de capital no dia, a queda entra, por maior que seja."""
    dia = DIA_B3.copy()
    dia.loc["MGLU3", "fechamento"] = 4.18  # −58,2%
    tabela = pregao.variacoes_das_empresas(VESPERA_B3, dia, PAPEIS)
    assert "MGLU3" in set(pregao.liquidas(tabela)["simbolo"])
    assert pregao.maiores_altas_e_quedas(tabela)["quedas"][0]["simbolo"] == "MGLU3"


# --- Tarefa 2: setores, maiores altas e quedas, amplitude ------------------------------------------


def test_liquidas_cortam_pelo_volume_da_vespera(tabela: pd.DataFrame) -> None:
    simbolos = set(pregao.liquidas(tabela)["simbolo"])
    assert "TINY3" not in simbolos  # R$ 1 milhão na véspera
    assert "PETR4" in simbolos


def test_liquidas_deixam_de_fora_o_que_esta_a_conferir(tabela: pd.DataFrame) -> None:
    assert "DESD3" not in set(pregao.liquidas(tabela)["simbolo"])


def test_amplitude_conta_subiram_cairam_e_ficaram(tabela: pd.DataFrame) -> None:
    assert pregao.amplitude(tabela) == {"subiram": 1, "cairam": 5, "estaveis": 1}


def test_maiores_altas_e_quedas_so_liquidas(tabela: pd.DataFrame) -> None:
    maiores = pregao.maiores_altas_e_quedas(tabela, quantas=2)
    assert [m["simbolo"] for m in maiores["altas"]] == [
        "RECV3"
    ]  # 0% não é alta; TINY3 sem liquidez
    # empate em −20%: vem antes a mais negociada na véspera
    assert [m["simbolo"] for m in maiores["quedas"]] == ["BBAS3", "BBDC4"]
    assert maiores["quedas"][0]["variacao"] == pytest.approx(-0.20)
    assert maiores["quedas"][0]["empresa"] == "Banco do Brasil"


def test_setor_contra_o_indice(tabela: pd.DataFrame) -> None:
    setores = pregao.setores_contra_o_indice(tabela, variacao_do_indice=-0.10)
    por_setor = {s["setor"]: s for s in setores}
    # Bancos: −10%, −20%, −20% → mediana −20%, 10 pontos abaixo do índice
    assert por_setor["Bancos"]["mediana"] == pytest.approx(-0.20)
    assert por_setor["Bancos"]["contra_o_indice"] == pytest.approx(-0.10)
    assert por_setor["Bancos"]["empresas"] == 3
    # Petróleo: −10%, −10%, +5% → mediana −10%, igual ao índice
    assert por_setor["Petróleo"]["contra_o_indice"] == pytest.approx(0.0)
    assert [s["setor"] for s in setores] == ["Petróleo", "Bancos"]  # do melhor ao pior


def test_setor_com_poucas_empresas_liquidas_fica_de_fora(tabela: pd.DataFrame) -> None:
    """Comércio só tem a MGLU3 líquida (TINY3 sem volume, DESD3 a conferir): mediana de um não é setor."""
    setores = pregao.setores_contra_o_indice(tabela, variacao_do_indice=-0.10)
    assert "Comércio" not in {s["setor"] for s in setores}


# --- Tarefa 3: dólar, juros e o dia na história ---------------------------------------------------


def _contratos(linhas: dict[str, tuple[float, float]]) -> pd.DataFrame:
    tabela = pd.DataFrame(
        [(s, a, b) for s, (a, b) in linhas.items()],
        columns=["simbolo", "ajuste", "ajuste_vespera"],
    )
    return tabela.set_index("simbolo")


def test_juros_usam_o_di_de_janeiro_mais_perto_de_dois_anos() -> None:
    contratos = _contratos(
        {
            "DI1F27": (13.50, 13.40),
            "DI1F28": (12.90, 12.70),
            "DI1F29": (13.10, 12.80),
            "DI1N28": (13.0, 12.9),
        }
    )
    juros = pregao.taxa_do_di(contratos, DIA)
    # 26/10/2026 + 2 anos = 26/10/2028: janeiro de 2029 está a ~2 meses, janeiro de 2028 a ~10
    assert juros["simbolo"] == "DI1F29"
    assert juros["taxa"] == 13.10
    assert juros["variacao_em_pontos_base"] == pytest.approx(30.0)


def test_juros_sem_o_contrato_no_boletim_levanta_erro() -> None:
    with pytest.raises(pregao.FaltaNoBoletimError):
        pregao.taxa_do_di(_contratos({"DI1F27": (13.5, 13.4)}), DIA)


def test_dolar_usa_o_primeiro_vencimento() -> None:
    contratos = _contratos(
        {
            "DOLX26": (5200.0, 5000.0),
            "DOLZ26": (5230.0, 5040.0),
            "DOLV26": (4990.0, 4980.0),
        }
    )
    dolar = pregao.dolar_futuro(contratos, DIA)
    assert dolar["simbolo"] == "DOLX26"  # em outubro, o 1º vencimento é novembro (X)
    assert dolar["reais_por_dolar"] == pytest.approx(5.20)
    assert dolar["variacao"] == pytest.approx(0.04)


def test_dolar_em_dezembro_vira_o_ano() -> None:
    contratos = _contratos({"DOLF27": (5100.0, 5000.0)})
    assert pregao.dolar_futuro(contratos, date(2026, 12, 10))["simbolo"] == "DOLF27"


def _ibovespa() -> pd.Series:
    """Série de 6 pregões; o último (26/10) cai 14%, pior que qualquer dia anterior."""
    datas = pd.to_datetime(
        [
            "2026-10-16",
            "2026-10-19",
            "2026-10-20",
            "2026-10-21",
            "2026-10-22",
            "2026-10-23",
            "2026-10-26",
        ]
    )
    return pd.Series([100.0, 95.0, 96.0, 90.0, 91.0, 100.0, 86.0], index=datas)


def test_lugar_na_historia_do_pior_dia() -> None:
    lugar = pregao.lugar_na_historia(_ibovespa(), DIA)
    assert lugar["variacao"] == pytest.approx(-0.14)
    assert lugar["pregoes_comparados"] == 5  # as variações antes de 26/10
    assert lugar["pregoes_tao_extremos"] == 0
    assert lugar["ultima_vez"] is None
    assert lugar["desde"] == "2026-10-19"


def test_lugar_na_historia_acha_a_ultima_vez() -> None:
    """Com 26/10 caindo 5%, as quedas do mesmo tamanho ou maiores antes dele são 19/10 e 21/10."""
    serie = _ibovespa()
    serie.iloc[-1] = 95.0  # 26/10 cai 5%
    lugar = pregao.lugar_na_historia(serie, DIA)
    assert lugar["pregoes_tao_extremos"] == 2  # 19/10 (−5%) e 21/10 (−6,25%)
    assert lugar["ultima_vez"] == "2026-10-21"


def test_lugar_na_historia_sem_olhar_o_futuro() -> None:
    """Cortar o futuro não muda o passado: um pregão depois de 26/10 não muda o lugar de 26/10."""
    serie = _ibovespa()
    com_futuro = pd.concat(
        [serie, pd.Series([60.0], index=pd.to_datetime(["2026-10-27"]))]
    )
    assert pregao.lugar_na_historia(com_futuro, DIA) == pregao.lugar_na_historia(
        serie, DIA
    )


def test_lugar_na_historia_sem_o_dia_levanta_erro() -> None:
    with pytest.raises(pregao.FaltaNoBoletimError):
        pregao.lugar_na_historia(_ibovespa(), date(2026, 10, 27))


def test_resumo_tem_fonte_e_data_em_cada_bloco(tabela: pd.DataFrame) -> None:
    resumo = pregao.resumo_do_pregao(
        pregao.EntradasDoPregao(
            dia=DIA,
            vespera=VESPERA,
            empresas=tabela,
            ibovespa=_ibovespa(),
            contratos=_contratos(
                {"DI1F29": (13.10, 12.80), "DOLX26": (5200.0, 5000.0)}
            ),
        )
    )
    blocos = ["ibovespa", "amplitude", "setores", "maiores", "juros", "dolar"]
    for bloco in blocos:
        assert resumo[bloco]["fonte"], bloco
        assert resumo[bloco]["data"] == "2026-10-26", bloco
    assert resumo["pregao"] == "2026-10-26"
    assert resumo["vespera"] == "2026-10-23"
    assert [a["simbolo"] for a in resumo["a_conferir"]] == ["DESD3"]
    # o texto diz os cortes usados; eles vêm do resumo, não repetidos no molde
    assert resumo["amplitude"]["liquidez_minima"] == pregao.LIQUIDEZ_MINIMA
    assert (
        resumo["setores"]["empresas_por_setor_minimo"]
        == pregao.EMPRESAS_POR_SETOR_MINIMO
    )


def test_resumo_vira_json(tabela: pd.DataFrame) -> None:
    """Tipos simples: o resumo vai para um arquivo JSON e para a API sem conversão."""
    import json

    resumo = pregao.resumo_do_pregao(
        pregao.EntradasDoPregao(
            dia=DIA,
            vespera=VESPERA,
            empresas=tabela,
            ibovespa=_ibovespa(),
            contratos=_contratos(
                {"DI1F29": (13.10, 12.80), "DOLX26": (5200.0, 5000.0)}
            ),
        )
    )
    assert json.loads(json.dumps(resumo)) == resumo
