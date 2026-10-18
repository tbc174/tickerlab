"""Coletor diário do IEX HIST: barras de 1 minuto do S&P 500 (F3 dos dados intradiários).

    python -m scripts.coletar_iex_do_dia                 (os dias úteis recentes que faltam)
    python -m scripts.coletar_iex_do_dia --data 2026-10-09
    python -m scripts.coletar_iex_do_dia --desde 2025-10-13 --maximo 20 --minutos 160   (carga)

Roda no VPS de madrugada, num contêiner próprio com limite de memória (não no do app). O arquivo
TOPS do dia (~9 GB comprimido) é lido enquanto baixa e não fica no disco; só as barras ficam, em
`dados_locais/intradiario/iex/AAAA-MM-DD.parquet`, com um resumo `.json` ao lado (conferências e
o SHA-256 do Parquet). Gravação atômica: o arquivo só aparece completo. Um arquivo da IEX
malformado (`ArquivoIexInvalidoError`) não grava nada e faz a tarefa falhar, para o alarme
avisar. Olha os últimos pregões e coleta só os que faltam: um dia perdido é recuperado na
madrugada seguinte. Fins de semana e feriados da NYSE (`src.calendario_nyse`) nem são pedidos: a
IEX responde 404 neles, e um 404 num dia de pregão continua sendo falha, para o alarme avisar.
Conexão que cai no meio do arquivo: o dia é baixado de novo uma vez; se cair de novo, o dia falha
(nada gravado, alarme avisa), mas a rodada segue com os outros dias e o selo.

Carga do passado (`--desde`): os pregões que faltam desde a data, do mais novo para o mais
antigo, até `--maximo` dias coletados (dia ainda sem arquivo não conta) ou até acabar o tempo (`--minutos`),
para a rodada da madrugada não encostar no backup. O orçamento vale para a rodada inteira, coleta e
selo: a carga segura a trava das tarefas do VPS, e o deploy automático espera por ela (18/10/2026: o
selo, fora do orçamento, segurou a trava por horas). Cada dia baixa ~9 GB (cabe com folga nos 8 TB
mensais do VPS, conferido em 13/10/2026).

Selo por ativo (plano dos intradiários grátis, PR 5): no fim de cada rodada, os dias com barras e
sem selo ganham `selo/AAAA-MM-DD.parquet` (o fechamento das barras contra o oficial do dia,
`src.barras_intradiarias.selo_dos_fechamentos`) e o resumo `.json` ganha a contagem. O oficial vem
do Yahoo e só serve para conferir: o preço dele não é guardado. Sem resposta do Yahoo, ou com o
tempo da rodada (`--minutos`) acabado, o dia fica para a rodada seguinte. `nao_confere` aparece na saída, mas não é falha (na carga antiga, um
desdobramento depois do dia muda o preço do Yahoo).

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

import pandas as pd
import requests
import urllib3

from src import calendario_nyse, catalogo, iex_tops
from src.barras_intradiarias import (
    cobertura_por_simbolo,
    montar_barras,
    selo_dos_fechamentos,
)

LISTA_DO_HIST = "https://iextrading.com/api/1.0/hist?date={data}"
PASTA = Path("dados_locais/intradiario/iex")
FUSO_NY = ZoneInfo("America/New_York")
DIAS_UTEIS_OLHADOS = 5
MAXIMO_DE_DIAS_POR_RODADA = 2  # ~12 min; o resto fica para a madrugada seguinte
TEMPO_LIMITE_S = 120
# Conexão que cai no meio do arquivo (~17 GB; 16/10/2026: IncompleteRead perto da metade): o dia é
# baixado de novo do começo, uma vez. Se cair de novo, o dia falha e a rodada segue para o próximo.
TENTATIVAS_DO_ARQUIVO = 2
CONEXAO_CAIU = (urllib3.exceptions.HTTPError, requests.ConnectionError)
SEM_ARQUIVO = "sem arquivo"  # ainda não publicado
MAXIMO_DE_SELOS_POR_RODADA = (
    40  # um pedido ao Yahoo por dia; a carga põe ~20 dias por noite
)

log = logging.getLogger(__name__)


def dias_uteis_recentes(hoje: date, quantos: int = DIAS_UTEIS_OLHADOS) -> list[date]:
    """Os `quantos` pregões da NYSE antes de `hoje` (o de hoje ainda não saiu), do mais antigo
    para o mais novo."""
    dias, dia = [], hoje - timedelta(days=1)
    while len(dias) < quantos:
        if calendario_nyse.eh_pregao(dia):
            dias.append(dia)
        dia -= timedelta(days=1)
    return sorted(dias)


def dias_uteis_desde(inicio: date, hoje: date) -> list[date]:
    """Os pregões da NYSE de `inicio` até ontem, do mais novo para o mais antigo."""
    dias, dia = [], hoje - timedelta(days=1)
    while dia >= inicio:
        if calendario_nyse.eh_pregao(dia):
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


def _ler_o_arquivo(
    link: str, simbolos: set[str], buscar: Callable
) -> iex_tops.NegociosDoDia:
    for tentativa in range(1, TENTATIVAS_DO_ARQUIVO + 1):
        try:
            with buscar(link, stream=True, timeout=TEMPO_LIMITE_S) as resposta:
                resposta.raise_for_status()
                with gzip.GzipFile(fileobj=resposta.raw) as descomprimido:
                    return iex_tops.coletar_negocios(
                        iex_tops.pacotes_do_pcapng(descomprimido), simbolos
                    )
        except CONEXAO_CAIU as erro:
            if tentativa == TENTATIVAS_DO_ARQUIVO:
                raise
            print(
                f"A conexão caiu no meio do arquivo ({type(erro).__name__}); baixando de novo."
            )
    raise AssertionError("inalcançável")


def coletar_dia(
    dia: date,
    simbolos: set[str],
    pasta: Path = PASTA,
    buscar: Callable = requests.get,
) -> dict | str:
    """Baixa, lê e grava as barras de `dia`. Devolve o resumo, ou `SEM_ARQUIVO`.

    Levanta `iex_tops.ArquivoIexInvalidoError` (arquivo malformado) ou o erro da conexão (se ela
    cair nas `TENTATIVAS_DO_ARQUIVO`) sem gravar nada.
    """
    link = endereco_do_tops(dia, buscar)
    if link is None:
        return SEM_ARQUIVO
    inicio = time.perf_counter()
    negocios = _ler_o_arquivo(link, simbolos, buscar)
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


def fechamentos_oficiais(dia: date, simbolos: list[str]) -> pd.Series:
    """O fechamento oficial de `dia` (Yahoo, sem ajuste de dividendos), pelo símbolo da IEX
    ("BRK.B"). Vazio se o Yahoo não respondeu."""
    import yfinance as yf  # só aqui: os testes do coletor não vão à internet

    para_yahoo = {s.replace(".", "-"): s for s in simbolos}
    tabela = yf.download(
        list(para_yahoo),
        start=dia,
        end=dia + timedelta(days=1),
        auto_adjust=False,
        progress=False,
    )
    if tabela is None or tabela.empty:
        return pd.Series(dtype=float)
    fechamentos = tabela["Close"].iloc[0]
    return fechamentos.rename(index=para_yahoo).dropna()


def pasta_do_selo(pasta: Path) -> Path:
    return pasta / "selo"


def dias_sem_selo(pasta: Path) -> list[date]:
    """Dias coletados (com o resumo `.json`) que ainda não têm selo, do mais novo ao mais antigo."""
    dias = [date.fromisoformat(r.stem) for r in pasta.glob("????-??-??.json")]
    return sorted(
        (d for d in dias if not (pasta_do_selo(pasta) / f"{d}.parquet").exists()),
        reverse=True,
    )


def selar_dia(
    dia: date, pasta: Path, oficiais: Callable[[date, list[str]], pd.Series]
) -> dict | None:
    """Grava o selo do dia e acrescenta a contagem ao resumo; None se não veio o oficial."""
    barras = pd.read_parquet(arquivo_do_dia(dia, pasta))
    fechamentos = oficiais(dia, sorted(barras["simbolo"].unique()))
    if fechamentos.empty:
        return None
    selo = selo_dos_fechamentos(barras, fechamentos)
    pasta_do_selo(pasta).mkdir(parents=True, exist_ok=True)
    _gravar_atomico(
        pasta_do_selo(pasta) / f"{dia}.parquet",
        lambda p: selo.to_parquet(p, index=False),
    )
    caminho_do_resumo = arquivo_do_dia(dia, pasta).with_suffix(".json")
    resumo = json.loads(caminho_do_resumo.read_text("utf-8"))
    contagem = selo["selo"].value_counts().sort_index()
    resumo["selo"] = {str(nome): int(n) for nome, n in contagem.items()}
    resumo["pior_diferenca"] = round(float(selo["diferenca"].abs().max()), 6)
    _gravar_atomico(
        caminho_do_resumo,
        lambda p: p.write_text(
            json.dumps(resumo, ensure_ascii=False, indent=1), "utf-8"
        ),
    )
    return resumo


def _passou_do_prazo(prazo: float | None) -> bool:
    """Se o instante `prazo` (no relógio de `time.monotonic`) já passou; sem prazo, nunca."""
    return prazo is not None and time.monotonic() > prazo


def selar_os_que_faltam(
    pasta: Path,
    oficiais: Callable[[date, list[str]], pd.Series],
    maximo: int = MAXIMO_DE_SELOS_POR_RODADA,
    prazo: float | None = None,
) -> list[str]:
    """Sela até `maximo` dias sem selo, parando quando passa o `prazo` (instante no relógio de
    `time.monotonic`; None = sem prazo). Devolve uma linha por dia selado.

    O prazo é conferido antes de cada dia: o dia já começado termina (um pedido ao Yahoo).
    """
    linhas = []
    fila = dias_sem_selo(pasta)[:maximo]
    for posicao, dia in enumerate(fila):
        if _passou_do_prazo(prazo):
            print(
                f"Tempo da rodada acabou; {len(fila) - posicao} dias ficam sem selo "
                "para a próxima rodada."
            )
            break
        resumo = selar_dia(dia, pasta, oficiais)
        if resumo is None:
            print(
                f"{dia}: sem o fechamento oficial ainda; o selo fica para a próxima rodada"
            )
            continue
        contagem = ", ".join(f"{n} {selo}" for selo, n in resumo["selo"].items())
        linhas.append(
            f"{dia}: selo {contagem}; pior diferença do fechamento "
            f"{resumo['pior_diferenca']:.2%}"
        )
    return linhas


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
        urllib3.exceptions.HTTPError,
        OSError,
    ) as erro:
        print(f"{dia}: FALHOU, nada gravado ({type(erro).__name__}: {erro})")
        return True, True
    if resultado == SEM_ARQUIVO:
        print(f"{dia}: a IEX ainda não tem arquivo (não publicado)")
        return False, False
    print(
        f"{dia}: {resultado['barras']:,} barras de {resultado['simbolos_com_barras']} ações, "
        f"cobertura mediana {resultado['cobertura_mediana']:.0%}, {resultado['segundos']:.0f} s"
    )
    return True, False


def main(
    argumentos: list[str] | None = None,
    buscar: Callable = requests.get,
    oficiais: Callable[[date, list[str]], pd.Series] | None = None,
) -> int:
    """0 = tudo certo (inclusive sem nada a coletar); 1 = algum dia falhou."""
    opcoes = _opcoes(argumentos)
    prazo = time.monotonic() + opcoes.minutos * 60 if opcoes.minutos else None
    codigo = _coletar(opcoes, buscar, prazo)
    for linha in selar_os_que_faltam(
        opcoes.pasta, oficiais or fechamentos_oficiais, prazo=prazo
    ):
        print(linha)
    return codigo


def _coletar(opcoes: argparse.Namespace, buscar: Callable, prazo: float | None) -> int:
    dias = _dias_da_rodada(opcoes, datetime.now(FUSO_NY).date())
    if not dias:
        print("Nada a coletar: os pregões pedidos já estão guardados.")
        return 0
    simbolos = simbolos_do_sp500()
    coletados, falhou = 0, False
    for dia in dias:
        if coletados >= opcoes.maximo:
            break
        if _passou_do_prazo(prazo):
            print(
                f"Tempo da rodada acabou; {coletados} dias coletados, o resto fica para a próxima."
            )
            break
        contou, deu_erro = _coletar_e_contar(dia, simbolos, opcoes.pasta, buscar)
        coletados += contou
        falhou = falhou or deu_erro
    print(f"Faltam {len(dias) - coletados} pregões.")
    return 1 if falhou else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
