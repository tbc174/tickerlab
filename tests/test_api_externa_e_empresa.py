"""A trava de pessoa da API externa (`empresas.e_empresa`) com a rede e sem ela (pelas listas sem pessoa).

Quando a rede conhece o CNPJ, decide ela, e pessoa ou conflito nela não cai para as listas (os casos dela
também estão em `test_api_externa_empresas.py`). O que ela não conhece, e qualquer CNPJ sem a rede, decidem
as listas sem pessoa da Receita do retrato mais novo: MEI, empresário individual, grupo 4, natureza
vazia, raiz ausente e estabelecimento ausente dão não.
"""

from datetime import date

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from base.porta import Porta
from src.api_externa.conjuntos import empresas

EMPRESA = "11111111000191"
FILIAL = "11111111000272"
MEI = "33333333000191"
EMPRESARIO_INDIVIDUAL = "44444444000191"
GRUPO_4 = "45454545000191"
NATUREZA_VAZIA = "55555555000191"
NATUREZA_NULA = "56565656000191"
SEM_EMPRESA = "66666666000191"  # o estabelecimento está na lista, a raiz não (lista quebrada: na dúvida, não)
SO_NO_MES_VELHO = "77777777000191"  # saiu da lista no retrato mais novo
INEXISTENTE = "88888888000191"
REPETIDA = "99999999000191"  # a raiz duas vezes no mesmo retrato
VELHO, NOVO = "2026-09", "2026-10"

# fmt: off
# raiz, natureza, mês: a lista de empresas sem pessoa (`cnpj_empresas_pj`). O empresário individual e o grupo
# 4 nunca deveriam estar nela; estão aqui para provar que a trava não confia só na montagem.
EMPRESAS = [
    (EMPRESA[:8], "2062", VELHO), (EMPRESA[:8], "2054", NOVO),
    (MEI[:8], "2062", NOVO),  # o MEI tem natureza de empresa: quem o tira é a lista de estabelecimentos
    (EMPRESARIO_INDIVIDUAL[:8], "2135", NOVO),
    (GRUPO_4[:8], "4120", NOVO),
    (NATUREZA_VAZIA[:8], "", NOVO),
    (NATUREZA_NULA[:8], None, NOVO),
    (SO_NO_MES_VELHO[:8], "2062", VELHO),
    (REPETIDA[:8], "2062", NOVO), (REPETIDA[:8], "2062", NOVO),
]
# cnpj, mês: a lista de estabelecimentos sem MEI (`cnpj_estabelecimentos_pj`)
ESTABELECIMENTOS = [
    (EMPRESA, VELHO), (EMPRESA, NOVO), (FILIAL, NOVO),
    (EMPRESARIO_INDIVIDUAL, NOVO), (GRUPO_4, NOVO),
    (NATUREZA_VAZIA, NOVO), (NATUREZA_NULA, NOVO), (SEM_EMPRESA, NOVO),
    (SO_NO_MES_VELHO, VELHO), (REPETIDA, NOVO),
]
# fmt: on


def _empresas(linhas=EMPRESAS) -> pd.DataFrame:
    tabela = pd.DataFrame(
        linhas, columns=["cnpj_basico", "natureza_juridica", "mes_do_retrato"]
    )
    return tabela.assign(razao_social="X S.A.", disponivel_em=date(2026, 10, 31))


def _estabelecimentos(linhas=ESTABELECIMENTOS) -> pd.DataFrame:
    tabela = pd.DataFrame(linhas, columns=["cnpj", "mes_do_retrato"])
    return tabela.assign(
        cnpj_basico=tabela["cnpj"].str[:8],
        situacao_cadastral="02",
        disponivel_em=date(2026, 10, 31),
    )


def _gravar(base, tabela: str, linhas: pd.DataFrame) -> None:
    pasta = base / tabela
    pasta.mkdir(parents=True, exist_ok=True)
    for prefixo, parte in linhas.groupby(linhas["cnpj_basico"].str[:2]):
        parte.to_parquet(pasta / f"{prefixo}.parquet", index=False)


def _gravar_rede(base, entidades: list[tuple[str, str, str, bool, bool]]) -> None:
    """(id, raiz, tipo, mei, trata_como_pessoa) de cada entidade, achada pela raiz."""
    rede = pd.DataFrame(
        entidades,
        columns=["id_entidade", "valor", "tipo", "mei", "trata_como_pessoa"],
    )
    (base / "rede").mkdir(parents=True, exist_ok=True)
    rede[["id_entidade", "tipo", "mei", "trata_como_pessoa"]].assign(
        nome=None,
        natureza_juridica="2062",
        natureza_fonte="receita",
        fontes="cvm-cadastro",
        publico_em=date(2020, 1, 1),
    ).to_parquet(base / "rede" / "entidades.parquet", index=False)
    rede[["id_entidade", "valor"]].assign(
        sistema="cnpj_raiz",
        desde=None,
        ate=None,
        publico_em=date(2020, 1, 1),
        regra=2,
        conferido_por="regra",
        fontes="cvm-cadastro",
    ).to_parquet(base / "rede" / "identificadores.parquet", index=False)


@pytest.fixture
def listas(tmp_path):
    base = tmp_path / "base"
    _gravar(base, empresas.LISTA_DE_EMPRESAS, _empresas())
    _gravar(base, empresas.LISTA_DE_ESTABELECIMENTOS, _estabelecimentos())
    return base


@pytest.mark.parametrize("cnpj", [EMPRESA, FILIAL])
def test_sem_a_rede_a_empresa_das_duas_listas_e_empresa(listas, cnpj):
    assert empresas.e_empresa(Porta(listas), cnpj)


@pytest.mark.parametrize(
    "cnpj",
    [
        MEI,
        EMPRESARIO_INDIVIDUAL,
        GRUPO_4,
        NATUREZA_VAZIA,
        NATUREZA_NULA,
        SEM_EMPRESA,
        SO_NO_MES_VELHO,
        INEXISTENTE,
        REPETIDA,
        "11111111000353",  # filial que não está na lista: não basta a raiz ser de empresa
    ],
)
def test_sem_a_rede_quem_nao_e_so_empresa_nas_listas_nao_e(listas, cnpj):
    assert not empresas.e_empresa(Porta(listas), cnpj)


@pytest.mark.parametrize(
    "falta", [empresas.LISTA_DE_EMPRESAS, empresas.LISTA_DE_ESTABELECIMENTOS]
)
def test_sem_a_rede_e_sem_uma_das_listas_ninguem_e_empresa(tmp_path, falta):
    base = tmp_path / "base"
    if falta != empresas.LISTA_DE_EMPRESAS:
        _gravar(base, empresas.LISTA_DE_EMPRESAS, _empresas())
    if falta != empresas.LISTA_DE_ESTABELECIMENTOS:
        _gravar(base, empresas.LISTA_DE_ESTABELECIMENTOS, _estabelecimentos())
    assert not empresas.e_empresa(Porta(base), EMPRESA)


def test_sem_a_rede_listas_de_meses_diferentes_nao_decidem(tmp_path):
    # a de empresas já tem o mês novo e a de estabelecimentos não: o MEI do mês novo não sairia dela
    base = tmp_path / "base"
    _gravar(base, empresas.LISTA_DE_EMPRESAS, _empresas())
    _gravar(
        base,
        empresas.LISTA_DE_ESTABELECIMENTOS,
        _estabelecimentos([(EMPRESA, VELHO), (MEI, VELHO)]),
    )
    porta = Porta(base)
    assert not empresas.e_empresa(porta, EMPRESA)
    assert not empresas.e_empresa(porta, MEI)


def test_sem_a_rede_nem_as_listas_ninguem_e_empresa(tmp_path):
    (tmp_path / "base").mkdir()
    assert not empresas.e_empresa(Porta(tmp_path / "base"), EMPRESA)


def test_com_a_rede_vale_a_rede_e_nao_as_listas(listas):
    # a rede trata a EMPRESA como pessoa e não conhece a FILIAL de outra raiz; as listas diriam sim às duas
    _gravar_rede(
        listas,
        [
            ("E" + "1" * 20, EMPRESA[:8], "empresa", False, True),
            ("E" + "3" * 20, MEI[:8], "empresa", False, False),
        ],
    )
    porta = Porta(listas)
    assert not empresas.e_empresa(porta, EMPRESA)
    assert not empresas.e_empresa(porta, FILIAL)
    # e o que a rede diz que é empresa continua sendo, como hoje, mesmo fora das listas
    assert empresas.e_empresa(porta, MEI)


OUTRA = "E" + "3" * 20  # uma companhia que a rede conhece, de outra raiz


def test_com_a_rede_a_empresa_fechada_que_ela_nao_conhece_cai_nas_listas(listas):
    # a rede (a do VPS, linha 843) só tem as companhias da CVM e dos reguladores: a fechada vem das listas
    _gravar_rede(listas, [(OUTRA, "12121212", "empresa", False, False)])
    porta = Porta(listas)
    assert empresas.e_empresa(porta, EMPRESA)
    assert empresas.e_empresa(porta, FILIAL)


@pytest.mark.parametrize(
    "cnpj",
    [
        MEI,
        EMPRESARIO_INDIVIDUAL,
        GRUPO_4,
        NATUREZA_VAZIA,
        SEM_EMPRESA,
        SO_NO_MES_VELHO,
        INEXISTENTE,
        REPETIDA,
    ],
)
def test_com_a_rede_quem_ela_nao_conhece_e_as_listas_negam_nao_e(listas, cnpj):
    _gravar_rede(listas, [(OUTRA, "12121212", "empresa", False, False)])
    assert not empresas.e_empresa(Porta(listas), cnpj)


def test_com_a_rede_a_companhia_que_ela_conhece_e_empresa_mesmo_fora_das_listas(
    listas,
):
    _gravar_rede(listas, [(OUTRA, INEXISTENTE[:8], "empresa", False, False)])
    assert empresas.e_empresa(Porta(listas), INEXISTENTE)


@pytest.mark.parametrize(
    "entidade",
    [
        ("E" + "1" * 20, EMPRESA[:8], "empresa", False, True),  # tratada como pessoa
        ("E" + "1" * 20, EMPRESA[:8], "empresa", True, False),  # MEI
        (
            "E" + "1" * 20,
            EMPRESA[:8],
            "empresa",
            False,
            None,
        ),  # marca vazia: na dúvida, pessoa
        ("E" + "1" * 20, EMPRESA[:8], "empresa", None, False),
        ("P" + "1" * 20, EMPRESA[:8], "pessoa", False, False),  # id de pessoa
        (
            "E" + "1" * 20,
            EMPRESA[:8],
            "fundo",
            False,
            False,
        ),  # conhecida, mas não é empresa
    ],
)
def test_pessoa_na_rede_nao_e_empresa_mesmo_nas_listas(listas, entidade):
    # a EMPRESA está nas duas listas; a rede a conhece e diz que não: não cai para as listas
    _gravar_rede(listas, [entidade])
    porta = Porta(listas)
    assert not empresas.e_empresa(porta, EMPRESA)
    assert not empresas.e_empresa(porta, FILIAL)  # a filial da mesma raiz também


def test_conflito_na_rede_nao_cai_para_as_listas(listas):
    # a mesma raiz em duas entidades: a rede conhece o CNPJ, mas não sabe qual é; na dúvida, não
    _gravar_rede(
        listas,
        [
            ("E" + "1" * 20, EMPRESA[:8], "empresa", False, False),
            ("E" + "2" * 20, EMPRESA[:8], "empresa", False, False),
        ],
    )
    assert not empresas.e_empresa(Porta(listas), EMPRESA)


def test_com_a_rede_sem_as_listas_quem_ela_nao_conhece_nao_e(tmp_path):
    base = tmp_path / "base"
    _gravar_rede(base, [(OUTRA, "12121212", "empresa", False, False)])
    porta = Porta(base)
    assert not empresas.e_empresa(porta, EMPRESA)
    assert empresas.e_empresa(porta, "12121212000191")


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    natureza=st.one_of(
        st.none(),
        st.sampled_from(["", " ", "2135", "4000", "4120", "2062", "2054", "3999"]),
        st.text(alphabet="0123456789", min_size=4, max_size=4),
    )
)
def test_sem_a_rede_so_a_natureza_informada_e_que_nao_e_de_pessoa_passa(
    tmp_path_factory, natureza
):
    base = tmp_path_factory.mktemp("base")
    _gravar(
        base, empresas.LISTA_DE_EMPRESAS, _empresas([(EMPRESA[:8], natureza, NOVO)])
    )
    _gravar(
        base, empresas.LISTA_DE_ESTABELECIMENTOS, _estabelecimentos([(EMPRESA, NOVO)])
    )
    limpa = (natureza or "").strip()
    pessoa = limpa == "2135" or limpa.startswith("4")
    assert empresas.e_empresa(Porta(base), EMPRESA) == (bool(limpa) and not pessoa)


def test_rede_sem_identificadores_nao_cai_para_as_listas(listas):
    # carga parcial da rede (entidades sem identificadores): não dá para saber quem ela conhece; na dúvida, não
    _gravar_rede(listas, [("E" + "1" * 20, EMPRESA[:8], "empresa", False, True)])
    (listas / "rede" / "identificadores.parquet").unlink()
    assert not empresas.e_empresa(Porta(listas), EMPRESA)
