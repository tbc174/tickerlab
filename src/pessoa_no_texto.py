"""Sinais de pessoa física num texto: CPF, e-mail e telefone (a busca que o conector e as novidades dividem).

O conector (`conector_remoto/pessoa.py`) recusa a resposta inteira que trouxer um destes sinais; as novidades
da pesquisa (`src/novidades_da_pesquisa.py`) derrubam o item, no exportador e na API, com a mesma função.
Sem Streamlit e sem acesso ao banco: texto entra, verdadeiro ou falso sai.
"""

import re
import unicodedata

# CPF formatado (nunca colado a outro dígito) e mascarado como nos dados abertos da Receita
# (***123456**) ou formatado (***.123.456-**).
CPF = re.compile(
    r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)"
    r"|\*{3}\.?\d{3}\.?\d{3}-?\*{2}"
)
# Onze dígitos soltos só contam como CPF se os dígitos verificadores batem: outro código de 11 dígitos
# (o NIRE da junta comercial, por exemplo) quase nunca bate por acaso.
ONZE_DIGITOS = re.compile(r"(?<!\d)\d{11}(?!\d)")
DIGITOS_DO_CPF = 11
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Telefone brasileiro com pontuação: (11) 91234-5678, +55 11 91234 5678, 11 3456-7890, 3456-7890. Na dúvida
# derruba (falso alarme, como um intervalo "2024-2025", só tira um item); dígitos soltos sem pontuação não.
TELEFONE = re.compile(
    r"(?<!\d)(?:\+\s?55[\s.-]?)?\(\d{2}\)\s?9?\d{4}[\s.-]?\d{4}(?!\d)"
    r"|(?<!\d)\+\s?55[\s.-]?\d{2}[\s.-]?9?\d{4}[\s.-]?\d{4}(?!\d)"
    r"|(?<!\d)(?!(?:19|20)\d{2}[\s.-](?:19|20)\d{2}(?!\d))(?:\d{2}[\s.-])?9?\d{4}[\s.-]\d{4}(?!\d)"
)


def cpf_valido(digitos: str) -> bool:
    """Os onze dígitos formam um CPF com os dois verificadores certos (e não são todos iguais)."""
    if len(digitos) != DIGITOS_DO_CPF or len(set(digitos)) == 1:
        return False
    numeros = [int(d) for d in digitos]
    for posicao in (9, 10):
        soma = sum(n * (posicao + 1 - i) for i, n in enumerate(numeros[:posicao]))
        if (soma * 10) % 11 % 10 != numeros[posicao]:
            return False
    return True


def texto_de_pessoa(texto: str) -> bool:
    """O texto traz um CPF (formatado, só com dígitos ou mascarado) ou um e-mail."""
    return bool(
        CPF.search(texto)
        or EMAIL.search(texto)
        or any(cpf_valido(m) for m in ONZE_DIGITOS.findall(texto))
    )


def telefone_no_texto(texto: str) -> bool:
    """O texto traz algo com cara de telefone (texto em NFKC: largura total e espaço não separável contam)."""
    return bool(TELEFONE.search(unicodedata.normalize("NFKC", texto)))
