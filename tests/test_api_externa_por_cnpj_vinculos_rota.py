"""A rota dos vínculos (linha 736, PR 5): `/data/v1/companies/{cnpj}/links`.

O leitor (`conjuntos/vinculos.py`) tem os testes dele em `test_api_externa_por_cnpj_vinculos.py`; aqui fica o
que é da rota: chave, contrato de `links`, portão com as linhas de verdade, nomes de fora, consumo e os erros.
Base de mentira, sem internet (a mesma do leitor). Riscos: vazar pessoa (o 404 de quem a rede trata como pessoa
é igual ao de um CNPJ que não existe; a ponta que é pessoa nunca sai) e olhar o futuro (nada publicado depois de
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
from src.api_externa import acesso, rotas
from src.api_externa.conjuntos import empresas, vinculos
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_por_cnpj_vinculos as vinculos_de_mentira

AGORA = empresas_de_mentira.AGORA
ALFA = vinculos_de_mentira.ALFA
DIA = vinculos_de_mentira.DIA.isoformat()
TABELAS_DA_REDE = ("ligacoes", "entidades", "identificadores")
TABELAS_PRONTAS = (*TABELAS_DA_REDE, "cnpj_empresas_pj")
# no dia, a um salto: a MAE, a FILHA, a VENDIDA_DEPOIS (o fim só se soube depois), a COLIGADA e a AUDITORA
VINCULOS_NO_DIA = 5


def _rota(cnpj: str = ALFA) -> str:
    return f"/data/v1/companies/{cnpj}/links"


def _regras(tabelas=TABELAS_PRONTAS) -> portao.Regras:
    """As regras de verdade, com as tabelas da rede prontas (provas do D10) no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = vinculos_de_mentira.gravar_base(tmp_path / "base")
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    """Uma organização com chave e contrato de `links`, e as tabelas prontas."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=vinculos.CONJUNTO)
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


def _tipos(corpo) -> list[str]:
    return [v["kind"]["value"] for v in corpo["links"]]


# ---------------------------------------------------------------- o que sai


def test_vinculos_saem_em_ingles_com_fonte_data_e_atribuicao(cliente, cenario):
    resposta = _get(cliente, cenario, known_at=DIA)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cnpj"] == ALFA and corpo["known_at"] == DIA
    assert corpo["depth"] == 1 and corpo["truncated"] is False
    assert corpo["limits"] == list(vinculos.LIMITES)
    assert corpo["unavailable_link_types"] == []
    assert _tipos(corpo) == [
        "subsidiary_of", "subsidiary_of", "subsidiary_of", "affiliate_of", "audits",
    ]  # fmt: skip
    mae = corpo["links"][0]
    assert mae["hops"] == 1
    assert mae["from"] == {
        "entity_id": "EALFA",
        "cnpj_root": "11111111",
        "legal_name": {"value": "ALFA LTDA", "source": "rfb-cnpj", "published_at": "2025-03-31", "observed_at": None},
        "registry_snapshot_month": {
            "value": "2025-03", "source": "rfb-cnpj", "published_at": "2025-03-31", "observed_at": None,
        },
    }  # fmt: skip
    assert mae["to"]["entity_id"] == "EMAE"
    assert mae["ownership_pct"] == {
        "value": 60.0, "source": "cvm-hist-fre", "published_at": "2019-05-31", "observed_at": None,
    }  # fmt: skip
    assert mae["valid_from"]["value"] == "2018-12-31"
    atribuicoes = {f["source"]: f["attribution"] for f in corpo["sources"]}
    assert set(atribuicoes) == {"cvm-hist-fre", "cvm-hist-fca", "rfb-cnpj"}
    assert "CVM" in atribuicoes["cvm-hist-fre"] and "CVM" in atribuicoes["cvm-hist-fca"]
    assert "Receita" in atribuicoes["rfb-cnpj"]


def test_known_at_no_passado_nao_mostra_o_que_veio_depois(cliente, cenario):
    corpo = _get(cliente, cenario, known_at=DIA, depth=3).json()
    envelopes = [
        valor
        for v in corpo["links"]
        for valor in (
            *v.values(),
            v["from"].get("legal_name"),
            v["to"].get("legal_name"),
        )
        if isinstance(valor, dict) and "published_at" in valor
    ]
    assert envelopes and all(e["published_at"] <= DIA for e in envelopes)
    assert "EFUTURA" not in {v["from"]["entity_id"] for v in corpo["links"]}


def test_sem_known_at_vale_hoje(cliente, cenario):
    corpo = _get(cliente, cenario).json()
    assert corpo["known_at"] == AGORA.date().isoformat()
    ids = {v["from"]["entity_id"] for v in corpo["links"]}
    assert "EFUTURA" in ids and "EVENDIDA_DEPOIS" not in ids


def test_depth_e_types_filtram(cliente, cenario):
    corpo = _get(
        cliente, cenario, known_at=DIA, depth=3, types=["subsidiary_of"]
    ).json()
    assert set(_tipos(corpo)) == {"subsidiary_of"}
    assert max(v["hops"] for v in corpo["links"]) == 3
    assert {f["source"] for f in corpo["sources"]} == {"cvm-hist-fre", "rfb-cnpj"}


def test_a_lista_vai_ate_o_limite_de_linhas(cliente, cenario, monkeypatch):
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda _contexto: 2)
    corpo = _get(cliente, cenario, known_at=DIA).json()
    assert corpo["truncated"] is True and len(corpo["links"]) == 2


def test_sem_a_prontidao_da_rede_nada_sai(cliente, cenario, monkeypatch):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(("ligacoes",)))
    resposta = _get(cliente, cenario, known_at=DIA)
    assert resposta.status_code == 404


# ---------------------------------------------------------------- sem pessoa


@pytest.mark.parametrize(
    "cnpj", [vinculos_de_mentira.PESSOA, vinculos_de_mentira.FORA_DA_REDE]
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
    resposta = _get(cliente, cenario, depth=3)
    corpo = resposta.json()
    conferir_sem_pessoas(corpo, set())
    assert not aj.chaves_de(corpo) & COLUNAS_DE_PESSOA
    ids = {v[ponta]["entity_id"] for v in corpo["links"] for ponta in ("from", "to")}
    assert not ids & {"EINDIVIDUAL", "EPESSOA", "EFUNDO"}
    assert not any(i.startswith("P") for i in ids)


# ---------------------------------------------------------------- o portão


def test_vinculos_suspensos_dao_o_mesmo_404_de_quem_nao_existe(cliente, cenario, banco):
    inexistente = _get(
        cliente, cenario, _rota(empresas_de_mentira.INEXISTENTE), known_at=DIA
    )
    ator, _org, _chave = cenario
    with banco.begin() as conexao:
        cb.suspender_conjunto(
            conexao, conjunto=vinculos.CONJUNTO, motivo="fonte", ator_id=ator.id
        )
    negado = _get(cliente, cenario, known_at=DIA)
    assert negado.status_code == 404
    assert negado.json() == inexistente.json()


def test_hoje_sem_a_prontidao_nada_sai(cliente, cenario, monkeypatch):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: None)  # as regras de verdade
    resposta = _get(cliente, cenario, known_at=DIA)
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_contrato_de_companies_nao_abre_os_vinculos(banco, monkeypatch, pasta):
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


def _sem(regras: portao.Regras, campo: str, fonte: str | None = None) -> portao.Regras:
    linhas = tuple(
        linha
        for linha in regras.linhas
        if not (
            linha.conjunto == vinculos.CONJUNTO
            and linha.campo == campo
            and (fonte is None or linha.fonte == fonte)
        )
    )
    return dataclasses.replace(regras, linhas=linhas)


def test_campo_sem_direito_nao_aparece(cliente, cenario, monkeypatch):
    regras = _sem(_regras(), "participacao")
    monkeypatch.setattr(rotas, "regras_da_api", lambda: regras)
    corpo = _get(cliente, cenario, known_at=DIA).json()
    assert corpo["links"] and all("ownership_pct" not in v for v in corpo["links"])


def test_sem_o_tipo_do_fca_a_auditoria_nao_sai(cliente, cenario, monkeypatch):
    regras = _sem(_regras(), "tipo", "cvm-hist-fca")
    monkeypatch.setattr(rotas, "regras_da_api", lambda: regras)
    corpo = _get(cliente, cenario, known_at=DIA).json()
    assert "audits" not in _tipos(corpo)
    assert "cvm-hist-fca" not in {f["source"] for f in corpo["sources"]}


# ---------------------------------------------------------------- o tipo barrado (linha 880)


@pytest.fixture
def duas(banco, monkeypatch, pasta):
    """Duas organizações: uma com o contrato de `links`, outra só com o de `companies`; o portão sem o tipo de
    vínculo do FCA (a auditoria barrada, como uma linha de direito retirada)."""
    ator = aj.admin(banco)
    com_links = aj.organizacao(banco, ator, "Organização com links")
    so_de_companies = aj.organizacao(banco, ator, "Organização sem links")
    aj.contrato(banco, ator, com_links, conjunto=vinculos.CONJUNTO)
    aj.contrato(banco, ator, so_de_companies, conjunto=empresas.CONJUNTO)
    regras = _sem(_regras(), "tipo", "cvm-hist-fca")
    monkeypatch.setattr(rotas, "regras_da_api", lambda: regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    return (
        cliente,
        aj.chave(banco, ator, com_links).valor,
        aj.chave(banco, ator, so_de_companies).valor,
    )


def test_o_tipo_barrado_vem_como_nao_disponivel_e_os_limites_nao_falam_dele(duas):
    cliente, com_links, _so_de_companies = duas
    resposta = cliente.get(
        _rota(), params={"known_at": DIA}, headers=aj.bearer(com_links)
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "audits" not in _tipos(corpo)
    assert corpo["unavailable_link_types"] == ["audits"]
    assert vinculos.LIMITE_DO_TIPO_NAO_DISPONIVEL in corpo["limits"]
    assert "unavailable_link_types" in vinculos.LIMITE_DO_TIPO_NAO_DISPONIVEL
    assert vinculos.LIMITES_DA_FONTE[vinculos.FCA] not in corpo["limits"]
    assert "cvm-hist-fca" not in {f["source"] for f in corpo["sources"]}


def test_a_lista_vazia_com_o_tipo_barrado_diz_o_que_nao_foi_consultado(duas):
    cliente, com_links, _so_de_companies = duas
    corpo = cliente.get(
        _rota(), params={"known_at": "2018-01-01"}, headers=aj.bearer(com_links)
    ).json()
    assert corpo["links"] == []
    assert corpo["unavailable_link_types"] == ["audits"]


def test_so_o_tipo_barrado_pedido_da_404(duas):
    cliente, com_links, _so_de_companies = duas
    resposta = cliente.get(
        _rota(),
        params={"known_at": DIA, "types": ["audits"]},
        headers=aj.bearer(com_links),
    )
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_o_tipo_liberado_pedido_sozinho_nao_lista_o_barrado(duas):
    cliente, com_links, _so_de_companies = duas
    corpo = cliente.get(
        _rota(),
        params={"known_at": DIA, "types": ["subsidiary_of"]},
        headers=aj.bearer(com_links),
    ).json()
    assert corpo["unavailable_link_types"] == []
    assert vinculos.LIMITE_DO_TIPO_NAO_DISPONIVEL not in corpo["limits"]


@pytest.mark.parametrize("tipos", [[], ["subsidiary_of"]])
def test_a_organizacao_sem_o_contrato_recebe_404_e_nao_a_lista_dos_barrados(
    duas, tipos
):
    cliente, _com_links, so_de_companies = duas
    resposta = cliente.get(
        _rota(),
        params={"known_at": DIA, "types": tipos},
        headers=aj.bearer(so_de_companies),
    )
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_sem_a_razao_social_da_receita_a_ponta_sai_sem_nome(
    cliente, cenario, monkeypatch
):
    regras = _sem(_regras(), "razao_social", "rfb-cnpj")
    monkeypatch.setattr(rotas, "regras_da_api", lambda: regras)
    mae = _get(cliente, cenario, known_at=DIA).json()["links"][0]
    assert mae["from"] == {"entity_id": "EALFA", "cnpj_root": "11111111"}


def test_sem_a_prontidao_da_lista_pj_os_vinculos_saem_sem_nome(
    cliente, cenario, monkeypatch
):
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(TABELAS_DA_REDE))
    corpo = _get(cliente, cenario, known_at=DIA).json()
    assert len(corpo["links"]) == VINCULOS_NO_DIA
    assert all(
        campo not in ponta
        for v in corpo["links"]
        for ponta in (v["from"], v["to"])
        for campo in ("legal_name", "registry_snapshot_month")
    )
    assert "rfb-cnpj" not in {f["source"] for f in corpo["sources"]}


def test_o_nome_das_pontas_declara_so_a_lista_sem_pessoa():
    # linha 867: uma linha por caminho, declarando só a tabela lida; o histórico datado (com pessoa) não é
    # lido, e exigir a prontidão dele (D10) tiraria o nome no VPS, onde ele não está
    da_receita = [
        linha
        for linha in portao.regras_vigentes().linhas
        if linha.conjunto == vinculos.CONJUNTO and linha.fonte == "rfb-cnpj"
    ]
    assert {linha.campo for linha in da_receita} == {
        "razao_social",
        "mes_do_retrato_do_cadastro",
    }
    assert {tabela for linha in da_receita for tabela in linha.tabelas} == {
        "cnpj_empresas_pj"
    }


# ---------------------------------------------------------------- erros e consumo


def test_um_pedido_conta_os_vinculos_servidos(cliente, cenario, banco):
    _ator, org, _chave = cenario
    _get(cliente, cenario, known_at=DIA)
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (1, VINCULOS_NO_DIA, 0)


def test_o_404_conta_como_negado_sem_gastar_a_quota(cliente, cenario, banco):
    _ator, org, _chave = cenario
    _get(cliente, cenario, _rota(vinculos_de_mentira.PESSOA), known_at=DIA)
    consumo = _consumo(banco, org)
    assert (consumo.pedidos, consumo.linhas, consumo.negados) == (0, 0, 1)


@pytest.mark.parametrize(
    ("parametros", "codigo"),
    [
        ({"types": ["controlada_de"]}, "invalid_link_type"),
        ({"types": ["owner_of"]}, "invalid_link_type"),
        ({"depth": 0}, "invalid_depth"),
        ({"depth": 4}, "invalid_depth"),
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


def test_depth_que_nao_e_numero_da_422(cliente, cenario):
    assert _get(cliente, cenario, depth="dois").status_code == 422


def test_cnpj_invalido_da_400(cliente, cenario):
    resposta = _get(cliente, cenario, _rota("123"))
    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "invalid_cnpj"}


def test_sem_chave_da_401(cliente, cenario):
    assert cliente.get(_rota()).status_code == 401


def test_sem_a_tabela_de_ligacoes_a_rota_da_404(duas, pasta):
    """Tabela fora da porta não é "sem vínculos" (linha 917)."""
    cliente, com_links, _so_de_companies = duas
    (pasta / "rede" / "ligacoes.parquet").unlink()
    resposta = cliente.get(
        _rota(), params={"known_at": DIA}, headers=aj.bearer(com_links)
    )
    assert resposta.status_code == 404
