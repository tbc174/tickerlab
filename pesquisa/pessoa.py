"""Pessoa física no bot de pesquisa: um lugar só para conferir se um texto tem cara de CPF.

Usado na hipótese da rodada (`agente.recusar_pessoa_fisica`) e nos links que o mapa do site devolve ao
modelo (`coletor.mapear_site`). Junta a expressão estreita do bot (`CPF`: formatado ou 11 dígitos
seguidos, mesmo que não confiram, o preço da leitura estreita da Diretoria em 26/11/2026) e o detector
largo do repositório (`achar_cpf`: mascarado, qualquer pontuação, largura total), sobre o texto como veio
e com a codificação de URL desfeita até parar de mudar.
"""

import re
from urllib.parse import unquote_plus

from src.novidades_da_pesquisa import achar_cpf

CPF = re.compile(r"(?<!\d)(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")
MAXIMO_DE_DECODIFICACOES = (
    4  # endereço dentro de endereço vem codificado mais de uma vez
)


def _leituras(texto: str) -> list[str]:
    leituras = [texto]
    for _ in range(MAXIMO_DE_DECODIFICACOES):
        decodificado = unquote_plus(leituras[-1])
        if decodificado == leituras[-1]:
            break
        leituras.append(decodificado)
    return leituras


def tem_sequencia_de_cpf(*textos: str) -> bool:
    """Algum dos textos tem cara de CPF, em qualquer das leituras."""
    return any(
        CPF.search(leitura) or achar_cpf(leitura)
        for texto in textos
        for leitura in _leituras(texto)
    )
