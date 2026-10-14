"""Barras de 1 minuto e selo dos pregões da B3 guardados pelo arquivista (plano dos intradiários
grátis, PR 2; ADR 0073). Só pesquisa (ADR 0019): fica no acervo, fora do banco do app.

    python -m scripts.barras_b3_do_dia                       (os pregões que faltam ou mudaram)
    python -m scripts.barras_b3_do_dia --pregao 2026-10-13   (refaz um)

Roda no servidor de casa depois do arquivista das 2h, que guarda os negócios (`b3-negocios`), o
boletim PR (`b3-boletim-pr`) e o COTAHIST do dia (`b3-cotahist-dia`). Acha os arquivos pelo
manifesto do acervo (a versão mais nova de cada um) e processa o pregão que ainda não tem resumo ou
cujo resumo foi feito com outros arquivos (a B3 corrigiu o dia, o boletim chegou depois). Grava em
`<acervo>/intradiario/b3/`:

- `barras/AAAA-MM-DD.parquet`: uma linha por instrumento e minuto (`base/intradiario_b3.py`);
- `selo/AAAA-MM-DD.parquet`: uma linha por instrumento, com o selo e os dois lados de cada campo;
- `selo/AAAA-MM-DD.json`: o resumo (selo do dia, SHA-256 de cada arquivo lido, contagens).

Pregão `incompleto` faz a última linha da saída ser `FALHAS: ...` e a saída 1 (o `rodar-tarefa.sh`
leva ao Kuma). Avisa uma vez: o mesmo arquivo não é refeito; uma versão nova é.
"""

import argparse
import json
import logging
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from base import intradiario_b3 as b3
from base.parquet import gravar_atomico
from src import acervo
from src.versao_do_codigo import versao_do_codigo

FONTE_DOS_NEGOCIOS = "b3-negocios"
FONTE_DO_PR = "b3-boletim-pr"
FONTE_DO_COTAHIST = "b3-cotahist-dia"
FONTES = (FONTE_DOS_NEGOCIOS, FONTE_DO_PR, FONTE_DO_COTAHIST)
NOME_DA_TAREFA = "b3-barras"

log = logging.getLogger("barras_b3_do_dia")


@dataclass(frozen=True)
class Guardado:
    caminho: Path
    sha256: str
    hora: str


def arquivos_no_acervo(pasta: Path) -> dict[str, dict[date, Guardado]]:
    """Por fonte e pregão, a versão mais nova guardada (pelo manifesto do arquivista)."""
    achados: dict[str, dict[date, Guardado]] = {fonte: {} for fonte in FONTES}
    for manifesto in sorted((pasta / "manifesto").glob("*.jsonl")):
        for texto in manifesto.read_text("utf-8").splitlines():
            linha = json.loads(texto)
            if linha.get("fonte") not in achados or not linha.get("caminho"):
                continue
            pregao = b3.pregao_do_endereco(linha["url"])
            novo = Guardado(pasta / linha["caminho"], linha["sha256"], linha["hora"])
            atual = achados[linha["fonte"]].get(pregao)
            if atual is None or novo.hora >= atual.hora:
                achados[linha["fonte"]][pregao] = novo
    return achados


def _entradas(
    pregao: date, arquivos: dict[str, dict[date, Guardado]]
) -> dict[str, Guardado | None]:
    """Os arquivos que o pregão lê: o dele, o do pregão anterior guardado, o PR e o COTAHIST."""
    negocios = arquivos[FONTE_DOS_NEGOCIOS]
    anteriores = [dia for dia in negocios if dia < pregao]
    return {
        "arquivo": negocios[pregao],
        "anterior": negocios[max(anteriores)] if anteriores else None,
        "pr": arquivos[FONTE_DO_PR].get(pregao),
        "cotahist": arquivos[FONTE_DO_COTAHIST].get(pregao),
    }


def _shas(entradas: dict[str, Guardado | None]) -> dict[str, str | None]:
    return {
        f"sha256_do_{nome}": guardado.sha256 if guardado else None
        for nome, guardado in entradas.items()
    }


def pregoes_a_processar(
    arquivos: dict[str, dict[date, Guardado]], forcar: date | None = None
) -> list[date]:
    """Pregões sem resumo, ou com resumo feito de outros arquivos ou com outra regra; do mais antigo
    ao mais novo."""
    if forcar is not None:
        return [forcar]
    pendentes = []
    for pregao in sorted(arquivos[FONTE_DOS_NEGOCIOS]):
        resumo = b3.resumo_guardado(pregao)
        atuais = _shas(_entradas(pregao, arquivos))
        if (
            resumo is None
            or resumo.get("versao_da_regra") != b3.VERSAO_DA_REGRA
            or any(resumo.get(k) != v for k, v in atuais.items())
        ):
            pendentes.append(pregao)
    return pendentes


def _contagem(conferencia: pd.DataFrame) -> dict[str, int]:
    return dict(Counter(conferencia["selo"]))


def processar_pregao(
    pregao: date, arquivos: dict[str, dict[date, Guardado]], pasta: Path
) -> dict:
    """Monta as barras e o selo do pregão, grava os três arquivos e devolve o resumo."""
    inicio = time.perf_counter()
    entradas = _entradas(pregao, arquivos)
    zips = [g.caminho for g in (entradas["anterior"], entradas["arquivo"]) if g]
    barras = b3.barras_do_pregao(pregao, zips)
    pr = b3.ler_boletim_pr(entradas["pr"].caminho) if entradas["pr"] else None
    cotahist = (
        b3.ler_cotahist(entradas["cotahist"].caminho) if entradas["cotahist"] else None
    )
    conferencia = b3.conferir_dia(barras, b3.boletim_do_dia(pr, cotahist))
    do_a_vista = b3.a_vista(cotahist) if cotahist is not None else set()
    destino = pasta / b3.PASTA_NO_ACERVO
    for subpasta in ("barras", "selo"):
        (destino / subpasta).mkdir(parents=True, exist_ok=True)
    nome = f"{pregao.isoformat()}.parquet"
    gravar_atomico(
        destino / "barras" / nome, lambda p: barras.to_parquet(p, index=False)
    )
    gravar_atomico(
        destino / "selo" / nome, lambda p: conferencia.to_parquet(p, index=False)
    )
    resumo = {
        "pregao": pregao.isoformat(),
        "selo_do_dia": b3.selo_do_dia(conferencia, do_a_vista),
        "versao_da_regra": b3.VERSAO_DA_REGRA,
        **_shas(entradas),
        "instrumentos": _contagem(conferencia),
        "a_vista": _contagem(
            conferencia[conferencia["simbolo"].isin(list(do_a_vista))]
        ),
        "barras": len(barras),
        "segundos": round(time.perf_counter() - inicio, 1),
        "processado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "versao_do_codigo": versao_do_codigo(),
    }
    texto = json.dumps(resumo, ensure_ascii=False, indent=1)
    gravar_atomico(
        b3.caminho_do_resumo(pregao, pasta),
        lambda p: p.write_text(texto, "utf-8"),
    )
    return resumo


def _motivo(resumo: dict) -> str:
    do_a_vista = resumo["a_vista"]
    partes = [
        f"{do_a_vista[selo]} {selo}s"
        for selo in (b3.SELO_AUSENTE, b3.SELO_INCOMPLETO)
        if do_a_vista.get(selo)
    ]
    return (
        f"{NOME_DA_TAREFA} {resumo['pregao']} incompleto (à vista: {', '.join(partes)})"
    )


def alarmes_da_janela(
    arquivos: dict[str, dict[date, Guardado]], hoje: date
) -> list[str]:
    """Pregões que vão sumir da B3 sem estar salvos, e o COTAHIST parado (PR 3 do plano).

    Pregão = dia com COTAHIST ou com o arquivo de negócios guardado. A cópia do VPS entra no
    acervo de casa pela reconciliação diária (PR 4), então "salvo" é "no acervo de casa".
    """
    salvos = set(arquivos[FONTE_DOS_NEGOCIOS])
    pregoes = sorted(set(arquivos[FONTE_DO_COTAHIST]) | salvos)
    alarmes = [
        f"{FONTE_DOS_NEGOCIOS} {pregao} não está salvo e some da B3 em {faltam} "
        + ("pregão" if faltam == 1 else "pregões")
        for pregao, faltam in b3.dias_em_risco(pregoes, salvos)
    ]
    com_cotahist = sorted(arquivos[FONTE_DO_COTAHIST])
    if b3.cotahist_atrasado(com_cotahist, hoje):
        ultimo = com_cotahist[-1].isoformat() if com_cotahist else "sempre"
        alarmes.append(
            f"{FONTE_DO_COTAHIST} sem pregão novo desde {ultimo} (o arquivista parou?)"
        )
    return alarmes


def _opcoes(argumentos: list[str] | None) -> argparse.Namespace:
    leitor = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    leitor.add_argument("--pregao", type=date.fromisoformat, default=None)
    leitor.add_argument(
        "--hoje", type=date.fromisoformat, default=None, help="para testes"
    )
    return leitor.parse_args(argumentos)


def main(argumentos: list[str] | None = None) -> int:
    """0 = tudo certo (inclusive nada a fazer ou boletim ainda não chegou); 1 = pregão incompleto,
    pregão perto de sumir sem estar salvo ou COTAHIST parado."""
    opcoes = _opcoes(argumentos)
    pasta = acervo.pasta_do_acervo()
    if pasta is None:
        print("Acervo desligado: nada a processar.")
        return 0
    hoje = opcoes.hoje or datetime.now(ZoneInfo(b3.FUSO_DA_B3)).date()
    arquivos = arquivos_no_acervo(pasta)
    falhas = _processar(pregoes_a_processar(arquivos, opcoes.pregao), arquivos, pasta)
    falhas += alarmes_da_janela(arquivos, hoje)
    if falhas:
        print("FALHAS: " + "; ".join(falhas))
        return 1
    return 0


def _processar(
    pregoes: list[date], arquivos: dict[str, dict[date, Guardado]], pasta: Path
) -> list[str]:
    """Processa os pregões e devolve os motivos dos que saíram incompletos."""
    if not pregoes:
        print("Nada a processar: todo pregão guardado já tem barras e selo.")
        return []
    falhas = []
    for pregao in pregoes:
        resumo = processar_pregao(pregao, arquivos, pasta)
        print(
            f"{pregao}: {resumo['selo_do_dia']}, {resumo['barras']:,} barras, "
            f"instrumentos {resumo['instrumentos']}, à vista {resumo['a_vista']}, "
            f"{resumo['segundos']:.0f} s",
            flush=True,
        )
        if resumo["selo_do_dia"] == b3.SELO_INCOMPLETO:
            falhas.append(_motivo(resumo))
    return falhas


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
