"""Download do ENET (série 1 da base de ML, PR 5): um pedido por vez, com pausa; retoma só o que
falhou; guarda o XML sem o PDF e sem dados pessoais, registrado pelo SHA-256 do XML (o do pacote
muda a cada download: o ENET monta o zip na hora). Sem internet."""

import hashlib
import io
import zipfile
from datetime import UTC, datetime

import pytest
import requests
import sqlalchemy as sa

from base.enet import limpar_xml
from base.enet_coleta import (
    FONTE,
    PAUSA_ENTRE_PEDIDOS,
    Baixador,
    baixar_em_fila,
    guardar,
    ja_guardados,
    registrar_falha,
    xml_do_pacote,
)
from src import acervo
from src.banco.modelo import coletas
from tests.test_base_enet import NOME_DE_QUEM_ENTREGOU, PDF_FALSO, _dfp

LINK = (
    "http://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx?"
    "CodigoInstituicao=1&NumeroSequencialDocumento=124061"
)
AGORA = datetime(2026, 10, 13, 9, tzinfo=UTC)


def _pacote(xml: bytes, carimbo: str = "13102026071621") -> bytes:
    """Um zip como o do ENET: o XML do documento, o PDF com data e hora no nome e anexos."""
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("014206DFP31-12-2022v1.xml", xml)
        z.writestr(f"124061_014206_{carimbo}.pdf", b"%PDF-1.7 " + carimbo.encode())
        z.writestr("FormularioDemonstracaoFinanceiraDFP.xml", b"<Formulario />")
        z.writestr("DadosDocumento.xlsx", b"planilha")
    return saida.getvalue()


class _Resposta:
    def __init__(self, conteudo=b"zip", status=200):
        self.content, self.status_code = conteudo, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class _Sessao:
    def __init__(self, resposta=None):
        self.pedidos: list[tuple[str, dict]] = []
        self.resposta = resposta or _Resposta()

    def get(self, url, **opcoes):
        self.pedidos.append((url, opcoes))
        return self.resposta


class _Relogio:
    def __init__(self):
        self.agora, self.dormidas = 100.0, []

    def __call__(self):
        return self.agora

    def dormir(self, segundos):
        self.dormidas.append(segundos)
        self.agora += segundos


# --- um pedido por vez ----------------------------------------------------------------------------
def test_um_pedido_por_vez_e_espera_entre_pedidos():
    relogio, sessao = _Relogio(), _Sessao()
    baixador = Baixador(sessao, relogio=relogio, dormir=relogio.dormir)
    baixador.baixar(LINK)
    baixador.baixar(LINK)  # logo em seguida: espera a pausa inteira
    relogio.agora += PAUSA_ENTRE_PEDIDOS * 3
    baixador.baixar(LINK)  # já passou bastante tempo: não espera
    assert relogio.dormidas == [PAUSA_ENTRE_PEDIDOS]
    assert len(sessao.pedidos) == 3


def test_pede_por_https_e_se_identifica():
    sessao = _Sessao()
    Baixador(sessao).baixar(LINK)
    url, opcoes = sessao.pedidos[0]
    assert url.startswith("https://www.rad.cvm.gov.br/")
    assert "TickerLab" in opcoes["headers"]["User-Agent"]
    assert opcoes["timeout"] > 0


def test_erro_do_servidor_sobe_para_quem_chamou():
    with pytest.raises(requests.HTTPError):
        Baixador(_Sessao(_Resposta(status=503))).baixar(LINK)


# --- fila retomável ---------------------------------------------------------------------------------
def test_fila_retoma_so_as_falhas():
    guardados = []

    def baixar(link):
        if link == "b":
            raise requests.ConnectionError("caiu")
        return b"pacote " + link.encode()

    resultado = baixar_em_fila(
        ["a", "b", "c"],
        baixar,
        ja_feitos={"a"},
        ao_baixar=lambda l, p: guardados.append(l),
    )
    assert resultado.baixados == ["c"]
    assert list(resultado.falhas) == ["b"] and "caiu" in resultado.falhas["b"]
    assert resultado.pulados == 1
    assert guardados == ["c"]


def test_fila_registra_pacote_estragado_como_falha_e_segue():
    def guardar_quebrando(link, pacote):
        if link == "a":
            xml_do_pacote(b"isto nao e zip")

    resultado = baixar_em_fila(["a", "b"], lambda l: b"x", set(), guardar_quebrando)
    assert resultado.baixados == ["b"] and list(resultado.falhas) == ["a"]


# --- guarda no acervo --------------------------------------------------------------------------------
def test_xml_do_pacote_acha_o_documento_e_recusa_pacote_sem_ele():
    xml = _dfp()
    assert xml_do_pacote(_pacote(xml)) == xml
    vazio = io.BytesIO()
    with zipfile.ZipFile(vazio, "w") as z:
        z.writestr("DadosDocumento.xlsx", b"x")
    with pytest.raises(ValueError, match="XML"):
        xml_do_pacote(vazio.getvalue())


def test_guarda_xml_sem_pdf_e_o_sha256_do_xml(banco):
    xml = _dfp(versao=2, motivo="Ajuste.")
    with banco.begin() as c:
        documento = guardar(c, LINK, _pacote(xml), AGORA)
    limpo = limpar_xml(xml)
    assert documento.versao == 2 and documento.motivo == "Ajuste."
    with banco.connect() as c:
        linha = c.execute(sa.select(coletas)).one()
        assert ja_guardados(c) == {LINK}
    assert (linha.fonte, linha.situacao) == (FONTE, "ok")
    assert linha.sha256 == hashlib.sha256(limpo).hexdigest()
    assert linha.caminho_do_original.endswith(".xml.gz")
    guardado = acervo.ler_original(linha.caminho_do_original)
    assert guardado == limpo
    assert PDF_FALSO.encode() not in guardado
    assert NOME_DE_QUEM_ENTREGOU.encode() not in guardado
    assert "pacote" in linha.detalhe


def test_mesmo_documento_baixado_de_novo_nao_ocupa_mais_espaco(banco):
    xml = _dfp()
    with banco.begin() as c:
        guardar(c, LINK, _pacote(xml, "13102026071621"), AGORA)
        guardar(c, LINK, _pacote(xml, "13102026081500"), AGORA)  # outro zip, mesmo XML
    with banco.connect() as c:
        caminhos = {l.caminho_do_original for l in c.execute(sa.select(coletas))}
    assert len(caminhos) == 1


def test_falha_fica_registrada_e_nao_conta_como_guardada(banco):
    with banco.begin() as c:
        registrar_falha(c, LINK, requests.ConnectionError("caiu"), AGORA)
    with banco.connect() as c:
        linha = c.execute(sa.select(coletas)).one()
        assert ja_guardados(c) == set()
    assert (linha.situacao, linha.detalhe) == ("falhou", "ConnectionError")
