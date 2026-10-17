"""Coleta em gotas dos PDFs dos ratings no sistema da CVM: a lista vem do IPE guardado, para no
limite da CVM e não pede de novo o que já veio. Sem internet: o IPE é montado aqui e o RAD é falso."""

import io
import zipfile
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from base import ratings
from scripts import coletar_ratings_pdf
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import registrar
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import coletas

VERSAO = "9b1e0c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7c"
CABECALHO = (
    "CNPJ_Companhia;Nome_Companhia;Codigo_CVM;Data_Referencia;Categoria;Tipo;Especie;Assunto;"
    "Data_Entrega;Tipo_Apresentacao;Protocolo_Entrega;Versao;Link_Download"
)
RAD = "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&descTipo=IPE"
PDF = b"%PDF-1.4\n...\n%%EOF\n"
PAGINA_DE_LIMITE = b"\r\n<!DOCTYPE html><html><body>Limite de acessos</body></html>"


def _ipe(ano: int, *protocolos_e_datas: tuple[str, str]) -> bytes:
    linhas = [
        f"11.111.111/0001-11;EMPRESA SA;9999;{data};Dados Econômico-Financeiros;"
        f"Relatório de Agência de Rating;;Fitch;{data};AP;{p};1;{RAD}&numProtocolo={p}"
        for p, data in protocolos_e_datas
    ]
    linhas.append(  # sem rating: não entra na lista
        f"11.111.111/0001-11;EMPRESA SA;9999;{ano}-01-02;Fato Relevante;Fato Relevante;;"
        f"Dividendos;{ano}-01-02;AP;999;1;{RAD}&numProtocolo=999"
    )
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        texto = "\n".join([CABECALHO, *linhas])
        z.writestr(f"ipe_cia_aberta_{ano}.csv", texto.encode("cp1252"))
    return saida.getvalue()


def _guardar_ipe(ano: int, conteudo: bytes) -> None:
    url = ratings.URL_DO_IPE.format(ano=ano)
    quando = datetime(2026, 10, 1, tzinfo=UTC)
    caminho = acervo.guardar_original(ratings.FONTE_DO_IPE, url, conteudo, quando)
    with criar_engine().begin() as c:
        registrar(c, ratings.FONTE_DO_IPE, url, conteudo, "ok", agora=quando,
                  caminho_do_original=caminho)  # fmt: skip


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    monkeypatch.setattr(coletar_ratings_pdf, "PAUSA_ENTRE_DOWNLOADS", 0)
    migrar_para("head", url=url)
    _guardar_ipe(2023, _ipe(2023, ("10", "2023-05-02"), ("11", "2023-08-09")))
    _guardar_ipe(2024, _ipe(2024, ("20", "2024-03-05")))


def _rad_falso(monkeypatch, respostas: dict[str, bytes | None]) -> list[str]:
    """O RAD de mentira: a resposta de cada protocolo; quem não está, página de limite."""
    pedidos: list[str] = []

    def baixar(endereco: str) -> bytes | None:
        pedidos.append(endereco)
        protocolo = endereco.split("numProtocolo=")[1]
        return coletar_ratings_pdf.conferir_documento(
            respostas.get(protocolo, PAGINA_DE_LIMITE)
        )

    monkeypatch.setattr(
        coletar_ratings_pdf,
        "baixar",
        coletar_ratings_pdf.com_registro(ratings.FONTE_DOS_PDFS, baixar),
    )
    return pedidos


def _protocolos(pedidos: list[str]) -> list[str]:
    return [p.split("numProtocolo=")[1] for p in pedidos]


def _situacoes() -> dict[str, str]:
    with criar_engine().connect() as c:
        return dict(
            c.execute(
                sa.select(coletas.c.url, coletas.c.situacao).where(
                    coletas.c.fonte == ratings.FONTE_DOS_PDFS
                )
            ).all()
        )


def test_lista_vem_do_ipe_guardado_do_mais_novo_ao_mais_velho(ambiente):
    with criar_engine().connect() as c:
        lista = coletar_ratings_pdf.alvos(c)
    assert _protocolos(list(lista["link"])) == ["20", "11", "10"]


def test_para_no_limite_da_cvm_sem_erro(ambiente, monkeypatch):
    pedidos = _rad_falso(monkeypatch, {"20": PDF})
    assert coletar_ratings_pdf.main(["--maximo", "10"]) == 0  # o limite não é erro
    assert _protocolos(pedidos) == ["20", "11"]
    assert sorted(_situacoes().values()) == ["falhou", "ok"]


def test_nao_pede_de_novo_o_que_ja_veio_e_respeita_o_maximo(ambiente, monkeypatch):
    pedidos = _rad_falso(monkeypatch, {"20": PDF, "11": None, "10": PDF})
    coletar_ratings_pdf.main(["--maximo", "2"])
    assert _protocolos(pedidos) == ["20", "11"]
    coletar_ratings_pdf.main(["--maximo", "10"])
    # o que veio, ou que a CVM disse não existir, não é pedido de novo
    assert _protocolos(pedidos) == ["20", "11", "10"]
    assert sorted(_situacoes().values()) == ["nao_encontrado", "ok", "ok"]


def test_conferir_documento_recusa_a_pagina_de_limite_e_aceita_outros_formatos():
    with pytest.raises(coletar_ratings_pdf.LimiteDaCVM):
        coletar_ratings_pdf.conferir_documento(PAGINA_DE_LIMITE)
    assert coletar_ratings_pdf.conferir_documento(None) is None
    assert coletar_ratings_pdf.conferir_documento(PDF) == PDF
    # alguns documentos do IPE não são PDF (Word, por exemplo): guardar, sem confundir com o limite
    word = b"PK\x03\x04[Content_Types].xml"
    assert coletar_ratings_pdf.conferir_documento(word) == word
