"""A rota dos comparáveis (linha 736, PR 3): `/data/v1/companies/{cnpj}/comparables`.

O leitor (`conjuntos/comparaveis.py`) tem os testes dele em `test_api_externa_por_cnpj_comparaveis.py`; aqui
fica o que é da rota: chave, contrato de `comparables`, portão com as linhas de verdade, nomes de fora,
consumo e os erros. Base de mentira, sem internet (a mesma do leitor). Riscos: vazar pessoa (o 404 de quem a
rede trata como pessoa é igual ao de um CNPJ que não existe) e olhar o futuro (nada publicado depois de
`known_at` sai).
"""

import dataclasses
from datetime import date

import pytest

from base import prontidao
from base.dossie import COLUNAS_DE_PESSOA, conferir_sem_pessoas
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import rotas
from src.api_externa.conjuntos import comparaveis, empresas
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_por_cnpj_comparaveis as comparaveis_de_mentira

AGORA = empresas_de_mentira.AGORA
ALFA = comparaveis_de_mentira.ALFA
PARES = comparaveis_de_mentira.PARES
DIA = comparaveis_de_mentira.DIA.isoformat()
TABELAS_PRONTAS = (comparaveis.TABELA_DO_CADASTRO, comparaveis.TABELA_DAS_DEMONSTRACOES)


def _rota(cnpj: str = ALFA) -> str:
    return f"/data/v1/companies/{cnpj}/comparables"


def _regras(tabelas=TABELAS_PRONTAS) -> portao.Regras:
    """As regras de verdade, com as tabelas dos comparáveis prontas (provas do D10) no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = comparaveis_de_mentira.gravar_base(tmp_path / "base")
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    """Uma organização com chave e contrato de `comparables`, e as tabelas prontas."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=comparaveis.CONJUNTO)
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    return ator, org, chave


@pytest.fixture
def cliente(monkeypatch, cenario):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, cenario, rota: str | None = None, **parametros):
    _ator, _org, chave = cenario
    return cliente.get(
        rota or _rota(), params=parametros, headers=aj.bearer(chave.valor)
    )


def _consumo(banco, org):
    with banco.connect() as conexao:
        return cb.consumo_do_mes(conexao, org.id, AGORA.date())


# ---------------------------------------------------------------- o que sai


def test_comparaveis_saem_em_ingles_com_fonte_data_e_atribuicao(cliente, cenario):
    resposta = _get(cliente, cenario, known_at=DIA)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cnpj"] == ALFA and corpo["known_at"] == DIA
    assert corpo["sector_group"]["value"] == "electric_power"
    pedida = corpo["subject_company"]
    assert pedida["company_name"]["value"] == "ALFA ENERGIA S.A."
    assert pedida["revenue"] == {
        "value": 1000.0, "source": "cvm-hist-dfp", "published_at": "2025-03-20", "observed_at": None,
    }  # fmt: skip
    assert pedida["ebitda"]["value"] == 250.0
    assert pedida["net_debt_to_ebitda"]["value"] == pytest.approx(2.4)
    assert pedida["fiscal_year_end"]["value"] == "2024-12-31"
    assert len(corpo["peers"]) == len(PARES) and corpo["truncated"] is False
    assert set(corpo["peer_medians"]) == {
        "ebitda_margin", "net_margin", "return_on_equity", "net_debt_to_ebitda",
    }  # fmt: skip
    assert corpo["limits"] == list(comparaveis.LIMITES)
    atribuicoes = {f["source"]: f["attribution"] for f in corpo["sources"]}
    assert set(atribuicoes) == {"cvm-hist-fca", "cvm-hist-dfp"}
    assert all("CVM" in texto for texto in atribuicoes.values())


def test_known_at_no_passado_nao_mostra_o_que_veio_depois(cliente, cenario):
    corpo = _get(cliente, cenario, known_at=DIA).json()
    envelopes = [
        corpo["sector_group"],
        *corpo["subject_company"].values(),
        *(e for par in corpo["peers"] for e in par.values()),
        *corpo["peer_medians"].values(),
    ]
    assert all(e["published_at"] <= DIA for e in envelopes)


def test_sem_known_at_vale_hoje(cliente, cenario):
    """Hoje a ALFA já informou outro setor (FCA de 2025): os pares de energia não são mais dela."""
    corpo = _get(cliente, cenario).json()
    assert corpo["known_at"] == AGORA.date().isoformat()
    assert corpo["sector_group"]["value"] == "trade"
    assert corpo["peers"] == []


def test_numeros_sem_prontidao_nao_saem_e_o_cadastro_continua(
    cliente, cenario, monkeypatch
):
    monkeypatch.setattr(
        rotas, "regras_da_api", lambda: _regras((comparaveis.TABELA_DO_CADASTRO,))
    )
    corpo = _get(cliente, cenario, known_at=DIA).json()
    assert set(corpo["subject_company"]) == {"cnpj", "company_name", "sector"}
    assert "peer_medians" not in corpo
    assert {f["source"] for f in corpo["sources"]} == {"cvm-hist-fca"}


# ---------------------------------------------------------------- sem pessoa


@pytest.mark.parametrize(
    "cnpj",
    [comparaveis_de_mentira.TRATADA_COMO_PESSOA, comparaveis_de_mentira.FORA_DA_REDE],
)
def test_pessoa_e_quem_nao_e_empresa_dao_o_mesmo_404_de_quem_nao_existe(
    cliente, cenario, cnpj
):
    inexistente = _get(
        cliente, cenario, _rota(empresas_de_mentira.INEXISTENTE), known_at=DIA
    )
    resposta = _get(cliente, cenario, _rota(cnpj), known_at=DIA)
    assert resposta.status_code == inexistente.status_code == 404
    assert resposta.json() == inexistente.json() == {"detail": "not_available"}


def test_sem_pessoa_na_resposta(cliente, cenario):
    corpo = _get(cliente, cenario, known_at=DIA).json()
    conferir_sem_pessoas(corpo, set())
    assert not aj.chaves_de(corpo) & COLUNAS_DE_PESSOA
    pares = {par["cnpj"]["value"] for par in corpo["peers"]}
    assert comparaveis_de_mentira.TRATADA_COMO_PESSOA not in pares


# ---------------------------------------------------------------- o portão


def test_comparaveis_suspensos_dao_o_mesmo_404_de_quem_nao_existe(
    cliente, cenario, banco
):
    inexistente = _get(
        cliente, cenario, _rota(empresas_de_mentira.INEXISTENTE), known_at=DIA
    )
    ator, _org, _chave = cenario
    with banco.begin() as conexao:
        cb.suspender_conjunto(
            conexao, conjunto=comparaveis.CONJUNTO, motivo="fonte", ator_id=ator.id
        )
    negado = _get(cliente, cenario, known_at=DIA)
    assert negado.status_code == 404
    assert negado.json() == inexistente.json()


def test_hoje_sem_a_prontidao_nada_sai(cliente, cenario, monkeypatch):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: None)  # as regras de verdade
    resposta = _get(cliente, cenario, known_at=DIA)
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_contrato_de_companies_nao_abre_os_comparaveis(banco, monkeypatch, pasta):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=empresas.CONJUNTO)
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    resposta = cliente.get(
        _rota(), params={"known_at": DIA}, headers=aj.bearer(chave.valor)
    )
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_campo_sem_direito_nao_aparece(cliente, cenario, monkeypatch):
    regras = _regras()
    sem_o_roe = tuple(
        linha
        for linha in regras.linhas
        if not (linha.conjunto == comparaveis.CONJUNTO and linha.campo == "roe")
    )
    monkeypatch.setattr(
        rotas, "regras_da_api", lambda: dataclasses.replace(regras, linhas=sem_o_roe)
    )
    corpo = _get(cliente, cenario, known_at=DIA).json()
    assert corpo["peers"]
    assert "return_on_equity" not in corpo["subject_company"]
    assert all("return_on_equity" not in par for par in corpo["peers"])
    assert "return_on_equity" not in corpo["peer_medians"]


# ---------------------------------------------------------------- erros e consumo


def test_um_pedido_conta_a_empresa_e_os_pares(cliente, cenario, banco):
    _ator, org, _chave = cenario
    _get(cliente, cenario, known_at=DIA)
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (1, 1 + len(PARES), 0)


def test_o_404_conta_como_negado_sem_gastar_a_quota(cliente, cenario, banco):
    _ator, org, _chave = cenario
    _get(
        cliente,
        cenario,
        _rota(comparaveis_de_mentira.TRATADA_COMO_PESSOA),
        known_at=DIA,
    )
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (0, 0, 1)


def test_known_at_no_futuro_da_400(cliente, cenario):
    amanha = date.fromordinal(AGORA.date().toordinal() + 1).isoformat()
    resposta = _get(cliente, cenario, known_at=amanha)
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_known_at"}


def test_cnpj_invalido_da_400(cliente, cenario):
    resposta = _get(cliente, cenario, _rota("123"))
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_cnpj"}


def test_sem_chave_da_401(cliente, cenario):
    assert cliente.get(_rota()).status_code == 401


# ---------------------------------------------------------------- número não disponível (linha 881)


def _sem_o_roe(regras: portao.Regras) -> portao.Regras:
    linhas = tuple(
        linha
        for linha in regras.linhas
        if not (linha.conjunto == comparaveis.CONJUNTO and linha.campo == "roe")
    )
    return dataclasses.replace(regras, linhas=linhas)


@pytest.fixture
def duas(banco, monkeypatch, pasta):
    """Duas organizações: uma com o contrato de `comparables`, outra só com o de `companies`; o portão sem a
    linha do ROE (como uma linha de direito retirada)."""
    ator = aj.admin(banco)
    com_comparaveis = aj.organizacao(banco, ator, "Organização com comparáveis")
    so_de_companies = aj.organizacao(banco, ator, "Organização sem comparáveis")
    aj.contrato(banco, ator, com_comparaveis, conjunto=comparaveis.CONJUNTO)
    aj.contrato(banco, ator, so_de_companies, conjunto=empresas.CONJUNTO)
    regras = _sem_o_roe(_regras())
    monkeypatch.setattr(rotas, "regras_da_api", lambda: regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return (
        cliente,
        aj.chave(banco, ator, com_comparaveis).valor,
        aj.chave(banco, ator, so_de_companies).valor,
    )


def test_com_tudo_liberado_a_lista_de_fora_sai_vazia(cliente, cenario):
    corpo = _get(cliente, cenario, known_at=DIA).json()
    assert corpo["unavailable_figures"] == []
    assert corpo["limits"] == list(comparaveis.LIMITES)


def test_a_razao_barrada_vem_como_nao_disponivel_e_a_mediana_nao_le_como_poucos_pares(
    duas,
):
    cliente, com_comparaveis, _so_de_companies = duas
    resposta = cliente.get(
        _rota(), params={"known_at": DIA}, headers=aj.bearer(com_comparaveis)
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "return_on_equity" not in corpo["peer_medians"]
    assert corpo["unavailable_figures"] == ["return_on_equity"]
    assert comparaveis.LIMITE_DO_NUMERO_NAO_DISPONIVEL in corpo["limits"]
    assert "unavailable_figures" in comparaveis.LIMITE_DO_NUMERO_NAO_DISPONIVEL


def test_a_organizacao_sem_o_contrato_recebe_404_e_nao_a_lista(duas):
    cliente, _com_comparaveis, so_de_companies = duas
    resposta = cliente.get(
        _rota(), params={"known_at": DIA}, headers=aj.bearer(so_de_companies)
    )
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_numeros_sem_prontidao_vem_todos_como_nao_disponiveis(
    cliente, cenario, monkeypatch
):
    monkeypatch.setattr(
        rotas, "regras_da_api", lambda: _regras((comparaveis.TABELA_DO_CADASTRO,))
    )
    corpo = _get(cliente, cenario, known_at=DIA).json()
    assert "peer_medians" not in corpo
    assert "revenue" in corpo["unavailable_figures"]
    assert "return_on_equity" in corpo["unavailable_figures"]
    assert not any("8 pares" in limite for limite in corpo["limits"])
