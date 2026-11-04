"""O endereço público de cada fonte citada nos relatórios (linha 601 da fila).

Cada número do relatório do setor e da ficha traz a fonte escrita ("DFP e ITR entregues à CVM"); aqui
ela ganha o endereço da página da base aberta de onde o dado vem, para quem lê conferir. O texto da
fonte continua o mesmo: o endereço vai no fim, depois de " — ". A data do dado já vai ao lado, na base
do número. Sem Streamlit nem banco: a tela, o PDF, o Markdown e a API leem o mesmo texto.
"""

import re

SEPARADOR = " — "
_ENDERECO = re.compile(r"https://[^\s;,)]*[^\s;,).]")
_CVM = "https://dados.cvm.gov.br/dataset/"

# (trecho que aparece na fonte, rótulo, endereço); o trecho é procurado sem diferenciar maiúsculas,
# como palavra inteira. A ordem é a de aparição no texto da fonte.
REGRAS: tuple[tuple[str, str, str], ...] = (
    (r"DFP", "DFP", _CVM + "cia_aberta-doc-dfp"),
    (r"ITR", "ITR", _CVM + "cia_aberta-doc-itr"),
    (r"FCA", "FCA", _CVM + "cia_aberta-doc-fca"),
    (r"FRE|Formulário de Referência", "FRE", _CVM + "cia_aberta-doc-fre"),
    (r"IPE", "IPE", _CVM + "cia_aberta-doc-ipe"),
    (r"VLMO", "VLMO", _CVM + "cia_aberta-doc-vlmo"),
    (r"cadastro de companhias", "cadastro da CVM", _CVM + "cia_aberta-cad"),
    (r"ofertas registradas", "ofertas", _CVM + "oferta-distrib"),
    (r"fundos", "fundos (CDA)", _CVM + "fi-doc-cda"),
    (r"ANEEL", "ANEEL", "https://dadosabertos.aneel.gov.br/"),
    (r"Yahoo Finance", "Yahoo Finance", "https://finance.yahoo.com/"),
    (r"Banco Central", "Banco Central", "https://dadosabertos.bcb.gov.br/"),
    (r"IBGE", "IBGE", "https://sidra.ibge.gov.br/"),
)
_GERAL_DA_CVM = ("CVM", "CVM", "https://dados.cvm.gov.br/")


def enderecos_da_fonte(fonte: str) -> list[tuple[str, str]]:
    """Os pares (rótulo, endereço) das bases que o texto da fonte cita, sem repetir. A "CVM" sozinha,
    sem documento citado, leva ao portal de dados abertos dela."""
    achados = []
    for trecho, rotulo, url in REGRAS:
        if re.search(rf"(?<!\w){trecho}(?!\w)", fonte, re.IGNORECASE):
            achados.append((rotulo, url))
    if not achados and re.search(r"(?<!\w)CVM(?!\w)", fonte):
        achados.append(_GERAL_DA_CVM[1:])
    return achados


def fonte_com_endereco(fonte: str) -> str:
    """A fonte com os endereços no fim ("texto — DFP: https://...; ITR: https://..."). Idempotente,
    e a fonte sem base conhecida volta como veio."""
    if not fonte or _ENDERECO.search(fonte):
        return fonte
    pares = enderecos_da_fonte(fonte)
    if not pares:
        return fonte
    return fonte + SEPARADOR + "; ".join(f"{rotulo}: {url}" for rotulo, url in pares)


def paragrafo_com_endereco(paragrafo: str) -> str:
    """O parágrafo "Fonte: ...", com o ponto final no fim, ganha os endereços; os outros voltam iguais."""
    prefixo = "Fonte: "
    if not paragrafo.startswith(prefixo):
        return paragrafo
    corpo = paragrafo.removeprefix(prefixo)
    ponto = corpo.endswith(".")
    com = fonte_com_endereco(corpo.removesuffix("."))
    return prefixo + com + ("." if ponto else "")


def separar(fonte: str) -> tuple[str, list[tuple[str, str]]]:
    """O texto da fonte sem os endereços e os pares (rótulo, endereço) que vinham no fim."""
    texto, achou, resto = fonte.partition(SEPARADOR)
    if not achou or not _ENDERECO.search(resto):
        return fonte, []
    pares = []
    for parte in resto.split("; "):
        rotulo, _, url = parte.partition(": ")
        if _ENDERECO.fullmatch(url):
            pares.append((rotulo, url))
    return texto, pares
