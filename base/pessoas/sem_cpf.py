"""Tira o CPF do nome de uma sociedade (ADR 0106, regra 3.1; RIPD R16).

A razão social do MEI e do empresário individual vem da Receita com o CPF do dono no fim
("FULANO DE TAL 12345678901"). Nenhuma saída (tela, API, exportação, PDF) pode mostrá-lo: todo caminho
que lê uma razão social passa por aqui, na leitura. O CPF sai inteiro, formatado ou mascarado; onze
dígitos que não fecham como CPF ficam (não são dado pessoal). Reaproveita o detector da carga da Receita
(`CPF_NO_TEXTO`) e a conferência dos dígitos (`cpf_confere`).
"""

import re

import pandas as pd

from base.arquivo.lote_brasil2 import CPF_NO_TEXTO
from base.cnpj import cpf_confere

ESPACOS = re.compile(r"\s{2,}")


def _sai_se_for_cpf(achado: re.Match[str]) -> str:
    """Vazio se o trecho é um CPF (mascarado, pontuado ou 11 dígitos válidos); senão, o próprio trecho."""
    trecho = achado.group()
    digitos = re.sub(r"\D", "", trecho)
    if "*" in trecho or len(digitos) != 11 or cpf_confere(digitos):
        return ""
    return trecho


def tirar_cpf[T: (str, None)](nome: T) -> T:
    """O nome sem o CPF; `None` e texto vazio passam como estão."""
    if not nome:
        return nome
    limpo = CPF_NO_TEXTO.sub(_sai_se_for_cpf, nome)
    if limpo == nome:
        return nome
    return ESPACOS.sub(" ", limpo).strip()  # type: ignore[return-value]


def tirar_cpf_da_coluna(nomes: pd.Series) -> pd.Series:
    """`tirar_cpf` em cada texto da coluna (ausente continua ausente)."""
    return nomes.map(lambda n: tirar_cpf(n) if isinstance(n, str) else n)
