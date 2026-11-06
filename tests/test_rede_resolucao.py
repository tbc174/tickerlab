"""Resolução de entidades pelas regras de código, em ordem fixa (ADR 0077, item 4; plano, tarefa 2.6).

Cada fonte vira observações: "a âncora (raiz da empresa ou CNPJ do fundo) tem este identificador, de
`desde` a `ate`, público desde `publico_em`, pela regra N". A resolução junta pela âncora; um
identificador que aponta para duas entidades no mesmo período é conflito e não liga nenhuma.
"""

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from base.rede import ids, resolucao

D = pd.Timestamp


def _obs(**campos):
    linha = {coluna: None for coluna in resolucao.COLUNAS_DAS_OBSERVACOES}
    linha.update(
        {
            "fonte": "teste",
            "tipo": "empresa",
            "regra": 2,
            "conferido_por": resolucao.PELA_REGRA,
        }
    )
    linha.update(campos)
    return linha


def _resolver(*linhas, fixados=None):
    return resolucao.resolver(
        pd.DataFrame(list(linhas), columns=list(resolucao.COLUNAS_DAS_OBSERVACOES)),
        fixados or {},
    )


def test_regras_em_ordem_fixa():
    assert [numero for numero, _ in resolucao.REGRAS] == [
        1,
        2,
        3,
        4,
        5,
        7,
    ]  # a 6 é da série de governo


def test_filial_liga_pela_raiz():
    """A matriz (0001) e a filial (0002) são a mesma empresa: a raiz é a âncora."""
    entidades, identificadores, _ = _resolver(
        _obs(
            ancora="33000167",
            sistema="cnpj",
            valor="33000167000101",
            regra=1,
            nome="PETRO",
        ),
        _obs(
            ancora="33000167",
            sistema="cnpj",
            valor="33000167000292",
            regra=1,
            fonte="outra",
        ),
        _obs(ancora="33000167", sistema="cnpj_raiz", valor="33000167"),
    )
    assert len(entidades) == 1
    assert entidades.iloc[0]["id_entidade"] == ids.id_entidade(
        "empresa", "cnpj_raiz", "33000167"
    )
    assert sorted(identificadores["valor"]) == [
        "33000167",
        "33000167000101",
        "33000167000292",
    ]
    assert entidades.iloc[0]["fontes"] == "outra,teste"


def test_nome_pela_prioridade_da_fonte():
    entidades, _, _ = _resolver(
        _obs(
            ancora="1",
            sistema="cnpj_raiz",
            valor="1",
            nome="NOME DO GLEIF",
            prioridade_do_nome=3,
        ),
        _obs(
            ancora="1",
            sistema="cnpj_raiz",
            valor="1",
            nome="NOME DA CVM",
            prioridade_do_nome=0,
        ),
    )
    assert entidades.iloc[0]["nome"] == "NOME DA CVM"


def test_conflito_entre_duas_entidades_no_mesmo_periodo():
    """O mesmo código de regulador em duas raízes ao mesmo tempo: não liga nenhuma (e fica anotado)."""
    _, identificadores, conflitos = _resolver(
        _obs(ancora="11111111", sistema="cnpj_raiz", valor="11111111"),
        _obs(ancora="22222222", sistema="cnpj_raiz", valor="22222222"),
        _obs(ancora="11111111", sistema="codigo_ans", valor="368253", regra=5),
        _obs(ancora="22222222", sistema="codigo_ans", valor="368253", regra=5),
    )
    assert "368253" not in set(identificadores["valor"])
    assert set(conflitos["ancora"]) == {"11111111", "22222222"}
    assert set(conflitos["regra"]) == {5}


def test_ticker_que_troca_de_dono_em_periodos_separados_nao_e_conflito():
    _, identificadores, conflitos = _resolver(
        _obs(ancora="1", sistema="ticker", valor="ABCD3", regra=4, desde=D("2010-05-31"), ate=D("2015-05-31")),
        _obs(ancora="2", sistema="ticker", valor="ABCD3", regra=4, desde=D("2015-05-31")),
    )  # fmt: skip
    assert conflitos.empty
    assert (identificadores["sistema"] == "ticker").sum() == 2


def test_um_identificador_por_entidade_por_periodo():
    """Duas fontes com o mesmo ticker no mesmo período viram uma linha (fontes juntas, regra menor)."""
    _, identificadores, _ = _resolver(
        _obs(ancora="1", sistema="ticker", valor="PETR4", regra=4, desde=D("2018-05-31"), publico_em=D("2018-05-31"), fonte="fca"),
        _obs(ancora="1", sistema="ticker", valor="PETR4", regra=7, desde=D("2018-05-31"), publico_em=D("2019-01-31"), fonte="conferida", conferido_por=resolucao.PELA_TABELA),
    )  # fmt: skip
    linha = identificadores[identificadores["sistema"] == "ticker"]
    assert len(linha) == 1
    assert linha.iloc[0][["regra", "conferido_por", "fontes"]].tolist() == [
        4, resolucao.PELA_REGRA, "conferida,fca",
    ]  # fmt: skip
    assert linha.iloc[0]["publico_em"] == D("2018-05-31")
    chave = ["sistema", "valor", "desde"]
    assert not identificadores.duplicated(chave).any()


def test_conferido_por():
    """O que veio só da tabela conferida à mão diz `tabela` (regra 7); o resto, `regra`."""
    _, identificadores, _ = _resolver(
        _obs(ancora="1", sistema="emissor", valor="ABCD", regra=7, conferido_por=resolucao.PELA_TABELA),
        _obs(ancora="1", sistema="cnpj_raiz", valor="1"),
    )  # fmt: skip
    por = dict(
        zip(identificadores["sistema"], identificadores["conferido_por"], strict=True)
    )
    assert por == {"emissor": resolucao.PELA_TABELA, "cnpj_raiz": resolucao.PELA_REGRA}


def _intervalos_se_cruzam(a, b):
    inicio_a, fim_a = a
    inicio_b, fim_b = b
    return (fim_b is None or inicio_a < fim_b) and (fim_a is None or inicio_b < fim_a)


_periodo = st.tuples(
    st.integers(2010, 2020), st.one_of(st.none(), st.integers(1, 6))
).map(lambda p: (p[0], None if p[1] is None else p[0] + p[1]))


@settings(max_examples=150, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from("123"), st.sampled_from(["A", "B"]), _periodo),
        min_size=1,
        max_size=8,
    )
)
def test_conflito_nunca_liga(observacoes):
    """Nenhum código fica em duas entidades ao mesmo tempo, e o que cruzava some de todas."""
    linhas = [
        _obs(ancora=ancora, sistema="codigo_x", valor=valor, regra=5,
             desde=D(f"{inicio}-01-01"), ate=None if fim is None else D(f"{fim}-01-01"))
        for ancora, valor, (inicio, fim) in observacoes
    ]  # fmt: skip
    _, identificadores, _ = _resolver(*linhas)
    saida = identificadores[identificadores["sistema"] == "codigo_x"]

    def periodo(linha):
        fim = None if pd.isna(linha["ate"]) else linha["ate"].year
        return linha["desde"].year, fim

    linhas_de_saida = list(saida.itertuples(index=False))
    for i, a in enumerate(linhas_de_saida):
        for b in linhas_de_saida[i + 1 :]:
            if a.valor == b.valor and a.id_entidade != b.id_entidade:
                assert not _intervalos_se_cruzam(
                    periodo(a._asdict()), periodo(b._asdict())
                )
    for ancora, valor, periodo_a in observacoes:
        cruza_com_outra = any(
            v == valor and an != ancora and _intervalos_se_cruzam(periodo_a, p)
            for an, v, p in observacoes
        )
        if cruza_com_outra:
            id_ = ids.id_entidade("empresa", "cnpj_raiz", ancora)
            mesmo = [
                linha for linha in linhas_de_saida
                if linha.id_entidade == id_ and linha.valor == valor
                and periodo(linha._asdict()) == periodo_a
            ]  # fmt: skip
            assert not mesmo
