"""O formato da análise escrita: 8 partes, parágrafos de fato ou de leitura, frases com notas.

Cada frase leva as notas (os ids da entrada de onde ela saiu) e, quando faz uma conta nossa
("a dívida subiu 6%"), a conta declarada: operação, operandos e resultado, que a porta 1 refaz.
O mesmo formato vale para a resposta do modelo, o molde de reserva e o gabarito guardado.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any

PARTES = (
    "em_meia_pagina",
    "o_que_e",
    "quem_manda",
    "o_que_mudou",
    "o_que_os_numeros_mostram",
    "dinheiro",
    "o_que_mudaria",
    "limites",
)
TITULOS = {
    "em_meia_pagina": "Em meia página",
    "o_que_e": "O que a empresa é e como ganha dinheiro",
    "quem_manda": "Quem manda",
    "o_que_mudou": "O que mudou",
    "o_que_os_numeros_mostram": "O que os números mostram",
    "dinheiro": "O dinheiro que sai e o que entra",
    "o_que_mudaria": "O que mudaria esta leitura",
    "limites": "Limites e perguntas em aberto",
}
FATO, LEITURA = "fato", "leitura"
TIPOS = (FATO, LEITURA)
OPERACOES = ("soma", "diferenca", "produto", "razao", "variacao", "contagem")
ORIGEM_MODELO, ORIGEM_MOLDE = "modelo", "molde"
CAMPOS_DO_OPERANDO = ("id", "valor", "conta")


class RespostaInvalidaError(ValueError):
    """A resposta não está no formato da análise (vira molde inteiro; fica na linhagem)."""


@dataclass(frozen=True)
class Operando:
    """Um número da conta: um id da entrada, uma constante (100, para %) ou uma conta anterior."""

    id: str | None = None
    valor: float | None = None
    conta: int | None = None  # posição de uma conta anterior da mesma frase


@dataclass(frozen=True)
class Conta:
    operacao: str
    de: tuple[Operando, ...]
    resultado: float


@dataclass(frozen=True)
class Frase:
    texto: str
    notas: tuple[str, ...] = ()
    contas: tuple[Conta, ...] = ()


@dataclass(frozen=True)
class Paragrafo:
    tipo: str  # fato (o que os dados dizem) ou leitura (o que a gente lê neles)
    frases: tuple[Frase, ...]


@dataclass(frozen=True)
class Parte:
    chave: str
    paragrafos: tuple[Paragrafo, ...]
    origem: str = ORIGEM_MODELO


@dataclass(frozen=True)
class Analise:
    partes: tuple[Parte, ...]

    def parte(self, chave: str) -> Parte:
        return next(p for p in self.partes if p.chave == chave)

    def como_dict(self) -> dict[str, Any]:
        """Pronto para JSON (listas no lugar das tuplas): é o que se guarda e o que a API devolve."""
        return json.loads(json.dumps(asdict(self), ensure_ascii=False))


def _operando(dado: dict[str, Any], posicao: int) -> Operando:
    preenchidos = [c for c in CAMPOS_DO_OPERANDO if dado.get(c) is not None]
    if len(preenchidos) != 1:
        raise RespostaInvalidaError(
            f"operando precisa de um só entre id, valor e conta: {dado}"
        )
    conta = dado.get("conta")
    if conta is not None and not 0 <= int(conta) < posicao:
        raise RespostaInvalidaError(
            f"operando aponta para uma conta que não é conta anterior: {conta}"
        )
    valor = dado.get("valor")
    return Operando(
        id=dado.get("id"),
        valor=None if valor is None else float(valor),
        conta=None if conta is None else int(conta),
    )


def _conta(dado: dict[str, Any], posicao: int) -> Conta:
    if dado.get("operacao") not in OPERACOES:
        raise RespostaInvalidaError(f"operação desconhecida: {dado.get('operacao')}")
    if not dado.get("de"):
        raise RespostaInvalidaError("conta sem operandos")
    return Conta(
        operacao=dado["operacao"],
        de=tuple(_operando(o, posicao) for o in dado["de"]),
        resultado=float(dado["resultado"]),
    )


def _frase(dado: dict[str, Any]) -> Frase:
    texto = str(dado.get("texto", "")).strip()
    if not texto:
        raise RespostaInvalidaError("frase vazia")
    contas = dado.get("contas") or []
    return Frase(
        texto=texto,
        notas=tuple(str(n) for n in dado.get("notas") or []),
        contas=tuple(_conta(c, i) for i, c in enumerate(contas)),
    )


def _paragrafo(dado: dict[str, Any]) -> Paragrafo:
    if dado.get("tipo") not in TIPOS:
        raise RespostaInvalidaError(
            f"tipo de parágrafo fora de fato e leitura: {dado.get('tipo')}"
        )
    return Paragrafo(dado["tipo"], tuple(_frase(f) for f in dado.get("frases") or []))


def _parte(dado: dict[str, Any]) -> Parte:
    if dado.get("chave") not in PARTES:
        raise RespostaInvalidaError(f"parte desconhecida: {dado.get('chave')}")
    paragrafos = tuple(_paragrafo(p) for p in dado.get("paragrafos") or [])
    return Parte(dado["chave"], paragrafos, dado.get("origem", ORIGEM_MODELO))


def ler_analise(dado: dict[str, Any]) -> Analise:
    """A resposta (ou o JSON guardado) como `Analise`; `RespostaInvalidaError` se sair do formato.

    Parte faltando, repetida ou fora de ordem não é erro de formato: a porta 1 reprova a estrutura.
    """
    if not isinstance(dado, dict) or not isinstance(dado.get("partes"), list):
        raise RespostaInvalidaError("a resposta não tem a lista de partes")
    return Analise(tuple(_parte(p) for p in dado["partes"]))


def _objeto(propriedades: dict[str, Any]) -> dict[str, Any]:
    """Objeto fechado com todos os campos obrigatórios (o que a saída estruturada pede)."""
    return {
        "type": "object",
        "properties": propriedades,
        "required": list(propriedades),
        "additionalProperties": False,
    }


def _lista(itens: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": itens}


_OPERANDO = _objeto(
    {
        "id": {"type": ["string", "null"], "description": "id da linha da entrada"},
        "valor": {"type": ["number", "null"], "description": "constante (só 100)"},
        "conta": {
            "type": ["integer", "null"],
            "description": "posição de uma conta anterior",
        },
    }
)
_CONTA = _objeto(
    {
        "operacao": {"type": "string", "enum": list(OPERACOES)},
        "de": _lista(_OPERANDO),
        "resultado": {"type": "number"},
    }
)
_FRASE = _objeto(
    {
        "texto": {"type": "string"},
        "notas": _lista({"type": "string"}),
        "contas": _lista(_CONTA),
    }
)
_PARAGRAFO = _objeto(
    {"tipo": {"type": "string", "enum": list(TIPOS)}, "frases": _lista(_FRASE)}
)
_PARTE = _objeto(
    {
        "chave": {"type": "string", "enum": list(PARTES)},
        "paragrafos": _lista(_PARAGRAFO),
    }
)
ESQUEMA: dict[str, Any] = _objeto({"partes": _lista(_PARTE)})
