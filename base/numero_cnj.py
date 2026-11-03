"""O número único do processo judicial (Resolução CNJ 65/2008): `NNNNNNN-DD.AAAA.J.TR.OOOO`.

O próprio número já diz muito sem consultar nada: o ano em que o processo começou (`AAAA`), o segmento
da Justiça (`J`), o tribunal (`TR`) e a vara ou foro de origem (`OOOO`). O dígito verificador (`DD`) é
o módulo 97 da norma ISO 7064: número com dígito errado não é um número de processo (erro de digitação
ou de leitura) e não entra na base.
"""

import re
from dataclasses import dataclass

TAMANHO = 20  # só os algarismos
MODULO = 97
_FORA_DOS_ALGARISMOS = re.compile(r"\D")

# o `J` do número (art. 1º, § 4º, da Resolução CNJ 65/2008)
SEGMENTOS = {
    "1": "Supremo Tribunal Federal",
    "2": "Conselho Nacional de Justiça",
    "3": "Superior Tribunal de Justiça",
    "4": "Justiça Federal",
    "5": "Justiça do Trabalho",
    "6": "Justiça Eleitoral",
    "7": "Justiça Militar da União",
    "8": "Justiça Estadual",
    "9": "Justiça Militar Estadual",
}
JUSTICA_DO_TRABALHO = "5"


class NumeroInvalido(ValueError):
    """O texto não é um número de processo CNJ (tamanho, segmento ou dígito verificador)."""


@dataclass(frozen=True)
class NumeroCnj:
    sequencial: str  # NNNNNNN
    digito: str  # DD
    ano: int  # AAAA: o ano em que o processo foi ajuizado
    segmento: str  # J
    tribunal: str  # TR
    origem: str  # OOOO

    @property
    def algarismos(self) -> str:
        return f"{self.sequencial}{self.digito}{self.ano:04d}{self.segmento}{self.tribunal}{self.origem}"

    @property
    def formatado(self) -> str:
        return (
            f"{self.sequencial}-{self.digito}.{self.ano:04d}.{self.segmento}."
            f"{self.tribunal}.{self.origem}"
        )

    @property
    def nome_do_segmento(self) -> str:
        return SEGMENTOS[self.segmento]


def digito_esperado(
    sequencial: str, ano: str, segmento: str, tribunal: str, origem: str
) -> str:
    """Os dois dígitos verificadores: 98 menos o resto, por 97, do número com "00" no fim."""
    resto = int(f"{sequencial}{ano}{segmento}{tribunal}{origem}00") % MODULO
    return f"{98 - resto:02d}"


def decodificar(numero: str) -> NumeroCnj:
    """O número (com ou sem máscara) separado nas partes; `NumeroInvalido` se não confere."""
    algarismos = _FORA_DOS_ALGARISMOS.sub("", numero or "")
    if len(algarismos) != TAMANHO:
        raise NumeroInvalido(
            f"o número do processo tem {len(algarismos)} algarismos, e não {TAMANHO}"
        )
    sequencial, digito = algarismos[:7], algarismos[7:9]
    ano, segmento, tribunal, origem = (
        algarismos[9:13],
        algarismos[13],
        algarismos[14:16],
        algarismos[16:],
    )
    if segmento not in SEGMENTOS:
        raise NumeroInvalido(f"segmento da Justiça {segmento!r} não existe")
    if digito != digito_esperado(sequencial, ano, segmento, tribunal, origem):
        raise NumeroInvalido("o dígito verificador não confere")
    return NumeroCnj(sequencial, digito, int(ano), segmento, tribunal, origem)


def confere(numero: str) -> bool:
    try:
        decodificar(numero)
    except NumeroInvalido:
        return False
    return True
