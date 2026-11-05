"""Monta o histórico datado do CNPJ (linha 686 da fila; `base/cnpj_historico.py`). Roda no servidor de casa.

    python -m scripts.montar_historico_do_cnpj simples --cnpj <base do CNPJ> --destino <acervo>/base
    python -m scripts.montar_historico_do_cnpj empresas --destino <acervo>/base --ensaio   (só lista os meses)
    python -m scripts.montar_historico_do_cnpj empresas --destino <acervo>/base [--ate AAAA-MM]

`simples`: `cnpj_simples_historico/<xx>.parquet` (um arquivo pelos 2 primeiros caracteres da raiz), do vigente
e das mudanças que a carga do CNPJ já guardou (`scripts/carga_receita_mes.py`). As mudanças são repartidas
pelo prefixo numa pasta de trabalho (cada mês é lido uma vez só); depois cada prefixo vira versões e a última
versão de cada raiz é conferida com o vigente (`HistoricoNaoConfere` para tudo). Remontar sem mês novo não
regrava nada (`gravar_se_mudou`).

`empresas`: `cnpj_empresas_historico/<xx>.parquet`, um mês por vez, em ordem, retomando do último gravado
(`meses.json` da pasta). Baixa os `Empresas*.zip` do mês (fonte oficial, ~500 MB), lê só raiz, razão social
e natureza (a razão social de pessoa nunca sai do leitor), acrescenta as versões novas e apaga os ZIPs.
Uma queda no meio deixa prefixos já com o mês: repetir o mês não acrescenta nada a eles.

Cada linha leva o SHA-256 do ZIP do mês de onde veio (`origem_sha256`, vazio na versão "saiu do arquivo"),
quando foi montada e a versão do código. Saída 0 tudo certo; 1 falha (última linha `FALHAS:`).
"""

import argparse
import json
import logging
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from base import cnpj_historico as historico
from base.parquet import gravar_se_mudou
from base.receita_retrato import ErroDeLayout
from scripts import carga_receita_mes as carga
from src.versao_do_codigo import versao_do_codigo

if TYPE_CHECKING:
    from base.arquivo.cliente_http import ClienteHttp

log = logging.getLogger("tickerlab.montar_historico_do_cnpj")

SIMPLES = "cnpj_simples_historico"
EMPRESAS = "cnpj_empresas_historico"
ZIP_DO_SIMPLES = "Simples"
ZIP_DE_EMPRESAS = "Empresas"
MESES = "meses.json"
TRABALHO = "_trabalho"
PREFIXO = carga.PREFIXO
CHAVE = list(historico.CHAVE)
ORDEM = [*CHAVE, historico.MES]
CARIMBOS = ("montado_em", "versao_do_codigo")
TAMANHO_MAXIMO_DO_RESUMO = 300


class MesForaDeOrdem(RuntimeError):
    """O mês não vem depois do último gravado: o histórico anda para a frente, um mês por vez."""


# --- comum -----------------------------------------------------------------------------------------
def _arquivos(caminho: Path) -> list[Path]:
    """Um mês ou um prefixo pode ser um arquivo só ou uma pasta de partes."""
    if caminho.is_file():
        return [caminho]
    return sorted(caminho.glob("*.parquet")) if caminho.is_dir() else []


def _ler(arquivos: Iterable[Path]) -> pd.DataFrame | None:
    partes = [pd.read_parquet(a) for a in arquivos]
    return pd.concat(partes, ignore_index=True) if partes else None


def _repartir(tabela: pd.DataFrame, destino: Path, nome: str) -> None:
    for prefixo, parte in tabela.groupby(tabela["cnpj_basico"].str[:PREFIXO]):
        pasta = destino / str(prefixo)
        pasta.mkdir(parents=True, exist_ok=True)
        parte.to_parquet(pasta / f"{nome}.parquet", index=False)


def _zips_do_mes(manifesto: dict, mes: str, nome: str) -> dict[str, str]:
    arquivos = manifesto["meses"][mes].get("arquivos", {})
    return {a: sha for a, sha in sorted(arquivos.items()) if a.startswith(nome)}


def _origens(zips_por_mes: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"url": f"{carga.ENDERECO_DOS_ZIPS}/{mes}/{nome}", "sha256": sha}
        for mes, zips in sorted(zips_por_mes.items())
        for nome, sha in zips.items()
    ]


def _carimbar(
    versoes: pd.DataFrame, sha_do_mes: pd.Series, agora: datetime
) -> pd.DataFrame:
    return versoes.assign(
        origem_sha256=sha_do_mes.fillna("").to_numpy(),
        montado_em=agora.isoformat(),
        versao_do_codigo=versao_do_codigo(),
    )


# --- Simples ---------------------------------------------------------------------------------------
def _repartir_mudancas(cnpj: Path, trabalho: Path) -> None:
    pasta = cnpj / "mudancas" / "simples"
    meses = sorted({p.name.removesuffix(".parquet") for p in pasta.glob("*")} - {""})
    for mes in (m for m in meses if not m.endswith(".json")):
        arquivos = _arquivos(pasta / f"{mes}.parquet") or _arquivos(pasta / mes)
        for numero, arquivo in enumerate(arquivos):
            _repartir(pd.read_parquet(arquivo), trabalho, f"{mes}-{numero:03d}")


def _prefixos(*pastas: Path) -> list[str]:
    nomes = {
        p.name.removesuffix(".parquet")
        for pasta in pastas
        if pasta.is_dir()
        for p in pasta.iterdir()
    }
    return sorted(n for n in nomes if len(n) == PREFIXO)


def montar_simples(cnpj: Path, destino: Path, agora: datetime) -> dict[str, int]:
    """`<destino>/cnpj_simples_historico/<xx>.parquet` do vigente e das mudanças da base do CNPJ."""
    manifesto = json.loads((cnpj / carga.MANIFESTO).read_text(encoding="utf-8"))
    meses = sorted(manifesto["meses"])
    zips = {m: _zips_do_mes(manifesto, m, ZIP_DO_SIMPLES) for m in meses}
    sha_do_mes = {m: next(iter(z.values()), "") for m, z in zips.items()}
    origens = _origens(zips)
    trabalho = destino / SIMPLES / TRABALHO
    shutil.rmtree(trabalho, ignore_errors=True)
    vigente = cnpj / "vigente" / "simples"
    contagem: dict[str, int] = {}
    try:
        _repartir_mudancas(cnpj, trabalho)
        for prefixo in _prefixos(vigente, trabalho):
            atual = _ler(
                _arquivos(vigente / f"{prefixo}.parquet")
                or _arquivos(vigente / prefixo)
            )
            atual = (
                atual
                if atual is not None
                else pd.DataFrame(
                    columns=[*historico.CHAVE, *historico.CAMPOS_DO_SIMPLES]
                )
            )
            mudancas = _ler(_arquivos(trabalho / prefixo))
            versoes = historico.versoes_das_mudancas(
                atual,
                mudancas if mudancas is not None else pd.DataFrame(),
                historico.CHAVE,
                historico.CAMPOS_DO_SIMPLES,
                meses[0],
            )
            historico.conferir_com_o_vigente(
                versoes, atual, historico.CHAVE, historico.CAMPOS_DO_SIMPLES
            )
            versoes = _carimbar(versoes, versoes[historico.MES].map(sha_do_mes), agora)
            gravar_se_mudou(
                versoes, destino / SIMPLES / prefixo, origens, ORDEM, carimbos=CARIMBOS
            )
            contagem[prefixo] = len(versoes)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)
    log.info(
        "simples: %d versões em %d prefixos", sum(contagem.values()), len(contagem)
    )
    return contagem


# --- Empresas --------------------------------------------------------------------------------------
def _meses_gravados(pasta: Path) -> dict[str, dict[str, str]]:
    arquivo = pasta / MESES
    if not arquivo.is_file():
        return {}
    return json.loads(arquivo.read_text(encoding="utf-8"))["meses"]


def pendentes(meses: Iterable[str], destino: Path) -> list[str]:
    """Os meses depois do último gravado, em ordem (retoma de onde parou)."""
    gravados = _meses_gravados(destino / EMPRESAS)
    ultimo = max(gravados) if gravados else None
    return sorted(m for m in meses if ultimo is None or m > ultimo)


def processar_mes_de_empresas(
    mes: str, destino: Path, zips: list[Path], agora: datetime
) -> int:
    """Acrescenta ao histórico as versões novas que os `Empresas*.zip` do mês trazem; devolve quantas."""
    pasta = destino / EMPRESAS
    gravados = _meses_gravados(pasta)
    if gravados and mes <= max(gravados):
        raise MesForaDeOrdem(f"último gravado {max(gravados)}; pedido {mes}")
    arquivos = {z.name: carga.sha256_do_arquivo(z) for z in zips}
    trabalho = pasta / TRABALHO
    shutil.rmtree(trabalho, ignore_errors=True)
    novas_no_mes = 0
    try:
        for numero, arquivo in enumerate(sorted(zips)):
            for parte_numero, parte in enumerate(historico.ler_empresas(arquivo)):
                parte["origem_sha256"] = arquivos[arquivo.name]
                _repartir(parte, trabalho, f"{numero:02d}-{parte_numero:04d}")
        origens = _origens(gravados | {mes: arquivos})
        for prefixo in _prefixos(trabalho, pasta):
            retrato = _ler(_arquivos(trabalho / prefixo))
            colunas = [*historico.CHAVE, *historico.CAMPOS_DA_EMPRESA, "origem_sha256"]
            retrato = retrato if retrato is not None else pd.DataFrame(columns=colunas)
            anterior = _ler(_arquivos(pasta / f"{prefixo}.parquet"))
            novas = historico.acrescentar_retrato(
                anterior, retrato, historico.CHAVE, historico.CAMPOS_DA_EMPRESA, mes
            )
            if novas.empty:
                continue
            sha = novas[CHAVE].merge(
                retrato.drop_duplicates(CHAVE, keep="last"),
                on=CHAVE,
                how="left",
            )["origem_sha256"]
            novas = _carimbar(novas, sha, agora)
            juntas = (
                novas
                if anterior is None
                else pd.concat([anterior, novas], ignore_index=True)
            )
            gravar_se_mudou(juntas, pasta / prefixo, origens, ORDEM, carimbos=CARIMBOS)
            novas_no_mes += len(novas)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / MESES).write_text(
        json.dumps({"meses": gravados | {mes: arquivos}}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    log.info("empresas %s: %d versões novas", mes, novas_no_mes)
    return novas_no_mes


def carregar_empresas(
    meses: Iterable[str],
    destino: Path,
    baixar: Callable[[str, Path], list[Path]],
    agora: Callable[[], datetime],
) -> None:
    """Baixa e acrescenta cada mês pendente, em ordem; os ZIPs ficam numa pasta temporária."""
    for mes in pendentes(meses, destino):
        destino.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destino) as temporaria:
            zips = baixar(mes, Path(temporaria))
            processar_mes_de_empresas(mes, destino, zips, agora())


def _baixar_empresas(
    cliente: "ClienteHttp", mes: str, temporaria: Path
) -> list[Path]:  # pragma: no cover - rede
    from base.arquivo.fontes import arquivos_do_mes
    from scripts import carga_receita_retrato as retrato

    zips = []
    for alvo in retrato._sem_os_cortados(
        arquivos_do_mes(cliente, mes, (ZIP_DE_EMPRESAS,))
    ):
        caminho = temporaria / retrato._nome_do_zip(alvo)
        retrato._baixar_zip_inteiro(cliente, alvo.url, caminho)
        zips.append(caminho)
    return zips


def main(argv: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    tarefas = analisador.add_subparsers(dest="tarefa", required=True)
    simples = tarefas.add_parser("simples")
    simples.add_argument(
        "--cnpj", type=Path, required=True, help="a base do CNPJ (vigente e mudanças)"
    )
    simples.add_argument("--destino", type=Path, required=True)
    empresas = tarefas.add_parser("empresas")
    empresas.add_argument("--destino", type=Path, required=True)
    empresas.add_argument("--ate", default=None, help="último mês (AAAA-MM)")
    empresas.add_argument("--ensaio", action="store_true")
    opcoes = analisador.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        if opcoes.tarefa == "simples":
            montar_simples(opcoes.cnpj, opcoes.destino, datetime.now(UTC))
            return 0
        return _main_empresas(opcoes)  # pragma: no cover - rede
    except (historico.HistoricoNaoConfere, ErroDeLayout, MesForaDeOrdem) as erro:
        print(
            f"FALHAS: histórico do CNPJ: {type(erro).__name__}: {erro}"[
                :TAMANHO_MAXIMO_DO_RESUMO
            ]
        )
        return 1


def _main_empresas(opcoes: argparse.Namespace) -> int:  # pragma: no cover - rede
    from base.arquivo.cliente_http import ClienteHttp
    from base.arquivo.fontes import meses_do_cnpj

    cliente = ClienteHttp()
    meses = [m for m in meses_do_cnpj(cliente) if opcoes.ate is None or m <= opcoes.ate]
    log.info(
        "meses pendentes: %s", ", ".join(pendentes(meses, opcoes.destino)) or "nenhum"
    )
    if not opcoes.ensaio:
        carregar_empresas(
            meses,
            opcoes.destino,
            lambda m, t: _baixar_empresas(cliente, m, t),
            lambda: datetime.now(UTC),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
