"""Resumo da falha de uma tarefa, sem texto livre (painel das coletas, decisão D3 do plano).

O resumo sai do servidor e vai para um repositório que um agente na nuvem lê para consertar a coleta.
O log pode trazer trecho de página de fonte (texto de terceiros, até com instrução para a IA), chave
ou e-mail, então nada dele passa adiante: o resumo só tem o **tipo** da falha, de uma lista fechada,
o nome da exceção e o host da fonte, cada um conferido por expressão regular. Quem classifica é este
código, sem IA; o agente vê o erro de verdade rodando o coletor de novo.
"""

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Final, Literal, get_args

from src.agenda_das_tarefas import NOME_VALIDO

TipoDeFalha = Literal[
    "http_403",
    "http_404",
    "http_5xx",
    "tempo_esgotado",
    "resposta_nao_json",
    "coluna_ou_campo_sumiu",
    "memoria",
    "disco",
    "trava",
    "sem_original_no_acervo",
    "conferencia_falhou",
    "atrasada",
    "outro",
]
TIPOS_DE_FALHA: Final = frozenset(get_args(TipoDeFalha))
Conferencia = Callable[[object], bool]

# códigos de saída que já dizem o tipo: 137 é o processo morto pelo kernel (falta de memória) e 75 é a
# saída do rodar-tarefa.sh quando a trava do deploy não soltou em 15 min
SAIDA_DE_MEMORIA = 137
SAIDA_DA_TRAVA = 75
MAIOR_CODIGO_DE_SAIDA = 255

# a ordem conta quando uma linha casa com mais de um padrão: o mais específico vem antes
PADROES_POR_TIPO: Final[tuple[tuple[TipoDeFalha, re.Pattern[str]], ...]] = (
    (
        "disco",
        re.compile(r"No space left on device|Errno 28|disco cheio", re.IGNORECASE),
    ),
    ("memoria", re.compile(r"\bMemoryError\b|Out of memory|OOMKilled")),
    ("trava", re.compile(r"saída trava")),
    (
        "http_403",
        re.compile(
            r"\b403\b.{0,40}(Forbidden|Client Error)|HTTP Error 403|status(_code)?[ =:]+403"
        ),
    ),
    (
        "http_404",
        re.compile(
            r"\b404\b.{0,40}(Not Found|Client Error)|HTTP Error 404|status(_code)?[ =:]+404"
        ),
    ),
    (
        "http_5xx",
        re.compile(
            r"\b5\d\d\b.{0,40}(Server Error|Bad Gateway|Service Unavailable|Gateway Time-?out)"
            r"|HTTP Error 5\d\d|status(_code)?[ =:]+5\d\d"
        ),
    ),
    (
        "tempo_esgotado",
        re.compile(
            r"ReadTimeout|ConnectTimeout|TimeoutError|timed out|tempo esgotado",
            re.IGNORECASE,
        ),
    ),
    (
        "resposta_nao_json",
        re.compile(r"JSONDecodeError|Expecting value|n[aã]o (respondeu|é) JSON"),
    ),
    (
        "coluna_ou_campo_sumiu",
        re.compile(
            r"\bKeyError\b|(coluna|campo) .{0,40}(sumiu|n[aã]o existe|ausente)",
            re.IGNORECASE,
        ),
    ),
    (
        "sem_original_no_acervo",
        re.compile(r"nenhum original da fonte|sem original no acervo"),
    ),
    ("conferencia_falhou", re.compile(r"\bC\d{1,2}: |confer[eê]ncia falhou")),
)

# o nome da exceção: um identificador curto terminado como as exceções do Python
EXCECAO_NO_LOG = re.compile(
    r"\b([A-Z][A-Za-z0-9]{0,62}(?:Error|Exception|Timeout|Interrupt|Exit))\b"
)
# só o host de um endereço http(s), sem usuário e senha que venham antes do "@"
HOST_NO_LOG = re.compile(r"https?://(?:[^/\s@]+@)?([A-Za-z0-9.-]+)")

SERVIDOR_VALIDO = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
EXCECAO_VALIDA = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
HOST_VALIDO = re.compile(
    r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
HORA_MAXIMA_EM_CARACTERES = 40


@dataclass(frozen=True)
class Classificacao:
    """O que se tira do log: o tipo da falha e, quando há, a exceção e o host da fonte."""

    tipo: TipoDeFalha
    excecao: str | None
    host: str | None


@dataclass(frozen=True)
class ResumoDaFalha:
    """O resumo que sai do servidor: só campos curtos e conferidos (ver `validar`)."""

    servidor: str
    tarefa: str
    hora: str
    codigo: int | None
    tipo: TipoDeFalha
    excecao: str | None
    host: str | None

    @classmethod
    def montar(
        cls,
        servidor: str,
        tarefa: str,
        hora: str,
        codigo: int | None,
        classificacao: Classificacao,
    ) -> "ResumoDaFalha":
        """Junta a tarefa e a classificação num resumo e o confere; recusa (ValueError) o que não passa."""
        return validar(
            {"servidor": servidor, "tarefa": tarefa, "hora": hora, "codigo": codigo}
            | asdict(classificacao)
        )

    def como_dicionario(self) -> dict[str, str | int | None]:
        """Devolve o resumo em tipos simples, pronto para virar JSON."""
        return asdict(self)


def classificar(cauda: str, codigo_de_saida: int) -> Classificacao:
    """Devolve o tipo da falha, a exceção e o host a partir da cauda do log e do código de saída.

    Vale o erro mais recente: a cauda é lida de baixo para cima, porque o log acumula as rodadas.
    """
    excecoes = EXCECAO_NO_LOG.findall(cauda)
    hosts = [
        h.lower() for h in HOST_NO_LOG.findall(cauda) if HOST_VALIDO.match(h.lower())
    ]
    return Classificacao(
        _tipo(cauda, codigo_de_saida),
        excecoes[-1] if excecoes else None,
        hosts[-1] if hosts else None,
    )


def validar(resumo: dict[str, object]) -> ResumoDaFalha:
    """Confere cada campo de um resumo (vindo do vigia ou lido do repositório) e devolve o resumo.

    Recusa com ValueError campo a mais ou faltando, tipo fora da lista e texto fora do padrão.
    """
    campos = set(ResumoDaFalha.__dataclass_fields__)
    if set(resumo) != campos:
        raise ValueError("resumo da falha com campos diferentes dos esperados")
    problemas = [
        nome for nome, confere in _CONFERENCIAS.items() if not confere(resumo[nome])
    ]
    if problemas:
        raise ValueError(
            f"resumo da falha com campo fora do padrão: {', '.join(sorted(problemas))}"
        )
    return ResumoDaFalha(**resumo)  # pyright: ignore[reportArgumentType]  # conferido acima


def _tipo(cauda: str, codigo_de_saida: int) -> TipoDeFalha:
    if codigo_de_saida == SAIDA_DE_MEMORIA:
        return "memoria"
    if codigo_de_saida == SAIDA_DA_TRAVA:
        return "trava"
    for linha in reversed(cauda.splitlines()):
        for tipo, padrao in PADROES_POR_TIPO:
            if padrao.search(linha):
                return tipo
    return "outro"


def _texto_que_casa(padrao: re.Pattern[str]) -> Conferencia:
    return lambda valor: isinstance(valor, str) and bool(padrao.match(valor))


def _opcional(conferir: Conferencia) -> Conferencia:
    return lambda valor: valor is None or conferir(valor)


def _hora_com_fuso(valor: object) -> bool:
    if not isinstance(valor, str) or len(valor) > HORA_MAXIMA_EM_CARACTERES:
        return False
    try:
        return datetime.fromisoformat(valor).tzinfo is not None
    except ValueError:
        return False


def _codigo(valor: object) -> bool:
    if valor is None:
        return True
    return type(valor) is int and 0 <= valor <= MAIOR_CODIGO_DE_SAIDA


_CONFERENCIAS = {
    "servidor": _texto_que_casa(SERVIDOR_VALIDO),
    "tarefa": _texto_que_casa(NOME_VALIDO),
    "hora": _hora_com_fuso,
    "codigo": _codigo,
    "tipo": lambda valor: valor in TIPOS_DE_FALHA,
    "excecao": _opcional(_texto_que_casa(EXCECAO_VALIDA)),
    "host": _opcional(_texto_que_casa(HOST_VALIDO)),
}
