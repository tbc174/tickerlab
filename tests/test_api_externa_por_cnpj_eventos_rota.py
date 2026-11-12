"""A rota dos eventos (linha 736, PR 4): `/data/v1/companies/{cnpj}/events`.

O leitor (`conjuntos/eventos.py`) tem os testes dele em `test_api_externa_por_cnpj_eventos.py`; aqui fica o
que é da rota: chave, contrato de `events`, portão com as linhas de verdade, nomes de fora, cursor, consumo e
os erros. Base de mentira, sem internet (a mesma do leitor). Riscos: vazar pessoa (o 404 de quem a rede trata
como pessoa é igual ao de um CNPJ que não existe; o assunto livre do IPE nunca sai) e olhar o futuro (nada
publicado depois de `known_at` sai).
"""

import dataclasses
from datetime import date

import pytest

from base import prontidao
from base.dossie import COLUNAS_DE_PESSOA, conferir_sem_pessoas
from base.porta import Porta
from base.prontidao import Prontidao, ProntidaoDePiloto, Prova
from src import portao_externo as portao
from src.api_externa import acesso, rotas
from src.api_externa.conjuntos import empresas, eventos
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_por_cnpj_eventos as eventos_de_mentira

AGORA = empresas_de_mentira.AGORA
ALFA = eventos_de_mentira.ALFA
DIA = eventos_de_mentira.DIA.isoformat()
TABELAS_PRONTAS = ("eventos", "trocas_de_auditor")
# no dia: P1, P2 e P3 da ALFA (P3 pela filial) e a troca de auditor que não é de pessoa
EVENTOS_NO_DIA = 4


def _rota(cnpj: str = ALFA) -> str:
    return f"/data/v1/companies/{cnpj}/events"


def _regras(tabelas=TABELAS_PRONTAS) -> portao.Regras:
    """As regras de verdade, com as tabelas dos eventos prontas (provas do D10) no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = eventos_de_mentira.gravar_base(tmp_path / "base")
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    """Uma organização com chave e contrato de `events`, e as tabelas prontas."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=eventos.CONJUNTO)
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


def test_eventos_saem_em_ingles_com_fonte_data_e_atribuicao(cliente, cenario):
    resposta = _get(cliente, cenario, known_at=DIA)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cnpj"] == ALFA and corpo["known_at"] == DIA
    assert corpo["truncated"] is False and corpo["next_cursor"] is None
    assert corpo["limits"] == list(eventos.LIMITES)
    assert corpo["unavailable_event_types"] == []
    lista = corpo["events"]
    assert [e["event_type"] for e in lista] == [
        "auditor_change", "ipe_filing", "ipe_filing", "ipe_filing",
    ]  # fmt: skip
    troca = lista[0]
    assert troca["previous"]["value"] == "AUDITORA UM"
    assert troca["new"] == {
        "value": "AUDITORA DOIS", "source": "cvm-hist-fca", "published_at": "2025-05-31", "observed_at": None,
    }  # fmt: skip
    assert troca["effective_on"]["value"] == "2025-01-01"
    assert troca["years_with_previous"]["value"] == 5.0
    documento = lista[1]
    assert documento["filing_id"]["value"] == "P1"
    assert documento["category"]["value"] == "Fato Relevante"
    assert documento["document_url"]["value"].endswith("numProtocolo=P1")
    atribuicoes = {f["source"]: f["attribution"] for f in corpo["sources"]}
    assert set(atribuicoes) == {"cvm-hist-ipe", "cvm-hist-fca"}
    assert all("CVM" in texto for texto in atribuicoes.values())


def test_known_at_no_passado_nao_mostra_o_que_veio_depois(cliente, cenario):
    corpo = _get(cliente, cenario, known_at=DIA).json()
    envelopes = [
        valor
        for e in corpo["events"]
        for valor in e.values()
        if isinstance(valor, dict)
    ]
    assert envelopes and all(e["published_at"] <= DIA for e in envelopes)
    assert "P4" not in {e.get("filing_id", {}).get("value") for e in corpo["events"]}


def test_sem_known_at_vale_hoje(cliente, cenario):
    corpo = _get(cliente, cenario).json()
    assert corpo["known_at"] == AGORA.date().isoformat()
    protocolos = {e["filing_id"]["value"] for e in corpo["events"] if "filing_id" in e}
    assert "P4" in protocolos


def test_types_filtra_os_eventos(cliente, cenario):
    corpo = _get(cliente, cenario, known_at=DIA, types=["auditor_change"]).json()
    assert [e["event_type"] for e in corpo["events"]] == ["auditor_change"]
    assert {f["source"] for f in corpo["sources"]} == {"cvm-hist-fca"}


def test_a_pagina_segue_pelo_cursor_sem_perder_nem_repetir(
    cliente, cenario, monkeypatch
):
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda _contexto: 3)
    primeira = _get(cliente, cenario, known_at=DIA).json()
    assert primeira["truncated"] is True and len(primeira["events"]) == 3
    segunda = _get(
        cliente, cenario, known_at=DIA, cursor=primeira["next_cursor"]
    ).json()
    assert segunda["truncated"] is False and segunda["next_cursor"] is None
    assert len(primeira["events"]) + len(segunda["events"]) == EVENTOS_NO_DIA
    inteira = _get(cliente, cenario, known_at=DIA)
    assert inteira.status_code == 200


def test_limit_encurta_a_pagina_e_o_plano_continua_sendo_o_teto(
    cliente, cenario, monkeypatch
):
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda _contexto: 3)
    curta = _get(cliente, cenario, known_at=DIA, limit=2).json()
    assert len(curta["events"]) == 2 and curta["truncated"] is True
    resto = _get(cliente, cenario, known_at=DIA, limit=2, cursor=curta["next_cursor"])
    assert len(curta["events"]) + len(resto.json()["events"]) <= EVENTOS_NO_DIA
    # pedir mais do que o plano deixa não passa do plano
    assert len(_get(cliente, cenario, known_at=DIA, limit=500).json()["events"]) == 3


def test_limit_menor_que_1_da_400_sem_gastar_a_quota(cliente, cenario, banco):
    _ator, org, _chave = cenario
    resposta = _get(cliente, cenario, limit=0)
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_limit"}
    assert _consumo(banco, org).pedidos == 0


def test_eventos_sem_prontidao_de_uma_tabela_saem_so_da_outra(
    cliente, cenario, monkeypatch
):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(("eventos",)))
    corpo = _get(cliente, cenario, known_at=DIA).json()
    assert {e["event_type"] for e in corpo["events"]} == {"ipe_filing"}
    assert {f["source"] for f in corpo["sources"]} == {"cvm-hist-ipe"}
    # a troca de auditor não some em silêncio (linha 878)
    assert corpo["unavailable_event_types"] == ["auditor_change"]
    assert eventos.LIMITE_DO_TIPO_NAO_DISPONIVEL in corpo["limits"]


# ---------------------------------------------------------------- o tipo barrado (linha 878)


def _regras_do_piloto() -> portao.Regras:
    """Como no ensaio da 739: as trocas de auditor só pelo registro de piloto; os documentos do IPE barrados."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    vigentes = portao.regras_vigentes()
    return dataclasses.replace(
        vigentes,
        prontidao={},
        prontidao_de_piloto={
            "trocas_de_auditor": ProntidaoDePiloto(
                versoes["trocas_de_auditor"], prova, prova
            )
        },
        pessoa_decidida=vigentes.pessoa_decidida | {"trocas_de_auditor"},
    )


@pytest.fixture
def duas(banco, monkeypatch, pasta):
    """Duas organizações com o contrato de `events`; só a primeira tem a marca de piloto."""
    ator = aj.admin(banco)
    do_piloto = aj.organizacao(banco, ator, "Organização do piloto")
    comum = aj.organizacao(banco, ator, "Organização comum")
    for org in (do_piloto, comum):
        aj.contrato(banco, ator, org, conjunto=eventos.CONJUNTO)
    with banco.begin() as conexao:
        cb.conceder_direito(
            conexao, organizacao_id=do_piloto.id, conjunto=cb.CONJUNTO_DO_PILOTO, finalidade="analise",
            vigente_desde=date(2026, 11, 1), ator_id=ator.id, agora=AGORA,
        )  # fmt: skip
    monkeypatch.setattr(rotas, "regras_da_api", _regras_do_piloto)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return (
        cliente,
        aj.chave(banco, ator, do_piloto).valor,
        aj.chave(banco, ator, comum).valor,
    )


def test_o_tipo_barrado_vem_como_nao_disponivel_e_nao_como_lista_vazia(duas):
    cliente, do_piloto, _comum = duas
    resposta = cliente.get(
        _rota(), params={"known_at": DIA}, headers=aj.bearer(do_piloto)
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [e["event_type"] for e in corpo["events"]] == ["auditor_change"]
    assert corpo["unavailable_event_types"] == ["ipe_filing"]
    # os limites não dizem que os documentos do IPE foram servidos
    assert eventos.LIMITE_DO_TIPO_NAO_DISPONIVEL in corpo["limits"]
    assert eventos.LIMITES_DO_TIPO[eventos.DOCUMENTO_DO_IPE] not in corpo["limits"]
    assert {f["source"] for f in corpo["sources"]} == {"cvm-hist-fca"}


def test_antes_da_troca_a_lista_vazia_vem_com_o_tipo_barrado(duas):
    cliente, do_piloto, _comum = duas
    corpo = cliente.get(
        _rota(), params={"known_at": "2025-05-01"}, headers=aj.bearer(do_piloto)
    ).json()
    assert corpo["events"] == []
    assert corpo["unavailable_event_types"] == ["ipe_filing"]


def test_so_o_tipo_barrado_pedido_da_404(duas):
    cliente, do_piloto, _comum = duas
    resposta = cliente.get(
        _rota(),
        params={"known_at": DIA, "types": ["ipe_filing"]},
        headers=aj.bearer(do_piloto),
    )
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_a_organizacao_sem_o_tipo_liberado_recebe_404(duas):
    cliente, _do_piloto, comum = duas
    resposta = cliente.get(_rota(), params={"known_at": DIA}, headers=aj.bearer(comum))
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


# ---------------------------------------------------------------- sem pessoa


@pytest.mark.parametrize(
    "cnpj", [eventos_de_mentira.PESSOA, eventos_de_mentira.FORA_DA_REDE]
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


def test_sem_pessoa_nem_assunto_na_resposta(cliente, cenario):
    resposta = _get(cliente, cenario)
    corpo = resposta.json()
    conferir_sem_pessoas(corpo, set())
    assert not aj.chaves_de(corpo) & COLUNAS_DE_PESSOA
    assert "Fulano" not in resposta.text and "FULANO" not in resposta.text
    assert "subject" not in aj.chaves_de(corpo)


# ---------------------------------------------------------------- o portão


def test_eventos_suspensos_dao_o_mesmo_404_de_quem_nao_existe(cliente, cenario, banco):
    inexistente = _get(
        cliente, cenario, _rota(empresas_de_mentira.INEXISTENTE), known_at=DIA
    )
    ator, _org, _chave = cenario
    with banco.begin() as conexao:
        cb.suspender_conjunto(
            conexao, conjunto=eventos.CONJUNTO, motivo="fonte", ator_id=ator.id
        )
    negado = _get(cliente, cenario, known_at=DIA)
    assert negado.status_code == 404
    assert negado.json() == inexistente.json()


def test_hoje_sem_a_prontidao_nada_sai(cliente, cenario, monkeypatch):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: None)  # as regras de verdade
    resposta = _get(cliente, cenario, known_at=DIA)
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_contrato_de_companies_nao_abre_os_eventos(banco, monkeypatch, pasta):
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
    sem_o_link = tuple(
        linha
        for linha in regras.linhas
        if not (linha.conjunto == eventos.CONJUNTO and linha.campo == "link")
    )
    monkeypatch.setattr(
        rotas, "regras_da_api", lambda: dataclasses.replace(regras, linhas=sem_o_link)
    )
    corpo = _get(cliente, cenario, known_at=DIA).json()
    documentos = [e for e in corpo["events"] if e["event_type"] == "ipe_filing"]
    assert documentos and all("document_url" not in e for e in documentos)


# ---------------------------------------------------------------- erros e consumo


def test_um_pedido_conta_os_eventos_servidos(cliente, cenario, banco):
    _ator, org, _chave = cenario
    _get(cliente, cenario, known_at=DIA)
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (1, EVENTOS_NO_DIA, 0)


def test_o_404_conta_como_negado_sem_gastar_a_quota(cliente, cenario, banco):
    _ator, org, _chave = cenario
    _get(cliente, cenario, _rota(eventos_de_mentira.PESSOA), known_at=DIA)
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (0, 0, 1)


@pytest.mark.parametrize(
    ("parametros", "codigo"),
    [
        ({"types": ["merger"]}, "invalid_event_type"),
        ({"cursor": "nao-e-nosso"}, "invalid_cursor"),
        ({"cursor": eventos.cursor_de((1, "x", "y"))[:-2] + "!!"}, "invalid_cursor"),
        ({"known_at": date.fromordinal(AGORA.date().toordinal() + 1).isoformat()}, "invalid_known_at"),
    ],
)  # fmt: skip
def test_pedido_invalido_da_400_sem_gastar_a_quota(
    cliente, cenario, banco, parametros, codigo
):
    _ator, org, _chave = cenario
    resposta = _get(cliente, cenario, **parametros)
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": codigo}
    assert _consumo(banco, org).pedidos == 0


def test_cnpj_invalido_da_400(cliente, cenario):
    resposta = _get(cliente, cenario, _rota("123"))
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_cnpj"}


def test_sem_chave_da_401(cliente, cenario):
    assert cliente.get(_rota()).status_code == 401
