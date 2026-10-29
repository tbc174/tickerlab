"""Acervo do arquivo original (Radar, PR 2): cada arquivo baixado das fontes oficiais, como veio.

Fica em `<acervo>/bruto/<fonte>/<ano>/<sha256>.<ext>`, fora da imagem (no VPS, a pasta
`dados_locais/` montada no contêiner). O nome é o próprio SHA-256: o mesmo arquivo baixado de novo
não ocupa mais espaço, e qualquer cópia pode ser conferida contra o registro de coletas. Texto
(JSON, XML, CSV, HTML) é guardado em gzip (`.json.gz`; o SHA-256 é sempre o do original); zip e PDF
já vêm comprimidos. Gravação atômica: o arquivo só aparece completo.

Fonte que traz nome de pessoa natural (`FONTES_COM_PESSOA`, ADR 0106) vai para `restrito/<fonte>/...`,
pasta que nenhum pacote, exportação ou cópia pública leva (`PASTAS_PUBLICAS` é a lista do que pode sair).

`TICKERLAB_ACERVO` escolhe a pasta; `desligado` para de guardar (o registro de coletas continua).
"""

import gzip
import hashlib
import os
import shutil
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
PASTA_PUBLICA = "bruto"
PASTA_RESTRITA = "restrito"
PASTAS_PUBLICAS = (PASTA_PUBLICA,)
FONTES_COM_PESSOA = frozenset(
    {
        "rfb-cnpj",
        "pgfn-divida",
        "mte-lista-suja",
        "ibama-autos",
        "ibama-embargos",
        "cvm-enet-notas",  # o texto das notas da DFP traz nomes (administradores, auditor)
        "antt-autos-de-transito",  # o autuado pode ser pessoa física (motorista autônomo)
    }
)
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
    """`bruto/<fonte>/<ano>/<sha256>.<ext>[.gz]` (`restrito/` se a fonte traz pessoa), com barras normais.

    `extensao` vale mais que a do endereço (o ENET entrega XML por um endereço `.aspx`).
    """
    sha256 = hashlib.sha256(conteudo).hexdigest()
    return _relativo_pelo_sha(fonte, url, sha256, quando, extensao)


def _relativo_pelo_sha(
    fonte: str, url: str, sha256: str, quando: datetime, extensao: str | None
) -> str:
    extensao = extensao or extensao_da_url(url)
    if extensao not in JA_COMPRIMIDOS:
        extensao += ".gz"
    pasta = PASTA_RESTRITA if fonte in FONTES_COM_PESSOA else PASTA_PUBLICA
    return f"{pasta}/{fonte}/{quando.year}/{sha256}{extensao}"


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


def guardar_arquivo(
    fonte: str,
    url: str,
    temporario: Path,
    sha256: str,
    quando: datetime,
    extensao: str | None = None,
) -> str | None:
    """Como `guardar_original`, para um arquivo já baixado em disco (o CNPJ tem GBs): move o
    temporário para o acervo sem carregá-lo na memória. O temporário sempre some.

    `sha256` é o do arquivo como veio (calculado em partes por quem baixou).
    """
    pasta = pasta_do_acervo()
    if pasta is None:
        temporario.unlink(missing_ok=True)
        return None
    relativo = _relativo_pelo_sha(fonte, url, sha256, quando, extensao)
    destino = pasta / relativo
    if destino.exists():
        temporario.unlink(missing_ok=True)
        return relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    if relativo.endswith(".gz"):
        parcial = destino.with_name(destino.name + ".parcial")
        with (
            temporario.open("rb") as entrada,
            gzip.GzipFile(parcial, "wb", mtime=0) as saida,
        ):
            shutil.copyfileobj(entrada, saida, length=1024 * 1024)
        os.replace(parcial, destino)
        temporario.unlink()
    else:
        shutil.move(temporario, destino)
    return relativo
