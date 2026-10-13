"""Download do ENET da CVM, com educação e retomável (série 1 da base de ML, PR 5).

- **Um pedido por vez, com pausa** (`Baixador`): a CVM recusou dois downloads ao mesmo tempo na
  prova do ENET (13/10/2026). Cada pacote tem de 13 a 33 MB, quase tudo do PDF.
- **Retomável** (`baixar_em_fila`): o que já está guardado é pulado; o que falhou fica para a
  próxima vez, sem parar a fila.
- **O que vai para o acervo é o XML limpo** (`base.enet.limpar_xml`: sem o PDF e sem os dados de
  quem entregou), registrado pelo SHA-256 dele. O SHA-256 do pacote não serve: o ENET monta o zip
  na hora (o PDF leva a data e a hora no nome), e o mesmo documento baixado duas vezes deu dois
  pacotes diferentes com o XML idêntico (conferido em 13/10/2026).
"""

import io
import logging
import re
import time
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from xml.etree.ElementTree import ParseError

import requests
import sqlalchemy as sa
from defusedxml import DefusedXmlException

from base.enet import DocumentoEnet, ler_xml_enet, limpar_xml
from src import acervo
from src.banco.coletas import registrar
from src.banco.modelo import coletas

log = logging.getLogger(__name__)

FONTE = "cvm-enet"
PAUSA_ENTRE_PEDIDOS = 1.5  # segundos entre o fim de um pedido e o começo do próximo
TEMPO_LIMITE = 120  # segundos por pacote
CABECALHO = {"User-Agent": "TickerLab (contato@tickerlab.com.br)"}
# o XML do documento dentro do pacote: 014206DFP31-12-2022v1.xml, 001023ITR31-03-2026v1.xml
NOME_DO_XML = re.compile(r"^\d+(DFP|ITR)\d{2}-\d{2}-\d{4}v\d+\.xml$", re.IGNORECASE)
# o que um pacote ruim pode causar (rede, zip estragado, XML inválido ou malicioso, valor estranho);
# erro do banco não está aqui: ele se repetiria em todos e para a fila
ERROS_DE_UM_PACOTE = (
    OSError,  # inclui os erros de rede do requests
    ValueError,
    zipfile.BadZipFile,
    ParseError,
    DefusedXmlException,
)


class Baixador:
    """Baixa um pacote por vez, esperando `pausa` segundos desde o pedido anterior."""

    def __init__(
        self,
        sessao: requests.Session | None = None,
        pausa: float = PAUSA_ENTRE_PEDIDOS,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self._sessao = sessao or requests.Session()
        self._pausa, self._relogio, self._dormir = pausa, relogio, dormir
        self._ultimo: float | None = None

    def baixar(self, link: str) -> bytes:
        if self._ultimo is not None:
            falta = self._pausa - (self._relogio() - self._ultimo)
            if falta > 0:
                self._dormir(falta)
        try:
            resposta = self._sessao.get(
                link.replace("http://", "https://", 1),
                headers=CABECALHO,
                timeout=TEMPO_LIMITE,
            )
            resposta.raise_for_status()
            return resposta.content
        finally:
            self._ultimo = self._relogio()


@dataclass
class ResultadoDaFila:
    baixados: list[str] = field(default_factory=list)
    falhas: dict[str, str] = field(default_factory=dict)  # link → erro
    pulados: int = 0


def baixar_em_fila(
    links: Iterable[str],
    baixar: Callable[[str], bytes],
    ja_feitos: set[str],
    ao_baixar: Callable[[str, bytes], object],
) -> ResultadoDaFila:
    """Baixa e entrega a `ao_baixar` cada link que ainda não está em `ja_feitos`.

    Um link que falha (no download ou ao guardar) vai para `falhas` e a fila segue.
    """
    resultado = ResultadoDaFila()
    for link in links:
        if link in ja_feitos:
            resultado.pulados += 1
            continue
        try:
            ao_baixar(link, baixar(link))
        except ERROS_DE_UM_PACOTE as erro:  # um pacote ruim não pode parar os outros
            log.warning("ENET: %s falhou (%s)", link, type(erro).__name__)
            resultado.falhas[link] = f"{type(erro).__name__}: {erro}"[:300]
            continue
        resultado.baixados.append(link)
    return resultado


def xml_do_pacote(pacote: bytes) -> bytes:
    """O XML do documento (DFP ou ITR) dentro do zip do ENET."""
    with zipfile.ZipFile(io.BytesIO(pacote)) as arquivo:
        nomes = [
            n for n in arquivo.namelist() if NOME_DO_XML.match(n.rsplit("/", 1)[-1])
        ]
        if not nomes:
            raise ValueError("o pacote do ENET não tem o XML do documento")
        return arquivo.read(nomes[0])


def guardar(
    conexao: sa.Connection, link: str, pacote: bytes, agora: datetime
) -> DocumentoEnet:
    """Lê o documento, guarda o XML limpo no acervo e registra a coleta. Devolve o documento."""
    limpo = limpar_xml(xml_do_pacote(pacote))
    documento = ler_xml_enet(limpo)  # só guarda o que dá para ler
    caminho = acervo.guardar_original(FONTE, link, limpo, agora, extensao=".xml")
    registrar(
        conexao,
        FONTE,
        link,
        limpo,
        "ok",
        detalhe=f"XML sem o PDF; pacote de {len(pacote)} bytes",
        agora=agora,
        caminho_do_original=caminho,
    )
    return documento


def registrar_falha(
    conexao: sa.Connection, link: str, erro: BaseException, agora: datetime
) -> None:
    registrar(
        conexao, FONTE, link, None, "falhou", detalhe=type(erro).__name__, agora=agora
    )


def ja_guardados(conexao: sa.Connection) -> set[str]:
    """Os links do ENET já guardados com sucesso (a fila pula esses)."""
    consulta = sa.select(coletas.c.url).where(
        coletas.c.fonte == FONTE, coletas.c.situacao == "ok"
    )
    return set(conexao.execute(consulta).scalars())
