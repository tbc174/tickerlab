"""Monta as tabelas `entidades`, `identificadores` e `ligacoes` da rede (ADR 0077; PRs 2 e 3).

    python -m scripts.montar_rede                  (a base do acervo)
    python -m scripts.montar_rede --pasta <base>    (a pasta com fca/, controladas/, fidc/...)
    python -m scripts.montar_rede --amostra <csv>   (e grava a amostra da tarefa 2.7 para conferir)
    python -m scripts.montar_rede --saida <pasta>   (ensaio: grava fora da base)

Lê o que a base já tem (nenhuma coleta nova): as tabelas `fca/tickers` e `fca/emissores`,
`controladas/<ano>`, `auditores/<ano>`, `empresa_serie`, `fidc/cadastro/cad_fi`,
`bcb/ifdata/cadastro/<AAAAMM>` e as carteiras dos fundos `cda/<ano>` (sem as versões `.v<N>`; o CDA um
ano por vez, só as colunas que a rede usa), as tabelas conferidas `emissores_antigos.csv` e `entidades.csv`, e três originais do
acervo: o `cad_cia_aberta.csv` mais recente da CVM, as páginas do GLEIF da cópia mais nova e, da
Receita, só duas colunas do mês mais recente (natureza jurídica e opção pelo MEI das raízes da rede).

Grava `rede/entidades`, `rede/identificadores` e `rede/ligacoes` com manifesto e versões
(`base/parquet.py::gravar_com_versoes`): com as mesmas origens, nada é lido nem regravado. As ligações
somam a carga nova à tabela que já existe sem apagar nada (`base/rede/ligacoes.py`), com o
`coletado_em` do registro de coletas. Mostra quantas linhas e quantos conflitos por regra e fonte.
Recusa rodar sem a versão do código (exigência 13 da ADR 0055).

Roda toda noite no servidor de casa, depois das cargas: saída 0 tudo certo; 1 alguma falha, com a
última linha `FALHAS: ...` (vai para o aviso do Kuma), como `scripts/copiar_b3_negocios.py`.
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
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
from base.rede import amostra, ids, ligacoes, ligacoes_das_fontes, montar
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
ORDEM_DAS_LIGACOES = list(ligacoes.CHAVE)
COLUNAS_DO_CDA = [
    "competencia",
    "cnpj_fundo",
    "tipo",
    "isin",
    "emissor",
    "disponivel_em",
]
FUSO = "America/Sao_Paulo"
TAMANHO_MAXIMO_DO_RESUMO = 200  # o aviso do Kuma corta mensagens longas
Origem = dict[str, str]
TabelasLidas = dict[
    str, list[str]
]  # sha256 do conteúdo da tabela → sha256 das origens dela


@dataclass
class Resumo:
    entidades: int
    identificadores: int
    conflitos: pd.DataFrame
    gravadas: dict[str, str]
    ligacoes: int = 0


class SemEntradasError(RuntimeError):
    """Nenhuma tabela de entrada na base: a montagem não grava nada (a noite avisa o Kuma)."""


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


def _manifesto(arquivo: Path) -> dict | None:
    caminho = arquivo.with_suffix(".json")
    return (
        json.loads(caminho.read_text(encoding="utf-8")) if caminho.is_file() else None
    )


def _com_origem(
    arquivo: Path, tabela: pd.DataFrame, lidas: TabelasLidas
) -> pd.DataFrame:
    """Linha sem `origem_sha256` (tabela com manifesto, como o cadastro do IF.data) leva o SHA-256
    do conteúdo da tabela: o `coletado_em` da ligação sai das origens dela no registro."""
    manifesto = _manifesto(arquivo)
    if manifesto is None:
        return tabela
    sha = manifesto["sha256_da_tabela"]
    lidas[sha] = [o["sha256"] for o in manifesto.get("origens", [])]
    if "origem_sha256" in tabela:
        return tabela
    return tabela.assign(origem_sha256=sha)


def _ler(
    arquivos: list[Path],
    pasta: Path,
    origens: list[Origem],
    conexao: sa.Connection,
    lidas: TabelasLidas,
) -> pd.DataFrame:
    if not arquivos:
        return pd.DataFrame()
    tabela = pd.concat(
        [_com_origem(a, ler_tabela(a), lidas) for a in arquivos], ignore_index=True
    )
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


@dataclass
class _Lidas:
    """O que a montagem leu: as entradas, a Receita, as carteiras e as origens de cada uma."""

    entradas: montar.Entradas
    receita: list[tuple[str, Path]]
    carteiras: list[Path]
    origens: list[Origem]
    tabelas: TabelasLidas


def _entradas(conexao: sa.Connection, pasta: Path) -> _Lidas:
    origens: list[Origem] = []
    lidas: TabelasLidas = {}

    def ler(arquivos: list[Path]) -> pd.DataFrame:
        return _ler(arquivos, pasta, origens, conexao, lidas)

    entradas = montar.Entradas(
        cadastro=_cadastro(conexao, origens),
        tickers=ler(_uma(pasta, "fca", "tickers")),
        emissores=ler(_uma(pasta, "fca", "emissores")),
        emissores_antigos=pd.read_csv(
            CONFERIDAS / "emissores_antigos.csv",
            sep=";",
            dtype=str,
            keep_default_na=False,
        ).replace("", None),
        controladas=ler(arquivos_atuais(pasta / "controladas")),
        auditores=ler(arquivos_atuais(pasta / "auditores")),
        empresa_serie=ler(_uma(pasta, "empresa_serie", "empresa_serie")),
        fundos=ler(_uma(pasta, "fidc", "cadastro", "cad_fi")),
        ifdata=ler(arquivos_atuais(pasta / "bcb" / "ifdata" / "cadastro")),
        gleif=_gleif(conexao, origens),
    )
    carteiras = arquivos_atuais(pasta / "cda")
    origens += [origem_de_tabela(a, pasta) for a in carteiras]
    origens += [
        _origem_da_conferida("emissores_antigos.csv"),
        _origem_da_conferida("entidades.csv"),
    ]
    return _Lidas(entradas, _receita(conexao, origens), carteiras, origens, lidas)


@dataclass
class _Carteiras:
    isins: pd.DataFrame
    periodos: pd.DataFrame
    ultimo_mes: int


def _carteiras(arquivos: list[Path], lidas: TabelasLidas) -> _Carteiras:
    """Os ISINs e os períodos da `detem`, um ano do CDA por vez (o CDA inteiro não cabe na memória)."""
    isins, periodos, ultimo = [], [], -1
    for arquivo in arquivos:
        ano = _com_origem(
            arquivo, pd.read_parquet(arquivo, columns=COLUNAS_DO_CDA), lidas
        )
        if ano.empty:
            continue
        isins.append(ligacoes_das_fontes.isins_das_posicoes(ano))
        periodos.append(ligacoes_das_fontes.periodos_das_posicoes(ano))
        ultimo = max(
            ultimo,
            int(ligacoes_das_fontes.mes(pd.to_datetime(ano["competencia"])).max()),
        )
    juntos = [p for p in periodos if not p.empty]
    return _Carteiras(
        ligacoes_das_fontes.juntar_isins(isins),
        ligacoes.comprimir_periodos(
            pd.concat(juntos, ignore_index=True), ["cnpj_fundo", "isin", "tipo"]
        )
        if juntos
        else pd.DataFrame(),
        ultimo,
    )


def _registro(
    conexao: sa.Connection, shas: set[str], tabelas: TabelasLidas
) -> dict[str, pd.Timestamp]:
    """SHA-256 da origem → quando a base o guardou (registro de coletas). A origem que é uma tabela
    da base vale o dia em que a última das origens dela foi guardada (antes disso a tabela não existia)."""
    originais = shas | {o for s in shas & tabelas.keys() for o in tabelas[s]}
    baixado = dict(
        conexao.execute(
            sa.select(coletas.c.sha256, sa.func.min(coletas.c.baixado_em))
            .where(coletas.c.sha256.in_(sorted(originais)), coletas.c.situacao == "ok")
            .group_by(coletas.c.sha256)
        ).all()
    )
    registro = {s: pd.Timestamp(baixado[s]) for s in shas if s in baixado}
    for sha in shas & tabelas.keys():
        datas = [pd.Timestamp(baixado[o]) for o in tabelas[sha] if o in baixado]
        if datas:
            registro[sha] = max(datas)
    return registro


def _vigente(destino: Path) -> pd.DataFrame | None:
    arquivo = destino.with_suffix(".parquet")
    return ler_tabela(arquivo) if arquivo.is_file() else None


def _hoje() -> pd.Timestamp:
    return pd.Timestamp.now(tz=FUSO).tz_localize(None).normalize()


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


# o que não vem da pasta da base: os originais do acervo, a tabela conferida do repositório e os ISINs
# (montados depois, das carteiras)
FORA_DA_PASTA = ("cadastro", "gleif", "emissores_antigos", "isins")


def _sem_entradas(lidas: _Lidas) -> bool:
    """Nenhuma tabela da base na pasta (pasta errada, base que não montou): nada a gravar."""
    return not lidas.carteiras and all(
        tabela.empty
        for nome, tabela in vars(lidas.entradas).items()
        if nome not in FORA_DA_PASTA
    )


def montar_no_acervo(
    conexao: sa.Connection,
    pasta: Path,
    saida: Path | None = None,
    hoje: pd.Timestamp | None = None,
) -> Resumo:
    """Monta e grava `entidades`, `identificadores` e `ligacoes` em `<pasta>/rede/` (ou em `saida`,
    no ensaio). `hoje` é o dia da carga (o fim das ligações que somem da fonte)."""
    lidas = _entradas(conexao, pasta)
    if _sem_entradas(lidas):
        raise SemEntradasError(f"nenhuma tabela de entrada em {pasta}")
    destino = saida or pasta / PASTA_DA_REDE

    def calcular() -> tuple[pd.DataFrame, ...]:
        carteiras = _carteiras(lidas.carteiras, lidas.tabelas)
        entradas = replace(lidas.entradas, isins=carteiras.isins)
        observacoes = montar.observacoes(entradas)
        naturezas, meis = _natureza_e_mei(lidas.receita, montar.raizes(observacoes))
        entidades, identificadores, conflitos = montar.montar_rede(
            observacoes, naturezas, meis, ids.ids_fixados()
        )
        nova = montar.montar_ligacoes(
            entradas, identificadores, carteiras.periodos, carteiras.ultimo_mes
        )
        shas = set(nova["origem_sha256"].dropna())
        nova = ligacoes.com_coletado_em(nova, _registro(conexao, shas, lidas.tabelas))
        return entidades, identificadores, conflitos, nova

    rede = _UmaVez(calcular)
    origens = lidas.origens
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
        "ligacoes": gravar_com_versoes(
            lambda: ligacoes.juntar_com_a_vigente(
                rede()[3], _vigente(destino / "ligacoes"), hoje or _hoje()
            ),
            destino / "ligacoes",
            origens,
            ORDEM_DAS_LIGACOES,
        ),
    }
    contagem = {t: _linhas_gravadas(destino / t) for t in gravadas}
    conflitos = (
        rede.resultado[2]
        if rede.resultado is not None
        else pd.DataFrame(
            columns=["regra", "fontes"]
        )  # nada mudou: as contas vêm dos manifestos
    )
    return Resumo(
        contagem["entidades"],
        contagem["identificadores"],
        conflitos,
        gravadas,
        contagem["ligacoes"],
    )


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


def _avisar(problemas: list[str]) -> int:
    linha = "FALHAS: rede: " + "; ".join(problemas)
    print(linha[:TAMANHO_MAXIMO_DO_RESUMO])
    return 1


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
    try:
        with obter_engine().connect() as conexao:
            resumo = montar_no_acervo(conexao, pasta, opcoes.saida)
    except Exception as erro:  # a noite não para em silêncio: o Kuma recebe o motivo
        log.exception("a montagem da rede falhou")
        return _avisar([f"{type(erro).__name__}: {erro}"])
    log.info(
        "rede: %d entidades, %d identificadores, %d ligações (%s); conflitos: %s",
        resumo.entidades,
        resumo.identificadores,
        resumo.ligacoes,
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
