"""Resumo do relatório mensal do Cecafé (café, PR 6): sacas por tipo de café e por destino.

Marca "não comercial" registrada (`licencas-por-fonte.md`; o robots.txt do site veda PDF): pela
ADR 0102 o arquivista guarda o PDF com ritmo e este leitor o resume; o que for para tela, API ou
tabela cita o Cecafé e o mês do relatório. O relatório chama a espécie conilon + robusta de "canéfora".
"""

import re
import unicodedata
from dataclasses import dataclass, field

import pypdfium2

MESES = (
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)  # fmt: skip
TIPOS = ("arabica", "canefora", "soluvel", "torrado")
CABECALHO = re.compile(r"relatorio mensal (\w+) (\d{4})")
LINHA_DE_TIPO = re.compile(r"^(arabica|canefora|soluvel|torrado) - total ([\d.]+) ")
INICIO_DOS_DESTINOS = re.compile(r"^paises de destino \w+ \d{4}")
LINHA_DE_DESTINO = re.compile(r"^(\D.*?) ([\d.]+) [\d.]+ -?[\d,]+%$")


class RelatorioIlegivel(ValueError):
    """O PDF não é (ou não parece mais) o relatório mensal do Cecafé."""


@dataclass(frozen=True)
class ResumoCecafe:
    ano: int
    mes: int
    sacas_por_tipo: dict[str, int] = field(default_factory=dict)
    sacas_por_destino: dict[str, int] = field(default_factory=dict)


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def _inteiro(texto: str) -> int:
    return int(texto.replace(".", ""))


def _linhas(pdf: bytes) -> list[str]:
    try:
        documento = pypdfium2.PdfDocument(pdf)
        texto = "\n".join(p.get_textpage().get_text_range() for p in documento)
    except pypdfium2.PdfiumError as erro:
        raise RelatorioIlegivel("o arquivo não abre como PDF") from erro
    return [" ".join(_sem_acento(t).split()) for t in texto.splitlines()]


def ler_resumo(pdf: bytes) -> ResumoCecafe:
    """As sacas de 60 kg do mês por tipo de café e pelos principais destinos (colunas do mês)."""
    linhas = _linhas(pdf)
    titulo = next((m for l in linhas if (m := CABECALHO.search(l.lower()))), None)
    if titulo is None or titulo.group(1) not in MESES:
        raise RelatorioIlegivel("não achei 'Relatório mensal <mês> <ano>' no PDF")
    por_tipo: dict[str, int] = {}
    por_destino: dict[str, int] = {}
    nos_destinos = False
    for linha in linhas:
        minuscula = linha.lower()
        if tipo := LINHA_DE_TIPO.match(minuscula):
            por_tipo.setdefault(tipo.group(1), _inteiro(tipo.group(2)))
        elif INICIO_DOS_DESTINOS.match(minuscula):
            nos_destinos = not por_destino  # só o primeiro quadro: o do mês
        elif nos_destinos and minuscula.startswith(("sub-total", "total geral")):
            nos_destinos = False
        elif nos_destinos and (destino := LINHA_DE_DESTINO.match(linha)):
            por_destino[destino.group(1)] = _inteiro(destino.group(2))
    if not por_tipo:
        raise RelatorioIlegivel("não achei o quadro de sacas por tipo de café")
    return ResumoCecafe(
        ano=int(titulo.group(2)),
        mes=MESES.index(titulo.group(1)) + 1,
        sacas_por_tipo=por_tipo,
        sacas_por_destino=por_destino,
    )
