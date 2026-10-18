"""Números e datas escritos num texto em português, lidos do mesmo jeito na entrada e na resposta.

A porta 1 só aceita um número da análise se ele bate com um número da ficha, e a comparação só é
justa se os dois lados forem lidos pela mesma regra: "R$ 45,6 bilhões" e "R$ 45,6 bi" valem
45,6 mil milhões de reais; "26,4%" vale a fração 0,264; "1.152.254.440" é um número inteiro. A
tolerância vem da precisão escrita: "45,6 bilhões" aceita de 45,55 a 45,65 bilhões.
"""

import re
from dataclasses import dataclass
from datetime import date

ESCALAS = {
    "mil": 1e3,
    "milhão": 1e6,
    "milhões": 1e6,
    "mi": 1e6,
    "bilhão": 1e9,
    "bilhões": 1e9,
    "bi": 1e9,
    "trilhão": 1e12,
    "trilhões": 1e12,
    "tri": 1e12,
}
MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
_ABREVIADOS = {nome[:3]: numero for nome, numero in MESES.items()}
PRIMEIRO_ANO, ULTIMO_ANO = 1900, 2099  # um inteiro de 4 algarismos nessa faixa é um ano
_FOLGA_DO_PONTO_FLUTUANTE = 1e-9

_SINAL = r"(?P<sinal>[-−–])?"
_DATA_COMPLETA = re.compile(
    r"(?<![\d/])(?P<dia>\d{1,2})/(?P<mes>\d{1,2})/(?P<ano>\d{4})(?![\d/])"
)
_DATA_ISO = re.compile(
    r"(?<![\d-])(?P<ano>\d{4})-(?P<mes>\d{2})-(?P<dia>\d{2})(?![\d-])"
)
_MES_E_ANO = re.compile(r"(?<![\d/])(?P<mes>\d{1,2})/(?P<ano>\d{4})(?![\d/])")
_MES_ABREVIADO = re.compile(
    r"\b(?P<mes>" + "|".join(_ABREVIADOS) + r")/(?P<ano>\d{4})\b", re.IGNORECASE
)
_MES_POR_EXTENSO = re.compile(
    r"\b(?P<mes>" + "|".join(MESES) + r") de (?P<ano>\d{4})\b", re.IGNORECASE
)
_MILHARES = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?")
# "1º", "2ª": ordinal é palavra, não número da ficha
_ORDINAL = re.compile(r"\b\d+\s?[ºª°]")
# "12 meses" é o nome de um período, como "trimestre"
_PERIODO = re.compile(r"\b12 meses\b", re.IGNORECASE)
_NUMERO = re.compile(
    r"(?<![\w.,])"
    + _SINAL
    + r"(?P<real>R\$\s?)?"
    + r"(?P<numero>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
    + r"(?P<depois>\s?(?:%|×|x\b)|\s(?:"
    + "|".join(sorted(ESCALAS, key=len, reverse=True))
    + r")\b)?"
    + r"(?![\w])",
)


@dataclass(frozen=True)
class NumeroEscrito:
    valor: float  # na unidade da entrada: fração para %, reais para R$
    tolerancia: float  # meia unidade do último algarismo escrito
    trecho: str
    com_sinal: bool  # escrito com "-" na frente

    def bate_com(self, candidato: float, sem_sinal: bool = False) -> bool:
        """O número escrito é o candidato arredondado? `sem_sinal` aceita o valor absoluto."""
        folga = self.tolerancia + _FOLGA_DO_PONTO_FLUTUANTE * max(1.0, abs(candidato))
        if abs(self.valor - candidato) <= folga:
            return True
        return (
            sem_sinal
            and not self.com_sinal
            and abs(self.valor - abs(candidato)) <= folga
        )


@dataclass(frozen=True)
class DataEscrita:
    ano: int
    mes: int | None
    dia: int | None
    trecho: str

    def bate_com(self, outra: "DataEscrita") -> bool:
        """Mesma data na precisão que as duas têm ("dezembro de 2025" bate com "DFP de 2025")."""
        if self.ano != outra.ano:
            return False
        if self.mes is not None and outra.mes is not None and self.mes != outra.mes:
            return False
        return self.dia is None or outra.dia is None or self.dia == outra.dia

    def depois_de(self, corte: date) -> bool:
        """A data passa do corte? Ano ou mês sozinhos contam pelo primeiro dia."""
        return date(self.ano, self.mes or 1, self.dia or 1) > corte


def _sem_datas(texto: str) -> tuple[list[DataEscrita], str]:
    """As datas do texto e o texto com elas apagadas (para os números não lerem o dia como valor)."""
    datas: list[DataEscrita] = []

    def guardar(achado: re.Match[str], mes: int, dia: int | None) -> str:
        datas.append(DataEscrita(int(achado["ano"]), mes, dia, achado.group(0)))
        return " " * len(achado.group(0))

    for padrao in (_DATA_COMPLETA, _DATA_ISO):
        texto = padrao.sub(lambda m: guardar(m, int(m["mes"]), int(m["dia"])), texto)
    texto = _MES_ABREVIADO.sub(
        lambda m: guardar(m, _ABREVIADOS[m["mes"].lower()], None), texto
    )
    texto = _MES_POR_EXTENSO.sub(
        lambda m: guardar(m, MESES[m["mes"].lower()], None), texto
    )
    texto = _MES_E_ANO.sub(lambda m: guardar(m, int(m["mes"]), None), texto)
    return datas, texto


def _valor_e_tolerancia(numero: str) -> tuple[float, float]:
    """'45,6' → (45.6, 0.05); '1.152.254.440' → (1152254440, 0.5); '1.5' → (1.5, 0.05).

    Ponto em grupos de 3 algarismos separa milhar (português); ponto solto é a vírgula do inglês.
    """
    if _MILHARES.fullmatch(numero) or "," in numero:
        numero = numero.replace(".", "")
    numero = numero.replace(",", ".")
    decimais = len(numero.split(".")[1]) if "." in numero else 0
    return float(numero), 0.5 * 10**-decimais


def _e_ano(achado: re.Match[str]) -> bool:
    numero = achado["numero"]
    return (
        not achado["sinal"]
        and not achado["real"]
        and not (achado["depois"] or "").strip()
        and re.fullmatch(r"\d{4}", numero) is not None
        and PRIMEIRO_ANO <= int(numero) <= ULTIMO_ANO
    )


def ler(texto: str) -> tuple[list[NumeroEscrito], list[DataEscrita]]:
    """Os números (sem os anos, os ordinais e o "12 meses") e as datas (com os anos) do texto."""
    datas, resto = _sem_datas(texto)
    resto = _PERIODO.sub(" ", _ORDINAL.sub(" ", resto))
    numeros: list[NumeroEscrito] = []
    for achado in _NUMERO.finditer(resto):
        if _e_ano(achado):
            datas.append(
                DataEscrita(int(achado["numero"]), None, None, achado["numero"])
            )
            continue
        valor, tolerancia = _valor_e_tolerancia(achado["numero"])
        depois = (achado["depois"] or "").strip().lower()
        escala = 0.01 if depois == "%" else ESCALAS.get(depois, 1.0)
        sinal = -1.0 if achado["sinal"] else 1.0
        numeros.append(
            NumeroEscrito(
                sinal * valor * escala,
                tolerancia * escala,
                achado.group(0).strip(),
                bool(achado["sinal"]),
            )
        )
    return numeros, datas


def numeros(texto: str) -> list[NumeroEscrito]:
    return ler(texto)[0]


def datas(texto: str) -> list[DataEscrita]:
    return ler(texto)[1]
