"""Energia na base (série T, PR T6): PLD da CCEE (hora, dia, mês e a semana de antes de 2021), restrição de
geração eólica e solar do ONS (por usina e hora) e capacidade instalada do ONS (por unidade geradora).

Amostras reais recortadas do acervo (`tests/arquivos/setoriais/ccee` e `ons`): os seis desenhos de CSV da
CCEE (aspas e CRLF até 2024, sem aspas e LF depois; o "horário" de 2001 a 2020 é semanal, com três
patamares sem rótulo), duas usinas de restrição eólica de 09/2026, uma fotovoltaica de 04/2024 e oito
unidades do cadastro de capacidade (seis de Xingó e duas desativadas).
"""

from pathlib import Path

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from base.setoriais import (
    ccee,
    ligacao,
    ons_capacidade,
    ons_restricao,
    prazos,
    revisoes,
)

PASTA = Path(__file__).parent / "arquivos" / "setoriais"
ENDERECO_EOLICA = "https://x.s3.amazonaws.com/dataset/restricao_coff_eolica_tm/RESTRICAO_COFF_EOLICA_2026_09.parquet"
ENDERECO_SOLAR = "https://x.s3.amazonaws.com/dataset/restricao_coff_fotovoltaica_tm/RESTRICAO_COFF_FOTOVOLTAICA_2024_04.parquet"


def _pld(nome: str) -> pd.DataFrame:
    return ccee.ler((PASTA / "ccee" / f"{nome}.csv").read_bytes())


# --- CCEE: os desenhos da fonte -------------------------------------------------------------------
def test_pld_horario_com_aspas_e_crlf_de_2021():
    tabela = _pld("hora_2021")
    assert list(tabela.columns) == list(ccee.COLUNAS)
    assert set(tabela["granularidade"]) == {"hora"}
    assert set(tabela["submercado"]) == {"NORDESTE", "NORTE", "SUDESTE", "SUL"}
    primeira = tabela.iloc[0]
    assert primeira["referencia"] == pd.Timestamp("2021-01-01 00:00")
    assert primeira["competencia"] == pd.Timestamp("2021-01-31")
    assert primeira["periodo_de_comercializacao"] == 1
    assert primeira["pld"] == pytest.approx(204.36)


def test_pld_horario_sem_aspas_e_lf_de_2025():
    tabela = _pld("hora_2025")
    segunda_hora = tabela[tabela["periodo_de_comercializacao"] == 722]
    assert set(segunda_hora["referencia"]) == {pd.Timestamp("2025-12-31 01:00")}
    assert segunda_hora["pld"].dtype.kind == "f"
    assert set(tabela["competencia"]) == {pd.Timestamp("2025-12-31")}


def test_pld_diario_tem_a_data_em_dia_mes_ano():
    for nome, dia in [("dia_2021", "2021-01-08"), ("dia_2025", "2025-12-31")]:
        tabela = _pld(nome)
        assert set(tabela["granularidade"]) == {"dia"}
        assert tabela["referencia"].iloc[0] == pd.Timestamp(dia)
        assert tabela["periodo_de_comercializacao"].isna().all()


def test_pld_mensal_vale_para_o_mes_inteiro():
    tabela = _pld("mes_2001")
    assert set(tabela["granularidade"]) == {"mes"}
    assert tabela["referencia"].iloc[0] == pd.Timestamp("2001-01-01")
    assert tabela["competencia"].iloc[0] == pd.Timestamp("2001-01-31")
    sul = tabela[
        (tabela["submercado"] == "SUL") & (tabela["competencia"] == "2001-02-28")
    ]
    assert sul["pld"].iloc[0] == pytest.approx(154.17)


def test_arquivo_de_horario_ate_2020_e_semanal_por_patamar():
    """Antes de 2021 o "horário" da CCEE é um preço por semana e patamar, sem rótulo do patamar: as
    linhas repetidas viram `ordem` (a posição no arquivo), nunca somem."""
    tabela = _pld("hora_2001_2020")
    assert set(tabela["granularidade"]) == {"semana_por_patamar"}
    assert tabela["referencia"].iloc[0] == pd.Timestamp("2001-06-30")
    nordeste = tabela[tabela["submercado"] == "NORDESTE"]
    assert nordeste["ordem"].tolist() == [1, 2, 3, 1, 2, 3]  # 2 semanas, 3 patamares
    assert len(tabela) == 15  # nada foi descartado
    assert not tabela.duplicated(list(ccee.CHAVE)).any()


def test_pld_de_arquivo_desconhecido_para_com_erro():
    with pytest.raises(ValueError, match="desenho"):
        ccee.ler(b"A;B\n1;2\n")


# --- CCEE: prazos e o passado -----------------------------------------------------------------------
def test_pld_so_vale_depois_de_publicado():
    """O preço do dia sai no dia anterior; a regra usa o fim do dia + 1 (nunca adianta). A média do mês
    só existe depois do mês."""
    for nome, dias in [("hora_2025", 1), ("dia_2021", 1)]:
        tabela = _pld(nome)
        dia = tabela["referencia"].dt.normalize()
        assert (tabela["disponivel_em"] - dia == pd.Timedelta(days=dias)).all()
    mensal = _pld("mes_2025")
    assert (mensal["disponivel_em"] > mensal["competencia"]).all()
    semanal = _pld("hora_2001_2020")
    assert (
        semanal["disponivel_em"] - semanal["referencia"] == pd.Timedelta(days=7)
    ).all()


# --- ONS: restrição eólica e solar ------------------------------------------------------------------
@pytest.fixture(scope="module")
def eolica() -> pd.DataFrame:
    conteudo = (
        PASTA / "ons_energia" / "RESTRICAO_COFF_EOLICA_2026_09.parquet"
    ).read_bytes()
    return ons_restricao.ler(conteudo, ENDERECO_EOLICA)


def test_restricao_vira_uma_linha_por_usina_e_hora(eolica):
    assert list(eolica.columns) == list(ons_restricao.COLUNAS)
    assert set(eolica["tipo"]) == {"eolica"}
    assert not eolica.duplicated(list(ons_restricao.CHAVE)).any()
    hora = eolica[
        (eolica["id_ons"] == "CJU_MAPLN") & (eolica["instante"] == "2026-09-01 09:00")
    ]
    assert len(hora) == 1
    linha = hora.iloc[0]
    assert linha["leituras"] == 2
    assert linha["geracao_mwmed"] == pytest.approx((397.244 + 386.284) / 2)
    assert linha["nao_realizada_mwmed"] == pytest.approx((33.196 + 43.344) / 2)
    assert linha["minutos_restricao"] == 54
    assert (linha["razao_da_restricao"], linha["origem_da_restricao"]) == ("ENE", "SIS")
    assert linha["agente_operador"] == "SIMM"


def test_hora_sem_restricao_fica_vazia_e_nao_zero(eolica):
    hora = eolica[
        (eolica["id_ons"] == "CJU_MAPLN") & (eolica["instante"] == "2026-09-01 08:00")
    ]
    linha = hora.iloc[0]
    assert pd.isna(linha["nao_realizada_mwmed"]) and pd.isna(linha["minutos_restricao"])
    assert pd.isna(linha["razao_da_restricao"])
    assert linha["referencia_mwmed"] == pytest.approx((430.413 + 114.367) / 2)


def test_restricao_fotovoltaica_e_tipo_pela_pasta_do_endereco():
    conteudo = (
        PASTA / "ons_energia" / "RESTRICAO_COFF_FOTOVOLTAICA_2024_04.parquet"
    ).read_bytes()
    solar = ons_restricao.ler(conteudo, ENDERECO_SOLAR)
    assert set(solar["tipo"]) == {"fotovoltaica"}
    assert solar["ceg"].isna().all()  # "-" do conjunto vira vazio
    assert (solar["disponivel_em"] - solar["instante"] == pd.Timedelta(days=2)).all()


def test_endereco_de_restricao_sem_tipo_para_com_erro():
    conteudo = (
        PASTA / "ons_energia" / "RESTRICAO_COFF_EOLICA_2026_09.parquet"
    ).read_bytes()
    with pytest.raises(ValueError, match="tipo"):
        ons_restricao.ler(conteudo, "https://x/arquivo.parquet")


def test_destino_da_restricao_e_o_mes_do_arquivo():
    assert ons_restricao.destino(ENDERECO_EOLICA) == "eolica_2026_09"
    assert ons_restricao.destino(ENDERECO_SOLAR) == "fotovoltaica_2024_04"
    assert ons_restricao.destino("https://x/Dicionario.pdf") is None


def test_revisao_da_restricao_so_vale_depois_de_vista(eolica):
    """O ONS fecha a apuração depois: o valor revisado vale só desde o dia da coleta que o trouxe."""
    chave = list(ons_restricao.CHAVE)
    revisada = eolica.copy()
    alvo = (revisada["id_ons"] == "CJU_MAPLN") & (
        revisada["instante"] == "2026-09-01 09:00"
    )
    revisada.loc[alvo, "nao_realizada_mwmed"] = 99.0
    coletas = [
        (pd.Timestamp("2026-10-14"), eolica),
        (pd.Timestamp("2026-11-20"), revisada),
    ]
    tabela = revisoes.juntar_coletas(coletas, chave, ons_restricao.CARIMBOS)

    def valor(data: str) -> float:
        vistas = revisoes.como_era_em(tabela, data, chave)
        linha = vistas[
            (vistas["id_ons"] == "CJU_MAPLN")
            & (vistas["instante"] == "2026-09-01 09:00")
        ]
        return float(linha["nao_realizada_mwmed"].iloc[0])

    assert valor("2026-11-01") == pytest.approx((33.196 + 43.344) / 2)
    assert valor("2026-11-20") == 99.0


# --- ONS: capacidade instalada ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def capacidade() -> pd.DataFrame:
    return ons_capacidade.ler(
        (PASTA / "ons_energia" / "CAPACIDADE_GERACAO.parquet").read_bytes()
    )


def test_capacidade_por_unidade_geradora(capacidade):
    assert list(capacidade.columns) == list(ons_capacidade.COLUNAS)
    assert not capacidade.duplicated(list(ons_capacidade.CHAVE)).any()
    xingo = capacidade[capacidade["usina"].str.startswith("XING")]
    assert len(xingo) == 6 and set(xingo["proprietario"]) == {"AXIA NORDESTE"}
    assert xingo["potencia_efetiva_mw"].sum() == pytest.approx(6 * 527.0)
    assert set(xingo["tipo_de_usina"]) == {"HIDROELÉTRICA"}  # a acentuação vem certa


def _capacidade_vista(capacidade: pd.DataFrame, data: str) -> pd.DataFrame:
    coletas = [(pd.Timestamp("2026-10-14"), capacidade)]
    chave = list(ons_capacidade.CHAVE)
    tabela = revisoes.juntar_coletas(coletas, chave, ons_capacidade.CARIMBOS)
    return revisoes.como_era_em(tabela, data, chave)


def test_unidade_vale_desde_a_entrada_em_operacao(capacidade):
    """A unidade existe para quem pergunta a partir do dia em que entrou em operação (e antes disso não:
    cortar o futuro não a traz para o passado)."""
    assert (capacidade["disponivel_em"] == capacidade["entrada_em_operacao"]).all()
    tabela = _capacidade_vista(capacidade, "1995-06-01")
    assert sorted(tabela["numero_da_unidade"]) == [
        "5",
        "6",
    ]  # a 4 só entrou em out/1995


def test_unidade_desativada_guarda_a_data_sem_apagar_a_linha(capacidade):
    desativadas = capacidade[capacidade["desativada_em"].notna()]
    assert len(desativadas) == 2
    assert (desativadas["desativada_em"] > desativadas["entrada_em_operacao"]).all()


# --- ligação à empresa só pela B13 ------------------------------------------------------------------
def _empresa_serie() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fonte": ["ons-capacidade-geracao"] * 3,
            "chave": ["AXIA NORDESTE", "SIMM", "GEBRA"],
            "cnpj_companhia": ["00.000.000/0001-91", None, "11.111.111/0001-11"],
            "principal": [True, True, True],
        }
    )


def test_capacidade_liga_pelo_nome_exato_do_proprietario(capacidade):
    ligada = ligacao.ligar(
        capacidade, "proprietario", ons_capacidade.FONTE, _empresa_serie()
    )
    assert set(ligada.loc[ligada["cnpj_companhia"].notna(), "proprietario"]) == {
        "AXIA NORDESTE",
        "GEBRA",
    }
    buracos = ligacao.buracos(
        capacidade,
        "proprietario",
        "potencia_efetiva_mw",
        ons_capacidade.FONTE,
        _empresa_serie(),
    )
    assert buracos.empty or "AXIA NORDESTE" not in set(buracos["chave"])


def test_restricao_liga_pelo_operador_e_o_que_nao_liga_vai_para_os_buracos(eolica):
    ligada = ligacao.ligar(
        eolica, "agente_operador", ons_restricao.FONTE_DA_LIGACAO, _empresa_serie()
    )
    assert ligada["cnpj_companhia"].isna().all()  # SIMM não tem CNPJ na B13 de teste
    buracos = ligacao.buracos(
        eolica,
        "agente_operador",
        "geracao_mwmed",
        ons_restricao.FONTE_DA_LIGACAO,
        _empresa_serie(),
    )
    assert set(buracos["chave"]) == {"SIMM", "AUREN OPERAÇÕES"}
    assert buracos["valor"].iloc[0] > 0


# --- sem olhar o futuro (propriedade) -----------------------------------------------------------------
_TODO_O_PLD = pd.concat(
    [
        _pld(n)
        for n in ("hora_2021", "dia_2021", "mes_2021", "mes_2001", "hora_2001_2020")
    ],
    ignore_index=True,
)
_CAPACIDADE = ons_capacidade.ler(
    (PASTA / "ons_energia" / "CAPACIDADE_GERACAO.parquet").read_bytes()
)
_DIAS = st.dates(
    min_value=pd.Timestamp("1990-01-01").date(),
    max_value=pd.Timestamp("2026-12-31").date(),
)


@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(corte=_DIAS, depois=st.integers(min_value=0, max_value=4000))
def test_cortar_o_futuro_nao_muda_o_passado_do_pld(corte, depois):
    """O que era público no dia do corte é o mesmo vendo a base mais tarde: o futuro só acrescenta."""
    dia = pd.Timestamp(corte)
    ordem = list(ccee.CHAVE)
    no_dia = _TODO_O_PLD[_TODO_O_PLD["disponivel_em"] <= dia]
    mais_tarde = _TODO_O_PLD[
        _TODO_O_PLD["disponivel_em"] <= dia + pd.Timedelta(days=depois)
    ]
    do_passado = mais_tarde[mais_tarde["disponivel_em"] <= dia]
    pd.testing.assert_frame_equal(
        no_dia.sort_values(ordem).reset_index(drop=True),
        do_passado.sort_values(ordem).reset_index(drop=True),
    )
    assert (no_dia["disponivel_em"] <= dia).all()
    assert len(mais_tarde) >= len(no_dia)


@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(corte=_DIAS)
def test_capacidade_nunca_traz_unidade_que_ainda_nao_entrou_em_operacao(corte):
    vistas = _capacidade_vista(_CAPACIDADE, pd.Timestamp(corte))
    assert (vistas["entrada_em_operacao"] <= pd.Timestamp(corte)).all()


def test_prazos_novos_dao_folga_sobre_o_medido():
    assert prazos.DIAS_ATE_PUBLICAR_PLD_SEMANAL >= 7
    assert prazos.DIAS_ATE_PUBLICAR_PLD_DIARIO >= 1
