"""A tabela `ligacoes` da rede com as três datas (ADR 0077; plano, tarefa 3.1).

Uma ligação é "de → para" com um tipo; `aconteceu_em` é a data do fato, `publico_em` quando ficou
público e `coletado_em` quando a base o guardou. Nada é apagado entre cargas: o que some da fonte fica,
encerrado pela carga (D6). "Como era em D" só traz o que já era público em D (D5).
"""

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from base.rede import ligacoes

D = pd.Timestamp
ULTRAPAR, IPIRANGA, OXITENO = "E" + "1" * 20, "E" + "2" * 20, "E" + "3" * 20


def _ligacao(**campos: object) -> dict[str, object]:
    return {
        "de": IPIRANGA,
        "para": ULTRAPAR,
        "tipo": "controlada_de",
        "participacao": 100.0,
        "aconteceu_em": D("2019-12-31"),
        "publico_em": D("2020-05-29"),
        "fonte": "cvm-fre",
        "origem_sha256": "ab" * 32,
        "conferido_por": "regra",
        **campos,
    }


def _tabela(*linhas: dict[str, object]) -> pd.DataFrame:
    return ligacoes.normalizar(pd.DataFrame(list(linhas)))


def test_colunas_e_tipos():
    tabela = _tabela(_ligacao(), _ligacao(de=OXITENO, ate=D("2021-12-31")))
    assert list(tabela.columns) == list(ligacoes.COLUNAS)
    for coluna in ligacoes.DATAS:
        assert str(tabela[coluna].dtype) == "datetime64[ns]", coluna
    assert tabela["participacao"].dtype == float
    vigente, encerrada = tabela.sort_values("de").to_dict("records")
    assert (vigente["situacao"], vigente["encerrada_por"]) == ("vigente", None)
    assert (encerrada["situacao"], encerrada["encerrada_por"]) == ("encerrada", "fonte")


def test_chave_repetida_e_erro():
    import pytest

    with pytest.raises(ValueError, match="repetida"):
        _tabela(_ligacao(), _ligacao(participacao=99.0))


def test_aconteceu_em_das_sancoes():
    """Na sanção, o fato é o ato administrativo publicado; a data da infração vai em coluna própria."""
    sancoes = pd.DataFrame(
        {
            "de": [IPIRANGA],
            "para": ["E" + "9" * 20],
            "ato_publicado_em": [D("2022-03-10")],
            "infracao_em": [D("2018-07-01")],
            "publico_em": [D("2022-03-10")],
            "fonte": ["governo-de-mentira"],
            "origem_sha256": ["cd" * 32],
        }
    )
    linha = ligacoes.de_sancoes(sancoes).iloc[0]
    assert linha["tipo"] == "sancionada_por"
    assert linha["aconteceu_em"] == D("2022-03-10")
    assert linha["infracao_em"] == D("2018-07-01")


def test_como_era_em_nao_traz_o_que_ficou_publico_depois():
    """Caso fixo: em 31/12/2020 a controlada do FRE entregue em 2021 ainda não existia."""
    tabela = _tabela(
        _ligacao(),
        _ligacao(de=OXITENO, aconteceu_em=D("2020-12-31"), publico_em=D("2021-05-31")),
    )
    em_2020 = ligacoes.como_era_em(tabela, D("2020-12-31"))
    assert list(em_2020["de"]) == [IPIRANGA]
    assert set(ligacoes.como_era_em(tabela, D("2021-06-01"))["de"]) == {
        IPIRANGA,
        OXITENO,
    }


def test_como_era_em_respeita_o_fim():
    tabela = _tabela(_ligacao(ate=D("2021-03-31")))
    assert len(ligacoes.como_era_em(tabela, D("2021-03-30"))) == 1
    assert ligacoes.como_era_em(tabela, D("2021-03-31")).empty  # `ate` não inclui o dia


_DIAS = st.integers(min_value=0, max_value=3000).map(
    lambda n: D("2015-01-01") + pd.Timedelta(days=n)
)


@settings(max_examples=60, deadline=None)
@given(
    linhas=st.lists(
        st.tuples(_DIAS, st.one_of(st.none(), _DIAS)), min_size=1, max_size=15
    ),
    dia=_DIAS,
)
def test_como_era_em_e_igual_sem_o_futuro(linhas, dia):
    """Cortar o que ficou público depois de D não muda "como era em D"; nada dela é de depois."""
    tabela = _tabela(
        *(
            _ligacao(de=f"E{n:020d}", publico_em=publico, ate=fim)
            for n, (publico, fim) in enumerate(linhas)
        )
    )
    em_d = ligacoes.como_era_em(tabela, dia)
    assert (em_d["publico_em"] <= dia).all()
    sem_o_futuro = tabela[tabela["publico_em"] <= dia]
    pd.testing.assert_frame_equal(
        em_d.reset_index(drop=True),
        ligacoes.como_era_em(sem_o_futuro, dia).reset_index(drop=True),
    )


def test_nada_apagado_entre_cargas():
    """A ligação que some da fonte fica, encerrada pela carga; a que a fonte encerra, pela fonte."""
    carga_1 = _tabela(
        _ligacao(),
        _ligacao(de=OXITENO),
        _ligacao(de="E" + "4" * 20),
    )
    nova = _tabela(
        _ligacao(publico_em=D("2020-06-30")),  # a mesma ligação, vista de novo
        _ligacao(de="E" + "4" * 20, ate=D("2022-12-31")),  # a fonte encerrou
        _ligacao(de="E" + "5" * 20, publico_em=D("2023-05-31")),  # nova
    )
    juntas = ligacoes.juntar_com_a_vigente(nova, carga_1, D("2023-06-02"))
    por_de = juntas.set_index("de")
    assert len(juntas) == 4
    assert por_de.loc[IPIRANGA, "publico_em"] == D(
        "2020-05-29"
    )  # a 1ª vez que se soube
    assert por_de.loc[OXITENO, ["situacao", "encerrada_por"]].tolist() == [
        "encerrada",
        "carga",
    ]
    assert por_de.loc[OXITENO, "ate"] == D("2023-06-02")
    assert por_de.loc["E" + "4" * 20, "encerrada_por"] == "fonte"
    assert por_de.loc["E" + "5" * 20, "situacao"] == "vigente"
    # a encerrada pela carga continua encerrada na carga seguinte, com a mesma data
    de_novo = ligacoes.juntar_com_a_vigente(nova, juntas, D("2023-07-01"))
    assert de_novo.set_index("de").loc[OXITENO, "ate"] == D("2023-06-02")


def test_primeira_carga_e_a_propria_nova():
    nova = _tabela(_ligacao())
    pd.testing.assert_frame_equal(
        ligacoes.juntar_com_a_vigente(nova, None, D("2023-06-02")), nova
    )


def test_coletado_em_vem_do_registro():
    tabela = _tabela(_ligacao(), _ligacao(de=OXITENO, origem_sha256="ef" * 32))
    registro = {"ab" * 32: D("2024-03-05 10:31", tz="UTC")}
    com_data = ligacoes.com_coletado_em(tabela, registro).set_index("de")
    assert com_data.loc[IPIRANGA, "coletado_em"] == D("2024-03-05")
    assert pd.isna(com_data.loc[OXITENO, "coletado_em"])


def test_comprimir_periodos_seguidos():
    """Passos seguidos da mesma chave viram um período; um buraco começa outro."""
    linhas = pd.DataFrame(
        {
            "fundo": ["F", "F", "F", "F", "G"],
            "isin": ["X", "X", "X", "X", "X"],
            "inicio": [1, 2, 3, 5, 2],
            "fim": [1, 2, 3, 5, 2],
            "publico_em": [D("2020-01-01") + pd.Timedelta(days=d) for d in range(5)],
        }
    )
    periodos = ligacoes.comprimir_periodos(linhas.iloc[::-1], ["fundo", "isin"])
    assert periodos[["fundo", "inicio", "fim"]].values.tolist() == [
        ["F", 1, 3],
        ["F", 5, 5],
        ["G", 2, 2],
    ]
    assert periodos["publico_em"].iloc[0] == D("2020-01-01")  # o do primeiro passo
    # comprimir de novo (os pedaços de cada ano) junta o que encosta
    junto = ligacoes.comprimir_periodos(
        pd.concat([periodos, periodos.assign(inicio=6, fim=7)]), ["fundo", "isin"]
    )
    assert junto[["fundo", "inicio", "fim"]].values.tolist() == [
        ["F", 1, 3],
        ["F", 5, 7],
        ["G", 2, 2],
        ["G", 6, 7],
    ]


def test_colunas_iguais_as_do_dicionario():
    from base.dicionario import TABELAS

    assert list(ligacoes.COLUNAS) == list(TABELAS["ligacoes"].colunas)
    assert TABELAS["ligacoes"].modulo == "rede"
    assert list(TABELAS["ligacoes"].chaves) == ligacoes.CHAVE
