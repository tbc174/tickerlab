"""Coleta restrita do Sintegra estadual, sem consulta unitária nem carga no CI.

    python -m scripts.carga_sintegra_estadual --uf PR

Aceita --uf PR --uf RS --uf MG; RS e MG falham antes de qualquer rede.
TXT temporário; acervo guarda somente colunas permitidas e manifesto com SHA-256.
Simples/MEI vem do cnpj_simples local, sem nova coleta da Receita.

Roda: manual pela Diretoria na máquina de casa; python -m scripts.carga_sintegra_estadual --uf PR.
"""

import argparse
import hashlib
import json
import logging
import tempfile
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Protocol

import pandas as pd
import requests

from base import sintegra_estadual as sintegra
from base.arquivo.coleta import FreioDeDisco, conferir_freio, espaco_do_disco
from base.parquet import (
    IGUAL,
    LINHAGEM,
    arquivos_atuais,
    como_no_disco,
    conferir_tabela,
    gravar_com_versoes,
    hash_da_tabela,
    ler_tabela,
)
from base.sintegra_http import ClienteSintegra
from src import acervo
from src.versao_do_codigo import exigir_versao_do_codigo, versao_do_codigo

log = logging.getLogger(__name__)


class Baixador(Protocol):
    """Só a operação usada pela carga, sem exigir os métodos do arquivista."""

    def baixar(self, url: str, destino: Path) -> Mapping[str, str]: ...


def _data_do_arquivo(cabecalhos: Mapping[str, str], quando: datetime) -> date | None:
    valor = {k.lower(): v for k, v in cabecalhos.items()}.get("last-modified")
    if not valor:
        return None
    try:
        dia = parsedate_to_datetime(valor).date()
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Sintegra: data do arquivo inválida") from None
    if dia > quando.date():
        raise ValueError("Sintegra: data do arquivo está no futuro")
    return dia


def _baixar_uf(
    uf: str, urls: dict[str, str], temporaria: Path, quando: datetime, cliente: Baixador
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    partes, origens = [], []
    for arquivo, url in urls.items():
        caminho = temporaria / f"{arquivo}.txt"
        cabecalhos = cliente.baixar(url, caminho)
        tabela = sintegra.ler_arquivo(caminho, uf, arquivo)
        with caminho.open("rb") as entrada:
            sha256 = hashlib.file_digest(entrada, "sha256").hexdigest()
        dia = _data_do_arquivo(cabecalhos, quando)
        origens.append(
            {
                "url": url,
                "sha256": sha256,
                "data_arquivo": dia.isoformat() if dia else "",
                "coletado_em": quando.isoformat(),
                **{k: str(v) for k, v in tabela.attrs["contagem"].items()},
            }
        )
        tabela["origem_sha256"] = sha256
        tabela["data_arquivo"] = dia
        partes.append(tabela)
    return pd.concat(partes, ignore_index=True), origens


def _arquivos_simples(pasta: Path, raizes: pd.Series) -> list[Path]:
    arquivos = []
    for prefixo in sorted(set(raizes.str[:2])):
        raiz = pasta / "cnpj/vigente/simples" / prefixo
        if raiz.with_suffix(".parquet").is_file():
            arquivos.append(raiz.with_suffix(".parquet"))
        elif raiz.is_dir():
            arquivos.extend(sorted(raiz.glob("*.parquet")))
    return arquivos


def _ligar_simples(
    tabela: pd.DataFrame, pasta: Path, quando: datetime
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    # O vigente é observado hoje; nunca interpretar suas opções como histórico
    # estadual nem retroagir sua disponibilidade às datas de opção da Receita.
    raizes = tabela.cnpj.str[:8]
    partes, origens = [], []
    for arquivo in _arquivos_simples(pasta, raizes):
        parte = pd.read_parquet(arquivo, columns=list(sintegra.COLUNAS_SIMPLES))
        partes.append(parte.loc[parte.cnpj_basico.isin(raizes)])
        with arquivo.open("rb") as entrada:
            sha256 = hashlib.file_digest(entrada, "sha256").hexdigest()
        origens.append(
            {
                "url": f"base/{arquivo.relative_to(pasta).as_posix()}",
                "sha256": sha256,
                "observado_em": quando.isoformat(),
            }
        )
    simples = (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=list(sintegra.COLUNAS_SIMPLES))
    )
    if simples.cnpj_basico.duplicated().any():
        raise ValueError("Sintegra: raiz duplicada no Simples local")
    for coluna in ("optante_simples", "optante_mei"):
        simples[coluna] = simples[coluna].astype("boolean")
    for coluna in sintegra.COLUNAS_SIMPLES:
        if coluna.startswith("data_"):
            simples[coluna] = pd.to_datetime(simples[coluna], errors="raise").dt.date
    simples["simples_observado_em"] = quando.date()
    tabela = tabela.assign(cnpj_basico=raizes).merge(
        simples, on="cnpj_basico", how="left", validate="many_to_one"
    )
    return tabela.drop(columns="cnpj_basico"), origens


def carregar_uf(uf: str, pasta: Path, quando: datetime, cliente: Baixador) -> str:
    """Valida os dois arquivos antes de publicar a edição; falha preserva o acervo."""
    urls = sintegra.urls_para_coleta(uf)
    pasta.mkdir(parents=True, exist_ok=True)
    conferir_freio(*espaco_do_disco(pasta))
    with tempfile.TemporaryDirectory(prefix="sintegra-", dir=pasta) as temporaria:
        tabela, origens = _baixar_uf(uf, urls, Path(temporaria), quando, cliente)
    tabela, origens_simples = _ligar_simples(tabela, pasta, quando)
    tabela["fonte"] = sintegra.FONTES[uf]
    tabela["origem_coletada_em"] = quando
    tabela["disponivel_em"] = quando.date()
    tabela["publico_em"] = quando.date()
    tabela["montado_em"] = quando
    tabela["versao_do_codigo"] = versao_do_codigo()
    datas = [
        date.fromisoformat(o["data_arquivo"]) for o in origens if o["data_arquivo"]
    ]
    edicao = max(datas) if len(datas) == len(origens) else quando.date()
    destino = pasta / sintegra.TABELA / uf / edicao.isoformat()
    return _gravar(tabela, destino, origens + origens_simples)


def _origens_da_edicao(arquivo: Path) -> list[dict[str, str]]:
    return json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))[
        "origens"
    ]


def _ultima_edicao(pasta: Path) -> Path | None:
    arquivos = arquivos_atuais(pasta)
    # Coletado_em vem da carga, não do Last-Modified da fonte. Assim uma
    # republicação com data antiga também pode ser a observação mais recente.
    return max(
        arquivos,
        key=lambda p: max(o.get("coletado_em", "") for o in _origens_da_edicao(p)),
        default=None,
    )


def _hash_do_conteudo(tabela: pd.DataFrame) -> str:
    carimbos = [
        *LINHAGEM,
        "publico_em",
        "disponivel_em",
        "simples_observado_em",
        "data_arquivo",
    ]
    return hash_da_tabela(
        como_no_disco(tabela).drop(columns=carimbos), list(sintegra.CHAVE)
    )


def _contagens(origens: list[dict[str, str]]) -> list[tuple[str | None, ...]]:
    return [
        (o.get("url"), o.get("linhas_lidas"), o.get("documentos_recusados"))
        for o in origens
    ]


def _gravar(tabela: pd.DataFrame, destino: Path, origens: list[dict[str, str]]) -> str:
    anterior = _ultima_edicao(destino.parent)
    if anterior is not None:
        if not conferir_tabela(anterior):
            raise ValueError("Sintegra: edição anterior não confere; carga recusada")
        if _hash_do_conteudo(ler_tabela(anterior)) == _hash_do_conteudo(
            tabela
        ) and _contagens(_origens_da_edicao(anterior)) == _contagens(origens):
            return IGUAL
    return gravar_com_versoes(
        lambda: tabela, destino, origens, list(sintegra.CHAVE), forcar=True
    )


def main(argv: list[str] | None = None) -> int:
    """Só PR operacional; recusas são explícitas e erros nunca imprimem a fonte."""
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "--uf", choices=sintegra.UFS, action="append", required=True
    )
    argumentos.add_argument("--pasta", type=Path)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # Validar todas antes de iniciar: --uf PR --uf RS não baixa uma UF pela metade.
    for uf in opcoes.uf:
        if uf in sintegra.BLOQUEIOS:
            log.error("Sintegra %s: %s", uf, sintegra.BLOQUEIOS[uf])
            return 1
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    pasta = opcoes.pasta or (acervo.pasta_do_acervo() or acervo.PASTA_PADRAO) / "base"
    cliente = ClienteSintegra()
    try:
        for uf in dict.fromkeys(opcoes.uf):
            try:
                resultado = carregar_uf(uf, pasta, datetime.now(UTC), cliente)
            except (
                ValueError,
                OSError,
                zipfile.BadZipFile,
                RuntimeError,
                requests.RequestException,
                FreioDeDisco,
            ) as erro:
                log.error("Sintegra %s: coleta recusada (%s)", uf, type(erro).__name__)
                return 1
            log.info("Sintegra %s: %s", uf, resultado)
    finally:
        cliente.sessao.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
