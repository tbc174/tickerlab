"""Validade das ligações e cadeia de controle (B-03 do backlog do dossiê da plataforma; ADR 0077).

O critério de aceite da B-03: para 20 CNPJs de teste, a controladora final na data D bate com o FRE de
D, e "cortar o futuro" vale para as ligações. Os FREs aqui são de mentira, montados como os da CVM
(uma linha por controlada em cada FRE da companhia) e passam pelo mesmo caminho da base
(`das_controladas` → `normalizar` → `controle`).
"""

import dataclasses
import json

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base.rede import controle, ligacoes, ligacoes_das_fontes

D = pd.Timestamp
# referência do FRE → quando ficou público (a entrega à CVM)
FRES = {
    "2019-12-31": "2020-05-29",
    "2020-12-31": "2021-05-31",
    "2021-12-31": "2022-05-31",
}
TODOS = tuple(FRES)
HOJE = D("2026-10-21")

# 20 CNPJs de teste (raiz = 8 primeiros dígitos; o id da entidade é "E" + a raiz, para ler fácil)
RAIZES = {
    nome: f"{i + 10:02d}{i + 10:02d}{i + 10:02d}{i + 10:02d}"
    for i, nome in enumerate(
        [
            "H1",
            "H2",
            "H3",
            "H4",
            "A1",
            "A2",
            "A3",
            "A4",
            "A5",
            "B1",
            "B2",
            "C1",
            "X1",
            "D1",
            "D2",
            "D3",
            "D4",
            "E1",
            "E2",
            "F1",
        ]
    )
}


def _cnpj(nome: str) -> str:
    return RAIZES[nome] + "000100"


def _id(nome: str) -> str:
    return "E" + RAIZES[nome]


# o que cada companhia diz no FRE: (controladora, controlada, tipo, participação, referências)
DECLARADO = [
    ("H1", "A1", "controlada", 100.0, TODOS),
    ("H1", "A2", "controlada", 70.0, TODOS),
    ("H1", "A5", "coligada", 30.0, TODOS),  # coligada não é controle
    ("A1", "B1", "controlada", 100.0, TODOS),
    ("A1", "B2", "controlada", 51.0, TODOS),
    ("B1", "C1", "controlada", 100.0, TODOS),
    ("H2", "A3", "controlada", 60.0, ("2019-12-31",)),  # vendida em 2020 ...
    ("H3", "A3", "controlada", 60.0, ("2020-12-31", "2021-12-31")),  # ... para a H3
    ("H2", "A4", "controlada", 60.0, ("2019-12-31",)),
    ("H2", "A4", "controlada", 80.0, ("2020-12-31", "2021-12-31")),  # a % mudou
    ("H4", "D1", "controlada", 100.0, TODOS),
    ("D1", "D2", "controlada", 100.0, TODOS),
    ("D2", "D3", "controlada", 100.0, TODOS),
    ("D3", "D4", "controlada", 100.0, TODOS),
    ("D4", "F1", "controlada", 100.0, ("2021-12-31",)),  # comprada em 2021
    ("H4", "E1", "controlada", 100.0, TODOS),
    ("H4", "E2", "controlada", 100.0, ("2019-12-31", "2020-12-31")),  # sai em 2021
]

# a controladora final pelo FRE de cada data (lido à mão das linhas acima)
FINAL_PELO_FRE = {
    "2019-12-31": {"A3": "H2", "F1": "F1", "E2": "H4"},
    "2020-12-31": {"A3": "H3", "F1": "F1", "E2": "H4"},
    "2021-12-31": {"A3": "H3", "F1": "H4", "E2": "E2"},
}
SEMPRE = {
    "H1": "H1", "H2": "H2", "H3": "H3", "H4": "H4", "A1": "H1", "A2": "H1", "A4": "H2",
    "A5": "A5", "B1": "H1", "B2": "H1", "C1": "H1", "X1": "X1", "D1": "H4", "D2": "H4",
    "D3": "H4", "D4": "H4", "E1": "H4",
}  # fmt: skip


def _controladas() -> pd.DataFrame:
    linhas = [
        {
            "cnpj_companhia": _cnpj(dona),
            "referencia": D(ref),
            "conhecido_em": D(FRES[ref]),
            "cnpj": _cnpj(filha),
            "tipo": tipo,
            "participacao": participacao,
            "origem_sha256": "aa" * 32,
        }
        for dona, filha, tipo, participacao, refs in DECLARADO
        for ref in refs
    ]
    # a X1 e a H3 de 2019 entregam FRE sem controladas: a linha da própria companhia sem `cnpj`
    vazias = [
        {"cnpj_companhia": _cnpj(dona), "referencia": D(ref), "conhecido_em": D(FRES[ref]),
         "cnpj": None, "tipo": None, "participacao": None, "origem_sha256": "aa" * 32}
        for dona in ("X1", "H3")
        for ref in TODOS
    ]  # fmt: skip
    return pd.DataFrame(linhas + vazias)


def _ligacoes() -> pd.DataFrame:
    identificadores = pd.DataFrame(
        {
            "sistema": "cnpj_raiz",
            "valor": list(RAIZES.values()),
            "id_entidade": [_id(n) for n in RAIZES],
        }
    )
    r = ligacoes_das_fontes.Resolvedor(identificadores)
    tabela = ligacoes_das_fontes.das_controladas(_controladas(), r)
    return ligacoes.normalizar(tabela)  # as colunas de trabalho do FRE ficam de fora


def _nome(id_entidade: str | None) -> str | None:
    por_id = {_id(n): n for n in RAIZES}
    return None if id_entidade is None else por_id[id_entidade]


@pytest.mark.parametrize("referencia", TODOS)
def test_controladora_final_dos_20_cnpjs_bate_com_o_fre_da_data(referencia):
    """Critério de aceite da B-03: sabendo o que se sabe hoje, a final em D é a que o FRE de D diz."""
    finais = controle.controladoras_finais(
        _ligacoes(), [_id(n) for n in RAIZES], D(referencia), conhecido_em=HOJE
    )
    assert len(finais) == len(RAIZES) == 20
    esperado = {**SEMPRE, **FINAL_PELO_FRE[referencia]}
    obtido = {
        _nome(e): _nome(f)
        for e, f in zip(finais["entidade"], finais["final"], strict=True)
    }
    assert obtido == esperado
    assert set(finais["situacao"]) == {controle.FINAL}


def test_sem_olhar_o_futuro_a_final_e_a_do_fre_ja_entregue():
    """Em 31/12/2020, sem saber o futuro, a venda da A3 (no FRE de 2020, entregue em 05/2021) não
    aparece: a final é a H2 do FRE de 2019. Sabendo o de hoje, é a H3."""
    tabela = _ligacoes()
    dia = D("2020-12-31")
    no_dia = controle.cadeia_de_controle(tabela, _id("A3"), dia)
    hoje = controle.cadeia_de_controle(tabela, _id("A3"), dia, conhecido_em=HOJE)
    assert _nome(no_dia.final) == "H2"
    assert _nome(hoje.final) == "H3"
    assert no_dia.conhecido_em == "2020-12-31"


def test_cadeia_inteira_com_o_caminho_e_a_participacao():
    cadeia = controle.cadeia_de_controle(
        _ligacoes(), _id("C1"), D("2021-12-31"), conhecido_em=HOJE
    )
    assert [_nome(e) for e in cadeia.caminho] == ["C1", "B1", "A1", "H1"]
    assert cadeia.participacoes == (100.0, 100.0, 100.0)
    assert cadeia.situacao == controle.FINAL
    # tipos simples: a cadeia vira JSON como está (para uma rota da API um dia)
    assert json.loads(json.dumps(dataclasses.asdict(cadeia)))["final"] == _id("H1")


def test_participacao_que_muda_e_outro_periodo_e_a_cadeia_segue():
    """D17: a A4 passa de 60% para 80% no FRE de 2020; são dois períodos e a H2 continua a final."""
    tabela = _ligacoes()
    a4 = tabela[tabela["de"] == _id("A4")].sort_values("aconteceu_em")
    assert a4["participacao"].tolist() == [60.0, 80.0]
    assert a4["ate"].iloc[0] == a4["aconteceu_em"].iloc[1]
    for ref, participacao in (("2019-12-31", 60.0), ("2021-12-31", 80.0)):
        cadeia = controle.cadeia_de_controle(
            tabela, _id("A4"), D(ref), conhecido_em=HOJE
        )
        assert cadeia.participacoes == (participacao,)


def test_grupo_de_controle_e_tudo_abaixo_da_final():
    grupo = controle.grupo_de_controle(_ligacoes(), _id("B2"), D("2021-12-31"), HOJE)
    assert {_nome(e) for e in grupo} == {"H1", "A1", "A2", "B1", "B2", "C1"}


def _ligacao(de: str, para: str, **campos: object) -> dict[str, object]:
    return {
        "de": de, "para": para, "tipo": "controlada_de", "participacao": 100.0,
        "aconteceu_em": D("2019-12-31"), "publico_em": D("2020-05-29"), "fonte": "cvm-fre",
        "origem_sha256": "ab" * 32, "conferido_por": "regra", **campos,
    }  # fmt: skip


def test_duas_controladoras_ao_mesmo_tempo_e_ambigua_e_nao_escolhe():
    tabela = ligacoes.normalizar(
        pd.DataFrame([_ligacao("EX", "EA"), _ligacao("EX", "EB", participacao=50.0)])
    )
    cadeia = controle.cadeia_de_controle(tabela, "EX", D("2020-12-31"))
    assert cadeia.situacao == controle.AMBIGUA
    assert cadeia.final is None
    assert set(cadeia.candidatas) == {"EA", "EB"}


def test_ciclo_para_e_avisa():
    tabela = ligacoes.normalizar(
        pd.DataFrame([_ligacao("EA", "EB"), _ligacao("EB", "EC"), _ligacao("EC", "EA")])
    )
    cadeia = controle.cadeia_de_controle(tabela, "EA", D("2020-12-31"))
    assert cadeia.situacao == controle.CICLO
    assert cadeia.final is None
    assert cadeia.caminho == ("EA", "EB", "EC")


def test_quem_nao_esta_na_rede_e_a_propria_final():
    cadeia = controle.cadeia_de_controle(_ligacoes(), "Esozinha", D("2020-12-31"))
    assert (cadeia.final, cadeia.caminho, cadeia.situacao) == (
        "Esozinha", ("Esozinha",), controle.FINAL,
    )  # fmt: skip


# --- "cortar o futuro" vale para as ligações -----------------------------------------------------
DIAS = st.dates(min_value=D("2018-01-01").date(), max_value=D("2024-12-31").date())
ENTIDADES = st.sampled_from(["EA", "EB", "EC", "ED"])


@st.composite
def _tabelas(draw):
    linhas = {}
    for _ in range(draw(st.integers(1, 10))):
        de, para = draw(ENTIDADES), draw(ENTIDADES)
        inicio = D(draw(DIAS))
        if de == para:
            continue
        publico = inicio + pd.Timedelta(days=draw(st.integers(0, 400)))
        fim = draw(st.one_of(st.none(), DIAS))
        fim = None if fim is None or D(fim) <= inicio else D(fim)
        fim_publico = (
            None if fim is None else fim + pd.Timedelta(days=draw(st.integers(0, 400)))
        )
        linhas[(de, para, inicio)] = _ligacao(
            de, para, aconteceu_em=inicio, publico_em=publico, ate=fim,
            ate_publico_em=fim_publico,
        )  # fmt: skip
    tabela = pd.DataFrame(list(linhas.values()), columns=list(ligacoes.COLUNAS))
    return ligacoes.normalizar(tabela)


def _chaves(tabela: pd.DataFrame) -> set[tuple]:
    return set(map(tuple, tabela[ligacoes.CHAVE].astype(str).to_numpy()))


@settings(max_examples=60, deadline=None)
@given(tabela=_tabelas(), dia=DIAS)
def test_no_proprio_dia_e_o_como_era_em_sem_o_que_ainda_nao_tinha_comecado(tabela, dia):
    dia = D(dia)
    esperado = ligacoes.como_era_em(tabela, dia)
    esperado = esperado[esperado["aconteceu_em"] <= dia]
    assert _chaves(controle.valiam_em(tabela, dia)) == _chaves(esperado)


@settings(max_examples=60, deadline=None)
@given(tabela=_tabelas(), dia=DIAS, depois=st.integers(0, 2000))
def test_cortar_o_futuro_nao_muda_o_que_valia(tabela, dia, depois):
    """Sabendo até K: tirar as ligações públicas depois de K e apagar os fins públicos depois de K
    não muda o que valia em D, nem a controladora final de ninguém."""
    dia = D(dia)
    conhecido_em = dia + pd.Timedelta(days=depois)
    cortada = tabela[tabela["publico_em"] <= conhecido_em].copy()
    fim_futuro = cortada["ate_publico_em"] > conhecido_em
    cortada.loc[fim_futuro, ["ate", "ate_publico_em"]] = pd.NaT
    antes = controle.valiam_em(tabela, dia, conhecido_em)
    assert _chaves(antes) == _chaves(controle.valiam_em(cortada, dia, conhecido_em))
    assert (antes["publico_em"] <= conhecido_em).all()
    ids = ["EA", "EB", "EC", "ED"]
    pd.testing.assert_frame_equal(
        controle.controladoras_finais(tabela, ids, dia, conhecido_em),
        controle.controladoras_finais(cortada, ids, dia, conhecido_em),
    )


def test_conhecido_em_antes_do_dia_e_erro():
    with pytest.raises(ValueError, match="conhecido_em"):
        controle.valiam_em(_ligacoes(), D("2021-12-31"), D("2021-01-01"))
