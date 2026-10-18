"""O dossiê da base no relatório da empresa (plano do dossiê da empresa no app, 17/10/2026, PR 3,
tarefas 13 e 14): o Pro vê as seções com os números; o Gratuito e o Plus, só os títulos e o convite.

A tranca é feita na montagem do `Relatorio`, no servidor: a página, o PDF e a API recebem a mesma
coisa, então quem não é Pro não acha nenhum número da base nem no `como_dict`.
"""

import json
from datetime import date
from io import BytesIO

import pytest
from pypdf import PdfReader

from src import dossie
from src import relatorio_empresa as re_
from src.relatorio_empresa_pdf import relatorio_da_empresa
from tests.test_relatorio_empresa import _entradas, dados_da_weg  # noqa: F401

CHAVES_DA_BASE = [  # na ordem do molde A: capital, governança, setor, negócios
    "ofertas_e_fundos",
    "auditor_e_controladas",
    "setor_regulado",
    "negocios",
]
DEPOIS_DE_DIAS = date(2026, 10, 18)


def _dossie(hoje: date = DEPOIS_DE_DIAS) -> re_.Dossie:
    return dossie.dossie_da_ficha(
        dossie.cortar(dossie.ler_ficha(dossie.FICHA_DE_EXEMPLO)), hoje
    )


@pytest.fixture
def entradas(dados_da_weg):  # noqa: F811
    return _entradas(dados_da_weg, dossie=_dossie())


def _valores(objeto: object) -> set[str]:
    """Todo texto e número de uma estrutura (o `como_dict`), em texto."""
    if isinstance(objeto, dict):
        return {v for valor in objeto.values() for v in _valores(valor)}
    if isinstance(objeto, list):
        return {v for valor in objeto for v in _valores(valor)}
    return set() if objeto is None or isinstance(objeto, bool) else {str(objeto)}


def _da_base(relatorio: re_.Relatorio) -> list[re_.Secao]:
    return [s for s in relatorio.secoes if s.chave in CHAVES_DA_BASE]


def test_pro_ve_as_secoes_da_base_no_lugar_do_molde(entradas):
    relatorio = re_.montar(entradas, "pro")
    chaves = [s.chave for s in relatorio.secoes]
    assert [c for c in chaves if c in CHAVES_DA_BASE] == CHAVES_DA_BASE
    assert chaves.index("ofertas_e_fundos") == chaves.index("dividendos") + 1
    assert chaves.index("setor_regulado") == chaves.index("pares") + 1
    assert chaves.index("negocios") == chaves.index("eventos") + 1
    fundos = relatorio.secao("ofertas_e_fundos")
    assert not fundos.trancada
    assert {i.texto for i in fundos.itens} >= {"370", "R$ 495,2 mi"}
    assert fundos.tabelas["fundos_por_mes"]


def test_pro_ve_a_fonte_e_a_atribuicao_odbl(entradas):
    relatorio = re_.montar(entradas, "pro")
    for secao in _da_base(relatorio):
        assert any(p.startswith("Fonte: ") for p in secao.paragrafos), secao.chave
    assert "ODbL (dados abertos da CVM; citar a fonte)" in relatorio.fontes


def test_pro_ve_os_limites_da_base_e_que_nada_e_recomendacao(entradas):
    limites = " ".join(re_.montar(entradas, "pro").secao("limites").paragrafos)
    assert "Nada aqui é recomendação" in limites
    assert "valor registrado" in limites
    assert "Nomes de pessoas" in limites


def test_ficha_em_dia_diz_de_quando_sao_os_dados(entradas):
    negocios = re_.montar(entradas, "pro").secao("negocios")
    assert negocios.paragrafos[0] == "Dados da base do TickerLab de 17/10/2026."


def test_ficha_velha_avisa(dados_da_weg):  # noqa: F811
    velha = _entradas(dados_da_weg, dossie=_dossie(date(2026, 10, 25)))
    for secao in _da_base(re_.montar(velha, "pro")):
        assert "17/10/2026" in secao.paragrafos[0]
        assert "atrasados" in secao.paragrafos[0]


@pytest.mark.parametrize("plano", ["gratuito", "plus", None, "desconhecido"])
def test_quem_nao_e_pro_ve_so_os_titulos_e_o_convite(entradas, plano):
    relatorio = re_.montar(entradas, plano)
    secoes = _da_base(relatorio)
    assert [s.chave for s in secoes] == CHAVES_DA_BASE
    for secao in secoes:
        assert secao.trancada
        assert secao.itens == [] and secao.tabelas == {}
        assert "plano Pro" in " ".join(secao.paragrafos)
        assert not any(c.isdigit() for p in secao.paragrafos for c in p)


@pytest.mark.parametrize("plano", ["gratuito", "plus"])
def test_nenhum_numero_da_base_no_como_dict_de_quem_nao_e_pro(
    dados_da_weg,  # noqa: F811
    entradas,
    plano,
):
    pro = re_.montar(entradas, "pro").como_dict()
    da_base = _valores([s for s in pro["secoes"] if s["chave"] in CHAVES_DA_BASE])
    sem_dossie = _valores(re_.montar(_entradas(dados_da_weg), plano).como_dict())
    trancado = _valores(re_.montar(entradas, plano).como_dict())
    vazou = (trancado & da_base) - sem_dossie
    titulos = {s.titulo for s in _da_base(re_.montar(entradas, plano))}
    assert vazou <= titulos | set(CHAVES_DA_BASE), vazou
    assert "PRICEWATERHOUSECOOPERS AUDITORES INDEPENDENTES LTDA" in da_base
    texto = json.dumps(re_.montar(entradas, plano).como_dict(), ensure_ascii=False)
    for numero in ("495,2", "9.743.641", "PRICEWATERHOUSECOOPERS", "ODbL (dados"):
        assert numero not in texto


def test_sem_ficha_nao_ha_secao_da_base(dados_da_weg):  # noqa: F811
    for plano in ("pro", "gratuito"):
        relatorio = re_.montar(_entradas(dados_da_weg), plano)
        assert [s.chave for s in relatorio.secoes] == list(re_.SECOES)


# --- PDF -----------------------------------------------------------------------------------------


def _texto_do_pdf(pdf: bytes) -> str:
    texto = " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
    return "".join(texto.split())


def test_pdf_do_pro_tem_os_titulos_e_uma_tabela_de_cada_secao(entradas):
    relatorio = re_.montar(entradas, "pro")
    texto = _texto_do_pdf(relatorio_da_empresa(relatorio))
    for secao in _da_base(relatorio):
        assert "".join(secao.titulo.split()) in texto, secao.chave
        primeira = dossie.titulo_da_tabela(next(iter(secao.tabelas)))
        assert "".join(primeira.split()) in texto, primeira
    assert "495,2" in texto and "PRICEWATERHOUSECOOPERS" in texto


def test_pdf_de_quem_nao_e_pro_tem_os_titulos_sem_os_numeros(entradas):
    relatorio = re_.montar(entradas, "gratuito")
    texto = _texto_do_pdf(relatorio_da_empresa(relatorio))
    for secao in _da_base(relatorio):
        assert "".join(secao.titulo.split()) in texto
    assert "planoPro" in texto
    for numero in ("495,2", "9.743.641", "PRICEWATERHOUSECOOPERS"):
        assert numero not in texto
