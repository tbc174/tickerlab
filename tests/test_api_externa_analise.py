"""A rota da análise completa do CNPJ (frente 3, 18/11/2026): `/data/v1/companies/{cnpj}/analysis`.

A montagem tem os testes dela em `test_api_externa_analise_montagem.py` e o bloco de sócios PJ em
`test_api_externa_socios_pj.py`; aqui fica o que é da rota, com o portão e os contratos de verdade: só sai o
bloco que a organização pode ver (contrato do conjunto e tabela pronta), o bloco fechado não vaza pelo nome,
pela fonte nem pelo tamanho, cada bloco conta no conjunto dele, pessoa e CNPJ inexistente dão o mesmo 404 e
nada publicado depois de `known_at` sai. Base de mentira, sem internet.
"""

import dataclasses
from datetime import date

import pytest
import sqlalchemy as sa

from base import prontidao
from base.dossie import COLUNAS_DE_PESSOA, conferir_sem_pessoas
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import rotas
from src.api_externa.conjuntos import compradores, empresas, ficha
from src.banco.modelo import consumo_da_api
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_socios_pj as socios_de_mentira

AGORA = empresas_de_mentira.AGORA
EMPRESA = empresas_de_mentira.EMPRESA
INEXISTENTE = empresas_de_mentira.INEXISTENTE
DO_PERFIL = (
    *empresas.TABELAS,
    ficha.TABELA_DO_ESTABELECIMENTO,
    ficha.TABELA_DAS_ENTREGAS,
)
TUDO_PRONTO = (*DO_PERFIL, compradores.ENTRADAS)
# o que só o bloco de sócios PJ põe na resposta: nome de fora e dado da empresa
DO_BLOCO_DE_SOCIOS = ("corporate_ownership", "equity_holders", "equity_stakes")
# a exceção: fechado para a chave, o bloco das vizinhas vem só com o aviso (test_api_externa_vizinhas.py)
VIZINHAS = "same_industry_neighbors"


def _rota(cnpj: str = EMPRESA) -> str:
    return f"/data/v1/companies/{cnpj}/analysis"


def _regras(tabelas=TUDO_PRONTO) -> portao.Regras:
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = socios_de_mentira.base_com_socios(tmp_path)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


@pytest.fixture
def ator(banco):
    return aj.admin(banco)


def _organizacao(banco, ator, nome: str, *conjuntos: str):
    """Uma organização com chave e o contrato de análise de cada conjunto."""
    org = aj.organizacao(banco, ator, nome)
    chave = aj.chave(banco, ator, org)
    for conjunto in conjuntos:
        aj.contrato(banco, ator, org, conjunto=conjunto)
    return org, chave


@pytest.fixture
def cliente(monkeypatch, pasta):
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, chave, cnpj: str = EMPRESA, **parametros):
    return cliente.get(_rota(cnpj), params=parametros, headers=aj.bearer(chave.valor))


def _por_conjunto(banco, org) -> dict[str, tuple[int, int]]:
    """(pedidos, negados) do mês, por conjunto."""
    with banco.connect() as conexao:
        linhas = conexao.execute(
            sa.select(
                consumo_da_api.c.conjunto,
                sa.func.sum(consumo_da_api.c.pedidos),
                sa.func.sum(consumo_da_api.c.negados),
            )
            .where(consumo_da_api.c.organizacao_id == org.id)
            .group_by(consumo_da_api.c.conjunto)
        ).all()
    return {
        conjunto: (int(pedidos), int(negados)) for conjunto, pedidos, negados in linhas
    }


# ---------------------------------------------------------------- o que sai


def test_analise_junta_o_perfil_e_os_socios_com_fonte_data_e_nomes_de_fora(
    cliente, banco, ator
):
    org, chave = _organizacao(banco, ator, "Alfa", ficha.CONJUNTO, compradores.CONJUNTO)
    resposta = _get(cliente, chave, known_at="2025-06-30")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cnpj"] == EMPRESA
    assert corpo["known_at"] == "2025-06-30"
    assert set(corpo["blocks"]) == {"profile", "corporate_ownership", VIZINHAS}
    socias = corpo["blocks"]["corporate_ownership"]["equity_holders"]
    assert [s["cnpj_root"] for s in socias] == [socios_de_mentira.HOLDING]
    assert socias[0]["legal_name"]["source"] == "rfb-cnpj"
    assert corpo["summary"]["kind"] == "fact"
    assert corpo["summary"]["text"].startswith("ALFA")
    assert all(leitura["kind"] == "inference" for leitura in corpo["inferences"])
    assert corpo["requests_used"] == 2
    assert corpo["timed_out"] == []
    assert corpo["not_included"]
    assert {f["source"] for f in corpo["sources"]} >= {"rfb-cnpj", "cvm-hist-dfp"}
    assert _por_conjunto(banco, org) == {
        ficha.CONJUNTO: (1, 0),
        compradores.CONJUNTO: (1, 0),
    }


def test_sem_pessoa_na_resposta(cliente, banco, ator):
    _org, chave = _organizacao(
        banco, ator, "Alfa", ficha.CONJUNTO, compradores.CONJUNTO
    )
    corpo = _get(cliente, chave).json()
    conferir_sem_pessoas(corpo, set())
    assert not aj.chaves_de(corpo) & COLUNAS_DE_PESSOA
    texto = str(corpo)
    assert socios_de_mentira.SEM_LISTA not in texto
    assert socios_de_mentira.EMPRESARIO not in texto


def test_known_at_no_passado_nao_mostra_o_que_veio_depois(cliente, banco, ator):
    _org, chave = _organizacao(
        banco, ator, "Alfa", ficha.CONJUNTO, compradores.CONJUNTO
    )
    antes = _get(cliente, chave, known_at="2025-06-30").json()
    hoje = _get(cliente, chave).json()
    assert socios_de_mentira.FUTURA not in str(antes)
    assert socios_de_mentira.FUTURA in str(hoje)
    assert all(marco["day"] <= "2025-06-30" for marco in antes["timeline"])
    assert all(marco["published_at"] <= "2025-06-30" for marco in antes["timeline"])


# ---------------------------------------------------------------- bloco fechado não vaza


def test_bloco_sem_prontidao_nao_aparece_nem_conta(cliente, banco, ator, monkeypatch):
    org, chave = _organizacao(banco, ator, "Alfa", ficha.CONJUNTO, compradores.CONJUNTO)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(DO_PERFIL))
    corpo = _get(cliente, chave).json()
    assert set(corpo["blocks"]) == {"profile", VIZINHAS}
    assert not aj.chaves_de(corpo) & set(DO_BLOCO_DE_SOCIOS)
    assert "corporate_ownership" not in str(corpo)
    assert socios_de_mentira.HOLDING not in str(corpo)
    assert corpo["requests_used"] == 1
    assert _por_conjunto(banco, org) == {ficha.CONJUNTO: (1, 0)}


def test_duas_organizacoes_cada_uma_ve_so_os_blocos_dela(cliente, banco, ator):
    _alfa, chave_alfa = _organizacao(
        banco, ator, "Alfa", ficha.CONJUNTO, compradores.CONJUNTO
    )
    beta, chave_beta = _organizacao(banco, ator, "Beta", empresas.CONJUNTO)
    da_alfa = _get(cliente, chave_alfa).json()
    da_beta = _get(cliente, chave_beta).json()
    assert "corporate_ownership" in da_alfa["blocks"]
    # o cadastro da Beta é a situação na Receita
    assert set(da_beta["blocks"]) == {"profile", VIZINHAS}
    assert "periodic_filings" not in str(da_beta)
    assert not aj.chaves_de(da_beta) & set(DO_BLOCO_DE_SOCIOS)
    assert {f["source"] for f in da_beta["sources"]} == {"rfb-cnpj"}
    assert _por_conjunto(banco, beta) == {empresas.CONJUNTO: (1, 0)}


def test_bloco_fechado_nao_muda_com_a_empresa_ter_ou_nao_dado_nele(
    tmp_path, banco, ator, monkeypatch
):
    """A Beta só tem `companies`: a resposta dela é a mesma com ou sem sócios PJ na base."""
    _beta, chave = _organizacao(
        banco, ator, "Beta", empresas.CONJUNTO, compradores.CONJUNTO
    )
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(empresas.TABELAS))
    respostas = []
    for nome, entradas in (("com", None), ("sem", socios_de_mentira._entradas([]))):
        base = tmp_path / nome
        pasta = socios_de_mentira.ficha_de_mentira._base(
            base, socios_de_mentira.ficha_de_mentira._rotulos()
        )
        socios_de_mentira.gravar_socios(pasta, entradas)
        monkeypatch.setattr(
            rotas, "abrir_porta", lambda banco_, pasta=pasta: Porta(pasta, banco_)
        )
        respostas.append(_get(aj.cliente_da_api(monkeypatch, AGORA), chave).content)
    assert respostas[0] == respostas[1]


def test_chave_sem_contrato_de_cadastro_da_404_mesmo_com_outros_contratos(
    cliente, banco, ator
):
    _org, chave = _organizacao(banco, ator, "Gama", compradores.CONJUNTO)
    resposta = _get(cliente, chave)
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


# ---------------------------------------------------------------- sem pessoa e o 404


@pytest.mark.parametrize(
    "cnpj",
    [
        empresas_de_mentira.MEI,
        empresas_de_mentira.EMPRESARIO_INDIVIDUAL,
        empresas_de_mentira.FUNDO,
    ],
)
def test_pessoa_e_quem_nao_e_empresa_dao_o_mesmo_404_de_quem_nao_existe(
    cliente, banco, ator, cnpj
):
    org, chave = _organizacao(banco, ator, "Alfa", ficha.CONJUNTO, compradores.CONJUNTO)
    inexistente = _get(cliente, chave, INEXISTENTE)
    resposta = _get(cliente, chave, cnpj)
    assert resposta.status_code == inexistente.status_code == 404
    assert resposta.json() == inexistente.json() == {"detail": "not_available"}
    # só o cadastro foi lido: os outros blocos nem correram
    assert _por_conjunto(banco, org) == {ficha.CONJUNTO: (0, 2)}


def test_cnpj_invalido_e_known_at_no_futuro_dao_400(cliente, banco, ator):
    _org, chave = _organizacao(banco, ator, "Alfa", ficha.CONJUNTO)
    assert _get(cliente, chave, "123").status_code == 400
    amanha = date.fromordinal(AGORA.date().toordinal() + 1).isoformat()
    assert _get(cliente, chave, known_at=amanha).status_code == 400


def test_sem_chave_da_401(cliente):
    assert cliente.get(_rota()).status_code == 401
