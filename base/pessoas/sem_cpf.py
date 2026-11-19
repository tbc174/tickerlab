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
# CPF escrito fora do padrão, que `CPF_NO_TEXTO` não pega: espaço, vírgula, barra ou travessão entre os grupos
# ("123.456.789 - 09", "123 456 789 09", "123-456-789-09"). Com a palavra CPF na frente sai sempre; sem ela,
# só se os dígitos fecham como CPF.
SEPARADOR_LARGO = r"[\s.,/\-‐-―]{0,3}"
CPF_COM_SEPARADOR_LARGO = re.compile(
    r"(?:(?P<palavra>\bCPF\W{0,3})|(?<![\d.,/*-]))"
    rf"\d{{3}}{SEPARADOR_LARGO}\d{{3}}{SEPARADOR_LARGO}\d{{3}}{SEPARADOR_LARGO}\d{{2}}(?!\d|[.,/-]\d)",
    re.IGNORECASE,
)


def _sai_se_for_cpf(achado: re.Match[str]) -> str:
    """Vazio se o trecho é um CPF (mascarado, pontuado ou 11 dígitos válidos); senão, o próprio trecho."""
    trecho = achado.group()
    digitos = re.sub(r"\D", "", trecho)
    if "*" in trecho or len(digitos) != 11 or cpf_confere(digitos):
        return ""
    return trecho


def _sai_o_cpf_largo(achado: re.Match[str]) -> str:
    """Vazio se tem a palavra CPF na frente ou se os dígitos fecham como CPF; senão, o próprio trecho."""
    digitos = re.sub(r"\D", "", achado.group())
    if achado.group("palavra") or (len(digitos) == 11 and cpf_confere(digitos)):
        return ""
    return achado.group()


def tirar_cpf[T: (str, None)](nome: T) -> T:
    """O nome sem o CPF; `None` e texto vazio passam como estão."""
    if not nome:
        return nome
    limpo = CPF_COM_SEPARADOR_LARGO.sub(
        _sai_o_cpf_largo, CPF_NO_TEXTO.sub(_sai_se_for_cpf, nome)
    )
    if limpo == nome:
        return nome
    return ESPACOS.sub(" ", limpo).strip()  # type: ignore[return-value]


def tirar_cpf_da_coluna(nomes: pd.Series) -> pd.Series:
    """`tirar_cpf` em cada texto da coluna (ausente continua ausente)."""
    return nomes.map(lambda n: tirar_cpf(n) if isinstance(n, str) else n)


# Nome de pessoa (sócio ou titular de MEI) que vai ao acervo de pessoa: o que sobra depois do CPF ainda pode
# trazer a raiz do CNPJ, um CEP, um telefone, um CPF digitado com dígito a menos ou um e-mail (achados da
# prova do acervo de 19/11/2026). Número de cinco dígitos ou mais, mesmo partido por espaço ou pontuação, e
# palavra com arroba saem; número curto ("24 HORAS", "2023") fica. Entre os dígitos vale qualquer coisa que não
# seja letra (o mesmo critério da prova, `ONZE_DIGITOS_SEPARADOS`): "*", ":", "_", "|", espaço de largura zero.
EMAIL_NO_NOME = re.compile(r"\S*@\S*")
NUMERO_NO_NOME = re.compile(r"\d(?:(?:[^\w]|_)*\d)*")
DIGITOS_DE_NUMERO_LONGO = 5


def _sai_se_for_longo(achado: re.Match[str]) -> str:
    digitos = sum(c.isdigit() for c in achado.group())
    return " " if digitos >= DIGITOS_DE_NUMERO_LONGO else achado.group()


def tirar_numero_longo_e_email(nomes: pd.Series) -> pd.Series:
    """Os nomes sem palavra com arroba e sem número de cinco dígitos ou mais (ausente vira vazio)."""
    sem_email = nomes.fillna("").astype(str).str.replace(EMAIL_NO_NOME, " ", regex=True)
    return (
        sem_email.str.replace(NUMERO_NO_NOME, _sai_se_for_longo, regex=True)
        .str.replace(ESPACOS, " ", regex=True)
        .str.strip()
    )
