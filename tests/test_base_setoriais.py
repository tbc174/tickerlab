"""Números da operação por setor, 1ª leva: ANAC, ANP e ONS (série 4 da base de ML, PR 4; ADR 0074).

Amostras reais recortadas do acervo (`tests/arquivos/setoriais/`): o estatístico da ANAC (GOL, Azul e
LATAM em 01/2019 e 08/2026, com a linha "Atualizado em: 2026-10-14"), as vendas de líquidos da ANP
(Raízen e Vibra em 01/2010 pelo histórico, que vem sem cabeçalho e sem a descrição do produto, e em
01/2019 e 08/2026 pelo atual) e a geração do ONS (Itaipu 50 e 60 Hz em dois dias de 2010 e de 2026;
em 2010 a geração vem como texto). Prazos medidos em 14/10/2026: ANAC e ANP com agosto publicado
(44 dias depois do fim do mês), ONS com o dia anterior inteiro.
"""

from pathlib import Path

import pandas as pd
import pytest

from base.setoriais import anac, anp, ligacao, ons, prazos

PASTA = Path(__file__).parent / "arquivos" / "setoriais"


@pytest.fixture(scope="module")
def voos() -> pd.DataFrame:
    return anac.ler((PASTA / "anac" / "Dados_Estatisticos.csv").read_bytes())


@pytest.fixture(scope="module")
def vendas() -> pd.DataFrame:
    return anp.ler((PASTA / "anp" / "liquidos.zip").read_bytes(), "liquidos")


@pytest.fixture(scope="module")
def geracao() -> pd.DataFrame:
    return pd.concat(
        [ons.ler(p.read_bytes()) for p in sorted((PASTA / "ons").glob("*.parquet"))],
        ignore_index=True,
    )


# --- cada fonte no formato da fonte ---------------------------------------------------------------
def test_le_a_anac_no_formato_da_fonte(voos):
    assert list(voos.columns) == list(anac.COLUNAS)
    assert set(voos["empresa_sigla"]) <= {"GLO", "AZU", "TAM"}
    assert set(voos["competencia"]) == {
        pd.Timestamp("2019-01-31"),
        pd.Timestamp("2026-08-31"),
    }
    assert (
        voos["passageiros_pagos"].dtype.kind == "f"
        and voos["passageiros_pagos"].sum() > 0
    )
    assert set(voos["atualizado_em"]) == {pd.Timestamp("2026-10-14")}


def test_le_a_anp_no_formato_da_fonte(vendas):
    assert list(vendas.columns) == list(anp.COLUNAS)
    assert set(vendas["agente"]) == {"RAIZEN S.A.", "VIBRA ENERGIA S.A"}
    assert {2010, 2019, 2026} == set(vendas["competencia"].dt.year)
    historico = vendas[vendas["competencia"].dt.year == 2010]
    assert (
        historico["descricao_do_produto"].isna().all()
    )  # o histórico não tem a coluna
    assert historico["quantidade"].sum() > 0  # "1,415000" vira 1.415
    assert set(vendas["unidade"]) == {"mil m³"}


def test_meses_do_historico_e_do_atual_nao_se_repetem():
    """O histórico dos líquidos vai até 2017 e o atual começa em 2017: os meses que o atual tem ficam
    só com ele."""
    linhas = [
        "2017;1;RAIZEN S.A.;320102001;Gasolina C;CO;DF;CO;DF;CONSUMIDOR FINAL;9,000000",
        "2016;12;RAIZEN S.A.;320102001;Gasolina C;CO;DF;CO;DF;CONSUMIDOR FINAL;1,000000",
    ]
    atual = [
        '"Ano";"Mês";"Agente Regulado";"Código do Produto";"Nome do Produto";"Descrição do Produto";'
        '"Região Origem";"UF Origem";"Região Destinatário";"UF Destino";"Mercado Destinatário";'
        '"Quantidade de Produto (mil m³)"',
        "2017;1;RAIZEN S.A.;320102001;Gasolina C;GASOLINA C COMUM;CO;DF;CO;DF;CONSUMIDOR FINAL;2,000000",
    ]
    import io
    import zipfile

    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as z:
        z.writestr(
            "Liquidos_Vendas_Historico_2007_a_2017.csv",
            "\r\n".join(linhas).encode("latin-1"),
        )
        z.writestr("Liquidos_Vendas_Atual.csv", "\r\n".join(atual).encode("latin-1"))
    tabela = anp.ler(conteudo.getvalue(), "liquidos").set_index("competencia")
    assert tabela.loc[pd.Timestamp("2017-01-31"), "quantidade"] == 2.0  # do atual
    assert tabela.loc[pd.Timestamp("2016-12-31"), "quantidade"] == 1.0  # do histórico


def test_le_o_ons_nos_dois_formatos(geracao):
    assert list(geracao.columns) == list(ons.COLUNAS)
    assert set(geracao["id_ons"]) == {"PYIT50", "PRIT60"}
    assert (
        geracao["geracao_mwmed"].dtype.kind == "f"
    )  # em 2010 vinha como texto ("0E-8")
    assert geracao.loc[geracao["instante"].dt.year == 2010, "geracao_mwmed"].sum() > 0
    # o mesmo CEG para as duas (Itaipu 50 e 60 Hz): a chave da usina é o id_ons, não o CEG
    assert geracao["ceg"].nunique() == 1


def test_ceg_vazio_do_ons_vira_vazio():
    tabela = pd.read_parquet(PASTA / "ons" / "GERACAO_USINA-2_2026_09.parquet").head(2)
    tabela["ceg"] = "-"
    import io

    saida = io.BytesIO()
    tabela.to_parquet(saida, index=False)
    assert ons.ler(saida.getvalue())["ceg"].isna().all()


# --- prazos ("como era na data") ------------------------------------------------------------------
def test_disponivel_em_respeita_o_prazo_da_fonte(voos, vendas, geracao):
    """Nunca antes do que a fonte publicou: agosto/2026 estava publicado em 14/10/2026 na ANAC e na
    ANP (o prazo de 60 dias dá 30/10, depois) e o ONS tinha o dia anterior inteiro (2 dias de prazo)."""
    for tabela in (voos, vendas):
        assert (
            tabela["disponivel_em"] - tabela["competencia"] == pd.Timedelta(days=60)
        ).all()
    agosto = voos[voos["competencia"] == pd.Timestamp("2026-08-31")]
    assert (agosto["disponivel_em"] >= pd.Timestamp("2026-10-14")).all()
    assert (
        geracao["disponivel_em"] - geracao["instante"] == pd.Timedelta(days=2)
    ).all()
    assert prazos.DIAS_ATE_PUBLICAR_MENSAL > prazos.ATRASO_MEDIDO_MENSAL


# --- ligação só pela B13 --------------------------------------------------------------------------
def _empresa_serie() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fonte": [
                "anp-vendas-distribuidora",
                "anp-vendas-distribuidora",
                "anac-estatistico",
            ],
            "chave": ["RAIZEN S.A.", "RAIZEN SA", "GLO"],
            "cnpj_companhia": ["33.453.598/0001-23", None, "06.164.253/0001-87"],
            "principal": [True, True, True],
        }
    )


def test_codigo_sem_ligacao_vai_para_os_buracos(vendas, voos):
    """A ligação vem só da B13 (conferida) pela chave exata da fonte: nada é casado por nome
    aproximado ("RAIZEN SA" sem CNPJ na B13 não liga, e a Vibra, que não está nela, vai para os
    buracos com o volume)."""
    ligadas = ligacao.ligar(vendas, "agente", anp.FONTE, _empresa_serie())
    assert set(ligadas.loc[ligadas["cnpj_companhia"].notna(), "agente"]) == {
        "RAIZEN S.A."
    }
    buracos = ligacao.buracos(
        vendas, "agente", "quantidade", anp.FONTE, _empresa_serie()
    )
    assert buracos["chave"].tolist() == ["VIBRA ENERGIA S.A"]
    assert buracos["valor"].iloc[0] > 0
    sem_aviao = ligacao.buracos(
        voos, "empresa_sigla", "passageiros_pagos", anac.FONTE, _empresa_serie()
    )
    assert set(sem_aviao["chave"]) == {"AZU", "TAM"}
