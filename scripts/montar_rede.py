"""Monta as tabelas `entidades` e `identificadores` da rede (ADR 0077; plano da série, PR 2).

    python -m scripts.montar_rede                  (a base do acervo)
    python -m scripts.montar_rede --pasta <base>    (a pasta com fca/, controladas/, fidc/...)
    python -m scripts.montar_rede --amostra <csv>   (e grava a amostra da tarefa 2.7 para conferir)
    python -m scripts.montar_rede --saida <pasta>   (ensaio: grava fora da base)

Lê o que a base já tem (nenhuma coleta nova): as tabelas `fca/tickers` e `fca/emissores`,
`controladas/<ano>`, `empresa_serie`, `fidc/cadastro/cad_fi` e `bcb/ifdata/cadastro/<AAAAMM>` (sem as
versões `.v<N>`), as tabelas conferidas `emissores_antigos.csv` e `entidades.csv`, e três originais do
acervo: o `cad_cia_aberta.csv` mais recente da CVM, as páginas do GLEIF da cópia mais nova e, da
Receita, só duas colunas do mês mais recente (natureza jurídica e opção pelo MEI das raízes da rede).

Grava `rede/entidades` e `rede/identificadores` com manifesto e versões
(`base/parquet.py::gravar_com_versoes`): com as mesmas origens, nada é lido nem regravado. Mostra
quantas linhas e quantos conflitos por regra e fonte. Recusa rodar sem a versão do código (exigência 13
da ADR 0055).
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base import gleif, receita_natureza
from base.cadastro import ler_cadastro
from base.parquet import (
    arquivos_atuais,
    gravar_com_versoes,
    ler_tabela,
    origem_de_tabela,
)
from base.rede import amostra, ids, montar
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import obter_engine
from src.banco.modelo import coletas
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.montar_rede")
PASTA_DA_REDE = "rede"
# do pacote `base`, não do script: na imagem o script roda pela entrada padrão (`python - <`)
CONFERIDAS = ids.TABELA_CONFERIDA.parent
FONTE_DO_CADASTRO, ARQUIVO_DO_CADASTRO = "cvm-cadastros", "cad_cia_aberta.csv"
FONTE_DO_GLEIF, FONTE_DA_RECEITA = "gleif-br", "rfb-cnpj"
ARQUIVO_DA_RECEITA = re.compile(r"/(\d{4}-\d{2})/(Empresas\d+|Simples)\.zip$")
ORDEM_DAS_ENTIDADES = ["id_entidade"]
ORDEM_DOS_IDENTIFICADORES = ["id_entidade", "sistema", "valor", "desde"]
Origem = dict[str, str]


@dataclass
class Resumo:
    entidades: int
    identificadores: int
    conflitos: pd.DataFrame
    gravadas: dict[str, str]


def _origem_da_conferida(nome: str) -> Origem:
    conteudo = (CONFERIDAS / nome).read_bytes()
    return {
        "url": f"base/conferidas/{nome}",
        "sha256": hashlib.sha256(conteudo).hexdigest(),
    }


def _origens_das_linhas(conexao: sa.Connection, tabela: pd.DataFrame) -> list[Origem]:
    """Tabela sem manifesto (as históricas da série B, como `controladas`): a origem está em cada
    linha (`origem_sha256`); o endereço vem do registro de coletas ou da tabela conferida."""
    shas = sorted(set(tabela["origem_sha256"].dropna()))
    conferidas = {
        hashlib.sha256(c.read_bytes()).hexdigest(): f"base/conferidas/{c.name}"
        for c in CONFERIDAS.glob("*.csv")
    }
    registradas = dict(
        conexao.execute(
            sa.select(coletas.c.sha256, sa.func.min(coletas.c.url))
            .where(coletas.c.sha256.in_(shas), coletas.c.situacao == "ok")
            .group_by(coletas.c.sha256)
        ).all()
    )
    return [
        {
            "url": conferidas.get(sha) or registradas.get(sha) or f"sha256:{sha}",
            "sha256": sha,
        }
        for sha in shas
    ]


def _ler(
    arquivos: list[Path], pasta: Path, origens: list[Origem], conexao: sa.Connection
) -> pd.DataFrame:
    if not arquivos:
        return pd.DataFrame()
    tabela = pd.concat([ler_tabela(a) for a in arquivos], ignore_index=True)
    if all(a.with_suffix(".json").is_file() for a in arquivos):
        origens += [origem_de_tabela(a, pasta) for a in arquivos]
    else:
        origens += _origens_das_linhas(conexao, tabela)
    return tabela


def _uma(pasta: Path, *partes: str) -> list[Path]:
    arquivo = pasta.joinpath(*partes).with_suffix(".parquet")
    return [arquivo] if arquivo.is_file() else []


def _cadastro(conexao: sa.Connection, origens: list[Origem]) -> pd.DataFrame:
    for original in originais_mais_recentes(conexao, FONTE_DO_CADASTRO):
        if original.url.rsplit("/", 1)[-1] != ARQUIVO_DO_CADASTRO:
            continue
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo is not None:
            origens.append({"url": original.url, "sha256": original.sha256})
            return ler_cadastro(conteudo)
    return pd.DataFrame()


def _gleif(conexao: sa.Connection, origens: list[Origem]) -> pd.DataFrame:
    """As páginas da cópia mais nova do GLEIF (uma página que sumiu fica de fora)."""
    paginas = []
    for original in originais_mais_recentes(conexao, FONTE_DO_GLEIF):
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo is not None:
            paginas.append((original, conteudo))
    if not paginas:
        return pd.DataFrame()
    copia = [json.loads(c)["meta"]["goldenCopy"]["publishDate"] for _, c in paginas]
    mais_nova = max(copia)
    da_copia = [
        (o, c) for (o, c), data in zip(paginas, copia, strict=True) if data == mais_nova
    ]
    origens += [{"url": o.url, "sha256": o.sha256} for o, _ in da_copia]
    return gleif.juntar_paginas([c for _, c in da_copia])


def _receita(conexao: sa.Connection, origens: list[Origem]) -> list[tuple[str, Path]]:
    """(nome, caminho no acervo) dos `Empresas*.zip` e do `Simples.zip` do mês mais recente."""
    pasta = acervo.pasta_do_acervo()
    achados = []
    for original in originais_mais_recentes(conexao, FONTE_DA_RECEITA):
        casou = ARQUIVO_DA_RECEITA.search(original.url)
        if (
            casou
            and pasta is not None
            and (pasta / original.caminho_do_original).is_file()
        ):
            achados.append((casou.group(1), casou.group(2), original))
    if not achados:
        return []
    mes = max(m for m, _, _ in achados)
    do_mes = sorted((n, o) for m, n, o in achados if m == mes)
    origens += [{"url": o.url, "sha256": o.sha256} for _, o in do_mes]
    return [(n, pasta / o.caminho_do_original) for n, o in do_mes if pasta is not None]


def _natureza_e_mei(
    arquivos: list[tuple[str, Path]], raizes: set[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    naturezas = [
        receita_natureza.ler_naturezas(c, raizes) for n, c in arquivos if n != "Simples"
    ]
    meis = [receita_natureza.ler_mei(c, raizes) for n, c in arquivos if n == "Simples"]
    return (
        pd.concat(naturezas, ignore_index=True)
        if naturezas
        else pd.DataFrame(columns=["cnpj_basico", "natureza_juridica"]),
        pd.concat(meis, ignore_index=True)
        if meis
        else pd.DataFrame(columns=["cnpj_basico", "mei"]),
    )


def _entradas(
    conexao: sa.Connection, pasta: Path
) -> tuple[montar.Entradas, list[tuple[str, Path]], list[Origem]]:
    origens: list[Origem] = []
    entradas = montar.Entradas(
        cadastro=_cadastro(conexao, origens),
        tickers=_ler(_uma(pasta, "fca", "tickers"), pasta, origens, conexao),
        emissores=_ler(_uma(pasta, "fca", "emissores"), pasta, origens, conexao),
        emissores_antigos=pd.read_csv(
            CONFERIDAS / "emissores_antigos.csv",
            sep=";",
            dtype=str,
            keep_default_na=False,
        ).replace("", None),
        controladas=_ler(
            arquivos_atuais(pasta / "controladas"), pasta, origens, conexao
        ),
        empresa_serie=_ler(
            _uma(pasta, "empresa_serie", "empresa_serie"), pasta, origens, conexao
        ),
        fundos=_ler(_uma(pasta, "fidc", "cadastro", "cad_fi"), pasta, origens, conexao),
        ifdata=_ler(
            arquivos_atuais(pasta / "bcb" / "ifdata" / "cadastro"),
            pasta,
            origens,
            conexao,
        ),
        gleif=_gleif(conexao, origens),
    )
    origens += [
        _origem_da_conferida("emissores_antigos.csv"),
        _origem_da_conferida("entidades.csv"),
    ]
    return entradas, _receita(conexao, origens), origens


class _UmaVez:
    """A montagem roda uma vez só, e só se alguma das duas tabelas precisar (origens novas)."""

    def __init__(self, calcular: Callable[[], tuple[pd.DataFrame, ...]]) -> None:
        self._calcular = calcular
        self.resultado: tuple[pd.DataFrame, ...] | None = None

    def __call__(self) -> tuple[pd.DataFrame, ...]:
        if self.resultado is None:
            self.resultado = self._calcular()
        return self.resultado


def _linhas_gravadas(destino: Path) -> int:
    return json.loads(destino.with_suffix(".json").read_text(encoding="utf-8"))[
        "linhas"
    ]


def montar_no_acervo(
    conexao: sa.Connection, pasta: Path, saida: Path | None = None
) -> Resumo:
    """Monta e grava `entidades` e `identificadores` em `<pasta>/rede/` (ou em `saida`, no ensaio)."""
    entradas, receita, origens = _entradas(conexao, pasta)

    def calcular() -> tuple[pd.DataFrame, ...]:
        observacoes = montar.observacoes(entradas)
        naturezas, meis = _natureza_e_mei(receita, montar.raizes(observacoes))
        return montar.montar_rede(observacoes, naturezas, meis, ids.ids_fixados())

    rede = _UmaVez(calcular)
    destino = saida or pasta / PASTA_DA_REDE
    gravadas = {
        "entidades": gravar_com_versoes(
            lambda: rede()[0], destino / "entidades", origens, ORDEM_DAS_ENTIDADES
        ),
        "identificadores": gravar_com_versoes(
            lambda: rede()[1],
            destino / "identificadores",
            origens,
            ORDEM_DOS_IDENTIFICADORES,
        ),
    }
    if rede.resultado is None:  # nada mudou: as contas vêm dos manifestos
        return Resumo(
            _linhas_gravadas(destino / "entidades"),
            _linhas_gravadas(destino / "identificadores"),
            pd.DataFrame(columns=["regra", "fontes"]),
            gravadas,
        )
    entidades, identificadores, conflitos = rede.resultado
    return Resumo(len(entidades), len(identificadores), conflitos, gravadas)


def gravar_amostra(rede: Path, destino: Path) -> int:
    """A amostra da tarefa 2.7 num CSV para conferir: até 200 por regra, com o tipo e o nome da
    entidade e `do_tiago` = sim nas 20 por regra que o Tiago confere. Devolve as linhas."""
    sorteada = amostra.sortear(ler_tabela(rede / "identificadores.parquet"))
    do_tiago = amostra.para_o_tiago(sorteada)[amostra.CHAVE].assign(do_tiago="sim")
    entidades = ler_tabela(rede / "entidades.parquet")[["id_entidade", "tipo", "nome"]]
    tabela = (
        sorteada.merge(entidades, on="id_entidade", how="left")
        .merge(do_tiago, on=amostra.CHAVE, how="left")
        .fillna({"do_tiago": "nao"})
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(destino, sep=";", index=False, encoding="utf-8")
    return len(tabela)


def _conflitos_por_regra_e_fonte(conflitos: pd.DataFrame) -> str:
    if conflitos.empty:
        return "nenhum"
    contagem = conflitos.groupby(["regra", "fontes"]).size().reset_index(name="linhas")
    return "; ".join(
        f"regra {c.regra}, {c.fontes}: {c.linhas}"
        for c in contagem.itertuples(index=False)
    )


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--saida", type=Path, default=None, help="pasta do ensaio")
    argumentos.add_argument(
        "--amostra", type=Path, default=None, help="CSV da amostra a conferir"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    with obter_engine().connect() as conexao:
        resumo = montar_no_acervo(conexao, pasta, opcoes.saida)
    log.info(
        "rede: %d entidades, %d identificadores (%s); conflitos: %s",
        resumo.entidades,
        resumo.identificadores,
        ", ".join(f"{t} {g}" for t, g in resumo.gravadas.items()),
        _conflitos_por_regra_e_fonte(resumo.conflitos),
    )
    if opcoes.amostra:
        log.info(
            "amostra: %d linhas em %s",
            gravar_amostra(opcoes.saida or pasta / PASTA_DA_REDE, opcoes.amostra),
            opcoes.amostra,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
