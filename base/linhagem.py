"""Linhagem para auditoria (série 3 da base de ML, PR 1; ADR 0055, exigência 13).

De qualquer linha de uma base em Parquet (`base/ponto_no_tempo.py::gravar_parquet`), refaz o caminho:
o `<ano>.json` ao lado do Parquet dá o hash da base, a versão do código e as origens (endereço e
SHA-256 de cada original); o registro de coletas dá a data da coleta e onde o original está no acervo;
o acervo confirma que o arquivo guardado ainda tem aquele SHA-256. A linhagem é "completa" só se
todos os elos existem e conferem.

Uma tabela conferida à mão (`base/conferidas/`, série 3, PR 8) não tem coleta: o elo é o arquivo no
repositório com o SHA-256 anotado (cada linha dela diz a fonte e quando foi conferida). Se a tabela
mudar depois, a base que a usou deixa de conferir até ser remontada (a versão antiga fica no Git).

Uma tabela **derivada** (série 4, PR 2: o painel dos fundos, a ligação dos bancos) vem de outras
tabelas da base, não de originais: a origem é o endereço de um Parquet (`cda/2025.parquet`,
`base/fca/emissores.parquet`), procurado a partir da pasta da tabela e subindo, com o SHA-256 do
conteúdo (o `sha256_da_tabela` do manifesto da entrada) ou dos bytes do arquivo. A linhagem segue o
manifesto da entrada até os originais; se a entrada foi regravada depois, a derivada não confere até
ser remontada. Ciclo, ou mais de `PROFUNDIDADE_MAXIMA` tabelas encadeadas, é erro.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base.parquet import conferir_tabela, e_tabela_da_base
from base.ponto_no_tempo import DEMONSTRACOES, SEM_DATA, Formato, conferir_pasta
from src import acervo
from src.banco.modelo import coletas

RAIZ_DO_REPOSITORIO = Path(__file__).resolve().parent.parent
TABELAS_CONFERIDAS = "base/conferidas/"
PROFUNDIDADE_MAXIMA = (
    5  # tabelas derivadas encadeadas (hoje: painel ← emissores ← FCA = 1)
)


@dataclass(frozen=True)
class Origem:
    url: str
    sha256: str
    baixado_em: datetime | None  # None: nenhuma coleta registrada com este arquivo
    caminho_do_original: str | None
    original_confere: (
        bool  # o arquivo do acervo (ou do repositório) ainda tem o SHA-256
    )
    no_repositorio: bool = False  # tabela conferida à mão, sem coleta
    derivada: "Linhagem | None" = None  # a origem é uma tabela da base: a linhagem dela

    @property
    def tem_procedencia(self) -> bool:
        """Há de onde veio: coleta registrada, arquivo do repositório ou tabela da base."""
        return (
            self.baixado_em is not None
            or self.no_repositorio
            or (self.derivada is not None and self.derivada.completa)
        )


@dataclass(frozen=True)
class Linhagem:
    ano: str  # o ano do Parquet, ou o nome da tabela
    versao_do_codigo: str | None  # None: manifesto gravado antes da exigência 13
    base_confere: bool  # o Parquet do ano ainda tem o hash anotado no manifesto
    origens: list[Origem]

    @property
    def completa(self) -> bool:
        return (
            self.versao_do_codigo is not None
            and self.base_confere
            and bool(self.origens)
            and all(o.tem_procedencia and o.original_confere for o in self.origens)
        )

    def originais(self) -> list[Origem]:
        """As origens do fim do caminho (arquivos coletados e tabelas conferidas), atravessando as
        tabelas derivadas."""
        return [
            folha
            for o in self.origens
            for folha in ([o] if o.derivada is None else o.derivada.originais())
        ]


def _ano_da_linha(linha: pd.Series) -> str:
    fim = linha.get("fim")
    return SEM_DATA if fim is None or pd.isna(fim) else str(pd.Timestamp(fim).year)


def _origem_no_repositorio(url: str, sha256: str) -> Origem:
    arquivo = (RAIZ_DO_REPOSITORIO / url).resolve()
    dentro = arquivo.is_relative_to(
        RAIZ_DO_REPOSITORIO / TABELAS_CONFERIDAS
    )  # nada de "../"
    confere = (
        dentro
        and arquivo.is_file()
        and hashlib.sha256(arquivo.read_bytes()).hexdigest() == sha256
    )
    return Origem(url, sha256, None, url, confere, no_repositorio=True)


def _achar_tabela(url: str, tabela: Path) -> Path | None:
    """O Parquet da origem, procurado a partir da pasta da tabela que a usou, subindo."""
    return next(
        (pasta / url for pasta in tabela.parents if (pasta / url).is_file()), None
    )


def _entrada_confere(entrada: Path, sha256: str) -> bool:
    """A tabela de entrada ainda é a que a derivada leu (pelo conteúdo ou pelos bytes)."""
    if not conferir_tabela(entrada):
        return False
    anotado = json.loads(entrada.with_suffix(".json").read_text(encoding="utf-8"))
    return sha256 in (
        anotado.get("sha256_da_tabela"),
        hashlib.sha256(entrada.read_bytes()).hexdigest(),
    )


def _origem_derivada(
    conexao: sa.Connection,
    url: str,
    sha256: str,
    tabela: Path,
    caminho: tuple[Path, ...],
) -> Origem:
    entrada = _achar_tabela(url, tabela)
    if entrada is None:
        return Origem(url, sha256, None, None, False)
    derivada = _linhagem_da_tabela(conexao, entrada, caminho)
    return Origem(
        url, sha256, None, str(entrada), _entrada_confere(entrada, sha256),
        derivada=derivada,
    )  # fmt: skip


def _origem(
    conexao: sa.Connection,
    url: str,
    sha256: str,
    tabela: Path,
    caminho: tuple[Path, ...],
) -> Origem:
    if url.startswith(TABELAS_CONFERIDAS):
        return _origem_no_repositorio(url, sha256)
    if e_tabela_da_base(url):
        return _origem_derivada(conexao, url, sha256, tabela, caminho)
    coleta = conexao.execute(
        sa.select(coletas.c.baixado_em, coletas.c.caminho_do_original)
        .where(coletas.c.sha256 == sha256, coletas.c.situacao == "ok")
        .order_by(coletas.c.baixado_em)
        .limit(1)
    ).first()
    if coleta is None:
        return Origem(url, sha256, None, None, False)
    caminho = coleta.caminho_do_original
    confere = caminho is not None and acervo.confere_com_o_registro(caminho, sha256)
    return Origem(url, sha256, coleta.baixado_em, caminho, confere)


def _linhagem(
    conexao: sa.Connection,
    nome: str,
    manifesto: Path,
    confere: bool,
    caminho: tuple[Path, ...] = (),
) -> Linhagem:
    anotado = json.loads(manifesto.read_text(encoding="utf-8"))
    return Linhagem(
        ano=nome,
        versao_do_codigo=anotado.get("versao_do_codigo"),
        base_confere=confere,
        origens=[
            _origem(conexao, o["url"], o["sha256"], manifesto, caminho)
            for o in anotado.get("origens", [])
        ],
    )


def _linhagem_da_tabela(
    conexao: sa.Connection, arquivo: Path, caminho: tuple[Path, ...]
) -> Linhagem:
    arquivo = arquivo.resolve()
    if arquivo in caminho:
        raise ValueError(f"ciclo na linhagem: {arquivo} já está no caminho")
    if len(caminho) > PROFUNDIDADE_MAXIMA:
        raise ValueError(
            f"profundidade da linhagem passa de {PROFUNDIDADE_MAXIMA} tabelas: {arquivo}"
        )
    return _linhagem(
        conexao, arquivo.stem, arquivo.with_suffix(".json"), conferir_tabela(arquivo),
        (*caminho, arquivo),
    )  # fmt: skip


def linhagem_da_linha(
    conexao: sa.Connection,
    pasta: Path,
    linha: pd.Series,
    formato: Formato = DEMONSTRACOES,
) -> Linhagem:
    """O caminho de uma linha da base "por ano" até os originais, a coleta e a versão do código.

    `formato`: o da tabela da pasta (a DMPL tem a coluna do patrimônio no fato e no hash).
    """
    ano = _ano_da_linha(linha)
    confere = conferir_pasta(pasta, formato).get(ano, False)
    return _linhagem(conexao, ano, pasta / f"{ano}.json", confere)


def linhagem_da_tabela(conexao: sa.Connection, arquivo: Path) -> Linhagem:
    """O mesmo para uma tabela gravada por `base/parquet.py::gravar_tabela` (todas as linhas),
    seguindo as tabelas de entrada das derivadas até os originais."""
    return _linhagem_da_tabela(conexao, arquivo, ())
