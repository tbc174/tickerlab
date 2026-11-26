"""Pessoa física no bot de pesquisa: uma expressão de CPF só, para todos os lugares que a conferem.

Usada na hipótese da rodada (`agente.recusar_pessoa_fisica`) e nos links que o mapa do site devolve ao
modelo (`coletor.mapear_site`). Pega também 11 dígitos seguidos que não são CPF: é o preço da leitura
estreita (Diretoria, 26/11/2026), e quem a usa deixa a conta à vista.
"""

import re
from urllib.parse import unquote_plus

CPF = re.compile(r"(?<!\d)(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")


def tem_sequencia_de_cpf(*textos: str) -> bool:
    """Algum dos textos tem cara de CPF, como veio ou com a codificação de URL desfeita."""
    return any(
        CPF.search(leitura)
        for texto in textos
        for leitura in (texto, unquote_plus(texto))
    )
