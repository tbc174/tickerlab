"""Pseudônimo da pessoa: HMAC-SHA256 do CPF mascarado, do primeiro e do último nome (ADR 0106).

A Receita só publica o CPF com os 6 dígitos do meio (`***982247**`); sozinhos eles repetem entre milhares
de pessoas, então entram junto com o primeiro e o último nome. A chave fica no servidor (nunca no Git); sem
chave nada roda, e girar a chave troca todos os ids.
"""

import hashlib
import hmac
import os
import re
import unicodedata
from pathlib import Path

VARIAVEL_DA_CHAVE = "TICKERLAB_PESSOAS_CHAVE"  # caminho do arquivo da chave
CAMINHO_PADRAO = Path("/etc/tickerlab/pessoas.chave")
TAMANHO_MINIMO_DA_CHAVE = 32
TAMANHO_DO_ID = 32
SUFIXOS_DO_NOME = {"JR", "JUNIOR", "FILHO", "NETO", "SOBRINHO"}
MASCARADO = re.compile(r"^\*{3}(\d{6})\*{2}$")
DIGITOS_DO_CPF = 11
MEIO_DO_CPF = slice(3, 9)


class ErroSemChave(RuntimeError):
    """A chave do pseudônimo não existe ou é curta demais: nada de pessoa roda sem ela."""


def mascarar_cpf(cpf: str) -> str:
    """O CPF como a Receita o publica: `***982247**`. Aceita inteiro, pontuado ou já mascarado."""
    texto = cpf.strip()
    if MASCARADO.match(texto):
        return texto
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) != DIGITOS_DO_CPF:
        raise ValueError("CPF com tamanho inesperado")
    return f"***{digitos[MEIO_DO_CPF]}**"


def normalizar_nome(nome: str) -> str:
    """Maiúsculas, sem acento nem pontuação, sem sufixo (JUNIOR, FILHO...): a única regra do projeto."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    palavras = re.sub(r"[^A-Za-z]+", " ", sem_acento).upper().split()
    return " ".join(p for p in palavras if p not in SUFIXOS_DO_NOME)


def primeiro_e_ultimo(nome: str) -> tuple[str, str]:
    """(primeiro, último) do nome normalizado; nome de uma palavra só repete a palavra."""
    partes = normalizar_nome(nome).split()
    if not partes:
        raise ValueError("nome vazio")
    return partes[0], partes[-1]


def id_pessoa(cpf: str, primeiro: str, ultimo: str, chave: bytes) -> str:
    """O pseudônimo (32 hex): igual para o CPF inteiro e para o mascarado, diferente a cada chave."""
    meio = mascarar_cpf(cpf)[3:9]
    mensagem = "|".join((meio, normalizar_nome(primeiro), normalizar_nome(ultimo)))
    return hmac.new(chave, mensagem.encode(), hashlib.sha256).hexdigest()[
        :TAMANHO_DO_ID
    ]


def ler_chave(caminho: Path | None = None) -> bytes:
    """A chave do arquivo (`TICKERLAB_PESSOAS_CHAVE` ou o caminho padrão); recusa sumida ou curta."""
    destino = caminho or Path(os.environ.get(VARIAVEL_DA_CHAVE, CAMINHO_PADRAO))
    try:
        conteudo = destino.read_bytes().strip()
    except OSError as erro:
        raise ErroSemChave("chave de pessoas ausente") from erro
    if len(conteudo) < TAMANHO_MINIMO_DA_CHAVE:
        raise ErroSemChave("chave de pessoas curta demais")
    return conteudo
