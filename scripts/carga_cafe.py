"""Carga das tabelas do café para a base (plano do café; ADR 0077): o que o `gerar_pacotes_do_cafe` empacota.

    python -m scripts.carga_cafe                       (as cinco tabelas, na base do acervo)
    python -m scripts.carga_cafe comex conab           (só estas)
    python -m scripts.carga_cafe --base <pasta>        (a pasta com empresa_serie/, ensaio fora do acervo)

Lê os originais que o arquivista já guardou (não baixa nada) e grava em `<base>/commodities/`, com
manifesto e versões (`gravar_com_versoes`: com as mesmas origens, nada é lido de novo):

- `comex`: `comex_cafe/<ano>.parquet`, uma linha nova a cada revisão do MDIC (`divulgado_em` é a 1ª
  coleta em que o número apareceu);
- `conab`: `conab_cafe/levantamentos.parquet`, nunca sobrescreve um levantamento; `divulgado_em` é a 1ª
  coleta que viu a planilha (o dia da CONAB não vem no arquivo: o dia da coleta nunca adianta o dado);
- `usda`: `usda_psd/<dia da baixada>.parquet`, uma fotografia por baixada;
- `clima`: `clima_regiao_cafe/<ano>.parquet`, INMET (estações) e CHIRPS (satélite) por região, com a
  normal de 1991–2020;
- `area`: `area_cafe_municipio/municipios.parquet`, a PAM (SIDRA, fonte `ibge-sidra`) e o MapBiomas.

A CFTC (`cftc_cot_agro`) segue em `scripts/carga_setoriais.py --fonte cftc-cot-disaggregated`; o
`carga-cafe.sh` roda as duas. Recusa rodar sem a versão do código (ADR 0055). Saída 0 tudo certo; 1 alguma
tabela falhou ou não tem original (última linha `FALHAS: ...`, que vai para o Kuma).
"""

import argparse
import io
import json
import logging
import re
import sys
import zipfile
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import sqlalchemy as sa

from base.commodities import (
    area_municipio,
    clima_regiao,
    comex_cafe,
    conab_cafe,
    usda_psd,
)
from base.parquet import gravar_com_versoes, origens_gravadas
from src import acervo
from src.banco.coletas import coletas_guardadas, originais_mais_recentes
from src.banco.conexao import criar_engine, migrar_para
from src.commodities.cafe.regioes import REGIOES
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_cafe")
FUSO = ZoneInfo("America/Sao_Paulo")  # o dia da coleta é o do Brasil
PASTA = "commodities"
TAMANHO_MAXIMO_DO_RESUMO = 300  # a linha `FALHAS:` vai no endereço do push do Kuma
FONTE_DO_SIDRA = "ibge-sidra"
TABELA_DA_PAM = "/t/1613/"
FONTE_DO_MAPBIOMAS = "mapbiomas-cafe"
FONTE_DA_MALHA = "ibge-malha-municipal"
FONTE_DO_INMET = "inmet-bdmep"
FONTE_DO_CHIRPS = "chirps-mensal"
ANO_DO_COMEX = re.compile(r"/ncm/EXP_(\d{4})\.csv$")
PAIS_DO_COMEX = "/tabelas/PAIS.csv"
ANO_DO_INMET = re.compile(r"/(\d{4})\.zip$")
MES_DO_CHIRPS = re.compile(r"chirps-v2\.0\.(\d{4})\.(\d{2})\.tif")
CSV_DO_PSD = "psd_coffee.csv"


class SemOriginalError(Exception):
    """O arquivista ainda não guardou o que a tabela precisa."""


def _dia(quando: object) -> date:
    """O dia, no Brasil, de uma hora de coleta (o banco devolve com ou sem fuso; sem fuso é UTC)."""
    momento = pd.Timestamp(quando)  # type: ignore[arg-type]
    if momento.tzinfo is None:
        momento = momento.tz_localize("UTC")
    return momento.tz_convert(FUSO).date()


def _origens(
    coletas: list[tuple[object, str, bytes]], url: str
) -> list[dict[str, str]]:
    return [{"url": url, "sha256": sha256} for _, sha256, _ in coletas]


def _conteudo(linha: sa.Row) -> bytes:
    conteudo = acervo.ler_original(linha.caminho_do_original)
    if conteudo is None:
        raise FileNotFoundError(f"original fora do acervo: {linha.url}")
    return conteudo


def _da_fonte(conexao: sa.Connection, fonte: str) -> list[sa.Row]:
    linhas = originais_mais_recentes(conexao, fonte)
    if not linhas:
        raise SemOriginalError(f"nenhum original da fonte `{fonte}` no acervo")
    return linhas


# --- Comex Stat -------------------------------------------------------------------------------------
def tirar_repeticoes_do_comex(tabela: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por valor visto: a coleta que repete o número não faz linha nova, a revisão faz."""
    valores = [c for c in tabela.columns if c != "divulgado_em"]
    primeiras = tabela.sort_values("divulgado_em", kind="stable").drop_duplicates(
        valores
    )
    return primeiras.reset_index(drop=True)


def _ano_do_comex(conexao: sa.Connection, url: str, paises: bytes) -> pd.DataFrame:
    lidas = [
        comex_cafe.ler(conteudo, paises, _dia(baixado_em))
        for baixado_em, _, conteudo in coletas_guardadas(conexao, url)
    ]
    return tirar_repeticoes_do_comex(pd.concat(lidas, ignore_index=True))


def carregar_comex(conexao: sa.Connection, base: Path) -> None:
    """Um Parquet por ano do `EXP_AAAA.csv`, com o café recortado e as revisões do MDIC."""
    linhas = _da_fonte(conexao, comex_cafe.FONTE)
    paises = next((lin for lin in linhas if lin.url.endswith(PAIS_DO_COMEX)), None)
    if paises is None:
        raise SemOriginalError("falta a tabela PAIS.csv do Comex no acervo")
    nomes = _conteudo(paises)
    for linha in linhas:
        if not (achado := ANO_DO_COMEX.search(linha.url)):
            continue
        coletas = coletas_guardadas(conexao, linha.url)
        origens = [
            *_origens(coletas, linha.url),
            {"url": paises.url, "sha256": paises.sha256},
        ]
        resultado = gravar_com_versoes(
            lambda u=linha.url, n=nomes: _ano_do_comex(conexao, u, n),
            base / PASTA / "comex_cafe" / achado.group(1), origens, comex_cafe.CHAVE,
        )  # fmt: skip
        log.info("comex_cafe %s: %s", achado.group(1), resultado)


# --- CONAB ------------------------------------------------------------------------------------------
def _levantamentos(conexao: sa.Connection, linhas: list[sa.Row]) -> pd.DataFrame:
    """Cada planilha guardada vira um levantamento, com a data em que o arquivista a viu pela 1ª vez."""
    guardada = pd.DataFrame()
    for linha in linhas:
        identificado = conab_cafe.identificar(linha.url)
        coletas = coletas_guardadas(conexao, linha.url)
        if identificado is None or not coletas:
            continue
        baixado_em, _, conteudo = coletas[
            0
        ]  # a 1ª: uma planilha republicada não adianta o dado
        nova = conab_cafe.ler_levantamento(conteudo, identificado[0], _dia(baixado_em))
        guardada = conab_cafe.acrescentar(guardada, nova)
    return guardada


def carregar_conab(conexao: sa.Connection, base: Path) -> None:
    """Todos os levantamentos de safra num Parquet só."""
    linhas = _da_fonte(conexao, conab_cafe.FONTE)
    origens = [{"url": lin.url, "sha256": lin.sha256} for lin in linhas]
    resultado = gravar_com_versoes(
        lambda: _levantamentos(conexao, linhas),
        base / PASTA / "conab_cafe" / "levantamentos", origens, list(conab_cafe.CHAVE),
    )  # fmt: skip
    log.info("conab_cafe: %s", resultado)


# --- USDA PSD ---------------------------------------------------------------------------------------
def _csv_do_psd(conteudo: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        return pacote.read(CSV_DO_PSD)


def carregar_usda(conexao: sa.Connection, base: Path) -> None:
    """Uma fotografia do balanço por baixada do `psd_coffee_csv.zip`."""
    for linha in _da_fonte(conexao, usda_psd.FONTE):
        for baixado_em, sha256, conteudo in coletas_guardadas(conexao, linha.url):
            dia = _dia(baixado_em)
            resultado = gravar_com_versoes(
                lambda c=conteudo, d=dia: usda_psd.ler(_csv_do_psd(c), d),
                base / PASTA / "usda_psd" / dia.isoformat(),
                [{"url": linha.url, "sha256": sha256}], usda_psd.CHAVE,
            )  # fmt: skip
            log.info("usda_psd %s: %s", dia, resultado)


# --- clima por região -------------------------------------------------------------------------------
def _malha(conexao: sa.Connection) -> dict:
    """A malha municipal das UFs com café: o original mais novo de cada UF, numa coleção só."""
    feicoes = []
    for linha in _da_fonte(conexao, FONTE_DA_MALHA):
        feicoes += json.loads(_conteudo(linha)).get("features", [])
    return {"type": "FeatureCollection", "features": feicoes}


def _mascaras_do_cafe(malha: Mapping) -> Mapping[str, clima_regiao.Mascara]:
    codigos = {m.codigo for regiao in REGIOES for m in regiao.municipios}
    return clima_regiao.mascaras_da_malha(malha, codigos)


def _inmet_do_ano(conteudo: bytes) -> pd.DataFrame:
    diario = clima_regiao.atribuir_regiao(clima_regiao.ler_inmet(conteudo))
    return clima_regiao.agregar(diario)


def _chirps_do_mes(
    linha: sa.Row, mascaras: Mapping[str, clima_regiao.Mascara]
) -> pd.DataFrame | None:
    achado = MES_DO_CHIRPS.search(linha.url)
    if achado is None:
        return None
    por_municipio = clima_regiao.ler_chirps(_conteudo(linha), mascaras)
    mes = date(int(achado.group(1)), int(achado.group(2)), 1)
    return clima_regiao.chirps_por_regiao(por_municipio, mes)


def _mensal_do_clima(
    conexao: sa.Connection, inmet: list[sa.Row], chirps: list[sa.Row]
) -> pd.DataFrame:
    """INMET e CHIRPS por região e mês, com a normal e a anomalia, de todos os anos juntos."""
    mascaras = _mascaras_do_cafe(_malha(conexao)) if chirps else {}
    partes = [_inmet_do_ano(_conteudo(lin)) for lin in inmet]
    partes += [p for lin in chirps if (p := _chirps_do_mes(lin, mascaras)) is not None]
    mensal = pd.concat([p for p in partes if not p.empty], ignore_index=True)
    return clima_regiao.com_normal(mensal)


def _origens_do_ano(
    ano: int, inmet: list[sa.Row], chirps: list[sa.Row], malha: list[sa.Row]
) -> list[dict[str, str]]:
    do_ano = [lin for lin in inmet if f"/{ano}.zip" in lin.url]
    do_ano += [lin for lin in chirps if f".{ano}." in lin.url]
    return [{"url": lin.url, "sha256": lin.sha256} for lin in [*do_ano, *malha]]


def carregar_clima(conexao: sa.Connection, base: Path) -> None:
    """Um Parquet por ano; o ano só é refeito se um original dele (ou a malha) mudou."""
    inmet = originais_mais_recentes(conexao, FONTE_DO_INMET)
    chirps = originais_mais_recentes(conexao, FONTE_DO_CHIRPS)
    if not inmet and not chirps:
        raise SemOriginalError("nenhum original do INMET nem do CHIRPS no acervo")
    malha = originais_mais_recentes(conexao, FONTE_DA_MALHA) if chirps else []
    destino = base / PASTA / "clima_regiao_cafe"
    anos = sorted({int(a.group(1)) for lin in inmet if (a := ANO_DO_INMET.search(lin.url))}
                  | {int(m.group(1)) for lin in chirps if (m := MES_DO_CHIRPS.search(lin.url))})  # fmt: skip
    mudou = [
        a
        for a in anos
        if origens_gravadas(destino / str(a))
        != _origens_do_ano(a, inmet, chirps, malha)
    ]
    if not mudou:
        log.info("clima_regiao_cafe: igual")
        return
    mensal = _mensal_do_clima(conexao, inmet, chirps)
    for ano in mudou:
        do_ano = mensal[pd.to_datetime(mensal["competencia"]).dt.year == ano]
        resultado = gravar_com_versoes(
            lambda t=do_ano: t.reset_index(drop=True), destino / str(ano),
            _origens_do_ano(ano, inmet, chirps, malha), ["regiao", "fonte", "competencia"],
        )  # fmt: skip
        log.info("clima_regiao_cafe %s: %s", ano, resultado)


# --- área por município -----------------------------------------------------------------------------
def _pam(respostas: list[sa.Row]) -> pd.DataFrame:
    """A PAM de todas as respostas do SIDRA; onde duas respostas têm o mesmo ano, vale a mais nova."""
    ordem = sorted(respostas, key=lambda lin: lin.baixado_em)
    lidas = [area_municipio.ler_pam(json.loads(_conteudo(lin))) for lin in ordem]
    juntas = pd.concat(lidas, ignore_index=True)
    return juntas.drop_duplicates(["codigo", "ano"], keep="last").reset_index(drop=True)


def carregar_area(conexao: sa.Connection, base: Path) -> None:
    """A PAM e o MapBiomas lado a lado, uma linha por município e ano."""
    respostas = [
        lin for lin in _da_fonte(conexao, FONTE_DO_SIDRA) if TABELA_DA_PAM in lin.url
    ]
    if not respostas:
        raise SemOriginalError("nenhuma resposta da PAM (SIDRA 1613) no acervo")
    mapbiomas = _da_fonte(conexao, FONTE_DO_MAPBIOMAS)[-1]
    origens = [
        {"url": lin.url, "sha256": lin.sha256} for lin in [*respostas, mapbiomas]
    ]
    resultado = gravar_com_versoes(
        lambda: area_municipio.juntar(
            _pam(respostas), area_municipio.ler_mapbiomas(_conteudo(mapbiomas))
        ),
        base / PASTA / "area_cafe_municipio" / "municipios", origens, ["codigo", "ano"],
    )  # fmt: skip
    log.info("area_cafe_municipio: %s", resultado)


CARGAS: dict[str, Callable[[sa.Connection, Path], None]] = {
    "comex": carregar_comex,
    "conab": carregar_conab,
    "usda": carregar_usda,
    "clima": carregar_clima,
    "area": carregar_area,
}


def carregar(conexao: sa.Connection, base: Path, quais: list[str]) -> list[str]:
    """Roda as cargas pedidas; devolve o motivo de cada uma que falhou (as outras seguem)."""
    falhas = []
    for nome in quais:
        try:
            CARGAS[nome](conexao, base)
        except SemOriginalError as erro:
            log.warning("%s: %s", nome, erro)
            falhas.append(f"{nome}: {erro}")
        except (
            Exception
        ) as erro:  # a noite não para em silêncio: o Kuma recebe o motivo
            log.exception("%s: falhou", nome)
            falhas.append(f"{nome}: {type(erro).__name__}: {erro}")
    return falhas


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("tabelas", nargs="*", choices=list(CARGAS))
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
            falhas = carregar(conexao, base, opcoes.tabelas or list(CARGAS))
    finally:
        motor.dispose()
    if falhas:
        print(("FALHAS: café: " + "; ".join(falhas))[:TAMANHO_MAXIMO_DO_RESUMO])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
