"""Formas especiais de obter um arquivo, quando "baixar inteiro e guardar como veio" não serve.

- **ZIP remoto por partes** (Anatel): o ZIP dos acessos de telefonia móvel tem 3,2 GB, mas o que
  interessa são CSVs de 1 a 18 MB lá dentro. O servidor aceita pedidos de trecho (HTTP Range): o
  `zipfile` lê o índice do fim do ZIP e depois só os bytes de cada CSV escolhido, sem baixar o resto
  nem pôr o ZIP na memória. O que vai para o acervo é o CSV como está dentro do ZIP.
- **Parquet sem colunas pessoais** (SAMP da ANEEL): o arquivo traz o CPF e o nome de quem compra
  energia (consumidor pessoa física). Pela LGPD (só pessoa jurídica), as duas colunas saem **antes**
  de guardar; o acervo fica com o arquivo da ANEEL menos essas colunas (e o registro diz isso).

Os dois devolvem os cabeçalhos do arquivo de origem, então as fontes pesadas continuam pulando o que
não mudou (ETag do ZIP inteiro ou do Parquet).
"""

import io
import shutil
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from base.arquivo.coleta import Cliente, Obter

TAMANHO_DO_TRECHO = 8 * 1024 * 1024  # cada pedido de trecho lê até 8 MB


class ArquivoRemoto(io.RawIOBase):
    """Um arquivo do servidor que se lê como arquivo local, por pedidos de trecho (Range)."""

    def __init__(self, cliente: Cliente, url: str) -> None:
        self.cliente = cliente
        self.url = url
        self.posicao = 0
        self.tamanho = int(cliente.cabecalhos(url)["Content-Length"])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.posicao

    def seek(self, deslocamento: int, de_onde: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.posicao, io.SEEK_END: self.tamanho}
        self.posicao = base[de_onde] + deslocamento
        return self.posicao

    def readinto(self, destino) -> int:  # noqa: ANN001 (buffer do io)
        if self.posicao >= self.tamanho:
            return 0
        fim = min(self.posicao + len(destino), self.tamanho) - 1
        trecho = self.cliente.ler_trecho(self.url, self.posicao, fim)
        destino[: len(trecho)] = trecho
        self.posicao += len(trecho)
        return len(trecho)


def _zip_remoto(cliente: Cliente, url: str) -> zipfile.ZipFile:
    return zipfile.ZipFile(
        io.BufferedReader(ArquivoRemoto(cliente, url), TAMANHO_DO_TRECHO)
    )


def membros_do_zip_remoto(cliente: Cliente, url: str) -> list[str]:
    """Os nomes dos arquivos dentro do ZIP (lê só o índice, no fim do arquivo)."""
    with _zip_remoto(cliente, url) as arquivo_zip:
        return arquivo_zip.namelist()


def extrair_do_zip_remoto(url: str, membro: str) -> Obter:
    """Grava em `destino` um arquivo de dentro do ZIP remoto, sem baixar o ZIP inteiro."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        with (
            _zip_remoto(cliente, url) as arquivo_zip,
            arquivo_zip.open(membro) as entrada,
            destino.open("wb") as saida,
        ):
            shutil.copyfileobj(entrada, saida, length=1024 * 1024)
        return cliente.cabecalhos(url)

    return obter


def parquet_sem_colunas(url: str, colunas: tuple[str, ...]) -> Obter:
    """Baixa o Parquet e grava em `destino` sem as colunas pedidas (dado pessoal)."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            tabela = pd.read_parquet(bruto)
        finally:
            bruto.unlink(missing_ok=True)
        tabela.drop(columns=[c for c in colunas if c in tabela.columns]).to_parquet(
            destino, index=False
        )
        return cabecalhos

    return obter
