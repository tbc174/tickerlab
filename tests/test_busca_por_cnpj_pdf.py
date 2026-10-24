"""O PDF do relatório do CNPJ (molde B, PR 4): as seções com fonte e data, "Limites e cuidados", nenhum
nome de pessoa, nada do que está desligado, a mesma resposta para todo CNPJ que a base não tem, e o CNPJ
pedido fora do log. A empresa sem ficha na CVM (cadastro da Receita): `tests/test_busca_por_cnpj_fechadas.py`. Mais a rota `POST /v1/busca-por-cnpj/pdf`."""

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from base import dossie as dossie_da_base
from src import busca_por_cnpj as busca
from src.banco import demonstracoes as repo
from src.banco.usuarios import mudar_plano
from src.relatorio_do_cnpj_pdf import relatorio_do_cnpj
from tests import test_api_v1_rotas as rotas
from tests.test_busca_por_cnpj import HOJE, PETROBRAS, _gravar_ficha

chave = rotas.chave
cliente = rotas.cliente
ROTA = "/api/v1/busca-por-cnpj/pdf"
GERADO_EM = datetime(2026, 10, 20, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def _texto_do_pdf(pdf: bytes) -> str:
    import pypdfium2

    documento = pypdfium2.PdfDocument(pdf)
    try:
        paginas = [p.get_textpage().get_text_range() for p in documento]
    finally:
        documento.close()
    return " ".join(" ".join(paginas).split())


@pytest.fixture
def com_a_petrobras(banco, tmp_path):
    from tests.test_fundamentos_no_app import _coletar

    _coletar(banco)
    return _gravar_ficha(tmp_path)


def _relatorio(banco, pasta, plano="pro", texto=PETROBRAS):
    with banco.connect() as conexao:
        return busca.buscar_por_cnpj(conexao, texto, plano, HOJE, pasta)


def _pdf(banco, pasta, plano="pro", texto=PETROBRAS) -> str:
    rel = _relatorio(banco, pasta, plano, texto)
    return _texto_do_pdf(relatorio_do_cnpj(rel, GERADO_EM))


def test_pdf_tem_as_secoes_na_ordem_e_a_fonte_com_a_data(
    banco, com_a_petrobras
) -> None:
    texto = _pdf(banco, com_a_petrobras)
    posicoes = [
        texto.index(t) for t in ("Cadastro", "Ligações na rede", "Limites e cuidados")
    ]
    assert posicoes == sorted(posicoes)
    assert "cadastro da CVM em" in texto  # a data em que o cadastro ficou público
    assert "Fonte:" in texto and "ODbL" in texto
    assert "17/10/2026" in texto  # o dia da ficha
    assert "CPFL Paulista" in texto  # a rede: empresa com empresa, nunca pessoa


def test_pdf_tem_limites_e_cuidados_e_o_que_nao_aparece(banco, com_a_petrobras) -> None:
    for plano in ("pro", "gratuito"):
        texto = _pdf(banco, com_a_petrobras, plano)
        assert "Limites e cuidados" in texto
        assert "recomendação de investimento" in texto
        assert "Aparecem as companhias abertas" in texto
        assert "O que ainda não aparece" in texto


def test_pdf_sem_o_plano_vem_trancado(banco, com_a_petrobras) -> None:
    texto = _pdf(banco, com_a_petrobras, "gratuito")
    assert "CPFL Paulista" not in texto
    assert "Cadastro" in texto and "Limites e cuidados" in texto


def test_pdf_nao_traz_nome_de_pessoa(banco, com_a_petrobras) -> None:
    """Risco 1 (ADR 0075): sem CPF, sem cargo e sem sócio. A ficha com coluna de pessoa já nem entra."""
    texto = _pdf(banco, com_a_petrobras)
    assert not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto)
    assert not re.search(r"\b(Diretor|Conselheir|Administrador|Acionista)", texto)
    assert "Nome de sócio ou administrador pessoa física: não aparece" in texto


def test_pdf_nao_traz_o_que_esta_desligado(banco, com_a_petrobras) -> None:
    """Riscos 2 e 3: nenhuma seção do molde D, nem dado da Receita ou da PGFN, só a lista do que falta."""
    rel = _relatorio(banco, com_a_petrobras)
    assert not set(dossie_da_base.SECOES_DO_MOLDE_D) & {s.chave for s in rel.secoes}
    texto = _texto_do_pdf(relatorio_do_cnpj(rel, GERADO_EM))
    for secao in rel.secoes:
        assert secao.titulo in texto
    for ligacao in ("Natureza jurídica:", "Situação cadastral:", "Dívida ativa:"):
        assert ligacao not in texto


def test_pdf_de_cnpj_fechado_e_desconhecido_diz_a_mesma_coisa(
    banco, com_a_petrobras
) -> None:
    """Risco 5: a empresa que o app conhece (tem setor), sem ficha e sem o cadastro da Receita, responde
    igual à desconhecida."""
    with banco.begin() as conexao:
        repo.gravar_setor(conexao, "00.000.000/0001-91", "Bancos")
    a = _pdf(banco, com_a_petrobras, texto="00000000000191")
    b = _pdf(banco, com_a_petrobras, texto="11222333000181")
    assert a.replace("00.000.000/0001-91", "CNPJ") == b.replace(
        "11.222.333/0001-81", "CNPJ"
    )
    assert "não está na base do TickerLab" in a
    assert "Limites e cuidados" in a and "Bancos" not in a


def test_gerar_o_pdf_nao_poe_o_cnpj_no_log(banco, com_a_petrobras, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        _pdf(banco, com_a_petrobras)
        _pdf(banco, com_a_petrobras, texto="11.222.333/0001-81")
    todo = " ".join(r.getMessage() for r in caplog.records)
    for trecho in ("33000167", "33.000.167", "11222333", "11.222.333"):
        assert trecho not in todo


# --- a rota -----------------------------------------------------------------------------------------
@pytest.fixture
def pasta_das_fichas(banco, tmp_path, monkeypatch):
    from tests.test_fundamentos_no_app import _coletar

    _coletar(banco)
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(tmp_path))
    return _gravar_ficha(tmp_path)


def _como_pro(banco) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "pro")


def test_rota_devolve_o_pdf_como_anexo(cliente, banco, pasta_das_fichas) -> None:
    _como_pro(banco)
    resposta = cliente.post(ROTA, json={"cnpj": "33.000.167/0001-01"})
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.content.startswith(b"%PDF")
    cabecalho = resposta.headers["content-disposition"]
    assert cabecalho.startswith("attachment") and "33000167" not in cabecalho
    assert resposta.headers["cache-control"] == "no-store"
    assert "CPFL Paulista" in _texto_do_pdf(resposta.content)


def test_rota_do_gratuito_vem_trancada(cliente, pasta_das_fichas) -> None:
    resposta = cliente.post(ROTA, json={"cnpj": PETROBRAS})
    assert resposta.status_code == 200
    assert "CPFL Paulista" not in _texto_do_pdf(resposta.content)


def test_rota_fora_da_base_aberta_tambem_devolve_pdf(cliente, pasta_das_fichas) -> None:
    resposta = cliente.post(ROTA, json={"cnpj": "11222333000181"})
    assert resposta.status_code == 200
    assert "não está na base do TickerLab" in _texto_do_pdf(resposta.content)


@pytest.mark.parametrize("cnpj", ["33000167000102", "abc", ""])
def test_rota_cnpj_invalido_422(cliente, pasta_das_fichas, cnpj) -> None:
    assert cliente.post(ROTA, json={"cnpj": cnpj}).status_code == 422


def test_rota_sem_login_401(cliente) -> None:
    cliente.headers.pop("Cookie")
    assert cliente.post(ROTA, json={"cnpj": PETROBRAS}).status_code == 401


def test_rota_nao_poe_o_cnpj_no_log(cliente, pasta_das_fichas, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        cliente.post(ROTA, json={"cnpj": PETROBRAS})
        cliente.post(ROTA, json={"cnpj": "11.222.333/0001-81"})
    todo = " ".join(r.getMessage() for r in caplog.records)
    for trecho in ("33000167", "33.000.167", "11222333", "11.222.333"):
        assert trecho not in todo
