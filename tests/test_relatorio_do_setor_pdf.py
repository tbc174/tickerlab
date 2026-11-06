"""O PDF do relatório do setor (molde D, PR 5): as seções da tela na mesma ordem, a fonte, "Limites e
cuidados", nenhuma pessoa, as seções com números trancadas sem o plano, e a rota
`GET /v1/relatorio-setor/pdf` com as mesmas regras de acesso da rota da tela."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from base import dossie as dossie_da_base
from src import dossie
from src import relatorio_setor as rs
from src.banco.usuarios import mudar_plano
from src.relatorio_do_setor_pdf import _blocos_de_tabela, relatorio_do_setor
from tests import test_api_v1_rotas as rotas
from tests.test_relatorio_setor import HOJE, _entradas, gravar_noite

chave = rotas.chave
cliente = rotas.cliente
ROTA = "/api/v1/relatorio-setor/pdf"
GERADO_EM = datetime(2026, 10, 21, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


@pytest.fixture
def da_noite(tmp_path):
    secao = dossie.secao_do_setor("eletricas", gravar_noite(tmp_path))
    assert secao is not None
    return secao


def _texto_do_pdf(pdf: bytes) -> str:
    import pypdfium2

    documento = pypdfium2.PdfDocument(pdf)
    try:
        paginas = [p.get_textpage().get_text_range() for p in documento]
    finally:
        documento.close()
    return " ".join(" ".join(paginas).split())


def _pdf(da_noite, plano: str | None = "pro") -> tuple[rs.RelatorioDoSetor, str]:
    relatorio = rs.montar_relatorio_do_setor(_entradas(da_noite), plano, HOJE)
    return relatorio, _texto_do_pdf(relatorio_do_setor(relatorio, GERADO_EM))


def test_pdf_tem_as_secoes_da_tela_na_ordem_e_as_fontes(da_noite) -> None:
    relatorio, texto = _pdf(da_noite)
    posicao = 0
    for _ in range(2):  # o sumário da capa e depois o corpo: cada um na ordem da tela
        for secao in relatorio.secoes:
            posicao = texto.index(secao.titulo, posicao) + 1
    assert "Fontes:" in texto
    for fonte in relatorio.fontes:
        assert fonte in texto
    assert (
        "CPFE3" in texto and "HHI (pontos)" in texto
    )  # tabela escrita, sigla preservada
    assert "21/10/2026" in texto  # a data da geração na capa


def test_pdf_tem_limites_e_cuidados_em_qualquer_plano(da_noite) -> None:
    for plano in ("pro", "gratuito", None):
        _, texto = _pdf(da_noite, plano)
        assert texto.rindex("Limites e cuidados") > texto.rindex("Metodologia")
        assert "recomendação de investimento" in texto
        assert "mercado relevante do CADE" in texto


def test_pdf_sem_o_plano_vem_trancado_sem_numero_da_base(da_noite) -> None:
    relatorio, texto = _pdf(da_noite, "gratuito")
    for secao in relatorio.secoes:
        assert secao.titulo in texto
    assert "4.626" not in texto and "HHI (pontos)" not in texto
    assert "O que não temos" in texto and "Limites e cuidados" in texto


def test_pdf_nao_traz_pessoa(da_noite) -> None:
    relatorio, texto = _pdf(da_noite)
    dossie_da_base.conferir_sem_pessoas(relatorio.como_dict(), set())
    assert not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto)


def test_pdf_sem_a_noite_avisa(da_noite) -> None:
    entradas = _entradas(da_noite)
    sem_noite = rs.EntradasDoSetor(entradas.setor, entradas.membros, None, {}, {})
    relatorio = rs.montar_relatorio_do_setor(sem_noite, "pro", HOJE)
    texto = _texto_do_pdf(relatorio_do_setor(relatorio, GERADO_EM))
    assert "ainda não chegou da base" in texto and "Limites e cuidados" in texto


def test_tabela_larga_vira_de_lado_em_blocos() -> None:
    colunas = ["Companhia", *(f"Indicador {i}" for i in range(8))]
    linhas = [[f"Empresa {n}", *(f"{n}{i}" for i in range(8))] for n in range(6)]
    blocos = _blocos_de_tabela(colunas, linhas)
    assert [len(cabecalho) for cabecalho, _ in blocos] == [5, 3]  # 4 empresas, depois 2
    assert blocos[0][0] == ["Companhia", *(f"Empresa {n}" for n in range(4))]
    assert blocos[1][1][0] == ["Indicador 0", "40", "50"]
    assert _blocos_de_tabela(colunas[:3], [l[:3] for l in linhas]) == [
        (colunas[:3], [l[:3] for l in linhas])
    ]


# --- a rota -----------------------------------------------------------------------------------------
@pytest.fixture
def com_a_noite(banco, tmp_path, monkeypatch):
    from tests.test_fundamentos_no_app import _coletar

    _coletar(banco)
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(tmp_path))
    return gravar_noite(tmp_path)


def _como_pro(banco) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "pro")


def test_rota_devolve_o_pdf_para_o_pro(cliente, banco, com_a_noite) -> None:
    _como_pro(banco)
    resposta = cliente.get(ROTA, params={"setor": "eletricas"})
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.headers["cache-control"] == "no-store"
    assert (
        "relatorio-do-setor-eletricas-tickerlab.pdf"
        in resposta.headers["content-disposition"]
    )
    texto = _texto_do_pdf(resposta.content)
    assert "Limites e cuidados" in texto and "HHI (pontos)" in texto


def test_rota_do_gratuito_vem_trancada(cliente, com_a_noite) -> None:
    resposta = cliente.get(ROTA, params={"setor": "eletricas"})
    assert resposta.status_code == 200
    texto = _texto_do_pdf(resposta.content)
    assert "HHI (pontos)" not in texto and "Limites e cuidados" in texto


@pytest.mark.parametrize("setor", ["aviacao", "../eletricas"])
def test_rota_setor_desconhecido_404(cliente, com_a_noite, setor) -> None:
    resposta = cliente.get(ROTA, params={"setor": setor})
    assert resposta.status_code == 404
    assert setor not in resposta.text


def test_rota_sem_setor_422_e_sem_login_401(cliente) -> None:
    assert cliente.get(ROTA).status_code == 422
    cliente.headers.pop("Cookie")
    assert cliente.get(ROTA, params={"setor": "eletricas"}).status_code == 401
