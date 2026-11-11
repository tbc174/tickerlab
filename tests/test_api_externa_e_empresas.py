"""A trava de pessoa em lote (`empresas.e_empresas`, linha 806): a mesma regra de `e_empresa`, item a item.

O lote existe só para a rota dos comparáveis não perguntar à rede uma vez por candidata; a regra de quem é
empresa e quem é pessoa não pode mudar em nada. O lote é comparado com o `e_empresa` de hoje e com a regra
como era antes do lote (`_regra_item_a_item`, cópia guardada aqui, com o `resolver` da rede de verdade): se
o lote, o `e_empresa` ou o `resolver` mudarem e deixarem de dizer o mesmo, este arquivo falha. Com as listas sem
pessoa da Receita (linha 843), o lote é comparado com o `e_empresa`, com e sem a rede. Rede de mentira, sem internet; os CNPJs são de ninguém.
"""

from datetime import date

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base.porta import Porta
from base.porta.rede import resolver, views
from src.api_externa.conjuntos import empresas
from tests import test_api_externa_e_empresa as um_a_um

EMPRESA = "11111111000191"
OUTRA_EMPRESA = "12121212000191"
MEI = "33333333000191"
EMPRESARIO_INDIVIDUAL = "44444444000191"
MEI_VAZIO = "45454545000191"  # sem a resposta do MEI: na dúvida, é pessoa
PESSOA_VAZIA = "46464646000191"  # sem a resposta de `trata_como_pessoa`: idem
FUNDO = "66666666000191"
FILIAL_QUE_E_FUNDO = (
    "11111111000272"  # a raiz é da EMPRESA, mas o CNPJ inteiro é de um fundo
)
EM_DUAS_ENTIDADES = "70707070000191"
ENTIDADE_REPETIDA = "71717171000191"
COM_ID_DE_PESSOA = "72727272000191"
SEM_LINHA_NA_REDE = (
    "73737373000191"  # o identificador aponta para um id que `entidades` não tem
)
COM_LETRAS = "12ABC34501DE35"
AUSENTE = "88888888000191"
TICKER = "ALFA3"
ID_DA_EMPRESA = "E" + "1" * 20
ID_DE_PESSOA = "P" + "2" * 20
ID_AUSENTE = "E" + "f" * 20


def _id(numero: int) -> str:
    return "E" + f"{numero:020x}"


# quem cada entidade é: (id, tipo, mei, trata_como_pessoa)
ENTIDADES = [
    (ID_DA_EMPRESA, "empresa", False, False),
    (_id(2), "empresa", False, False),
    (_id(3), "empresa", True, False),
    (_id(4), "empresa", False, True),
    (_id(5), "empresa", None, False),
    (_id(6), "empresa", False, None),
    (_id(7), "fundo", False, False),
    (_id(8), "fundo", False, False),
    (_id(9), "empresa", False, False),
    (_id(10), "empresa", False, False),
    (_id(11), "empresa", False, False),
    (
        _id(11),
        "empresa",
        False,
        False,
    ),  # a mesma entidade duas vezes: na dúvida, não sai
    (
        ID_DE_PESSOA,
        "empresa",
        False,
        False,
    ),  # id de pessoa nunca sai, diga a linha o que disser
    (_id(13), "empresa", False, False),
]
# por onde cada entidade é achada: (id, sistema, valor)
IDENTIFICADORES = [
    (ID_DA_EMPRESA, "cnpj_raiz", EMPRESA[:8]),
    (ID_DA_EMPRESA, "ticker", TICKER),
    (_id(2), "cnpj_raiz", OUTRA_EMPRESA[:8]),
    (_id(3), "cnpj_raiz", MEI[:8]),
    (_id(4), "cnpj_raiz", EMPRESARIO_INDIVIDUAL[:8]),
    (_id(5), "cnpj_raiz", MEI_VAZIO[:8]),
    (_id(6), "cnpj_raiz", PESSOA_VAZIA[:8]),
    (_id(7), "cnpj", FUNDO),
    (_id(8), "cnpj", FILIAL_QUE_E_FUNDO),
    (_id(9), "cnpj_raiz", EM_DUAS_ENTIDADES[:8]),
    (_id(10), "cnpj_raiz", EM_DUAS_ENTIDADES[:8]),
    (_id(11), "cnpj_raiz", ENTIDADE_REPETIDA[:8]),
    (ID_DE_PESSOA, "cnpj_raiz", COM_ID_DE_PESSOA[:8]),
    (_id(12), "cnpj_raiz", SEM_LINHA_NA_REDE[:8]),
    (_id(13), "cnpj_raiz", COM_LETRAS[:8]),
]
# o que se pergunta: CNPJs de todo tipo, formatos que a rota não deixaria passar e ids da rede
PERGUNTAS = [
    EMPRESA,
    OUTRA_EMPRESA,
    MEI,
    EMPRESARIO_INDIVIDUAL,
    MEI_VAZIO,
    PESSOA_VAZIA,
    FUNDO,
    FILIAL_QUE_E_FUNDO,
    EM_DUAS_ENTIDADES,
    ENTIDADE_REPETIDA,
    COM_ID_DE_PESSOA,
    SEM_LINHA_NA_REDE,
    COM_LETRAS,
    COM_LETRAS.lower(),
    AUSENTE,
    EMPRESA[:8],
    MEI[:8],
    "11.111.111/0001-91",
    f" {EMPRESA} ",
    TICKER,
    TICKER.lower(),
    ID_DA_EMPRESA,
    ID_DE_PESSOA,
    ID_AUSENTE,
    "",
    "   ",
    "123",
    "abc",
    "0" * 14,
    EMPRESA + "0",
    "CNPJ inválido",
]
SAO_EMPRESAS = {
    EMPRESA,
    OUTRA_EMPRESA,
    COM_LETRAS,
    COM_LETRAS.lower(),
    EMPRESA[:8],
    "11.111.111/0001-91",
    f" {EMPRESA} ",
    TICKER,
    TICKER.lower(),
    ID_DA_EMPRESA,
}  # fmt: skip  (a rede procura em maiúsculas e sem pontuação, como o `resolver`)


def _entidades(linhas=ENTIDADES) -> pd.DataFrame:
    tabela = pd.DataFrame(
        linhas, columns=["id_entidade", "tipo", "mei", "trata_como_pessoa"]
    )
    for coluna in ("mei", "trata_como_pessoa"):
        tabela[coluna] = tabela[coluna].astype("boolean")
    return tabela.astype({"id_entidade": "string", "tipo": "string"}).assign(
        publico_em=date(2020, 1, 1)
    )


def _identificadores(linhas=IDENTIFICADORES) -> pd.DataFrame:
    tabela = pd.DataFrame(linhas, columns=["id_entidade", "sistema", "valor"])
    return tabela.astype("string").assign(publico_em=date(2020, 1, 1))


def _porta(pasta, entidades=None, identificadores=None, sem=()) -> Porta:
    """A porta só com a rede de mentira; `sem` tira uma das duas tabelas."""
    extras = {
        "entidades": _entidades() if entidades is None else entidades,
        "identificadores": (
            _identificadores() if identificadores is None else identificadores
        ),
    }
    for nome in sem:
        del extras[nome]
    return Porta(pasta, arquivos={}, conferidas={}, extras=extras)


def _regra_item_a_item(porta: Porta, cnpj: str) -> bool:
    """O `e_empresa` como era antes do lote (PR da linha 806), guardado aqui como juiz da equivalência."""
    con = porta.con
    if "entidades" not in views(con):
        return False
    try:
        id_entidade = resolver(con, cnpj, None)
    except LookupError:
        return False
    if id_entidade.startswith("P"):
        return False
    achadas = con.execute(
        "SELECT tipo, mei, trata_como_pessoa FROM entidades WHERE id_entidade = $id",
        {"id": id_entidade},
    ).fetchall()
    if len(achadas) != 1:
        return False
    tipo, mei, trata_como_pessoa = achadas[0]
    return tipo == "empresa" and not empresas._sim(mei) and not empresas._sim(trata_como_pessoa)  # fmt: skip


# ---------------------------------------------------------------- a mesma regra


def test_o_lote_responde_o_mesmo_que_a_regra_item_a_item(tmp_path):
    with _porta(tmp_path) as porta:
        lote = empresas.e_empresas(porta, PERGUNTAS)
        um_a_um = {cnpj: _regra_item_a_item(porta, cnpj) for cnpj in PERGUNTAS}
    assert lote == um_a_um
    # o juiz não basta: o que sai como empresa é escrito à mão, e nenhuma pessoa está na lista
    assert {cnpj for cnpj, sim in lote.items() if sim} == SAO_EMPRESAS


def test_e_empresa_responde_o_mesmo_que_o_lote_e_que_a_regra_de_antes(tmp_path):
    with _porta(tmp_path) as porta:
        lote = empresas.e_empresas(porta, PERGUNTAS)
        for cnpj in PERGUNTAS:
            um = empresas.e_empresa(porta, cnpj)
            assert um is lote[cnpj] is _regra_item_a_item(porta, cnpj), cnpj


@pytest.mark.parametrize(
    "cnpj",
    [MEI, EMPRESARIO_INDIVIDUAL, MEI_VAZIO, PESSOA_VAZIA, COM_ID_DE_PESSOA, ID_DE_PESSOA],
)  # fmt: skip
def test_pessoa_nunca_sai_como_empresa_nem_sozinha_nem_no_meio_do_lote(tmp_path, cnpj):
    with _porta(tmp_path) as porta:
        assert empresas.e_empresas(porta, [cnpj]) == {cnpj: False}
        assert empresas.e_empresas(porta, [EMPRESA, cnpj, OUTRA_EMPRESA]) == {
            EMPRESA: True,
            cnpj: False,
            OUTRA_EMPRESA: True,
        }


def test_o_cnpj_inteiro_vale_antes_da_raiz(tmp_path):
    # a filial que a rede conhece como fundo não herda a empresa da raiz
    with _porta(tmp_path) as porta:
        assert empresas.e_empresas(porta, [EMPRESA, FILIAL_QUE_E_FUNDO]) == {
            EMPRESA: True,
            FILIAL_QUE_E_FUNDO: False,
        }


def test_lote_vazio_e_cnpj_repetido(tmp_path):
    with _porta(tmp_path) as porta:
        assert empresas.e_empresas(porta, []) == {}
        assert empresas.e_empresas(porta, [EMPRESA, MEI, EMPRESA]) == {
            EMPRESA: True,
            MEI: False,
        }


def test_o_lote_aceita_qualquer_iteravel(tmp_path):
    with _porta(tmp_path) as porta:
        serie = pd.Series([EMPRESA, MEI])
        assert empresas.e_empresas(porta, serie) == {EMPRESA: True, MEI: False}
        assert empresas.e_empresas(porta, iter([EMPRESA])) == {EMPRESA: True}


@pytest.mark.parametrize("sem", ["entidades", "identificadores"])
def test_sem_uma_das_tabelas_da_rede_o_lote_segue_a_regra_de_antes(tmp_path, sem):
    with _porta(tmp_path, sem=(sem,)) as porta:
        lote = empresas.e_empresas(porta, PERGUNTAS)
        assert lote == {cnpj: _regra_item_a_item(porta, cnpj) for cnpj in PERGUNTAS}
    # sem `entidades` ninguém sai; sem `identificadores`, só quem é pedido pelo próprio id
    assert {c for c, sim in lote.items() if sim} == (
        set() if sem == "entidades" else {ID_DA_EMPRESA}
    )


def test_o_lote_pergunta_a_rede_um_numero_fixo_de_vezes(tmp_path):
    """O porquê do lote: o custo não cresce com o número de candidatas."""
    with _porta(tmp_path) as porta:
        con = _ConexaoQueConta(porta.con)
        porta.con = con  # type: ignore[assignment]
        empresas.e_empresas(porta, PERGUNTAS[:2])
        de_duas = con.consultas
        con.consultas = 0
        empresas.e_empresas(porta, PERGUNTAS)
        assert con.consultas == de_duas <= MAXIMO_DE_CONSULTAS


MAXIMO_DE_CONSULTAS = 3  # as tabelas que existem, os identificadores e as entidades


class _ConexaoQueConta:
    """A conexão da porta, contando as consultas que passam por ela."""

    def __init__(self, con) -> None:
        self._con = con
        self.consultas = 0

    def execute(self, *args, **kwargs):
        self.consultas += 1
        return self._con.execute(*args, **kwargs)

    def __getattr__(self, nome: str):
        return getattr(self._con, nome)


# ---------------------------------------------------------------- propriedade

_IDS = [_id(n) for n in range(1, 5)] + ["P" + "0" * 19 + "1"]
_CNPJS = [EMPRESA, FILIAL_QUE_E_FUNDO, MEI, COM_LETRAS]
_VALORES = [*_CNPJS, *(c[:8] for c in _CNPJS), TICKER]
_SISTEMAS = ["cnpj", "cnpj_raiz", "ticker", "lei", "isin", "emissor", "outro"]
_SIM_NAO_VAZIO = st.sampled_from([True, False, None])
_entidades_sorteadas = st.lists(
    st.tuples(
        st.sampled_from(_IDS),
        st.sampled_from(["empresa", "empresa", "fundo", "pessoa"]),
        _SIM_NAO_VAZIO,
        _SIM_NAO_VAZIO,
    ),
    max_size=8,
)
_identificadores_sorteados = st.lists(
    st.tuples(
        st.sampled_from([*_IDS, ID_AUSENTE]),
        st.sampled_from(_SISTEMAS),
        st.sampled_from(_VALORES),
    ),
    max_size=10,
)
_perguntas_sorteadas = st.lists(
    st.one_of(
        st.sampled_from([*_VALORES, *_IDS, ID_AUSENTE, "11.111.111/0001-91"]),
        st.text(alphabet="0123456789ABEPaf./- ", max_size=22),
    ),
    max_size=12,
)


@settings(max_examples=150, deadline=None)
@given(
    entidades=_entidades_sorteadas,
    identificadores=_identificadores_sorteados,
    perguntas=_perguntas_sorteadas,
)
def test_em_qualquer_rede_o_lote_e_a_regra_item_a_item_dizem_o_mesmo(
    tmp_path_factory, entidades, identificadores, perguntas
):
    pasta = tmp_path_factory.mktemp("rede")
    with _porta(
        pasta, _entidades(entidades), _identificadores(identificadores)
    ) as porta:
        lote = empresas.e_empresas(porta, perguntas)
        assert lote == {cnpj: _regra_item_a_item(porta, cnpj) for cnpj in perguntas}
        for cnpj in perguntas:
            assert empresas.e_empresa(porta, cnpj) is lote[cnpj]


# ---------------------------------------------------------------- com as listas sem pessoa (linha 843)

# os CNPJs das listas de `test_api_externa_e_empresa.py` (empresa, filial, MEI, empresário individual, grupo 4,
# natureza vazia e nula, raiz fora da lista, só no mês velho, inexistente e raiz repetida) e os da rede daqui
PERGUNTAS_DAS_LISTAS = [
    um_a_um.EMPRESA, um_a_um.FILIAL, um_a_um.MEI, um_a_um.EMPRESARIO_INDIVIDUAL, um_a_um.GRUPO_4,
    um_a_um.NATUREZA_VAZIA, um_a_um.NATUREZA_NULA, um_a_um.SEM_EMPRESA, um_a_um.SO_NO_MES_VELHO,
    um_a_um.INEXISTENTE, um_a_um.REPETIDA, "11111111000353", "",
]  # fmt: skip


FECHADA = "15151515000191"  # a empresa fechada: nas listas, fora da rede


def _base_com_listas(tmp_path, empresas_pj=None, estabelecimentos_pj=None):
    base = tmp_path / "base"
    um_a_um._gravar(
        base,
        empresas.LISTA_DE_EMPRESAS,
        um_a_um._empresas(*([empresas_pj] if empresas_pj else [])),
    )
    um_a_um._gravar(
        base,
        empresas.LISTA_DE_ESTABELECIMENTOS,
        um_a_um._estabelecimentos(
            *([estabelecimentos_pj] if estabelecimentos_pj else [])
        ),
    )
    return base


def _item_a_item(porta: Porta, perguntas) -> dict[str, bool]:
    return {cnpj: empresas.e_empresa(porta, cnpj) for cnpj in perguntas}


def test_sem_a_rede_o_lote_decide_pelas_listas_como_o_e_empresa(tmp_path):
    with Porta(_base_com_listas(tmp_path)) as porta:
        assert "entidades" not in views(porta.con)
        lote = empresas.e_empresas(porta, PERGUNTAS_DAS_LISTAS)
        assert lote == _item_a_item(porta, PERGUNTAS_DAS_LISTAS)
    # escrito à mão: só a empresa e a filial das duas listas, nenhuma pessoa
    assert {cnpj for cnpj, sim in lote.items() if sim} == {
        um_a_um.EMPRESA,
        um_a_um.FILIAL,
    }


def test_com_a_rede_e_as_listas_o_lote_responde_o_mesmo_que_o_e_empresa(tmp_path):
    """A rede decide o que conhece (pessoa e conflito não caem para as listas); o resto, as listas."""
    base = _base_com_listas(
        tmp_path,
        [
            *um_a_um.EMPRESAS,
            (MEI[:8], "2062", "2026-10"),
            (EM_DUAS_ENTIDADES[:8], "2062", "2026-10"),
            (FECHADA[:8], "2062", "2026-10"),
        ],
        [
            *um_a_um.ESTABELECIMENTOS,
            (MEI, "2026-10"),
            (EM_DUAS_ENTIDADES, "2026-10"),
            (FECHADA, "2026-10"),
        ],
    )
    perguntas = [*PERGUNTAS_DAS_LISTAS, *PERGUNTAS, FECHADA]
    with Porta(
        base, extras={"entidades": _entidades(), "identificadores": _identificadores()}
    ) as porta:
        lote = empresas.e_empresas(porta, perguntas)
        assert lote == _item_a_item(porta, perguntas)
    # o MEI da rede e o conflito estão nas listas de mentira, mas a rede os conhece: não
    # (e a filial das listas é o fundo da rede daqui: vale a rede)
    assert lote[MEI] is lote[EM_DUAS_ENTIDADES] is lote[um_a_um.FILIAL] is False
    # a empresa fechada que a rede não conhece sai pelas listas, e o que a rede conhece como empresa também
    assert lote[FECHADA] is lote[OUTRA_EMPRESA] is True


def test_o_lote_com_as_listas_pergunta_um_numero_fixo_de_vezes(tmp_path):
    with Porta(_base_com_listas(tmp_path)) as porta:
        con = _ConexaoQueConta(porta.con)
        porta.con = con  # type: ignore[assignment]
        empresas.e_empresas(porta, PERGUNTAS_DAS_LISTAS[:2])
        de_duas = con.consultas
        con.consultas = 0
        empresas.e_empresas(porta, PERGUNTAS_DAS_LISTAS)
        assert con.consultas == de_duas <= MAXIMO_COM_AS_LISTAS


MAXIMO_COM_AS_LISTAS = (
    5  # as tabelas que existem, o mês de cada lista e uma consulta a cada lista
)


@settings(max_examples=100, deadline=None)
@given(
    empresas_pj=st.lists(
        st.tuples(
            st.sampled_from([c[:8] for c in PERGUNTAS_DAS_LISTAS if c]),
            st.sampled_from(["2062", "2054", "2135", "4120", "", "  ", None]),
            st.sampled_from(["2026-09", "2026-10"]),
        ),
        min_size=1,
        max_size=8,
    ),
    estabelecimentos_pj=st.lists(
        st.tuples(
            st.sampled_from([c for c in PERGUNTAS_DAS_LISTAS if c]),
            st.sampled_from(["2026-09", "2026-10"]),
        ),
        min_size=1,
        max_size=8,
    ),
)
def test_em_quaisquer_listas_o_lote_e_o_e_empresa_dizem_o_mesmo(
    tmp_path_factory, empresas_pj, estabelecimentos_pj
):
    base = _base_com_listas(
        tmp_path_factory.mktemp("listas"), empresas_pj, estabelecimentos_pj
    )
    with Porta(base) as porta:
        assert empresas.e_empresas(porta, PERGUNTAS_DAS_LISTAS) == _item_a_item(
            porta, PERGUNTAS_DAS_LISTAS
        )


# ---------------------------------------------------------------- identificador sem entidade

SEM_ID = "74747474000191"  # o identificador existe, mas o `id_entidade` dele está vazio


@pytest.mark.parametrize("com_as_listas", [False, True])
def test_identificador_com_id_entidade_nulo_nao_e_empresa_e_nao_cai_para_as_listas(
    tmp_path, com_as_listas
):
    """A rede menciona o CNPJ sem dizer de quem é: na dúvida, não; nem as listas o salvam."""
    base = (
        _base_com_listas(
            tmp_path, [(SEM_ID[:8], "2062", "2026-10")], [(SEM_ID, "2026-10")]
        )
        if com_as_listas
        else tmp_path
    )
    identificadores = _identificadores(
        [*IDENTIFICADORES, (None, "cnpj_raiz", SEM_ID[:8])]
    )
    with Porta(
        base, extras={"entidades": _entidades(), "identificadores": identificadores}
    ) as porta:
        assert empresas.e_empresa(porta, SEM_ID) is False
        assert empresas.e_empresas(porta, [EMPRESA, SEM_ID]) == {
            EMPRESA: True,
            SEM_ID: False,
        }
