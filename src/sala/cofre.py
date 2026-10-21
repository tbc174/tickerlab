"""A cifra da sala de dados (decisão D3 do plano do B-20): AES-256-GCM, uma chave por operação.

Como funciona, em camadas:
- **Chave-mestra** (`TICKERLAB_CHAVE_DA_SALA`, só no `.env` do VPS e na pasta de segredos do
  Tiago; gerada no servidor por script, nunca pelo chat). Ela só embrulha as chaves das operações.
- **Chave da operação** (32 bytes aleatórios), guardada no banco já embrulhada. Apagar a operação
  apaga a chave: o arquivo no disco fica ilegível na hora, mesmo se a remoção do disco falhar.
- **Cada arquivo** é cifrado com a chave da operação e um nonce aleatório. Os ids da operação e
  do documento (e se é o original ou o texto) entram como dado associado: um arquivo copiado para
  outra sala, ou o texto posto no lugar do original, não abre.

A variável tem a forma `v1:<base64 de 32 bytes>`; para trocar a chave-mestra sem recifrar os
arquivos, acrescente a nova na frente (`v2:...,v1:...`): as chaves novas saem com a maior versão,
e as antigas continuam abrindo pela versão gravada em `operacoes.versao_da_chave`.
"""

import base64
import binascii
import os
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VARIAVEL_DA_CHAVE_MESTRA = "TICKERLAB_CHAVE_DA_SALA"
BYTES_DA_CHAVE = 32  # AES-256
BYTES_DO_NONCE = 12  # o tamanho que o GCM recomenda

# separa os usos da mesma chave: a chave embrulhada nunca abre como arquivo, e vice-versa
_PROPOSITO_DA_CHAVE = b"tickerlab/sala/chave-da-operacao/v1"
_PROPOSITO_DO_ARQUIVO = b"tickerlab/sala/arquivo/v1"
PARTES_DO_DOCUMENTO = ("original", "texto")


class ChaveDaSalaAusenteError(RuntimeError):
    """A chave-mestra não está configurada (ou está num formato inválido)."""


class CifraInvalidaError(ValueError):
    """O conteúdo não abre com esta chave: outra sala, outro documento ou arquivo adulterado."""


def chaves_mestras(valor: str | None = None) -> dict[int, bytes]:
    """As chaves-mestras configuradas, pela versão (`v1:<base64>,v2:<base64>`)."""
    texto = (
        os.environ.get(VARIAVEL_DA_CHAVE_MESTRA, "") if valor is None else valor
    ).strip()
    if not texto:
        raise ChaveDaSalaAusenteError(
            f"Configure {VARIAVEL_DA_CHAVE_MESTRA} no servidor."
        )
    chaves = {}
    for item in texto.split(","):
        versao, _, codificada = item.strip().partition(":")
        try:
            numero = int(versao.removeprefix("v"))
            chave = base64.b64decode(codificada, validate=True)
        except (ValueError, binascii.Error):
            raise ChaveDaSalaAusenteError(
                f"{VARIAVEL_DA_CHAVE_MESTRA} fora do formato."
            ) from None
        if len(chave) != BYTES_DA_CHAVE or numero < 1 or numero in chaves:
            raise ChaveDaSalaAusenteError(
                f"{VARIAVEL_DA_CHAVE_MESTRA} fora do formato."
            )
        chaves[numero] = chave
    return chaves


def gerar_chave_mestra() -> str:
    """Uma chave-mestra nova, no formato da variável (`v1:<base64>`), para o script do servidor."""
    return "v1:" + base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii")


def _cifrar(chave: bytes, conteudo: bytes, associado: bytes) -> bytes:
    nonce = os.urandom(BYTES_DO_NONCE)
    return nonce + AESGCM(chave).encrypt(nonce, conteudo, associado)


def _decifrar(chave: bytes, cifrado: bytes, associado: bytes) -> bytes:
    nonce, resto = cifrado[:BYTES_DO_NONCE], cifrado[BYTES_DO_NONCE:]
    try:
        return AESGCM(chave).decrypt(nonce, resto, associado)
    except (InvalidTag, ValueError):
        raise CifraInvalidaError("O conteúdo não abre com esta chave.") from None


def nova_chave_da_operacao(operacao_id: uuid.UUID) -> tuple[bytes, bytes, int]:
    """Uma chave nova para a operação: (chave, chave embrulhada pela mestra, versão da mestra)."""
    mestras = chaves_mestras()
    versao = max(mestras)
    chave = AESGCM.generate_key(bit_length=256)
    embrulhada = _cifrar(
        mestras[versao], chave, _PROPOSITO_DA_CHAVE + operacao_id.bytes
    )
    return chave, embrulhada, versao


def abrir_chave_da_operacao(
    embrulhada: bytes, versao: int, operacao_id: uuid.UUID
) -> bytes:
    """A chave da operação, desembrulhada pela chave-mestra da versão em que foi gravada."""
    mestra = chaves_mestras().get(versao)
    if mestra is None:
        raise ChaveDaSalaAusenteError(f"Falta a versão v{versao} da chave-mestra.")
    return _decifrar(mestra, embrulhada, _PROPOSITO_DA_CHAVE + operacao_id.bytes)


def _associado_do_documento(
    operacao_id: uuid.UUID, documento_id: uuid.UUID, parte: str
) -> bytes:
    if parte not in PARTES_DO_DOCUMENTO:
        raise ValueError(f"Parte do documento: {PARTES_DO_DOCUMENTO}.")
    return b"|".join(
        (_PROPOSITO_DO_ARQUIVO, operacao_id.bytes, documento_id.bytes, parte.encode())
    )


def cifrar_documento(
    chave: bytes,
    conteudo: bytes,
    *,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
    parte: str,
) -> bytes:
    """O conteúdo cifrado (nonce + cifra + etiqueta), preso à operação, ao documento e à parte."""
    associado = _associado_do_documento(operacao_id, documento_id, parte)
    return _cifrar(chave, conteudo, associado)


def decifrar_documento(
    chave: bytes,
    cifrado: bytes,
    *,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
    parte: str,
) -> bytes:
    """O conteúdo original; `CifraInvalidaError` se for de outra sala, documento ou parte."""
    associado = _associado_do_documento(operacao_id, documento_id, parte)
    return _decifrar(chave, cifrado, associado)


def nonce_de(cifrado: bytes) -> bytes:
    """O nonce usado na cifra (os primeiros bytes), para guardar no banco junto do documento."""
    return cifrado[:BYTES_DO_NONCE]
