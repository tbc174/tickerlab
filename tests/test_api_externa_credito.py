"""A ficha de crédito na API externa (linha 754, PR 2): `/data/v1/credit/{cnpj}` e o lote.

Base de mentira de `test_credito_sinais` (a Mundial cede a dois FIDCs; o GPA tem insolvência e rating),
sem internet. As linhas de direito são as de verdade (`DIREITOS_DA_API_EXTERNA`); o teste só põe as
tabelas prontas (D10). Riscos do plano: vazar o que o portão nega (rating, insolvência, PGFN, listas de uso
interno, pagamentos de PE e ES), servir as regras de elegibilidade (CVM 9: fatos, não opinião), vazar
pessoa (MEI) e olhar o futuro (cada fato só a partir do dia em que ficou público).
"""

import dataclasses
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from base import cnpj as cnpj_
from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import rotas
from src.api_externa.conjuntos import credito
from src.banco.modelo import consumo_da_api
from src.credito.dicionario import DA_BASE, DA_FICHA
from src.credito.sinais import DO_FIDC
from src.portao_externo import (
    DIREITOS_DA_API_EXTERNA,
    PALAVRAS_QUE_NUNCA_SAEM,
    Finalidade,
)
from tests import ajudantes_da_api_externa as aj
from tests.test_credito_sinais import DIA, GPA, MEI, MUNDIAL, TABELAS, _entidade

AGORA = datetime(2026, 11, 10, 12, tzinfo=UTC)
FORA_DA_REDE = "11222333000181"
# o MEI de test_credito_sinais não tem dígito verificador válido (a rota o recusaria com 400 antes de
# chegar à rede): para a rota, uma pessoa com CNPJ válido que a rede conhece como pessoa
PESSOA = "445556660001" + cnpj_.digitos_verificadores("445556660001")
ROTA = f"/data/v1/credit/{MUNDIAL}"
LOTE = "/data/v1/credit/batch"


def _extras() -> dict:
    """As tabelas de `test_credito_sinais`, com o GPA também conhecido pela rede como empresa."""
    rede = [
        _entidade(MUNDIAL, False),
        _entidade(MEI, True),
        _entidade(PESSOA, True),
        _entidade(GPA, False),
    ]
    extras = {nome: pd.DataFrame(linhas) for nome, linhas in TABELAS.items()}
    extras["entidades"] = pd.DataFrame([entidade for entidade, _ in rede])
    extras["identificadores"] = pd.DataFrame([ident for _, ident in rede])
    return extras


def _porta(pasta) -> Porta:
    return Porta(pasta, arquivos={}, conferidas={}, extras=_extras())


def _ficha(pasta, cnpj, dia=DIA, permitido=None):
    with _porta(pasta) as porta:
        leitor = credito.LeitorDeCredito(porta, permitido or (lambda *_: True))
        return leitor.ficha(cnpj, dia)


# ---------------------------------------------------------------- o leitor


def test_a_mundial_sai_com_os_fatos_do_fidc_e_da_receita(tmp_path):
    servida = _ficha(tmp_path, MUNDIAL)
    assert servida is not None
    corpo = servida.corpo
    assert corpo["cnpj"] == MUNDIAL
    assert corpo["como_era_em"] == DIA.isoformat()
    assert corpo["fundos_em_que_cede"] == {
        "valor": 2,
        "fonte": "cvm-fidc",
        "publico_em": "2026-10-15",
        "visto_em": None,
    }
    assert corpo["situacao_cadastral_na_receita"]["valor"] == "Ativa"
    assert corpo["situacao_cadastral_na_receita"]["fonte"] == "rfb-cnpj"
    assert corpo["limites"] == list(credito.LIMITES)
    assert servida.fontes == {"cvm-fidc", "rfb-cnpj", "cvm-hist-ipe"}
    assert servida.linhas == 1


def test_mesmo_com_o_portao_aberto_so_saem_os_fatos_com_linha_de_direito(tmp_path):
    # o GPA tem insolvência e rating na base; a Mundial tem PGFN, CGU, MTE, IBAMA, Paraná, Minas, PE e ES
    for cnpj in (GPA, MUNDIAL):
        servida = _ficha(tmp_path, cnpj)
        assert servida is not None
        fatos = set(servida.corpo) - {"cnpj", "como_era_em", "limites"}
        assert fatos <= set(credito.FATOS), cnpj
        for chave in fatos:
            assert not PALAVRAS_QUE_NUNCA_SAEM & set(chave.split("_")), chave


def test_as_regras_de_elegibilidade_nao_saem(tmp_path):
    servida = _ficha(tmp_path, GPA)  # o GPA aciona a regra de insolvência como sacado
    assert servida is not None
    corpo = servida.corpo
    assert not {"regras", "papel", "resultado", "efeito"} & set(corpo)
    texto = str(corpo).lower()
    assert "inelegivel" not in texto and "inelegível" not in texto


def test_campo_que_o_portao_nega_nao_aparece(tmp_path):
    def sem_o_fidc(fonte, _campo, _derivado):
        return fonte != "cvm-fidc"

    servida = _ficha(tmp_path, MUNDIAL, permitido=sem_o_fidc)
    assert servida is not None
    corpo = servida.corpo
    assert not set(DO_FIDC) & set(corpo)
    assert "cvm-fidc" not in servida.fontes
    assert "situacao_cadastral_na_receita" in corpo


def test_o_portao_recebe_a_fonte_do_acervo_e_o_campo_como_derivado(tmp_path):
    perguntas = []

    def anota(fonte, campo, derivado):
        perguntas.append((fonte, campo, derivado))
        return True

    _ficha(tmp_path, MUNDIAL, permitido=anota)
    assert perguntas
    for fonte, campo, derivado in perguntas:
        assert credito.FATOS[campo].fonte == fonte
        assert derivado is True


def test_portao_fechado_nada_sai(tmp_path):
    assert _ficha(tmp_path, MUNDIAL, permitido=lambda *_: False) is None


@pytest.mark.parametrize("cnpj", [MEI, FORA_DA_REDE])
def test_mei_e_quem_a_rede_nao_conhece_nao_saem(tmp_path, cnpj):
    assert _ficha(tmp_path, cnpj) is None


def test_cnpj_invalido_e_recusado(tmp_path):
    with pytest.raises(ValueError, match="CNPJ inválido"):
        _ficha(tmp_path, "123")


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(dias=st.integers(min_value=0, max_value=400))
def test_nenhum_fato_e_de_depois_do_dia_pedido(tmp_path, dias):
    dia = date.fromordinal(DIA.toordinal() - dias)
    servida = _ficha(tmp_path, MUNDIAL, dia=dia)
    if servida is None:
        return
    for chave, valor in servida.corpo.items():
        if isinstance(valor, dict):
            assert valor["publico_em"] <= dia.isoformat(), chave


# ---------------------------------------------------------------- os direitos


def _linhas_de_credito():
    return [
        linha for linha in DIREITOS_DA_API_EXTERNA if linha.conjunto == credito.CONJUNTO
    ]


def test_os_fatos_servidos_sao_as_linhas_de_direito_do_conjunto():
    linhas = _linhas_de_credito()
    assert {(linha.fonte, linha.campo, linha.tabelas) for linha in linhas} == {
        (origem.fonte, chave, (origem.tabela,))
        for chave, origem in credito.FATOS.items()
    }
    assert {linha.finalidade for linha in linhas} == {Finalidade.CREDITO}


def test_todo_fato_servido_e_da_ficha():
    assert set(credito.FATOS) <= {*DA_BASE, *DA_FICHA}


# ---------------------------------------------------------------- a rota


def _regras_do_credito() -> portao.Regras:
    """As regras de verdade, com as tabelas de `credit` prontas (provas do D10) no dia do teste."""
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    tabelas = {origem.tabela for origem in credito.FATOS.values()}
    return dataclasses.replace(
        portao.regras_vigentes(),
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


def _organizacao(banco, monkeypatch, pasta, finalidade="credito", conjunto="credit"):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=conjunto, finalidade=finalidade)
    monkeypatch.setattr(rotas, "regras_da_api", _regras_do_credito)
    monkeypatch.setattr(rotas, "abrir_porta", lambda _banco: _porta(pasta))
    return org, chave


@pytest.fixture
def cenario(banco, monkeypatch, tmp_path):
    return _organizacao(banco, monkeypatch, tmp_path)


@pytest.fixture
def cliente(monkeypatch, cenario):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, cenario, rota=ROTA, **parametros):
    _org, chave = cenario
    return cliente.get(rota, params=parametros, headers=aj.bearer(chave.valor))


def _consumo(banco, org) -> list[tuple]:
    with banco.connect() as conexao:
        return conexao.execute(
            sa.select(
                consumo_da_api.c.conjunto,
                consumo_da_api.c.finalidade,
                consumo_da_api.c.pedidos,
                consumo_da_api.c.negados,
            ).where(consumo_da_api.c.organizacao_id == org.id)
        ).all()


def test_a_ficha_sai_em_ingles_com_fonte_e_atribuicao(cliente, cenario, banco):
    resposta = _get(cliente, cenario)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cnpj"] == MUNDIAL
    assert corpo["known_at"] == "2026-11-10"
    assert corpo["fidcs_as_assignor"] == {
        "value": 2,
        "source": "cvm-fidc",
        "published_at": "2026-10-15",
        "observed_at": None,
    }
    assert corpo["rfb_registration_status"]["value"] == "Ativa"
    assert corpo["limits"] == list(credito.LIMITES)
    fontes = {fonte["source"]: fonte for fonte in corpo["sources"]}
    assert set(fontes) == {"cvm-fidc", "cvm-hist-ipe", "rfb-cnpj"}
    assert "CVM" in fontes["cvm-fidc"]["attribution"]
    assert "Receita" in fontes["rfb-cnpj"]["attribution"]
    org, _chave = cenario
    assert _consumo(banco, org) == [("credit", "credito", 1, 0)]


def test_known_at_antes_do_informe_do_fidc_nao_traz_o_fidc(cliente, cenario):
    corpo = _get(cliente, cenario, known_at="2026-01-01").json()
    assert "fidcs_as_assignor" not in corpo


@pytest.mark.parametrize("cnpj", [PESSOA, FORA_DA_REDE])
def test_mei_e_quem_a_rede_nao_conhece_dao_not_available(cliente, cenario, cnpj, banco):
    resposta = _get(cliente, cenario, rota=f"/data/v1/credit/{cnpj}")
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}
    org, _chave = cenario
    assert _consumo(banco, org) == [("credit", "credito", 0, 1)]


def test_contrato_de_analise_nao_abre_o_credito(banco, monkeypatch, tmp_path):
    _org, chave = _organizacao(banco, monkeypatch, tmp_path, finalidade="analise")
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    resposta = cliente.get(ROTA, headers=aj.bearer(chave.valor))
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "not_available"}


def test_contrato_de_credito_de_outro_conjunto_nao_abre_a_ficha(
    banco, monkeypatch, tmp_path
):
    _org, chave = _organizacao(banco, monkeypatch, tmp_path, conjunto="companies")
    cliente = aj.cliente_da_api(monkeypatch, AGORA)
    assert cliente.get(ROTA, headers=aj.bearer(chave.valor)).status_code == 404


def test_sem_a_prontidao_das_tabelas_nada_sai(cliente, cenario, monkeypatch):
    monkeypatch.setattr(
        rotas, "regras_da_api", lambda: None
    )  # as regras de hoje: nada pronto
    assert _get(cliente, cenario).status_code == 404


def test_cnpj_invalido_e_known_at_no_futuro_dao_400(cliente, cenario):
    assert _get(cliente, cenario, rota="/data/v1/credit/123").json() == {
        "detail": "invalid_cnpj"
    }
    assert _get(cliente, cenario, known_at="2026-12-01").json() == {
        "detail": "invalid_known_at"
    }


def test_lote_com_status_por_item_e_um_pedido_por_cnpj(cliente, cenario, banco):
    org, chave = cenario
    resposta = cliente.post(
        LOTE,
        json={"cnpjs": [MUNDIAL, PESSOA, "123"]},
        headers=aj.bearer(chave.valor),
    )
    assert resposta.status_code == 200
    itens = {item["cnpj"]: item for item in resposta.json()["items"]}
    assert itens[MUNDIAL]["status"] == "ok"
    assert itens[MUNDIAL]["fidcs_as_assignor"]["value"] == 2
    assert itens[PESSOA] == {"cnpj": PESSOA, "status": "not_available"}
    assert itens["123"]["status"] == "invalid_cnpj"
    assert _consumo(banco, org) == [("credit", "credito", 2, 0)]


def test_sem_chave_da_401(cliente):
    assert cliente.get(ROTA).status_code == 401
