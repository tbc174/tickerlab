"""A rota do perfil por CNPJ (linha 736, PR 2): `/data/v1/companies/{cnpj}/profile`.

O leitor (`conjuntos/ficha.py`) tem os testes dele em `test_api_externa_por_cnpj_ficha.py`; aqui fica o que
é da rota: chave, contrato de `profiles`, portão com as linhas de verdade, nomes de fora, consumo e os
erros. Base de mentira, sem internet (a mesma de `test_api_externa_empresas.py`, com `rotulos_atraso`).
Riscos: vazar pessoa (o 404 do MEI é igual ao de um CNPJ que não existe) e olhar o futuro (nada publicado
depois de `known_at` sai).
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
from src.api_externa.conjuntos import empresas, ficha
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_por_cnpj_ficha as ficha_de_mentira

AGORA = empresas_de_mentira.AGORA
EMPRESA = empresas_de_mentira.EMPRESA
INEXISTENTE = empresas_de_mentira.INEXISTENTE
ROTA = f"/data/v1/companies/{EMPRESA}/profile"
TABELAS_PRONTAS = (*empresas.TABELAS, ficha.TABELA_DAS_ENTREGAS)


def _rota(cnpj: str) -> str:
    return f"/data/v1/companies/{cnpj}/profile"


def _regras(tabelas=TABELAS_PRONTAS) -> portao.Regras:
    """As regras de verdade, com as tabelas do perfil prontas (provas do D10) no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = ficha_de_mentira._base(tmp_path, ficha_de_mentira._rotulos())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    """Uma organização com chave e contrato de `profiles`, e as tabelas prontas."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=ficha.CONJUNTO)
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    return ator, org, chave


@pytest.fixture
def cliente(monkeypatch, cenario):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, cenario, rota: str = ROTA, **parametros):
    _ator, _org, chave = cenario
    return cliente.get(rota, params=parametros, headers=aj.bearer(chave.valor))


def _consumo(banco, org):
    with banco.connect() as conexao:
        return cb.consumo_do_mes(conexao, org.id, AGORA.date())


# ---------------------------------------------------------------- o que sai


def test_perfil_sai_em_ingles_com_fonte_data_e_atribuicao(cliente, cenario):
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cnpj"] == EMPRESA
    assert corpo["known_at"] == AGORA.date().isoformat()
    registro = corpo["registration"]
    assert registro["registration_status"]["value"] == "08"
    assert registro["legal_name"]["source"] == "rfb-cnpj"
    filings = corpo["periodic_filings"]
    assert len(filings) == len(ficha_de_mentira.ENTREGAS)
    mais_velha = filings[-1]
    assert mais_velha == {
        "document": {
            "value": "DFP",
            "source": "cvm-hist-dfp",
            "published_at": "2024-03-20",
            "observed_at": None,
        },
        "reference_period": mais_velha["reference_period"],
        "due_date": mais_velha["due_date"],
        "first_filed_on": mais_velha["first_filed_on"],
        "business_days_late": mais_velha["business_days_late"],
        "filing_status": mais_velha["filing_status"],
    }
    assert mais_velha["filing_status"]["value"] == ficha.NO_PRAZO
    assert mais_velha["first_filed_on"]["value"] == "2024-03-20"
    assert corpo["limits"] == list(ficha.LIMITES)
    atribuicoes = {f["source"]: f["attribution"] for f in corpo["sources"]}
    assert set(atribuicoes) == {"rfb-cnpj", "cvm-hist-dfp", "cvm-hist-itr"}
    assert "CVM" in atribuicoes["cvm-hist-dfp"]
    assert "Receita" in atribuicoes["rfb-cnpj"]


def test_known_at_no_passado_nao_mostra_o_que_veio_depois(cliente, cenario):
    corpo = _get(cliente, cenario, known_at="2025-06-30").json()
    assert corpo["known_at"] == "2025-06-30"
    envelopes = [
        *corpo["registration"].values(),
        *(e for linha in corpo["periodic_filings"] for e in linha.values()),
    ]
    assert all(e["published_at"] <= "2025-06-30" for e in envelopes)
    # a DFP de 2024 veio em 11/08/2025: em 30/06 ela faltava
    dfp_2024 = next(
        linha
        for linha in corpo["periodic_filings"]
        if linha["reference_period"]["value"] == "2024-12-31"
    )
    assert dfp_2024["filing_status"]["value"] == ficha.NAO_ENTREGUE
    assert "first_filed_on" not in dfp_2024


def test_entregas_sem_prontidao_nao_saem_e_o_cadastro_continua(
    cliente, cenario, monkeypatch
):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(empresas.TABELAS))
    corpo = _get(cliente, cenario).json()
    assert corpo["registration"]["registration_status"]["value"] == "08"
    assert "periodic_filings" not in corpo
    assert {f["source"] for f in corpo["sources"]} == {"rfb-cnpj"}


# ---------------------------------------------------------------- sem pessoa


@pytest.mark.parametrize(
    "cnpj",
    [
        empresas_de_mentira.MEI,
        empresas_de_mentira.EMPRESARIO_INDIVIDUAL,
        empresas_de_mentira.FORA_DA_REDE,
        empresas_de_mentira.FUNDO,
        empresas_de_mentira.SEM_SITUACAO,
    ],
)
def test_pessoa_e_quem_nao_e_empresa_dao_o_mesmo_404_de_quem_nao_existe(
    tmp_path, cenario, monkeypatch, cnpj
):
    """Mesmo com entregas na tabela para o CNPJ, a resposta é a de um CNPJ que não existe."""
    rotulos = ficha_de_mentira._rotulos(cnpj=cnpj)
    base = ficha_de_mentira._base(tmp_path / "com_pessoa", rotulos)
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    inexistente = _get(cliente, cenario, _rota(INEXISTENTE))
    resposta = _get(cliente, cenario, _rota(cnpj))
    assert resposta.status_code == inexistente.status_code == 404
    assert resposta.json() == inexistente.json() == {"detail": "not_available"}


def test_sem_pessoa_na_resposta(cliente, cenario):
    corpo = _get(cliente, cenario).json()
    conferir_sem_pessoas(corpo, set())
    assert not aj.chaves_de(corpo) & COLUNAS_DE_PESSOA


# ---------------------------------------------------------------- o portão


def test_perfil_suspenso_da_o_mesmo_404_de_quem_nao_existe(cliente, cenario, banco):
    inexistente = _get(cliente, cenario, _rota(INEXISTENTE))
    ator, _org, _chave = cenario
    with banco.begin() as conexao:
        cb.suspender_conjunto(
            conexao, conjunto=ficha.CONJUNTO, motivo="fonte", ator_id=ator.id
        )
    negado = _get(cliente, cenario)
    assert negado.status_code == 404
    assert negado.json() == inexistente.json()


def test_hoje_sem_a_prontidao_nada_sai(cliente, cenario, monkeypatch):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: None)  # as regras de verdade
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_contrato_de_companies_nao_abre_o_perfil(banco, monkeypatch, pasta):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=empresas.CONJUNTO)
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    resposta = cliente.get(ROTA, headers=aj.bearer(chave.valor))
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_campo_sem_direito_nao_aparece(cliente, cenario, monkeypatch):
    regras = _regras()
    sem_a_situacao = tuple(
        linha
        for linha in regras.linhas
        if not (
            linha.conjunto == ficha.CONJUNTO and linha.campo == "situacao_da_entrega"
        )
    )
    monkeypatch.setattr(
        rotas,
        "regras_da_api",
        lambda: dataclasses.replace(regras, linhas=sem_a_situacao),
    )
    corpo = _get(cliente, cenario).json()
    assert corpo["periodic_filings"]
    assert all("filing_status" not in linha for linha in corpo["periodic_filings"])


# ---------------------------------------------------------------- erros e consumo


def test_um_perfil_conta_um_pedido_e_as_linhas_servidas(cliente, cenario, banco):
    _ator, org, _chave = cenario
    _get(cliente, cenario)
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (
        1,
        1 + len(ficha_de_mentira.ENTREGAS),
        0,
    )


def test_o_404_conta_como_negado_sem_gastar_a_quota(cliente, cenario, banco):
    _ator, org, _chave = cenario
    _get(cliente, cenario, _rota(empresas_de_mentira.MEI))
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
    assert cliente.get(ROTA).status_code == 401


# ---------------------------------------------------------------- documento não disponível (linha 881)


def _sem_o_itr(regras: portao.Regras) -> portao.Regras:
    linhas = tuple(
        linha
        for linha in regras.linhas
        if not (linha.conjunto == ficha.CONJUNTO and linha.fonte == "cvm-hist-itr")
    )
    return dataclasses.replace(regras, linhas=linhas)


@pytest.fixture
def duas(banco, monkeypatch, pasta):
    """Duas organizações: uma com o contrato de `profiles`, outra só com o de `companies`; o portão sem as
    linhas do ITR (como uma linha de direito retirada)."""
    ator = aj.admin(banco)
    com_perfil = aj.organizacao(banco, ator, "Organização com perfil")
    so_de_companies = aj.organizacao(banco, ator, "Organização sem perfil")
    aj.contrato(banco, ator, com_perfil, conjunto=ficha.CONJUNTO)
    aj.contrato(banco, ator, so_de_companies, conjunto=empresas.CONJUNTO)
    regras = _sem_o_itr(_regras())
    monkeypatch.setattr(rotas, "regras_da_api", lambda: regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return (
        cliente,
        aj.chave(banco, ator, com_perfil).valor,
        aj.chave(banco, ator, so_de_companies).valor,
    )


def test_com_tudo_liberado_a_lista_de_fora_sai_vazia(cliente, cenario):
    corpo = _get(cliente, cenario).json()
    assert corpo["unavailable_filings"] == []


def test_o_documento_barrado_vem_como_nao_disponivel_com_o_aviso(duas):
    cliente, com_perfil, _so_de_companies = duas
    resposta = cliente.get(ROTA, headers=aj.bearer(com_perfil))
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert {f["document"]["value"] for f in corpo["periodic_filings"]} == {"DFP"}
    assert corpo["unavailable_filings"] == ["ITR"]
    assert ficha.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL in corpo["limits"]
    assert "unavailable_filings" in ficha.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL
    assert "cvm-hist-itr" not in {f["source"] for f in corpo["sources"]}


def test_a_organizacao_sem_o_contrato_recebe_404_e_nao_a_lista(duas):
    cliente, _com_perfil, so_de_companies = duas
    resposta = cliente.get(ROTA, headers=aj.bearer(so_de_companies))
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_entregas_sem_prontidao_dizem_que_os_dois_documentos_nao_foram_consultados(
    cliente, cenario, monkeypatch
):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(empresas.TABELAS))
    corpo = _get(cliente, cenario).json()
    assert "periodic_filings" not in corpo
    assert corpo["unavailable_filings"] == ["DFP", "ITR"]
    assert ficha.LIMITE_DO_DOCUMENTO_NAO_DISPONIVEL in corpo["limits"]
    assert not any(
        "periodic" in limite or "entregas cobrem" in limite
        for limite in corpo["limits"]
    )
