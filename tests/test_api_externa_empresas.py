"""A situação cadastral das empresas na API externa (B-32a, PR 4): `/data/v1/companies/{cnpj}` e o lote.

Base de mentira, sem internet; os CNPJs são de ninguém. As linhas de direito são as de verdade
(`DIREITOS_DA_API_EXTERNA`); o teste só põe a tabela pronta (D10), como a A7 fará. Riscos do plano: vazar
pessoa (MEI, empresário individual e quem a rede não conhece saem `not_available`, igual a um CNPJ que não
existe) e olhar o futuro (o retrato do mês só vale desde o dia em que ficou público).

Só a situação cadastral sai (decisão do Tiago em 04/11/2026): nome, natureza jurídica e Simples a base só
guarda como são hoje, e servi-los numa data passada mostraria o futuro.
"""

import dataclasses
from datetime import UTC, date, datetime

import duckdb
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from base import prontidao
from base.dossie import COLUNAS_DE_PESSOA, conferir_sem_pessoas
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import acesso, rotas
from src.api_externa.conjuntos import empresas
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj

AGORA = datetime(2026, 11, 10, 12, tzinfo=UTC)  # o beta começa em 03/11
TABELA = "cnpj_situacao_cadastral"
EMPRESA = "11111111000191"
MEI = "33333333000191"
EMPRESARIO_INDIVIDUAL = "44444444000191"
FORA_DA_REDE = "55555555000191"
FUNDO = "66666666000191"
SEM_SITUACAO = "77777777000191"
INEXISTENTE = "88888888000191"
ROTA = f"/data/v1/companies/{EMPRESA}"
LOTE = "/data/v1/companies/batch"


def _formatado(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


# os retratos da Receita: o de jan/2025 diz ativa; o de jun/2025, baixada, só foi baixado em 12/07 (o
# porta vale o mês pelo último dia: público em 31/07). MEI, empresário individual e quem está fora da
# rede também têm retrato: só a rota sabe tirá-los.
COLUNAS_DOS_RETRATOS = (
    "cnpj", "situacao_cadastral", "data_situacao_cadastral", "motivo_situacao", "mes_do_retrato",
    "disponivel_em",
)  # fmt: skip
# fmt: off
RETRATOS = [
    (EMPRESA, "02", "2010-05-01", "00", "2025-01", "2025-01-31"),
    (EMPRESA, "08", "2025-06-20", "01", "2025-06", "2025-07-12"),
    (MEI, "02", "2019-03-01", "00", "2025-06", "2025-06-30"),
    (EMPRESARIO_INDIVIDUAL, "02", "2015-01-01", "00", "2025-06", "2025-06-30"),
    (FORA_DA_REDE, "02", "2001-01-01", "00", "2025-06", "2025-06-30"),
    (FUNDO, "02", "2012-01-01", "00", "2025-06", "2025-06-30"),
]
# fmt: on

# a rede: quem a entidade é e por qual identificador ela é achada
COLUNAS_DA_REDE = (
    "id_entidade",
    "valor",
    "sistema",
    "tipo",
    "mei",
    "trata_como_pessoa",
)
# fmt: off
REDE = pd.DataFrame(
    [
        ("E" + "1" * 20, EMPRESA[:8], "cnpj_raiz", "empresa", False, False),
        ("E" + "3" * 20, MEI[:8], "cnpj_raiz", "empresa", True, False),  # a opção pelo MEI basta
        ("E" + "4" * 20, EMPRESARIO_INDIVIDUAL[:8], "cnpj_raiz", "empresa", False, True),
        ("E" + "6" * 20, FUNDO, "cnpj", "fundo", False, False),
        ("E" + "7" * 20, SEM_SITUACAO[:8], "cnpj_raiz", "empresa", False, False),
    ],
    columns=list(COLUNAS_DA_REDE),
)
# fmt: on


def _retratos(linhas=RETRATOS) -> pd.DataFrame:
    tabela = pd.DataFrame(list(linhas), columns=list(COLUNAS_DOS_RETRATOS))
    tabela["cnpj_basico"] = tabela["cnpj"].str[:8]
    tabela["cnpj"] = tabela["cnpj"].map(_formatado)
    tabela["matriz"] = True
    tabela["data_situacao_cadastral"] = pd.to_datetime(
        tabela["data_situacao_cadastral"]
    ).dt.date
    tabela["disponivel_em"] = pd.to_datetime(tabela["disponivel_em"]).dt.date
    tabela["origem_sha256"] = "0" * 64
    tabela["origem_coletada_em"] = pd.Timestamp("2025-07-12", tz="UTC")
    tabela["montado_em"] = pd.Timestamp("2025-07-12", tz="UTC")
    tabela["versao_do_codigo"] = "teste"
    return tabela


def _entidades() -> pd.DataFrame:
    return REDE[["id_entidade", "tipo", "mei", "trata_como_pessoa"]].assign(
        nome=None,
        natureza_juridica="2062",
        natureza_fonte="receita",
        fontes="cvm-cadastro",
        publico_em=date(2020, 1, 1),
    )


def _identificadores() -> pd.DataFrame:
    return REDE[["id_entidade", "sistema", "valor"]].assign(
        desde=None,
        ate=None,
        publico_em=date(2020, 1, 1),
        regra=2,
        conferido_por="regra",
        fontes="cvm-cadastro",
    )


def _gravar_base(base, retratos: pd.DataFrame, com_rede: bool = True) -> None:
    pasta = base / TABELA
    pasta.mkdir(parents=True, exist_ok=True)
    for mes, linhas in retratos.groupby("mes_do_retrato"):
        linhas.to_parquet(pasta / f"{mes}.parquet", index=False)
    if com_rede:
        (base / "rede").mkdir(exist_ok=True)
        _entidades().to_parquet(base / "rede" / "entidades.parquet", index=False)
        _identificadores().to_parquet(
            base / "rede" / "identificadores.parquet", index=False
        )


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = tmp_path / "base"
    _gravar_base(base, _retratos())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


def _regras_das_empresas() -> portao.Regras:
    """As regras de verdade, com a tabela da situação cadastral pronta (provas do D10) no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versao = prontidao.versoes_maiores()[TABELA]
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={TABELA: Prontidao(versao, prova, prova, prova)},
    )


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    """Uma organização com chave e contrato de `companies`, e a tabela pronta."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto="companies")
    monkeypatch.setattr(rotas, "regras_da_api", _regras_das_empresas)
    return ator, org, chave


@pytest.fixture
def cliente(monkeypatch, cenario):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, cenario, rota: str = ROTA, **parametros):
    _ator, _org, chave = cenario
    return cliente.get(rota, params=parametros, headers=aj.bearer(chave.valor))


def _post(cliente, cenario, corpo: dict):
    _ator, _org, chave = cenario
    return cliente.post(LOTE, json=corpo, headers=aj.bearer(chave.valor))


def _pedidos_do_mes(banco, org) -> int:
    with banco.connect() as conexao:
        return cb.consumo_do_mes(conexao, org.id, AGORA.date()).pedidos


# ---------------------------------------------------------------- o que sai


def test_situacao_sai_com_fonte_data_e_atribuicao_em_ingles(cliente, cenario):
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cnpj"] == EMPRESA
    assert corpo["known_at"] == "2026-11-10"
    assert corpo["registration_status"] == {
        "value": "08",
        "source": "rfb-cnpj",
        "published_at": "2025-07-31",  # o mês vale pelo último dia, depois do download
        "observed_at": None,
    }
    assert corpo["registration_status_date"]["value"] == "2025-06-20"
    assert corpo["registration_status_reason"]["value"] == "01"
    assert corpo["head_office"]["value"] is True
    assert corpo["snapshot_month"]["value"] == "2025-06"
    (fonte,) = corpo["sources"]
    assert fonte["source"] == "rfb-cnpj"
    assert "Receita" in fonte["attribution"]


@pytest.mark.parametrize(
    ("dia", "situacao", "retrato"),
    [
        (
            "2025-01-31",
            "02",
            "2025-01",
        ),  # o primeiro retrato, no dia em que ficou público
        (
            "2025-07-15",
            "02",
            "2025-01",
        ),  # o de junho já foi baixado, mas o mês só vale em 31/07
        ("2025-07-31", "08", "2025-06"),
    ],
)
def test_known_at_ve_o_retrato_que_ja_era_publico(
    cliente, cenario, dia, situacao, retrato
):
    corpo = _get(cliente, cenario, known_at=dia).json()
    assert corpo["registration_status"]["value"] == situacao
    assert corpo["snapshot_month"]["value"] == retrato
    assert corpo["registration_status"]["published_at"] <= dia


def test_known_at_antes_do_retrato_da_not_available(cliente, cenario, banco):
    resposta = _get(cliente, cenario, known_at="2025-01-30")
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


# ---------------------------------------------------------------- sem pessoa


@pytest.mark.parametrize(
    "cnpj", [MEI, EMPRESARIO_INDIVIDUAL, FORA_DA_REDE, FUNDO, SEM_SITUACAO]
)
def test_mei_e_empresario_individual_dao_not_available(cliente, cenario, cnpj):
    # o mesmo corpo de um CNPJ que não existe: a resposta não diz qual foi o motivo
    inexistente = _get(cliente, cenario, f"/data/v1/companies/{INEXISTENTE}")
    resposta = _get(cliente, cenario, f"/data/v1/companies/{cnpj}")
    assert resposta.status_code == inexistente.status_code == 404
    assert resposta.json() == inexistente.json() == {"detail": "not_available"}


def test_sem_pessoa_em_nenhuma_resposta(cliente, cenario):
    respostas = [
        _get(cliente, cenario).json(),
        _post(
            cliente, cenario, {"cnpjs": [EMPRESA, MEI, EMPRESARIO_INDIVIDUAL]}
        ).json(),
    ]
    for corpo in respostas:
        conferir_sem_pessoas(corpo, set())
        assert not aj.chaves_de(corpo) & COLUNAS_DE_PESSOA


def test_entidade_com_dois_ids_na_rede_da_not_available(cenario, pasta, monkeypatch):
    # o mesmo CNPJ em duas entidades é conflito: não dá para saber se é pessoa
    identificadores = _identificadores()
    repetido = identificadores.iloc[[0]].assign(id_entidade="E" + "9" * 20)
    pd.concat([identificadores, repetido]).to_parquet(
        pasta / "rede" / "identificadores.parquet", index=False
    )
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    assert _get(cliente, cenario).status_code == 404


def _regravar_rede(
    pasta, entidades: pd.DataFrame, identificadores: pd.DataFrame
) -> None:
    entidades.to_parquet(pasta / "rede" / "entidades.parquet", index=False)
    identificadores.to_parquet(pasta / "rede" / "identificadores.parquet", index=False)


def test_entidade_repetida_na_rede_da_not_available(cenario, pasta, monkeypatch):
    # duas linhas para o mesmo id, uma delas de pessoa: na dúvida, é pessoa
    entidades = _entidades()
    repetida = entidades.iloc[[0]].assign(trata_como_pessoa=True)
    _regravar_rede(pasta, pd.concat([entidades, repetida]), _identificadores())
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    assert _get(cliente, cenario).status_code == 404


def test_cnpj_ligado_a_um_id_de_pessoa_da_not_available(cenario, pasta, monkeypatch):
    # o id de pessoa da rede nunca sai, mesmo se a linha dele dissesse empresa
    pessoa = "P" + "1" * 20
    entidades = _entidades().assign(
        id_entidade=lambda t: t["id_entidade"].replace("E" + "1" * 20, pessoa)
    )
    identificadores = _identificadores().assign(
        id_entidade=lambda t: t["id_entidade"].replace("E" + "1" * 20, pessoa)
    )
    _regravar_rede(pasta, entidades, identificadores)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    assert _get(cliente, cenario).status_code == 404


def test_base_sem_a_rede_nao_serve_nenhuma_empresa(tmp_path, cenario, monkeypatch):
    base = tmp_path / "sem_rede"
    _gravar_base(base, _retratos(), com_rede=False)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


# ---------------------------------------------------------------- sem olhar o futuro


def _o_que_era(dia: date) -> dict | None:
    """O oráculo: o retrato mais novo da empresa já público no dia (o mês vale pelo último dia)."""
    retratos = _retratos()
    retratos = retratos[retratos["cnpj"] == _formatado(EMPRESA)].assign(
        publico=lambda t: pd.to_datetime(t["disponivel_em"]) + pd.offsets.MonthEnd(0)
    )
    publicos = retratos[retratos["publico"].dt.date <= dia]
    if publicos.empty:
        return None
    return publicos.sort_values("mes_do_retrato").iloc[-1].to_dict()


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(dia=st.dates(min_value=date(2024, 12, 1), max_value=AGORA.date()))
def test_known_at_nunca_mostra_o_futuro(cliente, cenario, dia):
    resposta = _get(cliente, cenario, known_at=dia.isoformat())
    esperado = _o_que_era(dia)
    if esperado is None:
        assert resposta.status_code == 404
        return
    corpo = resposta.json()
    assert corpo["registration_status"]["value"] == esperado["situacao_cadastral"]
    assert corpo["snapshot_month"]["value"] == esperado["mes_do_retrato"]
    assert corpo["registration_status"]["published_at"] <= dia.isoformat()


def test_cortar_o_futuro_nao_muda_o_passado(tmp_path, cenario, monkeypatch):
    dia = "2025-07-15"
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    inteira = _get(cliente, cenario, known_at=dia).json()
    base = tmp_path / "cortada"
    retratos = _retratos()
    _gravar_base(base, retratos[retratos["mes_do_retrato"] < "2025-06"])
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    assert _get(cliente, cenario, known_at=dia).json() == inteira


# ---------------------------------------------------------------- o portão


def test_empresa_negada_e_inexistente_dao_o_mesmo_404(cliente, cenario, banco):
    inexistente = _get(cliente, cenario, f"/data/v1/companies/{INEXISTENTE}")
    ator, _org, _chave = cenario
    with banco.begin() as conexao:
        cb.suspender_conjunto(
            conexao, conjunto="companies", motivo="fonte", ator_id=ator.id
        )
    negado = _get(cliente, cenario)
    assert negado.status_code == 404
    assert negado.json() == inexistente.json()


def test_hoje_sem_a_prontidao_nada_sai(cliente, cenario, monkeypatch):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: None)  # as regras de verdade
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_organizacao_sem_contrato_de_companies_recebe_404(banco, monkeypatch, pasta):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto="financials")
    monkeypatch.setattr(rotas, "regras_da_api", _regras_das_empresas)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    resposta = cliente.get(ROTA, headers=aj.bearer(chave.valor))
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_campo_sem_direito_nao_aparece(cliente, cenario, monkeypatch):
    regras = _regras_das_empresas()
    sem_o_motivo = tuple(
        linha
        for linha in regras.linhas
        if not (linha.conjunto == "companies" and linha.campo == "motivo_situacao")
    )
    monkeypatch.setattr(
        rotas,
        "regras_da_api",
        lambda: dataclasses.replace(regras, linhas=sem_o_motivo),
    )
    corpo = _get(cliente, cenario).json()
    assert "registration_status_reason" not in corpo
    assert corpo["registration_status"]["value"] == "08"


# ---------------------------------------------------------------- erros e consumo


def test_known_at_no_futuro_da_400(cliente, cenario):
    resposta = _get(cliente, cenario, known_at="2026-11-11")
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_known_at"}


def test_cnpj_invalido_da_400(cliente, cenario):
    resposta = _get(cliente, cenario, "/data/v1/companies/123")
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_cnpj"}


@pytest.mark.parametrize("rota", ["get", "lote"])
def test_chave_revogada_da_401(cliente, cenario, banco, rota):
    ator, org, chave = cenario
    with banco.begin() as conexao:
        cb.revogar_chave(
            conexao, organizacao_id=org.id, chave_id=chave.chave_id, ator_id=ator.id
        )
    if rota == "get":
        resposta = _get(cliente, cenario)
    else:
        resposta = _post(cliente, cenario, {"cnpjs": [EMPRESA]})
    assert resposta.status_code == 401


def test_base_fora_do_ar_da_503_sem_dizer_onde(cliente, cenario, monkeypatch):
    def sem_base(_banco):
        raise ValueError("acervo desligado (TICKERLAB_ACERVO): a porta não tem base")

    monkeypatch.setattr(rotas, "abrir_porta", sem_base)
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 503
    assert resposta.json() == {"detail": "service_unavailable"}


@pytest.mark.parametrize("pedido", ["get", "lote"])
def test_falha_na_leitura_da_base_da_503_e_nao_conta(
    cliente, cenario, banco, monkeypatch, pedido
):
    def arquivo_quebrado(*_args, **_kwargs):
        raise duckdb.IOException("arquivo corrompido em /caminho/do/servidor")

    monkeypatch.setattr(Porta, "ler", arquivo_quebrado)
    _ator, org, _chave = cenario
    if pedido == "get":
        resposta = _get(cliente, cenario)
    else:
        resposta = _post(cliente, cenario, {"cnpjs": [EMPRESA]})
    assert resposta.status_code == 503
    assert resposta.json() == {"detail": "service_unavailable"}
    assert _pedidos_do_mes(banco, org) == 0


def test_uma_empresa_conta_um_pedido_e_uma_linha(cliente, cenario, banco):
    _ator, org, _chave = cenario
    assert _get(cliente, cenario).status_code == 200
    with banco.connect() as conexao:
        consumo = cb.consumo_do_mes(conexao, org.id, AGORA.date())
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (1, 1, 0)


def test_empresa_que_nao_sai_conta_como_negada(cliente, cenario, banco):
    _ator, org, _chave = cenario
    _get(cliente, cenario, f"/data/v1/companies/{MEI}")
    with banco.connect() as conexao:
        consumo = cb.consumo_do_mes(conexao, org.id, AGORA.date())
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (
        0,
        0,
        1,
    )  # o negado não gasta a quota


# ---------------------------------------------------------------- o lote


def test_lote_de_empresas_com_status_por_item(cliente, cenario, banco):
    _ator, org, _chave = cenario
    resposta = _post(
        cliente,
        cenario,
        {
            "cnpjs": [EMPRESA, "x", MEI, _formatado(EMPRESA), FORA_DA_REDE],
            "known_at": "2025-07-15",
        },
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["known_at"] == "2025-07-15"
    itens = corpo["items"]
    assert [(i["cnpj"], i["status"]) for i in itens] == [
        (EMPRESA, "ok"),
        (MEI, "not_available"),
        (FORA_DA_REDE, "not_available"),
        ("x", "invalid_cnpj"),
    ]
    assert (
        itens[0]["registration_status"]["value"] == "02"
    )  # o known_at vale para o lote
    assert set(itens[1]) == set(itens[2]) == {"cnpj", "status"}
    assert _pedidos_do_mes(banco, org) == 3  # os 3 CNPJs válidos e distintos
    assert [f["source"] for f in corpo["sources"]] == ["rfb-cnpj"]


def test_lote_acima_do_teto_da_400(cliente, cenario):
    resposta = _post(cliente, cenario, {"cnpjs": [EMPRESA] * 101})
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_batch"}


def test_lote_que_passa_da_quota_volta_inteiro(cliente, cenario, banco):
    _ator, org, chave = cenario
    with banco.begin() as conexao:
        contexto = cb.conferir_chave(conexao, chave.valor, agora=AGORA)
        cb.registrar_consumo(
            conexao, contexto, conjunto="companies", finalidade="analise", linhas=0,
            pedidos=10_000 - 1, agora=AGORA,
        )  # fmt: skip
    resposta = _post(cliente, cenario, {"cnpjs": [EMPRESA, MEI]})
    assert resposta.status_code == 429
    assert resposta.json() == {"detail": "monthly_quota_exceeded"}
    assert _pedidos_do_mes(banco, org) == 10_000 - 1


def test_o_conjunto_e_o_do_catalogo():
    assert empresas.CONJUNTO == "companies"
    assert acesso is not None
