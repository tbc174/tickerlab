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

- **ZIP dentro de ZIP remoto** (PIT do TCE-PR): o ZIP anual (1,7 GB em 2013) tem um ZIP por
  município e tema. O índice do ZIP anual dá o CRC, a posição e o tamanho de cada ZIP interno: a
  descoberta já sabe a versão (o CRC) sem baixar nada, e ler um ZIP interno custa dois pedidos de
  trecho (cabeçalho local e dados). Quem chama regrava o conteúdo (só os atributos da lista).

- **ZIP que pode faltar** (negócios do pregão da B3): 404 (feriado, dia que ainda não saiu) e
  "200 com 0 bytes" (dia que já saiu da janela) viram `SemArquivo`; o zip é conferido inteiro (CRC de
  cada arquivo, como o `unzip -t`), porque um download cortado também começa com "PK".

- **CSV do BDI da B3** (aluguel e posições em aberto): o site pede por POST (tabela e dia no corpo);
  sem pregão vem só o cabeçalho, e vira `SemArquivo`.

Os dois primeiros devolvem os cabeçalhos do arquivo de origem, então as fontes pesadas continuam
pulando o que não mudou (ETag do ZIP inteiro ou do Parquet).
"""

import codecs
import csv
import hashlib
import io
import json
import re
import shutil
import struct
import zipfile
import zlib
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from base.arquivo.coleta import (
    SHA256_DA_ORIGEM,
    Cliente,
    Obter,
    SemArquivo,
    assinatura,
)

TAMANHO_DO_TRECHO = 8 * 1024 * 1024  # cada pedido de trecho lê até 8 MB
HTTP_NAO_ENCONTRADO = 404
# O CSV do BDI abre com 1 a 2 linhas de descrição (sem ";") e traz o cabeçalho; o de empréstimos
# registrados tem dois cabeçalhos (grupos de taxa e colunas). Dia sem pregão: só os cabeçalhos
# (verificado com um download real em 18/10/2026).
LINHAS_DE_CABECALHO = {"BTBLoanBalance": 2}
# cabeçalho local de cada arquivo dentro do ZIP: 30 bytes fixos, depois o nome e o campo extra
TAMANHO_DO_CABECALHO_LOCAL = 30
ASSINATURA_DO_CABECALHO_LOCAL = b"PK\x03\x04"
SEM_JANELA_DO_ZLIB = -15  # o "deflate" cru do ZIP, sem o cabeçalho do zlib
# o maior ZIP interno do PIT tem ~8 MB: acima disto é defeito ou bomba de descompressão (o contêiner
# do arquivista tem 1 GB)
LIMITE_DO_MEMBRO = 256 * 1024**2
# caracteres de controle que o XML 1.0 não aceita (o PIT manda alguns: \x0b, \x1f)
CONTROLE_INVALIDO = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# o mesmo caractere escrito como referência numérica (`&#11;`, `&#x1F;`; o PIT manda, 2013 e 2025)
REFERENCIA_NUMERICA = re.compile(r"&#(?:([0-9]{1,7})|[xX]([0-9a-fA-F]{1,6}));")


class ArquivoRemoto(io.RawIOBase):
    """Um arquivo do servidor que se lê como arquivo local, por pedidos de trecho (Range)."""

    def __init__(self, cliente: Cliente, url: str) -> None:
        self.cliente = cliente
        self.url = url
        self.posicao = 0
        # o IIS do TCE-PR manda os nomes em minúsculas ("content-length"); o HTTP não diferencia
        cabecalhos = {k.lower(): v for k, v in cliente.cabecalhos(url).items()}
        self.tamanho = int(cabecalhos["content-length"])

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


def indice_do_zip_remoto(cliente: Cliente, url: str) -> list[zipfile.ZipInfo]:
    """O índice do ZIP remoto (nome, CRC, posição e tamanhos de cada arquivo), sem baixar os dados."""
    with _zip_remoto(cliente, url) as arquivo_zip:
        return arquivo_zip.infolist()


def ler_membro(cliente: Cliente, url: str, membro: zipfile.ZipInfo) -> bytes:
    """Os bytes de um arquivo de dentro do ZIP remoto, em dois pedidos de trecho e com o CRC conferido.

    O `zipfile` pediria trechos de 8 MB (o buffer de `_zip_remoto`) para um ZIP interno de 30 KB;
    aqui sai o cabeçalho local (que diz onde os dados começam) e os dados, nada além.
    """
    if max(membro.file_size, membro.compress_size) > LIMITE_DO_MEMBRO:
        raise zipfile.BadZipFile(f"{membro.filename}: maior que o limite de leitura")
    inicio = membro.header_offset
    cabecalho = cliente.ler_trecho(url, inicio, inicio + TAMANHO_DO_CABECALHO_LOCAL - 1)
    if not cabecalho.startswith(ASSINATURA_DO_CABECALHO_LOCAL):
        raise zipfile.BadZipFile(
            f"{membro.filename}: cabeçalho local sem a assinatura do ZIP"
        )
    tamanho_do_nome, tamanho_do_extra = struct.unpack("<HH", cabecalho[26:30])
    comeco = inicio + TAMANHO_DO_CABECALHO_LOCAL + tamanho_do_nome + tamanho_do_extra
    comprimido = (
        cliente.ler_trecho(url, comeco, comeco + membro.compress_size - 1)
        if membro.compress_size
        else b""
    )
    if membro.compress_type == zipfile.ZIP_DEFLATED:
        # nunca mais que o tamanho do índice (+1, para o excesso aparecer na conferência abaixo)
        descompressor = zlib.decompressobj(SEM_JANELA_DO_ZLIB)
        dados = descompressor.decompress(comprimido, membro.file_size + 1)
    elif membro.compress_type == zipfile.ZIP_STORED:
        dados = comprimido
    else:
        raise zipfile.BadZipFile(
            f"{membro.filename}: compressão {membro.compress_type} desconhecida"
        )
    if zlib.crc32(dados) != membro.CRC or len(dados) != membro.file_size:
        raise zipfile.BadZipFile(
            f"{membro.filename}: CRC ou tamanho diferente do índice"
        )
    return dados


def cabecalhos_do_membro(membro: zipfile.ZipInfo, dados: bytes) -> dict[str, str]:
    """A versão de um arquivo de dentro do ZIP (o CRC no lugar do ETag) e o SHA-256 dele."""
    return {
        "ETag": f'"crc32-{membro.CRC:08x}"',
        "Content-Length": str(membro.file_size),
        SHA256_DA_ORIGEM: hashlib.sha256(dados).hexdigest(),
    }


def versao_do_membro(membro: zipfile.ZipInfo) -> str:
    """A assinatura que o arquivista grava para o arquivo de dentro do ZIP, já na descoberta (pelo
    índice): igual à da última coleta, nem pede nada."""
    return assinatura(cabecalhos_do_membro(membro, b""))


def membro_regravado(
    url: str, membro: zipfile.ZipInfo, regravar: Callable[[bytes], bytes]
) -> Obter:
    """Grava em `destino` o arquivo de dentro do ZIP remoto depois de passar por `regravar` (que tira
    o que não pode ser guardado); os cabeçalhos dizem a versão e o SHA-256 do original."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        dados = ler_membro(cliente, url, membro)
        destino.write_bytes(regravar(dados))
        return cabecalhos_do_membro(membro, dados)

    return obter


def decodificar_xml(conteudo: bytes) -> str:
    """O texto de um XML em UTF-16 (começa com FF FE) ou UTF-8 (com ou sem BOM), sem os caracteres de
    controle que o XML não aceita. Decodifica primeiro e limpa depois: em UTF-16 um byte 0x0b pode ser
    metade de uma letra."""
    if conteudo.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        texto = conteudo.decode("utf-16")
    else:
        texto = conteudo.decode("utf-8-sig")
    texto = REFERENCIA_NUMERICA.sub(_referencia_valida, texto)
    return CONTROLE_INVALIDO.sub("", texto)


def _referencia_valida(achado: re.Match[str]) -> str:
    """A referência (`&#11;`, `&#x1F;`) como veio, se o caractere vale no XML; senão, nada (o PIT
    escreve alguns caracteres de controle assim, e o leitor de XML recusa o arquivo inteiro)."""
    decimal, hexadecimal = achado.groups()
    codigo = int(decimal) if decimal else int(hexadecimal, 16)
    vale = (
        codigo in (0x9, 0xA, 0xD)
        or 0x20 <= codigo <= 0xD7FF
        or 0xE000 <= codigo <= 0x10FFFF
    )
    return achado.group(0) if vale and codigo not in (0xFFFE, 0xFFFF) else ""


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


def csv_do_bdi_da_b3(url: str, tabela: str, dia: date) -> Obter:
    """Pede ao BDI da B3 o CSV de `tabela` em `dia` (POST, o mesmo pedido do botão "Informações em
    arquivo") e guarda o corpo como veio. Dia sem pregão responde só o cabeçalho, corpo vazio ou 404:
    vira `SemArquivo`; HTML no lugar do CSV (manutenção, bloqueio) é erro."""
    pedido = json.dumps(
        {"Name": tabela, "Date": dia.isoformat(), "FinalDate": dia.isoformat()}
    ).encode()

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        try:
            resposta = cliente.ler(
                url,
                metodo="POST",
                cabecalhos={"Content-Type": "application/json"},
                corpo=pedido,
            )
        except requests.HTTPError as erro:
            if (
                erro.response is not None
                and erro.response.status_code == HTTP_NAO_ENCONTRADO
            ):
                raise SemArquivo(
                    "HTTP 404 (dia sem pregão ou que ainda não saiu)"
                ) from erro
            raise
        texto = resposta.conteudo.decode("utf-8-sig", errors="replace")
        if texto.lstrip().startswith("<"):
            raise ValueError(f"{tabela} {dia}: veio HTML no lugar do CSV")
        linhas_de_tabela = sum(1 for linha in texto.splitlines() if ";" in linha)
        if linhas_de_tabela <= LINHAS_DE_CABECALHO.get(tabela, 1):
            raise SemArquivo("só o cabeçalho (dia sem pregão ou que ainda não saiu)")
        destino.write_bytes(resposta.conteudo)
        return resposta.cabecalhos

    return obter
