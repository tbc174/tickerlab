"""Gatilho G1 das notas de dado: resultado trimestral (ADR 0093, plano das notícias, Tarefa 4).

Os números de ACME são pequenos de propósito, para conferir a conta à mão:

    receita acumulada     2025: 3M=90   6M=240  9M=380  12M=560      2026: 3M=100  6M=250  9M=420
    trimestre isolado     2025: 1T=90   2T=150  3T=140  4T=180       2026: 1T=100  2T=150  3T=170
    resultado operacional 2025: 9, 30, 48, 80      2026: 12, 33, 60   (isolado 2026: 12, 21, 27)
    lucro                 2025: 5, 18, 30, 50      2026: 7, 20, 38    (isolado 2026: 7, 13, 18)
    dívida bruta (cp+lp)  dez/25=100  mar/26=90  jun/26=100  set/26=120
"""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base.noticias_fatos import (
    COLUNAS_DOS_FATOS,
    COLUNAS_DOS_NUMEROS,
    fatos_de_resultado,
    universo_em,
)

ACME = "11.111.111/0001-11"
OUTRA = "22.222.222/0001-22"
COLETADO = datetime(2026, 10, 17, tzinfo=UTC)

RECEITA = {
    (2025, 3): 90, (2025, 6): 240, (2025, 9): 380, (2025, 12): 560,
    (2026, 3): 100, (2026, 6): 250, (2026, 9): 420,
}  # fmt: skip
EBIT = {
    (2025, 3): 9, (2025, 6): 30, (2025, 9): 48, (2025, 12): 80,
    (2026, 3): 12, (2026, 6): 33, (2026, 9): 60,
}  # fmt: skip
LUCRO = {
    (2025, 3): 5, (2025, 6): 18, (2025, 9): 30, (2025, 12): 50,
    (2026, 3): 7, (2026, 6): 20, (2026, 9): 38,
}  # fmt: skip
DIVIDA = {  # (circulante, não circulante)
    (2025, 12): (30, 70), (2026, 3): (20, 70), (2026, 6): (25, 75), (2026, 9): (40, 80),
}  # fmt: skip
ENTREGA = {  # quando cada documento ficou público
    (2025, 3): "2025-05-09", (2025, 6): "2025-08-08", (2025, 9): "2025-11-07",
    (2025, 12): "2026-03-20",
    (2026, 3): "2026-05-08", (2026, 6): "2026-08-07", (2026, 9): "2026-11-06",
}  # fmt: skip
FIM = {3: "03-31", 6: "06-30", 9: "09-30", 12: "12-31"}


def _linha(cnpj, conta, ano, mes, valor, *, grupo="con", demonstracao="DRE", **extra):
    dre = demonstracao == "DRE"
    linha = {
        "cnpj": cnpj,
        "empresa": "ACME S.A.",
        "grupo": grupo,
        "demonstracao": demonstracao,
        "conta": conta,
        "descricao": conta,
        "inicio": pd.Timestamp(f"{ano}-01-01") if dre else pd.NaT,
        "fim": pd.Timestamp(f"{ano}-{FIM[mes]}"),
        "valor": float(valor),
        "documento": "DFP" if mes == 12 else "ITR",
        "referencia": pd.Timestamp(f"{ano}-{FIM[mes]}"),
        "versao": 1,
        "ordem": "ultimo",
        "origem": "dados_abertos",
        "divulgado_em": pd.Timestamp(ENTREGA[(ano, mes)]),
        "ate": pd.NaT,
    }
    linha.update(extra)
    return linha


def _acme(cnpj=ACME, grupo="con"):
    linhas = []
    for conta, serie in (("3.01", RECEITA), ("3.05", EBIT), ("3.11", LUCRO)):
        linhas += [
            _linha(cnpj, conta, ano, mes, valor, grupo=grupo)
            for (ano, mes), valor in serie.items()
        ]
    for (ano, mes), (circulante, longo) in DIVIDA.items():
        for conta, valor in (("2.01.04", circulante), ("2.02.01", longo)):
            linhas.append(
                _linha(cnpj, conta, ano, mes, valor, grupo=grupo, demonstracao="BPP")
            )
    return linhas


def _base(*linhas):
    base = pd.DataFrame(list(linhas))
    for coluna in ("inicio", "fim", "referencia", "divulgado_em", "ate"):
        base[coluna] = pd.to_datetime(base[coluna])
    return base


def _numero(numeros, id_fato, campo):
    achado = numeros[(numeros["id_fato"] == id_fato) & (numeros["campo"] == campo)]
    assert len(achado) == 1, (campo, achado)
    return achado.iloc[0]


def _valor(numeros, id_fato, campo):
    return _numero(numeros, id_fato, campo)["valor"]


def _roda(base, dia, universo=(ACME,), **opcoes):
    return fatos_de_resultado(base, set(universo), dia, coletado_em=COLETADO, **opcoes)


def _achar(linhas, conta, ano, mes):
    return next(
        linha
        for linha in linhas
        if linha["conta"] == conta and linha["fim"] == pd.Timestamp(f"{ano}-{FIM[mes]}")
    )


# --- trimestre isolado, conferido à mão -----------------------------------------------------------


def test_terceiro_trimestre_e_nove_meses_menos_seis_meses():
    fatos, numeros = _roda(_base(*_acme()), date(2026, 11, 9))
    assert len(fatos) == 1
    fato = fatos.iloc[0]
    assert fato["pauta"] == "resultado_trimestral"
    assert fato["aconteceu_em"] == pd.Timestamp("2026-09-30")
    assert fato["publico_em"] == pd.Timestamp("2026-11-06")
    assert not fato["reapresentacao"]
    i = fato["id_fato"]
    assert _valor(numeros, i, "receita_trimestre") == 170  # 420 - 250
    assert (
        _valor(numeros, i, "receita_mesmo_trimestre_ano_anterior") == 140
    )  # 380 - 240
    assert _valor(numeros, i, "receita_trimestre_anterior") == 150  # 250 - 100
    assert _valor(numeros, i, "resultado_operacional_trimestre") == 27  # 60 - 33
    assert (
        _valor(numeros, i, "resultado_operacional_mesmo_trimestre_ano_anterior") == 18
    )
    assert _valor(numeros, i, "resultado_operacional_trimestre_anterior") == 21
    assert _valor(numeros, i, "lucro_trimestre") == 18  # 38 - 20
    assert _valor(numeros, i, "lucro_mesmo_trimestre_ano_anterior") == 12
    assert _valor(numeros, i, "lucro_trimestre_anterior") == 13
    # a dívida é saldo: o do fim do trimestre e o do fim do trimestre anterior
    assert _valor(numeros, i, "divida_bruta") == 120  # 40 + 80
    assert _valor(numeros, i, "divida_bruta_trimestre_anterior") == 100  # 25 + 75


def test_cada_numero_diz_de_onde_saiu():
    fatos, numeros = _roda(_base(*_acme()), date(2026, 11, 9))
    i = fatos.iloc[0]["id_fato"]
    receita = _numero(numeros, i, "receita_trimestre")
    assert receita["unidade"] == "reais"
    assert receita["periodo"] == "3T26"
    assert receita["origem_conta"] == "3.01"
    assert receita["origem_periodo"] == "acumulado"
    assert receita["origem_versao"] == 1
    assert receita["origem_divulgado_em"] == pd.Timestamp("2026-11-06")
    assert receita["calculo"] == "acumulado 9M26 - acumulado 6M26"
    anterior = _numero(numeros, i, "receita_trimestre_anterior")
    assert anterior["periodo"] == "2T26"
    assert anterior["calculo"] == "acumulado 6M26 - acumulado 3M26"
    # a data é a do documento mais novo entre as partes do cálculo
    assert anterior["origem_divulgado_em"] == pd.Timestamp("2026-08-07")
    divida = _numero(numeros, i, "divida_bruta")
    assert divida["periodo"] == "30/09/2026"
    assert divida["origem_conta"] == "2.01.04 + 2.02.01"
    assert divida["origem_periodo"] == "posicao"
    assert divida["calculo"] == "2.01.04 + 2.02.01"


@pytest.mark.parametrize(
    ("dia", "periodo", "receita", "ano_anterior", "anterior", "calculo"),
    [
        (date(2026, 5, 11), "1T26", 100, 90, 180, ""),  # 1T = acumulado de 3 meses
        (date(2026, 8, 10), "2T26", 150, 150, 100, "acumulado 6M26 - acumulado 3M26"),
    ],
)
def test_primeiro_e_segundo_trimestre(
    dia, periodo, receita, ano_anterior, anterior, calculo
):
    fatos, numeros = _roda(_base(*_acme()), dia)
    assert len(fatos) == 1
    i = fatos.iloc[0]["id_fato"]
    assert _numero(numeros, i, "receita_trimestre")["periodo"] == periodo
    assert _valor(numeros, i, "receita_trimestre") == receita
    assert _valor(numeros, i, "receita_mesmo_trimestre_ano_anterior") == ano_anterior
    assert _valor(numeros, i, "receita_trimestre_anterior") == anterior
    assert _numero(numeros, i, "receita_trimestre")["calculo"] == calculo


def test_quarto_trimestre_e_exercicio_menos_nove_meses_e_parte_faltando_some_a_comparacao():
    fatos, numeros = _roda(_base(*_acme()), date(2026, 3, 23))
    assert len(fatos) == 1
    fato = fatos.iloc[0]
    assert fato["aconteceu_em"] == pd.Timestamp("2025-12-31")
    i = fato["id_fato"]
    receita = _numero(numeros, i, "receita_trimestre")
    assert receita["valor"] == 180  # 560 - 380
    assert receita["periodo"] == "4T25"
    assert receita["origem_periodo"] == "exercicio"
    assert receita["calculo"] == "exercício 12M25 - acumulado 9M25"
    assert _valor(numeros, i, "receita_trimestre_anterior") == 140  # 3T25
    # 2024 não está na base: sem a parte, a comparação não existe (e não é inventada)
    faltando = numeros[
        (numeros["id_fato"] == i)
        & (numeros["campo"] == "receita_mesmo_trimestre_ano_anterior")
    ]
    assert faltando.empty


def test_trimestre_do_fato_sem_parte_nao_vira_fato():
    """Sem o acumulado de 6 meses não há 3T isolado: não sai nota com número inventado."""
    sem_o_semestre = [
        linha
        for linha in _acme()
        if not (
            linha["demonstracao"] == "DRE"
            and linha["fim"] == pd.Timestamp("2026-06-30")
        )
    ]
    fatos, _ = _roda(_base(*sem_o_semestre), date(2026, 11, 9))
    assert fatos.empty


# --- universo, janela, consolidado/individual ----------------------------------------------------


def test_fora_do_universo_nao_gera_fato():
    fatos, numeros = _roda(_base(*_acme()), date(2026, 11, 9), universo=(OUTRA,))
    assert fatos.empty
    assert numeros.empty
    assert list(fatos.columns) == COLUNAS_DOS_FATOS
    assert list(numeros.columns) == COLUNAS_DOS_NUMEROS


def test_janela_de_cinco_dias_uteis():
    base = _base(*_acme())
    # publicado na sexta 06/11: só vale o que ficou público até ontem
    assert _roda(base, date(2026, 11, 6))[0].empty
    assert len(_roda(base, date(2026, 11, 7))[0]) == 1
    # sexta, segunda, terça, quarta e quinta = 5 dias úteis: ainda entra
    assert len(_roda(base, date(2026, 11, 13))[0]) == 1
    # com a sexta seguinte são 6: o fato é velho demais e não vira nota
    assert _roda(base, date(2026, 11, 14))[0].empty


def test_sem_consolidado_vale_o_individual_com_marca():
    fatos, _ = _roda(_base(*_acme(grupo="ind")), date(2026, 11, 9))
    assert len(fatos) == 1
    assert "individual" in fatos.iloc[0]["marcas"]


def test_com_consolidado_nao_ha_marca_de_individual():
    fatos, _ = _roda(_base(*_acme(), *_acme(grupo="ind")), date(2026, 11, 9))
    assert len(fatos) == 1
    assert "individual" not in fatos.iloc[0]["marcas"]


def test_achado_de_qualidade_aberto_leva_a_marca():
    fatos, _ = _roda(_base(*_acme()), date(2026, 11, 9), em_conferencia={ACME})
    assert fatos.iloc[0]["marcas"] == ["dado_em_conferencia"]


def test_conta_faltando_nao_gera_fato():
    sem_divida = [linha for linha in _acme() if linha["demonstracao"] != "BPP"]
    assert _roda(_base(*sem_divida), date(2026, 11, 9))[0].empty


# --- universo: ticker na data e setor financeiro fora ---------------------------------------------


def test_universo_so_companhias_com_ticker_na_data_e_fora_dos_financeiros():
    banco, velha, nova = (
        "33.333.333/0001-33",
        "44.444.444/0001-44",
        "55.555.555/0001-55",
    )
    tickers = pd.DataFrame(
        {
            "codigo": ["ACME3", "BANC3", "VELH3", "NOVA3"],
            "cnpj": [ACME, banco, velha, nova],
            "primeiro_visto": pd.to_datetime(["2020-01-01"] * 3 + ["2027-01-01"]),
            "valido_ate": pd.to_datetime([None, None, "2025-01-01", None]),
        }
    )
    setores = pd.DataFrame(
        {
            "cnpj": [ACME, banco, velha, nova],
            "setor": ["Energia Elétrica", "Bancos", "Comércio", "Comércio"],
        }
    )
    assert universo_em(tickers, setores, date(2026, 11, 9)) == {ACME}


# --- reapresentação --------------------------------------------------------------------------------


def _com_reapresentacao(lucro_novo=36, entrega="2026-11-20"):
    linhas = _acme()
    antiga = _achar(linhas, "3.11", 2026, 9)
    antiga["ate"] = pd.Timestamp(entrega)
    nova = {
        **antiga,
        "versao": 2,
        "valor": float(lucro_novo),
        "divulgado_em": pd.Timestamp(entrega),
        "ate": pd.NaT,
    }
    return [*linhas, nova]


def test_reapresentacao_que_muda_uma_das_quatro_contas_vira_fato_com_o_anterior():
    base = _base(*_com_reapresentacao())
    v1, _ = _roda(base, date(2026, 11, 9))
    v2, numeros = _roda(base, date(2026, 11, 23))
    assert len(v1) == 1
    assert len(v2) == 1
    fato = v2.iloc[0]
    assert bool(fato["reapresentacao"]) is True
    assert fato["publico_em"] == pd.Timestamp("2026-11-20")
    assert fato["fato_anterior"] == v1.iloc[0]["id_fato"]
    assert fato["id_fato"] != v1.iloc[0]["id_fato"]
    assert _valor(numeros, fato["id_fato"], "lucro_trimestre") == 16  # 36 - 20
    assert _numero(numeros, fato["id_fato"], "lucro_trimestre")["origem_versao"] == 2


def test_reapresentacao_que_so_mexe_em_outra_conta_nao_gera_nota():
    linhas = _acme()
    ativo = {
        **linhas[0],
        "demonstracao": "BPA",
        "conta": "1.01",
        "valor": 1.0,
        "versao": 2,
        "divulgado_em": pd.Timestamp("2026-11-20"),
        "inicio": pd.NaT,
    }
    assert _roda(_base(*linhas, ativo), date(2026, 11, 23))[0].empty


def test_reapresentacao_com_as_quatro_contas_iguais_nao_gera_nota():
    base = _base(*_com_reapresentacao(lucro_novo=38))
    assert _roda(base, date(2026, 11, 23))[0].empty


# --- sem olhar o futuro ----------------------------------------------------------------------------


def _com_semestre_reapresentado_depois():
    linhas = _acme()
    semestre = _achar(linhas, "3.01", 2026, 6)
    semestre["ate"] = pd.Timestamp("2026-12-15")
    futura = {
        **semestre,
        "versao": 2,
        "valor": 260.0,
        "divulgado_em": pd.Timestamp("2026-12-15"),
        "ate": pd.NaT,
    }
    return [*linhas, futura]


def test_reapresentacao_posterior_nao_muda_o_fato_de_antes():
    """O 2T foi reapresentado em dezembro: a nota de novembro continua com o valor de agosto."""
    base = _base(*_com_semestre_reapresentado_depois())
    fatos, numeros = _roda(base, date(2026, 11, 9))
    assert _valor(numeros, fatos.iloc[0]["id_fato"], "receita_trimestre") == 170


def test_propriedade_nenhuma_origem_do_futuro_nem_ja_trocada():
    """Em todo dia: `origem_divulgado_em <= publico_em` e a linha de origem ainda valia em `publico_em`."""
    base = _base(*_com_semestre_reapresentado_depois())
    conferidos = 0
    for dia in pd.date_range("2026-03-01", "2026-12-31"):
        fatos, numeros = _roda(base, dia.date())
        publico = fatos.set_index("id_fato")["publico_em"]
        for _, n in numeros.iterrows():
            quando = publico[n["id_fato"]]
            assert n["origem_divulgado_em"] <= quando
            usadas = base[
                base["conta"].isin(n["origem_conta"].split(" + "))
                & (base["versao"] == n["origem_versao"])
                & (base["divulgado_em"] == n["origem_divulgado_em"])
            ]
            assert not usadas.empty
            assert (usadas["ate"].isna() | (usadas["ate"] > quando)).any()
            conferidos += 1
    assert conferidos > 50


# --- identidade estável ---------------------------------------------------------------------------


def test_montar_duas_vezes_da_o_mesmo_id_e_o_mesmo_hash():
    base = _base(*_acme())
    primeiro = _roda(base, date(2026, 11, 9))
    segundo = _roda(base.iloc[::-1].reset_index(drop=True), date(2026, 11, 9))
    assert primeiro[0]["id_fato"].tolist() == segundo[0]["id_fato"].tolist()
    assert primeiro[0]["hash_da_linha"].tolist() == segundo[0]["hash_da_linha"].tolist()
    pd.testing.assert_frame_equal(primeiro[1], segundo[1])


def test_o_mesmo_fato_em_outro_dia_da_janela_tem_o_mesmo_id():
    base = _base(*_acme())
    assert (
        _roda(base, date(2026, 11, 9))[0]["id_fato"].tolist()
        == _roda(base, date(2026, 11, 12))[0]["id_fato"].tolist()
    )


def test_o_fato_cumpre_o_contrato_da_tabela():
    fatos, numeros = _roda(_base(*_acme()), date(2026, 11, 9))
    fato = fatos.iloc[0]
    assert list(fatos.columns) == COLUNAS_DOS_FATOS
    assert list(numeros.columns) == COLUNAS_DOS_NUMEROS
    assert fato["tabela_de_origem"] == "demonstracoes_como_era"
    assert fato["versao_do_gatilho"] == "resultado-1.0"
    assert fato["licenca"] == "cvm"
    assert fato["empresa"] == "ACME S.A."
    assert fato["link"].startswith("https://dados.cvm.gov.br/")
    assert fato["topico"] == ""
    assert fato["aconteceu_em"] <= fato["publico_em"]
    assert len(fato["hash_da_linha"]) == 64
    assert len(fato["id_fato"]) == 64
