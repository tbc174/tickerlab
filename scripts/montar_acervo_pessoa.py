"""Monta o `acervo_pessoa/` da tela da equipe (ADR 0128, Emenda 1; linha 808). Roda só no servidor de casa.

    python -m scripts.montar_acervo_pessoa --cnpj <acervo>/base/cnpj --bruto <acervo>/bruto/rfb-cnpj \
        --destino <fora do acervo>/acervo_pessoa [--ensaio]

Para o mês do retrato vigente da base do CNPJ (o último do `manifesto.json`) lê os ZIPs que a carga já
guardou em `--bruto` (pelo SHA-256 do manifesto; nada é baixado) e grava, repartidas pelos 2 primeiros
caracteres da raiz:
- `socios_pf/<xx>.parquet` (dos `Socios*.zip`): raiz da empresa, nome do sócio pessoa física, qualificação e
  data de entrada. Sem CPF e sem menor de idade (`base/receita_pessoa.py` diz o que é descartado);
- `contato/<xx>.parquet` (dos `Estabelecimentos*.zip`): endereço, telefones e e-mail dos estabelecimentos
  ativos. Sem nome fantasia, sem fax e sem nada com cara de CPF (`base/receita_contato.py`).

A pasta fica **fora do acervo**: o script recusa um `--destino` dentro dele, para que nenhuma cópia do acervo
(PC, Drive, VPS, recorte da API) leve pessoa junto. Levar esta pasta a outro servidor é outra decisão, pedida
à parte.

A montagem de cada tabela é inteira ou nada: grava numa pasta de trabalho e só então troca a tabela. O
`manifesto.json` da pasta e a saída dizem o mês, as linhas e **quantas** linhas ou campos foram descartados
por motivo (só números, nunca nome nem contato). `--ensaio` só diz o mês e os arquivos. Saída 0 tudo certo;
1 falha (última linha `FALHAS:`).

Roda: manual (python -m scripts.montar_acervo_pessoa), na VM de casa, uma vez por mês de retrato novo; coberto
por test_montar_acervo_pessoa.py.
"""

import argparse
import json
import logging
import shutil
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, NamedTuple

import pandas as pd

from base import receita_contato, receita_pessoa
from base.receita_retrato import ErroDeLayout
from scripts import carga_receita_mes as carga
from scripts.montar_historico_do_cnpj import _arquivos, _ler, _repartir, _zips_do_mes

log = logging.getLogger("tickerlab.montar_acervo_pessoa")

NOME_DA_PASTA = "acervo_pessoa"
SOCIOS = "socios_pf"
CONTATO = "contato"
TRABALHO = "_trabalho"
ANTIGA = "_antiga"  # a tabela anterior, posta de lado só durante a troca
MANIFESTO = "manifesto.json"
MES = "mes_do_retrato"
TAMANHO_MAXIMO_DO_RESUMO = 300

Parte = tuple[
    pd.DataFrame, Counter[str]
]  # as linhas que ficam e os descartes por motivo


class Tabela(NamedTuple):
    """Uma tabela do acervo de pessoa: de que ZIPs sai, quem os lê e o que identifica uma linha."""

    nome: str
    arquivos: str  # começo do nome dos ZIPs do mês
    ler: Callable[[Path | IO[bytes]], Iterator[Parte]]
    chave: list[str]
    motivos: tuple[str, ...]


TABELAS = (
    Tabela(
        SOCIOS,
        "Socios",
        receita_pessoa.ler_socios_pf,
        ["cnpj_basico", "nome_socio", "qualificacao", "data_entrada"],
        receita_pessoa.MOTIVOS,
    ),
    Tabela(
        CONTATO,
        "Estabelecimentos",
        receita_contato.ler_contato,
        ["cnpj"],
        receita_contato.MOTIVOS,
    ),
)


class DestinoRecusadoError(ValueError):
    """O destino não é uma pasta `acervo_pessoa` fora do acervo."""


class ZipAusenteError(FileNotFoundError):
    """Um ZIP do manifesto não está no bruto, ou o SHA-256 dele não confere."""


def conferir_destino(cnpj: Path, destino: Path) -> None:
    """Recusa o destino com outro nome ou dentro do acervo (que é copiado para outros lugares)."""
    acervo = cnpj.resolve().parents[1]  # <acervo>/base/cnpj
    alvo = destino.resolve()
    if alvo.name != NOME_DA_PASTA:
        raise DestinoRecusadoError(f"o destino tem de se chamar {NOME_DA_PASTA}")
    if alvo.is_relative_to(acervo):
        raise DestinoRecusadoError("o destino não pode ficar dentro do acervo")


def zips_do_mes(cnpj: Path, bruto: Path) -> tuple[str, dict[str, dict[str, Path]]]:
    """O mês vigente e, por tabela e por nome, o ZIP guardado no bruto (achado pelo SHA-256 do manifesto)."""
    manifesto = json.loads((cnpj / carga.MANIFESTO).read_text(encoding="utf-8"))
    mes = max(manifesto["meses"])
    achados: dict[str, dict[str, Path]] = {}
    for tabela in TABELAS:
        achados[tabela.nome] = {}
        for nome, sha in _zips_do_mes(manifesto, mes, tabela.arquivos).items():
            guardados = sorted(bruto.glob(f"*/{sha}.zip"))
            if not guardados:
                raise ZipAusenteError(f"{nome} de {mes} não está no bruto")
            achados[tabela.nome][nome] = guardados[0]
        if not achados[tabela.nome]:
            raise ZipAusenteError(
                f"o manifesto de {mes} não tem {tabela.arquivos}*.zip"
            )
    return mes, achados


def _repartir_os_zips(
    tabela: Tabela, zips: dict[str, Path], trabalho: Path
) -> Counter[str]:
    descartes: Counter[str] = Counter()
    for numero, (nome, arquivo) in enumerate(sorted(zips.items())):
        for parte_numero, (linhas, da_parte) in enumerate(tabela.ler(arquivo)):
            descartes += da_parte
            _repartir(linhas, trabalho, f"{numero:02d}-{parte_numero:04d}")
        log.info("lido %s", nome)
    return descartes


def _gravar_prefixos(
    tabela: Tabela, trabalho: Path, pronta: Path, mes: str
) -> dict[str, int]:
    pronta.mkdir(parents=True)
    total, empresas = 0, 0
    for pasta in sorted(p for p in trabalho.iterdir() if p.is_dir()):
        linhas = _ler(_arquivos(pasta))
        if linhas is None or linhas.empty:
            continue
        linhas = linhas.drop_duplicates(tabela.chave).sort_values(
            tabela.chave, na_position="last"
        )
        linhas.assign(**{MES: mes}).to_parquet(
            pronta / f"{pasta.name}.parquet", index=False
        )
        total += len(linhas)
        empresas += linhas["cnpj_basico"].nunique()
    return {"linhas": total, "empresas": empresas}


def _trocar(pronta: Path, atual: Path) -> None:
    """Põe a tabela nova no lugar da atual sem deixar uma tabela pela metade: a antiga sai inteira para
    o lado (um `rename`), a nova entra, e só então a antiga é apagada. Se a nova não entra, a antiga volta."""
    antiga = atual.with_name(atual.name + ANTIGA)
    shutil.rmtree(antiga, ignore_errors=True)
    if atual.exists():
        atual.rename(antiga)
    try:
        pronta.rename(atual)
    except OSError:
        if antiga.exists():
            antiga.rename(atual)
        raise
    shutil.rmtree(antiga, ignore_errors=True)


def _preparar_tabela(
    tabela: Tabela, trabalho: Path, mes: str, zips: dict[str, Path]
) -> tuple[dict[str, int], Counter[str]]:
    """Lê os ZIPs e grava a tabela pronta em `trabalho/<nome>`, sem tocar no destino."""
    descartes = _repartir_os_zips(tabela, zips, trabalho / f"{tabela.nome}-partes")
    contagem = _gravar_prefixos(
        tabela, trabalho / f"{tabela.nome}-partes", trabalho / tabela.nome, mes
    )
    return contagem, descartes


def montar(
    destino: Path,
    mes: str,
    zips: dict[str, dict[str, Path]],
    shas: dict[str, str],
    agora: datetime,
) -> dict:
    """Grava as tabelas do `mes` e o manifesto; devolve o manifesto (só números e SHA-256).

    Todas as tabelas ficam prontas na pasta de trabalho antes de qualquer troca: se a leitura de uma falha,
    o destino e o manifesto continuam como estavam (mês único em todas as tabelas).
    """
    for arquivos in zips.values():
        for nome, arquivo in arquivos.items():
            if carga.sha256_do_arquivo(arquivo) != shas[nome]:
                raise ZipAusenteError(
                    f"o SHA-256 de {nome} não confere com o manifesto"
                )
    destino.mkdir(parents=True, exist_ok=True)
    trabalho = destino / TRABALHO
    shutil.rmtree(trabalho, ignore_errors=True)
    contagens, descartes = {}, {}
    try:
        for tabela in TABELAS:
            contagem, da_tabela = _preparar_tabela(
                tabela, trabalho, mes, zips[tabela.nome]
            )
            contagens[tabela.nome] = contagem
            descartes |= {motivo: da_tabela.get(motivo, 0) for motivo in tabela.motivos}
        for tabela in TABELAS:
            _trocar(trabalho / tabela.nome, destino / tabela.nome)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)
    manifesto = {
        MES: mes,
        "montado_em": agora.isoformat(),
        "tabelas": contagens,
        "descartes": descartes,
        "origens": dict(sorted(shas.items())),
    }
    (destino / MANIFESTO).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifesto


def _nomes(zips: dict[str, dict[str, Path]]) -> list[str]:
    return sorted(nome for arquivos in zips.values() for nome in arquivos)


def carregar(cnpj: Path, bruto: Path, destino: Path, agora: datetime) -> dict:
    """Confere o destino, acha os ZIPs do mês vigente no bruto e monta."""
    conferir_destino(cnpj, destino)
    mes, zips = zips_do_mes(cnpj, bruto)
    shas = {
        nome: arquivo.stem
        for arquivos in zips.values()
        for nome, arquivo in arquivos.items()
    }
    return montar(destino, mes, zips, shas, agora)


def main(argv: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    analisador.add_argument("--cnpj", type=Path, required=True)
    analisador.add_argument("--bruto", type=Path, required=True)
    analisador.add_argument("--destino", type=Path, required=True)
    analisador.add_argument("--ensaio", action="store_true")
    opcoes = analisador.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        conferir_destino(opcoes.cnpj, opcoes.destino)
        mes, zips = zips_do_mes(opcoes.cnpj, opcoes.bruto)
        print(f"mês do retrato vigente: {mes}; arquivos: {', '.join(_nomes(zips))}")
        if not opcoes.ensaio:
            agora = datetime.now(UTC)
            manifesto = carregar(opcoes.cnpj, opcoes.bruto, opcoes.destino, agora)
            print(json.dumps({k: manifesto[k] for k in ("tabelas", "descartes")}))
        return 0
    except (ErroDeLayout, KeyError, ValueError, OSError) as erro:
        resumo = f"FALHAS: acervo de pessoa: {type(erro).__name__}: {erro}"
        print(resumo[:TAMANHO_MAXIMO_DO_RESUMO])
        return 1


if __name__ == "__main__":
    sys.exit(main())
