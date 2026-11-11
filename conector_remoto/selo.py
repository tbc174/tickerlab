"""O selo do conector: pacotes cifrados e assinados com a chave do servidor (AES-256-GCM).

Tudo o que o OAuth do conector entrega à IA é um pacote selado: o `client_id` do registro (DCR), o pedido
de autorização que vai na URL da página `/autorizar` e os tokens de acesso e de renovação. Assim o servidor
não grava nada: reiniciar não derruba ninguém, e trocar a chave do servidor derruba todos de uma vez (é o
plano de incidente quando ela vaza).

Cada selo tem um nonce aleatório de 96 bits e leva o propósito como dado associado: um pacote selado para
um propósito (ex.: `pedido`) nunca abre como outro (ex.: `acesso`), mesmo com a mesma chave. A chave nunca
aparece em `repr`, log ou mensagem de erro.
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
from collections.abc import Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

TAMANHO_DA_CHAVE = 32  # AES-256
TAMANHO_DO_NONCE = 12  # 96 bits, o tamanho recomendado para o GCM
VERSAO = b"tickerlab-mcp/v1/"
CAMPO_DA_VALIDADE = "exp"


class ChaveInvalida(ValueError):
    """A chave do servidor não é base64url de 32 bytes (a mensagem nunca traz o valor)."""


def ler_chave(texto: str) -> bytes:
    """Os 32 bytes da chave do servidor, a partir do base64url da variável de ambiente."""
    limpo = texto.strip()
    try:
        chave = base64.urlsafe_b64decode(limpo + "=" * (-len(limpo) % 4))
    except (binascii.Error, ValueError):
        raise ChaveInvalida("a chave do servidor não é base64url") from None
    if len(chave) != TAMANHO_DA_CHAVE:
        raise ChaveInvalida(f"a chave do servidor precisa ter {TAMANHO_DA_CHAVE} bytes")
    return chave


def nova_chave() -> str:
    """Uma chave do servidor nova, em base64url (é o que vai no `.env` do contêiner)."""
    return base64.urlsafe_b64encode(os.urandom(TAMANHO_DA_CHAVE)).decode().rstrip("=")


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).decode().rstrip("=")


def _de_b64(texto: str) -> bytes | None:
    try:
        return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))
    except (binascii.Error, ValueError):
        return None


def _derivar(chave: bytes, uso: bytes) -> bytes:
    # uma subchave por uso: a mesma chave não serve ao mesmo tempo para cifrar e para assinar
    return HKDF(
        algorithm=hashes.SHA256(), length=TAMANHO_DA_CHAVE, salt=None, info=VERSAO + uso
    ).derive(chave)


class Selador:
    """Sela e abre pacotes JSON com a chave do servidor."""

    def __init__(self, chave: bytes) -> None:
        if len(chave) != TAMANHO_DA_CHAVE:
            raise ChaveInvalida(
                f"a chave do servidor precisa ter {TAMANHO_DA_CHAVE} bytes"
            )
        self._cifra = AESGCM(_derivar(chave, b"cifra"))
        self._assinatura = _derivar(chave, b"assinatura")

    def __repr__(self) -> str:
        return "Selador(<chave escondida>)"

    def selar(
        self,
        proposito: str,
        dados: Mapping[str, object],
        *,
        agora: float,
        validade_s: float | None = None,
    ) -> str:
        """O pacote selado (texto seguro para URL); com `validade_s`, ele vence em `agora + validade_s`."""
        conteudo = dict(dados)
        if validade_s is not None:
            conteudo[CAMPO_DA_VALIDADE] = int(agora + validade_s)
        nonce = os.urandom(TAMANHO_DO_NONCE)
        texto = json.dumps(conteudo, separators=(",", ":"), ensure_ascii=False)
        cifrado = self._cifra.encrypt(
            nonce, texto.encode(), VERSAO + proposito.encode()
        )
        return _b64(nonce + cifrado)

    def abrir(self, proposito: str, selado: str, *, agora: float) -> dict | None:
        """O conteúdo do pacote, ou None se ele foi mexido, é de outro propósito ou venceu."""
        bruto = _de_b64(selado) if selado.isascii() else None
        if bruto is None or len(bruto) <= TAMANHO_DO_NONCE:
            return None
        nonce, cifrado = bruto[:TAMANHO_DO_NONCE], bruto[TAMANHO_DO_NONCE:]
        try:
            texto = self._cifra.decrypt(nonce, cifrado, VERSAO + proposito.encode())
        except InvalidTag:
            return None
        conteudo = json.loads(texto)
        if not isinstance(conteudo, dict):
            return None
        validade = conteudo.get(CAMPO_DA_VALIDADE)
        if validade is not None and (
            not isinstance(validade, int) or validade <= agora
        ):
            return None
        return conteudo

    def assinar(self, proposito: str, texto: str) -> str:
        """Uma assinatura (HMAC-SHA256) de `texto` para `proposito`; serve de segredo derivado."""
        mensagem = VERSAO + proposito.encode() + b"\x00" + texto.encode()
        return hmac.new(self._assinatura, mensagem, hashlib.sha256).hexdigest()
