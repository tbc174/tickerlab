"""O quadro de sócios pessoa jurídica do dia (`conjuntos/socios_pj.py`), o bloco de sócios da análise completa.

Base de mentira, sem internet: a do perfil (`test_api_externa_por_cnpj_ficha.py`) com as entradas e saídas de
sócio PJ e a lista sem pessoa da Receita com as sócias e as participadas. Riscos: pessoa (a sócia fora da lista
sem pessoa, ou com natureza de empresário, não sai, nem pela raiz) e olhar o futuro (a entrada publicada depois
do dia não sai, e cortar o futuro não muda o passado).
"""

from datetime import date

import pandas as pd
import pytest

from base.porta import Porta
from src.api_externa.conjuntos import compradores, empresas, socios_pj
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_por_cnpj_ficha as ficha_de_mentira

EMPRESA = empresas_de_mentira.EMPRESA
RAIZ = EMPRESA[:8]
DIA = ficha_de_mentira.DIA  # 30/06/2025
HOLDING, CONTROLADA, VELHA, SEM_LISTA, EMPRESARIO, FUTURA = (
    "12000004",
    "12000009",
    "12000005",
    "12000006",
    "12000008",
    "12000007",
)
NOMES = {
    HOLDING: ("HOLDING LTDA", "2062"),
    CONTROLADA: ("CONTROLADA LTDA", "2062"),
    VELHA: ("VELHA LTDA", "2062"),
    EMPRESARIO: (
        "EMPRESARIO DE MENTIRA",
        "2135",
    ),  # natureza de empresário individual: não é empresa
    FUTURA: ("FUTURA LTDA", "2062"),
}  # SEM_LISTA fica fora da lista sem pessoa
MESES = (
    ("2023-05", "2023-05-21"),
    ("2025-06", "2025-06-21"),
    ("2025-07", "2025-07-21"),
)
# fmt: off
ENTRADAS = [
    # sócia, empresa, data de entrada, mês do retrato, disponível em, movimento
    (HOLDING, RAIZ, "2010-05-01", "2023-05", "2023-06-30", "entrou"),
    (RAIZ, CONTROLADA, "2020-01-01", "2023-05", "2023-06-30", "entrou"),  # a empresa é sócia da controlada
    (VELHA, RAIZ, "2018-01-01", "2023-05", "2023-06-30", "entrou"),
    (VELHA, RAIZ, "2018-01-01", "2024-05", "2024-06-30", "saiu"),  # saiu antes do dia: não está no quadro
    (SEM_LISTA, RAIZ, "2024-01-01", "2024-02", "2024-03-31", "entrou"),  # fora da lista sem pessoa
    (EMPRESARIO, RAIZ, "2024-02-01", "2024-03", "2024-04-30", "entrou"),  # natureza de empresário
    (RAIZ, RAIZ, "2010-05-01", "2023-05", "2023-06-30", "entrou"),  # sócia de si mesma não conta
    (FUTURA, RAIZ, "2025-07-01", "2025-07", "2025-08-31", "entrou"),  # só pública depois do dia
]
# fmt: on


def _entradas(linhas=ENTRADAS) -> pd.DataFrame:
    tabela = pd.DataFrame(
        linhas,
        columns=["raiz_socio_pj", "cnpj_basico", "data_entrada", "mes_do_retrato", "disponivel_em", "movimento"],
    )  # fmt: skip
    tabela["data_entrada"] = pd.to_datetime(tabela["data_entrada"]).dt.date
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
    return tabela.assign(qualificacao="22", **empresas_de_mentira._CARIMBOS)


def _lista() -> list[tuple]:
    """A lista sem pessoa do perfil, com as sócias e as participadas nos mesmos meses."""
    extras = [
        (raiz, nome, natureza, "05", mes, disponivel)
        for mes, disponivel in MESES
        for raiz, (nome, natureza) in NOMES.items()
    ]
    return [*empresas_de_mentira.LISTA_DO_NOME, *extras]


def gravar_socios(pasta, entradas: pd.DataFrame | None = None) -> None:
    """Grava as entradas de sócio PJ e a lista sem pessoa ampliada numa base do perfil."""
    (pasta / compradores.ENTRADAS).mkdir(parents=True, exist_ok=True)
    (entradas if entradas is not None else _entradas()).to_parquet(
        pasta / compradores.ENTRADAS / "parte.parquet", index=False
    )
    empresas_de_mentira._lista_pj(_lista()).to_parquet(
        pasta / empresas.LISTA_DE_EMPRESAS / "00.parquet", index=False
    )


def base_com_socios(tmp_path):
    """A base do perfil (cadastro e entregas) com o quadro de sócios PJ."""
    pasta = ficha_de_mentira._base(tmp_path, ficha_de_mentira._rotulos())
    gravar_socios(pasta)
    return pasta


@pytest.fixture
def pasta(tmp_path):
    return base_com_socios(tmp_path)


def _tudo(_fonte: str, _campo: str, _derivado: bool) -> bool:
    return True


def _ler(pasta, cnpj=EMPRESA, dia=DIA, permitido=_tudo, linhas=20):
    with Porta(pasta) as porta:
        return socios_pj.LeitorDeSociosPj(porta, permitido, linhas).socios(cnpj, dia)


def _raizes(corpo: dict, lista: str) -> list[str]:
    return [item["raiz_do_cnpj"] for item in corpo[lista]]


def test_quadro_do_dia_traz_so_as_empresas_da_lista_sem_pessoa(pasta):
    servido = _ler(pasta)
    assert servido is not None
    assert _raizes(servido.corpo, socios_pj.SOCIAS) == [HOLDING]
    assert _raizes(servido.corpo, socios_pj.PARTICIPACOES) == [CONTROLADA]
    assert servido.linhas == 2
    assert servido.fontes == {compradores.RECEITA}
    socia = servido.corpo[socios_pj.SOCIAS][0]
    assert socia["razao_social"]["valor"] == "HOLDING LTDA"
    assert socia["razao_social"]["fonte"] == compradores.RECEITA
    assert socia["data_entrada"]["valor"] == "2010-05-01"
    assert socia["data_entrada"]["publico_em"] == "2023-06-30"


def test_quem_esta_fora_da_lista_ou_tem_natureza_de_empresario_nao_sai_nem_pela_raiz(
    pasta,
):
    texto = str(_ler(pasta).corpo)  # type: ignore[union-attr]
    for raiz in (SEM_LISTA, EMPRESARIO):
        assert raiz not in texto
    assert "EMPRESARIO DE MENTIRA" not in texto


def test_socia_que_saiu_antes_do_dia_nao_esta_no_quadro(pasta):
    assert VELHA not in _raizes(_ler(pasta).corpo, socios_pj.SOCIAS)  # type: ignore[union-attr]


def test_socia_que_saiu_depois_do_dia_ainda_esta_no_quadro_daquele_dia(pasta):
    corpo = _ler(pasta, dia=date(2024, 1, 31)).corpo  # type: ignore[union-attr]
    assert set(_raizes(corpo, socios_pj.SOCIAS)) == {HOLDING, VELHA}


def test_entrada_publicada_depois_do_dia_nao_sai_e_depois_sai(pasta):
    assert FUTURA not in str(_ler(pasta).corpo)  # type: ignore[union-attr]
    depois = _ler(pasta, dia=date(2025, 9, 30)).corpo  # type: ignore[union-attr]
    assert _raizes(depois, socios_pj.SOCIAS) == [FUTURA, HOLDING]


def test_cortar_o_futuro_nao_muda_o_passado(tmp_path, pasta):
    sem_futuro = ficha_de_mentira._base(tmp_path / "sem", ficha_de_mentira._rotulos())
    gravar_socios(
        sem_futuro, _entradas([e for e in ENTRADAS if e[4] <= DIA.isoformat()])
    )
    assert _ler(sem_futuro).corpo == _ler(pasta).corpo  # type: ignore[union-attr]


def test_sem_a_data_de_entrada_ou_o_nome_liberados_o_bloco_nao_sai(pasta):
    for negado in socios_pj.CAMPOS:

        def permitido(fonte, campo, _derivado, negado=negado):
            return (fonte, campo) != negado

        assert _ler(pasta, permitido=permitido) is None


@pytest.mark.parametrize(
    "cnpj",
    [
        empresas_de_mentira.MEI,
        empresas_de_mentira.EMPRESARIO_INDIVIDUAL,
        empresas_de_mentira.INEXISTENTE,
    ],
)
def test_cnpj_que_nao_e_de_empresa_nao_tem_quadro(pasta, cnpj):
    assert _ler(pasta, cnpj=cnpj) is None


def test_base_sem_a_tabela_de_entradas_nao_tem_quadro(tmp_path):
    assert _ler(ficha_de_mentira._base(tmp_path, ficha_de_mentira._rotulos())) is None


def test_lista_maior_que_o_limite_sai_cortada_com_as_entradas_mais_novas(pasta):
    servido = _ler(pasta, dia=date(2025, 9, 30), linhas=1)
    assert servido is not None
    assert servido.corpo["cortada"] is True
    assert _raizes(servido.corpo, socios_pj.SOCIAS) == [FUTURA]
    assert servido.linhas == 2  # uma sócia e uma participação


def test_cnpj_invalido_e_erro_de_quem_chama(pasta):
    with pytest.raises(ValueError, match="CNPJ inválido"):
        _ler(pasta, cnpj="123")
