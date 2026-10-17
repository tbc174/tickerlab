"""Carga dos fatos dos posts das assessorias de M&A (ADR 0082, série 5 do plano de M&A, passo 2;
`base/ma_assessorias.py`).

    python -m scripts.carga_ma_assessorias                     (a base do acervo)
    python -m scripts.carga_ma_assessorias --base <pasta>

Lê as páginas que o arquivista já guardou (fonte `assessoria-<id>`; não baixa nada) e grava uma linha
por negócio em `<base>/ma/assessorias/<id>.parquet`, com manifesto e versões (`gravar_com_versoes`:
com as mesmas páginas, nada é lido de novo). No fim, imprime quantos negócios saíram com alvo e
comprador, com tipo e sem tipo, para a conferência. Recusa rodar sem a versão do código (exigência 13
da ADR 0055). O esquema `ma` no banco só vem na série 1 do plano: até lá, Parquet no servidor de casa.

Depois liga as partes à rede e junta as duplicatas (passo 3, `base/ma_ligacao.py`): grava
`<base>/ma/ligacao/partes.parquet` e `negocios.parquet`. Lê a rede (`<base>/rede`) e o CNPJ da Receita do
mês mais recente guardado; sem a rede, não liga. Com as mesmas entradas, nada é lido de novo.

Por fim, as datas e a confirmação (passo 4, `base/ma_datas.py`): grava `<base>/ma/datas/negocios.parquet`
com o `conhecido_em` de cada página (a prova mais antiga: a cópia no Wayback que o arquivista guardou
na fonte `wayback-<id>`, os sócios PJ do CNPJ do mês mais recente ou a nossa coleta). Sem a ligação, não
data.

E a régua do middle market (passo 5, `base/ma_regua.py`): grava `<base>/ma/regua/negocios.parquet` com a
receita anual da alvo de antes do negócio (a DRE da CVM já montada em `<base>/demonstracoes` e as lidas à
mão em `base/conferidas/ma_receitas.csv`) e o porte do CNPJ do mês mais recente. Sem as datas, não mede.
"""

import argparse
import hashlib
import logging
import re
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base import ma_assessorias, ma_datas, ma_ligacao, ma_regua
from base.arquivo.assessorias import ASSESSORIAS, Assessoria
from base.parquet import (
    GRAVADO,
    arquivos_atuais,
    gravar_com_versoes,
    ler_tabela,
    origem_de_tabela,
)
from base.rede.ids import ids_fixados
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_ma_assessorias")
ORDEM = ["assessoria", "url"]
ORDEM_DAS_PARTES = ["assessoria", "url", "nome"]
FONTE_DA_RECEITA = "rfb-cnpj"
ARQUIVO_DA_RECEITA = re.compile(
    r"/(\d{4}-\d{2})/(Empresas|Estabelecimentos|Simples|Socios)\d*\.zip$"
)
DA_LIGACAO = ("Empresas", "Estabelecimentos", "Simples")
SOCIOS = "Socios"
EMPRESAS = "Empresas"
DA_REGUA = [("demonstracao", "==", "DRE"), ("conta", "==", "3.01")]
Origem = dict[str, str]


def montar(conexao: sa.Connection, assessoria: Assessoria) -> pd.DataFrame:
    linhas = []
    for guardada in originais_mais_recentes(conexao, f"assessoria-{assessoria.id}"):
        conteudo = acervo.ler_original(guardada.caminho_do_original)
        if conteudo is None:
            raise FileNotFoundError(f"original fora do acervo: {guardada.url}")
        linhas.append(
            ma_assessorias.extrair(
                conteudo,
                guardada.url,
                guardada.sha256,
                guardada.baixado_em,
                assessoria.id,
            )
        )
    return ma_assessorias.tabela(linhas)


def resumo(tabela: pd.DataFrame) -> str:
    """Os números da conferência: quantos negócios, com alvo e comprador, com tipo e sem."""
    com_partes = (tabela["alvo"].notna() & tabela["comprador"].notna()).sum()
    sem_tipo = (tabela["tipo"] == ma_assessorias.SEM_TIPO).sum()
    por_tipo = ", ".join(f"{t} {n}" for t, n in tabela["tipo"].value_counts().items())
    return (
        f"{len(tabela)} negócios; {com_partes} com alvo e comprador; "
        f"{len(tabela) - sem_tipo} com tipo, {sem_tipo} {ma_assessorias.SEM_TIPO} ({por_tipo})"
    )


def carregar(conexao: sa.Connection, base: Path) -> None:
    for assessoria in ASSESSORIAS:
        fonte = f"assessoria-{assessoria.id}"
        guardadas = originais_mais_recentes(conexao, fonte)
        if not guardadas:
            log.warning("%s: nenhuma página guardada", fonte)
            continue
        origens = [{"url": g.url, "sha256": g.sha256} for g in guardadas]
        destino = base / "ma" / "assessorias" / assessoria.id
        resultado = gravar_com_versoes(
            lambda a=assessoria: montar(conexao, a), destino, origens, ORDEM
        )
        log.info("%s: %s", fonte, resultado)
        if resultado == GRAVADO:
            print(f"{fonte}: {resumo(ler_tabela(destino.with_suffix('.parquet')))}")


def _do_mes_mais_recente(conexao: sa.Connection) -> list[tuple[str, Path, sa.Row]]:
    """(tipo, caminho, coleta) dos ZIPs da Receita do mês mais recente guardado, em ordem."""
    pasta = acervo.pasta_do_acervo()
    achados = []
    for original in originais_mais_recentes(conexao, FONTE_DA_RECEITA):
        casou = ARQUIVO_DA_RECEITA.search(original.url)
        if casou and pasta and (pasta / original.caminho_do_original).is_file():
            achados.append((casou.group(1), casou.group(2), original))
    if not achados or pasta is None:
        return []
    mes = max(m for m, _, _ in achados)
    do_mes = sorted(
        ((t, o) for m, t, o in achados if m == mes), key=lambda par: par[1].url
    )
    return [(t, pasta / o.caminho_do_original, o) for t, o in do_mes]


def _receita(conexao: sa.Connection) -> tuple[dict[str, list[Path]], list[Origem]]:
    """Os `Empresas*`, `Estabelecimentos*` e `Simples` do mês mais recente guardado, e as origens."""
    arquivos: dict[str, list[Path]] = {tipo: [] for tipo in DA_LIGACAO}
    do_mes = [a for a in _do_mes_mais_recente(conexao) if a[0] in DA_LIGACAO]
    for tipo, caminho, _ in do_mes:
        arquivos[tipo].append(caminho)
    return arquivos, [{"url": o.url, "sha256": o.sha256} for _, _, o in do_mes]


def _consultas_do_wayback(conexao: sa.Connection) -> list[sa.Row]:
    """As consultas ao Wayback guardadas (a mais recente de cada página), de todas as assessorias."""
    return [
        o
        for a in ASSESSORIAS
        for o in originais_mais_recentes(conexao, f"wayback-{a.id}")
    ]


def _primeira_copia(consultas: list[sa.Row]) -> pd.Series:
    """página → a primeira cópia no Wayback: quando o post ficou público (regra 2 da ligação)."""
    copias = ma_datas.copias_do_wayback((_guardado(o), _conteudo(o)) for o in consultas)
    return copias.dropna(subset=["wayback_em"]).set_index("url")["wayback_em"]


def ligar(conexao: sa.Connection, base: Path) -> None:
    """Partes ligadas à rede e duplicatas juntas (`base/ma_ligacao.py`), se a rede já foi montada."""
    rede = base / "rede"
    entidades, identificadores = (
        rede / "entidades.parquet",
        rede / "identificadores.parquet",
    )
    tabelas = arquivos_atuais(base / "ma" / "assessorias")
    if not (entidades.exists() and identificadores.exists()) or not tabelas:
        log.warning("ligação das partes: sem a rede ou sem negócios; fica para depois")
        return
    receita, da_receita = _receita(conexao)
    consultas = _consultas_do_wayback(conexao)
    origens = (
        [origem_de_tabela(a, base) for a in [*tabelas, entidades, identificadores]]
        + da_receita
        + [{"url": o.url, "sha256": o.sha256} for o in consultas]
    )
    montadas: dict[str, pd.DataFrame] = {}

    def montar_tudo() -> dict[str, pd.DataFrame]:
        if not montadas:
            negocios = pd.concat([ler_tabela(t) for t in tabelas], ignore_index=True)
            partes = ma_ligacao.partes(negocios)
            achados = ma_ligacao.ler_receita(
                receita["Empresas"],
                receita["Estabelecimentos"],
                receita["Simples"],
                set(partes["nome_normalizado"].dropna()),
            )
            ligadas = ma_ligacao.ligar(
                partes,
                ma_ligacao.nomes_da_rede(
                    ler_tabela(entidades), ler_tabela(identificadores)
                ),
                achados,
                ids_fixados(),
                publico_em=_primeira_copia(consultas),
            )
            montadas.update(
                negocios=ma_ligacao.negocios(negocios, ligadas),
                partes=ligadas,
                ma=negocios,
            )
            print(
                "ligação: " + ma_ligacao.resumo(negocios, ligadas, montadas["negocios"])
            )
        return montadas

    destino = base / "ma" / "ligacao"
    for nome, ordem in (("partes", ORDEM_DAS_PARTES), ("negocios", ORDEM)):
        resultado = gravar_com_versoes(
            lambda n=nome: montar_tudo()[n], destino / nome, origens, ordem
        )
        log.info("ligação, %s: %s", nome, resultado)


def _guardado(original: sa.Row) -> ma_datas.Guardado:
    return ma_datas.Guardado(original.url, original.sha256, original.baixado_em)


def _conteudo(original: sa.Row) -> bytes:
    conteudo = acervo.ler_original(original.caminho_do_original)
    if conteudo is None:
        raise FileNotFoundError(f"original fora do acervo: {original.url}")
    return conteudo


def datar(conexao: sa.Connection, base: Path) -> None:
    """O `conhecido_em` e a confirmação de cada página (`base/ma_datas.py`), se a ligação já existe."""
    ligacao = base / "ma" / "ligacao"
    partes, negocios = ligacao / "partes.parquet", ligacao / "negocios.parquet"
    tabelas = arquivos_atuais(base / "ma" / "assessorias")
    if not (partes.exists() and negocios.exists()) or not tabelas:
        log.warning("datas dos negócios: sem a ligação; fica para depois")
        return
    consultas = _consultas_do_wayback(conexao)
    socios = [(c, o) for t, c, o in _do_mes_mais_recente(conexao) if t == SOCIOS]
    origens = [origem_de_tabela(t, base) for t in [*tabelas, partes, negocios]] + [
        {"url": o.url, "sha256": o.sha256}
        for o in [*consultas, *(o for _, o in socios)]
    ]

    def montar_datas() -> pd.DataFrame:
        ligadas = ler_tabela(partes)
        alvos = set(ligadas.loc[ligadas["papel"] == "alvo", "cnpj_raiz"].dropna())
        saida = ma_datas.datar(
            pd.concat([ler_tabela(t) for t in tabelas], ignore_index=True),
            ligadas,
            ler_tabela(negocios),
            ma_datas.copias_do_wayback((_guardado(o), _conteudo(o)) for o in consultas),
            ma_datas.ler_socios_pj([(c, _guardado(o)) for c, o in socios], alvos),
        )
        print("datas: " + ma_datas.resumo(saida))
        return saida

    resultado = gravar_com_versoes(
        montar_datas, base / "ma" / "datas" / "negocios", origens, ORDEM
    )
    log.info("datas dos negócios: %s", resultado)


def medir_regua(conexao: sa.Connection, base: Path) -> None:
    """A régua do middle market de cada página (`base/ma_regua.py`), se as datas já existem."""
    datas = base / "ma" / "datas" / "negocios.parquet"
    partes = base / "ma" / "ligacao" / "partes.parquet"
    if not (datas.exists() and partes.exists()):
        log.warning("régua do middle market: sem as datas; fica para depois")
        return
    demonstracoes = arquivos_atuais(base / "demonstracoes")
    empresas = [(c, o) for t, c, o in _do_mes_mais_recente(conexao) if t == EMPRESAS]
    conferidas = ma_regua.CONFERIDAS
    origens = (
        [origem_de_tabela(t, base) for t in [datas, partes, *demonstracoes]]
        + [{"url": o.url, "sha256": o.sha256} for _, o in empresas]
        + [
            {
                "url": f"base/conferidas/{conferidas.name}",
                "sha256": hashlib.sha256(conferidas.read_bytes()).hexdigest(),
            }
        ]
    )

    def montar_regua() -> pd.DataFrame:
        ligadas = ler_tabela(partes)
        alvos = set(ligadas.loc[ligadas["papel"] == "alvo", "cnpj_raiz"].dropna())
        dre = [pd.read_parquet(t, filters=DA_REGUA) for t in demonstracoes]
        receitas = [ma_regua.receitas_conferidas()]
        if dre:
            receitas.append(
                ma_regua.receitas_da_cvm(pd.concat(dre, ignore_index=True), alvos)
            )
        saida = ma_regua.medir(
            ler_tabela(datas),
            ligadas,
            pd.concat(receitas, ignore_index=True),
            ma_regua.portes_do_cnpj([(c, _guardado(o)) for c, o in empresas], alvos),
        )
        print("régua: " + ma_regua.resumo(saida))
        return saida

    resultado = gravar_com_versoes(
        montar_regua, base / "ma" / "regua" / "negocios", origens, ORDEM
    )
    log.info("régua do middle market: %s", resultado)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--base", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    raiz = acervo.pasta_do_acervo()
    base = opcoes.base or (None if raiz is None else raiz / "base")
    if base is None:
        argumentos.error("acervo desligado: informe --base")
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            carregar(conexao, base)
            ligar(conexao, base)
            datar(conexao, base)
            medir_regua(conexao, base)
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
