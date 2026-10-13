"""Acervo do arquivo original (Radar, PR 2): cada arquivo baixado das fontes oficiais, como veio.

Fica em `<acervo>/bruto/<fonte>/<ano>/<sha256>.<ext>`, fora da imagem (no VPS, a pasta
`dados_locais/` montada no contêiner). O nome é o próprio SHA-256: o mesmo arquivo baixado de novo
não ocupa mais espaço, e qualquer cópia pode ser conferida contra o registro de coletas. Texto
(JSON, XML, CSV, HTML) é guardado em gzip (`.json.gz`; o SHA-256 é sempre o do original); zip e PDF
já vêm comprimidos. Gravação atômica: o arquivo só aparece completo.

`TICKERLAB_ACERVO` escolhe a pasta; `desligado` para de guardar (o registro de coletas continua).
"""

import gzip
import hashlib
import os
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

PASTA_RAIZ = Path(__file__).resolve().parent.parent
PASTA_PADRAO = PASTA_RAIZ / "dados_locais" / "acervo"
VARIAVEL_DA_PASTA = "TICKERLAB_ACERVO"
DESLIGADO = "desligado"
EXTENSOES_CONHECIDAS = {
    ".zip",
    ".csv",
    ".json",
    ".xml",
    ".txt",
    ".htm",
    ".html",
    ".pdf",
}
SEM_EXTENSAO = ".bin"
JA_COMPRIMIDOS = {".zip", ".pdf"}  # o resto é texto (ou desconhecido) e vai em gzip


def pasta_do_acervo() -> Path | None:
    """A pasta do acervo, ou None se a guarda do original está desligada."""
    valor = os.environ.get(VARIAVEL_DA_PASTA, "").strip()
    if valor.lower() == DESLIGADO:
        return None
    return Path(valor) if valor else PASTA_PADRAO


def extensao_da_url(url: str) -> str:
    """A extensão do arquivo pelo endereço (".zip"), ou ".bin" se não for uma das conhecidas."""
    extensao = PurePosixPath(urlparse(url).path).suffix.lower()
    return extensao if extensao in EXTENSOES_CONHECIDAS else SEM_EXTENSAO


def caminho_relativo(
    fonte: str, url: str, conteudo: bytes, quando: datetime, extensao: str | None = None
) -> str:
    """`bruto/<fonte>/<ano>/<sha256>.<ext>[.gz]`, com barras normais (vai para o registro).

    `extensao` vale mais que a do endereço (o ENET entrega XML por um endereço `.aspx`).
    """
    sha256 = hashlib.sha256(conteudo).hexdigest()
    extensao = extensao or extensao_da_url(url)
    if extensao not in JA_COMPRIMIDOS:
        extensao += ".gz"
    return f"bruto/{fonte}/{quando.year}/{sha256}{extensao}"


def ler_original(relativo: str) -> bytes | None:
    """O arquivo como veio da fonte (descomprime o `.gz`), ou None se não está no acervo."""
    pasta = pasta_do_acervo()
    if pasta is None or not (pasta / relativo).is_file():
        return None
    guardado = (pasta / relativo).read_bytes()
    return gzip.decompress(guardado) if relativo.endswith(".gz") else guardado


def guardar_original(
    fonte: str,
    url: str,
    conteudo: bytes,
    quando: datetime,
    extensao: str | None = None,
) -> str | None:
    """Guarda o arquivo como veio e devolve o caminho relativo ao acervo (None se desligado).

    Se o arquivo já está lá (mesmo SHA-256), não grava de novo.
    """
    pasta = pasta_do_acervo()
    if pasta is None:
        return None
    relativo = caminho_relativo(fonte, url, conteudo, quando, extensao)
    destino = pasta / relativo
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_name(destino.name + ".parcial")
        temporario.write_bytes(
            # mtime=0: o mesmo original dá sempre o mesmo .gz
            gzip.compress(conteudo, mtime=0) if relativo.endswith(".gz") else conteudo
        )
        os.replace(temporario, destino)
    return relativo


def confere_com_o_registro(relativo: str, sha256: str) -> bool:
    """O arquivo guardado ainda tem o SHA-256 do registro? (para o teste mensal do backup)"""
    original = ler_original(relativo)
    return original is not None and hashlib.sha256(original).hexdigest() == sha256
