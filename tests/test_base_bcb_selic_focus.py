"""Meta da Selic (SGS 432) e Focus Selic anual na base, com a safra (ADR 0093, plano das notícias de dado)."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from base import bcb_selic_focus
from base.parquet import conferir_tabela, ler_tabela

AGORA = datetime(2026, 10, 17, 9, tzinfo=UTC)


def _exportacao(*linhas: tuple[str, str, float, str]) -> pd.DataFrame:
    """Como sai de `src.exportacao_do_acervo.ler_base(conexao, "series")`: uma linha por safra."""
    return pd.DataFrame(
        [
            {
                "serie": serie,
                "nome": serie,
                "unidade": "x",
                "referencia": pd.Timestamp(referencia),
                "valor": valor,
                "divulgado_em": pd.Timestamp(divulgado),
                "registrado_em": pd.Timestamp(divulgado, tz="UTC"),
                "fonte": "bcb",
            }
            for serie, referencia, valor, divulgado in linhas
        ]
    )


def test_safra_vira_publico_em():
    """Uma revisão gera linha nova com o `divulgado_em` dela; a antiga fica."""
    saida = bcb_selic_focus.montar(
        _exportacao(
            ("bcb-focus-selic", "2026-12-31", 14.50, "2026-09-14"),
            ("bcb-focus-selic", "2026-12-31", 14.25, "2026-09-21"),
        )
    )
    assert saida["valor"].tolist() == [14.50, 14.25]
    assert (saida["publico_em"] == saida["divulgado_em"]).all()
    assert saida["divulgado_em"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-09-14",
        "2026-09-21",
    ]


def test_focus_so_selic_anual():
    """Só a meta (432) e o Focus da Selic entram; IPCA, câmbio e o resto ficam de fora."""
    saida = bcb_selic_focus.montar(
        _exportacao(
            ("bcb-sgs-432", "2026-09-17", 15.0, "2026-09-18"),
            ("bcb-sgs-433", "2026-09-01", 0.5, "2026-10-01"),
            ("bcb-focus-selic", "2026-12-31", 14.5, "2026-09-14"),
            ("bcb-focus-ipca", "2026-12-31", 4.5, "2026-09-14"),
            ("bcb-ptax-venda", "2026-09-14", 5.4, "2026-09-14"),
        )
    )
    assert sorted(saida["serie"].unique()) == ["bcb-sgs-432", "focus-selic-anual"]
    assert len(saida) == 2


def test_colunas_do_contrato_e_ordem_estavel():
    entrada = _exportacao(
        ("bcb-focus-selic", "2027-12-31", 12.0, "2026-09-14"),
        ("bcb-sgs-432", "2026-09-17", 15.0, "2026-09-18"),
        ("bcb-focus-selic", "2026-12-31", 14.5, "2026-09-14"),
    )
    saida = bcb_selic_focus.montar(entrada)
    assert list(saida.columns) == bcb_selic_focus.COLUNAS
    # ordenada por série, referência e safra: montar de novo (ou com linhas embaralhadas) dá o mesmo
    assert saida.equals(bcb_selic_focus.montar(entrada.iloc[::-1]))
    assert saida["serie"].tolist() == [
        "bcb-sgs-432",
        "focus-selic-anual",
        "focus-selic-anual",
    ]


def test_exportacao_vazia_nao_quebra():
    assert bcb_selic_focus.montar(pd.DataFrame()).empty


def test_gravar_cria_parquet_com_manifesto_e_linhagem(tmp_path):
    entrada = _exportacao(("bcb-sgs-432", "2026-09-17", 15.0, "2026-09-18"))
    assert bcb_selic_focus.gravar(entrada, tmp_path, AGORA) == 1
    arquivo = tmp_path / "bcb_selic_focus" / "bcb_selic_focus.parquet"
    assert conferir_tabela(arquivo)
    tabela = ler_tabela(arquivo)
    linha = tabela.iloc[0]
    assert len(linha["origem_sha256"]) == 64
    assert linha["versao_do_codigo"]
    assert pd.Timestamp(linha["montado_em"]) == pd.Timestamp(AGORA)


def test_remontar_com_linha_nova_acrescenta_sem_perder_a_antiga(tmp_path):
    antes = _exportacao(("bcb-focus-selic", "2026-12-31", 14.5, "2026-09-14"))
    depois = pd.concat(
        [
            antes,
            _exportacao(("bcb-focus-selic", "2026-12-31", 14.25, "2026-09-21")),
        ],
        ignore_index=True,
    )
    bcb_selic_focus.gravar(antes, tmp_path, AGORA)
    assert bcb_selic_focus.gravar(depois, tmp_path, AGORA) == 2
    tabela = ler_tabela(tmp_path / "bcb_selic_focus" / "bcb_selic_focus.parquet")
    assert tabela["valor"].tolist() == [14.5, 14.25]


@pytest.mark.parametrize("serie", ["bcb-sgs-432", "bcb-focus-selic"])
def test_valor_vem_como_na_origem(serie):
    saida = bcb_selic_focus.montar(
        _exportacao((serie, "2026-12-31", 14.75, "2026-09-14"))
    )
    assert saida["valor"].iloc[0] == 14.75
