"""Monta a amostra integrada (ADR 0058; plano `2026-10-16-amostra-integrada-v1.md`): o painel companhia ×
fim de mês "como era na data", das tabelas que já estão na base (não baixa nada).

    python -m scripts.montar_amostra                     (a base do acervo, até o último mês fechado)
    python -m scripts.montar_amostra --base <pasta> --fim 2026-09-30

Grava `<base>/amostra/v1/painel/<ano>.parquet` com manifesto, versões e linhagem: as origens são as
tabelas de entrada (e o cadastro da CVM, um original), e a linhagem segue delas até os originais. Blocos:
universo (quem está, desde quando e com que tickers), demonstrações (balanço e resultado como eram) e
eventos e governança (documentos, insolvência, auditor, negociações, conselho, remuneração e ofertas);
os outros entram um por PR. Uma tabela de entrada que ainda não existe na base fica vazia (o bloco
continua, com as colunas dela vazias). Recusa rodar sem a versão do código (exigência 13 da ADR 0055).
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base.amostra import demonstracoes, eventos, universo
from base.cadastro import ler_cadastro
from base.parquet import gravar_com_versoes, origem_de_tabela
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.montar_amostra")
PASTA = Path("amostra") / "v1" / "painel"
FONTE_DO_CADASTRO, ARQUIVO_DO_CADASTRO = "cvm-cadastros", "cad_cia_aberta.csv"
ROTULOS_ATRASO = Path("rotulos_atraso") / "rotulos_atraso.parquet"
TICKERS = Path("fca") / "tickers.parquet"
DEMONSTRACOES = "demonstracoes"
CONTAS = sorted(
    {c for _, contas, _ in demonstracoes.INDICADORES.values() for c in contas}
)
ORDEM = ["cnpj", "data"]


def ultimo_mes_fechado(hoje: pd.Timestamp) -> pd.Timestamp:
    """O último dia do mês anterior ao de `hoje` (em 01/10 e em 31/10, 30/09)."""
    primeiro_dia = pd.Timestamp(year=hoje.year, month=hoje.month, day=1)
    return pd.Timestamp(primeiro_dia - pd.Timedelta(days=1))


def _cadastro(conexao: sa.Connection) -> tuple[pd.DataFrame, dict[str, str]]:
    for original in originais_mais_recentes(conexao, FONTE_DO_CADASTRO):
        if original.url.rsplit("/", 1)[-1] != ARQUIVO_DO_CADASTRO:
            continue
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo is not None:
            return ler_cadastro(conteudo), {
                "url": original.url,
                "sha256": original.sha256,
            }
    raise FileNotFoundError(f"sem o {ARQUIVO_DO_CADASTRO} no acervo")


def _demonstracoes(base: Path) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """Só as contas dos indicadores, ano a ano (a base inteira não precisa ficar na memória)."""
    arquivos = sorted(
        p for p in (base / DEMONSTRACOES).glob("*.parquet") if p.stem.isdigit()
    )
    partes = [pd.read_parquet(p, filters=[("conta", "in", CONTAS)]) for p in arquivos]
    tabela = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    return tabela, [origem_de_tabela(p, base) for p in arquivos]


# entrada do bloco de eventos -> (pasta ou arquivo na base, colunas lidas)
TABELAS_DOS_EVENTOS = {
    "eventos": ("eventos", ["cnpj", "tema", "rotulo", "publicado_em"]),
    "insolvencia": ("insolvencia", ["cnpj", "rotulo", "conhecido_em"]),
    "auditores": ("auditores", ["cnpj", "conhecido_em", "inicio", "auditor_id"]),
    "trocas_de_auditor": ("trocas_de_auditor", ["cnpj", "conhecido_em", "efetiva_em"]),
    "negociacoes": ("negociacoes", ["cnpj", "cargo", "operacao", "data", "entregue_em", "valor"]),
    "fre_conselho": ("fre_conselho", ["cnpj", "id_documento", "conhecido_em", "orgao", "membros",
                                      "independentes"]),
    "fre_remuneracao": ("fre_remuneracao", ["cnpj", "id_documento", "conhecido_em", "orgao",
                                            "fim_do_exercicio", "total_do_orgao"]),
    "ofertas": ("ofertas", ["cnpj_emissor", "anunciada_em"]),
}  # fmt: skip


def _tabelas_da_pasta(
    base: Path, pasta: str, colunas: list[str]
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """Os Parquets atuais da pasta (sem as versões guardadas), só com as colunas pedidas."""
    arquivos = sorted(p for p in (base / pasta).glob("*.parquet") if ".v" not in p.stem)
    partes = [pd.read_parquet(p, columns=colunas) for p in arquivos]
    tabela = (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=colunas)
    )
    return tabela, [origem_de_tabela(p, base) for p in arquivos]


def _eventos(base: Path) -> tuple[dict[str, pd.DataFrame], list[dict[str, str]]]:
    tabelas, origens = {}, []
    for nome, (pasta, colunas) in TABELAS_DOS_EVENTOS.items():
        tabelas[nome], de_onde = _tabelas_da_pasta(base, pasta, colunas)
        origens += de_onde
    return tabelas, origens


def entradas_e_origens(
    conexao: sa.Connection, base: Path
) -> tuple[dict[str, pd.DataFrame], list[dict[str, str]]]:
    """As entradas do painel (já preparadas) e as origens para o manifesto."""
    cadastro, origem_do_cadastro = _cadastro(conexao)
    entregas = pd.read_parquet(
        base / ROTULOS_ATRASO, columns=["cnpj", "primeira_entrega"]
    )
    tickers = pd.read_parquet(base / TICKERS)
    tabela, origens_das_demonstracoes = _demonstracoes(base)
    tabelas_dos_eventos, origens_dos_eventos = _eventos(base)
    origens = [
        origem_do_cadastro,
        origem_de_tabela(base / ROTULOS_ATRASO, base),
        origem_de_tabela(base / TICKERS, base),
        *origens_das_demonstracoes,
        *origens_dos_eventos,
    ]
    entradas = (
        universo.preparar(cadastro, entregas, tickers)
        | {"demonstracoes": tabela}
        | tabelas_dos_eventos
    )
    return entradas, origens


def montar_painel(entradas: dict[str, pd.DataFrame], fim: pd.Timestamp) -> pd.DataFrame:
    """O universo e, em cada linha dele, as colunas de cada bloco."""
    painel = universo.montar(entradas, fim)
    if not entradas["demonstracoes"].empty:
        colunas = demonstracoes.montar(entradas, painel)
        painel = painel.merge(colunas, on=["cnpj", "data"], how="left")
    colunas = eventos.montar(entradas, painel)
    return painel.merge(colunas, on=["cnpj", "data"], how="left")


def gravar(painel: pd.DataFrame, base: Path, origens: list[dict[str, str]]) -> None:
    for ano, do_ano in painel.groupby(painel["data"].dt.year):
        resultado = gravar_com_versoes(
            lambda t=do_ano: t.reset_index(drop=True),
            base / PASTA / str(ano),
            origens,
            ORDEM,
        )
        log.info("amostra %s: %s (%s linhas)", ano, resultado, len(do_ano))


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--base", type=Path, default=None)
    argumentos.add_argument("--fim", type=pd.Timestamp, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    raiz = acervo.pasta_do_acervo()
    base = opcoes.base or (None if raiz is None else raiz / "base")
    if base is None:
        argumentos.error("acervo desligado: informe --base")
    fim = opcoes.fim or ultimo_mes_fechado(pd.Timestamp.now())
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            entradas, origens = entradas_e_origens(conexao, base)
    finally:
        motor.dispose()
    painel = montar_painel(entradas, fim)
    log.info(
        "universo: %s companhias, %s linhas, %s com ticker",
        painel["cnpj"].nunique(), len(painel), int(painel["com_ticker_na_data"].sum()),
    )  # fmt: skip
    gravar(painel, base, origens)
    return 0


if __name__ == "__main__":
    sys.exit(main())
