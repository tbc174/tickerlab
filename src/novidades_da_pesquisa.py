"""O que vale para uma novidade da pesquisa (linha 830), dos dois lados: o exportador no PC e a API no servidor.

Uma novidade é uma fonte que o bot conferente provou (trecho literal e sha256 do original). Aqui ficam as regras
que decidem se ela pode sair: só órgão público da tabela `ORGAOS`, citação curta e nenhuma marca de pessoa
física. Sem Streamlit e sem acesso ao banco: tipos simples.
"""

import re
import unicodedata
from urllib.parse import urlsplit

# como o trecho foi recortado do original (marcado fora das aspas por quem mostra)
SEM_CORTE = ""
CORTE_NO_INICIO = "inicio"
CORTE_NO_FIM = "fim"
CORTE_NOS_DOIS = "ambos"
RECORTES = frozenset({SEM_CORTE, CORTE_NO_INICIO, CORTE_NO_FIM, CORTE_NOS_DOIS})

TRECHO_MAXIMO = 300  # citação curta, não a página

# domínio -> (chave da fonte no catálogo de licenças `LICENCAS`, nome do órgão). Domínio fora daqui não sai
# (portal genérico, que serve vários órgãos, também não: não diz de quem é a prova).
ORGAOS: dict[str, tuple[str, str]] = {
    "dados.cvm.gov.br": ("cvm", "CVM"),
    "conteudo.cvm.gov.br": ("cvm", "CVM"),
    "dadosabertos.bcb.gov.br": ("bcb", "Banco Central do Brasil"),
    "www.bcb.gov.br": ("bcb", "Banco Central do Brasil"),
    "www.bndes.gov.br": ("bndes", "BNDES"),
    "pncp.gov.br": ("pncp", "PNCP"),
    "dadosabertos.aneel.gov.br": ("aneel", "ANEEL"),
    "dadosabertos.ans.gov.br": ("ans", "ANS"),
    "dados.pgfn.gov.br": ("pgfn", "PGFN"),
    "dadosabertos.ibama.gov.br": ("ibama", "IBAMA"),
    "sidra.ibge.gov.br": ("ibge", "IBGE"),
    "www.ibge.gov.br": ("ibge", "IBGE"),
    "www.susep.gov.br": ("susep", "SUSEP"),
    "dados.anp.gov.br": ("anp", "ANP"),
    "dadosabertos.tcu.gov.br": ("tcu", "TCU"),
    "portaldatransparencia.gov.br": ("cgu", "CGU"),
}

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


def orgao_da_url(url: str) -> tuple[str, str] | None:
    """(fonte, órgão) do endereço, se o domínio é de um órgão da tabela; senão None."""
    partes = urlsplit(url)
    if partes.scheme not in ("http", "https") or "\\" in url:
        return None
    return ORGAOS.get((partes.hostname or "").lower())


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


def texto_publicavel(afirmacao: str, trecho: str, *outros: str) -> bool:
    """Citação curta e sem CPF nem marca de pessoa física; `outros` (endereço, posição) sem CPF."""
    texto = f"{afirmacao}\n{trecho}"
    return (
        0 < len(trecho) <= TRECHO_MAXIMO
        and not achar_cpf("\n".join((texto, *outros)))
        and not MARCAS_DE_PESSOA.search(texto)
    )
