"""Retrato mensal do CNPJ aberto da Receita (`rfb-cnpj`): estabelecimentos, Simples/MEI e sócios.

Plano da base de CNPJ (PR 3), ADR 0106. Lê **direto do ZIP**, por partes (o mês inteiro tem 70 milhões de
linhas e cabe em ~650 MB). Layout conferido em 15 e 17/10/2026: sem cabeçalho, `;`, aspas, latin-1;
Estabelecimentos tem 30 campos, Simples 7 e Sócios 11.

**O que nunca sai do leitor** (as colunas nem são guardadas): nome fantasia (o do MEI costuma ser o
nome da pessoa), telefone, DDD, fax e e-mail; do sócio, a faixa etária e o representante legal (nome, CPF e qualificação). Para empresário individual e MEI o endereço vai só até o município e a UF (`so_municipio`).

**Sócio pessoa física:** o nome e o CPF mascarado saem num quadro à parte (`pessoas_brutas`), que só o
esquema `pessoas` (PR 4) grava; o quadro `socios` leva só o que é de empresa. CPF inteiro quebra a carga.
"""

import csv
import io
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import IO, NamedTuple

import pandas as pd

from base import cnpj
from base.receita_natureza import Raizes, _pedidas

CODIFICACAO = "latin-1"
TAMANHO_DA_PARTE = 1_000_000
CAMPOS_DO_ESTABELECIMENTO = 30
CAMPOS_DO_SIMPLES = 7
CAMPOS_DO_SOCIO = 11
DATA_VAZIA = {"", "0", "00000000"}
FORMATO_DA_DATA = "%Y%m%d"
OPTANTE = "S"
MATRIZ = "1"
TIPO_PESSOA_JURIDICA = "1"
CPF_MASCARADO = r"\*{3}\d{6}\*{2}"
CPF_ZERADO = r"0{11}"  # o sócio estrangeiro vem sem CPF
CPF_INTEIRO = r"(?!0{11}$)\d{11}"

# posição de cada campo no arquivo; só estes são lidos
ESTABELECIMENTO = {
    0: "cnpj_basico", 1: "ordem", 2: "dv", 3: "matriz", 5: "situacao_cadastral",
    6: "data_situacao_cadastral", 7: "motivo_situacao", 9: "pais", 10: "data_inicio_atividade",
    11: "cnae_principal", 12: "cnae_secundaria", 13: "tipo_logradouro", 14: "logradouro",
    15: "numero", 16: "complemento", 17: "bairro", 18: "cep", 19: "uf", 20: "municipio",
    28: "situacao_especial", 29: "data_situacao_especial",
}  # fmt: skip
ENDERECO_FINO = (
    "tipo_logradouro", "logradouro", "numero", "complemento", "bairro", "cep",
)  # fmt: skip
DATAS_DO_ESTABELECIMENTO = (
    "data_situacao_cadastral", "data_inicio_atividade", "data_situacao_especial",
)  # fmt: skip
SIMPLES = {
    0: "cnpj_basico", 1: "optante_simples", 2: "data_opcao_simples", 3: "data_exclusao_simples",
    4: "optante_mei", 5: "data_opcao_mei", 6: "data_exclusao_mei",
}  # fmt: skip
SOCIO = {
    0: "cnpj_basico", 1: "tipo_socio", 2: "nome_socio", 3: "documento", 4: "qualificacao",
    5: "data_entrada", 6: "pais",
}  # fmt: skip


class ErroDeLayout(ValueError):
    """Linha com campos a mais que o layout: a Receita mudou o arquivo (a menos, o pandas completa)."""


class ErroDeCpfInteiro(ValueError):
    """CPF sem máscara num arquivo de sócios: nunca entra na base (ADR 0106, item 3.1)."""


class ParteDoQsa(NamedTuple):
    """Um pedaço do `Socios*.zip`: `socios` (de empresa) e `pessoas_brutas` (nome e CPF mascarado)."""

    socios: pd.DataFrame
    pessoas_brutas: pd.DataFrame


def _conferir_campos(zipado: zipfile.ZipFile, membro: str, campos: int) -> None:
    """Confere a 1ª linha: coluna nova da Receita vem em todas, e o pandas a cortaria calado."""
    with zipado.open(membro) as binario:
        primeira = next(
            csv.reader(io.TextIOWrapper(binario, CODIFICACAO), delimiter=";"), []
        )
    if len(primeira) != campos:
        raise ErroDeLayout(f"esperava {campos} campos por linha, achou {len(primeira)}")


def _partes(
    arquivo_zip: Path | IO[bytes], campos: int, posicoes: Iterable[int]
) -> Iterator[pd.DataFrame]:
    """Partes do único arquivo do ZIP, só com as posições pedidas (as outras nem são guardadas)."""
    with zipfile.ZipFile(arquivo_zip) as zipado:
        (membro,) = zipado.namelist()  # cada ZIP da Receita tem um arquivo só
        _conferir_campos(zipado, membro, campos)
        with zipado.open(membro) as texto:
            leitor = pd.read_csv(
                texto, sep=";", header=None, dtype=str, encoding=CODIFICACAO,
                keep_default_na=False, na_values=[], chunksize=TAMANHO_DA_PARTE,
                usecols=sorted(posicoes),
            )  # fmt: skip
            try:
                yield from leitor
            except (ValueError, pd.errors.ParserError) as erro:
                raise ErroDeLayout(
                    f"esperava {campos} campos por linha: {erro}"
                ) from erro


def _datas(serie: pd.Series) -> pd.Series:
    """`AAAAMMDD` em data; vazio, `0` e `00000000` (115 mil casos em 2026-10) viram `NaT`."""
    texto = serie.str.strip()
    return pd.to_datetime(
        texto.mask(texto.isin(DATA_VAZIA)), format=FORMATO_DA_DATA, errors="coerce"
    )


def _estabelecimentos(
    parte: pd.DataFrame, so_municipio: Raizes | None, todos_so_municipio: bool
) -> pd.DataFrame:
    parte = parte.rename(columns=ESTABELECIMENTO)
    completo = (parte["cnpj_basico"] + parte["ordem"] + parte["dv"]).str.upper()
    saida = parte.drop(columns=["ordem", "dv"])
    saida.insert(0, "cnpj", completo)
    saida["dv_confere"] = completo.map(cnpj.dv_confere)
    saida["matriz"] = parte["matriz"] == MATRIZ
    for coluna in DATAS_DO_ESTABELECIMENTO:
        saida[coluna] = _datas(saida[coluna])
    if todos_so_municipio:
        saida[list(ENDERECO_FINO)] = ""
    elif so_municipio is not None and len(so_municipio):
        fino = _pedidas(saida["cnpj_basico"], so_municipio)
        saida.loc[fino, list(ENDERECO_FINO)] = ""
    return saida


def ler_estabelecimentos(
    arquivo_zip: Path | IO[bytes],
    so_municipio: Raizes | None = None,
    todos_so_municipio: bool = False,
) -> Iterator[pd.DataFrame]:
    """Estabelecimentos de um `Estabelecimentos*.zip`, em partes, sem contato nem nome fantasia.

    `cnpj` tem os 14 caracteres (com letras no CNPJ novo); DV errado vira `dv_confere=False`, não
    descarte. `so_municipio` são as raízes de empresário individual e MEI: o endereço delas fica só em
    município e UF. `todos_so_municipio` faz isso com todas as empresas, enquanto não há o leitor de
    `Empresas*` que diz quem é empresário individual (a carga usa até a linha 233 da fila).
    """
    for parte in _partes(arquivo_zip, CAMPOS_DO_ESTABELECIMENTO, ESTABELECIMENTO):
        yield _estabelecimentos(parte, so_municipio, todos_so_municipio)


def ler_simples(arquivo_zip: Path | IO[bytes]) -> Iterator[pd.DataFrame]:
    """Opção pelo Simples e pelo MEI, com as datas, de um `Simples.zip`."""
    for parte in _partes(arquivo_zip, CAMPOS_DO_SIMPLES, SIMPLES):
        saida = parte.rename(columns=SIMPLES)
        for coluna in ("optante_simples", "optante_mei"):
            saida[coluna] = saida[coluna].str.strip() == OPTANTE
        for coluna in [c for c in saida.columns if c.startswith("data_")]:
            saida[coluna] = _datas(saida[coluna])
        yield saida


def _separar_socios(parte: pd.DataFrame) -> ParteDoQsa:
    parte = parte.rename(columns=SOCIO)
    parte["data_entrada"] = _datas(parte["data_entrada"])
    documento = parte["documento"].str.strip().str.upper()
    juridica = parte["tipo_socio"] == TIPO_PESSOA_JURIDICA
    # em 2023-05 o sócio estrangeiro vinha com o documento vazio: vira o mesmo CPF zerado de hoje
    documento = documento.mask((documento == "") & ~juridica, "0" * 11)
    if documento[~juridica].str.fullmatch(CPF_INTEIRO).any():
        raise ErroDeCpfInteiro("arquivo de sócios com CPF sem máscara")
    socios = parte.drop(columns=["nome_socio", "documento"])
    # desde 08/2026 a Receita traz só a raiz (8); antes vinham os 14: as duas viram a raiz
    socios["raiz_socio_pj"] = documento.str[: cnpj.TAMANHO_DA_RAIZ].where(juridica)
    pessoas = parte.loc[
        ~juridica,
        ["cnpj_basico", "tipo_socio", "nome_socio", "qualificacao", "data_entrada"],
    ].copy()
    pessoas["cpf_mascarado"] = documento[~juridica]
    formato = f"{CPF_MASCARADO}|{CPF_ZERADO}"
    if len(pessoas) and not pessoas["cpf_mascarado"].str.fullmatch(formato).all():
        raise ErroDeLayout("documento de sócio fora do formato mascarado")
    return ParteDoQsa(socios.reset_index(drop=True), pessoas.reset_index(drop=True))


def ler_qsa(arquivos_zip: Iterable[Path | IO[bytes]]) -> Iterator[ParteDoQsa]:
    """Quadro de sócios dos `Socios*.zip`: o que é de empresa separado do nome e do CPF mascarado.

    `socios`: raiz da empresa, tipo (1 PJ, 2 PF, 3 estrangeiro), raiz do sócio PJ, qualificação, data de
    entrada e país. `pessoas_brutas`: nome e CPF mascarado de quem não é PJ, só para o PR 4 gravar no
    esquema `pessoas`. Faixa etária e representante legal nem são lidos.
    """
    for arquivo in arquivos_zip:
        for parte in _partes(arquivo, CAMPOS_DO_SOCIO, SOCIO):
            yield _separar_socios(parte)
