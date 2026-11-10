"""O filtro de pessoa física: a resposta que traz um sinal de pessoa é recusada inteira.

A API externa já não serve pessoa (o portão nega e os nomes de saída são uma lista fechada); este filtro
é a segunda tranca, para o dia em que um conjunto novo trouxer um campo que escapou. Ele não tenta
apagar o campo e mandar o resto: uma resposta com pessoa é um defeito, e a IA recebe só o aviso.

Olha duas coisas: o nome de cada chave, em qualquer profundidade (as palavras do portão, em português,
e as mesmas ideias em inglês, que é como a API dá nome aos campos), e o texto dos valores (CPF, inteiro
ou mascarado como a Receita publica, e e-mail). O aviso diz onde está o campo, nunca o valor.
"""

import re
from collections.abc import Iterator

# As palavras do portão (`src/portao_externo.PALAVRAS_QUE_NUNCA_SAEM`; um teste confere que nenhuma
# falta aqui) e mais as de contato e endereço, que a busca de empresas também não serve.
PALAVRAS_EM_PORTUGUES = frozenset(
    {
        "cpf", "pf", "pessoa", "socio", "socios", "administrador", "administradores", "mei",
        "empresario", "score", "rating", "pd", "insolvencia", "default",
        "fantasia", "email", "telefone", "logradouro", "endereco", "nascimento", "idade",
    }
)  # fmt: skip
# As mesmas ideias com o nome que a API externa daria (ela traduz os campos para o inglês).
PALAVRAS_EM_INGLES = frozenset(
    {
        "person", "persons", "people", "individual", "individuals", "natural", "partner",
        "partners", "shareholder", "shareholders", "administrator", "administrators", "director",
        "directors", "officer", "officers", "owner", "owners", "proprietor", "entrepreneur",
        "insolvency", "birth", "birthdate", "age", "phone", "telephone", "address", "street",
        "qsa", "ssn",
    }
)  # fmt: skip
PALAVRAS_DE_PESSOA = PALAVRAS_EM_PORTUGUES | PALAVRAS_EM_INGLES

# CPF inteiro (com ou sem pontuação, nunca colado a outro dígito) e mascarado como nos dados abertos da
# Receita (***123456**) ou formatado (***.123.456-**); e-mail de qualquer domínio.
_CPF = re.compile(
    r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)"
    r"|\*{3}\.?\d{3}\.?\d{3}-?\*{2}"
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# separa as palavras de um nome de chave: snake_case, kebab-case, camelCase e pontos
_PALAVRA = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


class RespostaComPessoa(Exception):
    """A resposta da API trazia um sinal de pessoa física; `caminhos` diz onde (sem o valor)."""

    def __init__(self, caminhos: list[str]) -> None:
        super().__init__(f"sinal de pessoa física em {len(caminhos)} lugar(es)")
        self.caminhos = caminhos


def palavras_da_chave(chave: str) -> set[str]:
    """As palavras de um nome de chave, em minúsculas: `peerMedians` e `peer_medians` dão as mesmas."""
    return {palavra.lower() for palavra in _PALAVRA.findall(chave)}


def chave_de_pessoa(chave: str) -> bool:
    """A chave tem nome de campo de pessoa (inteira ou alguma das palavras)."""
    return chave.lower() in PALAVRAS_DE_PESSOA or bool(
        palavras_da_chave(chave) & PALAVRAS_DE_PESSOA
    )


def texto_de_pessoa(texto: str) -> bool:
    """O texto traz um CPF (inteiro ou mascarado) ou um e-mail."""
    return bool(_CPF.search(texto) or _EMAIL.search(texto))


def _sinais(valor: object, caminho: str) -> Iterator[str]:
    if isinstance(valor, dict):
        for chave, filho in valor.items():
            onde = f"{caminho}.{chave}" if caminho else str(chave)
            if chave_de_pessoa(str(chave)):
                yield onde
            yield from _sinais(filho, onde)
    elif isinstance(valor, list):
        for indice, filho in enumerate(valor):
            yield from _sinais(filho, f"{caminho}[{indice}]")
    elif isinstance(valor, str) and texto_de_pessoa(valor):
        yield caminho or "(raiz)"


def sinais_de_pessoa(corpo: object) -> list[str]:
    """Onde a resposta tem sinal de pessoa física: o caminho de cada um, sem o valor."""
    return list(_sinais(corpo, ""))


def exigir_sem_pessoa(corpo: object) -> None:
    """`RespostaComPessoa` se há qualquer sinal de pessoa física na resposta."""
    caminhos = sinais_de_pessoa(corpo)
    if caminhos:
        raise RespostaComPessoa(caminhos)
