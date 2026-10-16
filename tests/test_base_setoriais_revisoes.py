"""Números da operação, 2ª leva (série 4, PR 5): SAMP da ANEEL, acessos da Anatel e beneficiários da
ANS, lidos de recortes reais (acervo do servidor de casa, 14/10/2026), e as revisões de meses passados
(cada baixada é uma coleta; a revisão só vale desde o dia em que foi vista)."""

import io
from pathlib import Path

import pandas as pd
import pytest

from base.arquivo import fontes
from base.setoriais import anatel, aneel, ans, prazos, revisoes

PASTA = Path(__file__).parent / "arquivos" / "setoriais"


@pytest.fixture(scope="module")
def samp():
    return aneel.ler((PASTA / "aneel" / "samp-2024.parquet").read_bytes())


@pytest.fixture(scope="module")
def beneficiarios():
    return ans.ler(
        (PASTA / "ans" / "Beneficiarios_operadora_e_carteira.csv").read_bytes()
    )


def _anatel(nome: str) -> pd.DataFrame:
    return anatel.ler((PASTA / "anatel" / nome).read_bytes(), nome)


# --- leitores ---------------------------------------------------------------------------------------
def test_le_o_samp_no_formato_da_fonte(samp):
    assert list(samp.columns) == list(aneel.COLUNAS)
    assert set(samp["cnpj"]) == {"06840748000189", "15139629000194"}
    assert samp["competencia"].dt.is_month_end.all()
    assert not samp.duplicated(aneel.CHAVE).any()
    nucleos = samp["nucleo_ceg"].dropna()
    assert nucleos.str.fullmatch(r"\d+").all()  # texto inteiro ("31771"), não "31771.0"


def test_samp_soma_as_linhas_de_cada_acessante_e_tira_a_media_do_percentual():
    """Sem as colunas do acessante (CPF e nome), as linhas de cada consumidor livre repetem a chave."""
    bruto = pd.read_parquet(PASTA / "aneel" / "samp-2024.parquet")
    receita = bruto[bruto["DscDetalheMercado"].eq("Receita Demanda (R$)")].head(1)
    desconto = receita.assign(DscDetalheMercado="Desconto Demanda %", VlrMercado=10.0)
    dobrado = pd.concat([receita, receita, desconto, desconto.assign(VlrMercado=30.0)])
    saida = io.BytesIO()
    dobrado.to_parquet(saida, index=False)
    lido = aneel.ler(saida.getvalue()).set_index("detalhe_do_mercado")
    assert lido.loc["Receita Demanda (R$)", "valor"] == pytest.approx(
        2 * receita["VlrMercado"].iloc[0]
    )
    assert lido.loc["Receita Demanda (R$)", "linhas_somadas"] == 2
    assert lido.loc["Desconto Demanda %", "valor"] == pytest.approx(20.0)


def test_le_a_anatel_somada_por_uf_sem_municipio():
    banda = _anatel("Acessos_Banda_Larga_Fixa_2024_Colunas.csv")
    assert list(banda.columns) == list(anatel.COLUNAS)
    assert not banda.duplicated(anatel.CHAVE).any()
    bruto = pd.read_csv(
        PASTA / "anatel" / "Acessos_Banda_Larga_Fixa_2024_Colunas.csv", sep=";", dtype=str,
        encoding="utf-8-sig",
    )  # fmt: skip
    assert banda.loc[
        banda["competencia"] == "2024-12-31", "acessos"
    ].sum() == pytest.approx(pd.to_numeric(bruto["2024-12"]).sum())
    assert set(banda["servico"]) == {"banda_larga_fixa"}
    assert banda["cnpj"].str.len().eq(14).all()


def test_movel_de_2009_a_2018_traz_dois_recortes_dos_mesmos_acessos():
    modalidade = _anatel("Acessos_Telefonia_Movel_200902-2018_Modalidade_Colunas.csv")
    tecnologia = _anatel("Acessos_Telefonia_Movel_200902-2018_Tecnologia_Colunas.csv")
    assert set(modalidade["recorte"]) == {"modalidade"}
    assert set(tecnologia["recorte"]) == {"tecnologia"}
    assert set(_anatel("Acessos_Telefonia_Movel_2026_2S_Colunas.csv")["recorte"]) == {
        "completo"
    }
    with pytest.raises(ValueError, match="desconhecido"):
        anatel.servico_e_recorte("Acessos_Telefonia_Fixa_2020_Colunas.csv")


def test_le_a_ans_no_formato_da_fonte(beneficiarios):
    assert list(beneficiarios.columns) == list(ans.COLUNAS)
    assert set(beneficiarios["cd_operadora"]) == {
        "368253",
        "005711",
        "326305",
    }  # o zero à esquerda fica
    assert beneficiarios["base_de"].eq(pd.Timestamp("2026-06-30")).all()
    assert not beneficiarios.duplicated(ans.CHAVE).any()
    assert ans.URL == fontes.BENEFICIARIOS_POR_OPERADORA_DA_ANS


def test_disponivel_em_respeita_o_prazo_de_cada_fonte(samp, beneficiarios):
    assert (
        (samp["disponivel_em"] - samp["competencia"])
        .dt.days.eq(prazos.DIAS_ATE_PUBLICAR_MENSAL)
        .all()
    )
    assert (
        (beneficiarios["disponivel_em"] - beneficiarios["competencia"])
        .dt.days.eq(prazos.DIAS_ATE_PUBLICAR_ANS)
        .all()
    )
    assert prazos.DIAS_ATE_PUBLICAR_ANS > prazos.ATRASO_MEDIDO_ANS


# --- revisões ---------------------------------------------------------------------------------------
def _coleta(valor: float, gerado: str = "2026-09-15") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competencia": pd.to_datetime(["2026-06-30", "2026-07-31"]),
            "codigo": ["A", "A"],
            "valor": [valor, 5.0],
            "gerado_em": pd.Timestamp(gerado),
            "disponivel_em": pd.to_datetime(["2026-08-29", "2026-09-29"]),
        }
    )


def test_mes_revisado_vira_versao_e_como_era_ignora_a_revisao():
    chave = ["competencia", "codigo"]
    tabela = revisoes.juntar_coletas(
        [
            (pd.Timestamp("2026-10-14"), _coleta(1.0)),
            (pd.Timestamp("2026-11-14"), _coleta(2.0)),
        ],
        chave,
        carimbos=("gerado_em",),
    )
    junho = tabela[tabela["competencia"] == "2026-06-30"].sort_values(revisoes.VISTO_EM)
    assert junho["valor"].tolist() == [1.0, 2.0]
    assert junho["disponivel_em"].tolist() == [
        pd.Timestamp("2026-08-29"),
        pd.Timestamp("2026-11-14"),
    ]
    assert (
        len(tabela[tabela["competencia"] == "2026-07-31"]) == 1
    )  # o mesmo valor não vira linha
    antes = revisoes.como_era_em(tabela, "2026-11-13", chave)
    depois = revisoes.como_era_em(tabela, "2026-11-14", chave)
    assert antes.set_index("competencia").loc["2026-06-30", "valor"] == 1.0
    assert depois.set_index("competencia").loc["2026-06-30", "valor"] == 2.0
    assert revisoes.como_era_em(tabela, "2026-08-28", chave).empty


def test_carimbo_que_muda_sem_mudar_o_numero_nao_e_revisao():
    tabela = revisoes.juntar_coletas(
        [
            (pd.Timestamp("2026-10-14"), _coleta(1.0, "2026-09-15")),
            (pd.Timestamp("2026-11-14"), _coleta(1.0, "2026-10-15")),
        ],
        ["competencia", "codigo"],
        carimbos=("gerado_em",),
    )
    assert len(tabela) == 2
    assert (
        tabela["gerado_em"].eq(pd.Timestamp("2026-09-15")).all()
    )  # fica o da primeira vez


def test_revisao_vista_antes_do_prazo_vale_desde_o_prazo():
    """A revisão nunca adianta o número: vista antes do prazo da fonte, vale do prazo."""
    tabela = revisoes.juntar_coletas(
        [
            (pd.Timestamp("2026-07-10"), _coleta(1.0)),
            (pd.Timestamp("2026-07-20"), _coleta(2.0)),
        ],
        ["competencia", "codigo"],
        carimbos=("gerado_em",),
    )
    revisada = tabela[tabela["valor"] == 2.0]
    assert revisada["disponivel_em"].iloc[0] == pd.Timestamp("2026-08-29")
    era = revisoes.como_era_em(tabela, "2026-08-29", ["competencia", "codigo"])
    assert (
        era.set_index("competencia").loc["2026-06-30", "valor"] == 2.0
    )  # a mais nova vence


def test_sem_coleta_nao_junta_nada():
    with pytest.raises(ValueError, match="nenhuma coleta"):
        revisoes.juntar_coletas([], ["competencia"])
