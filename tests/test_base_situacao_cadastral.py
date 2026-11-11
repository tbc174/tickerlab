"""B-30c: situação cadastral do CNPJ por versão, só PJ e sem olhar o futuro (linha 841)."""

from datetime import date

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import cnpj_historico as historico
from base import situacao_cadastral as sc
from base.receita_diff import diff, disponivel_em

MESES = ("2023-05", "2023-06", "2023-07", "2023-08")
EMPRESA, FILIAL, OUTRA, MEI = (
    "11111111000111",
    "11111111000292",
    "22222222000122",
    "33333333000133",
)
RAIZES_PJ = {EMPRESA[:8], OUTRA[:8]}  # a raiz do MEI não está na lista sem pessoa


def _estabelecimento(
    cnpj: str, situacao: str, data: str, motivo="00", fone="1"
) -> dict:
    return {
        "cnpj": cnpj,
        "cnpj_basico": cnpj[:8],
        "matriz": cnpj[8:12] == "0001",
        "situacao_cadastral": situacao,
        "data_situacao_cadastral": pd.Timestamp(data),
        "motivo_situacao": motivo,
        "telefone": fone,  # outro campo do arquivo: mudar só ele não é versão nova
    }


RETRATOS = [
    [
        _estabelecimento(EMPRESA, "02", "2010-01-01"),
        _estabelecimento(OUTRA, "02", "2015-01-01"),
        _estabelecimento(MEI, "02", "2019-01-01"),
    ],
    [  # a empresa só trocou o telefone; a filial abriu; o MEI baixou
        _estabelecimento(EMPRESA, "02", "2010-01-01", fone="2"),
        _estabelecimento(FILIAL, "02", "2023-06-02"),
        _estabelecimento(OUTRA, "02", "2015-01-01"),
        _estabelecimento(MEI, "08", "2023-06-10", "01"),
    ],
    [  # a outra saiu do arquivo; a empresa ficou inapta (escrita sem o zero, como em alguns meses)
        _estabelecimento(EMPRESA, "4", "2023-07-05", "63", fone="2"),
        _estabelecimento(FILIAL, "02", "2023-06-02"),
        _estabelecimento(MEI, "08", "2023-06-10", "01"),
    ],
    [  # a mesma inapta, agora com o zero: não é versão nova
        _estabelecimento(EMPRESA, "04", "2023-07-05", "63", fone="2"),
        _estabelecimento(FILIAL, "02", "2023-06-02"),
        _estabelecimento(MEI, "08", "2023-06-10", "01"),
    ],
]


def _mudancas(retratos, meses) -> pd.DataFrame:
    partes = [
        diff(pd.DataFrame(antes), pd.DataFrame(depois), ["cnpj"], mes)
        for antes, depois, mes in zip(retratos, retratos[1:], meses[1:], strict=False)
    ]
    return pd.concat(partes, ignore_index=True)


def _versoes(retratos=RETRATOS, meses=MESES, raizes=RAIZES_PJ) -> pd.DataFrame:
    return sc.versoes(
        pd.DataFrame(retratos[-1]), _mudancas(retratos, meses), meses[0], raizes
    )


def _de(versoes: pd.DataFrame, cnpj: str) -> pd.DataFrame:
    return versoes[versoes["cnpj"] == sc._formatado(pd.Series([cnpj]))[0]]


def test_uma_versao_por_mudanca_da_situacao():
    versoes = _versoes()
    empresa = _de(versoes, EMPRESA)
    assert list(empresa[historico.MES]) == ["2023-05", "2023-07"]
    assert list(empresa["situacao_cadastral"]) == ["02", "04"]
    assert list(empresa["motivo_situacao"]) == ["00", "63"]
    assert list(empresa["data_situacao_cadastral"]) == [
        date(2010, 1, 1),
        date(2023, 7, 5),
    ]
    publicos = [pd.Timestamp(disponivel_em(m)) for m in ("2023-05", "2023-07")]
    assert list(empresa["disponivel_em"].map(pd.Timestamp)) == publicos
    filial = _de(versoes, FILIAL)
    assert list(filial[historico.MES]) == ["2023-06"]
    assert list(filial["matriz"]) == [False]


def test_quem_saiu_do_arquivo_ganha_versao_vazia_com_consta_falso():
    outra = _de(_versoes(), OUTRA)
    assert list(outra[historico.MES]) == ["2023-05", "2023-07"]
    assert list(outra[historico.CONSTA]) == [True, False]
    saiu = outra.iloc[-1]
    assert saiu["cnpj_basico"] == OUTRA[:8]  # a raiz fica, para o filtro da porta
    assert pd.isna(saiu["situacao_cadastral"]) and pd.isna(saiu["matriz"])


def test_so_pj_a_raiz_fora_da_lista_some_da_historia_inteira():
    versoes = _versoes()
    assert MEI[:8] not in set(versoes["cnpj_basico"])
    assert set(versoes["cnpj_basico"]) == RAIZES_PJ


def test_so_as_colunas_da_situacao_saem_e_o_cnpj_formatado():
    versoes = _versoes()
    assert list(versoes.columns) == list(sc.COLUNAS)
    assert "telefone" not in versoes.columns
    assert set(versoes["cnpj"]) == {
        "11.111.111/0001-11",
        "11.111.111/0002-92",
        "22.222.222/0001-22",
    }


def test_historico_que_nao_bate_com_o_vigente_para():
    vigente = [dict(linha) for linha in RETRATOS[-1]]
    vigente[0]["situacao_cadastral"] = "08"
    with pytest.raises(historico.HistoricoNaoConfere):
        sc.versoes(
            pd.DataFrame(vigente), _mudancas(RETRATOS, MESES), MESES[0], RAIZES_PJ
        )


def test_sem_mudanca_nenhuma_o_vigente_vale_desde_o_primeiro_mes():
    versoes = sc.versoes(pd.DataFrame(RETRATOS[0]), pd.DataFrame(), MESES[0], RAIZES_PJ)
    assert set(versoes[historico.MES]) == {MESES[0]}
    assert len(versoes) == 2


# --- sem olhar o futuro ---------------------------------------------------------------------------
_SITUACOES = st.sampled_from(
    ["02", "03", "04", "08", None]
)  # None: fora do arquivo naquele mês


@st.composite
def _historias(desenho):
    """Retratos de 2 a 5 meses de três estabelecimentos: cada mês, cada um tem uma situação ou está fora."""
    n = desenho(st.integers(2, 5))
    meses = [f"2023-{m:02d}" for m in range(5, 5 + n)]
    retratos = []
    for _ in range(n):
        retrato = []
        for cnpj in (EMPRESA, FILIAL, OUTRA):
            situacao = desenho(_SITUACOES)
            fone = desenho(st.sampled_from(["1", "2"]))
            if situacao is not None:
                retrato.append(
                    _estabelecimento(cnpj, situacao, "2020-01-01", fone=fone)
                )
        retratos.append(retrato)
    return meses, retratos


def _frame(retrato: list[dict]) -> pd.DataFrame:
    colunas = list(_estabelecimento(EMPRESA, "02", "2020-01-01"))
    return pd.DataFrame(retrato, columns=colunas)


def _o_que_valia(versoes: pd.DataFrame, mes: str) -> dict[str, str | None]:
    """A situação de cada CNPJ pela versão mais nova até o mês (sem a que tinha saído)."""
    ate = versoes[versoes[historico.MES] <= mes].sort_values(["cnpj", historico.MES])
    ultimas = ate.groupby("cnpj").tail(1)
    return {
        linha["cnpj"]: linha["situacao_cadastral"]
        for _, linha in ultimas.iterrows()
        if linha[historico.CONSTA]
    }


@settings(max_examples=60, deadline=None)
@given(_historias())
def test_a_versao_de_cada_mes_e_o_retrato_daquele_mes(historia):
    meses, retratos = historia
    frames = [_frame(r) for r in retratos]
    mudancas = pd.concat(
        [
            diff(a, b, ["cnpj"], m)
            for a, b, m in zip(frames, frames[1:], meses[1:], strict=False)
        ],
        ignore_index=True,
    )
    versoes = sc.versoes(frames[-1], mudancas, meses[0], RAIZES_PJ)
    for mes, retrato in zip(meses, retratos, strict=True):
        esperado = {
            sc._formatado(pd.Series([linha["cnpj"]]))[0]: linha["situacao_cadastral"]
            for linha in retrato
        }
        assert _o_que_valia(versoes, mes) == esperado
    # cortar o futuro não muda o passado: montar só até um mês dá as mesmas versões até ele
    corte = len(meses) // 2
    if corte >= 1:
        ate_o_corte = sc.versoes(
            frames[corte],
            mudancas[mudancas["mes"] <= meses[corte]],
            meses[0],
            RAIZES_PJ,
        )
        do_inteiro = versoes[versoes[historico.MES] <= meses[corte]]
        pd.testing.assert_frame_equal(
            ate_o_corte.reset_index(drop=True), do_inteiro.reset_index(drop=True)
        )
