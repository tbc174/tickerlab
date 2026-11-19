"""Dublês para os testes do bot de pesquisa (`pesquisa/`): cliente de rede falso, PDF e planilha
pequenos feitos na hora. Nenhum teste do bot usa a internet."""

import io
from collections.abc import Mapping
from pathlib import Path

import pytest
import requests
from openpyxl import Workbook

from base.arquivo.coleta import Resposta

ROBOTS_ABERTO = "User-agent: *\nDisallow: /privado/\n"


def erro_http(status: int) -> requests.HTTPError:
    resposta = requests.Response()
    resposta.status_code = status
    return requests.HTTPError(f"HTTP {status}", response=resposta)


class ClienteFalso:
    """Responde de um dicionário `url -> bytes | Exception`. Guarda os pedidos feitos."""

    def __init__(
        self,
        paginas: Mapping[str, bytes | Exception],
        robots: str | None = ROBOTS_ABERTO,
        cabecalhos: Mapping[str, str] | None = None,
    ) -> None:
        self.paginas = dict(paginas)
        self.robots = robots
        self.cabecalhos_padrao = dict(cabecalhos or {})
        self.pedidos: list[str] = []

    def _conteudo(self, url: str) -> bytes:
        if url.endswith("/robots.txt"):
            if self.robots is None:
                raise erro_http(404)
            return self.robots.encode()
        self.pedidos.append(url)
        item = self.paginas[url]
        if isinstance(item, Exception):
            raise item
        return item

    def ler(self, url: str) -> Resposta:
        return Resposta(url, self._conteudo(url), {"Content-Type": "text/html"})

    def cabecalhos(self, url: str) -> Mapping[str, str]:
        return self.cabecalhos_padrao

    def baixar(self, url: str, destino: Path) -> Mapping[str, str]:
        destino.write_bytes(self._conteudo(url))
        return {"Content-Type": "application/octet-stream", **self.cabecalhos_padrao}


def pdf_com_texto(paginas: list[str]) -> bytes:
    """Um PDF mínimo e válido, uma página por texto (só ASCII)."""
    objetos: list[bytes] = []
    quantidade = len(paginas)
    filhos = " ".join(f"{3 + 2 * i} 0 R" for i in range(quantidade))
    objetos.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objetos.append(f"<< /Type /Pages /Kids [{filhos}] /Count {quantidade} >>".encode())
    for indice, texto in enumerate(paginas):
        fluxo = f"BT /F1 12 Tf 50 700 Td ({texto}) Tj ET".encode()
        objetos.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {4 + 2 * indice} 0 R "
                f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>"
            ).encode()
        )
        objetos.append(
            b"<< /Length %d >>\nstream\n" % len(fluxo) + fluxo + b"\nendstream"
        )
    saida = io.BytesIO()
    saida.write(b"%PDF-1.4\n")
    posicoes = []
    for numero, corpo in enumerate(objetos, 1):
        posicoes.append(saida.tell())
        saida.write(b"%d 0 obj\n" % numero + corpo + b"\nendobj\n")
    inicio_xref = saida.tell()
    saida.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1))
    for posicao in posicoes:
        saida.write(b"%010d 00000 n \n" % posicao)
    saida.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objetos) + 1, inicio_xref)
    )
    return saida.getvalue()


def xlsx_com_linhas(linhas: list[list[object]], planilha: str = "Dados") -> bytes:
    pasta = Workbook()
    folha = pasta.active
    assert folha is not None
    folha.title = planilha
    for linha in linhas:
        folha.append(linha)
    saida = io.BytesIO()
    pasta.save(saida)
    return saida.getvalue()


def html_com_links(titulo: str, links: list[tuple[str, str]], texto: str = "") -> bytes:
    ancoras = "".join(f'<a href="{href}">{rotulo}</a>' for href, rotulo in links)
    return (
        f"<html><head><title>{titulo}</title><script>var x=1;</script></head>"
        f"<body><p>{texto}</p>{ancoras}</body></html>"
    ).encode()


@pytest.fixture(autouse=True)
def sem_docling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Os testes leem com o núcleo (pypdf, openpyxl): o Docling baixa modelos e demora minutos.
    Quem testa o caminho do Docling o faz com um dublê (`test_docling_*`)."""
    from pesquisa import leitores

    monkeypatch.setattr(leitores, "docling_instalado", lambda: False)
