"""Petróleo e logística na base (série T, PR T8): concessionários da ANP, produção ferroviária da ANTT
(SIADE) e preço médio do Comex Stat.

Amostras reais recortadas do acervo (`tests/arquivos/setoriais/anp`, `antt` e `comex`): os 27 concessionários
da ANP (CSV latin-1 com CRLF, CNPJ sem o zero à esquerda), 29 linhas do SIADE de 2006 e de 2026 (TU e TKU
com ponto de milhar) e 1200 linhas de cada CSV do Comex (exportação de 2024 e 2026, importação de 2026).
"""

from pathlib import Path

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from base.setoriais import (
    anp_concessionarios,
    antt_siade,
    comex_preco_medio,
    ligacao,
    prazos,
    revisoes,
)
from base.vitrine import LICENCIADA, situacao_da_licenca
from src.banco.coletas import (
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
    revenda_da_fonte,
)

PASTA = Path(__file__).parent / "arquivos" / "setoriais"
COMEX = "https://x.gov.br/comexstat-bd/ncm/"


def _ler(*partes: str) -> bytes:
    return (PASTA.joinpath(*partes)).read_bytes()


# --- ANP: concessionários ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def concessionarios() -> pd.DataFrame:
    return anp_concessionarios.ler(_ler("anp", "concessionarios.csv"))


def test_concessionarios_uma_linha_por_contrato_e_socio(concessionarios):
    assert list(concessionarios.columns) == list(anp_concessionarios.COLUNAS)
    assert len(concessionarios) == 27
    assert not concessionarios.duplicated(list(anp_concessionarios.CHAVE)).any()
    assert set(concessionarios["fase"]) == {"Produção", "Avaliação", "Exploração"}
    assert set(concessionarios["ambiente"]) == {"Terra", "Mar"}


def test_cnpj_recebe_o_zero_a_esquerda_que_a_fonte_perde(concessionarios):
    guto = concessionarios[concessionarios["empresa"] == "Guto & Cacal"].iloc[0]
    assert guto["cnpj"] == "04054366000102"  # a fonte traz 4054366000102
    assert concessionarios["cnpj"].str.len().eq(14).all()


def test_operador_vira_marca_e_sai_do_nome(concessionarios):
    consorcio = concessionarios[
        concessionarios["numero_do_contrato"] == "48610007482200671"
    ]
    assert dict(zip(consorcio["empresa"], consorcio["operador"], strict=True)) == {
        "Imetame": True,
        "IPI": False,
    }
    assert not concessionarios["empresa"].str.contains("Operador").any()


def test_participacao_em_pontos_percentuais_com_virgula_decimal(concessionarios):
    consorcio = concessionarios[
        concessionarios["numero_do_contrato"] == "48610007482200671"
    ]
    assert consorcio["participacao_pct"].tolist() == [50.0, 50.0]
    assert concessionarios["participacao_pct"].dtype.kind == "f"
    assert concessionarios["bid"].eq("AM1").sum() == 9  # os espaços à direita saem


def test_concessionarios_sem_data_propria_ficam_para_a_carga(concessionarios):
    assert concessionarios["disponivel_em"].isna().all()
    assert anp_concessionarios.destino(
        "https://x/arquivos/rc/relacao-concessionarios.csv"
    )
    assert anp_concessionarios.destino("https://x/outro.csv") is None


def test_concessionario_so_vale_desde_a_coleta_que_o_trouxe(concessionarios):
    """O arquivo não tem data: o primeiro valor vale desde a 1ª coleta e uma troca de sócio, desde a
    coleta que a trouxe. A coleta anterior continua respondendo como era."""
    primeira = pd.Timestamp("2026-10-14")
    segunda = pd.Timestamp("2026-11-14")
    antes = concessionarios.assign(disponivel_em=primeira)
    depois = antes.copy()
    depois.loc[depois["empresa"] == "IPI", "participacao_pct"] = 40.0
    depois["disponivel_em"] = segunda
    chave = list(anp_concessionarios.CHAVE)
    junta = revisoes.juntar_coletas([(primeira, antes), (segunda, depois)], chave)
    ipi = junta[junta["empresa"] == "IPI"].sort_values("visto_em")
    assert ipi["participacao_pct"].tolist() == [50.0, 40.0]
    assert ipi["disponivel_em"].tolist() == [primeira, segunda]
    em_outubro = revisoes.como_era_em(junta, "2026-10-20", chave)
    em_novembro = revisoes.como_era_em(junta, "2026-11-20", chave)
    assert (
        em_outubro[em_outubro["empresa"] == "IPI"]["participacao_pct"].iloc[0] == 50.0
    )
    assert (
        em_novembro[em_novembro["empresa"] == "IPI"]["participacao_pct"].iloc[0] == 40.0
    )
    assert len(junta) == len(antes) + 1  # só o sócio que mudou ganha linha nova
    assert (em_outubro["disponivel_em"] <= pd.Timestamp("2026-10-20")).all()


def test_concessionarios_ligam_pelo_cnpj_e_o_resto_vira_buraco(concessionarios):
    b13 = pd.DataFrame(
        {
            "fonte": [anp_concessionarios.FONTE],
            "chave": ["33000167000101"],
            "cnpj_companhia": ["33.000.167/0001-01"],
            "principal": [True],
        }
    )
    ligadas = ligacao.ligar(concessionarios, "cnpj", anp_concessionarios.FONTE, b13)
    assert ligadas["cnpj_companhia"].notna().sum() == 1  # a Petrobras
    buracos = ligacao.buracos(
        concessionarios.assign(disponivel_em=pd.Timestamp("2026-10-14")),
        "cnpj",
        "participacao_pct",
        anp_concessionarios.FONTE,
        b13,
    )
    assert "33000167000101" not in set(buracos["chave"])
    assert buracos["valor"].iloc[0] >= buracos["valor"].iloc[-1]


# --- ANTT: produção ferroviária ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def siade_2026() -> pd.DataFrame:
    return antt_siade.ler(_ler("antt", "producao_2026.csv"))


def test_siade_tira_o_ponto_de_milhar_de_tu_e_tku(siade_2026):
    assert list(siade_2026.columns) == list(antt_siade.COLUNAS)
    primeira = siade_2026.iloc[0]
    assert primeira["toneladas_uteis"] == 33420.0
    assert primeira["tku"] == 28774620.0
    assert primeira["ferrovia"] == "EFC"
    assert primeira["mercadoria"] == "Carvão Mineral"
    assert (primeira["estacao_de_origem"], primeira["uf_de_origem"]) == (
        "Ponta da Madeira",
        "MA",
    )
    assert siade_2026["tku"].dtype.kind == "f"


def test_siade_mes_vira_fim_do_mes_e_a_chave_nao_repete(siade_2026):
    assert set(siade_2026["competencia"]) == {pd.Timestamp("2026-01-31")}
    assert not siade_2026.duplicated(list(antt_siade.CHAVE)).any()


def test_siade_de_2006_tem_o_mesmo_desenho():
    antigo = antt_siade.ler(_ler("antt", "producao_2006.csv"))
    assert list(antigo.columns) == list(antt_siade.COLUNAS)
    assert antigo["competencia"].dt.year.eq(2006).all()
    assert antigo["tku"].notna().all()


def test_siade_so_vale_60_dias_depois_do_fim_do_mes(siade_2026):
    atraso = siade_2026["disponivel_em"] - siade_2026["competencia"]
    assert (atraso == pd.Timedelta(days=prazos.DIAS_ATE_PUBLICAR_MENSAL)).all()


def test_siade_destino_pelo_ano_e_sem_o_pdf():
    assert antt_siade.destino("https://x/producao_origem_destino_2026.csv") == "2026"
    assert antt_siade.destino("https://x/dicionario_producao.pdf") is None


def test_siade_liga_a_ferrovia_pela_sigla_exata(siade_2026):
    b13 = pd.DataFrame(
        {
            "fonte": [antt_siade.FONTE],
            "chave": ["EFC"],
            "cnpj_companhia": ["33.592.510/0001-54"],
            "principal": [True],
        }
    )
    buracos = ligacao.buracos(siade_2026, "ferrovia", "tku", antt_siade.FONTE, b13)
    assert "EFC" not in set(buracos["chave"])


def test_siade_revisao_de_mes_passado_vale_so_desde_a_coleta(siade_2026):
    """A ANTT pode corrigir um mês: o número novo vale desde o dia em que foi visto, nunca antes."""
    primeira, segunda = pd.Timestamp("2026-10-14"), pd.Timestamp("2026-12-01")
    revisado = siade_2026.copy()
    revisado.loc[0, "tku"] = 1.0
    chave = list(antt_siade.CHAVE)
    junta = revisoes.juntar_coletas(
        [(primeira, siade_2026), (segunda, revisado)], chave
    )
    em_novembro = revisoes.como_era_em(junta, "2026-11-20", chave)
    em_dezembro = revisoes.como_era_em(junta, "2026-12-10", chave)
    primeira_linha = siade_2026.iloc[0]

    def da_linha(tabela: pd.DataFrame) -> pd.DataFrame:
        achadas = tabela
        for coluna in chave:
            achadas = achadas[achadas[coluna] == primeira_linha[coluna]]
        return achadas

    assert da_linha(em_novembro)["tku"].iloc[0] == 28774620.0
    assert da_linha(em_dezembro)["tku"].iloc[0] == 1.0


# --- Comex Stat: preço médio ------------------------------------------------------------------------
def _comex(nome: str) -> pd.DataFrame:
    return comex_preco_medio.ler(_ler("comex", f"{nome}.csv"), f"{COMEX}{nome}.csv")


@pytest.fixture(scope="module")
def exportacao() -> pd.DataFrame:
    return _comex("EXP_2026")


def test_preco_medio_e_valor_fob_sobre_quilo(exportacao):
    assert list(exportacao.columns) == list(comex_preco_medio.COLUNAS)
    assert set(exportacao["fluxo"]) == {"exportacao"}
    com_quilo = exportacao[exportacao["kg_liquido"] > 0]
    esperado = com_quilo["vl_fob_usd"] / com_quilo["kg_liquido"]
    assert (com_quilo["preco_usd_por_kg"] - esperado).abs().max() < 1e-9


def test_quilo_zero_deixa_o_preco_vazio_e_nao_zero(exportacao):
    sem_quilo = exportacao[exportacao["kg_liquido"] == 0]
    assert len(sem_quilo) > 0
    assert sem_quilo["preco_usd_por_kg"].isna().all()


def test_soma_das_linhas_da_fonte_por_mes_ncm_e_urf(exportacao):
    bruto = pd.read_csv(
        PASTA / "comex" / "EXP_2026.csv", sep=";", dtype=str, encoding="latin-1"
    )
    assert not exportacao.duplicated(list(comex_preco_medio.CHAVE)).any()
    assert exportacao["vl_fob_usd"].sum() == pytest.approx(
        bruto["VL_FOB"].astype(float).sum()
    )
    assert exportacao["kg_liquido"].sum() == pytest.approx(
        bruto["KG_LIQUIDO"].astype(float).sum()
    )
    assert exportacao["competencia"].dt.is_month_end.all()
    assert exportacao["ncm"].str.len().eq(8).all()


def test_importacao_e_outro_fluxo_e_ignora_frete_e_seguro():
    importacao = _comex("IMP_2026")
    assert set(importacao["fluxo"]) == {"importacao"}
    assert list(importacao.columns) == list(comex_preco_medio.COLUNAS)


def test_comex_so_vale_60_dias_depois_do_fim_do_mes(exportacao):
    atraso = exportacao["disponivel_em"] - exportacao["competencia"]
    assert (atraso == pd.Timedelta(days=prazos.DIAS_ATE_PUBLICAR_MENSAL)).all()


def test_comex_destino_so_dos_csv_de_ncm():
    assert comex_preco_medio.destino(f"{COMEX}EXP_2026.csv") == "exportacao_2026"
    assert comex_preco_medio.destino(f"{COMEX}IMP_1997.csv") == "importacao_1997"
    assert (
        comex_preco_medio.destino("https://x/comexstat-bd/mun/EXP_2026_MUN.csv") is None
    )
    assert comex_preco_medio.destino(f"{COMEX}EXP_2026_TOTAIS_CONFERENCIA.csv") is None
    assert comex_preco_medio.destino("https://x/comexstat-bd/tabelas/URF.csv") is None


def test_comex_recusa_endereco_que_nao_e_de_ncm():
    with pytest.raises(ValueError, match="Comex"):
        comex_preco_medio.ler(_ler("comex", "EXP_2026.csv"), "https://x/URF.csv")


def test_comex_revisao_do_mdic_vale_so_desde_a_coleta(exportacao):
    primeira, segunda = pd.Timestamp("2026-10-14"), pd.Timestamp("2026-12-01")
    revisado = exportacao.copy()
    revisado.loc[0, "vl_fob_usd"] += 1000.0
    chave = list(comex_preco_medio.CHAVE)
    junta = revisoes.juntar_coletas(
        [(primeira, exportacao), (segunda, revisado)], chave
    )
    assert len(junta) == len(exportacao) + 1
    antes = revisoes.como_era_em(junta, "2026-11-20", chave)
    depois = revisoes.como_era_em(junta, "2026-12-10", chave)
    publico_antes = exportacao[
        exportacao["disponivel_em"] <= pd.Timestamp("2026-11-20")
    ]
    assert antes["vl_fob_usd"].sum() == pytest.approx(publico_antes["vl_fob_usd"].sum())
    assert depois["vl_fob_usd"].sum() == pytest.approx(revisado["vl_fob_usd"].sum())


# --- Licença: o Comex é vendável com atribuição desde a resposta do MDIC (21/10/2026) ---------------
def test_preco_medio_e_vendavel_com_atribuicao_e_licenciado():
    """Até 29/10/2026 a tabela era de uso interno (marca "a confirmar"); o MDIC respondeu por
    LAI que os dados abertos da Secex têm uso livre, inclusive comercial, citando Secex/MDIC."""
    from base.dicionario import TABELAS

    tabela = TABELAS["comex_preco_medio"]
    assert tabela.familia_da_fonte == "comexstat"
    assert marca_da_fonte(tabela.familia_da_fonte) is Marca.VENDAVEL
    assert revenda_da_fonte(tabela.familia_da_fonte).startswith("vendável")
    licenca = licenca_da_fonte(tabela.familia_da_fonte)
    assert (
        situacao_da_licenca(licenca, revenda_da_fonte(tabela.familia_da_fonte))
        == LICENCIADA
    )
    assert "Secex/MDIC" in tabela.descricao
    assert "uso interno" not in tabela.descricao.lower()


def test_concessionarios_e_ferrovias_vem_de_fonte_com_licenca_escrita():
    from base.dicionario import TABELAS

    for nome in ("anp_concessionarios", "antt_siade"):
        familia = TABELAS[nome].familia_da_fonte
        assert marca_da_fonte(familia) is Marca.VENDAVEL, nome


# --- Sem olhar o futuro -----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def anos_do_siade() -> pd.DataFrame:
    return pd.concat(
        [
            antt_siade.ler(_ler("antt", "producao_2006.csv")),
            antt_siade.ler(_ler("antt", "producao_2026.csv")),
        ],
        ignore_index=True,
    )


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    dia=st.dates(
        min_value=pd.Timestamp("2006-01-01").date(),
        max_value=pd.Timestamp("2027-12-31").date(),
    )
)
def test_siade_cortar_o_futuro_nao_muda_o_passado(anos_do_siade, dia):
    chave = list(antt_siade.CHAVE)
    inteira = revisoes.como_era_em(
        revisoes.juntar_coletas([(pd.Timestamp("2026-10-14"), anos_do_siade)], chave),
        dia,
        chave,
    )
    cortada = anos_do_siade[anos_do_siade["disponivel_em"] <= pd.Timestamp(dia)]
    sobra = revisoes.como_era_em(
        revisoes.juntar_coletas([(pd.Timestamp("2026-10-14"), cortada)], chave)
        if len(cortada)
        else anos_do_siade.iloc[0:0].assign(visto_em=pd.NaT),
        dia,
        chave,
    )
    assert (inteira["disponivel_em"] <= pd.Timestamp(dia)).all()
    ordem = [*chave, "toneladas_uteis", "tku"]
    pd.testing.assert_frame_equal(
        inteira[ordem].sort_values(chave).reset_index(drop=True),
        sobra[ordem].sort_values(chave).reset_index(drop=True),
        check_dtype=False,
    )


def test_comex_nada_e_publico_antes_do_prazo(exportacao):
    """Num dia qualquer só entra o mês que já fechou há 60 dias: o último mês do arquivo ainda não."""
    ultimo = exportacao["competencia"].max()
    na_vespera = ultimo + pd.Timedelta(days=prazos.DIAS_ATE_PUBLICAR_MENSAL - 1)
    chave = list(comex_preco_medio.CHAVE)
    visto = revisoes.juntar_coletas([(pd.Timestamp("2026-10-14"), exportacao)], chave)
    publico = revisoes.como_era_em(visto, na_vespera, chave)
    assert ultimo not in set(publico["competencia"])
    assert (publico["disponivel_em"] <= na_vespera).all()
