"""A ficha "Foi sorte?": cinco checagens "passou / não passou" e um veredito (ADR 0037, D1 e D2).

A ficha junta, em linguagem simples, a validação que o backtest já faz (`validacao.py` e
`acaso.py`); nenhuma conta nova de estatística nasce aqui. Cada checagem responde uma pergunta:

1. Funcionou fora do período usado para escolher os parâmetros?
2. Sobrevive aos custos e ao imposto (rende mais que o CDI)?
3. Bate o acaso, contando as tentativas da pessoa?
4. Funciona com parâmetros vizinhos?
5. As quedas cabem no que a pessoa aguenta?

Os limites de cada checagem são constantes deste módulo, escritos antes de qualquer resultado
(o espírito da ADR 0006) e publicados na metodologia.
"""

from dataclasses import dataclass
from enum import Enum

AVISO = "Vale para os dados do passado. Não é promessa de resultado nem recomendação."


class Situacao(Enum):
    PASSOU = "passou"
    NAO_PASSOU = "não passou"
    NAO_SE_APLICA = "não se aplica"  # não havia o que conferir (ex.: nada foi ajustado)
    SEM_MEDIDA = "não deu para medir"  # faltaram dados ou operações


class Resultado(Enum):
    PASSOU = "passou"
    NAO_PASSOU = "não passou"
    INCONCLUSIVO = "inconclusivo"


@dataclass(frozen=True)
class Checagem:
    pergunta: str
    situacao: Situacao
    explicacao: str  # uma frase em português, com os números que decidiram


@dataclass(frozen=True)
class Veredito:
    resultado: Resultado
    titulo: str
    texto: str  # sempre termina com o AVISO


@dataclass(frozen=True)
class Ficha:
    checagens: tuple[Checagem, ...]
    tentativas: int  # quantas variações entraram na conta da checagem 3

    @property
    def veredito(self) -> Veredito:
        """Passou só se nenhuma checagem falhou nem ficou sem medida ("não se aplica" não pesa)."""
        return montar_veredito(self.checagens)


def _perguntas(checagens: tuple[Checagem, ...], situacao: Situacao) -> str:
    return "; ".join(c.pergunta for c in checagens if c.situacao is situacao)


def montar_veredito(checagens: tuple[Checagem, ...]) -> Veredito:
    """O veredito da ficha a partir das checagens, com o texto que explica o porquê."""
    falhas = _perguntas(checagens, Situacao.NAO_PASSOU)
    if falhas:
        return Veredito(
            Resultado.NAO_PASSOU,
            "Não passou no teste contra a sorte",
            f"Não passou em: {falhas} Uma regra assim pode ter funcionado só no passado: "
            f"não coloque dinheiro nela por causa deste resultado. {AVISO}",
        )
    sem_medida = _perguntas(checagens, Situacao.SEM_MEDIDA)
    if sem_medida or not any(c.situacao is Situacao.PASSOU for c in checagens):
        return Veredito(
            Resultado.INCONCLUSIVO,
            "Inconclusivo",
            "Nenhuma checagem falhou, mas não deu para medir: "
            f"{sem_medida or 'nenhuma checagem se aplica'}. Com mais histórico ou mais "
            f"operações a ficha pode responder. {AVISO}",
        )
    return Veredito(
        Resultado.PASSOU,
        "Passou no teste contra a sorte",
        "Todas as checagens que se aplicam passaram: o resultado não parece ser só sorte. "
        f"{AVISO}",
    )
