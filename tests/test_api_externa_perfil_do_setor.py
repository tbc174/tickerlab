"""O perfil de um setor por CNAE (linha 903, tela de setor): só contagens, só pessoa jurídica.

Base de mentira, sem internet; as raízes são de ninguém. O portão é o de verdade (`DIREITOS_DA_API_EXTERNA`,
pelo `permitido_na_tela` da tela do analista), com as tabelas prontas dadas no teste (D10). Riscos: o número não
bater com o `empresas_ativas` da lista de compradores (a tela mostra os dois), sair alguma empresa (só contagem),
olhar o futuro (retrato ainda não público, abertura depois do dia) e o bloco barrado sair como zero.
"""

import dataclasses
from datetime import date

import pandas as pd
import pytest

from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.analista import leitura
from src.api_externa.conjuntos import compradores
from src.api_externa.conjuntos import perfil_do_setor as perfil

SETOR, CLASSE, OUTRO = "6201501", "62015", "6201502"
DIA = date(2026, 11, 10)
ANTES_DO_RETRATO_DE_OUTUBRO = date(2026, 10, 20)
CARIMBOS = {
    "origem_sha256": "0" * 64,
    "montado_em": pd.Timestamp("2026-11-05", tz="UTC"),
    "versao_do_codigo": "teste",
}
SP_E_RJ, SO_SP, BAIXADA, FORA, NOVA, FILIAL_NOVA, SUBCLASSE, DATA_FUTURA = (
    "21000001", "21000002", "21000003", "21000004", "21000005", "21000006", "21000007", "21000008",
)  # fmt: skip
# fmt: off
LINHAS = [
    # raiz, ordem do estabelecimento, situação, abertura, cnae, uf
    (SP_E_RJ, "0001", "02", "2010-03-01", SETOR, "SP"),
    (SP_E_RJ, "0002", "02", "2020-05-01", SETOR, "RJ"),   # a mesma empresa conta em SP e no RJ
    (SP_E_RJ, "0003", "08", "2018-01-01", SETOR, "MG"),   # filial baixada: MG não conta como ativa
    (SO_SP, "0001", "02", "2019-07-01", SETOR, "SP"),
    (BAIXADA, "0001", "08", "2017-02-01", SETOR, "SP"),   # baixada: não é ativa, mas abriu em 2017
    (FORA, "0001", "02", "2018-01-01", "4711302", "SP"),  # fora do setor
    (FILIAL_NOVA, "0001", "02", "2012-01-01", "4711302", "PR"),  # a matriz é de outro CNAE
    (FILIAL_NOVA, "0002", "02", "2022-08-01", SETOR, "PR"),      # a filial do setor abriu em 2022
    (SUBCLASSE, "0001", "02", "2021-04-01", OUTRO, "BA"),  # mesma classe, outra subclasse
]
NOVA_EM_OUTUBRO = (NOVA, "0001", "02", "2026-10-01", SETOR, "SP")  # só no retrato de outubro
# no retrato de outubro, com início de atividade depois do dia do pedido (a Receita aceita data futura)
INICIO_FUTURO = (DATA_FUTURA, "0001", "08", "2026-11-20", SETOR, "SP")
# fmt: on


def _retrato(linhas, mes: str, disponivel_em: str) -> pd.DataFrame:
    tabela = pd.DataFrame(
        linhas,
        columns=["cnpj_basico", "ordem", "situacao_cadastral", "data_inicio_atividade", "cnae_principal", "uf"],
    )  # fmt: skip
    tabela["cnpj"] = tabela["cnpj_basico"] + tabela["ordem"] + "00"
    tabela["matriz"] = tabela["ordem"] == "0001"
    tabela["municipio"] = "7107"
    tabela["data_inicio_atividade"] = pd.to_datetime(tabela["data_inicio_atividade"])
    tabela["mes_do_retrato"] = mes
    tabela["disponivel_em"] = pd.Timestamp(disponivel_em).date()
    return tabela.drop(columns="ordem").assign(**CARIMBOS)


def _empresas() -> pd.DataFrame:
    raizes = sorted({linha[0] for linha in [*LINHAS, NOVA_EM_OUTUBRO, INICIO_FUTURO]})
    linhas = [
        (raiz, "EMPRESA DE TESTE LTDA", mes, pd.Timestamp(disponivel).date())
        for mes, disponivel in (("2026-09", "2026-09-30"), ("2026-10", "2026-10-31"))
        for raiz in raizes
    ]
    tabela = pd.DataFrame(
        linhas,
        columns=["cnpj_basico", "razao_social", "mes_do_retrato", "disponivel_em"],
    )
    return tabela.assign(
        natureza_juridica="2062",
        porte="demais",
        capital_social=1_000_000.0,
        n_estabelecimentos=1,
        **CARIMBOS,
    )


def _gravar(arquivo, tabela: pd.DataFrame) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(arquivo, index=False)


@pytest.fixture
def base(tmp_path):
    pasta = tmp_path / "base"
    estabelecimentos = pd.concat([
        _retrato(LINHAS, "2026-09", "2026-09-30"),
        _retrato([*LINHAS, NOVA_EM_OUTUBRO, INICIO_FUTURO], "2026-10", "2026-10-31"),
    ])  # fmt: skip
    _gravar(pasta / compradores.ESTABELECIMENTOS / "21.parquet", estabelecimentos)
    _gravar(pasta / compradores.EMPRESAS / "21.parquet", _empresas())
    return pasta


@pytest.fixture
def porta(base, banco):
    return Porta(base, banco)


def _regras(*prontas: str) -> portao.Regras:
    """As regras de verdade, com as tabelas dadas prontas (provas do D10) no dia do teste."""
    prova = Prova(DIA, "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in prontas},
    )


PRONTAS = (compradores.ESTABELECIMENTOS, compradores.EMPRESAS)


def _permitido(*prontas: str):
    return leitura.permitido_na_tela(compradores.CONJUNTO, DIA, _regras(*prontas))


def _perfil(porta, cnae: str = SETOR, dia: date = DIA, permitido=None):
    leitor = perfil.LeitorDoPerfilDoSetor(porta, permitido or _permitido(*PRONTAS))
    return leitor.perfil(perfil.cnae_do_parametro(cnae), dia)


# ---------------------------------------------------------------- o que sai


def test_o_perfil_conta_ativas_por_uf_e_aberturas(porta):
    servido = _perfil(porta)
    assert servido is not None
    corpo = servido.corpo
    # ativas: SP_E_RJ, SO_SP, FILIAL_NOVA e a NOVA de outubro (a BAIXADA e a FORA não)
    assert corpo["empresas_ativas"] == 4
    assert corpo["por_uf"] == [
        {"uf": "SP", "empresas_ativas": 3},
        {"uf": "PR", "empresas_ativas": 1},
        {"uf": "RJ", "empresas_ativas": 1},
    ]
    aberturas = {item["ano"]: item["aberturas"] for item in corpo["aberturas_por_ano"]}
    assert list(aberturas) == list(
        range(2016, 2027)
    )  # os 10 anos antes do dia e o ano do dia
    # a mais antiga de cada empresa no CNAE: SP_E_RJ 2010 (antes da janela), BAIXADA 2017, SO_SP 2019,
    # FILIAL_NOVA 2022 (a filial do setor, não a matriz de 2012), NOVA 2026
    assert {ano: n for ano, n in aberturas.items() if n} == {
        2017: 1,
        2019: 1,
        2022: 1,
        2026: 1,
    }
    assert aberturas[2016] == 0  # zero de verdade: a tabela foi lida
    assert corpo["blocos_nao_disponiveis"] == []
    assert corpo["fonte"] == "rfb-cnpj"
    assert corpo["data_do_retrato"] == "2026-10"
    assert corpo["publico_em"] == "2026-10-31"
    assert corpo["como_era_em"] == "2026-11-10"
    assert corpo["cnae_principal"] == SETOR
    assert servido.fontes == {"rfb-cnpj"}


def test_so_contagens_sem_nenhuma_empresa(porta):
    corpo = _perfil(porta).corpo
    assert set(corpo) == {
        "como_era_em", "cnae_principal", "fonte", "data_do_retrato", "publico_em", "empresas_ativas",
        "por_uf", "aberturas_por_ano", "blocos_nao_disponiveis", "limites",
    }  # fmt: skip
    texto = repr(corpo)
    for raiz in (SP_E_RJ, SO_SP, BAIXADA, FILIAL_NOVA, NOVA):
        assert raiz not in texto
    assert "EMPRESA DE TESTE" not in texto


def test_o_total_e_cada_uf_batem_com_a_lista_de_compradores(porta):
    """A tela mostra o perfil e a lista lado a lado: o total e a UF têm de dar o mesmo número."""
    corpo = _perfil(porta).corpo
    mes = compradores.mes_do_retrato(porta, DIA)
    assert mes is not None
    consulta = compradores._Consulta(porta, mes, DIA, DIA)

    def da_lista(uf: str | None) -> int:  # o `empresas_ativas` da lista é `len(setor)`
        return len(consulta.setor(SETOR, uf))

    assert corpo["empresas_ativas"] == da_lista(None)
    for item in corpo["por_uf"]:
        assert item["empresas_ativas"] == da_lista(item["uf"])


def test_a_classe_junta_as_subclasses(porta):
    corpo = _perfil(porta, CLASSE).corpo
    assert (
        corpo["empresas_ativas"] == 5
    )  # as 4 da subclasse e a SUBCLASSE, de outra subclasse da classe
    assert {"uf": "BA", "empresas_ativas": 1} in corpo["por_uf"]
    assert corpo["cnae_principal"] == CLASSE


def test_setor_sem_empresa_sai_com_zero_e_as_listas_vazias(porta):
    corpo = _perfil(porta, "0111301").corpo
    assert corpo["empresas_ativas"] == 0
    assert corpo["por_uf"] == []
    assert all(item["aberturas"] == 0 for item in corpo["aberturas_por_ano"])


def test_o_por_uf_desempata_pela_uf(porta):
    ufs = [item["uf"] for item in _perfil(porta).corpo["por_uf"]]
    assert ufs == ["SP", "PR", "RJ"]  # PR e RJ empatam em 1: ordem alfabética


# ---------------------------------------------------------------- sem olhar o futuro


def test_antes_do_retrato_de_outubro_vale_o_de_setembro(porta):
    corpo = _perfil(porta, dia=ANTES_DO_RETRATO_DE_OUTUBRO).corpo
    assert corpo["data_do_retrato"] == "2026-09"
    assert corpo["publico_em"] == "2026-09-30"
    assert corpo["empresas_ativas"] == 3  # sem a NOVA
    aberturas = {item["ano"]: item["aberturas"] for item in corpo["aberturas_por_ano"]}
    assert aberturas[2026] == 0
    assert corpo["como_era_em"] == "2026-10-20"


def test_abertura_depois_do_dia_nao_conta(porta):
    # a DATA_FUTURA está no retrato de outubro (público em 31/10) com início em 20/11: em 10/11 ela não abriu
    aberturas = {
        item["ano"]: item["aberturas"]
        for item in _perfil(porta).corpo["aberturas_por_ano"]
    }
    assert aberturas[2026] == 1  # só a NOVA
    depois = {
        item["ano"]: item["aberturas"]
        for item in _perfil(porta, dia=date(2026, 11, 25)).corpo["aberturas_por_ano"]
    }
    assert depois[2026] == 2


def test_antes_de_qualquer_retrato_nao_ha_perfil(porta):
    assert _perfil(porta, dia=date(2026, 9, 1)) is None


# ---------------------------------------------------------------- portão e porta


def test_sem_as_tabelas_prontas_nada_sai(porta):
    assert _perfil(porta, permitido=_permitido()) is None


def test_a_linha_do_portao_libera_a_abertura_no_conjunto_de_compradores():
    permitido = _permitido(*PRONTAS)
    assert permitido("rfb-cnpj", "data_inicio_atividade", True)
    assert permitido("rfb-cnpj", "cnae_principal", True)
    assert permitido("rfb-cnpj", "uf", True)
    # outro conjunto não ganha o campo por tabela
    outro = leitura.permitido_na_tela("sectors", DIA, _regras(*PRONTAS))
    assert not outro("rfb-cnpj", "data_inicio_atividade", True)


def test_bloco_barrado_sai_como_nao_disponivel_nunca_zero(porta):
    def sem_abertura(fonte: str, campo: str, derivado: bool) -> bool:
        return campo != "data_inicio_atividade"

    corpo = _perfil(porta, permitido=sem_abertura).corpo
    assert corpo["aberturas_por_ano"] is None
    assert corpo["blocos_nao_disponiveis"] == ["aberturas_por_ano"]
    assert corpo["empresas_ativas"] == 4
    assert not any("Aberturas por ano" in limite for limite in corpo["limites"])
    assert any("unavailable_sections" in limite for limite in corpo["limites"])

    def sem_uf(fonte: str, campo: str, derivado: bool) -> bool:
        return campo != "uf"

    corpo = _perfil(porta, permitido=sem_uf).corpo
    assert corpo["por_uf"] is None
    assert corpo["blocos_nao_disponiveis"] == ["por_uf"]
    assert not any("Por UF" in limite for limite in corpo["limites"])


def test_sem_o_cnae_liberado_nada_sai(porta):
    assert (
        _perfil(porta, permitido=lambda f, campo, d: campo != "cnae_principal") is None
    )


def test_sem_a_tabela_na_porta_nada_sai(tmp_path, banco):
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    leitor = perfil.LeitorDoPerfilDoSetor(Porta(vazia, banco), lambda *_: True)
    assert leitor.perfil(SETOR, DIA) is None


def test_os_limites_dizem_o_recorte_e_o_criterio_de_mei(porta):
    limites = " ".join(_perfil(porta).corpo["limites"])
    assert "MEI" in limites and "empresário individual" in limites
    assert "a soma das UFs pode passar do total" in limites
    assert "baixadas" in limites
    assert "recomendação de investimento" in limites


# ---------------------------------------------------------------- o pedido


@pytest.mark.parametrize("cnae", ["6201-5/01", "62.01-5", " 6201501 "])
def test_o_cnae_aceita_pontuacao(cnae):
    assert perfil.cnae_do_parametro(cnae) in {SETOR, CLASSE}


@pytest.mark.parametrize(
    "cnae", ["", "620", "620150", "62015011", "62O1501", "６２０１５０１"]
)
def test_cnae_fora_da_forma_e_recusado(cnae):
    with pytest.raises(compradores.PedidoInvalido) as erro:
        perfil.cnae_do_parametro(cnae)
    assert erro.value.codigo == "invalid_cnae"
