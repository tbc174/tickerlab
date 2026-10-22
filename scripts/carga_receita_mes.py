"""Carga mensal do CNPJ na base (ADR 0106, PR 5): um mês por vez, em partes, retomando do último gravado.

Cada mês é lido em partes e repartido pelos 2 primeiros caracteres da raiz (a memória fica pequena). Para
cada repartição compara-se o que já estava (`vigente/<tabela>/<xx>.parquet`) com o mês novo e grava-se só o
que mudou (`mudancas/<tabela>/<AAAA-MM>.parquet`, `receita_diff`). O primeiro mês vira o retrato inicial.

Os nomes dos sócios pessoa física vão só para `<restrita>/pessoas/<xx>.parquet` (o vigente do mês; quem
saiu sai dali), nunca para `vigente/` nem para `mudancas/`, onde o sócio é só o `id_pessoa`. Quem se opôs
(`<restrita>/pessoas_oposicoes.parquet`) não volta: fica fora de `pessoas` e com o id vazio no QSA, como a
lápide deixou (`base.pessoas.oposicoes`). Tudo do mês é
montado numa pasta de trabalho e só então trocado pelo vigente: queda no meio não deixa mês pela metade.
O `manifesto.json` guarda, por mês, o SHA-256 de cada ZIP lido.
"""

import hashlib
import json
import shutil
from collections.abc import Callable, Iterable
from pathlib import Path

import pandas as pd

from base.parquet import sem_os_ids
from base.pessoas.oposicoes import ids_opostos
from base.pessoas.tabelas import montar_pessoas, sem_opostos
from base.receita_diff import CHAVE_DO_QSA, diff, qsa_para_diff
from base.receita_retrato import ParteDoQsa

FONTE = "rfb-cnpj"
LIVRE_MINIMO = 30 * 1024**3
TAMANHO_DO_PEDACO = 1024 * 1024
PREFIXO = 2
CHAVES = {
    "estabelecimentos": ["cnpj"],
    "simples": ["cnpj_basico"],
    "qsa": CHAVE_DO_QSA,
}
RAIZ_DA_PARTICAO = {
    "estabelecimentos": "cnpj",
    "simples": "cnpj_basico",
    "qsa": "cnpj_basico",
}
MANIFESTO = "manifesto.json"
TRABALHO = "_novo"


class PoucoDisco(RuntimeError):
    """Menos de 30 GB livres: a carga não começa (70 milhões de linhas por mês)."""


class MesForaDeOrdem(RuntimeError):
    """O mês não é o seguinte ao último gravado: a carga anda um mês por vez, em ordem."""


def _livre(pasta: Path) -> int:
    while not pasta.exists() and pasta != pasta.parent:
        pasta = pasta.parent
    return shutil.disk_usage(pasta).free


def exigir_disco(pasta: Path, livre: Callable[[Path], int] = _livre) -> None:
    if livre(pasta) < LIVRE_MINIMO:
        raise PoucoDisco("menos de 30 GB livres: a carga do CNPJ não começa")


def sha256_do_arquivo(arquivo: Path) -> str:
    resumo = hashlib.sha256()
    with arquivo.open("rb") as aberto:
        while pedaco := aberto.read(TAMANHO_DO_PEDACO):
            resumo.update(pedaco)
    return resumo.hexdigest()


def _manifesto(pasta: Path) -> dict:
    arquivo = pasta / MANIFESTO
    if not arquivo.is_file():
        return {"meses": {}}
    return json.loads(arquivo.read_text(encoding="utf-8"))


def ultimo_mes(pasta: Path) -> str | None:
    """O último mês gravado (`AAAA-MM`), ou None se a carga ainda não começou."""
    meses = _manifesto(pasta)["meses"]
    return max(meses) if meses else None


def _seguinte(mes: str) -> str:
    ano, numero = int(mes[:4]), int(mes[5:])
    return f"{ano + numero // 12}-{numero % 12 + 1:02d}"


def pendentes(meses: Iterable[str], pasta: Path) -> list[str]:
    """Os meses ainda não gravados, em ordem (retoma do último)."""
    ultimo = ultimo_mes(pasta)
    return sorted(m for m in meses if ultimo is None or m > ultimo)


def _repartir(partes: Iterable[pd.DataFrame], raiz: str, destino: Path) -> None:
    for numero, parte in enumerate(partes):
        for prefixo, grupo in parte.groupby(parte[raiz].str[:PREFIXO]):
            pasta = destino / str(prefixo)
            pasta.mkdir(parents=True, exist_ok=True)
            grupo.to_parquet(
                pasta / f"{len(list(pasta.iterdir())):05d}-{numero}.parquet"
            )


def _ler_prefixo(pasta: Path) -> pd.DataFrame | None:
    arquivos = sorted(pasta.glob("*.parquet")) if pasta.is_dir() else []
    if not arquivos:
        return None
    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)


def _aplicar(
    tabela: str, mes: str, trabalho: Path, vigente: Path, primeiro: bool
) -> pd.DataFrame | None:
    """Passa o mês novo (repartido em `trabalho/<tabela>`) para o vigente e devolve as mudanças."""
    novo, antigo = trabalho / tabela, vigente / tabela
    saida = trabalho / "vigente" / tabela
    saida.mkdir(parents=True, exist_ok=True)
    prefixos = {p.name for p in novo.iterdir()} if novo.is_dir() else set()
    if not primeiro:
        prefixos |= {a.stem for a in antigo.glob("*.parquet")}
    mudancas = []
    for prefixo in sorted(prefixos):
        depois = _ler_prefixo(novo / prefixo)
        antes = None if primeiro else _ler_prefixo_vigente(antigo, prefixo)
        if depois is None:
            if antes is None:
                continue
            depois = antes.iloc[0:0]
        if not primeiro:
            antes = antes if antes is not None else depois.iloc[0:0]
            mudancas.append(diff(antes, depois, CHAVES[tabela], mes))
        depois.to_parquet(saida / f"{prefixo}.parquet")
    return pd.concat(mudancas, ignore_index=True) if mudancas else None


def _ler_prefixo_vigente(antigo: Path, prefixo: str) -> pd.DataFrame | None:
    arquivo = antigo / f"{prefixo}.parquet"
    return pd.read_parquet(arquivo) if arquivo.is_file() else None


def _trocar(novo: Path, atual: Path) -> None:
    if atual.exists():
        shutil.rmtree(atual)
    atual.parent.mkdir(parents=True, exist_ok=True)
    novo.rename(atual)


def _sem_os_opostos(socios: pd.DataFrame, opostos: set[str]) -> pd.DataFrame:
    """O QSA do mês com o id de quem se opôs vazio, igual ao que a lápide deixou no vigente."""
    sem = sem_os_ids(socios, opostos) if opostos else None
    return socios if sem is None else sem


def processar_mes(
    mes: str,
    pasta: Path,
    restrita: Path,
    *,
    estabelecimentos: Iterable[pd.DataFrame],
    simples: Iterable[pd.DataFrame],
    qsa: Iterable[ParteDoQsa],
    chave_de_pessoas: bytes,
    arquivos: dict[str, str],
) -> None:
    """Lê o mês, grava o vigente, as mudanças, as pessoas (restrito) e o manifesto. Um mês, em ordem."""
    ultimo = ultimo_mes(pasta)
    if ultimo is not None and mes != _seguinte(ultimo):
        raise MesForaDeOrdem(f"último gravado {ultimo}; pedido {mes}")
    trabalho, trabalho_restrito = pasta / TRABALHO, restrita / TRABALHO
    for pasta_de_trabalho in (trabalho, trabalho_restrito):
        shutil.rmtree(pasta_de_trabalho, ignore_errors=True)
    try:
        _repartir(estabelecimentos, "cnpj", trabalho / "estabelecimentos")
        _repartir(simples, "cnpj_basico", trabalho / "simples")
        opostos = ids_opostos(restrita)
        for parte in qsa:
            if parte.socios.empty:
                continue
            # as pessoas primeiro: CPF inteiro quebra aqui, antes de qualquer coisa ser gravada
            pessoas = sem_opostos(
                montar_pessoas(parte.pessoas_brutas, FONTE, chave_de_pessoas), opostos
            )
            if len(pessoas):
                _repartir([pessoas], "cnpj_basico", trabalho_restrito / "pessoas")
            socios = qsa_para_diff(parte, chave_de_pessoas)
            _repartir(
                [_sem_os_opostos(socios, opostos)], "cnpj_basico", trabalho / "qsa"
            )
        vigente = pasta / "vigente"
        mudancas = {
            t: _aplicar(t, mes, trabalho, vigente, ultimo is None) for t in CHAVES
        }
    except BaseException:
        shutil.rmtree(trabalho, ignore_errors=True)
        shutil.rmtree(trabalho_restrito, ignore_errors=True)
        raise
    for tabela, quadro in mudancas.items():
        if quadro is not None and not quadro.empty:
            destino = pasta / "mudancas" / tabela / f"{mes}.parquet"
            destino.parent.mkdir(parents=True, exist_ok=True)
            quadro.to_parquet(destino)
    (trabalho_restrito / "pessoas").mkdir(parents=True, exist_ok=True)
    _trocar(trabalho / "vigente", vigente)
    _trocar(trabalho_restrito / "pessoas", restrita / "pessoas")
    shutil.rmtree(trabalho, ignore_errors=True)
    shutil.rmtree(trabalho_restrito, ignore_errors=True)
    manifesto = _manifesto(pasta)
    manifesto["meses"][mes] = {
        "arquivos": arquivos,
        "mudancas": {t: 0 if q is None else len(q) for t, q in mudancas.items()},
    }
    (pasta / MANIFESTO).write_text(
        json.dumps(manifesto, indent=2, sort_keys=True), encoding="utf-8"
    )
