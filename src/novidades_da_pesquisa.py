"""O que vale para uma novidade da pesquisa (linha 830), dos dois lados: o exportador no PC e a API no servidor.

Uma novidade é uma fonte que o bot conferente provou (trecho literal e sha256 do original). Aqui ficam as regras
que decidem se ela pode sair: só conjunto público da lista `CONJUNTOS`, citação curta e nenhuma marca de pessoa
física. Sem Streamlit e sem acesso ao banco: tipos simples.
"""

import re
import unicodedata
from urllib.parse import urlsplit

from base.cnpj import dv_confere
from src.pessoa_no_texto import telefone_no_texto, texto_de_pessoa

# como o trecho foi recortado do original (marcado fora das aspas por quem mostra)
SEM_CORTE = ""
CORTE_NO_INICIO = "inicio"
CORTE_NO_FIM = "fim"
CORTE_NOS_DOIS = "ambos"
RECORTES = frozenset({SEM_CORTE, CORTE_NO_INICIO, CORTE_NO_FIM, CORTE_NOS_DOIS})

TRECHO_MAXIMO = 300  # citação curta, não a página
CNPJ_TAMANHO = 14

# (domínio, prefixo do caminho) -> (chave da fonte no catálogo de licenças `LICENCAS`, nome do órgão). Lista positiva
# **por conjunto**, negada por padrão (Diretoria, 11/11/2026, ADR 0128): só entra conjunto que se verificou que não
# traz pessoa na linha (o cadastro de companhias e o de fundos da CVM trazem responsável, e-mail, telefone e diretor:
# ficam fora). Domínio ou caminho fora daqui não sai. BCB, ANEEL e ANP esperam o conjunto verificado.
CONJUNTOS: tuple[tuple[str, str, str, str], ...] = (
    ("dados.cvm.gov.br", "/dados/CIA_ABERTA/DOC/DFP/", "cvm", "CVM"),
    ("dados.cvm.gov.br", "/dados/CIA_ABERTA/DOC/ITR/", "cvm", "CVM"),
    ("dados.cvm.gov.br", "/dados/FI/DOC/INF_DIARIO/", "cvm", "CVM"),
)

# CNPJ (numérico ou alfanumérico) solto no texto, depois do NFKC e da caixa alta: tolera espaço, ponto, barra,
# hífen e travessão entre os grupos, e letra colada antes ou depois (só dígito colado não vale). Quem acha mais
# CNPJ só deixa a regra mais estreita (todos precisam estar na lista sem pessoa).
_SEP = r"[\s./\-‐-―]*"
CNPJ_NO_TEXTO = re.compile(
    rf"(?=((?<![0-9])[0-9A-Z]{{2}}{_SEP}[0-9A-Z]{{3}}{_SEP}[0-9A-Z]{{3}}{_SEP}[0-9A-Z]{{4}}{_SEP}\d{{2}}(?![0-9])))"
)
SEPARADOR_DE_CNPJ = re.compile(_SEP)
CPF_FORMATADO = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
ONZE_DIGITOS = re.compile(r"(?<!\d)\d{11}(?!\d)")
# qualquer separador comum entre dígitos (espaço, ponto, traços Unicode, barra, vírgula, sublinhado)
SEPARADOR_ENTRE_DIGITOS = re.compile(r"(?<=\d)[\s.\-‐-―−/,_]{1,3}(?=\d)")
CPF_MASCARADO = re.compile(r"[*xX•#]{3}\D{0,2}\d{3}\D{0,2}\d{3}\D{0,2}[*xX•#]{2}")
MARCAS_DE_PESSOA = re.compile(
    r"\b(?:cpf|rg|sr\.|sra\.|dr\.|dra\.|nascid[oa]|filiação|pessoa\s+f[ií]sica)(?!\w)",
    re.IGNORECASE,
)


def _cpf_valido(onze: str) -> bool:
    if len(set(onze)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * (tamanho + 1 - i) for i, d in enumerate(onze[:tamanho]))
        if (soma * 10 % 11) % 10 != int(onze[tamanho]):
            return False
    return True


def achar_cpf(texto: str) -> bool:
    """CPF formatado, mascarado ou com 11 dígitos (separados por qualquer pontuação) com os verificadores certos.

    Texto em NFKC (largura total, espaço não separável). Na dúvida, para: falso alarme é aceitável.
    """
    texto = unicodedata.normalize("NFKC", texto)
    if CPF_FORMATADO.search(texto) or CPF_MASCARADO.search(texto):
        return True
    colado = SEPARADOR_ENTRE_DIGITOS.sub("", texto)
    return any(
        _cpf_valido(achado)
        for variante in (texto, colado)
        for achado in ONZE_DIGITOS.findall(variante)
    )


def cnpjs_validos(texto: str) -> set[str]:
    """Os CNPJs (14 caracteres, sem pontuação) do texto cujos dígitos verificadores conferem."""
    texto = unicodedata.normalize("NFKC", texto).upper()
    limpos = (
        SEPARADOR_DE_CNPJ.sub("", m.group(1)) for m in CNPJ_NO_TEXTO.finditer(texto)
    )
    return {cnpj for cnpj in limpos if len(cnpj) == CNPJ_TAMANHO and dv_confere(cnpj)}


def orgao_da_url(url: str) -> tuple[str, str] | None:
    """(fonte, órgão) do endereço, se o domínio e o caminho são de um conjunto da lista; senão None."""
    try:
        partes = urlsplit(url)
        host = (partes.hostname or "").lower()
    except ValueError:  # `https://[dados...`: endereço malformado nunca é fonte
        return None
    if partes.scheme not in ("http", "https") or "\\" in url or "%" in partes.path:
        return None
    if ".." in partes.path.split("/"):
        return None
    for dominio, prefixo, fonte, orgao in CONJUNTOS:
        if host == dominio and partes.path.startswith(prefixo):
            return fonte, orgao
    return None


def fonte_liberada(fonte: str) -> bool:
    """A fonte tem licença conhecida e revenda liberada (vendável com atribuição); uso interno, não."""
    from src.banco.coletas import (  # import tardio: `coletas` é pesado
        SEM_LICENCA_CONHECIDA,
        licenca_da_fonte,
        revenda_da_fonte,
    )

    return licenca_da_fonte(fonte) != SEM_LICENCA_CONHECIDA and revenda_da_fonte(
        fonte
    ).startswith("vendável")


def sinal_de_contato(texto: str) -> bool:
    """CPF, e-mail ou telefone no texto (a mesma busca nas duas pontas: exportador e API)."""
    normal = unicodedata.normalize("NFKC", texto)
    return achar_cpf(normal) or texto_de_pessoa(normal) or telefone_no_texto(normal)


def texto_publicavel(trecho: str, *textos: str, url: str = "") -> bool:
    """Citação curta com CNPJ válido **no próprio trecho servido**, sem sinal de pessoa em nenhum texto.

    `textos` (afirmação, trecho inteiro, posição) e o `url` não saem, mas também não podem trazer CPF, e-mail,
    telefone nem marca de pessoa (a marca não olha o endereço)."""
    tudo = " ".join((trecho, *textos, url))
    return (
        0 < len(trecho) <= TRECHO_MAXIMO
        and bool(cnpjs_validos(trecho))
        and not sinal_de_contato(tudo)
        and not MARCAS_DE_PESSOA.search(" ".join((trecho, *textos)))
    )
