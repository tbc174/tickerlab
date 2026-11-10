"""A busca de empresas da API externa (linha 794): `GET /data/v1/companies` com filtros, só pessoa jurídica.

Base de mentira, sem internet; os CNPJs são de ninguém. As duas tabelas são as montadas sem pessoa
(linha 584); as linhas de direito são as de verdade (`DIREITOS_DA_API_EXTERNA`) e o teste só põe as tabelas
prontas (D10). Riscos: vazar pessoa (nenhuma coluna de sócio, contato ou endereço fino sai), baixar a base
inteira (sem filtro é 400, página no máximo 100) e olhar o futuro (o retrato só vale desde que ficou público).
"""

import dataclasses
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import rotas
from src.api_externa.conjuntos import prospeccao
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj

AGORA = datetime(2026, 11, 10, 12, tzinfo=UTC)
ROTA = "/data/v1/companies"
CARIMBOS = {
    "origem_sha256": "0" * 64,
    "montado_em": pd.Timestamp("2026-11-05", tz="UTC"),
    "versao_do_codigo": "teste",
}
# a Receita publica o retrato de um mês no mês seguinte; a porta vale o mês pelo último dia dele
# fmt: off
ESTABELECIMENTOS = [
    # cnpj, raiz, matriz, situação, abertura, cnae, uf, município, mês, disponível em
    ("11111111000191", "11111111", True, "02", "2010-05-01", "6201501", "SP", "7107", "2026-09", "2026-09-30"),
    ("11111111000272", "11111111", False, "02", "2015-01-10", "6201501", "RJ", "6001", "2026-09", "2026-09-30"),
    ("22222222000191", "22222222", True, "02", "2022-03-15", "4711302", "SP", "7107", "2026-09", "2026-09-30"),
    ("33333333000191", "33333333", True, "08", "2000-01-01", "6201501", "SP", "7107", "2026-09", "2026-09-30"),
    ("44444444000191", "44444444", True, "02", "2018-06-01", "0600001", "RJ", "6001", "2026-09", "2026-09-30"),
    # o retrato de outubro só vale a partir de 31/10; a 11111111 mudou de UF nele
    ("11111111000191", "11111111", True, "02", "2010-05-01", "6201501", "MG", "4123", "2026-10", "2026-10-31"),
    ("22222222000191", "22222222", True, "02", "2022-03-15", "4711302", "SP", "7107", "2026-10", "2026-10-31"),
]
EMPRESAS = [
    ("11111111", "ALFA TECNOLOGIA S.A.", "2054", "demais", "2026-09", "2026-09-30"),
    ("22222222", "BETA COMERCIO LTDA", "2062", "pequeno", "2026-09", "2026-09-30"),
    ("33333333", "GAMA SERVICOS LTDA", "2062", "micro", "2026-09", "2026-09-30"),
    ("44444444", "DELTA MINERACAO S.A.", "2046", "demais", "2026-09", "2026-09-30"),
    ("11111111", "ALFA TECNOLOGIA S.A.", "2054", "demais", "2026-10", "2026-10-31"),
    ("22222222", "BETA COMERCIO LTDA", "2062", "pequeno", "2026-10", "2026-10-31"),
]
# fmt: on


def _estabelecimentos() -> pd.DataFrame:
    tabela = pd.DataFrame(
        ESTABELECIMENTOS,
        columns=[
            "cnpj", "cnpj_basico", "matriz", "situacao_cadastral", "data_inicio_atividade",
            "cnae_principal", "uf", "municipio", "mes_do_retrato", "disponivel_em",
        ],
    )  # fmt: skip
    tabela["data_inicio_atividade"] = pd.to_datetime(tabela["data_inicio_atividade"])
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
    return tabela.assign(**CARIMBOS)


def _empresas() -> pd.DataFrame:
    tabela = pd.DataFrame(
        EMPRESAS,
        columns=[
            "cnpj_basico", "razao_social", "natureza_juridica", "porte", "mes_do_retrato",
            "disponivel_em",
        ],
    )  # fmt: skip
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
    return tabela.assign(**CARIMBOS)


def _gravar(base, nome: str, tabela: pd.DataFrame) -> None:
    pasta = base / nome
    pasta.mkdir(parents=True)
    for prefixo, linhas in tabela.groupby(tabela["cnpj_basico"].str[:2]):
        linhas.to_parquet(pasta / f"{prefixo}.parquet", index=False)


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = tmp_path / "base"
    _gravar(base, prospeccao.ESTABELECIMENTOS, _estabelecimentos())
    _gravar(base, prospeccao.EMPRESAS, _empresas())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


def _regras_da_busca() -> portao.Regras:
    """As regras de verdade, com as duas tabelas prontas (provas do D10) no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    tabelas = (prospeccao.ESTABELECIMENTOS, prospeccao.EMPRESAS)
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=prospeccao.CONJUNTO)
    monkeypatch.setattr(rotas, "regras_da_api", _regras_da_busca)
    return ator, org, chave


@pytest.fixture
def cliente(monkeypatch, cenario):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, cenario, **parametros):
    _ator, _org, chave = cenario
    return cliente.get(ROTA, params=parametros, headers=aj.bearer(chave.valor))


def _cnpjs(resposta) -> list[str]:
    return [e["cnpj"] for e in resposta.json()["companies"]]


# ---------------------------------------------------------------- o que sai


def test_uma_empresa_sai_com_fonte_e_dia_em_que_ficou_publica(cliente, cenario):
    resposta = _get(cliente, cenario, cnae="4711302")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["known_at"] == "2026-11-10"
    (empresa,) = corpo["companies"]
    assert empresa["cnpj"] == "22222222000191"
    assert empresa["legal_name"] == {
        "value": "BETA COMERCIO LTDA",
        "source": "rfb-cnpj",
        "published_at": "2026-10-31",
        "observed_at": None,
    }
    assert empresa["size"]["value"] == "pequeno"
    assert empresa["opened_at"]["value"] == "2022-03-15"
    assert empresa["state_code"]["value"] == "SP"
    assert empresa["head_office"]["value"] is True
    assert corpo["truncated"] is False
    assert corpo["next_cursor"] is None
    (fonte,) = corpo["sources"]
    assert fonte["source"] == "rfb-cnpj"


def test_nenhum_campo_de_pessoa_sai(cliente, cenario):
    corpo = _get(cliente, cenario, state="SP").json()
    proibidas = (
        "socio",
        "cpf",
        "email",
        "telefone",
        "logradouro",
        "fantasia",
        "partner",
    )
    texto = str(corpo).lower()
    assert not any(palavra in texto for palavra in proibidas)
    assert set(corpo["companies"][0]) <= {
        "cnpj", "legal_name", "legal_nature_code", "size", "registration_status",
        "opened_at", "cnae_code", "state_code", "municipality", "head_office",
    }  # fmt: skip


# ---------------------------------------------------------------- filtros


def test_padrao_e_so_ativa_e_baixada_so_se_pedida(cliente, cenario):
    # em setembro a 33333333 está baixada (08); no retrato de outubro nem existe
    assert "33333333000191" not in _cnpjs(_get(cliente, cenario, cnae="62"))
    antes = _get(
        cliente,
        cenario,
        cnae="62",
        registration_status="baixada",
        known_at="2026-10-15",
    )
    assert _cnpjs(antes) == ["33333333000191"]


def test_cnae_por_prefixo_uf_e_municipio_por_nome_ou_codigo(cliente, cenario):
    novo = _get(cliente, cenario, cnae="62", state="mg")
    assert _cnpjs(novo) == ["11111111000191"]
    por_codigo = _get(cliente, cenario, municipality="7107")
    assert _cnpjs(por_codigo) == ["22222222000191"]
    por_nome = _get(
        cliente, cenario, municipality="Sao Paulo", state="SP", known_at="2026-09-30"
    )
    assert por_nome.status_code == 400 or _cnpjs(
        por_nome
    )  # nome fora do cadastro oficial é 400


def test_porte_natureza_abertura_e_matriz(cliente, cenario):
    assert _cnpjs(_get(cliente, cenario, size="pequeno")) == ["22222222000191"]
    assert _cnpjs(_get(cliente, cenario, legal_nature="205")) == ["11111111000191"]
    depois = _get(cliente, cenario, opened_after="2020-01-01")
    assert _cnpjs(depois) == ["22222222000191"]
    antes = _get(cliente, cenario, opened_before="2012-01-01", known_at="2026-09-30")
    assert _cnpjs(antes) == ["11111111000191"]
    filiais = _get(cliente, cenario, head_office="false", known_at="2026-10-31")
    assert _cnpjs(filiais) == []
    filiais = _get(cliente, cenario, head_office="false", known_at="2026-09-30")
    assert _cnpjs(filiais) == ["11111111000272"]


# ---------------------------------------------------------------- sem olhar o futuro


def test_o_retrato_de_outubro_so_vale_depois_de_publicado(cliente, cenario):
    antes = _get(cliente, cenario, cnae="62", known_at="2026-10-30").json()
    assert {e["state_code"]["value"] for e in antes["companies"]} == {"SP", "RJ"}
    depois = _get(cliente, cenario, cnae="62", known_at="2026-10-31").json()
    assert [e["state_code"]["value"] for e in depois["companies"]] == ["MG"]


def test_sem_retrato_publico_na_data_e_404(cliente, cenario):
    assert _get(cliente, cenario, cnae="62", known_at="2026-01-01").status_code == 404


# ---------------------------------------------------------------- página e limite


def test_pagina_com_cursor_percorre_tudo_sem_repetir(cliente, cenario):
    vistos: list[str] = []
    cursor = None
    for _ in range(5):
        parametros = {"cnae": "62", "limit": 1, "known_at": "2026-09-30"}
        if cursor:
            parametros["cursor"] = cursor
        corpo = _get(cliente, cenario, **parametros).json()
        vistos += [e["cnpj"] for e in corpo["companies"]]
        cursor = corpo["next_cursor"]
        if not cursor:
            break
    assert vistos == ["11111111000191", "11111111000272"]


def test_limite_passa_do_maximo_e_e_cortado(cliente, cenario):
    corpo = _get(
        cliente, cenario, cnae="62", limit=100000, known_at="2026-09-30"
    ).json()
    assert len(corpo["companies"]) <= prospeccao.LIMITE_MAXIMO


# ---------------------------------------------------------------- recusas


@pytest.mark.parametrize(
    "parametros",
    [
        {},  # sem filtro nenhum
        {"registration_status": "ativa"},  # a situação sozinha não conta como filtro
        {"cnae": "abc"},
        {"cnae": "1"},
        {"state": "SPX"},
        {"size": "gigante"},
        {"registration_status": "morta", "cnae": "62"},
        {"municipality": "Cidade Que Nao Existe", "state": "SP"},
        {"cnae": "62", "cursor": "isto-nao-e-um-cursor!"},
        {"cnae": "62", "limit": 0},
    ],
)
def test_filtro_invalido_ou_ausente_e_400(cliente, cenario, parametros):
    assert _get(cliente, cenario, **parametros).status_code == 400


def test_sem_chave_nao_busca(cliente):
    assert cliente.get(ROTA, params={"cnae": "62"}).status_code == 401


def test_busca_conta_uma_unidade_de_pedido(cliente, banco, cenario):
    _ator, org, _chave = cenario
    _get(cliente, cenario, cnae="62")
    with banco.connect() as conexao:
        assert cb.consumo_do_mes(conexao, org.id, AGORA.date()).pedidos == 1


def test_texto_do_pedido_nao_vira_sql(cliente, cenario):
    resposta = _get(cliente, cenario, cnae="62", state="SP' OR '1'='1")
    assert resposta.status_code == 400


def test_data_de_abertura_e_so_data(cliente, cenario):
    assert _get(cliente, cenario, opened_after="amanha").status_code == 422


def test_busca_dos_pedidos_aceita_so_a_situacao_padrao():
    busca = prospeccao.busca_dos_pedidos(
        cnae=["62"], state=[], municipality=[], size=[], legal_nature=[],
        registration_status=[], opened_before=None, opened_after=date(2020, 1, 1),
        head_office=None, cursor=None, limit=None,
    )  # fmt: skip
    assert busca.situacoes == ("02",)
    assert busca.limite == prospeccao.LIMITE_PADRAO
