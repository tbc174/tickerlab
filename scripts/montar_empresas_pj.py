"""Monta as duas tabelas sem pessoa do CNPJ (linha 584; `base/receita_empresas.py`). Roda no servidor de casa.

    python -m scripts.montar_empresas_pj --cnpj <base do CNPJ> --destino <acervo>/base [--ensaio]

Para o mês do retrato vigente da base do CNPJ (o último do `manifesto.json`) baixa os `Empresas*.zip` (fonte
oficial, ~500 MB, apagados ao fim) e grava, repartidas pelos 2 primeiros caracteres da raiz:
- `cnpj_empresas_pj/<xx>.parquet`: razão social, natureza e porte de toda pessoa jurídica (empresário
  individual e grupo 4 nem saem do leitor);
- `cnpj_estabelecimentos_pj/<xx>.parquet`: os estabelecimentos dessas empresas, sem o MEI e sem endereço fino.

**Só acrescenta tabelas novas:** não lê nem toca nas outras pastas de `--destino`. Remontar o mesmo mês não
regrava nada (`gravar_se_mudou`). Imprime o mês; `--ensaio` só diz o mês. A contagem de linhas de cada
tabela vai no log. Saída 0 tudo certo; 1 falha (última linha `FALHAS:`).

Roda: manual (python -m scripts.montar_empresas_pj), na VM de casa, uma vez por mês de retrato novo; coberto
por test_montar_empresas_pj.py; ver dicionario-da-base.md; citado em dicionario.py.
"""

import argparse
import json
import logging
import shutil
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from base import receita_empresas as empresas_pj
from base.parquet import gravar_se_mudou
from base.receita_diff import disponivel_em
from base.receita_retrato import ErroDeLayout
from scripts import carga_receita_mes as carga
from scripts.montar_historico_do_cnpj import (
    CARIMBOS,
    TRABALHO,
    _arquivos,
    _carimbar,
    _ler,
    _origens,
    _repartir,
)

log = logging.getLogger("tickerlab.montar_empresas_pj")

EMPRESAS = "cnpj_empresas_pj"
ESTABELECIMENTOS = "cnpj_estabelecimentos_pj"
MES = "mes_do_retrato"
DISPONIVEL_EM = "disponivel_em"
TAMANHO_MAXIMO_DO_RESUMO = 300
Baixar = Callable[[str, Path], list[Path]]


def _no_retrato(
    tabela: pd.DataFrame, mes: str, sha: pd.Series, agora: datetime
) -> pd.DataFrame:
    datada = tabela.assign(
        **{MES: mes, DISPONIVEL_EM: pd.Timestamp(disponivel_em(mes))}
    )
    return _carimbar(datada, sha, agora)


def _vigente(cnpj: Path, tabela: str, prefixo: str) -> pd.DataFrame:
    pasta = cnpj / "vigente" / tabela
    lido = _ler(_arquivos(pasta / f"{prefixo}.parquet") or _arquivos(pasta / prefixo))
    return lido if lido is not None else pd.DataFrame()


def _gravar(
    nome: str,
    destino: Path,
    prefixo: str,
    tabela: pd.DataFrame,
    origens: list[dict[str, str]],
    chave: str,
    contagem: dict[str, int],
) -> None:
    gravar_se_mudou(
        tabela, destino / nome / prefixo, origens, [chave], carimbos=CARIMBOS
    )
    contagem[nome] += len(tabela)


def _um_prefixo(
    cnpj: Path,
    destino: Path,
    pasta: Path,
    mes: str,
    origens: list[dict[str, str]],
    agora: datetime,
    contagem: dict[str, int],
) -> None:
    empresas = _ler(_arquivos(pasta))
    if empresas is None or empresas.empty:
        return
    empresas = empresas.drop_duplicates("cnpj_basico", keep="last")
    sha = empresas.pop("origem_sha256")
    tabela = _no_retrato(empresas, mes, sha, agora)
    _gravar(EMPRESAS, destino, pasta.name, tabela, origens, "cnpj_basico", contagem)
    vista = empresas_pj.estabelecimentos_sem_pessoa(
        _vigente(cnpj, "estabelecimentos", pasta.name),
        empresas,
        _vigente(cnpj, "simples", pasta.name),
    )
    sha_da_vista = pd.Series([origens[0]["sha256"] if origens else ""] * len(vista))
    tabela = _no_retrato(vista, mes, sha_da_vista, agora)
    _gravar(ESTABELECIMENTOS, destino, pasta.name, tabela, origens, "cnpj", contagem)


def montar(
    cnpj: Path, destino: Path, mes: str, zips: list[Path], agora: datetime
) -> dict[str, int]:
    """Grava as duas tabelas do `mes` e devolve as linhas de cada uma."""
    if not list((cnpj / "vigente" / "simples").glob("*")):
        # sem a tabela do Simples inteira não há como excluir o MEI: parar (só um prefixo sem registro é normal)
        raise ErroDeLayout(f"tabela do Simples ausente em {cnpj / 'vigente'}")
    shas = {z.name: carga.sha256_do_arquivo(z) for z in zips}
    origens = _origens({mes: shas})
    trabalho = destino / EMPRESAS / TRABALHO
    shutil.rmtree(trabalho, ignore_errors=True)
    contagem = {EMPRESAS: 0, ESTABELECIMENTOS: 0}
    try:
        for numero, arquivo in enumerate(sorted(zips)):
            for parte_numero, parte in enumerate(empresas_pj.ler_empresas_pj(arquivo)):
                parte["origem_sha256"] = shas[arquivo.name]
                _repartir(parte, trabalho, f"{numero:02d}-{parte_numero:04d}")
        for pasta in sorted(p for p in trabalho.iterdir() if p.is_dir()):
            _um_prefixo(cnpj, destino, pasta, mes, origens, agora, contagem)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)
    log.info("empresas_pj %s: %s", mes, contagem)
    return contagem


def mes_do_vigente(cnpj: Path) -> str:
    """O mês do retrato vigente: o último do manifesto da base do CNPJ."""
    manifesto = json.loads((cnpj / carga.MANIFESTO).read_text(encoding="utf-8"))
    return max(manifesto["meses"])


def carregar(
    cnpj: Path, destino: Path, baixar: Baixar, agora: Callable[[], datetime]
) -> dict[str, int]:
    """Baixa os ZIPs do mês vigente para uma pasta temporária e monta as tabelas."""
    mes = mes_do_vigente(cnpj)
    destino.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destino) as temporaria:
        return montar(cnpj, destino, mes, baixar(mes, Path(temporaria)), agora())


def _carregar_da_rede(
    opcoes: argparse.Namespace,
) -> dict[str, int]:  # pragma: no cover - rede
    from base.arquivo.cliente_http import ClienteHttp
    from scripts.montar_historico_do_cnpj import _baixar_empresas

    cliente = ClienteHttp()
    return carregar(
        opcoes.cnpj,
        opcoes.destino,
        lambda mes, temporaria: _baixar_empresas(cliente, mes, temporaria),
        lambda: datetime.now(UTC),
    )


def main(argv: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    analisador.add_argument("--cnpj", type=Path, required=True)
    analisador.add_argument("--destino", type=Path, required=True)
    analisador.add_argument("--ensaio", action="store_true")
    opcoes = analisador.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        print(f"mês do retrato vigente: {mes_do_vigente(opcoes.cnpj)}")
        if not opcoes.ensaio:
            print(_carregar_da_rede(opcoes))  # pragma: no cover - rede
        return 0
    except (ErroDeLayout, KeyError, ValueError, OSError) as erro:
        resumo = f"FALHAS: empresas PJ: {type(erro).__name__}: {erro}"
        print(resumo[:TAMANHO_MAXIMO_DO_RESUMO])
        return 1


if __name__ == "__main__":
    sys.exit(main())
