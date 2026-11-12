"""A rota dos ativos (linha 845): `/data/v1/companies/{cnpj}/assets`.

O leitor (`conjuntos/ativos.py`) tem os testes dele em `test_api_externa_por_cnpj_ativos.py`; aqui fica o que
é da rota: chave, contrato de `assets`, portão com as linhas de verdade (a ANM fica sem linha de direito até a
leitura dos termos), nomes de fora, consumo e os erros. Base de mentira, sem internet (a mesma do leitor).
Riscos: vazar pessoa (o 404 de MEI e de quem a rede trata como pessoa é igual ao de um CNPJ que não existe; o
nome do sócio da ANP nunca sai) e olhar o futuro (nada publicado depois de `known_at` sai).
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
from src.api_externa.conjuntos import ativos, empresas
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_por_cnpj_ativos as ativos_de_mentira

AGORA = empresas_de_mentira.AGORA
ALFA = ativos_de_mentira.ALFA
DIA = ativos_de_mentira.DIA.isoformat()
TABELAS_PRONTAS = ("anp_concessionarios", "anm_sigbm_barragens", "anm_cfem_arrecadacao")
# no dia: o contrato 002/2015 (pela filial) e o 001/2010, já na fase de produção
CONTRATOS_NO_DIA = 2


def _rota(cnpj: str = ALFA) -> str:
    return f"/data/v1/companies/{cnpj}/assets"


def _regras(tabelas=TABELAS_PRONTAS) -> portao.Regras:
    """As regras de verdade, com as tabelas dos ativos prontas no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = ativos_de_mentira.gravar_base(tmp_path / "base")
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    """Uma organização com chave e contrato de `assets`, e as tabelas prontas."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=ativos.CONJUNTO)
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


def test_contratos_saem_em_ingles_com_fonte_data_e_atribuicao(cliente, cenario):
    resposta = _get(cliente, cenario, known_at=DIA)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cnpj"] == ALFA and corpo["known_at"] == DIA
    assert corpo["limits"] == list(ativos.LIMITES)
    assert corpo["not_covered"][-len(ativos.NAO_COBERTO) :] == list(ativos.NAO_COBERTO)
    bloco = corpo["oil_gas_contracts"]
    assert bloco["found"] is True and bloco["truncated"] is False
    assert bloco["source"] == "anp-concessionarios"
    assert bloco["latest_published_at"] == "2025-03-01"
    assert bloco["coverage"]
    numeros = [item["contract_number"]["value"] for item in bloco["items"]]
    assert numeros == ["48000.002/2015", "48000.001/2010"]
    contrato = bloco["items"][1]
    assert set(contrato) == {
        "contract_number", "bid_round", "phase", "field_or_block_name", "basin", "onshore_offshore",
        "contract_share_pct", "is_operator",
    }  # fmt: skip
    assert contrato["phase"] == {
        "value": "Produção", "source": "anp-concessionarios", "published_at": "2025-03-01",
        "observed_at": "2025-03-01",
    }  # fmt: skip
    assert contrato["contract_share_pct"]["value"] == 60.0
    assert contrato["is_operator"]["value"] is True
    atribuicoes = {f["source"]: f["attribution"] for f in corpo["sources"]}
    assert set(atribuicoes) == {"anp-concessionarios"}
    assert "ANP" in atribuicoes["anp-concessionarios"]


def test_a_anm_fica_sem_linha_de_direito_ate_a_leitura_dos_termos(cliente, cenario):
    corpo = _get(cliente, cenario, known_at=DIA).json()
    assert "mining_dams" not in corpo and "mining_royalties" not in corpo
    assert "BARRAGEM UM" not in repr(corpo) and "830.001/2001" not in repr(corpo)
    # a ausência não pode ser lida como "a empresa não tem barragem": a resposta diz que a rota não cobre
    mineracao = [
        frase for frase in corpo["not_covered"] if frase.startswith("Mineração")
    ]
    assert mineracao == [
        ativos.FORA_DA_ROTA[ativos.BARRAGENS],
        ativos.FORA_DA_ROTA[ativos.ROYALTIES],
    ]
    assert not any("petróleo" in frase for frase in corpo["not_covered"])


def test_known_at_no_passado_nao_mostra_o_que_veio_depois(cliente, cenario):
    corpo = _get(cliente, cenario, known_at=DIA).json()
    itens = corpo["oil_gas_contracts"]["items"]
    envelopes = [envelope for item in itens for envelope in item.values()]
    assert envelopes and all(e["published_at"] <= DIA for e in envelopes)
    assert "48000.003/2025" not in {item["contract_number"]["value"] for item in itens}


def test_sem_known_at_vale_hoje(cliente, cenario):
    corpo = _get(cliente, cenario).json()
    assert corpo["known_at"] == AGORA.date().isoformat()
    numeros = {
        item["contract_number"]["value"] for item in corpo["oil_gas_contracts"]["items"]
    }
    assert "48000.003/2025" in numeros


def test_empresa_sem_ativo_na_base_diz_que_nao_achou(cliente, cenario):
    resposta = _get(cliente, cenario, _rota(ativos_de_mentira.VAZIA), known_at=DIA)
    assert resposta.status_code == 200
    bloco = resposta.json()["oil_gas_contracts"]
    assert bloco["found"] is False and bloco["items"] == []
    assert bloco["latest_published_at"] == "2025-03-01"


# ---------------------------------------------------------------- sem pessoa


@pytest.mark.parametrize(
    "cnpj",
    [ativos_de_mentira.PESSOA, ativos_de_mentira.MEI, ativos_de_mentira.FORA_DA_REDE],
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
    resposta = _get(cliente, cenario)
    corpo = resposta.json()
    conferir_sem_pessoas(corpo, set())
    assert not aj.chaves_de(corpo) & COLUNAS_DE_PESSOA
    assert ativos_de_mentira.NOME_DO_SOCIO not in resposta.text
    assert ativos_de_mentira.NOME_DO_EMPREENDEDOR not in resposta.text


# ---------------------------------------------------------------- o portão


def test_ativos_suspensos_dao_o_mesmo_404_de_quem_nao_existe(cliente, cenario, banco):
    inexistente = _get(
        cliente, cenario, _rota(empresas_de_mentira.INEXISTENTE), known_at=DIA
    )
    ator, _org, _chave = cenario
    with banco.begin() as conexao:
        cb.suspender_conjunto(
            conexao, conjunto=ativos.CONJUNTO, motivo="fonte", ator_id=ator.id
        )
    negado = _get(cliente, cenario, known_at=DIA)
    assert negado.status_code == 404
    assert negado.json() == inexistente.json()


def test_hoje_sem_a_prontidao_nada_sai(cliente, cenario, monkeypatch):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: None)  # as regras de verdade
    resposta = _get(cliente, cenario, known_at=DIA)
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_contrato_de_companies_nao_abre_os_ativos(banco, monkeypatch, pasta):
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
    sem_a_participacao = tuple(
        linha
        for linha in regras.linhas
        if not (linha.conjunto == ativos.CONJUNTO and linha.campo == "participacao_pct")
    )
    monkeypatch.setattr(
        rotas,
        "regras_da_api",
        lambda: dataclasses.replace(regras, linhas=sem_a_participacao),
    )
    itens = _get(cliente, cenario, known_at=DIA).json()["oil_gas_contracts"]["items"]
    assert itens and all("contract_share_pct" not in item for item in itens)


# ---------------------------------------------------------------- erros e consumo


def test_um_pedido_conta_os_itens_servidos(cliente, cenario, banco):
    _ator, org, _chave = cenario
    _get(cliente, cenario, known_at=DIA)
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (
        1,
        CONTRATOS_NO_DIA,
        0,
    )


def test_o_404_conta_como_negado_sem_gastar_a_quota(cliente, cenario, banco):
    _ator, org, _chave = cenario
    _get(cliente, cenario, _rota(ativos_de_mentira.PESSOA), known_at=DIA)
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (0, 0, 1)


def test_known_at_no_futuro_da_400_sem_gastar_a_quota(cliente, cenario, banco):
    _ator, org, _chave = cenario
    amanha = date.fromordinal(AGORA.date().toordinal() + 1).isoformat()
    resposta = _get(cliente, cenario, known_at=amanha)
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_known_at"}
    assert _consumo(banco, org).pedidos == 0


def test_cnpj_invalido_da_400(cliente, cenario):
    resposta = _get(cliente, cenario, _rota("123"))
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_cnpj"}


def test_sem_chave_da_401(cliente, cenario):
    assert cliente.get(_rota()).status_code == 401
