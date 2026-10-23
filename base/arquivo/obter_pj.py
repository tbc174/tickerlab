"""Formas de obter licitações e contratos públicos guardando só pessoa jurídica (ADR 0088, LGPD).

Os CSVs e as APIs de compras misturam CPF e CNPJ (fornecedor, contratado, favorecido) e trazem nomes de
servidores (pregoeiro, fiscal, responsável, `usuarioNome`). O acervo guarda só a linha cujo documento
tem 14 dígitos (ou está em branco) e fica sem as colunas de pessoa:

- `csv_so_pj`: lê o CSV (solto, em ZIP ou em GZIP) em fluxo, sem pôr o arquivo na memória, e grava
  um CSV ";" em UTF-8.
- `json_paginado`: percorre uma API paginada e grava um item por linha (JSON Lines), com o mesmo filtro.

O arquivo guardado **não é o da fonte**: é o da fonte menos as pessoas físicas (o registro diz isso).
Um MEI tem CNPJ de 14 dígitos e entra, como a regra da ADR 0088 manda.
"""

import csv
import gzip
import io
import itertools
import json
import re
import time
import zipfile
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

from base.arquivo.coleta import Cliente, Obter, SemArquivo

DIGITOS_DO_CNPJ = 14
LIMITE_DO_CAMPO_DO_CSV = (
    10 * 1024**2
)  # objeto e justificativa de compra passam de 128 KB
# colunas que guardam o documento (CPF ou CNPJ) de quem vende ao governo; "cnpj" no nome também vale
DOCUMENTOS = frozenset(
    {
        "ni_fornecedor",
        "nifornecedor",
        "nifornecedorsubcontratado",
        "cod_fornecedor",
        "identificacao_participante",
        "id_fornecedor_contrato",
        "identif_fornecedor",
        "identif_proponente",
        "identificacao_fornecedor_item_licitacao",
        "identif_favorecido_obtv_conv",
        "nr_documento_anonimizado",
        "idcontratado",
        "identificacao_empresa_executora_instrumento_contratual",
        "identificacao_fornecedor_licitacao_vrpl",
    }
)
SO_COMECO_DO_CNPJ = re.compile(r"basico|raiz")
# colunas e campos de pessoa (servidor, parlamentar, contato, conta bancária): saem de qualquer arquivo
PESSOAL = re.compile(
    r"cpf|usuario|responsavel|_resp_|logado|parlamentar|mail|telefone|fax|nmfiscal|nmrep"
    r"|no_adjudic|no_hom$|nome_vencedor_pf|banco|agencia|numero_conta|dv_conta|dado_bancario",
    re.IGNORECASE,
)
NAO_DIGITO = re.compile(r"\D")


def e_documento(nome: str) -> bool:
    nome = nome.strip().lower()
    return nome in DOCUMENTOS or ("cnpj" in nome and not SO_COMECO_DO_CNPJ.search(nome))


def e_pessoal(nome: str) -> bool:
    return not e_documento(nome) and bool(PESSOAL.search(nome))


def e_pessoa_juridica(valor: object) -> bool:
    """Documento em branco (sem fornecedor identificado) ou com 14 dígitos; CPF e máscara de fora."""
    texto = "" if valor is None else str(valor).strip()
    return not texto or len(NAO_DIGITO.sub("", texto)) == DIGITOS_DO_CNPJ


def sem_pessoas(valor: object) -> object:
    """O valor sem os campos de pessoa, também dentro dos objetos e listas que ele traz."""
    if isinstance(valor, dict):
        return {k: sem_pessoas(v) for k, v in valor.items() if not e_pessoal(k)}
    if isinstance(valor, list):
        return [sem_pessoas(v) for v in valor]
    return valor


def item_so_pj(item: Mapping[str, Any]) -> dict[str, object] | None:
    """O item da API sem os campos de pessoa, ou None se o documento dele não é de pessoa jurídica."""
    for chave, valor in item.items():
        if chave.lower() == "tipopessoa" and str(valor).strip().upper() == "PF":
            return None
        if e_documento(chave) and not e_pessoa_juridica(valor):
            return None
    return {k: sem_pessoas(v) for k, v in item.items() if not e_pessoal(k)}


@contextmanager
def _abrir_o_csv(bruto: Path, recipiente: str) -> Generator[IO[bytes]]:
    """O CSV de dentro do ZIP ou do GZIP, ou o próprio arquivo, em fluxo."""
    if recipiente == "zip":
        with zipfile.ZipFile(bruto) as arquivo_zip:
            nomes = [n for n in arquivo_zip.namelist() if n.lower().endswith(".csv")]
            if not nomes:
                raise ValueError(f"{bruto.name}: nenhum CSV dentro do ZIP")
            with arquivo_zip.open(nomes[0]) as csv_do_zip:
                yield csv_do_zip
    elif recipiente == "gz":
        with gzip.open(bruto, "rb") as csv_do_gzip:
            yield csv_do_gzip
    else:
        with bruto.open("rb") as csv_solto:
            yield csv_solto


def _filtrar_o_csv(binario: IO[bytes], destino: Path, codificacao: str) -> int:
    """Grava o CSV filtrado em `destino` e devolve quantas linhas ficaram."""
    csv.field_size_limit(LIMITE_DO_CAMPO_DO_CSV)
    texto = io.TextIOWrapper(
        binario, encoding=codificacao, errors="replace", newline=""
    )
    primeira = texto.readline()
    separador = ";" if primeira.count(";") >= primeira.count(",") else ","
    leitor = csv.reader(itertools.chain([primeira], texto), delimiter=separador)
    cabecalho = next(leitor, None)
    if not cabecalho:
        raise ValueError(f"{destino.name}: CSV sem cabeçalho")
    ficam = [i for i, nome in enumerate(cabecalho) if not e_pessoal(nome)]
    documentos = [i for i, nome in enumerate(cabecalho) if e_documento(nome)]
    gravadas = 0
    with destino.open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
        escritor.writerow([cabecalho[i] for i in ficam])
        for linha in leitor:
            linha += [""] * (len(cabecalho) - len(linha))
            if all(e_pessoa_juridica(linha[i]) for i in documentos):
                escritor.writerow([linha[i] for i in ficam])
                gravadas += 1
    return gravadas


def csv_so_pj(url: str, recipiente: str, codificacao: str = "utf-8-sig") -> Obter:
    """Baixa o CSV (solto, "zip" ou "gz") e grava em `destino` só as linhas de pessoa jurídica,
    sem as colunas de pessoa; o separador é achado no cabeçalho e sai sempre ";"."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            with _abrir_o_csv(bruto, recipiente) as binario:
                _filtrar_o_csv(binario, destino, codificacao)
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return obter


class PaginacaoSemFim(RuntimeError):
    """A API não parou de devolver páginas: melhor falhar do que guardar um pedaço."""


def json_paginado(
    endereco: Callable[[int], str],
    ler: Callable[[Any], tuple[list[dict[str, Any]], bool]],
    *,
    maximo_de_paginas: int,
    pausa_s: float = 0.0,
) -> Obter:
    """Percorre uma API paginada (`endereco(n)` é a página n, de 1 em diante; `ler` devolve os itens
    e se há mais páginas; resposta vazia, como o 204 do PNCP, chega como `{}`) e grava os itens de pessoa jurídica, um por linha. Sem nenhum item, a janela
    não tem dado (`SemArquivo`); passar de `maximo_de_paginas` é erro, nunca um arquivo cortado."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        gravados = 0
        with destino.open("w", encoding="utf-8", newline="\n") as saida:
            for pagina in range(1, maximo_de_paginas + 1):
                conteudo = cliente.ler(endereco(pagina)).conteudo
                itens, ha_mais = ler(json.loads(conteudo) if conteudo.strip() else {})
                for item in itens:
                    limpo = item_so_pj(item)
                    if limpo is not None:
                        saida.write(json.dumps(limpo, ensure_ascii=False) + "\n")
                        gravados += 1
                if not ha_mais:
                    break
                time.sleep(pausa_s)
            else:
                raise PaginacaoSemFim(
                    f"{endereco(1)}: mais de {maximo_de_paginas} páginas"
                )
        if not gravados:
            raise SemArquivo("janela sem registros de pessoa jurídica")
        return {}

    return obter
