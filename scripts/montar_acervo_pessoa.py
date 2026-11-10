"""Monta o `acervo_pessoa/` da tela da equipe (ADR 0128, Emenda 1; linha 808). Roda só no servidor de casa.

    python -m scripts.montar_acervo_pessoa --cnpj <acervo>/base/cnpj --bruto <acervo>/bruto/rfb-cnpj \
        --destino <fora do acervo>/acervo_pessoa [--ensaio]

Para o mês do retrato vigente da base do CNPJ (o último do `manifesto.json`) lê os `Socios*.zip` que a carga
já guardou em `--bruto` (pelo SHA-256 do manifesto; nada é baixado) e grava, repartida pelos 2 primeiros
caracteres da raiz:
- `socios_pf/<xx>.parquet`: raiz da empresa, nome do sócio pessoa física, qualificação e data de entrada.

Sem CPF e sem menor de idade (`base/receita_pessoa.py` diz o que é descartado). A pasta fica **fora do
acervo**: o script recusa um `--destino` dentro dele, para que nenhuma cópia do acervo (PC, Drive, VPS, recorte
da API) leve pessoa junto. Levar esta pasta a outro servidor é outra decisão, pedida à parte.

A montagem é inteira ou nada: grava numa pasta de trabalho e só então troca a tabela. O `manifesto.json` da
pasta e a saída dizem o mês, as linhas e **quantas** linhas foram descartadas por motivo (só números, nunca
nome). `--ensaio` só diz o mês e os arquivos. Saída 0 tudo certo; 1 falha (última linha `FALHAS:`).

Roda: manual (python -m scripts.montar_acervo_pessoa), na VM de casa, uma vez por mês de retrato novo; coberto
por test_montar_acervo_pessoa.py.
"""

import argparse
import json
import logging
import shutil
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from base import receita_pessoa
from base.receita_retrato import ErroDeLayout
from scripts import carga_receita_mes as carga
from scripts.montar_historico_do_cnpj import _arquivos, _ler, _repartir, _zips_do_mes

log = logging.getLogger("tickerlab.montar_acervo_pessoa")

NOME_DA_PASTA = "acervo_pessoa"
SOCIOS = "socios_pf"
ARQUIVOS_DE_SOCIOS = "Socios"
TRABALHO = "_trabalho"
MANIFESTO = "manifesto.json"
MES = "mes_do_retrato"
CHAVE = ["cnpj_basico", "nome_socio", "qualificacao", "data_entrada"]
TAMANHO_MAXIMO_DO_RESUMO = 300


class DestinoRecusadoError(ValueError):
    """O destino não é uma pasta `acervo_pessoa` fora do acervo."""


class ZipAusenteError(FileNotFoundError):
    """Um `Socios*.zip` do manifesto não está no bruto, ou o SHA-256 dele não confere."""


def conferir_destino(cnpj: Path, destino: Path) -> None:
    """Recusa o destino com outro nome ou dentro do acervo (que é copiado para outros lugares)."""
    acervo = cnpj.resolve().parents[1]  # <acervo>/base/cnpj
    alvo = destino.resolve()
    if alvo.name != NOME_DA_PASTA:
        raise DestinoRecusadoError(f"o destino tem de se chamar {NOME_DA_PASTA}")
    if alvo.is_relative_to(acervo):
        raise DestinoRecusadoError("o destino não pode ficar dentro do acervo")


def zips_de_socios(cnpj: Path, bruto: Path) -> tuple[str, dict[str, Path]]:
    """O mês vigente e, por nome, o `Socios*.zip` guardado no bruto (achado pelo SHA-256 do manifesto)."""
    manifesto = json.loads((cnpj / carga.MANIFESTO).read_text(encoding="utf-8"))
    mes = max(manifesto["meses"])
    achados = {}
    for nome, sha in _zips_do_mes(manifesto, mes, ARQUIVOS_DE_SOCIOS).items():
        guardados = sorted(bruto.glob(f"*/{sha}.zip"))
        if not guardados:
            raise ZipAusenteError(f"{nome} de {mes} não está no bruto")
        achados[nome] = guardados[0]
    if not achados:
        raise ZipAusenteError(f"o manifesto de {mes} não tem {ARQUIVOS_DE_SOCIOS}*.zip")
    return mes, achados


def _repartir_os_zips(zips: dict[str, Path], trabalho: Path) -> Counter[str]:
    descartes: Counter[str] = Counter()
    for numero, (nome, arquivo) in enumerate(sorted(zips.items())):
        for parte_numero, parte in enumerate(receita_pessoa.ler_socios_pf(arquivo)):
            descartes += parte.descartes
            _repartir(parte.socios, trabalho, f"{numero:02d}-{parte_numero:04d}")
        log.info("lido %s", nome)
    return descartes


def _gravar_prefixos(trabalho: Path, pronta: Path, mes: str) -> dict[str, int]:
    pronta.mkdir(parents=True)
    linhas, empresas = 0, 0
    for pasta in sorted(p for p in trabalho.iterdir() if p.is_dir()):
        socios = _ler(_arquivos(pasta))
        if socios is None or socios.empty:
            continue
        socios = socios.drop_duplicates(CHAVE).sort_values(CHAVE, na_position="last")
        socios.assign(**{MES: mes}).to_parquet(
            pronta / f"{pasta.name}.parquet", index=False
        )
        linhas += len(socios)
        empresas += socios["cnpj_basico"].nunique()
    return {"linhas": linhas, "empresas": empresas}


def _trocar(pronta: Path, atual: Path) -> None:
    shutil.rmtree(atual, ignore_errors=True)
    pronta.rename(atual)


def montar(
    destino: Path,
    mes: str,
    zips: dict[str, Path],
    shas: dict[str, str],
    agora: datetime,
) -> dict:
    """Grava `socios_pf/` do `mes` e o manifesto; devolve o manifesto (só números e SHA-256)."""
    for nome, arquivo in zips.items():
        if carga.sha256_do_arquivo(arquivo) != shas[nome]:
            raise ZipAusenteError(f"o SHA-256 de {nome} não confere com o manifesto")
    destino.mkdir(parents=True, exist_ok=True)
    trabalho = destino / TRABALHO
    shutil.rmtree(trabalho, ignore_errors=True)
    try:
        descartes = _repartir_os_zips(zips, trabalho / "partes")
        contagem = _gravar_prefixos(trabalho / "partes", trabalho / SOCIOS, mes)
        _trocar(trabalho / SOCIOS, destino / SOCIOS)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)
    manifesto = {
        MES: mes,
        "montado_em": agora.isoformat(),
        "tabelas": {SOCIOS: contagem},
        "descartes": {
            motivo: descartes.get(motivo, 0) for motivo in receita_pessoa.MOTIVOS
        },
        "origens": dict(sorted(shas.items())),
    }
    (destino / MANIFESTO).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifesto


def carregar(cnpj: Path, bruto: Path, destino: Path, agora: datetime) -> dict:
    """Confere o destino, acha os ZIPs do mês vigente no bruto e monta."""
    conferir_destino(cnpj, destino)
    mes, zips = zips_de_socios(cnpj, bruto)
    shas = {nome: arquivo.stem for nome, arquivo in zips.items()}
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
        mes, zips = zips_de_socios(opcoes.cnpj, opcoes.bruto)
        print(f"mês do retrato vigente: {mes}; arquivos: {', '.join(sorted(zips))}")
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
