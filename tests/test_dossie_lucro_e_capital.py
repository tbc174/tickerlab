"""As seções do PR 2 dos relatórios v2 no dossiê: qualidade do lucro e capital e acionistas.

Tabelas de mentira, pequenas, já só com a empresa da ficha (o script separa por CNPJ antes). As duas
seções são a entrada da análise escrita (ADR 0100): cada número com a data e sem olhar o futuro.
"""

import pandas as pd
import pytest

from base import dossie

D = pd.Timestamp
HOJE = D("2026-10-17")
CNPJ = "02429144000193"
MILHAO = 1_000_000.0


def _itens(secao: dict) -> dict[str, dict]:
    return {item["chave"]: item for item in secao["itens"]}


# --- qualidade do lucro: reapresentações ---------------------------------------------------------


def _linha_da_dre(
    conta: str,
    descricao: str,
    ano: int,
    valor: float,
    divulgado_em: str,
    ate: str | None = None,
    grupo: str = "con",
) -> dict:
    return {
        "grupo": grupo,
        "demonstracao": "DRE",
        "conta": conta,
        "descricao": descricao,
        "inicio": D(f"{ano}-01-01"),
        "fim": D(f"{ano}-12-31"),
        "valor": valor,
        "documento": "DFP",
        "divulgado_em": D(divulgado_em),
        "ate": D(ate) if ate else pd.NaT,
    }


LUCRO = ("3.11", "Lucro/Prejuízo Consolidado do Período")
RECEITA = ("3.01", "Receita de Venda de Bens e/ou Serviços")


def _como_era() -> pd.DataFrame:
    """O lucro de 2023 saiu 100 mi e a DFP de 2024 o refez para 80 mi; o resto não mudou (a receita
    de 2023 mudou R$ 400, arredondamento da CVM)."""
    return pd.DataFrame(
        [
            _linha_da_dre(*LUCRO, 2023, 100 * MILHAO, "2024-03-10", "2025-03-12"),
            _linha_da_dre(*LUCRO, 2023, 80 * MILHAO, "2025-03-12"),
            _linha_da_dre(*LUCRO, 2024, 120 * MILHAO, "2025-03-12"),
            _linha_da_dre(*RECEITA, 2023, 1000 * MILHAO, "2024-03-10", "2025-03-12"),
            _linha_da_dre(*RECEITA, 2023, 1000 * MILHAO + 400, "2025-03-12"),
            _linha_da_dre(*RECEITA, 2024, 1100 * MILHAO, "2025-03-12"),
            # o individual mudou muito, mas a ficha olha o consolidado quando ele existe
            _linha_da_dre(
                "3.11", "Lucro/Prejuízo do Período", 2024, 1.0, "2025-03-12",
                "2025-06-01", grupo="ind",
            ),
            _linha_da_dre(
                "3.11", "Lucro/Prejuízo do Período", 2024, 9e9, "2025-06-01", grupo="ind"
            ),
        ]
    )  # fmt: skip


def _qualidade(**tabelas: pd.DataFrame) -> dict | None:
    vazio = pd.DataFrame()
    return dossie.secao_qualidade_do_lucro(
        tabelas.get("como_era", vazio),
        tabelas.get("releases", vazio),
        tabelas.get("trocas", vazio),
        HOJE,
    )


def test_reapresentacao_mostra_o_primeiro_valor_e_o_de_hoje() -> None:
    secao = _qualidade(como_era=_como_era())
    assert secao is not None
    [refeito] = secao["tabelas"]["reapresentacoes"]
    assert refeito == {
        "exercicio": 2023,
        "linha": "Lucro do período",
        "primeiro_valor": pytest.approx(100 * MILHAO),
        "primeiro_em": "2024-03-10",
        "valor_atual": pytest.approx(80 * MILHAO),
        "trocado_em": "2025-03-12",
        "diferenca": pytest.approx(-20 * MILHAO),
        "diferenca_pct": pytest.approx(-20.0),
    }
    itens = _itens(secao)
    assert itens["exercicios_reapresentados"]["valor"] == 1
    assert itens["exercicios_reapresentados"]["base"] == "2025-03-12"
    assert itens["exercicios_olhados"]["valor"] == 2


def test_diferenca_de_arredondamento_nao_e_reapresentacao() -> None:
    so_a_receita = _como_era().query("conta == '3.01'")
    secao = _qualidade(como_era=so_a_receita)
    assert secao is not None
    assert _itens(secao)["exercicios_reapresentados"]["valor"] == 0
    assert "reapresentacoes" not in secao["tabelas"]


def test_sem_consolidado_a_ficha_olha_o_individual() -> None:
    so_o_individual = _como_era().query("grupo == 'ind'")
    secao = _qualidade(como_era=so_o_individual)
    assert secao is not None
    [refeito] = secao["tabelas"]["reapresentacoes"]
    assert refeito["exercicio"] == 2024
    assert refeito["valor_atual"] == pytest.approx(9e9)


def test_lucro_e_achado_pela_descricao_e_nao_so_pelo_codigo() -> None:
    # em parte das empresas a 3.11 é a reversão dos juros sobre capital próprio e o lucro fica na 3.13
    como_era = pd.DataFrame(
        [
            _linha_da_dre("3.11", "Reversão dos Juros sobre Capital Próprio", 2024, 5.0,
                          "2025-03-12", "2025-05-01"),
            _linha_da_dre("3.11", "Reversão dos Juros sobre Capital Próprio", 2024, 9.0e9,
                          "2025-05-01"),
            _linha_da_dre("3.13", "Lucro/Prejuízo Consolidado do Período", 2024, 7.0e8,
                          "2025-03-12"),
        ]
    )  # fmt: skip
    secao = _qualidade(como_era=como_era)
    assert secao is not None
    assert _itens(secao)["exercicios_reapresentados"]["valor"] == 0
    assert _itens(secao)["exercicios_olhados"]["valor"] == 1


def test_reapresentacao_nao_olha_o_futuro() -> None:
    # na véspera da DFP de 2024, o lucro de 2023 ainda era o primeiro: nada refeito
    antes = dossie.secao_qualidade_do_lucro(
        _como_era(), pd.DataFrame(), pd.DataFrame(), D("2025-03-11")
    )
    assert antes is not None
    assert _itens(antes)["exercicios_reapresentados"]["valor"] == 0
    assert _itens(antes)["exercicios_olhados"]["valor"] == 1


def test_lucro_por_exercicio_e_a_ultima_versao_ja_divulgada_de_cada_ano() -> None:
    secao = _qualidade(como_era=_como_era())
    assert secao is not None
    assert secao["tabelas"]["lucro_por_exercicio"] == [
        {"exercicio": 2024, "lucro": 120 * MILHAO, "divulgado_em": "2025-03-12"},
        {"exercicio": 2023, "lucro": 80 * MILHAO, "divulgado_em": "2025-03-12"},
    ]
    vazio = pd.DataFrame()
    antes = dossie.secao_qualidade_do_lucro(_como_era(), vazio, vazio, D("2024-06-01"))
    assert antes is not None
    assert antes["tabelas"]["lucro_por_exercicio"] == [
        {"exercicio": 2023, "lucro": 100 * MILHAO, "divulgado_em": "2024-03-10"},
    ]


def test_reapresentacoes_so_dos_ultimos_10_exercicios() -> None:
    velho = pd.DataFrame(
        [
            _linha_da_dre(*LUCRO, 2010, 1.0e8, "2011-03-10", "2012-03-10"),
            _linha_da_dre(*LUCRO, 2010, 2.0e8, "2012-03-10"),
        ]
    )
    secao = _qualidade(como_era=pd.concat([_como_era(), velho], ignore_index=True))
    assert secao is not None
    assert [r["exercicio"] for r in secao["tabelas"]["reapresentacoes"]] == [2023]


# --- qualidade do lucro: release contra o oficial ------------------------------------------------


def _release(
    periodo: str,
    linha: str,
    classe: str,
    diferenca_pct: float | None = 0.0,
    versao: int = 1,
    data_entrega: str = "2025-11-10",
    leitura: int = 0,
) -> dict:
    return {
        "protocolo": f"p-{periodo}",
        "versao": versao,
        "periodo": periodo,
        "referencia": D("2025-09-30"),
        "data_entrega": D(data_entrega),
        "link": f"https://cvm/{periodo}",
        "linha": linha,
        "periodo_lido": "trimestre",
        "leitura": leitura,
        "valor_release_reais": 110.0,
        "valor_oficial_reais": 100.0,
        "diferenca_reais": 10.0,
        "diferenca_pct": diferenca_pct,
        "classe": classe,
        "publico_em": D(data_entrega),
    }


def _releases() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _release("3T25", "receita_liquida", "igual"),
            _release("3T25", "lucro_liquido_controladores", "diferente", 10.0),
            _release("3T25", "resultado_operacional", "igual (arredondamento)"),
            _release("2T25", "receita_liquida", "release não mostra", None),
            _release("2T25", "lucro_liquido_controladores", "sem ITR", None),
            # a versão 2 do release do 2T25 corrigiu o resultado operacional: só ela conta
            _release("2T25", "resultado_operacional", "diferente", 3.0,
                     data_entrega="2025-08-10"),
            _release("2T25", "resultado_operacional", "igual", versao=2,
                     data_entrega="2025-08-12"),
        ]
    )  # fmt: skip


def test_release_conta_so_o_que_deu_para_comparar() -> None:
    secao = _qualidade(releases=_releases())
    assert secao is not None
    itens = _itens(secao)
    assert itens["releases_comparados"]["valor"] == 4
    assert itens["releases_comparados"]["base"] == "2025-11-10"
    assert itens["releases_diferentes"]["valor"] == 1
    [diferente] = secao["tabelas"]["releases_diferentes"]
    assert diferente["periodo"] == "3T25"
    assert diferente["linha"] == "Lucro dos controladores"
    assert diferente["diferenca_pct"] == pytest.approx(10.0)
    por_classe = {
        linha["classe"]: linha["valores"]
        for linha in secao["tabelas"]["releases_por_classe"]
    }
    assert por_classe == {
        "igual": 2,
        "igual (arredondamento)": 1,
        "diferente": 1,
        "release não mostra": 1,
        "sem ITR": 1,
    }


def test_release_publicado_depois_de_hoje_fica_fora() -> None:
    futuro = _releases().assign(publico_em=D("2026-12-01"))
    assert _qualidade(releases=futuro) is None


# --- qualidade do lucro: trocas de auditor -------------------------------------------------------


def _trocas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "efetiva_em": [D("2012-01-01"), D("2018-04-01"), D("2024-04-01")],
            "conhecido_em": [D("2012-05-01"), D("2018-05-01"), D("2024-05-31")],
            "anterior": ["A", "B", "C"],
            "novo": ["B", "C", "D"],
            "anos_com_o_anterior": [5.0, 6.0, 6.0],
        }
    )


def test_trocas_de_auditor_contam_os_ultimos_10_anos() -> None:
    secao = _qualidade(trocas=_trocas())
    assert secao is not None
    troca = _itens(secao)["trocas_de_auditor_10_anos"]
    assert troca["valor"] == 2
    assert troca["base"] == "2024-04-01"


def test_secao_sem_nada_nao_existe() -> None:
    assert _qualidade() is None


# --- capital e acionistas: insiders --------------------------------------------------------------


def _negociacao(
    cargo: str, operacao: str, data: str, valor: float, entregue_em: str | None = None
) -> dict:
    dia = D(data)
    return {
        "cnpj": "02.429.144/0001-93",
        "cargo": cargo,
        "operacao": operacao,
        "data": dia,
        "entregue_em": D(entregue_em) if entregue_em else dia + pd.Timedelta(days=10),
        "quantidade": 1000.0,
        "preco": valor / 1000,
        "valor": valor,
        "link": "https://cvm/vlmo",
    }


def _negociacoes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # últimos 12 meses (de 18/10/2025 a 17/10/2026)
            _negociacao("diretoria", "compra", "2026-03-01", 2 * MILHAO),
            _negociacao("conselho", "venda", "2026-05-01", 5 * MILHAO),
            _negociacao("controlador", "compra", "2025-12-01", 1 * MILHAO),
            _negociacao("companhia", "compra", "2026-06-01", 30 * MILHAO),
            # os 12 meses anteriores
            _negociacao("diretoria", "venda", "2025-01-10", 4 * MILHAO),
            # negociada antes de hoje, mas declarada depois: a ficha de hoje não a conhece
            _negociacao("diretoria", "compra", "2026-10-15", 9 * MILHAO, "2026-11-05"),
        ]
    )


def _capital(**tabelas: object) -> dict | None:
    vazio = pd.DataFrame()
    return dossie.secao_capital_e_acionistas(
        tabelas.get("negociacoes", vazio),  # type: ignore[arg-type]
        tabelas.get("eventos", vazio),  # type: ignore[arg-type]
        tabelas.get("painel", vazio),  # type: ignore[arg-type]
        HOJE,
        tabelas.get("ultimo_mes"),  # type: ignore[arg-type]
        proventos=tabelas.get("proventos", vazio),  # type: ignore[arg-type]
    )


def test_insiders_somam_12_meses_sem_a_tesouraria() -> None:
    secao = _capital(negociacoes=_negociacoes())
    assert secao is not None
    itens = _itens(secao)
    assert itens["insiders_compras_12m"]["valor"] == pytest.approx(3 * MILHAO)
    assert itens["insiders_vendas_12m"]["valor"] == pytest.approx(5 * MILHAO)
    assert itens["recompras_12m"]["valor"] == pytest.approx(30 * MILHAO)
    assert itens["insiders_compras_12m"]["base"] == "2026-10-17"


def test_insiders_por_cargo_tem_o_nome_do_cargo_e_nenhuma_pessoa() -> None:
    secao = _capital(negociacoes=_negociacoes())
    assert secao is not None
    por_cargo = {
        linha["cargo"]: linha for linha in secao["tabelas"]["insiders_por_cargo"]
    }
    assert set(por_cargo) == {
        "Diretoria",
        "Conselho de administração",
        "Controlador",
        "A própria empresa",
    }
    assert por_cargo["Diretoria"]["compras"] == pytest.approx(2 * MILHAO)
    assert por_cargo["Diretoria"]["negociacoes"] == 1
    dossie.conferir_sem_pessoas(secao, set())


def test_insiders_comparam_com_os_12_meses_anteriores() -> None:
    secao = _capital(negociacoes=_negociacoes())
    assert secao is not None
    janelas = secao["tabelas"]["insiders_janelas"]
    assert [j["ate"] for j in janelas] == ["2026-10-17", "2025-10-17"]
    assert janelas[1]["vendas"] == pytest.approx(4 * MILHAO)
    assert janelas[1]["compras"] == 0


def test_insiders_sem_negociacao_no_ano_mostram_zero() -> None:
    antigas = _negociacoes().query("data < '2025-06-01'")
    secao = _capital(negociacoes=antigas)
    assert secao is not None
    assert _itens(secao)["insiders_compras_12m"]["valor"] == 0


# --- capital e acionistas: eventos de capital ----------------------------------------------------


def _eventos_de_capital() -> pd.DataFrame:
    # o desdobramento de 2021 aparece no FRE de 2022 e de novo no de 2023: conta uma vez
    return pd.DataFrame(
        {
            "referencia": [D("2022-01-01"), D("2023-01-01"), D("2023-01-01"), D("2012-01-01")],
            "versao": [1, 2, 2, 1],
            "tipo": ["desdobramento", "desdobramento", "aumento", "grupamento"],
            "data": [D("2021-04-01"), D("2021-04-01"), D("2023-08-01"), D("2011-05-01")],
            "fator": [2.0, 2.0, None, 0.1],
            "acoes_novas": [None, None, 5_000_000.0, None],
            "valor": [None, None, 300 * MILHAO, None],
        }
    )  # fmt: skip


def test_eventos_de_capital_dos_10_anos_sem_repetir() -> None:
    secao = _capital(eventos=_eventos_de_capital())
    assert secao is not None
    eventos = secao["tabelas"]["eventos_de_capital"]
    assert [(e["data"], e["tipo"]) for e in eventos] == [
        ("2023-08-01", "aumento"),
        ("2021-04-01", "desdobramento"),
    ]
    item = _itens(secao)["eventos_de_capital"]
    assert item["valor"] == 2
    assert item["base"] == "2023-08-01"


# --- capital e acionistas: proventos de cada exercício -------------------------------------------


def _provento(
    fre: tuple[str, int, str], exercicio: str, lucro: float, dividendo: float
) -> dict[str, object]:
    referencia, versao, conhecido_em = fre
    return {
        "cnpj": "02.429.144/0001-93",
        "referencia": D(referencia),
        "versao": versao,
        "conhecido_em": D(conhecido_em),
        "exercicio": D(exercicio),
        "lucro_ajustado": lucro * MILHAO,
        "dividendo_total": dividendo * MILHAO,
        "payout": dividendo / lucro if lucro else None,
    }


FRE_2025 = ("2025-01-01", 1, "2025-05-31")
FRE_2026 = ("2026-01-01", 1, "2026-05-29")
FRE_2027 = ("2027-01-01", 1, "2026-11-30")  # entregue depois de hoje


def _proventos() -> pd.DataFrame:
    # o FRE de 2026 refaz 2024 (dividendo 55 contra 50) e traz 2025; o de 2027 ainda não foi entregue
    return pd.DataFrame(
        [
            _provento(FRE_2025, "2023-12-31", 100, 40),
            _provento(FRE_2025, "2024-12-31", 100, 50),
            _provento(FRE_2026, "2024-12-31", 100, 55),
            _provento(FRE_2026, "2025-12-31", 100, 130),
            _provento(FRE_2027, "2026-12-31", 10, 90),
        ]
    )


def test_proventos_por_exercicio_vem_do_fre_mais_novo_ja_entregue() -> None:
    secao = _capital(proventos=_proventos())
    assert secao is not None
    assert secao["tabelas"]["proventos_por_exercicio"] == [
        {"exercicio": 2025, "lucro_ajustado": 100 * MILHAO, "dividendo_total": 130 * MILHAO,
         "payout": 1.3, "conhecido_em": "2026-05-29"},
        {"exercicio": 2024, "lucro_ajustado": 100 * MILHAO, "dividendo_total": 55 * MILHAO,
         "payout": 0.55, "conhecido_em": "2026-05-29"},
        {"exercicio": 2023, "lucro_ajustado": 100 * MILHAO, "dividendo_total": 40 * MILHAO,
         "payout": 0.4, "conhecido_em": "2025-05-31"},
    ]  # fmt: skip
    assert secao["itens"] == []  # só a tabela: nenhum número novo para o rastro


def test_proventos_sem_a_data_da_entrega_do_fre_ficam_fora() -> None:
    sem_data = _proventos().assign(conhecido_em=pd.NaT)
    assert _capital(proventos=sem_data) is None


def test_proventos_cortar_o_futuro_nao_muda_o_passado() -> None:
    dia = D("2026-03-01")
    vazio = pd.DataFrame()
    proventos = _proventos()

    def secao(tabela: pd.DataFrame) -> dict | None:
        return dossie.secao_capital_e_acionistas(
            vazio, vazio, vazio, dia, None, proventos=tabela
        )

    assert secao(proventos) == secao(proventos[proventos["conhecido_em"] <= dia])
    assert secao(proventos) is not None


# --- capital e acionistas: compras e vendas dos fundos -------------------------------------------


def _painel() -> pd.DataFrame:
    meses = pd.date_range("2024-07-31", periods=27, freq="ME")  # jul/2024 a set/2026
    return pd.DataFrame(
        {
            "competencia": meses,
            "tipo": "comprado",
            "fundos": 400,
            "valor": 9.0e9,
            "compras": [1.0 * MILHAO] * 4 + [2.0 * MILHAO] * 23,
            "vendas": [0.5 * MILHAO] * 4 + [1.0 * MILHAO] * 23,
        }
    )


def test_fundos_somam_compras_e_vendas_dos_12_ultimos_meses_completos() -> None:
    secao = _capital(painel=_painel(), ultimo_mes=D("2026-08-31"))
    assert secao is not None
    itens = _itens(secao)
    assert itens["compras_dos_fundos_12m"]["valor"] == pytest.approx(24 * MILHAO)
    assert itens["vendas_dos_fundos_12m"]["valor"] == pytest.approx(12 * MILHAO)
    assert itens["compras_dos_fundos_12m"]["base"] == "2026-08-31"
    janelas = secao["tabelas"]["fundos_janelas"]
    assert [j["ate"] for j in janelas] == ["2026-08-31", "2025-08-31"]
    # set/2024 a ago/2025: 2 meses a R$ 1 mi e 10 a R$ 2 mi
    assert janelas[1]["compras"] == pytest.approx(22 * MILHAO)


def test_painel_sem_compras_nao_tem_o_movimento_dos_fundos() -> None:
    painel = _painel().drop(columns=["compras", "vendas"])
    assert _capital(painel=painel) is None


def test_capital_sem_nada_nao_existe() -> None:
    assert _capital() is None


# --- registro, regra de mostrar e ordem ----------------------------------------------------------


@pytest.mark.parametrize("chave", ["qualidade_do_lucro", "capital_e_acionistas"])
def test_secoes_novas_estao_registradas_e_podem_ser_mostradas(chave: str) -> None:
    registro = {secao.chave: secao for secao in dossie.SECOES}[chave]
    dossie.exigir_que_pode_mostrar(registro.tabelas)
    assert chave in dossie.LIMITES


def test_proventos_estao_registrados_na_secao_de_capital() -> None:
    registro = {secao.chave: secao for secao in dossie.SECOES}["capital_e_acionistas"]
    assert "proventos" in registro.tabelas


def test_tabelas_bloqueadas_ficam_fora_das_secoes_novas() -> None:
    lidas = {
        tabela
        for secao in dossie.SECOES
        if secao.chave in ("qualidade_do_lucro", "capital_e_acionistas")
        for tabela in secao.tabelas
    }
    assert not lidas & {"rotulos_atraso", "colunas_atraso", "pgfn_divida"}


def test_ficha_com_as_secoes_novas_passa_pelo_filtro_de_pessoas() -> None:
    secoes = [
        _qualidade(como_era=_como_era(), releases=_releases(), trocas=_trocas()),
        _capital(
            negociacoes=_negociacoes(), eventos=_eventos_de_capital(), painel=_painel()
        ),
    ]
    ficha = dossie.montar_ficha(CNPJ, "CPFL Energia", secoes, "2026-10-17")
    dossie.conferir_sem_pessoas(ficha, {"fulano de tal"})
    assert [s["chave"] for s in ficha["secoes"]] == [
        "qualidade_do_lucro",
        "capital_e_acionistas",
    ]
