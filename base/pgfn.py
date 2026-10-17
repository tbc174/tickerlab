"""Dívida ativa da União (PGFN) por CNPJ de empresa: a tabela `pgfn_divida` (camada do monitor de
cedentes, ADR 0076 com a Emenda 1; sinal "dívida ativa" da Emenda 1 da ADR 0030).

**Só pessoa jurídica** (ADR 0075): a lista da PGFN traz pessoas físicas com o nome inteiro (o CPF vem
mascarado). Do CSV o leitor só pede as colunas daqui (`LIDAS`): o nome do devedor nunca é lido, e as
linhas que não são de pessoa jurídica ou cujo CNPJ não tem o dígito certo saem antes de qualquer
conta (e são contadas). Empresário individual e MEI têm CNPJ, mas a razão social deles é o nome da
pessoa: ficam com `trata_como_pessoa` (pela natureza jurídica e pelo MEI da Receita,
`base/receita_natureza.py`; sem a Receita, também, que é o conservador).

**Agregada**: uma linha por (CNPJ, tipo de dívida, região da PGFN, tipo de devedor, situação,
ajuizada), com quantas inscrições, o valor somado e a primeira e a última data de inscrição. As
inscrições uma a uma (dezenas de milhões) ficam no acervo bruto; a tabela cabe na memória do servidor
de casa. Layout conferido em 16/10/2026 (retrato de 2026-06): três ZIPs (SIDA = não previdenciária,
PREV = previdenciária, FGTS), um CSV por região dentro de cada um (`arquivo_lai_SIDA_3_202606.csv`),
`;`, latin-1, com cabeçalho; as colunas mudam um pouco entre os três, por isso o leitor lê pelo nome.

**Datas** (sem olhar o futuro): `data_do_retrato` é o último dia do mês do retrato; a PGFN não diz
quando publicou, então `disponivel_em` é o dia em que o arquivista viu o arquivo pela primeira vez;
`gerado_em` é a data dos CSVs dentro do ZIP (informativa: não é a de publicação).
"""

import csv
import re
import zipfile
from calendar import monthrange
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import IO

import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import receita_natureza
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from base.rede.entidades import natureza_de_pessoa
from src import acervo
from src.banco.coletas import originais_mais_recentes, versoes_guardadas
from src.versao_do_codigo import versao_do_codigo

FONTE = "pgfn-divida"
TABELA = "pgfn_divida"
CODIFICACAO = "latin-1"
TAMANHO_DA_PARTE = 500_000  # linhas do CSV por vez
JUNTAR_A_CADA = 8  # partes já somadas que se juntam numa só (limita a memória)
JA_MONTADO = {"ja_montado": 1}  # no resumo: o arquivo já estava montado deste mesmo ZIP
SISTEMAS = {"SIDA": "nao_previdenciaria", "PREV": "previdenciaria", "FGTS": "fgts"}
MEMBRO = re.compile(
    r"arquivo_lai_(SIDA|PREV|FGTS)_([0-9A-Z]+)_(\d{4})(\d{2})\.csv$", re.IGNORECASE
)
PESSOA_JURIDICA = "Pessoa jurídica"
FORMA_DO_CNPJ = re.compile(r"^[0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3}/[0-9A-Z]{4}-\d{2}$")
SEPARADORES = re.compile(r"[./-]")
PRIMEIRA_DATA_DE_VERDADE = pd.Timestamp(
    "1900-01-01"
)  # a PGFN escreve 01/01/1000 sem data
LIDAS = {
    "CPF_CNPJ": "cnpj",
    "TIPO_PESSOA": "tipo_pessoa",
    "TIPO_DEVEDOR": "tipo_devedor",
    "TIPO_SITUACAO_INSCRICAO": "tipo_situacao",
    "SITUACAO_INSCRICAO": "situacao_inscricao",
    "DATA_INSCRICAO": "data",
    "INDICADOR_AJUIZADO": "ajuizado",
    "VALOR_CONSOLIDADO": "valor",
}
GRUPO = ["cnpj", "tipo_devedor", "tipo_situacao", "situacao_inscricao", "ajuizado"]
ORDEM = [
    "cnpj",
    "tipo_divida",
    "regiao",
    "tipo_devedor",
    "tipo_situacao",
    "situacao_inscricao",
    "ajuizado",
]
COLUNAS = [
    "cnpj",
    "cnpj_basico",
    "tipo_divida",
    "regiao",
    "tipo_devedor",
    "tipo_situacao",
    "situacao_inscricao",
    "ajuizado",
    "inscricoes",
    "valor_consolidado",
    "primeira_inscricao",
    "ultima_inscricao",
    "data_do_retrato",
    "gerado_em",
    "trata_como_pessoa",
]
Arquivo = Path | IO[bytes]
Soma = tuple[str, str]  # (coluna, conta) do `agg` do pandas


@dataclass(frozen=True)
class Membro:
    """Um CSV dentro do ZIP: um sistema da PGFN, uma região, um retrato."""

    nome: str
    sistema: str  # SIDA, PREV ou FGTS
    regiao: str  # "1" a "6" ou "NA", como no nome do arquivo
    data_do_retrato: date
    gerado_em: date

    @property
    def tipo_divida(self) -> str:
        return SISTEMAS[self.sistema]

    @property
    def mes(self) -> str:
        return self.data_do_retrato.strftime("%Y-%m")

    @property
    def arquivo(self) -> str:
        return f"{self.sistema.lower()}-{self.regiao}"


def membros(arquivo_zip: Arquivo) -> list[Membro]:
    """Os CSVs da dívida ativa dentro do ZIP (o resto, como um leia-me, fica de fora)."""
    achados = []
    with zipfile.ZipFile(arquivo_zip) as zipado:
        for info in zipado.infolist():
            casou = MEMBRO.search(info.filename)
            if casou is None:
                continue
            sistema, regiao, ano, mes = casou.groups()
            ano_, mes_ = int(ano), int(mes)
            achados.append(
                Membro(
                    nome=info.filename,
                    sistema=sistema.upper(),
                    regiao=regiao.upper(),
                    data_do_retrato=date(ano_, mes_, monthrange(ano_, mes_)[1]),
                    gerado_em=date(*info.date_time[:3]),
                )
            )
    return achados


def _partes(
    arquivo_zip: Arquivo, nome: str, colunas: list[str]
) -> Iterator[pd.DataFrame]:
    with zipfile.ZipFile(arquivo_zip) as zipado, zipado.open(nome) as texto:
        yield from pd.read_csv(
            texto, sep=";", usecols=colunas, dtype=str, encoding=CODIFICACAO,
            keep_default_na=False, quoting=csv.QUOTE_NONE, chunksize=TAMANHO_DA_PARTE,
        )  # fmt: skip


def _de_pessoa_juridica(parte: pd.DataFrame) -> pd.Series:
    return (parte["TIPO_PESSOA"].str.strip() == PESSOA_JURIDICA) & parte[
        "CPF_CNPJ"
    ].str.strip().str.match(FORMA_DO_CNPJ)


def _so_digitos(cnpj: pd.Series) -> pd.Series:
    return cnpj.str.replace(SEPARADORES, "", regex=True)


def raizes_dos_devedores(arquivo_zip: Arquivo) -> set[str]:
    """As raízes (8 primeiros caracteres) dos CNPJs de pessoa jurídica do ZIP (1ª leitura, leve)."""
    raizes: set[str] = set()
    for membro in membros(arquivo_zip):
        for parte in _partes(arquivo_zip, membro.nome, ["CPF_CNPJ", "TIPO_PESSOA"]):
            cnpj = parte.loc[_de_pessoa_juridica(parte), "CPF_CNPJ"].str.strip()
            raizes.update(_so_digitos(cnpj.drop_duplicates()).str[:8])
    return raizes


def raizes_de_pessoa(
    raizes: set[str], naturezas: pd.DataFrame, meis: pd.DataFrame
) -> set[str]:
    """As raízes que são (ou podem ser) pessoa: empresário individual, grupo 4, MEI ou sem Receita."""
    todas = pd.Index(sorted(raizes))
    de_pessoa = naturezas.loc[
        naturezas["natureza_juridica"].map(natureza_de_pessoa), "cnpj_basico"
    ]
    e_pessoa = (
        ~todas.isin(naturezas["cnpj_basico"])
        | todas.isin(de_pessoa)
        | todas.isin(meis.loc[meis["mei"], "cnpj_basico"])
    )
    return set(todas[e_pessoa])


def _sem_acento(texto: pd.Series) -> pd.Series:
    return (
        texto.str.strip()
        .str.lower()
        .str.normalize("NFKD")
        .str.encode("ascii", "ignore")
        .str.decode("ascii")
    )


def _padronizar(parte: pd.DataFrame) -> pd.DataFrame:
    tabela = parte[list(LIDAS)].rename(columns=LIDAS)
    data = pd.to_datetime(tabela["data"], format="%d/%m/%Y", errors="coerce")
    return tabela.assign(
        cnpj=tabela["cnpj"].str.strip(),
        tipo_devedor=_sem_acento(tabela["tipo_devedor"]),
        tipo_situacao=tabela["tipo_situacao"].str.strip(),
        situacao_inscricao=tabela["situacao_inscricao"].str.strip(),
        ajuizado=tabela["ajuizado"].str.strip().str.upper() == "SIM",
        valor=pd.to_numeric(tabela["valor"].str.strip(), errors="coerce"),
        data=data.where(data >= PRIMEIRA_DATA_DE_VERDADE),
    ).drop(columns=["tipo_pessoa"])


def _somar(
    tabela: pd.DataFrame, inscricoes: Soma, valor: Soma, primeira: Soma, ultima: Soma
) -> pd.DataFrame:
    return (
        tabela.groupby(GRUPO, sort=False)
        .agg(
            inscricoes=inscricoes,
            valor_consolidado=valor,
            primeira_inscricao=primeira,
            ultima_inscricao=ultima,
        )
        .reset_index()
    )  # fmt: skip


def _agregar(parte: pd.DataFrame) -> pd.DataFrame:
    return _somar(
        parte, ("valor", "size"), ("valor", "sum"), ("data", "min"), ("data", "max")
    )


def _juntar(partes: list[pd.DataFrame]) -> pd.DataFrame:
    return _somar(
        pd.concat(partes, ignore_index=True),
        ("inscricoes", "sum"),
        ("valor_consolidado", "sum"),
        ("primeira_inscricao", "min"),
        ("ultima_inscricao", "max"),
    )


def _cnpj_valido(cnpj: str) -> bool:
    return cnpjs.dv_confere(SEPARADORES.sub("", cnpj))


def ler_membro(
    arquivo_zip: Arquivo, membro: Membro, pessoas: set[str]
) -> tuple[pd.DataFrame, dict[str, int]]:
    """A tabela agregada de um CSV e a contagem do que ficou de fora (linhas do CSV)."""
    lidas = fora_por_pessoa = 0
    partes: list[pd.DataFrame] = []
    for parte in _partes(arquivo_zip, membro.nome, list(LIDAS)):
        juridica = _de_pessoa_juridica(parte)
        lidas += len(parte)
        fora_por_pessoa += int((~juridica).sum())
        partes.append(_agregar(_padronizar(parte[juridica])))
        if len(partes) >= JUNTAR_A_CADA:
            partes = [_juntar(partes)]
    tabela = (
        _juntar(partes)
        if partes
        else _agregar(_padronizar(pd.DataFrame(columns=list(LIDAS))))
    )
    unicos = tabela["cnpj"].drop_duplicates()
    valido = tabela["cnpj"].map(
        dict(zip(unicos, unicos.map(_cnpj_valido), strict=True))
    )
    invalidas = int(tabela.loc[~valido.astype(bool), "inscricoes"].sum())
    tabela = tabela[valido.astype(bool)].sort_values(GRUPO).reset_index(drop=True)
    basico = _so_digitos(tabela["cnpj"]).str[:8]
    tabela = tabela.assign(
        cnpj_basico=basico,
        tipo_divida=membro.tipo_divida,
        regiao=membro.regiao,
        inscricoes=tabela["inscricoes"].astype("int64"),
        valor_consolidado=tabela["valor_consolidado"].astype("float64"),
        primeira_inscricao=pd.to_datetime(tabela["primeira_inscricao"]).dt.date,
        ultima_inscricao=pd.to_datetime(tabela["ultima_inscricao"]).dt.date,
        data_do_retrato=membro.data_do_retrato,
        gerado_em=membro.gerado_em,
        trata_como_pessoa=basico.isin(pessoas),
    )[COLUNAS]
    contagem = {
        "linhas": lidas,
        "pessoa_fisica": fora_por_pessoa,
        "cnpj_invalido": invalidas,
        "na_tabela": len(tabela),
    }
    return tabela, contagem


@dataclass(frozen=True)
class _Guardado:
    original: sa.Row
    caminho: Path
    disponivel_em: date


def _guardados(conexao: sa.Connection) -> list[_Guardado]:
    """Os ZIPs da PGFN guardados no acervo, cada um com o dia em que foi visto pela primeira vez."""
    pasta = acervo.pasta_do_acervo()
    achados = []
    for original in originais_mais_recentes(conexao, FONTE):
        if pasta is None or not (pasta / original.caminho_do_original).is_file():
            continue
        primeira = next(
            v.baixado_em
            for v in versoes_guardadas(conexao, original.url)
            if v.sha256 == original.sha256
        )
        achados.append(
            _Guardado(
                original,
                pasta / original.caminho_do_original,
                pd.Timestamp(primeira).date(),
            )
        )
    return achados


def pessoas_pela_receita(conexao: sa.Connection, raizes: set[str]) -> set[str]:
    """As raízes de pessoa entre as `raizes`, pela Receita do mês mais recente (sem ela, todas)."""
    arquivos = receita_natureza.arquivos_do_mes_mais_recente(conexao)
    if not arquivos:
        return set(raizes)
    naturezas = [
        receita_natureza.ler_naturezas(c, raizes) for n, c in arquivos if n != "Simples"
    ]
    meis = [receita_natureza.ler_mei(c, raizes) for n, c in arquivos if n == "Simples"]
    return raizes_de_pessoa(
        raizes,
        pd.concat(naturezas, ignore_index=True)
        if naturezas
        else pd.DataFrame(columns=["cnpj_basico", "natureza_juridica"]),
        pd.concat(meis, ignore_index=True)
        if meis
        else pd.DataFrame(
            {"cnpj_basico": pd.Series(dtype=str), "mei": pd.Series(dtype=bool)}
        ),
    )


def _destino(pasta: Path, membro: Membro) -> Path:
    return pasta / TABELA / membro.mes / membro.arquivo


def _origem(guardado: _Guardado) -> list[dict[str, str]]:
    return [{"url": guardado.original.url, "sha256": guardado.original.sha256}]


def _ja_montado(pasta: Path, guardado: _Guardado) -> bool:
    """Todos os CSVs do ZIP já gravados com ele de origem (o manifesto diz o SHA-256)."""
    return all(
        origens_gravadas(_destino(pasta, m)) == _origem(guardado)
        for m in membros(guardado.caminho)
    )


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: set[str] | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/pgfn_divida/<AAAA-MM>/<sistema>-<região>.parquet` para cada CSV guardado.

    Um arquivo de cada vez (o maior tem ~2,7 GB descompactado). ZIP já montado é pulado (a PGFN muda
    por trimestre; `refazer` relê mesmo assim, para código novo). `pessoas`: as raízes de pessoa já
    sabidas; sem elas, lê as raízes dos devedores e pergunta à Receita guardada (a marca vale pela
    Receita do dia da montagem).
    """
    resumo: dict[str, dict[str, int]] = {}
    guardados = []
    for guardado in _guardados(conexao):
        if not refazer and _ja_montado(pasta, guardado):
            for membro in membros(guardado.caminho):
                resumo[f"{membro.mes}/{membro.arquivo}"] = JA_MONTADO
        else:
            guardados.append(guardado)
    if pessoas is None and guardados:
        raizes: set[str] = set()
        for guardado in guardados:
            raizes |= raizes_dos_devedores(guardado.caminho)
        pessoas = pessoas_pela_receita(conexao, raizes)
    for guardado in guardados:
        original = guardado.original
        for membro in membros(guardado.caminho):
            tabela, contagem = ler_membro(guardado.caminho, membro, pessoas or set())
            tabela = tabela.assign(
                disponivel_em=guardado.disponivel_em,
                origem_sha256=original.sha256,
                origem_coletada_em=pd.Timestamp(original.baixado_em).isoformat(),
                montado_em=agora.isoformat(),
                versao_do_codigo=versao_do_codigo(),
            )
            gravar_se_mudou(
                tabela,
                _destino(pasta, membro),
                _origem(guardado),
                ORDEM,
                carimbos=LINHAGEM,
            )
            resumo[f"{membro.mes}/{membro.arquivo}"] = contagem
    return resumo
