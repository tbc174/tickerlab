"""O que vale para uma novidade da pesquisa (linha 830), dos dois lados: o exportador no PC e a API no servidor.

Uma novidade é uma fonte que o bot conferente provou (trecho literal e sha256 do original). Aqui ficam as regras
que decidem se ela pode sair: só órgão público da tabela `ORGAOS`, citação curta e nenhuma marca de pessoa
física. Sem Streamlit e sem acesso ao banco: tipos simples.
"""

import re
from urllib.parse import urlsplit

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
ONZE_DIGITOS = re.compile(r"(?<![\d.\-/])\d{11}(?![\d.\-/])")
SEPARADOR_ENTRE_DIGITOS = re.compile(
    r"(?<=\d)[ .\-](?=\d)"
)  # "529 982 247 25", "529.982.24725"
MARCAS_DE_PESSOA = re.compile(
    r"\b(?:cpf|rg|sr\.|sra\.|dr\.|dra\.|nascid[oa]|filiação)(?!\w)", re.IGNORECASE
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
    """Formato de CPF, ou 11 dígitos (também com espaço ou ponto no meio) com os dígitos verificadores certos."""
    if CPF_FORMATADO.search(texto):
        return True
    colado = SEPARADOR_ENTRE_DIGITOS.sub(
        "", texto
    )  # na dúvida, para (falso alarme é aceitável)
    return any(
        _cpf_valido(achado)
        for variante in (texto, colado)
        for achado in ONZE_DIGITOS.findall(variante)
    )


def orgao_da_url(url: str) -> tuple[str, str] | None:
    """(fonte, órgão) do endereço, se o domínio é de um órgão da tabela; senão None."""
    return ORGAOS.get((urlsplit(url).hostname or "").lower())


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


def texto_publicavel(afirmacao: str, trecho: str) -> bool:
    """Citação curta e sem CPF nem marca de pessoa física."""
    texto = f"{afirmacao}\n{trecho}"
    return (
        0 < len(trecho) <= TRECHO_MAXIMO
        and not achar_cpf(texto)
        and not MARCAS_DE_PESSOA.search(texto)
    )
