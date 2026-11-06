"""A chave da API externa (N7; ADR 0108, linha 117): formato, hash e o contexto que ela abre.

A chave tem o formato `tld_<prefixo>_<segredo>`. O prefixo (8 letras de base32 em minúsculas, 40 bits)
não é segredo: acha a linha no banco e aparece nas listas para o cliente saber qual chave é qual. O
segredo tem 256 bits (`secrets.token_urlsafe(32)`). O banco guarda só o SHA-256 da chave inteira: com
256 bits de acaso, o hash sem sal basta e a conferência fica rápida (não é senha escolhida por gente).

A chave só existe na volta de `gerar_chave` (e no `ChaveNova`, que não a mostra no `repr`): mostrar
uma vez para o admin e nunca mais. O contexto que ela abre é sempre o da API externa: o canal não é um
campo, então não há como montar um contexto de `api_interna` com uma chave (plano N7, D7). As consultas
ao banco ficam em `src/banco/chaves_da_api.py`.
"""

import base64
import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from src.banco.modelo import CANAL_DA_CHAVE, FINALIDADES_DA_ORGANIZACAO
from src.portao_externo import Canal, Finalidade

INICIO = "tld"
BYTES_DO_PREFIXO = 5  # 40 bits = 8 letras de base32, sem "=" no fim
BYTES_DO_SEGREDO = 32  # 256 bits = 43 caracteres de base64 para URL
TAMANHO_DO_HASH = 64  # SHA-256 em hexadecimal
TAMANHO_DA_CHAVE = len(INICIO) + 1 + 8 + 1 + 43
FORMATO = re.compile(rf"{INICIO}_([a-z2-7]{{8}})_[A-Za-z0-9_-]{{43}}")

# o banco e o portão (N3) falam da mesma API externa e das mesmas finalidades
assert Canal(CANAL_DA_CHAVE) is Canal.API_EXTERNA
assert set(FINALIDADES_DA_ORGANIZACAO) == {Finalidade.ANALISE, Finalidade.CREDITO}


class MotivoDaRecusa(StrEnum):
    """Por que a chave não entrou. Só para o log: para fora, toda recusa é o mesmo 401 (D8)."""

    FORMATO = "formato"
    DESCONHECIDA = "desconhecida"  # prefixo que não existe ou segredo que não confere
    REVOGADA = "revogada"
    VENCIDA = "vencida"  # a antiga de uma rotação, depois do prazo
    ORGANIZACAO_SUSPENSA = "organizacao_suspensa"


@dataclass(frozen=True)
class ChaveNova:
    """A chave recém-emitida: a única vez em que o valor existe fora da mão do cliente."""

    chave_id: uuid.UUID
    prefixo: str
    valor: str = field(repr=False)


@dataclass(frozen=True)
class ContextoDaChave:
    """Quem está pedindo: o que a rota recebe depois que a chave confere."""

    organizacao_id: uuid.UUID
    chave_id: uuid.UUID
    prefixo: str
    plano_da_api: str

    @property
    def canal(self) -> Canal:
        return Canal.API_EXTERNA


def gerar_chave() -> tuple[str, str]:
    """Um prefixo novo e a chave inteira que o contém."""
    prefixo = base64.b32encode(secrets.token_bytes(BYTES_DO_PREFIXO)).decode().lower()
    segredo = secrets.token_urlsafe(BYTES_DO_SEGREDO)
    return prefixo, f"{INICIO}_{prefixo}_{segredo}"


def separar(texto: str) -> str | None:
    """O prefixo, se o texto tem o formato de uma chave; senão None (sem olhar o banco)."""
    if len(texto) != TAMANHO_DA_CHAVE:
        return None
    encontrado = FORMATO.fullmatch(texto)
    return encontrado.group(1) if encontrado else None


def hash_da_chave(chave: str) -> str:
    return hashlib.sha256(chave.encode()).hexdigest()
