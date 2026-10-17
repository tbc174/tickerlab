"""Formas especiais de obter um arquivo, quando "baixar inteiro e guardar como veio" não serve.

- **ZIP remoto por partes** (Anatel): o ZIP dos acessos de telefonia móvel tem 3,2 GB, mas o que
  interessa são CSVs de 1 a 18 MB lá dentro. O servidor aceita pedidos de trecho (HTTP Range): o
  `zipfile` lê o índice do fim do ZIP e depois só os bytes de cada CSV escolhido, sem baixar o resto
  nem pôr o ZIP na memória. O que vai para o acervo é o CSV como está dentro do ZIP.
- **Parquet sem colunas pessoais** (SAMP da ANEEL): o arquivo traz o CPF e o nome de quem compra
  energia (consumidor pessoa física). Pela LGPD (só pessoa jurídica), as duas colunas saem **antes**
  de guardar; o acervo fica com o arquivo da ANEEL menos essas colunas (e o registro diz isso).

- **CSV e JSON só com as colunas da lista** (cadastros da ANS e da SUSEP): o cadastro das operadoras
  traz o nome do representante, e-mail e telefone. Guarda-se só o que a lista permite (a lista diz o
  que entra; uma coluna nova da fonte fica de fora até alguém pôr na lista).

- **ZIP que pode faltar** (negócios do pregão da B3): 404 (feriado, dia que ainda não saiu) e
  "200 com 0 bytes" (dia que já saiu da janela) viram `SemArquivo`; o zip é conferido inteiro (CRC de
  cada arquivo, como o `unzip -t`), porque um download cortado também começa com "PK".

Os dois primeiros devolvem os cabeçalhos do arquivo de origem, então as fontes pesadas continuam
pulando o que não mudou (ETag do ZIP inteiro ou do Parquet).
"""

import csv
import io
import json
import shutil
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import requests

from base.arquivo.coleta import Cliente, Obter, SemArquivo

TAMANHO_DO_TRECHO = 8 * 1024 * 1024  # cada pedido de trecho lê até 8 MB
HTTP_NAO_ENCONTRADO = 404


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


def csv_so_com_colunas(url: str, colunas: tuple[str, ...], codificacao: str) -> Obter:
    """Baixa o CSV (";") e grava em `destino` só as `colunas` da lista, na ordem da fonte."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            with bruto.open(encoding=codificacao, newline="") as entrada:
                leitor = csv.DictReader(entrada, delimiter=";")
                campos = [c for c in (leitor.fieldnames or []) if c in colunas]
                if not campos:
                    raise ValueError(f"{url}: nenhuma das colunas pedidas no cabeçalho")
                with destino.open("w", encoding=codificacao, newline="") as saida:
                    escritor = csv.DictWriter(
                        saida, campos, delimiter=";", extrasaction="ignore",
                        quoting=csv.QUOTE_MINIMAL,
                    )  # fmt: skip
                    escritor.writeheader()
                    escritor.writerows(leitor)
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return obter


def json_so_com_campos(url: str, campos: tuple[str, ...]) -> Obter:
    """Baixa o JSON do OData (`{"value": [...]}`) e grava só os `campos` da lista de cada item."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            itens = json.loads(bruto.read_bytes())["value"]
        finally:
            bruto.unlink(missing_ok=True)
        filtrados = [{c: item.get(c) for c in campos} for item in itens]
        destino.write_text(
            json.dumps({"value": filtrados}, ensure_ascii=False), encoding="utf-8"
        )
        return cabecalhos

    return obter


def zip_que_pode_faltar(url: str) -> Obter:
    """Baixa o zip; 404, resposta vazia e zip vazio viram `SemArquivo`; zip quebrado ou cortado é erro."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        try:
            cabecalhos = cliente.baixar(url, destino)
        except requests.HTTPError as erro:
            resposta = erro.response
            if resposta is not None and resposta.status_code == HTTP_NAO_ENCONTRADO:
                raise SemArquivo(
                    "HTTP 404 (feriado ou dia que ainda não saiu)"
                ) from erro
            raise
        if destino.stat().st_size == 0:
            raise SemArquivo("HTTP 200 com 0 bytes (dia fora da janela)")
        with zipfile.ZipFile(destino) as arquivo_zip:
            if not arquivo_zip.infolist():
                # o boletim PR de feriado vem assim (22 bytes; 12/10/2026)
                raise SemArquivo("zip vazio (dia sem pregão)")
            estragado = arquivo_zip.testzip()
        if estragado is not None:
            raise zipfile.BadZipFile(f"{estragado} com CRC errado dentro do zip")
        return cabecalhos

    return obter
