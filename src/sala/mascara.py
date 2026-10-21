"""Mascara o CPF no texto lido dos documentos da sala (decisão D8 do plano do B-20).

O texto extraído de um documento vai para a tela, para as evidências e (um dia) para a busca; o
CPF de sócios, sacados e devedores não precisa ir junto. Fica só o dígito verificador
(`***.***.***-12`), o bastante para a pessoa reconhecer de quem se trata conferindo o original,
que continua só no arquivo cifrado.

Só vira máscara o número que é CPF de verdade: 11 dígitos (com ou sem pontos e traço) cujo
dígito verificador confere e que não são todos iguais. Um número qualquer de 11 dígitos tem ~1%
de chance de passar na conta; nesse caso também é mascarado, porque esconder um número a mais
custa menos do que deixar um CPF à mostra. Sem `presidio`: é uma regra só, e cabe aqui.
"""

import re

DIGITOS_DO_CPF = 11
DIGITOS_SEM_O_VERIFICADOR = 9
RESTO_QUE_VIRA_ZERO = 10  # regra do CPF: quando a conta dá 10, o dígito é 0

# CPF escrito com pontos e traço (123.456.789-09) ou só os 11 dígitos (12345678909); nunca um
# pedaço de um número maior (CNPJ, conta, valor com milhar): antes e depois não pode haver dígito,
# nem ponto ou vírgula seguido de dígito
_CPF = re.compile(
    r"(?<!\d)(?<!\d[.,])"
    r"(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})"
    r"(?!\d)(?![.,]\d)"
)


def _digito_verificador(digitos: str) -> int:
    peso_inicial = len(digitos) + 1
    soma = sum(
        int(d) * peso
        for d, peso in zip(digitos, range(peso_inicial, 1, -1), strict=True)
    )
    resto = soma * 10 % DIGITOS_DO_CPF
    return 0 if resto == RESTO_QUE_VIRA_ZERO else resto


def e_cpf_valido(numero: str) -> bool:
    """Se os 11 dígitos de `numero` (pontuação é ignorada) formam um CPF com o verificador certo."""
    digitos = re.sub(r"\D", "", numero)
    if len(digitos) != DIGITOS_DO_CPF or len(set(digitos)) == 1:
        return False
    base = digitos[:DIGITOS_SEM_O_VERIFICADOR]
    primeiro = _digito_verificador(base)
    segundo = _digito_verificador(base + str(primeiro))
    return digitos[DIGITOS_SEM_O_VERIFICADOR:] == f"{primeiro}{segundo}"


def _mascarar(achado: re.Match[str]) -> str:
    numero = achado.group(0)
    if not e_cpf_valido(numero):
        return numero
    return f"***.***.***-{numero[-2:]}"


def mascarar_cpfs(texto: str) -> str:
    """O texto com cada CPF válido trocado por `***.***.***-DV` (DV = os 2 dígitos finais)."""
    return _CPF.sub(_mascarar, texto)
