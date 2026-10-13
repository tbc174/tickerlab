"""Boletim diário de derivativos da B3: futuros com abertura, máxima, mínima, último e ajuste.

Fonte pública, sem login: o arquivo "Consolidated Trades Derivatives" do site de dados da B3
(o mesmo que o pacote `rb3` usa). Cobre todos os derivativos do dia (boi BGI, café ICF, milho
CCM, mini índice WIN, mini dólar WDO, DI1...). **A B3 só guarda umas 3 semanas por esse
caminho**: para ter histórico, é preciso baixar todo dia e acumular (`python -m
trader.atualizar_b3`). Histórico longo exige outra fonte (corretora no MT5 ou serviço pago).

Cada arquivo diário vira `dados_b3/futuros/AAAA-MM-DD.parquet`, só com os contratos futuros
(as opções ficam de fora). Cada contrato é uma linha por dia; a série contínua, com a regra de
rolagem, é montada à parte.
"""

from __future__ import annotations

import io
import re
import time
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

URL = "https://arquivos.b3.com.br/bdi/table/export/csv?lang=en-us"
PASTA_PADRAO = Path(__file__).resolve().parent.parent / "dados_b3" / "futuros"
TENTATIVAS = 3
PAUSA_ENTRE_PEDIDOS = 1.0  # segundos: não sobrecarregar o site
# produto (3 letras ou 2 letras e 1 dígito, como DI1) + letra do mês + ano com 2 dígitos
PADRAO_DO_FUTURO = re.compile(r"[A-Z][A-Z0-9]{2}[FGHJKMNQUVXZ]\d{2}")
CABECALHO = "Ticker symbol"
COLUNAS = {
    "Ticker symbol": "contrato",
    "Segment": "segmento",
    "Opening price": "Open",
    "Minimum price": "Low",
    "Maximum price": "High",
    "Trade average price": "Media",
    "Last price": "Close",
    "Adjusted quote": "Ajuste",
    "Previous adjusted quote tax": "Ajuste_anterior",
    "Variation": "Variacao",
    "Trade quantity": "Negocios",
    "Financial instrument quantity": "Contratos",  # contratos NEGOCIADOS no dia (não é posição em aberto)
    "National financial volume": "Volume_financeiro",
}
Baixador = Callable[[date], str]


def baixar_texto(dia: date) -> str:
    """Pede à B3 o boletim do dia. Devolve o CSV bruto (só o cabeçalho se não houve pregão)."""
    corpo = {
        "Name": "ConsolidatedTradesDerivatives",
        "Date": dia.isoformat(),
        "FinalDate": dia.isoformat(),
    }
    erro: Exception | None = None
    for tentativa in range(TENTATIVAS):
        try:
            resposta = requests.post(
                URL, json=corpo, timeout=90, headers={"User-Agent": "Mozilla/5.0"}
            )
            resposta.raise_for_status()
            return resposta.content.decode("utf-8-sig")
        except requests.RequestException as e:
            erro = e
            time.sleep(2 * (tentativa + 1))
    raise RuntimeError(f"A B3 não respondeu para {dia}: {erro}")


def ler_boletim(texto: str, dia: date) -> pd.DataFrame:
    """Converte o CSV da B3 numa tabela só com os contratos futuros (sem opções)."""
    linhas = texto.splitlines()
    inicio = next(
        (i for i, linha in enumerate(linhas) if linha.startswith(CABECALHO)), None
    )
    if inicio is None:
        raise ValueError("Formato inesperado: não achei o cabeçalho do boletim.")
    corpo = "\n".join(linhas[inicio:])
    tabela = pd.read_csv(
        io.StringIO(corpo),
        sep=";",
        thousands=",",
        na_values=["-", ""],
        dtype={"Ticker symbol": str},
    )
    faltando = set(COLUNAS) - set(tabela.columns)
    if faltando:
        raise ValueError(f"O boletim mudou de formato: faltam as colunas {faltando}.")
    tabela = tabela[list(COLUNAS)].rename(columns=COLUNAS)
    # futuro = código de 6 caracteres; opções têm sufixo C/P e o preço de exercício
    eh_futuro = tabela["contrato"].str.fullmatch(PADRAO_DO_FUTURO.pattern, na=False)
    tabela = tabela[eh_futuro].copy()
    tabela.insert(0, "Date", pd.Timestamp(dia))
    tabela.insert(2, "produto", tabela["contrato"].str[:3])
    tabela.insert(3, "vencimento", tabela["contrato"].str[3:])
    numericas = [
        c
        for c in tabela.columns
        if c not in {"Date", "contrato", "produto", "vencimento", "segmento"}
    ]
    tabela[numericas] = tabela[numericas].apply(pd.to_numeric, errors="coerce")
    return tabela.reset_index(drop=True)


def _caminho(dia: date, pasta: Path) -> Path:
    return pasta / f"{dia.isoformat()}.parquet"


def dias_uteis(inicio: date, fim: date) -> list[date]:
    """Segunda a sexta entre as datas (feriados aparecem vazios no boletim e são pulados)."""
    dias = []
    atual = inicio
    while atual <= fim:
        if atual.weekday() < 5:
            dias.append(atual)
        atual += timedelta(days=1)
    return dias


def atualizar(
    inicio: date,
    fim: date,
    pasta: Path = PASTA_PADRAO,
    baixar: Baixador = baixar_texto,
    pausa: float = PAUSA_ENTRE_PEDIDOS,
) -> dict[str, list[date]]:
    """Baixa os dias que ainda não estão na pasta. Devolve o que foi baixado, pulado e vazio."""
    resultado: dict[str, list[date]] = {
        "baixados": [],
        "ja_tinha": [],
        "sem_pregao": [],
    }
    pasta.mkdir(parents=True, exist_ok=True)
    for dia in dias_uteis(inicio, fim):
        if _caminho(dia, pasta).exists():
            resultado["ja_tinha"].append(dia)
            continue
        tabela = ler_boletim(baixar(dia), dia)
        if tabela.empty:
            resultado["sem_pregao"].append(dia)
        else:
            tabela.to_parquet(_caminho(dia, pasta))
            resultado["baixados"].append(dia)
        time.sleep(pausa)
    return resultado


def carregar(pasta: Path = PASTA_PADRAO) -> pd.DataFrame:
    """Todos os dias já acumulados, num só quadro (vazio se ainda não há nada)."""
    arquivos = sorted(pasta.glob("*.parquet"))
    if not arquivos:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)
