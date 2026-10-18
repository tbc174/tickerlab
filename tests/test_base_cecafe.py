"""Relatório mensal do Cecafé: fonte só pesquisa e leitor do resumo (café, PR 6).

`cecafe_relatorio_pequeno.pdf` é um dublê (9 linhas) com números do relatório de setembro/2026.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from base.arquivo import coleta, destinos, fontes
from base.arquivo.coleta import ErroDeDescoberta
from base.commodities import cecafe
from src.banco import coletas

PASTA = Path(__file__).parent / "arquivos" / "commodities"
AGORA = datetime(2026, 10, 18, 22, tzinfo=UTC)
ROBOTS_ABERTO = b"User-agent: *\nDisallow: /wp-admin/\n"
ROBOTS_COM_PDF_PROIBIDO = b"User-agent: *\nDisallow: /*.pdf$\nDisallow: /wp-*/\n"
PAGINA = (
    b'<a href="https://www.cecafe.com.br/site/wp-content/uploads/graficos/'
    b'CECAFE-Relatorio-Mensal-SETEMBRO-2026.pdf">Relatorio mensal</a>'
)


class Paginas:
    def __init__(self, paginas):
        self.paginas = paginas

    def ler(self, url, **_):
        return coleta.Resposta(url, self.paginas[url], {})


def test_ler_pdf_cecafe_arabica_conilon_soluvel():
    resumo = cecafe.ler_resumo((PASTA / "cecafe_relatorio_pequeno.pdf").read_bytes())
    assert (resumo.ano, resumo.mes) == (2026, 9)
    assert resumo.sacas_por_tipo == {
        "arabica": 2766290,
        "canefora": 813904,
        "soluvel": 304899,
        "torrado": 8654,
    }
    assert resumo.sacas_por_destino == {"E.U.A.": 625192, "Alemanha": 482236}


def test_pdf_que_nao_e_o_relatorio_da_erro_claro():
    with pytest.raises(cecafe.RelatorioIlegivel):
        cecafe.ler_resumo(b"%PDF-1.4 nao e um pdf de verdade")


def test_a_fonte_so_pesquisa_esta_no_arquivista():
    destino = destinos.DESTINOS["cecafe-relatorio-mensal"]
    assert destino.tipo == destinos.SO_PESQUISA
    assert "18/10/2026" in destino.porque and "robots.txt" in destino.porque
    fonte = fontes.POR_ID["cecafe-relatorio-mensal"]
    assert (fonte.grupo, fonte.tipo) == ("mensal", "pdf")
    assert destinos.DESTINOS["termos-cecafe-robots"].tipo == destinos.VIGIA


def test_licenca_do_cecafe_e_so_pesquisa():
    assert (
        coletas.revenda_da_fonte("cecafe-relatorio-mensal") == coletas.REVENDA["cecafe"]
    )
    assert (
        coletas.marca_da_fonte("cecafe-relatorio-mensal") == coletas.Marca.NAO_COMERCIAL
    )


def test_descoberta_acha_o_pdf_quando_o_robots_deixa():
    cliente = Paginas(
        {fontes.CECAFE_ROBOTS: ROBOTS_ABERTO, fontes.CECAFE_RELATORIOS: PAGINA}
    )
    alvos = fontes.POR_ID["cecafe-relatorio-mensal"].descobrir(cliente, AGORA)
    assert [a.url.rsplit("/", 1)[-1] for a in alvos] == [
        "CECAFE-Relatorio-Mensal-SETEMBRO-2026.pdf"
    ]


def test_descoberta_nao_baixa_nada_se_o_robots_proibe_pdf():
    cliente = Paginas(
        {
            fontes.CECAFE_ROBOTS: ROBOTS_COM_PDF_PROIBIDO,
            fontes.CECAFE_RELATORIOS: PAGINA,
        }
    )
    with pytest.raises(ErroDeDescoberta, match="robots.txt"):
        fontes.POR_ID["cecafe-relatorio-mensal"].descobrir(cliente, AGORA)
