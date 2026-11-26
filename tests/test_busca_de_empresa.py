"""A busca de empresa pelo nome (linhas 1033 e 1037; `base/busca_de_empresa.py`): razão social, nome fantasia e
razão social antiga, com UF, município e CNAE, o nome exato na frente. Base de mentira, nomes inventados."""

from datetime import date

import pandas as pd
import pytest

from base import busca_de_empresa as busca
from base import nomes_de_empresa as nomes
from base.porta import Porta

MES = "2026-10"
PUBLICO = date(2026, 10, 31)
DIA = date(2026, 11, 10)
CARIMBOS = {
    "origem_sha256": "0" * 64,
    "montado_em": pd.Timestamp("2026-11-05", tz="UTC"),
    "versao_do_codigo": "teste",
}
# raiz, razão social, capital, situação, CNAE, UF, município
EMPRESAS = [
    (
        "11111111",
        "D Q R AVICULTURA - COMERCIO DE OVOS LTDA",
        90_000.0,
        "02",
        "0155505",
        "RN",
        "1761",
    ),
    (
        "22222222",
        "VITAFICTA AGROPECUARIA GOIAS LTDA",
        10_000.0,
        "08",
        "0151201",
        "GO",
        "9253",
    ),
    ("33333333", "VELOZ TECNOLOGIA LTDA", 5_000_000.0, "02", "6201501", "SP", "7107"),
    ("44444444", "REVENDA CERTA LTDA", 1_000.0, "02", "4511102", "ES", "5703"),
    (
        "55555555",
        "LUMINA ESPECIALIDADES BRASIL LTDA",
        2_000_000.0,
        "02",
        "2063100",
        "SP",
        "6789",
    ),
    (
        "66666666",
        "ELETROMETALURGICA SUL LTDA",
        9_000_000.0,
        "02",
        "2599399",
        "RS",
        "8001",
    ),
    ("77777777", "ROMETA COMPONENTES LTDA", 100.0, "02", "3103900", "RS", "8001"),
    ("88888888", "OMEGA S.A.", 50.0, "02", "2710401", "SC", "8179"),
    (
        "99999999",
        "OMEGA EQUIPAMENTOS ELETRICOS S.A.",
        8_000_000.0,
        "02",
        "2710401",
        "SC",
        "8179",
    ),
]
# raiz, nome fantasia
FANTASIAS = [
    ("11111111", "VITAFICTA"),
    ("33333333", "REVENDA CERTA"),
]
# raiz, mês da versão, consta, razão social
HISTORICO = [
    ("55555555", "2023-05", True, "FARMAQUIMICA ESTRELA LTDA"),
    ("55555555", "2024-12", True, "LUMINA ESPECIALIDADES BRASIL LTDA"),
]


def _empresas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cnpj_basico": [e[0] for e in EMPRESAS],
            "razao_social": [e[1] for e in EMPRESAS],
            "natureza_juridica": "2062",
            "porte": "demais",
            "capital_social": [e[2] for e in EMPRESAS],
            "n_estabelecimentos": 1,
            "mes_do_retrato": MES,
            "disponivel_em": PUBLICO,
        }
    ).assign(**CARIMBOS)


def _estabelecimentos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cnpj": [e[0] + "000100" for e in EMPRESAS],
            "cnpj_basico": [e[0] for e in EMPRESAS],
            "matriz": True,
            "situacao_cadastral": [e[3] for e in EMPRESAS],
            "data_inicio_atividade": pd.Timestamp("2010-01-01"),
            "cnae_principal": [e[4] for e in EMPRESAS],
            "uf": [e[5] for e in EMPRESAS],
            "municipio": [e[6] for e in EMPRESAS],
            "mes_do_retrato": MES,
            "disponivel_em": PUBLICO,
        }
    ).assign(**CARIMBOS)


def _nomes(mes: str = MES, publico: date = PUBLICO) -> pd.DataFrame:
    historico = pd.DataFrame(
        HISTORICO, columns=["cnpj_basico", "mes_do_retrato", "consta", "razao_social"]
    )
    fantasias = pd.DataFrame(FANTASIAS, columns=["cnpj_basico", "nome_fantasia"])
    tabela = nomes.tabela_de_nomes(_empresas(), fantasias, historico)
    return tabela.assign(mes_do_retrato=mes, disponivel_em=publico, **CARIMBOS)


def _gravar(base, nome: str, tabela: pd.DataFrame) -> None:
    pasta = base / nome
    pasta.mkdir(parents=True)
    tabela.to_parquet(pasta / "00.parquet", index=False)


def _porta(tmp_path, com_nomes: pd.DataFrame | None) -> Porta:
    base = tmp_path / "base"
    _gravar(base, "cnpj_empresas_pj", _empresas())
    _gravar(base, "cnpj_estabelecimentos_pj", _estabelecimentos())
    if com_nomes is not None:
        _gravar(base, "cnpj_nomes_pj", com_nomes)
    return Porta(base)


@pytest.fixture
def porta(tmp_path):
    return _porta(tmp_path, _nomes())


def _procurar(porta, nome: str, **filtros) -> busca.Busca:
    return busca.procurar(
        porta, palavras=busca.palavras_do_nome(nome), dia=DIA, **filtros
    )


def _raizes(resultado: busca.Busca) -> list[str]:
    return [linha["cnpj_basico"] for linha in resultado.linhas]


def test_nome_fantasia_acha_a_empresa_e_diz_por_onde_casou(porta):
    resultado = _procurar(porta, "vitaficta")
    # a de nome fantasia igual ao pedido vem antes da homônima baixada que só começa por ele
    assert _raizes(resultado) == ["11111111", "22222222"]
    primeira = resultado.linhas[0]
    assert primeira["casou_com"] == "nome_fantasia"
    assert primeira["casou_nome"] == "VITAFICTA"
    assert primeira["razao_social"].startswith("D Q R AVICULTURA")
    assert primeira["cnpj"] == "11111111000100"


def test_razao_social_antiga_acha_a_empresa_de_hoje(porta):
    resultado = _procurar(porta, "farmaquimica estrela")
    assert _raizes(resultado) == ["55555555"]
    (linha,) = resultado.linhas
    assert linha["casou_com"] == "razao_social_anterior"
    assert linha["trocado_em_mes"] == "2024-12"
    assert linha["razao_social"] == "LUMINA ESPECIALIDADES BRASIL LTDA"


def test_letras_soltas_da_razao_social_valem_juntas(porta):
    assert _raizes(_procurar(porta, "dqr avicultura")) == ["11111111"]
    assert _raizes(_procurar(porta, "d.q.r. avicultura")) == ["11111111"]


def test_nome_exato_sem_a_forma_juridica_vem_primeiro(porta):
    resultado = _procurar(porta, "omega")
    # "OMEGA S.A." é o nome igual, mesmo com capital menor
    assert _raizes(resultado) == ["88888888", "99999999"]


def test_palavra_inteira_vem_antes_do_pedaco(porta):
    resultado = _procurar(porta, "rometa")
    assert _raizes(resultado) == ["77777777", "66666666"]
    assert resultado.achadas == 2


def test_sem_nome_com_todas_as_palavras_procura_cada_uma(porta):
    resultado = _procurar(porta, "veloz farmaquimica")
    assert resultado.por_palavra
    assert set(_raizes(resultado)) == {"33333333", "55555555"}
    assert not _procurar(porta, "veloz tecnologia").por_palavra


def test_filtros_de_uf_municipio_e_cnae(porta):
    assert _raizes(_procurar(porta, "vitaficta", uf="RN")) == ["11111111"]
    assert _raizes(_procurar(porta, "vitaficta", cnaes=["0151"])) == ["22222222"]
    assert _raizes(_procurar(porta, "revenda certa", municipios=["7107"])) == [
        "33333333"
    ]
    vazio = _procurar(porta, "vitaficta", uf="SP")
    assert vazio.linhas == [] and vazio.achadas == 0


def test_o_filtro_vale_antes_do_corte_pelo_limite(porta):
    resultado = _procurar(porta, "omega", cnaes=["27"], limite=1)
    assert len(resultado.linhas) == 1
    assert resultado.achadas == 2


def test_sem_a_tabela_de_nomes_a_busca_e_pela_razao_social(tmp_path):
    resultado = _procurar(_porta(tmp_path, None), "vitaficta")
    assert _raizes(resultado) == ["22222222"]
    assert not resultado.com_outros_nomes


def test_nomes_publicados_depois_do_dia_nao_contam(tmp_path):
    porta = _porta(tmp_path, _nomes(publico=date(2026, 11, 30)))
    resultado = _procurar(porta, "vitaficta")
    assert _raizes(resultado) == ["22222222"]
    assert not resultado.com_outros_nomes


def test_nomes_de_um_retrato_velho_nao_escondem_a_razao_social_de_hoje(tmp_path):
    velha = _nomes(mes="2026-09", publico=date(2026, 9, 30))
    porta = _porta(tmp_path, velha[velha["cnpj_basico"] != "77777777"])
    assert _raizes(_procurar(porta, "vitaficta")) == ["11111111", "22222222"]
    assert _raizes(_procurar(porta, "rometa componentes")) == ["77777777"]


@pytest.mark.parametrize(
    "pedido",
    ["", "  ", "ab", "123.456.789-09", "um dois tres quatro cinco seis sete", "a;b%"],
)
def test_pedido_fora_da_forma_e_recusado_sem_repetir_o_que_entrou(pedido):
    with pytest.raises(busca.EntradaInvalida) as erro:
        busca.palavras_do_nome(pedido)
    assert "123" not in str(erro.value)
