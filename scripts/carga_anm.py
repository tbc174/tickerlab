"""Carga da ANM para a base: CFEM (arrecadação), SIGBM (barragens) e Anuário Mineral (AMB) (linha 657).

    python -m scripts.carga_anm                                  (grava no acervo: as 2 faixas mais novas do CFEM)
    python -m scripts.carga_anm --faixa 2017_2021 --pasta /tmp/base --forcar
    python -m scripts.carga_anm --so sigbm --so amb

Lê os CSV de https://dadosabertos.anm.gov.br (`base/anm.py`) e grava, com manifesto e versões
(`base/parquet.py::gravar_com_versoes`):
- `anm_cfem_arrecadacao/<faixa>.parquet`: um arquivo por faixa de anos da ANM (`2022_2026`...), só pessoa
  jurídica com CNPJ completo (pessoa física e documento mascarado são descartados e contados no log) e só
  de raiz que está na `cnpj_empresas_pj` e `cnpj_estabelecimentos_pj` (empresário individual e MEI são pessoa: saem e são contados);
- `anm_sigbm_barragens/barragens.parquet`: uma linha por barragem, com a categoria de risco e o dano potencial
  como a ANM declarou; empreendedor de raiz fora das duas listas fica sem CNPJ e sem nome;
- `anm_amb_producao_bruta`, `anm_amb_producao_beneficiada` e `anm_amb_agua_mineral` (`atual.parquet`): o
  Anuário, série setorial sem CNPJ.

**Sem olhar o futuro:** o CFEM traz a data de criação da linha (vira `disponivel_em`). SIGBM e AMB são
sobrescritos pela ANM, sem histórico: a data de disponibilidade é a da coleta, e a linha que não mudou entre
duas coletas mantém a data da primeira (olhar de novo não empurra o passado para frente).

Ritmo mensal: o app não depende dela; o servidor de casa roda uma vez por mês. Licença da ANM não declarada:
a confirmar, só uso interno (ADR 0102, Emenda 2); nada é perguntado à fonte. Recusa rodar sem a versão do
código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 se alguma tabela falhou.

Roda: manual (python -m scripts.carga_anm); coberto por test_carga_anm.py; ver
dicionario-da-base.md; citado em dicionario.py.
"""

import argparse
import hashlib
import logging
import re
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
GRUPOS_COM_CNPJ = frozenset({"cfem", "sigbm"})
TABELA_PJ = "cnpj_empresas_pj"
TABELA_ESTAB = "cnpj_estabelecimentos_pj"
ARQUIVO_VERSIONADO = re.compile(r"\.v\d+\.parquet$")


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


def _raizes_da_tabela(base: Path, tabela: str) -> frozenset[str]:
    """As raízes (`cnpj_basico`) dos arquivos atuais de uma tabela da base; sem arquivo, recusa."""
    pasta = base / tabela
    arquivos = [
        a for a in pasta.glob("*.parquet") if not ARQUIVO_VERSIONADO.search(a.name)
    ]
    if not arquivos:
        raise FileNotFoundError(
            f"sem a {tabela} em {pasta}: não dá para conferir quem é pessoa"
        )
    raizes: set[str] = set()
    for arquivo in arquivos:
        raizes.update(
            pd.read_parquet(arquivo, columns=["cnpj_basico"])["cnpj_basico"].astype(str)
        )
    return frozenset(raizes)


def raizes_de_empresa(base: Path) -> frozenset[str]:
    """Raízes que estão nas duas listas sem pessoa: `cnpj_empresas_pj` e `cnpj_estabelecimentos_pj`.

    A de empresas só tira empresário individual pela natureza; MEI com natureza de empresa só sai
    na de estabelecimentos (opção pelo Simples). Por isso vale a interseção, como no recorte da API
    (`montar_recorte_da_api.tirar_raizes_de_mei`)."""
    return _raizes_da_tabela(base, TABELA_PJ) & _raizes_da_tabela(base, TABELA_ESTAB)


def so_empresa(
    tabela: pd.DataFrame, raizes: frozenset[str], descartar: bool = True
) -> pd.DataFrame:
    """Tira da tabela o que é de CNPJ fora da lista de empresas; conta o que saiu em `fora_da_pj`.

    `descartar`: a linha inteira sai (CFEM). Sem ele (barragens) a linha fica, sem CNPJ, raiz nem nome
    do empreendedor, como o leitor já faz com o documento incompleto."""
    cnpj = tabela["cnpj"].astype(str)
    completo = cnpj.str.len() == 14
    fora = completo & ~cnpj.str[:8].isin(raizes)
    if descartar:
        saida = tabela[completo & ~fora].reset_index(drop=True)
        conta = int((~(completo & ~fora)).sum())
    else:
        saida = tabela.copy()
        saida.loc[fora, ["cnpj", "cnpj_raiz", "empreendedor"]] = ""
        saida = saida.reset_index(drop=True)
        conta = int(fora.sum())
    saida.attrs = {**tabela.attrs, "fora_da_pj": conta}
    return saida


def hash_das_raizes(raizes: frozenset[str]) -> str:
    """Impressão digital da lista de raízes: entra na origem, para a tabela refazer se a lista mudar."""
    return hashlib.sha256("\n".join(sorted(raizes)).encode()).hexdigest()


def carregar(
    tabela: Tabela,
    saida: Path,
    coletado_em: date,
    baixar_arquivo: Callable[[str], bytes] = baixar,
    forcar: bool = False,
    raizes: frozenset[str] | None = None,
) -> str:
    """Baixa, lê e grava uma tabela; devolve `GRAVADO` ou `IGUAL`.

    CFEM e SIGBM trazem CNPJ de empreendedor e só se gravam com a lista de raízes de empresa: sem ela,
    a carga recusa (empresário individual e MEI são pessoa)."""
    if tabela.grupo in GRUPOS_COM_CNPJ and raizes is None:
        raise ValueError(
            f"{tabela.nome}: sem a lista de empresas (raizes) não se grava CNPJ"
        )
    conteudo = baixar_arquivo(tabela.url)
    origem = {"url": tabela.url, "sha256": hashlib.sha256(conteudo).hexdigest()}
    if raizes is not None and tabela.grupo in GRUPOS_COM_CNPJ:
        origem["raizes_sha256"] = hash_das_raizes(raizes)
    destino = saida / tabela.nome
    arquivo = destino.with_suffix(".parquet")

    def montar() -> pd.DataFrame:
        lida = tabela.leitor(conteudo, coletado_em)
        if raizes is not None and tabela.grupo in GRUPOS_COM_CNPJ:
            lida = so_empresa(lida, raizes, descartar=tabela.grupo == "cfem")
            log.info(
                "%s: %d linhas de fora da lista de empresas (pessoa ou sem CNPJ) tiradas ou sem CNPJ",
                tabela.fonte,
                lida.attrs["fora_da_pj"],
            )
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
    argumentos.add_argument(
        "--base-pj",
        type=Path,
        default=None,
        help="pasta base/ que tem a cnpj_empresas_pj (padrão: a base do acervo)",
    )
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
    base_da_pj = (
        opcoes.base_pj
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    pedidas = tabelas_pedidas(opcoes.faixa, opcoes.so, hoje)
    raizes = None
    if any(t.grupo in GRUPOS_COM_CNPJ for t in pedidas):
        try:
            raizes = raizes_de_empresa(base_da_pj)
        except (OSError, KeyError, ValueError) as erro:
            log.error("sem a lista de empresas: %s", erro)
            return 1
    falhas = 0
    for tabela in pedidas:
        try:
            resultado = carregar(
                tabela, saida, hoje, forcar=opcoes.forcar, raizes=raizes
            )
        except (TypeError, ValueError, OSError) as erro:
            log.error("%s falhou: %s", tabela.nome, erro)
            falhas += 1
            continue
        log.info("%s: %s", tabela.nome, resultado)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
