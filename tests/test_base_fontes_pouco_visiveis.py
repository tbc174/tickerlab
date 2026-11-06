"""Fontes, famílias de licença e originais das fontes pouco visíveis (linha 718; ADR 0124).

Sudeco (FDCO) e Sudam (FDA): CC BY-ND, como a CONAB; a cópia do PDF não é republicada. Jornal oficial,
FNET e prospecto (família `divida`): só prova interna; na ficha, fato e link. Os CSV do PERSE
e do II/IPI ficam na família `rfb-renuncias`, que já cobre o endereço deles.
"""

from datetime import UTC, datetime

from base import fatos_documentais
from base.arquivo import fontes, lote_documentais, registro
from base.licenca import familia_do_endereco
from src.banco import coletas
from src.banco.coletas import Coleta, Guarda

FAMILIAS_NOVAS = ("sudeco", "sudam", "divida")
FONTES_NOVAS = {"divida-documental", "sudeco-fdco", "sudam-fda"}
SUDECO = "https://www.gov.br/sudeco/pt-br/assuntos/fundo-de-desenvolvimento-do-centro-oeste/projetos"
RECEITA = "https://arquivos.receitafederal.gov.br/Dados/Obrigacoes_Acessorias/"
AGORA = datetime(2026, 11, 5, 23, tzinfo=UTC)


class _SemRede:
    """Os originais vêm do manifesto conferido: descobrir não lê nada da rede."""

    def ler(self, url: str):
        raise AssertionError(f"leu a rede: {url}")


def test_familias_novas_tem_licenca_coleta_e_termos_lidos():
    for familia in FAMILIAS_NOVAS:
        assert familia in coletas.LICENCAS, familia
        assert familia in coletas.COLETA_E_GUARDA, familia
    assert registro.TERMOS_LIDOS_EM["sudeco"] == registro.TERMOS_LIDOS_EM["sudam"]


def test_divida_nao_diz_que_leu_termos_que_nao_leu():
    """Os termos dos sites dos PDFs não foram lidos um a um: o catálogo público não mostra data."""
    assert coletas.COLETA_E_GUARDA["divida"].coleta is Coleta.NAO_LIDA
    assert "divida" not in registro.TERMOS_LIDOS_EM


def test_familias_novas_tem_revenda_e_guarda():
    assert coletas.REVENDA["sudeco"] == coletas.VENDAVEL_RISCO_ASSUMIDO
    assert coletas.REVENDA["sudam"] == coletas.VENDAVEL_RISCO_ASSUMIDO
    assert "BY-ND" in coletas.LICENCAS["sudeco"]
    assert coletas.REVENDA["divida"] == coletas.A_CONFIRMAR
    assert coletas.COLETA_E_GUARDA["divida"].guarda is Guarda.SO_PROVA


def test_familia_do_endereco_das_paginas_novas():
    assert familia_do_endereco(SUDECO) == "sudeco"
    assert (
        familia_do_endereco("https://www.gov.br/sudam/pt-br/01.07.25projetos.pdf")
        == "sudam"
    )
    for endereco in (
        "https://auniao.pb.gov.br/servicos/copy_of_jornal-a-uniao/2026/abril/x.pdf",
        "https://digital.jornaldocomercio.com/jcomercio/2026/04/17/144286/issue14177.pdf",
        "https://ecoagro.agr.br/emissoes-integra/660",
        "https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id=1064843",
    ):
        assert familia_do_endereco(endereco) == "divida", endereco
    for caminho in (
        "EFD_Contribuicoes/receita-desonerada-pis-cofins-efd.csv",
        "DUIMP/renuncia-ii-ipi.csv",
    ):
        assert familia_do_endereco(RECEITA + caminho) == "rfb-renuncias", caminho


def test_licenca_da_rfb_renuncias_cita_perse_e_ii_ipi():
    texto = coletas.LICENCAS["rfb-renuncias"]
    assert "PERSE" in texto
    assert "II/IPI" in texto


def test_originais_documentais_no_catalogo_do_arquivista():
    por_id = {f.id: f for f in fontes.FONTES if f.id in FONTES_NOVAS}
    assert set(por_id) == FONTES_NOVAS
    manifesto = lote_documentais.originais_documentais()
    for id_, fonte in por_id.items():
        assert fonte.grupo == "mensal"
        assert (
            fonte.tipo == "pdf"
        )  # o arquivista recusa HTML ou outro tipo no lugar do PDF
        alvos = fonte.descobrir(_SemRede(), AGORA)
        esperados = [o["url"] for o in manifesto if o["fonte"] == id_]
        assert [a.url for a in alvos] == esperados and esperados, id_
        assert {a.extensao for a in alvos} == {".pdf"}
    for original in manifesto:
        familia = familia_do_endereco(original["url"])
        assert coletas.licenca_da_fonte(original["fonte"]) == coletas.LICENCAS[familia]


def test_todo_pdf_do_gabarito_tem_original_no_manifesto():
    gabarito = fatos_documentais.gabarito()
    pdfs = set(
        gabarito.loc[~gabarito["fonte"].str.endswith(".csv"), "documento_sha256"]
    )
    manifesto = {o["sha256"] for o in lote_documentais.originais_documentais()}
    assert pdfs <= manifesto, pdfs - manifesto
