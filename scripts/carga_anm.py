"""Carga da ANM para a base: CFEM (arrecadação), SIGBM (barragens) e Anuário Mineral (AMB) (linha 657).

    python -m scripts.carga_anm                                  (grava no acervo: as 2 faixas mais novas do CFEM)
    python -m scripts.carga_anm --faixa 2017_2021 --pasta /tmp/base --forcar
    python -m scripts.carga_anm --so sigbm --so amb

Lê os CSV de https://dadosabertos.anm.gov.br (`base/anm.py`) e grava, com manifesto e versões
(`base/parquet.py::gravar_com_versoes`):
- `anm_cfem_arrecadacao/<faixa>.parquet`: um arquivo por faixa de anos da ANM (`2022_2026`...), só pessoa
  jurídica com CNPJ completo (pessoa física e documento mascarado são descartados e contados no log);
- `anm_sigbm_barragens/barragens.parquet`: uma linha por barragem, com a categoria de risco e o dano potencial
  como a ANM declarou;
- `anm_amb_producao_bruta`, `anm_amb_producao_beneficiada` e `anm_amb_agua_mineral` (`atual.parquet`): o
  Anuário, série setorial sem CNPJ.

**Sem olhar o futuro:** o CFEM traz a data de criação da linha (vira `disponivel_em`). SIGBM e AMB são
sobrescritos pela ANM, sem histórico: a data de disponibilidade é a da coleta, e a linha que não mudou entre
duas coletas mantém a data da primeira (olhar de novo não empurra o passado para frente).

Ritmo mensal: o app não depende dela; o servidor de casa roda uma vez por mês. Licença da ANM não declarada:
a confirmar, só uso interno (ADR 0102, Emenda 2); nada é perguntado à fonte. Recusa rodar sem a versão do
código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 se alguma tabela falhou.
"""

import argparse
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from base import anm
from base.parquet import gravar_com_versoes, ler_tabela
from src import acervo, rede
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_anm")
SITE = "https://dadosabertos.anm.gov.br"
URL_CFEM = SITE + "/CFEM/CFEM_Arrecadacao_{faixa}.csv"
URL_SIGBM = SITE + "/SIGBM/Barragens.csv"
URL_AMB = SITE + "/AMB/{nome}.csv"
TEMPO_LIMITE = 300  # o maior arquivo do CFEM tem ~57 MB
ANOS_POR_FAIXA = 5
PRIMEIRA_FAIXA = 2002  # as faixas do CFEM começam em 2002 e andam de 5 em 5 anos
FAIXAS_PADRAO = (
    2  # a faixa do ano de `hoje` e a anterior: as mais antigas quase não mudam
)
SEPARADOR = "\x1f"

Leitor = Callable[[bytes, date], pd.DataFrame]


@dataclass(frozen=True)
class Tabela:
    """Uma tabela da carga: de onde vem, como se lê e onde se grava."""

    grupo: str
    nome: str
    fonte: str
    url: str
    leitor: Leitor
    ordem: tuple[str, ...]


TABELAS_FIXAS = (
    Tabela("sigbm", "anm_sigbm_barragens/barragens", anm.FONTE_SIGBM, URL_SIGBM,
           anm.ler_sigbm, ("id",)),
    Tabela("amb", "anm_amb_producao_bruta/atual", anm.FONTE_AMB_BRUTA,
           URL_AMB.format(nome="Producao_Bruta"), anm.ler_amb_producao_bruta,
           tuple(anm.CHAVE_AMB_COM_INDICACAO)),
    Tabela("amb", "anm_amb_producao_beneficiada/atual", anm.FONTE_AMB_BENEFICIADA,
           URL_AMB.format(nome="Producao_Beneficiada"), anm.ler_amb_producao_beneficiada,
           tuple(anm.CHAVE_AMB_COM_INDICACAO)),
    Tabela("amb", "anm_amb_agua_mineral/atual", anm.FONTE_AMB_AGUA,
           URL_AMB.format(nome="Agua_Mineral_Producao"), anm.ler_amb_agua_mineral,
           tuple(anm.CHAVE_AMB_AGUA)),
)  # fmt: skip
ORDEM_DO_CFEM = (
    "ano",
    "mes",
    "processo",
    "ano_processo",
    "cnpj",
    "substancia",
    "municipio",
    "criado_em",
)


def faixa_do_ano(ano: int) -> str:
    """A faixa de anos do CFEM que contém `ano` (2026 → "2022_2026"; 2005 → "2002_2006")."""
    inicio = PRIMEIRA_FAIXA + (ano - PRIMEIRA_FAIXA) // ANOS_POR_FAIXA * ANOS_POR_FAIXA
    return f"{inicio}_{inicio + ANOS_POR_FAIXA - 1}"


def faixas_recentes(hoje: date, quantas: int = FAIXAS_PADRAO) -> list[str]:
    """As `quantas` faixas mais novas até o ano de `hoje`, da mais antiga à mais nova."""
    return [
        faixa_do_ano(hoje.year - ANOS_POR_FAIXA * passo)
        for passo in reversed(range(quantas))
    ]


def tabela_do_cfem(faixa: str) -> Tabela:
    return Tabela("cfem", f"anm_cfem_arrecadacao/{faixa}", anm.FONTE_CFEM, URL_CFEM.format(faixa=faixa),
                  anm.ler_cfem, ORDEM_DO_CFEM)  # fmt: skip


def baixar(url: str) -> bytes:
    """O arquivo da ANM, pelo agente do TickerLab."""
    resposta = rede.get_com_agente(url, timeout=TEMPO_LIMITE)
    resposta.raise_for_status()
    return resposta.content


def _linha_como_texto(tabela: pd.DataFrame, colunas: list[str]) -> pd.Series:
    linhas = [
        SEPARADOR.join(map(str, valores))
        for valores in tabela[colunas].itertuples(index=False)
    ]
    return pd.Series(linhas, index=tabela.index)


def manter_a_data_da_primeira_coleta(
    nova: pd.DataFrame, anterior: pd.DataFrame
) -> pd.DataFrame:
    """A linha igual à da coleta anterior (fora o `disponivel_em`) conserva a data dela."""
    if anterior.empty or nova.empty:
        return nova
    colunas = [c for c in nova.columns if c != "disponivel_em"]
    antigas = pd.Series(
        anterior["disponivel_em"].to_numpy(), index=_linha_como_texto(anterior, colunas)
    )
    antigas = antigas.groupby(level=0).min()
    herdadas = _linha_como_texto(nova, colunas).map(antigas)
    resultado = nova.copy()
    resultado["disponivel_em"] = pd.to_datetime(herdadas.fillna(nova["disponivel_em"]))
    return resultado


def carregar(
    tabela: Tabela,
    saida: Path,
    coletado_em: date,
    baixar_arquivo: Callable[[str], bytes] = baixar,
    forcar: bool = False,
) -> str:
    """Baixa, lê e grava uma tabela; devolve `GRAVADO` ou `IGUAL`."""
    conteudo = baixar_arquivo(tabela.url)
    origem = {"url": tabela.url, "sha256": hashlib.sha256(conteudo).hexdigest()}
    destino = saida / tabela.nome
    arquivo = destino.with_suffix(".parquet")

    def montar() -> pd.DataFrame:
        lida = tabela.leitor(conteudo, coletado_em)
        if lida.attrs.get("descartadas"):
            log.info(
                "%s: %d linhas sem CNPJ completo descartadas",
                tabela.fonte,
                lida.attrs["descartadas"],
            )
        if tabela.grupo == "cfem" or not arquivo.exists():
            return lida
        return manter_a_data_da_primeira_coleta(lida, ler_tabela(arquivo))

    return gravar_com_versoes(
        montar, destino, [origem], list(tabela.ordem), forcar=forcar
    )


def tabelas_pedidas(
    faixas: list[str], so: list[str] | None, hoje: date
) -> list[Tabela]:
    """As tabelas da rodada: o CFEM nas faixas pedidas (ou nas mais novas) e as demais, filtradas por `so`."""
    pedidas = [tabela_do_cfem(f) for f in (faixas or faixas_recentes(hoje))]
    pedidas += list(TABELAS_FIXAS)
    return [t for t in pedidas if not so or t.grupo in so]


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "--faixa", action="append", default=[], help="faixa do CFEM, como 2022_2026"
    )
    argumentos.add_argument(
        "--so", action="append", choices=["cfem", "sigbm", "amb"], default=None
    )
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--forcar", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    saida = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    falhas = 0
    for tabela in tabelas_pedidas(opcoes.faixa, opcoes.so, hoje):
        try:
            resultado = carregar(tabela, saida, hoje, forcar=opcoes.forcar)
        except (TypeError, ValueError, OSError) as erro:
            log.error("%s falhou: %s", tabela.nome, erro)
            falhas += 1
            continue
        log.info("%s: %s", tabela.nome, resultado)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
