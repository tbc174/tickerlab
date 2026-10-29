"""O motor dos cadastros em retrato (`base/retratos.py`), sem a regra de nenhum cadastro: as sanções
(`tests/test_base_sancoes.py`) e as licenças usam o mesmo."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import retratos

VALORES = ["situacao", "consta"]


def _retrato(dia: int) -> retratos.Retrato:
    return retratos.Retrato(
        url="https://exemplo.gov.br/cadastro.csv",
        sha256=f"{dia:064d}",
        caminho=Path("nao-lido.csv"),
        baixado_em=datetime(2026, 10, dia, 13, tzinfo=UTC),
    )


def _tabela(**situacoes: str) -> pd.DataFrame:
    return pd.DataFrame(
        {"id_na_fonte": list(situacoes), "situacao": list(situacoes.values())}
    )


def _no_dia(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    return pd.Series(dia, index=novos.index)


def test_mudanca_e_saida_viram_linhas_novas_so_do_dia_em_que_foram_vistas():
    lidos = [
        (_retrato(14), _tabela(a="Ativo", b="Ativo")),
        (_retrato(15), _tabela(a="Ativo", b="Ativo")),  # nada mudou: nenhuma linha
        (_retrato(16), _tabela(a="Cancelado")),  # a mudou, b saiu
    ]
    tabela, pulados = retratos.juntar(lidos, VALORES, _no_dia)

    assert pulados == 0
    linhas = tabela[["id_na_fonte", "situacao", "consta", "visto_em"]].to_dict(
        "records"
    )
    dia = pd.Timestamp
    assert linhas == [
        {"id_na_fonte": "a", "situacao": "Ativo", "consta": True, "visto_em": dia("2026-10-14")},
        {"id_na_fonte": "b", "situacao": "Ativo", "consta": True, "visto_em": dia("2026-10-14")},
        {"id_na_fonte": "a", "situacao": "Cancelado", "consta": True, "visto_em": dia("2026-10-16")},
        {"id_na_fonte": "b", "situacao": "Ativo", "consta": False, "visto_em": dia("2026-10-16")},
    ]  # fmt: skip
    assert (tabela["disponivel_em"] == tabela["visto_em"]).all()


def test_primeiro_retrato_usa_a_regra_do_cadastro():
    def publicado(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
        return pd.Series(pd.Timestamp("2020-01-02"), index=novos.index)

    tabela, _ = retratos.juntar(
        [(_retrato(14), _tabela(a="Ativo"))], VALORES, publicado
    )

    assert tabela["disponivel_em"].tolist() == [pd.Timestamp("2020-01-02")]


def test_retrato_cortado_e_pulado_e_o_que_sumiu_nele_continua_constando():
    lidos = [
        (_retrato(14), _tabela(a="Ativo", b="Ativo", c="Ativo")),
        (_retrato(15), _tabela(a="Ativo")),  # menos da metade: arquivo cortado
    ]
    tabela, pulados = retratos.juntar(lidos, VALORES, _no_dia)

    assert pulados == 1
    assert tabela["consta"].all() and len(tabela) == 3


def test_sem_retrato_falha():
    with pytest.raises(ValueError, match="nenhum retrato"):
        retratos.juntar([], VALORES, _no_dia)


def test_chave_junta_as_colunas_e_nome_da_coluna_tira_acento():
    tabela = pd.DataFrame({"cnpj": ["1"], "processo": ["2"]})

    assert retratos.chave(tabela, ["cnpj", "processo"]).tolist() == ["1|2"]
    assert retratos.nome_da_coluna("Código – da Sanção") == "CODIGODASANCAO"
