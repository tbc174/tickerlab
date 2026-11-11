"""O setor do molde D na API externa (linha 781): `/data/v1/sectors` e `/data/v1/sectors/{key}`.

A seção `setor` da ficha da noite é a do dublê do relatório do setor (elétricas, a série de consumidores da
ANEEL, a CPFL e outra companhia). As linhas de direito são as de verdade (`DIREITOS_DA_API_EXTERNA`); o teste
só põe as tabelas de onde os campos saem prontas (D10), como a A7 fará. Riscos do plano: pessoa física na
resposta, campo sem linha de direito saindo, `known_at` antes da noite e o pedido fora da quota.
"""

import dataclasses
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from base import prontidao
from base.prontidao import Prontidao, Prova
from scripts.gerar_openapi_data import openapi_data_v1
from src import dossie
from src import portao_externo as portao
from src.api_externa import acesso, rotas
from src.api_externa.conjuntos import setores
from src.banco import chaves_da_api as cb
from tests import ajudantes_da_api_externa as aj
from tests.test_relatorio_setor import CPFL, OUTRA, gravar_noite, secao_da_noite

AGORA = datetime(2026, 11, 10, 12, tzinfo=UTC)  # o beta começa em 03/11
DIA_DA_NOITE = "2026-10-17"  # o `gerado_em` da ficha de exemplo da CPFL
ROTA = "/data/v1/sectors/eletricas"
LISTA = "/data/v1/sectors"
TABELAS_DO_SETOR = ("aneel_samp", "empresa_serie", "cadastro_das_companhias")


def _regras(tabelas: tuple[str, ...] = TABELAS_DO_SETOR) -> portao.Regras:
    """As regras de verdade, com as tabelas do setor prontas (provas do D10) no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


@pytest.fixture
def pasta(tmp_path: Path, monkeypatch) -> Path:
    """A noite das elétricas gravada e a pasta das fichas apontando para ela."""
    gravar_noite(tmp_path)
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(tmp_path))
    return tmp_path


@pytest.fixture
def cenario(banco, monkeypatch, pasta):
    """Uma organização com chave e contrato de `sectors`, e as tabelas do setor prontas."""
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=setores.CONJUNTO)
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    return ator, org, chave


@pytest.fixture
def cliente(monkeypatch, cenario):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, cenario, rota: str = ROTA, **parametros):
    _ator, _org, chave = cenario
    return cliente.get(rota, params=parametros, headers=aj.bearer(chave.valor))


def _consumo(banco, org) -> cb.ConsumoDoMes:
    with banco.connect() as conexao:
        return cb.consumo_do_mes(conexao, org.id, AGORA.date())


def _regravar_noite(pasta: Path, mudar) -> None:
    secao = secao_da_noite()
    mudar(secao)
    gravar_noite(pasta, secao)


# ---------------------------------------------------------------- um setor


def test_setor_sai_com_fonte_data_e_atribuicao_em_ingles(cliente, cenario):
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["sector"] == "eletricas"
    assert corpo["name"] == "Elétricas"
    assert corpo["known_at"] == DIA_DA_NOITE
    [serie] = corpo["by_series"]
    assert serie["series"] == "aneel_consumidores"
    topo = serie["concentration"][0]
    assert topo["year"]["value"] == 2025
    assert topo["hhi"] == {
        "value": 4626.0,
        "source": "aneel-samp",
        "published_at": DIA_DA_NOITE,
        "observed_at": None,
    }
    assert topo["concentration_band"]["value"] == "altamente concentrado"
    cpfl = serie["member_shares"][0]
    assert cpfl["cnpj"]["value"] == CPFL
    assert cpfl["market_share"]["value"] == pytest.approx(0.11)
    assert cpfl["market_share"]["source"] == "aneel-samp"
    membros = {m["cnpj"]["value"]: m for m in corpo["members"]}
    assert set(membros) == {CPFL, OUTRA}
    assert membros[CPFL]["company_name"]["source"] == "cvm-cadastros"
    assert corpo["notes"] and all(isinstance(n, str) for n in corpo["notes"])
    fontes = {f["source"]: f for f in corpo["sources"]}
    assert set(fontes) == {"aneel-samp", "cvm-cadastros"}
    assert "ANEEL" in fontes["aneel-samp"]["attribution"]
    assert "CVM" in fontes["cvm-cadastros"]["attribution"]


def test_nenhuma_pessoa_fisica_na_resposta(cliente, cenario, pasta):
    # uma linha com 11 dígitos (CPF) plantada nos membros e na participação não sai
    def plantar(secao: dict) -> None:
        pessoa = {"cnpj": "12345678909", "empresa": "FULANO", "motivo": "ligada"}
        secao["tabelas"]["membros"].append(pessoa)
        linha = dict(secao["tabelas"]["participacao_dos_membros"][0])
        secao["tabelas"]["participacao_dos_membros"].append(
            linha | {"cnpj": "12345678909", "empresa": "FULANO"}
        )

    _regravar_noite(pasta, plantar)
    corpo = _get(cliente, cenario).json()
    texto = json.dumps(corpo)
    assert "12345678909" not in texto
    assert "FULANO" not in texto
    for chave in aj.chaves_de(corpo):
        assert not set(chave.split("_")) & portao.PALAVRAS_QUE_NUNCA_SAEM, chave


def test_coluna_sem_linha_de_direito_nao_sai(cliente, cenario, pasta):
    # a lista de entidades e a tabela do mercado de energia não têm linha: ficam fora
    def acrescentar(secao: dict) -> None:
        for linha in secao["tabelas"]["concentracao_aneel_consumidores"]:
            linha["lista_de_entidades"] = ["DISTRIBUIDORA X"]
        secao["tabelas"]["mercado_ccee_pld"] = [{"ano": 2025, "valor": 1.0}]

    _regravar_noite(pasta, acrescentar)
    corpo = _get(cliente, cenario).json()
    assert "DISTRIBUIDORA X" not in json.dumps(corpo)
    assert [s["series"] for s in corpo["by_series"]] == ["aneel_consumidores"]


def test_tabela_da_agencia_sem_prontidao_tira_so_a_serie(cliente, cenario, monkeypatch):
    sem_a_aneel = ("empresa_serie", "cadastro_das_companhias")
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(sem_a_aneel))
    corpo = _get(cliente, cenario).json()
    assert corpo["by_series"] == []
    assert {m["cnpj"]["value"] for m in corpo["members"]} == {CPFL, OUTRA}
    assert {f["source"] for f in corpo["sources"]} == {"cvm-cadastros"}


def test_sem_contrato_do_conjunto_sai_not_available(banco, monkeypatch, pasta):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto="funds")
    monkeypatch.setattr(rotas, "regras_da_api", _regras)
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    resposta = cliente.get(ROTA, headers=aj.bearer(chave.valor))
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == rotas.NAO_DISPONIVEL


@pytest.mark.parametrize("chave", ["aviacao", "nao_existe", "ELETRICAS"])
def test_setor_fora_do_relatorio_sai_not_available(cliente, cenario, chave):
    resposta = _get(cliente, cenario, f"{LISTA}/{chave}")
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == rotas.NAO_DISPONIVEL


def test_caminho_fora_da_pasta_nao_chega_a_ficha(cliente, cenario):
    # a chave só vale se está na lista do relatório; o roteador nem casa a barra codificada
    assert _get(cliente, cenario, f"{LISTA}/..%2Feletricas").status_code == 404


def test_sem_a_noite_sai_not_available(cliente, cenario, pasta):
    (pasta / "atual" / dossie.NOME_DO_MANIFESTO).unlink()
    assert _get(cliente, cenario).status_code == 404


def test_known_at_antes_da_noite_sai_not_available(cliente, cenario):
    # a base guarda só a noite mais nova: antes dela, o setor não é conhecido
    assert _get(cliente, cenario, known_at="2026-10-16").status_code == 404
    assert _get(cliente, cenario, known_at=DIA_DA_NOITE).status_code == 200
    assert _get(cliente, cenario, known_at="2026-11-01").json()["known_at"] == (
        DIA_DA_NOITE
    )


def test_known_at_no_futuro_e_recusado(cliente, cenario):
    resposta = _get(cliente, cenario, known_at="2026-11-11")
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "invalid_known_at"


def test_setor_conta_na_quota_e_a_recusa_conta_como_negada(cliente, cenario, banco):
    _ator, org, _chave = cenario
    assert _get(cliente, cenario).status_code == 200
    depois = _consumo(banco, org)
    assert (depois.pedidos, depois.negados) == (1, 0)
    assert depois.linhas > 0
    assert _get(cliente, cenario, known_at="2026-10-01").status_code == 404
    assert _consumo(banco, org).negados == 1


def test_linhas_alem_do_plano_saem_cortadas(cliente, cenario, monkeypatch):
    monkeypatch.setattr(acesso, "linhas_por_resposta", lambda contexto: 3)
    corpo = _get(cliente, cenario).json()
    servidas = sum(
        len(s["concentration"]) + len(s["member_shares"]) for s in corpo["by_series"]
    ) + len(corpo["members"])
    assert servidas == 3
    assert corpo["truncated"] is True


def test_sem_chave_e_recusado(cliente):
    assert cliente.get(ROTA).status_code == 401


# ---------------------------------------------------------------- a lista


def test_lista_mostra_os_setores_da_noite_sem_gastar_quota(cliente, cenario, banco):
    _ator, org, _chave = cenario
    resposta = _get(cliente, cenario, LISTA)
    assert resposta.status_code == 200
    assert resposta.json() == {
        "sectors": [
            {"sector": "eletricas", "name": "Elétricas", "known_at": DIA_DA_NOITE}
        ]
    }
    assert _consumo(banco, org).pedidos == 0


def test_lista_sem_a_noite_sai_vazia(cliente, cenario, pasta):
    (pasta / "atual" / dossie.NOME_DO_MANIFESTO).unlink()
    assert _get(cliente, cenario, LISTA).json() == {"sectors": []}


# ---------------------------------------------------------------- o catálogo e as linhas


def test_catalogo_mostra_o_conjunto_dos_setores(cliente, cenario):
    corpo = _get(cliente, cenario, "/data/v1/catalog").json()
    [conjunto] = [c for c in corpo["datasets"] if c["dataset"] == setores.CONJUNTO]
    campos = {(c["field"], c["source"]) for c in conjunto["fields"]}
    assert ("hhi", "aneel-samp") in campos
    assert ("company_name", "cvm-cadastros") in campos


def test_as_linhas_dos_setores_sao_de_empresa_ou_de_mercado():
    linhas = [
        linha
        for linha in portao.DIREITOS_DA_API_EXTERNA
        if linha.conjunto == setores.CONJUNTO
    ]
    assert linhas
    assert {linha.categoria for linha in linhas} == {
        portao.Categoria.AGREGADO,
        portao.Categoria.FATO_DE_PJ,
    }
    assert all(linha.vigente_desde >= date(2026, 11, 3) for linha in linhas)
    # cada fonte de agência sai só das tabelas dela e da ligação às companhias
    for linha in linhas:
        assert linha.tabelas, linha


def test_o_contrato_publicado_tem_os_erros_que_a_rota_do_setor_da():
    caminhos = openapi_data_v1()["paths"]
    do_setor = caminhos["/data/v1/sectors/{key}"]["get"]["responses"]
    assert {"400", "401", "404", "429"} <= set(do_setor)
    assert "503" not in do_setor  # lê a ficha da noite, não a base
    assert {"404", "503"}.isdisjoint(caminhos["/data/v1/sectors"]["get"]["responses"])
