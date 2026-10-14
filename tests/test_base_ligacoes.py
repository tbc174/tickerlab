"""Ligação fundo → ação → empresa (série 3 da base de ML, PR 5; decisão do Tiago em 14/10/2026:
painel por emissor desde 2005 e tabela conferida de emissores antigos até 95% do valor de cada ano)."""

import re
from pathlib import Path

import pandas as pd
import pytest

from base import fca, fidc, ligacoes

PASTA_FCA = Path(__file__).parent / "arquivos" / "cvm" / "fca"
ITAU, PETROBRAS = "60.872.504/0001-23", "33.000.167/0001-01"


@pytest.fixture(scope="module")
def emissores_do_fca():
    valores = pd.concat(
        [
            fca.ler_valores_mobiliarios(p.read_bytes())
            for p in sorted(PASTA_FCA.glob("*.zip"))
        ],
        ignore_index=True,
    )
    return fca.emissores(valores)


def test_tabela_conferida_e_valida():
    tabela = ligacoes.tabela_conferida()
    assert tabela["emissor"].is_unique
    assert tabela["emissor"].str.fullmatch(fca.EMISSOR).all()
    assert (tabela["cnpj"].map(fidc.documento_de_empresa) == tabela["cnpj"]).all()
    for coluna in (
        "empresa_no_cadastro",
        "cd_cvm",
        "registro",
        "observacao",
        "fonte",
        "conferido_em",
    ):
        assert tabela[coluna].str.len().gt(0).all(), coluna
    assert tabela["no_cda"].str.fullmatch(r"\d{4}-\d{2}–\d{4}-\d{2}").all()


def test_fca_vem_primeiro_e_a_tabela_completa(emissores_do_fca):
    ligacao = ligacoes.ligacao_dos_emissores(
        emissores_do_fca, ligacoes.tabela_conferida()
    )
    por_emissor = ligacao.set_index("emissor")
    assert por_emissor.loc["ITUB", ["cnpj", "origem"]].tolist() == [
        ITAU,
        ligacoes.PELO_FCA,
    ]
    assert por_emissor.loc["ITAU", ["cnpj", "origem"]].tolist() == [
        ITAU,
        ligacoes.PELA_TABELA,
    ]
    assert not ligacao["conflito"].any()


def test_emissor_dos_codigos_conferidos_diz_a_origem(emissores_do_fca):
    """Série 3, PR 8: o BTG entra pela tabela de códigos conferidos da `carga_fca`, e a ligação diz isso."""
    tickers = pd.DataFrame(columns=["codigo", "cnpj"])
    _, emissores = fca.com_codigos_conferidos(
        tickers, emissores_do_fca, fca.codigos_conferidos()
    )
    ligacao = ligacoes.ligacao_dos_emissores(emissores, ligacoes.tabela_conferida())
    por_emissor = ligacao.set_index("emissor")
    assert por_emissor.loc["BPAC", ["cnpj", "origem"]].tolist() == [
        "30.306.294/0001-45",
        fca.PELOS_CODIGOS_CONFERIDOS,
    ]
    assert por_emissor.loc["ITUB", "origem"] == ligacoes.PELO_FCA


def test_emissor_com_cnpj_diferente_no_fca_e_na_tabela_e_conflito(emissores_do_fca):
    """Nada é casado no escuro: se as duas fontes discordam, o emissor fica sem CNPJ e é listado."""
    errada = pd.DataFrame({"emissor": ["PETR"], "cnpj": ["11.111.111/0001-11"]})
    ligacao = ligacoes.ligacao_dos_emissores(emissores_do_fca, errada)
    petr = ligacao[ligacao["emissor"] == "PETR"]
    assert petr["conflito"].all()
    assert ligacoes.resolver(ligacao, "PETR") is None
    assert ligacoes.resolver(ligacao, "ITUB") == ITAU


def _posicoes() -> pd.DataFrame:
    linhas = [
        # competência, fundo, tipo, emissor, valor, quantidade, compras, vendas, disponível em
        ("2008-12-31", "F1", "comprado", "ITAU", 100.0, 10, 5.0, 0.0, "2009-03-31"),
        ("2008-12-31", "F1", "comprado", "ITUB", 50.0, 5, 0.0, 1.0, "2009-03-31"),
        ("2008-12-31", "F2", "comprado", "ITUB", 30.0, 3, 0.0, 0.0, "2009-04-15"),
        ("2008-12-31", "F2", "vendido", "PETR", 20.0, 2, 0.0, 0.0, "2009-03-31"),
        ("2008-12-31", "F3", "comprado", "XXXX", 25.0, 1, 0.0, 0.0, "2009-03-31"),
    ]
    colunas = ["competencia", "cnpj_fundo", "tipo", "emissor", "valor", "quantidade", "compras",
               "vendas", "disponivel_em"]  # fmt: skip
    tabela = pd.DataFrame(linhas, columns=colunas)
    tabela["descricao"] = tabela["emissor"] + " ON"
    for coluna in ("competencia", "disponivel_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    return tabela


def _ligacao() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "emissor": ["ITAU", "ITUB", "PETR"],
            "cnpj": [ITAU, ITAU, PETROBRAS],
            "origem": [ligacoes.PELA_TABELA, ligacoes.PELO_FCA, ligacoes.PELO_FCA],
            "conflito": [False, False, False],
        }
    )


def test_painel_por_emissor_soma_valor_e_conta_fundos():
    painel = ligacoes.painel_por_emissor(_posicoes()).set_index(["emissor", "tipo"])
    assert painel.loc[
        ("ITUB", "comprado"), ["fundos", "valor", "quantidade"]
    ].tolist() == [2, 80.0, 8]
    assert painel.loc[("PETR", "vendido"), "fundos"] == 1
    # público só quando a última posição somada ficou pública
    assert painel.loc[("ITUB", "comprado"), "disponivel_em"] == pd.Timestamp(
        "2009-04-15"
    )


def test_painel_por_empresa_junta_emissores_e_conta_cada_fundo_uma_vez():
    """O Itaú aparece como ITAU (tabela conferida) e ITUB (FCA): é uma empresa só, e o fundo F1, que
    tinha os dois, conta uma vez."""
    painel = ligacoes.painel_por_empresa(_posicoes(), _ligacao()).set_index(
        ["cnpj", "tipo"]
    )
    assert painel.loc[(ITAU, "comprado"), ["fundos", "valor"]].tolist() == [2, 180.0]
    assert "XXXX" not in " ".join(painel.index.get_level_values("cnpj"))


def test_cobertura_e_buracos():
    cobertura = ligacoes.cobertura(_posicoes(), _ligacao())
    linha = cobertura.iloc[0]
    assert linha["valor_comprado"] == 205.0 and linha["valor_com_cnpj"] == 180.0
    assert linha["fracao_com_cnpj"] == pytest.approx(180 / 205)
    buracos = ligacoes.buracos(_posicoes(), _ligacao())
    assert buracos["emissor"].tolist() == ["XXXX"]
    assert re.fullmatch(r"XXXX ON", buracos["descricao"].iloc[0])
