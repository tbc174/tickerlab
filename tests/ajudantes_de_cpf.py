"""CPF de teste montado na hora (linhas 885 e 886 da fila; LGPD, repositório público).

Nenhum arquivo do repositório guarda um CPF que confere: `tests/test_exemplos_sem_cpf.py` cobra. O teste que
precisa de um (máscara, detector de CPF no texto, trava de pessoa física) monta o número aqui, a partir de nove
dígitos claramente inventados (começam com 888), e escreve-o na forma que quiser com `no_formato`.
"""

from __future__ import annotations

import re

from base.cnpj import cpf_confere, dv_confere

FINAIS_POSSIVEIS = 100


def cpf_que_confere(nove_digitos: str) -> str:
    """Os 11 dígitos de um CPF que confere, com os nove primeiros dados."""
    for final in range(FINAIS_POSSIVEIS):
        candidato = f"{nove_digitos}{final:02d}"
        if cpf_confere(candidato):
            return candidato
    raise ValueError("nenhum dígito verificador confere")  # pragma: no cover


def no_formato(cpf: str, molde: str) -> str:
    """Escreve os dígitos no molde: cada "d" recebe um dígito, na ordem ("ddd.ddd.ddd-dd", "ddd ddd ddd dd")."""
    digitos = iter(cpf)
    return re.sub("d", lambda _: next(digitos), molde)


def formatado(cpf: str) -> str:
    """O CPF na forma 999.999.999-99."""
    return no_formato(cpf, "ddd.ddd.ddd-dd")


def meio(cpf: str) -> str:
    """Os seis dígitos do meio, os que a Receita deixa à vista no CPF mascarado (***999999**)."""
    return cpf[3:9]


def cpf_que_tambem_passa_como_cnpj() -> str:
    """Um CPF que confere e que, com "000" na frente, também confere como CNPJ, de filial que não é 0001.

    É o caso ambíguo das bases que completam o CPF com zeros (cerca de 1 CPF em 70 passa no dígito do CNPJ).
    """
    # com os dois primeiros dígitos zero, os pesos do CNPJ e do CPF dão os mesmos dígitos verificadores
    for numero in range(8_880_100, 8_890_000):
        cpf = cpf_que_confere(f"{numero:09d}")
        completado = "000" + cpf
        if dv_confere(completado) and completado[8:12] != "0001":
            return cpf
    raise ValueError("nenhum CPF inventado passa como CNPJ")  # pragma: no cover


CPF_DE_TESTE = cpf_que_confere("888000001")
OUTRO_CPF_DE_TESTE = cpf_que_confere("888000002")
