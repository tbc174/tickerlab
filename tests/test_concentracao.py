"""CR4 e HHI com a régua do CADE (molde D, plano de 19/10/2026, PR 1, tarefa 1.1)."""

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import concentracao

D = pd.Timestamp


def test_hhi_de_monopolio_e_10000() -> None:
    assert concentracao.hhi(pd.Series([42.0])) == pytest.approx(10_000)


def test_hhi_de_n_iguais() -> None:
    assert concentracao.hhi(pd.Series([5.0] * 4)) == pytest.approx(2_500)
    assert concentracao.hhi(pd.Series([1.0] * 10)) == pytest.approx(1_000)


def test_hhi_e_cr4_ignoram_zero_e_vazio() -> None:
    valores = pd.Series([3.0, 1.0, 0.0, None])
    assert concentracao.hhi(valores) == pytest.approx(75**2 + 25**2)
    assert concentracao.cr4(valores) == pytest.approx(1.0)


def test_cr4_soma_as_4_maiores() -> None:
    valores = pd.Series([40.0, 30.0, 10.0, 10.0, 5.0, 5.0])
    assert concentracao.cr4(valores) == pytest.approx(0.9)


def test_cr4_com_menos_de_4() -> None:
    assert concentracao.cr4(pd.Series([2.0, 1.0])) == pytest.approx(1.0)


def test_mercado_vazio_nao_tem_hhi() -> None:
    assert concentracao.hhi(pd.Series([], dtype=float)) is None
    assert concentracao.cr4(pd.Series([0.0])) is None


@pytest.mark.parametrize(
    ("hhi", "faixa"),
    [
        (1_499.9, concentracao.NAO_CONCENTRADO),
        (1_500, concentracao.MODERADO),
        (2_500, concentracao.MODERADO),
        (2_500.1, concentracao.ALTO),
    ],
)
def test_faixa_do_cade_nas_bordas(hhi: float, faixa: str) -> None:
    assert concentracao.faixa_do_cade(hhi) == faixa


def _mercado() -> pd.DataFrame:
    """3 participantes em 2024 e 2025 (anos completos) e 2026 pela metade."""
    return pd.DataFrame(
        {
            "ano": [2024] * 3 + [2025] * 3 + [2026] * 3,
            "participante": ["a", "b", "c"] * 3,
            "valor": [50.0, 30.0, 20.0, 60.0, 30.0, 10.0, 70.0, 20.0, 10.0],
            "meses": [12] * 6 + [6] * 3,
            "ultimo_mes": [D("2024-12-31")] * 3
            + [D("2025-12-31")] * 3
            + [D("2026-06-30")] * 3,
        }
    )


def test_concentracao_por_ano_com_delta() -> None:
    tabela = concentracao.concentracao_por_ano(_mercado()).set_index("ano")
    assert list(tabela.index) == [2026, 2025, 2024]  # o mais novo primeiro
    assert tabela.loc[2024, "hhi"] == pytest.approx(50**2 + 30**2 + 20**2)
    assert tabela.loc[2025, "hhi"] == pytest.approx(60**2 + 30**2 + 10**2)
    assert tabela.loc[2025, "delta_hhi"] == pytest.approx(4_600 - 3_800)
    assert tabela.loc[2025, "faixa"] == concentracao.ALTO
    assert tabela.loc[2025, "participantes"] == 3
    assert tabela.loc[2025, "total"] == pytest.approx(100.0)
    # o 1º ano não tem com o que comparar; o ano pela metade não compara com um completo
    assert pd.isna(tabela.loc[2024, "delta_hhi"])
    assert pd.isna(tabela.loc[2026, "delta_hhi"])
    assert tabela.loc[2026, "meses"] == 6


def test_delta_so_entre_anos_seguidos() -> None:
    sem_2025 = _mercado().query("ano != 2025")
    tabela = concentracao.concentracao_por_ano(sem_2025).set_index("ano")
    assert pd.isna(tabela.loc[2026, "delta_hhi"])


def test_mercado_sem_linhas_da_tabela_vazia() -> None:
    assert concentracao.concentracao_por_ano(_mercado().head(0)).empty


@settings(max_examples=50, deadline=None)
@given(st.lists(st.floats(min_value=0.01, max_value=1e9), min_size=1, max_size=30))
def test_hhi_fica_entre_o_de_iguais_e_o_monopolio(valores: list[float]) -> None:
    hhi = concentracao.hhi(pd.Series(valores))
    assert hhi is not None
    assert 10_000 / len(valores) - 1e-6 <= hhi <= 10_000 + 1e-6


def test_cortar_o_futuro_nao_muda_o_passado() -> None:
    inteira = concentracao.concentracao_por_ano(_mercado())
    cortada = concentracao.concentracao_por_ano(_mercado().query("ano <= 2025"))
    pd.testing.assert_frame_equal(
        inteira[inteira["ano"] <= 2025].reset_index(drop=True),
        cortada.reset_index(drop=True),
    )
