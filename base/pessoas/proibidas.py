"""Colunas e conteúdos que não podem existir fora do esquema `pessoas` (ADR 0106, tarefa 6.4 da rede).

`procurar` olha uma tabela (nomes das colunas e valores); `colunas_proibidas` olha só os nomes (o dicionário).
CNPJ (14 posições, inclusive com letras) nunca é confundido com CPF; CPF mascarado passa.
"""

import re
from collections.abc import Iterable

import pandas as pd

NOME_PROIBIDO = re.compile(
    r"(^|_)(cpf|nascimento|data_nasc\w*|endereco_pessoa|partido|religiao|saude|processo_criminal"
    r"|faixa_etaria|representante\w*|telefone\w*|ddd\w*|fax|email|e_mail)($|_)",
    re.IGNORECASE,
)
# Exceções conferidas à mão: o nome parece proibido, o conteúdo não é. Cada uma com o motivo.
EXCECOES = {
    "cadastro_de_fundos.CPF_CNPJ_GESTOR": "só o CNPJ do gestor; vazio quando é pessoa física (base/fidc.py)",
}
CPF_PONTUADO = re.compile(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$")
CPF_CRU = re.compile(r"^(?!0{11}$)\d{11}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def colunas_proibidas(colunas: Iterable[str], tabela: str) -> list[str]:
    """Os nomes de coluna proibidos, já com o nome da tabela para a mensagem."""
    return [
        achado
        for c in colunas
        if NOME_PROIBIDO.search(c) and (achado := f"{tabela}.{c}") not in EXCECOES
    ]


def _valor_proibido(valor: object) -> bool:
    texto = str(valor).strip()
    return bool(CPF_PONTUADO.match(texto) or CPF_CRU.match(texto) or EMAIL.match(texto))


def procurar(tabela: pd.DataFrame, nome: str) -> list[str]:
    """Achados numa tabela: coluna proibida ou valor que parece CPF inteiro ou e-mail."""
    achados = colunas_proibidas(tabela.columns, nome)
    for coluna in tabela.columns:
        eh_texto = tabela[coluna].dtype == object or pd.api.types.is_string_dtype(
            tabela[coluna]
        )
        if eh_texto and tabela[coluna].dropna().map(_valor_proibido).any():
            achados.append(f"{nome}.{coluna}: valor parecido com CPF ou e-mail")
    return achados
