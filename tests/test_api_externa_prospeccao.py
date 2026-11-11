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
    # raiz, razão, natureza, porte, capital, estabelecimentos ativos, mês, disponível em
    ("11111111", "ALFA TECNOLOGIA S.A.", "2054", "demais", 5_000_000.0, 2, "2026-09", "2026-09-30"),
    ("22222222", "BETA COMERCIO LTDA", "2062", "pequeno", 100_000.0, 1, "2026-09", "2026-09-30"),
    ("33333333", "GAMA SERVICOS LTDA", "2062", "micro", 50_000.0, 0, "2026-09", "2026-09-30"),
    ("44444444", "DELTA MINERACAO S.A.", "2046", "demais", 5_000_000.0, 1, "2026-09", "2026-09-30"),
    ("11111111", "ALFA TECNOLOGIA S.A.", "2054", "demais", 6_000_000.0, 1, "2026-10", "2026-10-31"),
    ("22222222", "BETA COMERCIO LTDA", "2062", "pequeno", 100_000.0, 1, "2026-10", "2026-10-31"),
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
            "cnpj_basico", "razao_social", "natureza_juridica", "porte", "capital_social",
            "n_estabelecimentos", "mes_do_retrato", "disponivel_em",
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
    assert empresa["size"]["value"] == "small"
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
        "share_capital", "active_establishments",
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
    assert _cnpjs(_get(cliente, cenario, size="small")) == ["22222222000191"]
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
        {"cnae": "٦٢"},  # dígitos que não são 0 a 9
        {"state": "SPX"},
        {"size": "gigante"},
        {"size": "pequeno"},  # o vocabulário de fora é em inglês
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


def test_sem_contrato_do_conjunto_a_busca_nao_entrega_nem_cnpj(
    banco, monkeypatch, pasta
):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto="companies")  # contrato de outro conjunto
    monkeypatch.setattr(rotas, "regras_da_api", _regras_da_busca)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    resposta = cliente.get(
        ROTA, params={"cnae": "62", "size": "micro"}, headers=aj.bearer(chave.valor)
    )
    assert resposta.status_code == 404
    assert "cnpj" not in resposta.text


def test_filtro_por_campo_negado_pelo_portao_nao_serve_de_oraculo(
    cliente, cenario, monkeypatch
):
    def sem_porte(_conexao, _contexto, _conjunto):
        return lambda fonte, campo, _publico: campo != "porte"

    monkeypatch.setattr(rotas, "_portao", sem_porte)
    assert _get(cliente, cenario, size="micro").status_code == 404
    assert _get(cliente, cenario, cnae="62").status_code == 200


def test_lista_de_filtro_grande_demais_e_400(cliente, cenario):
    muitos = [str(10 + i) for i in range(prospeccao.VALORES_MAXIMOS + 1)]
    assert _get(cliente, cenario, cnae=muitos).status_code == 400


# ---------------------------------------------------------------- capital, estabelecimentos e ordem
# em 15/10 vale o retrato de setembro; ativos: ALFA (2 estabelecimentos, 5 mi), BETA (1, 100 mil) e DELTA (1, 5 mi)

SETEMBRO = {"known_at": "2026-10-15"}


def test_capital_e_estabelecimentos_saem_como_numero_com_fonte(cliente, cenario):
    corpo = _get(cliente, cenario, cnae="4711302").json()
    (empresa,) = corpo["companies"]
    assert empresa["share_capital"]["value"] == 100_000.0
    assert empresa["share_capital"]["source"] == "rfb-cnpj"
    assert empresa["active_establishments"]["value"] == 1


def test_filtro_de_capital_minimo_e_maximo(cliente, cenario):
    grandes = _get(cliente, cenario, capital_min=1_000_000, **SETEMBRO)
    assert _cnpjs(grandes) == ["11111111000191", "11111111000272", "44444444000191"]
    pequena = _get(cliente, cenario, capital_max=200_000, **SETEMBRO)
    assert _cnpjs(pequena) == ["22222222000191"]
    faixa = _get(cliente, cenario, capital_min=100_000, capital_max=100_000, **SETEMBRO)
    assert _cnpjs(faixa) == ["22222222000191"]


def test_filtro_de_estabelecimentos_ativos_minimo(cliente, cenario):
    resposta = _get(cliente, cenario, branches_min=2, **SETEMBRO)
    assert _cnpjs(resposta) == ["11111111000191", "11111111000272"]


def test_ordem_por_capital_decrescente_desempata_pelo_cnpj(cliente, cenario):
    resposta = _get(cliente, cenario, capital_min=1, sort="-capital", **SETEMBRO)
    assert _cnpjs(resposta) == [
        "11111111000191", "11111111000272", "44444444000191", "22222222000191",
    ]  # fmt: skip


def test_ordem_por_capital_crescente(cliente, cenario):
    resposta = _get(cliente, cenario, capital_min=1, sort="capital", **SETEMBRO)
    assert _cnpjs(resposta) == [
        "22222222000191", "11111111000191", "11111111000272", "44444444000191",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("sort", "esperado"),
    [
        ("-capital", ["11111111000191", "11111111000272", "44444444000191", "22222222000191"]),
        ("capital", ["22222222000191", "11111111000191", "11111111000272", "44444444000191"]),
        ("-branches", ["11111111000191", "11111111000272", "22222222000191", "44444444000191"]),
        ("branches", ["22222222000191", "44444444000191", "11111111000191", "11111111000272"]),
    ],
)  # fmt: skip
def test_cursor_da_ordem_percorre_tudo_sem_repetir_nem_pular(
    cliente, cenario, sort, esperado
):
    vistos: list[str] = []
    cursor = None
    for _ in range(10):
        parametros = {"capital_min": 1, "sort": sort, "limit": 1, **SETEMBRO}
        if cursor:
            parametros["cursor"] = cursor
        corpo = _get(cliente, cenario, **parametros).json()
        vistos += [e["cnpj"] for e in corpo["companies"]]
        cursor = corpo["next_cursor"]
        if not cursor:
            break
    assert vistos == esperado


def test_cursor_de_uma_ordem_nao_serve_em_outra(cliente, cenario):
    pagina = _get(cliente, cenario, capital_min=1, sort="-capital", limit=1, **SETEMBRO)
    cursor = pagina.json()["next_cursor"]
    outra = _get(
        cliente,
        cenario,
        capital_min=1,
        sort="capital",
        cursor=cursor,
        limit=1,
        **SETEMBRO,
    )
    assert (
        outra.status_code == 200
    )  # mesma família de ordem: o cursor vale o valor, não a direção
    por_cnpj = _get(cliente, cenario, capital_min=1, cursor=cursor, **SETEMBRO)
    assert por_cnpj.status_code == 400
    assert por_cnpj.json()["detail"] == "invalid_cursor"
    simples = _get(cliente, cenario, capital_min=1, limit=1, **SETEMBRO)
    ordenado = _get(
        cliente, cenario, capital_min=1, sort="-capital",
        cursor=simples.json().get("next_cursor"), **SETEMBRO,
    )  # fmt: skip
    assert ordenado.status_code == 400


@pytest.mark.parametrize(
    "parametros",
    [
        {"capital_min": -1},
        {"capital_min": 10, "capital_max": 5},
        {"capital_min": "nan"},
        {"capital_max": "inf"},
        {"capital_min": 1e20},
        {"branches_min": 0},
        {"branches_min": 2_000_000},
        {"cnae": "62", "sort": "faturamento"},
        {"cnae": "62", "sort": "--capital"},
    ],
)
def test_capital_estabelecimentos_ou_ordem_invalidos_sao_400(
    cliente, cenario, parametros
):
    assert _get(cliente, cenario, **parametros).status_code in (400, 422)


def test_so_a_ordem_nao_basta_como_filtro(cliente, cenario):
    resposta = _get(cliente, cenario, sort="-capital")
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "filter_required"


def test_tabela_montada_antes_do_capital_nao_quebra_a_busca_sem_esse_filtro(
    cliente, cenario, pasta
):
    for arquivo in (pasta / prospeccao.EMPRESAS).glob("*.parquet"):
        tabela = pd.read_parquet(arquivo).drop(
            columns=["capital_social", "n_estabelecimentos"]
        )
        tabela.to_parquet(arquivo, index=False)
    antiga = _get(cliente, cenario, cnae="4711302")
    assert antiga.status_code == 200
    (empresa,) = antiga.json()["companies"]
    assert "share_capital" not in empresa
    assert _get(cliente, cenario, capital_min=1).status_code == 404


def test_cursor_com_numero_gigante_e_400_e_nao_500(cliente, cenario):
    import base64

    texto = '["capital_social", ' + "9" * 400 + ', "11111111000191"]'
    cursor = base64.urlsafe_b64encode(texto.encode()).decode().rstrip("=")
    resposta = _get(
        cliente, cenario, capital_min=1, sort="capital", cursor=cursor, **SETEMBRO
    )
    assert resposta.status_code == 400


def test_cursor_de_uma_coluna_nao_serve_em_outra(cliente, cenario):
    pagina = _get(cliente, cenario, capital_min=1, sort="capital", limit=1, **SETEMBRO)
    cursor = pagina.json()["next_cursor"]
    outra = _get(
        cliente, cenario, capital_min=1, sort="branches", cursor=cursor, **SETEMBRO
    )
    assert outra.status_code == 400
    assert outra.json()["detail"] == "invalid_cursor"


def test_capital_ausente_nao_quebra_o_carregar_mais(cliente, cenario, pasta):
    for arquivo in (pasta / prospeccao.EMPRESAS).glob("*.parquet"):
        tabela = pd.read_parquet(arquivo)
        tabela["capital_social"] = float("nan")
        tabela.to_parquet(arquivo, index=False)
    vistos: list[str] = []
    cursor = None
    for _ in range(10):
        parametros = {"branches_min": 1, "sort": "capital", "limit": 1, **SETEMBRO}
        if cursor:
            parametros["cursor"] = cursor
        resposta = _get(cliente, cenario, **parametros)
        assert resposta.status_code == 200
        corpo = resposta.json()
        vistos += [e["cnpj"] for e in corpo["companies"]]
        cursor = corpo["next_cursor"]
        if not cursor:
            break
    assert len(vistos) == len(set(vistos)) == 4


def test_cursor_aninhado_demais_e_400_e_nao_500(cliente, cenario):
    import base64

    cursor = base64.urlsafe_b64encode(b"[" * 3000).decode().rstrip("=")
    resposta = _get(
        cliente, cenario, capital_min=1, sort="capital", cursor=cursor, **SETEMBRO
    )
    assert resposta.status_code == 400


def test_cursor_ordenado_cabe_no_limite_da_tela_do_analista():
    from src.api_v1.analista import TAMANHO_MAXIMO_DO_CURSOR

    maior = prospeccao.cursor_de(
        "ZZZZZZZZZZZZZZ", 999_999_999_999_999.99, "n_estabelecimentos"
    )
    assert len(maior) <= TAMANHO_MAXIMO_DO_CURSOR


# --- a busca em dois passos (linha 584): o corte nos estabelecimentos, a junção só nas linhas da página ---


def _leitor(base) -> prospeccao.LeitorDeProspeccao:
    return prospeccao.LeitorDeProspeccao(Porta(base), lambda *_: True, 100)


BUSCAS_DE_DOIS_PASSOS = [
    prospeccao.Busca(ufs=("SP",)),
    prospeccao.Busca(cnaes=("62",)),
    prospeccao.Busca(ufs=("SP", "RJ"), cnaes=("4711", "0600")),
    prospeccao.Busca(municipios=("7107",), matriz=True),
    prospeccao.Busca(ufs=("SP",), situacoes=("02", "08")),
]


def _paginas(leitor, busca, como_era_em):
    """Todas as páginas de uma busca, de uma em uma empresa, pelo cursor."""
    paginas = []
    while True:
        servida = leitor.buscar(busca, como_era_em)
        paginas.append(servida.corpo)
        if not servida.corpo["cortada"]:
            return paginas
        ultimo = servida.corpo["empresas"][-1]["cnpj"]
        busca = dataclasses.replace(busca, depois_de=ultimo)


@pytest.mark.parametrize("busca", BUSCAS_DE_DOIS_PASSOS)
def test_dois_passos_respondem_igual_a_juncao_primeiro(pasta, monkeypatch, busca):
    busca = dataclasses.replace(busca, limite=1)
    hoje = date(2026, 11, 10)
    leitor = _leitor(pasta)
    em_dois_passos = _paginas(leitor, busca, hoje)
    monkeypatch.setattr(prospeccao, "_depende_da_empresa", lambda _busca: True)
    assert _paginas(leitor, busca, hoje) == em_dois_passos


def test_estabelecimento_sem_empresa_nao_estraga_o_corte_da_pagina(tmp_path):
    estabelecimentos = _estabelecimentos()
    novos = pd.DataFrame(
        [
            # a raiz 00000000 não tem empresa; a 66666666 tem
            ("00000000000191", "00000000", True, "02", "2020-01-01", "6201501", "SP", "7107", "2026-10", "2026-10-31"),
            ("66666666000191", "66666666", True, "02", "2020-01-01", "6201501", "SP", "7107", "2026-10", "2026-10-31"),
        ],
        columns=estabelecimentos.columns[:10],
    )  # fmt: skip
    novos["data_inicio_atividade"] = pd.to_datetime(novos["data_inicio_atividade"])
    novos["disponivel_em"] = pd.to_datetime(novos["disponivel_em"]).dt.date
    empresas = pd.concat(
        [
            _empresas(),
            pd.DataFrame(
                [("66666666", "OMEGA LTDA", "2062", "micro", 1_000.0, 1, "2026-10", "2026-10-31")],
                columns=_empresas().columns[:8],
            ).assign(disponivel_em=date(2026, 10, 31), **CARIMBOS),
        ]
    )  # fmt: skip
    base = tmp_path / "base"
    _gravar(
        base,
        prospeccao.ESTABELECIMENTOS,
        pd.concat([estabelecimentos, novos.assign(**CARIMBOS)]),
    )
    _gravar(base, prospeccao.EMPRESAS, empresas)
    servida = _leitor(base).buscar(
        prospeccao.Busca(ufs=("SP",), limite=1), date(2026, 11, 10)
    )
    assert [e["cnpj"] for e in servida.corpo["empresas"]] == ["22222222000191"]
    assert servida.corpo["cortada"] is True  # ainda há a 66666666 depois
