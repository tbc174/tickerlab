"""CPF dentro de texto livre (linha 884): achar o número que confere e tirá-lo.

O `assunto` de um documento da CVM é escrito pela empresa e, em poucas linhas, traz o CPF de uma pessoa. Esta
é a regra **única** para isso, usada na leitura do IPE (acervo e banco do app), na gravação dos eventos e na
conferência da saída do recorte para o VPS. Só conta o número cujos dois dígitos verificadores conferem
(11 dígitos iguais não valem), com ou sem pontos, hífen ou espaços, e que não faz parte de um número maior
(protocolo, CNPJ). Sem Streamlit e sem acesso a banco: tipos simples.
"""

import re
from collections.abc import Iterable

import pandas as pd

# 11 dígitos, com ponto/espaço/hífen opcionais entre os grupos 3-3-3-2, sem dígito colado dos lados
_CANDIDATO = re.compile(r"(?<!\d)\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}(?!\d)")
MARCA = "[CPF omitido]"


def _verificadores_conferem(onze: str) -> bool:
    if len(set(onze)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * (tamanho + 1 - i) for i, d in enumerate(onze[:tamanho]))
        if (soma * 10 % 11) % 10 != int(onze[tamanho]):
            return False
    return True


def _vale(achado: re.Match[str]) -> bool:
    return _verificadores_conferem(re.sub(r"\D", "", achado.group(0)))


def tem_cpf_valido(texto: object) -> bool:
    """O texto traz algum número de CPF que confere?"""
    return any(_vale(m) for m in _CANDIDATO.finditer(str(texto or "")))


def mascarar_cpf(texto: object) -> str:
    """O texto sem os números de CPF que conferem (trocados por `[CPF omitido]`); o resto fica igual."""
    return _CANDIDATO.sub(lambda m: MARCA if _vale(m) else m.group(0), str(texto or ""))


def mascarar_coluna(serie: pd.Series) -> pd.Series:
    """`mascarar_cpf` em cada texto da coluna, só onde há candidato (o IPE tem centenas de milhares de linhas)."""
    texto = serie.fillna("").astype(str)
    candidatas = texto.str.contains(_CANDIDATO)
    if not candidatas.any():
        return texto
    return texto.where(~candidatas, texto[candidatas].map(mascarar_cpf))


def quantos_com_cpf_valido(textos: Iterable[object]) -> int:
    """Quantos textos da lista trazem CPF que confere (só a contagem, nunca o valor)."""
    return sum(tem_cpf_valido(t) for t in textos)
