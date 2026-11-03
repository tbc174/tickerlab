"""O raio-x de fundo na API externa (B-32a, PR 5): `/data/v1/funds/{cnpj}` e `/data/v1/funds/batch`.

Base de mentira, sem internet; os CNPJs são de ninguém. As linhas de direito são as de verdade
(`DIREITOS_DA_API_EXTERNA`); o teste só põe as duas tabelas dos fundos prontas (D10), como a A7 fará.
Riscos do plano: olhar o futuro (a carteira e o cadastro "como eram" em `known_at`), um retorno escondido
no custo da taxa e o lote contando 1 na quota.
"""

import dataclasses
import hashlib
from datetime import UTC, datetime

import pandas as pd
import pytest

from base import prontidao
from base.parquet import gravar_tabela
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src import versao_do_codigo as vc
from src.api_externa import acesso, rotas
from src.banco import chaves_da_api as cb
from src.banco.coletas import registrar
from src.ferramentas.custos import custo_da_taxa
from tests import ajudantes_da_api_externa as aj

AGORA = datetime(2026, 11, 10, 12, tzinfo=UTC)  # o beta começa em 03/11
BAIXADO_EM = datetime(2026, 11, 5, 3, tzinfo=UTC)  # o dia do retrato do cadastro
FUNDO = "11111111000191"
OUTRO = "22222222000191"
SEM_CADASTRO = "33333333000191"
URL_DO_CADASTRO = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv"
ORIGINAL = b"CNPJ_FUNDO;DENOM_SOCIAL\n"  # o conteudo baixado: so o hash importa aqui
TABELAS_DOS_FUNDOS = ("cadastro_de_fundos", "carteiras_dos_fundos")
ROTA = f"/data/v1/funds/{FUNDO}"
LOTE = "/data/v1/funds/batch"


def _formatado(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def _cadastro() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "TP_FUNDO": ["FI", "FI"],
            "CNPJ_FUNDO": [_formatado(FUNDO), _formatado(OUTRO)],
            "DENOM_SOCIAL": ["FUNDO UM", "FUNDO DOIS"],
            "DT_REG": pd.to_datetime(["2015-01-01", "2015-01-01"]),
            "CLASSE": ["Ações", "Renda Fixa"],
            "SIT": ["EM FUNCIONAMENTO NORMAL"] * 2,
            "TAXA_ADM": [2.0, 0.5],
            "TAXA_PERFM": [20.0, None],
            "INF_TAXA_ADM": ["2% ao ano", None],
            "INF_TAXA_PERFM": ["20% sobre o que passar do Ibovespa", None],
            "VL_PATRIM_LIQ": [1_000_000.0, 5.0],
            "DT_PATRIM_LIQ": pd.to_datetime(["2026-09-30", "2026-09-30"]),
        }
    )


def _carteira() -> pd.DataFrame:
    """Três competências do FUNDO (a última só ficou pública em 2026, vista pelo arquivista)."""
    linhas = [
        (FUNDO, "2024-01-31", "PETR4", 100.0, "2024-05-01", None),
        (FUNDO, "2024-01-31", "VALE3", 50.0, "2024-05-01", None),
        (FUNDO, "2024-02-29", "PETR4", 80.0, "2024-05-30", None),
        (FUNDO, "2026-02-28", "ITUB4", 999.0, "2026-05-29", "2026-05-20"),
        (FUNDO, "2026-02-28", "WEGE3", 9.0, "2026-05-29", "2026-05-20"),
        (OUTRO, "2024-02-29", "BBAS3", 7.0, "2024-05-30", None),
    ]
    return pd.DataFrame(
        {
            "competencia": pd.to_datetime([x[1] for x in linhas]),
            "cnpj_fundo": [_formatado(x[0]) for x in linhas],
            "tipo_do_fundo": "FI",
            "fundo": "NOME",
            "tipo": "comprado",
            "codigo": [x[2] for x in linhas],
            "isin": "BRXXXXACNOR0",
            "emissor": "XXXX",
            "descricao": "ACAO ON",
            "quantidade": 1.0,
            "valor": [x[3] for x in linhas],
            "compras": 0.0,
            "vendas": 0.0,
            "confidencial_ate": pd.NaT,
            "disponivel_em": pd.to_datetime([x[4] for x in linhas]),
            "visto_em": pd.to_datetime([x[5] for x in linhas]),
        }
    )


@pytest.fixture
def pasta(tmp_path, banco, monkeypatch):
    """A base de mentira e a coleta do cadastro no registro (a linhagem diz o dia do retrato)."""
    monkeypatch.setenv(vc.VARIAVEL, "7ddaf09c1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b")
    with banco.begin() as conexao:
        registrar(
            conexao, "cvm-cadastros", URL_DO_CADASTRO, ORIGINAL, "ok", agora=BAIXADO_EM
        )
    base = tmp_path / "base"
    origem = {"url": URL_DO_CADASTRO, "sha256": hashlib.sha256(ORIGINAL).hexdigest()}
    gravar_tabela(_cadastro(), base / "fidc/cadastro/cad_fi", [origem], ["CNPJ_FUNDO"])
    for ano in (2024, 2026):
        arquivo = base / "cda" / f"{ano}.parquet"
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        _carteira()[lambda d, a=ano: d.competencia.dt.year == a].to_parquet(
            arquivo, index=False
        )
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


def _regras_dos_fundos() -> portao.Regras:
    """As regras de verdade, com as duas tabelas dos fundos prontas (provas do D10) no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={
            t: Prontidao(versoes[t], prova, prova, prova) for t in TABELAS_DOS_FUNDOS
        },
    )


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    """Uma organização com chave e contrato de `funds`, e as tabelas dos fundos prontas."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto="funds")
    monkeypatch.setattr(rotas, "regras_da_api", _regras_dos_fundos)
    return ator, org, chave


@pytest.fixture
def cliente(monkeypatch, cenario):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, cenario, rota: str = ROTA, **parametros):
    _ator, _org, chave = cenario
    return cliente.get(rota, params=parametros, headers=aj.bearer(chave.valor))


def _codigos(corpo: dict) -> list[str]:
    return [p["code"]["value"] for p in corpo["holdings"]["positions"]]


def _pedidos_do_mes(banco, org) -> int:
    with banco.connect() as conexao:
        return cb.consumo_do_mes(conexao, org.id, AGORA.date()).pedidos


# ---------------------------------------------------------------- um fundo


def test_fundo_sai_com_fonte_data_e_atribuicao_em_ingles(cliente, cenario):
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cnpj"] == FUNDO
    assert corpo["known_at"] == "2026-11-10"
    assert corpo["profile"]["management_fee_pct_per_year"] == {
        "value": 2.0,
        "source": "cvm-cadastros",
        "published_at": "2026-11-05",
        "observed_at": "2026-11-05T03:00:00+00:00",
    }
    assert corpo["profile"]["class"]["value"] == "Ações"
    fontes = {f["source"]: f for f in corpo["sources"]}
    assert set(fontes) == {"cvm-cadastros", "cvm-cda-recente"}
    assert all("CVM" in f["attribution"] for f in fontes.values())


def test_cda_como_era_respeita_disponivel_em(cliente, cenario):
    # a carteira de 2026-02-28 só ficou pública em 2026-05-29; em 2025-01-01 vale a de fev/2024
    corpo = _get(cliente, cenario, known_at="2025-01-01").json()
    assert _codigos(corpo) == ["PETR4"]
    posicao = corpo["holdings"]["positions"][0]
    assert posicao["reporting_month"]["value"] == "2024-02-29"
    assert posicao["value"]["published_at"] == "2024-05-30"
    assert posicao["value"]["source"] == "cvm-hist-cda"
    assert posicao["value"]["observed_at"] is None
    # cortar o futuro não muda o passado
    de_novo = _get(cliente, cenario, known_at="2026-05-28").json()
    assert de_novo["holdings"] == corpo["holdings"]


def test_carteira_vista_pelo_arquivista_sai_como_cda_recente(cliente, cenario):
    corpo = _get(cliente, cenario).json()
    assert _codigos(corpo) == ["ITUB4", "WEGE3"]
    posicao = corpo["holdings"]["positions"][0]
    assert posicao["code"]["source"] == "cvm-cda-recente"
    assert posicao["code"]["observed_at"] == "2026-05-20"


def test_cadastro_antes_do_retrato_da_not_available(cliente, cenario):
    # o cadastro é o retrato baixado em 05/11: antes disso as taxas não são observáveis
    corpo = _get(cliente, cenario, known_at="2026-11-04", assumed_return=0.08).json()
    assert "profile" not in corpo
    assert "fee_cost" not in corpo
    assert _codigos(corpo) == ["ITUB4", "WEGE3"]  # a carteira já era pública


def test_cadastro_sem_coleta_registrada_nao_sai(cliente, cenario, banco):
    # sem a coleta no registro não há data de publicação: o campo não sai (nem com data inventada)
    with banco.begin() as conexao:
        conexao.exec_driver_sql("DELETE FROM coletas")
    corpo = _get(cliente, cenario, assumed_return=0.08).json()
    assert "profile" not in corpo
    assert "fee_cost" not in corpo
    assert _codigos(corpo) == ["ITUB4", "WEGE3"]


def test_known_at_no_futuro_da_400(cliente, cenario):
    resposta = _get(cliente, cenario, known_at="2026-11-11")
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_known_at"}


def test_cnpj_invalido_da_400(cliente, cenario):
    resposta = _get(cliente, cenario, "/data/v1/funds/11111111000192")
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_cnpj"}


# ---------------------------------------------------------------- o custo da taxa


def test_custo_da_taxa_exige_assumed_return(cliente, cenario):
    # sem retorno dado pelo cliente não há conta: nada de retorno escondido
    assert "fee_cost" not in _get(cliente, cenario).json()
    for errado in (-1, -1.5, 1.01):
        resposta = _get(cliente, cenario, assumed_return=errado)
        assert resposta.status_code == 400, errado
        assert resposta.json() == {"detail": "invalid_assumed_return"}


def test_custo_da_taxa_bate_com_custos_py(cliente, cenario):
    corpo = _get(cliente, cenario, assumed_return=0.08).json()
    custo = corpo["fee_cost"]
    assert custo["assumptions"] == {"initial_amount": 10_000.0, "assumed_return": 0.08}
    por_prazo = {h["years"]: h for h in custo["horizons"]}
    assert set(por_prazo) == {5, 20}
    for anos, prazo in por_prazo.items():
        esperado = custo_da_taxa(10_000.0, 0.08, 0.02, anos)
        assert prazo["with_fee"]["value"] == pytest.approx(esperado.com_taxa)
        assert prazo["without_fee"]["value"] == pytest.approx(esperado.sem_taxa)
        assert prazo["fee_amount"]["value"] == pytest.approx(esperado.ficou_com_a_taxa)
        assert prazo["fee_share_of_return"]["value"] == pytest.approx(
            esperado.fracao_do_resultado
        )
        assert prazo["with_fee"]["source"] == "cvm-cadastros"
        assert prazo["with_fee"]["published_at"] == "2026-11-05"


# ---------------------------------------------------------------- o que não sai


def test_fundo_inexistente_e_fundo_negado_dao_o_mesmo_404(cliente, cenario, banco):
    inexistente = _get(cliente, cenario, f"/data/v1/funds/{SEM_CADASTRO}")
    assert inexistente.status_code == 404
    assert inexistente.json() == {"detail": "not_available"}
    ator, _org, _chave = cenario
    with banco.begin() as conexao:
        cb.suspender_conjunto(
            conexao, conjunto="funds", motivo="fonte", ator_id=ator.id
        )
    negado = _get(cliente, cenario)
    assert negado.status_code == 404
    assert negado.json() == inexistente.json()


def test_hoje_sem_a_prontidao_nada_sai(cliente, cenario, monkeypatch):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: None)  # as regras de verdade
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_organizacao_sem_contrato_de_funds_recebe_404(banco, monkeypatch, pasta):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto="financials")
    monkeypatch.setattr(rotas, "regras_da_api", _regras_dos_fundos)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    resposta = cliente.get(ROTA, headers=aj.bearer(chave.valor))
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


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
        resposta = cliente.post(
            LOTE, json={"cnpjs": [FUNDO]}, headers=aj.bearer(chave.valor)
        )
    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "invalid_api_key"}


def test_base_fora_do_ar_da_503_sem_dizer_onde(cliente, cenario, monkeypatch):
    def sem_base(_banco):
        raise ValueError("acervo desligado (TICKERLAB_ACERVO): a porta não tem base")

    monkeypatch.setattr(rotas, "abrir_porta", sem_base)
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 503
    assert resposta.json() == {"detail": "service_unavailable"}


# ---------------------------------------------------------------- consumo e limite


def test_um_fundo_conta_um_pedido_e_as_linhas_servidas(cliente, cenario, banco):
    _ator, org, _chave = cenario
    assert _get(cliente, cenario).status_code == 200
    with banco.connect() as conexao:
        consumo = cb.consumo_do_mes(conexao, org.id, AGORA.date())
    assert consumo.pedidos == 1
    assert consumo.linhas == 3  # o cadastro e as duas posições


def test_posicoes_cortadas_no_limite_do_plano(cliente, cenario, monkeypatch):
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda _contexto: 1)
    corpo = _get(cliente, cenario).json()
    assert _codigos(corpo) == ["ITUB4"]
    assert corpo["holdings"]["truncated"] is True


# ---------------------------------------------------------------- o lote


def test_lote_de_fundos(cliente, cenario, banco):
    _ator, org, chave = cenario
    resposta = cliente.post(
        LOTE,
        json={
            "cnpjs": [FUNDO, "x", SEM_CADASTRO, _formatado(FUNDO), OUTRO],
            "known_at": "2025-01-01",
            "assumed_return": 0.08,
        },
        headers=aj.bearer(chave.valor),
    )
    assert resposta.status_code == 200
    itens = resposta.json()["items"]
    assert [(i["cnpj"], i["status"]) for i in itens] == [
        (FUNDO, "ok"),
        (SEM_CADASTRO, "not_available"),
        (OUTRO, "ok"),
        ("x", "invalid_cnpj"),
    ]
    assert _codigos(itens[0]) == ["PETR4"]  # o known_at vale para o lote inteiro
    assert "profile" not in itens[0]  # 2025: antes do retrato
    assert _codigos(itens[2]) == ["BBAS3"]
    assert set(itens[1]) == {"cnpj", "status"}  # o negado não diz nada além do código
    assert _pedidos_do_mes(banco, org) == 3  # os 3 CNPJs válidos e distintos
    fontes = {f["source"] for f in resposta.json()["sources"]}
    assert fontes == {"cvm-hist-cda"}


def test_lote_acima_do_teto_da_400(cliente, cenario):
    _ator, _org, chave = cenario
    resposta = cliente.post(
        LOTE, json={"cnpjs": [FUNDO] * 101}, headers=aj.bearer(chave.valor)
    )
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_batch"}


def test_lote_que_passa_da_quota_volta_inteiro(cliente, cenario, banco):
    _ator, org, chave = cenario
    with banco.begin() as conexao:
        contexto = cb.conferir_chave(conexao, chave.valor, agora=AGORA)
        cb.registrar_consumo(
            conexao, contexto, conjunto="funds", finalidade="analise", linhas=0,
            pedidos=10_000 - 1, agora=AGORA,
        )  # fmt: skip
    resposta = cliente.post(
        LOTE, json={"cnpjs": [FUNDO, OUTRO]}, headers=aj.bearer(chave.valor)
    )
    assert resposta.status_code == 429
    assert resposta.json() == {"detail": "monthly_quota_exceeded"}
    assert _pedidos_do_mes(banco, org) == 10_000 - 1
