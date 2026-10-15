"""CNPJ com letras (IN RFB nº 2.229/2024): normalizar, conferir o DV, raiz e formato.

Desde julho de 2026 a Receita dá CNPJ alfanumérico às inscrições novas: as **12 primeiras posições**
aceitam `0`–`9` e `A`–`Z`, os **2 DVs continuam números** e o tamanho continua 14. O DV é o mesmo
cálculo de sempre, com cada caractere valendo o código ASCII − 48 (`0` → 0, `A` → 17, `Z` → 42), então
um CNPJ só com números dá o mesmo DV de antes (FAQ da Receita, "CNPJ alfanumérico", pergunta 14, e o
documento do Serpro sobre o cálculo). Exemplo oficial: `12.ABC.345/01DE-35`.

Os leitores da base usavam `re.sub(r"\\D", "", ...)`, que apagava as letras e deixava um CNPJ errado
(ou nenhum): todos passam por `normalizar_cnpj`. A recomendação da Receita de não emitir I, O, Q e F é
regra de emissão, não de validação: aqui toda letra vale.
"""

import re

import pandas as pd

TAMANHO = 14
TAMANHO_DA_RAIZ = 8
MENOR_COM_ZEROS = (
    TAMANHO_DA_RAIZ  # só números: a raiz sozinha ganha zeros à esquerda (ISPB do Pix)
)
SEPARADORES = re.compile(r"[\s./\-]")
FORMA = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
PESOS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
VALOR_DO_ZERO = ord("0")


def normalizar_cnpj(valor: object) -> str | None:
    """Os 14 caracteres do CNPJ, maiúsculos e sem pontuação; None se não tiver a forma de um CNPJ.

    Aceita texto formatado ("12.abc.345/01de-35"), número lido como decimal ("8884213000135.0") e,
    só com números, a raiz de 8 a 13 dígitos (ganha zeros à esquerda, como o `cnpj14` de antes). Com
    letra, só os 14 completos. Não confere o DV: o dado da fonte fica como veio (`dv_confere` diz).
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    texto = SEPARADORES.sub("", str(valor).strip().removesuffix(".0")).upper()
    if texto.isdigit() and MENOR_COM_ZEROS <= len(texto) < TAMANHO:
        texto = texto.zfill(TAMANHO)
    if not FORMA.match(texto) or not texto.strip("0"):
        return None
    return texto


def completo(valor: object) -> str | None:
    """Só os 14 caracteres, sem completar com zeros: para colunas que misturam CPF e CNPJ.

    Um CPF de 11 dígitos com zeros à esquerda viraria um "CNPJ" no `normalizar_cnpj`; aqui não.
    """
    if not isinstance(valor, str):
        return None
    texto = SEPARADORES.sub("", valor.strip()).upper()
    return texto if FORMA.match(texto) and texto.strip("0") else None


def _digito(base: str, pesos: tuple[int, ...]) -> int:
    soma = sum((ord(c) - VALOR_DO_ZERO) * p for c, p in zip(base, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto  # resto 0 ou 1 vira 0


def dv_confere(cnpj: str) -> bool:
    """True se os dois dígitos verificadores conferem (com ou sem letras)."""
    if not FORMA.match(cnpj) or cnpj == cnpj[0] * TAMANHO:
        return False
    primeiro = _digito(cnpj[:12], PESOS)
    segundo = _digito(cnpj[:13], (6, *PESOS))
    return cnpj[12:] == f"{primeiro}{segundo}"


def raiz(valor: object) -> str | None:
    """Os 8 primeiros caracteres (a empresa; o resto é a filial e o DV)."""
    cnpj = normalizar_cnpj(valor)
    return cnpj[:TAMANHO_DA_RAIZ] if cnpj else None


def formatar(cnpj: str) -> str:
    """'12ABC34501DE35' -> '12.ABC.345/01DE-35'."""
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def tem_letra(cnpj: str) -> bool:
    """True se o CNPJ é alfanumérico (nunca pode ser um CPF)."""
    return any(c.isalpha() for c in cnpj)
