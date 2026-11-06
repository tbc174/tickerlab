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

- **Ficha do conjunto no dados.gov.br** (vigia da licença do CNPJ): a rota pública da ficha responde
  401 sem a chave do portal (`chave-api-dados-abertos`, no `.env` do servidor). Guarda só o que decide a
  licença (`id`, `nome`, `titulo`, `licenca`): o JSON inteiro traz datas que mudam a cada carga (e o
  e-mail do responsável, dado de pessoa) e faria a vigia avisar à toa.

Os dois primeiros devolvem os cabeçalhos do arquivo de origem, então as fontes pesadas continuam
pulando o que não mudou (ETag do ZIP inteiro ou do Parquet).
"""

import codecs
import csv
import hashlib
import html
import io
import json
import os
import re
import shutil
import struct
import zipfile
import zlib
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import IO
from urllib.parse import urlencode

import pandas as pd
import requests

from base import cnpj as cnpjs
from base.arquivo.coleta import (
    SHA256_DA_ORIGEM,
    Cliente,
    Obter,
    SemArquivo,
    assinatura,
)

# o que a vigia da licença guarda da ficha: quem é o conjunto e qual licença ele declara
CAMPOS_DA_LICENCA_DA_FICHA = ("id", "nome", "titulo", "licenca")
CAMPO_DA_LICENCA = "licenca"
TAMANHO_DO_TRECHO = 8 * 1024 * 1024  # cada pedido de trecho lê até 8 MB
HTTP_NAO_ENCONTRADO = 404
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


TAMANHO_DO_PEDACO_DO_XML = 1024**2
# quantos caracteres atrás de um "&" ainda cabem numa referência numérica (`&#x10FFFF;` tem 10)
ALCANCE_DA_REFERENCIA = 12


class TextoDoXml:
    """O texto de um XML grande, lido em pedaços de um arquivo binário (UTF-16 com BOM ou UTF-8), com a
    mesma limpeza de `decodificar_xml`; é o `read` que o `iterparse` pede, sem carregar o arquivo inteiro.

    Uma referência numérica cortada entre dois pedaços (`&#1` | `1;`) espera o pedaço seguinte para ser
    julgada: o resultado é igual ao de `decodificar_xml` para qualquer corte.
    """

    def __init__(
        self, binario: IO[bytes], tamanho_do_pedaco: int = TAMANHO_DO_PEDACO_DO_XML
    ) -> None:
        self.binario = binario
        self.tamanho_do_pedaco = tamanho_do_pedaco
        self.decodificador: codecs.IncrementalDecoder | None = None
        self.inicio = b""
        self.pronto = ""  # limpo, esperando o `read`
        self.pendente = ""  # decodificado, mas pode terminar numa referência cortada
        self.acabou = False

    def _decodificador_para(self, inicio: bytes) -> codecs.IncrementalDecoder:
        nome = (
            "utf-16"
            if inicio.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE))
            else "utf-8-sig"
        )
        return codecs.getincrementaldecoder(nome)()

    def _proximo_pedaco(self) -> None:
        bruto = self.binario.read(self.tamanho_do_pedaco)
        fim_da_leitura = not bruto
        if self.decodificador is None:
            self.inicio += bruto
            if len(self.inicio) < 2 and not fim_da_leitura:  # o BOM tem 2 bytes
                return
            self.decodificador = self._decodificador_para(self.inicio)
            bruto, self.inicio = self.inicio, b""
        self.acabou = fim_da_leitura
        texto = self.pendente + self.decodificador.decode(bruto, final=self.acabou)
        corte = len(texto)
        if not self.acabou:
            e_comercial = texto.rfind("&", max(0, len(texto) - ALCANCE_DA_REFERENCIA))
            if e_comercial >= 0 and ";" not in texto[e_comercial:]:
                corte = e_comercial
        self.pendente = texto[corte:]
        limpo = REFERENCIA_NUMERICA.sub(_referencia_valida, texto[:corte])
        self.pronto += CONTROLE_INVALIDO.sub("", limpo)

    def read(self, tamanho: int = -1) -> str:
        while not self.acabou and (tamanho < 0 or len(self.pronto) < tamanho):
            self._proximo_pedaco()
        if tamanho < 0:
            tamanho = len(self.pronto)
        entregue, self.pronto = self.pronto[:tamanho], self.pronto[tamanho:]
        return entregue


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


def tem_cnpj_inteiro(documento: str | None) -> bool:
    """O documento é um CNPJ inteiro, com letras ou não (`base/cnpj.py`), e o dígito confere: não é
    CPF, nem CNPJ mascarado `**.***.101/***-**`, nem CPF completado com zeros até 14 dígitos.

    Mais estrito que `obter_pj.e_pessoa_juridica`: aqui o documento em branco também sai, porque a
    linha de um cadastro sem o CNPJ não serve para nada."""
    cnpj = cnpjs.completo(documento)
    return cnpj is not None and cnpjs.dv_confere(cnpj)


@contextmanager
def _texto_do_csv(
    bruto: Path, codificacao: str, dentro_do_zip: bool
) -> Generator[IO[str]]:
    if not dentro_do_zip:
        with bruto.open(encoding=codificacao, newline="") as texto:
            yield texto
        return
    with zipfile.ZipFile(bruto) as arquivo:
        csvs = [n for n in arquivo.namelist() if n.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError(
                f"{bruto.name}: o ZIP devia ter um CSV só, tem {len(csvs)}"
            )
        with io.TextIOWrapper(
            arquivo.open(csvs[0]), encoding=codificacao, newline=""
        ) as texto:
            yield texto


def csv_so_com_colunas(
    url: str,
    colunas: tuple[str, ...],
    codificacao: str,
    *,
    separador: str = ";",
    so_com_cnpj_em: str | None = None,
    dentro_do_zip: bool = False,
) -> Obter:
    """Baixa o CSV e grava em `destino` só as `colunas` da lista, na ordem da fonte (sempre com ";").

    Lista de colunas que ficam, e não de colunas que saem (como `obter_pj.csv_so_pj`): o nome do
    titular vem em colunas como "Titular" ou "NO_RAZAO_SOCIAL", que nenhum filtro de nome pegaria.
    `so_com_cnpj_em`: a coluna do documento; a linha sem um CNPJ inteiro (CPF de pessoa física, CNPJ
    mascarado) não é gravada, então o CPF nem chega ao acervo. `dentro_do_zip`: o endereço é um ZIP
    com um CSV só (Anatel). O "utf-8-sig" da leitura tira o BOM; a gravação sai sem ele.
    """

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            with _texto_do_csv(bruto, codificacao, dentro_do_zip) as entrada:
                leitor = csv.DictReader(entrada, delimiter=separador)
                campos = [c for c in (leitor.fieldnames or []) if c in colunas]
                if not campos:
                    raise ValueError(f"{url}: nenhuma das colunas pedidas no cabeçalho")
                if so_com_cnpj_em is not None and so_com_cnpj_em not in campos:
                    raise ValueError(
                        f"{url}: sem a coluna do documento {so_com_cnpj_em!r}"
                    )
                linhas = (
                    leitor
                    if so_com_cnpj_em is None
                    else (l for l in leitor if tem_cnpj_inteiro(l[so_com_cnpj_em]))
                )
                saida_codificacao = codificacao.removesuffix("-sig")
                with destino.open("w", encoding=saida_codificacao, newline="") as saida:
                    escritor = csv.DictWriter(
                        saida, campos, delimiter=";", extrasaction="ignore",
                        quoting=csv.QUOTE_MINIMAL,
                    )  # fmt: skip
                    escritor.writeheader()
                    escritor.writerows(linhas)
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


class SemChaveDoPortal(ValueError):
    """A variável com a chave do dados.gov.br não está no ambiente (vigia da licença)."""


def licenca_da_ficha_do_dados_gov_br(url: str, variavel_da_chave: str) -> Obter:
    """A licença declarada na ficha de um conjunto do dados.gov.br, sem os campos que mudam todo dia.

    Falha (nunca grava um arquivo vazio) se a chave não existe, se a ficha não traz a `licenca` ou
    se o portal respondeu outra coisa: uma vigia que cala quando a página muda não serve."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        chave = os.environ.get(variavel_da_chave, "").strip()
        if not chave:
            raise SemChaveDoPortal(f"{variavel_da_chave} não está no ambiente")
        resposta = cliente.ler(
            url,
            cabecalhos={"chave-api-dados-abertos": chave, "Accept": "application/json"},
        )
        ficha = json.loads(resposta.conteudo)
        if not isinstance(ficha, dict) or not ficha.get(CAMPO_DA_LICENCA):
            raise ValueError(f"a ficha do dados.gov.br não traz {CAMPO_DA_LICENCA}")
        enxuta = {c: ficha.get(c) for c in CAMPOS_DA_LICENCA_DA_FICHA}
        destino.write_text(
            json.dumps(enxuta, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        return {}

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


def arquivo_que_pode_faltar(url: str) -> Obter:
    """Baixa o arquivo; 404 vira `SemArquivo` (o mês que a fonte ainda não publicou)."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        try:
            return cliente.baixar(url, destino)
        except requests.HTTPError as erro:
            resposta = erro.response
            if resposta is not None and resposta.status_code == HTTP_NAO_ENCONTRADO:
                raise SemArquivo("HTTP 404 (mês que ainda não saiu)") from erro
            raise

    return obter

    return obter


# o Google Drive, num arquivo grande demais para a verificação de vírus, responde uma página HTML
# com um formulário; o arquivo mesmo vem do `action` dele com os campos ocultos (id, export, confirm, uuid)
PRIMEIROS_BYTES_QUE_DIZEM_HTML = 512
_FORMULARIO = re.compile(rb"<form[^>]*\saction=\"([^\"]+)\"", re.IGNORECASE)
_CAMPO = re.compile(rb"<input[^>]*>", re.IGNORECASE)
_ATRIBUTO = {
    nome: re.compile(rb"\s" + nome.encode() + rb"=\"([^\"]*)\"", re.IGNORECASE)
    for nome in ("name", "value")
}


def endereco_de_confirmacao_do_drive(pagina: bytes) -> str:
    """O endereço de baixa que a página de confirmação do Google Drive esconde no formulário."""
    formulario = _FORMULARIO.search(pagina)
    if formulario is None:
        raise ValueError(
            "o Google Drive respondeu HTML sem o formulário de confirmação (arquivo privado ou "
            "removido?)"
        )
    campos = {}
    for campo in _CAMPO.findall(pagina):
        nome, valor = (_ATRIBUTO[a].search(campo) for a in ("name", "value"))
        if nome is not None and valor is not None:
            campos[nome.group(1).decode()] = valor.group(1).decode()
    return f"{html.unescape(formulario.group(1).decode())}?{urlencode(campos)}"


def arquivo_do_google_drive(url: str) -> Obter:
    """Baixa um arquivo público do Google Drive; se vier a página de confirmação de arquivo grande
    no lugar dele, segue o formulário dela e baixa de novo."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        cabecalhos = cliente.baixar(url, destino)
        with destino.open("rb") as arquivo:
            inicio = arquivo.read(PRIMEIROS_BYTES_QUE_DIZEM_HTML)
        if b"<html" not in inicio.lower():
            return cabecalhos
        return cliente.baixar(
            endereco_de_confirmacao_do_drive(destino.read_bytes()), destino
        )

    return obter
