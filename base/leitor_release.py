"""O leitor de press-releases de resultado (vitrine, ideia 2; ADR 0090, regras da 0087).

O modelo só **copia**: devolve cada número com o trecho literal do documento. O código confere
cada par antes de aceitar (o trecho existe no texto e o número está no trecho). Nada que o modelo
escreva chega ao usuário; a tela usa só modelos de frase com os números conferidos. Este módulo
não chama a API: monta o pedido, mascara pessoas, confere a resposta e calcula o custo.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src import rotulos_ia as ri

MODELO = (
    "claude-haiku-5-5"  # quem lê (barato); o Sonnet 5.5 confere às cegas com `--modelo`
)
VERSAO_DO_GUIA = "v1"
ARQUIVO_DO_GUIA = Path(__file__).with_name(f"leitor_release_guia_{VERSAO_DO_GUIA}.md")
MAX_TOKENS_DA_RESPOSTA = 4_000
SAIDA_ESTIMADA_POR_RELEASE = (
    500  # 3 linhas e alguns ajustes, com os trechos; o piloto mede o real
)

# Haiku 5.5 (skill claude-api, 17/10/2026): US$ 0,10 entrada e 0,50 saída por milhão, até 100 mil
# tokens por pedido (um release tem ~10 mil). A fração do cache lido não consta na tabela: usa-se 0,1
# (a mais alta dos outros modelos), então a estimativa sai igual ou acima do real.
PRECO_DO_HAIKU = ri.Modelo(0.10, 0.50, 0.1, SAIDA_ESTIMADA_POR_RELEASE)

TRECHO_AUSENTE = "trecho_ausente"
NUMERO_FORA_DO_TRECHO = "numero_fora_do_trecho"
PESSOA = ri.PESSOA

Linha = Literal[
    "receita_liquida", "lucro_liquido_controladores", "resultado_operacional"
]
Unidade = Literal["unidade", "mil", "milhoes", "bilhoes"]
Periodo = Literal["trimestre", "acumulado_no_ano", "ano"]


class LinhaLida(BaseModel):
    linha: Linha
    valor: float
    unidade: Unidade
    periodo: Periodo
    trecho: str = Field(min_length=1)
    pagina: int | None = None


class Ajuste(BaseModel):
    descricao: str  # como a empresa escreveu ("EBITDA ajustado", "lucro recorrente")
    valor: float
    unidade: Unidade
    trecho: str = Field(min_length=1)


class LeituraDoRelease(BaseModel):
    linhas: list[LinhaLida] = []
    ajustes: list[Ajuste] = []


@dataclass(frozen=True)
class Descarte:
    motivo: str
    trecho: str
    valor: float


@dataclass(frozen=True)
class LeituraConferida:
    linhas: list[LinhaLida]
    ajustes: list[Ajuste]
    descartes: list[Descarte]


# --- conferência -----------------------------------------------------------------------------

# Sinal de menos ou parêntese só vale colado ao número e no começo ou depois de espaço ou "(":
# "2T24-5.891" é hífen, "-149,4" e "(5.138)" são negativos.
_NUMERO = re.compile(r"(?:(?<![^\s(])(?P<sinal>[-−–(]))?(?P<numero>\d[\d.,]*\d|\d)")


def normalizar(texto: str) -> str:
    """Espaços e quebras de linha iguais, sem diferença de maiúscula (a regra da 0069)."""
    return " ".join(unicodedata.normalize("NFKC", texto).split()).casefold()


def _numeros_do_trecho(trecho: str) -> set[float]:
    """Cada número do trecho, com o sinal, lido nos dois formatos (1.234,5 e 1,234.5): o valor
    pode estar em qualquer um, e só vale se bater exatamente com algum, sinal incluído."""
    achados: set[float] = set()
    for achado in _NUMERO.finditer(trecho):
        token = achado["numero"]
        sinal = -1.0 if achado["sinal"] else 1.0
        for texto in (
            token.replace(".", "").replace(",", "."),  # brasileiro
            token.replace(",", ""),  # americano
        ):
            try:
                achados.add(sinal * float(texto))
            except ValueError:
                continue
    return achados


def _confere(trecho: str, valor: float, texto_normalizado: str) -> str | None:
    """O motivo de descartar o par (trecho, valor), ou None se o par está certo."""
    if normalizar(trecho) not in texto_normalizado:
        return TRECHO_AUSENTE
    if not any(abs(n - valor) < 1e-9 for n in _numeros_do_trecho(trecho)):
        return NUMERO_FORA_DO_TRECHO
    return None


def conferir(leitura: LeituraDoRelease, texto: str) -> LeituraConferida:
    """Fica só o que o código consegue provar no texto: o trecho existe e o número está nele."""
    normalizado = normalizar(texto)
    linhas, ajustes, descartes = [], [], []
    for item in (*leitura.linhas, *leitura.ajustes):
        motivo = _confere(item.trecho, item.valor, normalizado)
        if motivo:
            descartes.append(Descarte(motivo, item.trecho, item.valor))
        elif isinstance(item, LinhaLida):
            linhas.append(item)
        else:
            ajustes.append(item)
    return LeituraConferida(linhas, ajustes, descartes)


# --- máscara de pessoas (desde o prompt v3 dos rótulos, 17/10/2026, mora em `src/rotulos_ia.py`) ---

mascarar_pessoas = ri.mascarar_pessoas


# --- pedido e custo --------------------------------------------------------------------------

_ESQUEMA_DA_LINHA = {
    "type": "object",
    "properties": {
        "linha": {"type": "string", "enum": list(Linha.__args__)},
        "valor": {"type": "number"},
        "unidade": {"type": "string", "enum": list(Unidade.__args__)},
        "periodo": {"type": "string", "enum": list(Periodo.__args__)},
        "trecho": {"type": "string"},
        "pagina": {"type": ["integer", "null"]},
    },
    "required": ["linha", "valor", "unidade", "periodo", "trecho", "pagina"],
    "additionalProperties": False,
}
_ESQUEMA_DO_AJUSTE = {
    "type": "object",
    "properties": {
        "descricao": {"type": "string"},
        "valor": {"type": "number"},
        "unidade": {"type": "string", "enum": list(Unidade.__args__)},
        "trecho": {"type": "string"},
    },
    "required": ["descricao", "valor", "unidade", "trecho"],
    "additionalProperties": False,
}
ESQUEMA_DA_RESPOSTA = {
    "type": "object",
    "properties": {
        "linhas": {"type": "array", "items": _ESQUEMA_DA_LINHA},
        "ajustes": {"type": "array", "items": _ESQUEMA_DO_AJUSTE},
    },
    "required": ["linhas", "ajustes"],
    "additionalProperties": False,
}


def guia() -> str:
    return ARQUIVO_DO_GUIA.read_text(encoding="utf-8")


def texto_do_envio(texto: str) -> str:
    """O que realmente vai para a API: o texto com as pessoas mascaradas."""
    return mascarar_pessoas(texto)


def pedido(texto: str, modelo: str = MODELO) -> dict:
    """O pedido à API (formato da Batch API): o guia fica no prefixo em cache; o release vai depois."""
    return {
        "model": modelo,
        "max_tokens": MAX_TOKENS_DA_RESPOSTA,
        "system": [
            {"type": "text", "text": guia(), "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": ESQUEMA_DA_RESPOSTA},
        },
        "messages": [{"role": "user", "content": texto_do_envio(texto)}],
    }


def chave_da_entrada(texto: str, modelo: str = MODELO) -> str:
    """SHA-256 de texto enviado + guia + modelo: a mesma entrada nunca é paga duas vezes (0087, regra 4)."""
    corpo = json.dumps(
        {"texto": texto_do_envio(texto), "guia": guia(), "modelo": modelo},
        sort_keys=True,
    )
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()


def sha256_do_documento(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def preco(modelo: str) -> ri.Modelo:
    """O preço do modelo; um nome fora da lista é erro (nunca o preço de outro)."""
    return PRECO_DO_HAIKU if modelo == MODELO else ri.modelo_conhecido(modelo)


def custo_em_dolares(
    tokens_entrada: float, tokens_saida: float, lote: bool = True, modelo: str = MODELO
) -> float:
    """O custo pelos preços do modelo; pela Batch API, a metade."""
    p = preco(modelo)
    custo = (tokens_entrada * p.entrada + tokens_saida * p.saida) / 1_000_000
    return custo * (ri.DESCONTO_DO_LOTE if lote else 1.0)
