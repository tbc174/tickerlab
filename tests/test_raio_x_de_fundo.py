"""`base.raio_x_de_fundo`: taxas, carteira "como era em D" e custo da taxa por CNPJ de fundo (API A3b).
Base de mentira, sem internet; os CNPJs são de ninguém."""

import pandas as pd
import pytest

from base.porta import Porta
from base.raio_x_de_fundo import (
    CAPITAL_DO_EXEMPLO,
    RETORNO_DO_EXEMPLO,
    raio_x_de_fundo,
)
from src.ferramentas.custos import custo_da_taxa

FUNDO = "11.111.111/0001-91"
OUTRO = "22.222.222/0001-91"


def _gravar(pasta, caminho: str, tabela: pd.DataFrame) -> None:
    arquivo = pasta / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


def _cadastro(taxa_adm: float | None = 2.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "TP_FUNDO": ["FI", "FI"],
            "CNPJ_FUNDO": [FUNDO, OUTRO],
            "DENOM_SOCIAL": ["FUNDO UM", "FUNDO DOIS"],
            "DT_REG": pd.to_datetime(["2015-01-01", "2015-01-01"]),
            "CLASSE": ["Ações", "Renda Fixa"],
            "SIT": ["EM FUNCIONAMENTO NORMAL"] * 2,
            "TAXA_ADM": [taxa_adm, 0.5],
            "TAXA_PERFM": [20.0, None],
            "INF_TAXA_ADM": ["2% ao ano", None],
            "INF_TAXA_PERFM": ["20% sobre o que passar do Ibovespa", None],
            "VL_PATRIM_LIQ": [1_000_000.0, 5.0],
            "DT_PATRIM_LIQ": pd.to_datetime(["2026-09-30", "2026-09-30"]),
        }
    )


def _carteira() -> pd.DataFrame:
    """Três competências do FUNDO (a última só ficou pública em 2026) e uma posição de OUTRO."""
    linhas = [
        (FUNDO, "2024-01-31", "PETR4", 100.0, "2024-05-01"),
        (FUNDO, "2024-01-31", "VALE3", 50.0, "2024-05-01"),
        (FUNDO, "2024-02-29", "PETR4", 80.0, "2024-05-30"),
        (FUNDO, "2026-02-28", "ITUB4", 999.0, "2026-05-29"),
        (OUTRO, "2024-02-29", "WEGE3", 7.0, "2024-05-30"),
    ]
    return pd.DataFrame(
        {
            "competencia": pd.to_datetime([x[1] for x in linhas]),
            "cnpj_fundo": [x[0] for x in linhas],
            "tipo_do_fundo": "FI",
            "fundo": "NOME",
            "tipo": "comprado",
            "codigo": [x[2] for x in linhas],
            "isin": "BRXXXXACNOR0",
            "emissor": "XXXX",
            "descricao": "ACAO ON",
            "quantidade": 1.0,
            "valor": [x[3] for x in linhas],
            "compras": 0.0,
            "vendas": 0.0,
            "confidencial_ate": pd.NaT,
            "disponivel_em": pd.to_datetime([x[4] for x in linhas]),
        }
    )


@pytest.fixture
def porta(tmp_path):
    _gravar(tmp_path, "fidc/cadastro/cad_fi.parquet", _cadastro())
    _gravar(
        tmp_path,
        "cda/2024.parquet",
        _carteira()[lambda d: d.competencia.dt.year == 2024],
    )
    _gravar(
        tmp_path,
        "cda/2026.parquet",
        _carteira()[lambda d: d.competencia.dt.year == 2026],
    )
    with Porta(tmp_path) as p:
        yield p


def test_taxas_do_cadastro(porta):
    raio = raio_x_de_fundo(porta, "11111111000191")
    assert raio.cnpj == FUNDO
    assert raio.cadastro["taxa_administracao_pct_ao_ano"] == 2.0
    assert raio.cadastro["taxa_performance_pct"] == 20.0
    assert raio.cadastro["classe"] == "Ações"
    assert raio.cadastro["patrimonio_liquido"] == 1_000_000.0


def test_carteira_e_a_competencia_mais_nova_do_fundo(porta):
    raio = raio_x_de_fundo(porta, FUNDO)
    assert raio.competencia_da_carteira == "2026-02-28"
    assert [p["codigo"] for p in raio.carteira] == ["ITUB4"]


def test_sem_olhar_o_futuro_a_carteira_em_d_so_tem_o_que_ja_era_publico(porta):
    # 2026-02-28 só ficou pública em 2026-05-29; em 2025-01-01 vale a de fev/2024
    raio = raio_x_de_fundo(porta, FUNDO, como_era_em="2025-01-01")
    assert raio.competencia_da_carteira == "2024-02-29"
    assert [p["codigo"] for p in raio.carteira] == ["PETR4"]
    # cortar o futuro não muda o passado: a mesma foto vista de outra data posterior ao corte
    de_novo = raio_x_de_fundo(porta, FUNDO, como_era_em="2026-05-28")
    assert de_novo.carteira == raio.carteira


def test_carteira_nunca_traz_posicao_de_outro_fundo(porta):
    raio = raio_x_de_fundo(porta, FUNDO, como_era_em="2025-01-01")
    assert "WEGE3" not in [p["codigo"] for p in raio.carteira]


def test_em_d_as_taxas_ficam_de_fora_e_a_lacuna_diz_por_que(porta):
    raio = raio_x_de_fundo(porta, FUNDO, como_era_em="2025-01-01")
    assert raio.cadastro is None
    assert raio.custo_da_taxa == {}
    assert any("taxa" in lacuna and "2025-01-01" in lacuna for lacuna in raio.lacunas)


def test_fundo_registrado_depois_de_d_nao_existia(porta):
    raio = raio_x_de_fundo(porta, FUNDO, como_era_em="2014-12-31")
    assert raio.carteira == []
    assert any("ainda não existia" in lacuna for lacuna in raio.lacunas)


def test_custo_da_taxa_em_5_e_20_anos_e_a_conta_de_custos(porta):
    raio = raio_x_de_fundo(porta, FUNDO)
    for anos in (5, 20):
        esperado = custo_da_taxa(CAPITAL_DO_EXEMPLO, RETORNO_DO_EXEMPLO, 0.02, anos)
        linha = raio.custo_da_taxa[anos]
        assert linha["com_taxa"] == pytest.approx(esperado.com_taxa)
        assert linha["sem_taxa"] == pytest.approx(esperado.sem_taxa)
        assert linha["ficou_com_a_taxa"] == pytest.approx(esperado.ficou_com_a_taxa)
    assert raio.hipotese_do_custo["retorno_ao_ano"] == RETORNO_DO_EXEMPLO


def test_taxa_ausente_nao_vira_zero(tmp_path):
    _gravar(tmp_path, "fidc/cadastro/cad_fi.parquet", _cadastro(taxa_adm=None))
    with Porta(tmp_path) as p:
        raio = raio_x_de_fundo(p, FUNDO)
    assert raio.cadastro["taxa_administracao_pct_ao_ano"] is None
    assert raio.custo_da_taxa == {}
    assert any("taxa de administração" in lacuna for lacuna in raio.lacunas)


def test_cnpj_invalido_e_erro(porta):
    with pytest.raises(ValueError):
        raio_x_de_fundo(porta, "123")


def test_fundo_que_nao_esta_no_cadastro(porta):
    raio = raio_x_de_fundo(porta, "33.333.333/0001-91")
    assert raio.cadastro is None
    assert raio.carteira == []
    assert any("não está no cadastro" in lacuna for lacuna in raio.lacunas)


def test_sem_pessoa_natural_no_resultado(porta):
    raio = raio_x_de_fundo(porta, FUNDO)
    proibidas = {"gestor", "cpf_cnpj_gestor", "pf_pj_gestor", "administrador"}
    assert not proibidas & set(raio.cadastro)


@pytest.mark.parametrize("dt_reg", ["2015-01-01", "01/01/2015", "lixo", "", None])
def test_dt_reg_como_texto_nao_derruba_o_raio_x(tmp_path, dt_reg):
    """Regressão da linha 792: `DT_REG` chegou como texto no VPS e `'>'` entre str e Timestamp dava 500."""
    cadastro = _cadastro().astype({"DT_REG": "object"})
    cadastro["DT_REG"] = dt_reg
    _gravar(tmp_path, "fidc/cadastro/cad_fi.parquet", cadastro)
    with Porta(tmp_path) as p:
        raio = raio_x_de_fundo(p, FUNDO, como_era_em="2025-01-01")
    assert raio.cnpj == FUNDO


def test_dt_reg_texto_posterior_a_d_ainda_vale_como_nao_existia(tmp_path):
    cadastro = _cadastro().astype({"DT_REG": "object"})
    cadastro["DT_REG"] = "2015-01-01"
    _gravar(tmp_path, "fidc/cadastro/cad_fi.parquet", cadastro)
    with Porta(tmp_path) as p:
        raio = raio_x_de_fundo(p, FUNDO, como_era_em="2014-12-31")
    assert any("ainda não existia" in lacuna for lacuna in raio.lacunas)
