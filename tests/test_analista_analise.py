"""A análise completa na tela do analista (`src/analista/analise.py`): a montagem da rota `/analysis` pelo portão da tela.

A montagem tem os testes dela em `test_api_externa_analise_montagem.py` e a rota da API em
`test_api_externa_analise.py`; aqui fica o que é da tela: os blocos abrem pelo que o portão da tela (o da API externa,
sem o contrato da organização) libera hoje, nunca pela finalidade de crédito; os três estados (pronta, não liberada,
não disponível) sem dizer o motivo; nada de pessoa; os nomes de bloco na voz da tela, com o título; e os limites
sem nome de campo de quem programa. Base de mentira, sem internet.
"""

import dataclasses

import pytest

from base.dossie import COLUNAS_DE_PESSOA, conferir_sem_pessoas
from base.porta import Porta
from src.analista import analise, leitura
from src.api_externa import tabelas_por_cnpj
from src.api_externa.conjuntos import analise as analise_
from src.api_externa.conjuntos import socios_pj
from src.portao_externo import Finalidade
from tests import ajudantes_da_api_externa as aj
from tests import test_api_externa_analise as analise_de_mentira
from tests import test_api_externa_empresas as empresas_de_mentira
from tests import test_api_externa_socios_pj as socios_de_mentira

HOJE = analise_de_mentira.AGORA.date()
EMPRESA = empresas_de_mentira.EMPRESA


@pytest.fixture
def pasta(tmp_path):
    return socios_de_mentira.base_com_socios(tmp_path)


def _analise(pasta, cnpj: str = EMPRESA, regras=None, piloto: bool = False):
    with Porta(pasta) as porta:
        return analise.analise(
            porta,
            cnpj,
            hoje=HOJE,
            regras=regras or analise_de_mentira._regras(),
            piloto=piloto,
        )


# ---------------------------------------------------------------- o que sai


def test_pronta_com_frase_cadastro_socios_pj_fontes_e_titulos(pasta):
    resposta = _analise(pasta)
    assert resposta.estado == leitura.PRONTA
    corpo = resposta.corpo
    assert corpo["cnpj"] == EMPRESA
    assert corpo["frase"]["texto"].startswith("ALFA")
    assert corpo["frase"]["tipo"] == analise_.FATO
    nomes = [bloco["nome"] for bloco in corpo["blocos"]]
    assert nomes[0] == analise_.CADASTRO
    assert "socios_pj" in nomes
    for bloco in corpo["blocos"]:
        assert bloco["titulo"] and bloco["o_que_traz"]
    socios = next(b for b in corpo["blocos"] if b["nome"] == "socios_pj")
    raizes = [s["raiz_do_cnpj"] for s in socios["corpo"][socios_pj.SOCIAS]]
    assert (
        socios_de_mentira.HOLDING in raizes
    )  # o quadro de hoje (a tela lê o dia de hoje)
    assert {f["fonte"] for f in resposta.fontes} >= {"rfb-cnpj"}
    assert resposta.linhas > 0


def test_as_leituras_sao_deducao_e_citam_o_bloco_na_voz_da_tela(pasta):
    corpo = _analise(pasta).corpo
    assert corpo["leituras"]
    for item in corpo["leituras"]:
        assert item["tipo"] == analise_.DEDUCAO
        assert set(item["a_partir_de"]) <= {b.nome for b in analise_.BLOCOS} | {
            analise_.CADASTRO
        }


def test_linha_do_tempo_e_nao_encontrado_trazem_o_bloco_pelo_nome_da_tela(pasta):
    corpo = _analise(pasta).corpo
    nomes = {b.nome for b in (*analise_.CADASTROS, *analise_.BLOCOS)}
    for marco in corpo["linha_do_tempo"]:
        assert marco["bloco"] in nomes
        assert marco["titulo_do_bloco"]
        assert marco["dia"] <= HOJE.isoformat()
    for item in corpo["nao_encontrado"] + corpo["nao_respondeu_a_tempo"]:
        assert item["bloco"] in nomes
        assert item["titulo"]


def test_o_que_nao_traz_fala_da_tela_e_inclui_o_credito(pasta):
    corpo = _analise(pasta).corpo
    textos = corpo["ainda_nao_traz"]
    assert not any(analise_.NAO_DISPONIVEL_NESTA_CHAVE in t for t in textos)
    assert any("CGU" in t and analise.NAO_DISPONIVEL_NA_TELA in t for t in textos)
    assert analise.CREDITO_NAO_DISPONIVEL in textos
    assert any("Pessoas físicas" in t for t in textos)


def test_limites_sem_nome_de_campo_de_quem_programa(pasta):
    limites = _analise(pasta).corpo["limites"]
    assert limites
    for proibido in ("known_at", "ainda_nao_traz", "truncated", "organização pode ver"):
        assert not any(proibido in limite for limite in limites), proibido
    assert any("recomendação de investimento" in limite for limite in limites)


def test_sem_pessoa_na_resposta(pasta):
    corpo = _analise(pasta).corpo
    conferir_sem_pessoas(corpo, set())
    assert not aj.chaves_de(corpo) & COLUNAS_DE_PESSOA
    texto = str(corpo)
    assert socios_de_mentira.SEM_LISTA not in texto
    assert socios_de_mentira.EMPRESARIO not in texto


def test_o_bloco_de_credito_nunca_abre_na_tela(pasta, monkeypatch):
    """A tela lê só com a finalidade de análise (a leitura mais estreita): o crédito é de contrato próprio."""
    vistas = []
    original = analise_.montar_analise

    def espiar(*args, **kwargs):
        liberadas = set(kwargs["liberadas"])
        vistas.append(liberadas)
        return original(*args, **{**kwargs, "liberadas": liberadas})

    monkeypatch.setattr(analise_, "montar_analise", espiar)
    corpo = _analise(pasta).corpo
    assert vistas
    assert all(fin == Finalidade.ANALISE.value for _, fin, _, _ in vistas[0])
    assert "credito" not in {b["nome"] for b in corpo["blocos"]}


# ---------------------------------------------------------------- os outros estados


def test_sem_prontidao_e_nao_liberada_sem_ler_a_base(tmp_path):
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    regras = dataclasses.replace(analise_de_mentira._regras(), prontidao={})
    resposta = _analise(vazia, regras=regras)
    assert resposta.estado == leitura.NAO_LIBERADA
    assert resposta.corpo is None


@pytest.mark.parametrize(
    "cnpj",
    [
        empresas_de_mentira.INEXISTENTE,
        empresas_de_mentira.MEI,
        empresas_de_mentira.EMPRESARIO_INDIVIDUAL,
    ],
)
def test_pessoa_mei_e_cnpj_desconhecido_dao_a_mesma_resposta(pasta, cnpj):
    resposta = _analise(pasta, cnpj)
    assert resposta.estado == leitura.NAO_DISPONIVEL
    assert resposta.corpo is None
    assert resposta.fontes == []


@pytest.mark.parametrize("cnpj", ["123", "abc", ""])
def test_cnpj_invalido_e_value_error(pasta, cnpj):
    with pytest.raises(ValueError):
        _analise(pasta, cnpj)


def test_cada_bloco_tem_titulo_na_tela():
    """Bloco novo na análise (uma tabela do registro, por exemplo) precisa do título da tela, ou a aba mostra o
    nome interno: o teste cobra."""
    for bloco in (*analise_.CADASTROS, *analise_.BLOCOS):
        assert bloco.nome in analise.TITULOS, bloco.nome


def test_integridade_nunca_abre_na_tela_mesmo_com_o_portao_liberando(
    pasta, monkeypatch
):
    """Sanções (CGU), embargos (IBAMA) e lista suja (MTE) só saem para a organização com o conjunto de integridade
    no contrato (ADR 0122, Emenda 1). A tela não tem o contrato da organização: mesmo que a prontidão um dia libere
    as tabelas, o conjunto fica fora e a análise diz "não disponível nesta tela"."""
    monkeypatch.setattr(
        analise,
        "decidir",
        lambda *_args, **_kw: type("Libera", (), {"libera": True})(),
    )
    regras = analise_de_mentira._regras()
    liberadas = analise.liberadas_na_tela(HOJE, regras)
    assert liberadas  # o portão de mentira libera tudo o mais
    assert tabelas_por_cnpj.INTEGRIDADE not in {conjunto for conjunto, *_ in liberadas}
    fechado = analise.portao_da_tela(HOJE, regras, piloto=False)(
        tabelas_por_cnpj.INTEGRIDADE, Finalidade.ANALISE.value
    )
    assert not fechado("cgu-ceis", "cnpj", False)
    corpo = _analise(pasta, regras=regras).corpo
    integridade = {
        tabelas_por_cnpj.SANCOES,
        tabelas_por_cnpj.EMBARGOS_AMBIENTAIS,
        tabelas_por_cnpj.LISTA_SUJA,
    }
    assert not integridade & {b["nome"] for b in corpo["blocos"]}
    for fonte in ("CGU", "IBAMA", "MTE"):
        assert any(
            fonte in t and analise.NAO_DISPONIVEL_NA_TELA in t
            for t in corpo["ainda_nao_traz"]
        ), fonte
