"""Coletor diário do IEX HIST: barras de 1 minuto do S&P 500 (F3 dos dados intradiários).

    python -m scripts.coletar_iex_do_dia                 (os dias úteis recentes que faltam)
    python -m scripts.coletar_iex_do_dia --data 2026-10-09
    python -m scripts.coletar_iex_do_dia --desde 2025-10-13 --maximo 20 --minutos 160   (carga)

Roda no VPS de madrugada, num contêiner próprio com limite de memória (não no do app). O arquivo
TOPS do dia (~9 GB comprimido) é lido enquanto baixa e não fica no disco; só as barras ficam, em
`dados_locais/intradiario/iex/AAAA-MM-DD.parquet`, com um resumo `.json` ao lado (conferências e
o SHA-256 do Parquet). Gravação atômica: o arquivo só aparece completo. Um arquivo da IEX
malformado (`ArquivoIexInvalidoError`) não grava nada e faz a tarefa falhar, para o alarme
avisar. Olha os últimos dias úteis e coleta só os que faltam: um dia perdido é recuperado na
madrugada seguinte, e feriados (sem arquivo na IEX) são pulados.

Carga do passado (`--desde`): os dias úteis que faltam desde a data, do mais novo para o mais
antigo, até `--maximo` dias coletados (feriados não contam) ou até acabar o tempo (`--minutos`),
para a rodada da madrugada não encostar no backup. Cada dia baixa ~9 GB (cabe com folga nos 8 TB
mensais do VPS, conferido em 13/10/2026).

Atribuição obrigatória ao mostrar estes dados: `iex_tops.ATRIBUICAO` (termos da IEX, ADR 0019).
"""

import argparse
import gzip
import hashlib
import json
import logging
import os
import sys
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from src import catalogo, iex_tops
from src.barras_intradiarias import cobertura_por_simbolo, montar_barras

LISTA_DO_HIST = "https://iextrading.com/api/1.0/hist?date={data}"
PASTA = Path("dados_locais/intradiario/iex")
FUSO_NY = ZoneInfo("America/New_York")
DIAS_UTEIS_OLHADOS = 5
MAXIMO_DE_DIAS_POR_RODADA = 2  # ~12 min; o resto fica para a madrugada seguinte
TEMPO_LIMITE_S = 120
SEM_ARQUIVO = "sem arquivo"  # fim de semana, feriado ou ainda não publicado

log = logging.getLogger(__name__)


def dias_uteis_recentes(hoje: date, quantos: int = DIAS_UTEIS_OLHADOS) -> list[date]:
    """Os `quantos` dias de segunda a sexta antes de `hoje` (o de hoje ainda não saiu), do mais
    antigo para o mais novo. Feriados entram e são pulados por não terem arquivo na IEX."""
    dias, dia = [], hoje - timedelta(days=1)
    while len(dias) < quantos:
        if dia.weekday() < 5:
            dias.append(dia)
        dia -= timedelta(days=1)
    return sorted(dias)


def dias_uteis_desde(inicio: date, hoje: date) -> list[date]:
    """Os dias de segunda a sexta de `inicio` até ontem, do mais novo para o mais antigo."""
    dias, dia = [], hoje - timedelta(days=1)
    while dia >= inicio:
        if dia.weekday() < 5:
            dias.append(dia)
        dia -= timedelta(days=1)
    return dias


def arquivo_do_dia(dia: date, pasta: Path = PASTA) -> Path:
    return pasta / f"{dia.isoformat()}.parquet"


def dias_que_faltam(hoje: date, pasta: Path = PASTA) -> list[date]:
    return [
        d for d in dias_uteis_recentes(hoje) if not arquivo_do_dia(d, pasta).exists()
    ]


def endereco_do_tops(dia: date, buscar: Callable = requests.get) -> str | None:
    """O link do TOPS do dia, ou None se a IEX não tem arquivo para a data."""
    resposta = buscar(
        LISTA_DO_HIST.format(data=dia.strftime("%Y%m%d")), timeout=TEMPO_LIMITE_S
    )
    resposta.raise_for_status()
    lista = resposta.json() or []
    tops = [item for item in lista if item.get("feed") == "TOPS"]
    return tops[0]["link"] if tops else None


def simbolos_do_sp500() -> set[str]:
    """As ações dos EUA do catálogo, no formato da IEX ("BRK.B", não o "BRK-B" do Yahoo)."""
    tabela = catalogo.carregar()
    acoes = tabela[(tabela["bolsa"] == "EUA") & (tabela["tipo"] == "Ação")]
    return {simbolo.replace("-", ".") for simbolo in acoes.index}


def _gravar_atomico(caminho: Path, escrever: Callable[[Path], None]) -> None:
    temporario = caminho.with_name(caminho.name + ".parcial")
    escrever(temporario)
    os.replace(temporario, caminho)


def coletar_dia(
    dia: date,
    simbolos: set[str],
    pasta: Path = PASTA,
    buscar: Callable = requests.get,
) -> dict | str:
    """Baixa, lê e grava as barras de `dia`. Devolve o resumo, ou `SEM_ARQUIVO`.

    Levanta `iex_tops.ArquivoIexInvalidoError` (arquivo malformado) sem gravar nada.
    """
    link = endereco_do_tops(dia, buscar)
    if link is None:
        return SEM_ARQUIVO
    inicio = time.perf_counter()
    with buscar(link, stream=True, timeout=TEMPO_LIMITE_S) as resposta:
        resposta.raise_for_status()
        with gzip.GzipFile(fileobj=resposta.raw) as descomprimido:
            negocios = iex_tops.coletar_negocios(
                iex_tops.pacotes_do_pcapng(descomprimido), simbolos
            )
    barras = montar_barras(iex_tops.tabela_de_negocios(negocios), "America/New_York")
    pasta.mkdir(parents=True, exist_ok=True)
    parquet = arquivo_do_dia(dia, pasta)
    _gravar_atomico(parquet, lambda p: barras.to_parquet(p, index=False))
    cobertura = cobertura_por_simbolo(barras)
    resumo = {
        "data": dia.isoformat(),
        "coletado_em": datetime.now(FUSO_NY).isoformat(timespec="seconds"),
        "fonte": "IEX HIST (TOPS 1.6)",
        "atribuicao": iex_tops.ATRIBUICAO,
        "pacotes_lidos": negocios.pacotes_lidos,
        "negocios_guardados": len(negocios.preco),
        "cancelamentos": len(negocios.cancelados),
        "simbolos_com_barras": int(barras["simbolo"].nunique()) if len(barras) else 0,
        "barras": len(barras),
        "cobertura_mediana": round(float(cobertura.median()), 4)
        if len(cobertura)
        else 0.0,
        "segundos": round(time.perf_counter() - inicio, 1),
        "sha256_do_parquet": hashlib.sha256(parquet.read_bytes()).hexdigest(),
    }
    _gravar_atomico(
        parquet.with_suffix(".json"),
        lambda p: p.write_text(
            json.dumps(resumo, ensure_ascii=False, indent=1), "utf-8"
        ),
    )
    return resumo


def _opcoes(argumentos: list[str] | None) -> argparse.Namespace:
    leitor = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    leitor.add_argument("--data", type=date.fromisoformat, default=None)
    leitor.add_argument("--desde", type=date.fromisoformat, default=None)
    leitor.add_argument("--maximo", type=int, default=MAXIMO_DE_DIAS_POR_RODADA)
    leitor.add_argument("--minutos", type=float, default=None)
    leitor.add_argument("--pasta", type=Path, default=PASTA)
    return leitor.parse_args(argumentos)


def _dias_da_rodada(opcoes: argparse.Namespace, hoje: date) -> list[date]:
    if opcoes.data:
        return [opcoes.data]
    if opcoes.desde:
        candidatos = dias_uteis_desde(opcoes.desde, hoje)
        return [d for d in candidatos if not arquivo_do_dia(d, opcoes.pasta).exists()]
    return dias_que_faltam(hoje, opcoes.pasta)


def _coletar_e_contar(
    dia: date, simbolos: set[str], pasta: Path, buscar: Callable
) -> tuple[bool, bool]:
    """Coleta um dia e conta a história. Devolve (contou no máximo, falhou)."""
    try:
        resultado = coletar_dia(dia, simbolos, pasta, buscar)
    except (
        iex_tops.ArquivoIexInvalidoError,
        requests.RequestException,
        OSError,
    ) as erro:
        print(f"{dia}: FALHOU, nada gravado ({type(erro).__name__}: {erro})")
        return True, True
    if resultado == SEM_ARQUIVO:
        print(f"{dia}: a IEX não tem arquivo (feriado ou ainda não publicado)")
        return False, False
    print(
        f"{dia}: {resultado['barras']:,} barras de {resultado['simbolos_com_barras']} ações, "
        f"cobertura mediana {resultado['cobertura_mediana']:.0%}, {resultado['segundos']:.0f} s"
    )
    return True, False


def main(argumentos: list[str] | None = None, buscar: Callable = requests.get) -> int:
    """0 = tudo certo (inclusive sem nada a coletar); 1 = algum dia falhou."""
    opcoes = _opcoes(argumentos)
    inicio = time.monotonic()
    dias = _dias_da_rodada(opcoes, datetime.now(FUSO_NY).date())
    if not dias:
        print("Nada a coletar: os dias úteis pedidos já estão guardados.")
        return 0
    simbolos = simbolos_do_sp500()
    coletados, falhou = 0, False
    for dia in dias:
        if coletados >= opcoes.maximo:
            break
        if opcoes.minutos and time.monotonic() - inicio > opcoes.minutos * 60:
            print(
                f"Tempo da rodada acabou; {coletados} dias coletados, o resto fica para a próxima."
            )
            break
        contou, deu_erro = _coletar_e_contar(dia, simbolos, opcoes.pasta, buscar)
        coletados += contou
        falhou = falhou or deu_erro
    print(f"Faltam {len(dias) - coletados} dias úteis (feriados incluídos).")
    return 1 if falhou else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
