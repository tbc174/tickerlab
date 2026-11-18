"""A entrega dos sócios e donos (ADR 0128, Emenda 4, 18/11/2026): a única resposta com pessoa física que o
conector passa adiante, e só a da organização com a permissão `pessoa_no_conector`.

As outras ferramentas recusam a resposta inteira que trouxer um sinal de pessoa (`conector_remoto/pessoa.py`).
Esta, de propósito, traz nome de sócio e de titular; em troca, a tranca é mais estreita: só as chaves de uma
lista fechada (a mesma da API, `src/api_externa/pessoas.CHAVES_DA_RESPOSTA`; um teste confere) e nenhum texto
com CPF (formatado, mascarado ou onze dígitos que conferem), e-mail, telefone ou CEP. Qualquer falha recusa a
resposta inteira, como nas outras: a IA recebe só o aviso, e o registro diz onde, nunca o valor.

Quem decide se a organização pode é a API, no servidor, a cada pedido (o conector só esconde a ferramenta
quando o catálogo da chave não tem o conjunto). O conector não importa `src/`: os padrões ficam aqui.
"""

import re
import unicodedata
from collections.abc import Iterator

from conector_remoto.pessoa import RespostaComPessoa, texto_de_pessoa
from conector_remoto.saida import (
    TETO_DE_CARACTERES,
    RespostaGrandeDemais,
    limpar_texto,
    tamanho_em_caracteres,
)

FERRAMENTA = "socios_e_donos"
CONJUNTO = "pessoa_no_conector"
CAMINHO = "/companies/{numeros}/people"
# a lista fechada de chaves, em qualquer profundidade: CPF, nascimento, idade, endereço e contato não estão nela
CHAVES_PERMITIDAS = frozenset(
    {
        "status", "partners", "partners_total", "owners", "owners_status", "name", "role",
        "since", "source", "attribution", "snapshot_month", "limits",
    }
)  # fmt: skip
# telefone brasileiro com pontuação, como em `src/pessoa_no_texto.TELEFONE` (um teste confere os dois)
TELEFONE = re.compile(
    r"(?<!\d)(?:\+\s?55[\s.-]?)?\(\d{2}\)\s?9?\d{4}[\s.-]?\d{4}(?!\d)"
    r"|(?<!\d)\+\s?55[\s.-]?\d{2}[\s.-]?9?\d{4}[\s.-]?\d{4}(?!\d)"
    r"|(?<!\d)(?!(?:19|20)\d{2}[\s.-](?:19|20)\d{2}(?!\d))(?:\d{2}[\s.-])?9?\d{4}[\s.-]\d{4}(?!\d)"
)
# CEP com ou sem hífen, nunca colado a outro dígito
CEP = re.compile(r"(?<!\d)\d{5}-?\d{3}(?!\d)")


def _texto_proibido(texto: str) -> bool:
    normal = unicodedata.normalize("NFKC", texto)
    return texto_de_pessoa(normal) or bool(
        TELEFONE.search(normal) or CEP.search(normal)
    )


def _falhas(valor: object, caminho: str) -> Iterator[str]:
    if isinstance(valor, dict):
        for chave, filho in valor.items():
            onde = f"{caminho}.{chave}" if caminho else str(chave)
            if chave not in CHAVES_PERMITIDAS:
                yield onde
            yield from _falhas(filho, onde)
    elif isinstance(valor, list):
        for indice, filho in enumerate(valor):
            yield from _falhas(filho, f"{caminho}[{indice}]")
    elif isinstance(valor, str) and _texto_proibido(valor):
        yield caminho or "(raiz)"


def falhas_da_resposta(corpo: object) -> list[str]:
    """Onde a resposta foge da regra (chave fora da lista ou texto com CPF, e-mail, telefone ou CEP); só o
    caminho de cada falha, nunca o valor."""
    if not isinstance(corpo, dict):
        return ["(raiz)"]
    return list(_falhas(corpo, ""))


def preparar_pessoas(corpo: object) -> object:
    """A resposta pronta para a IA: limpa, na lista fechada, sem CPF nem contato e dentro do teto
    (`RespostaComPessoa` ou `RespostaGrandeDemais` se não)."""
    limpo = limpar_texto(corpo)
    falhas = falhas_da_resposta(limpo)
    if falhas:
        raise RespostaComPessoa(falhas)
    tamanho = tamanho_em_caracteres(limpo)
    if tamanho > TETO_DE_CARACTERES:
        raise RespostaGrandeDemais(tamanho)
    return limpo
