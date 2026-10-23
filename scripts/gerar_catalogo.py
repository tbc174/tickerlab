"""Gera o catálogo de ativos da busca: `conteudo/catalogo_de_ativos.csv`.

    python -m scripts.gerar_catalogo            (usa o último pregão)
    python -m scripts.gerar_catalogo 2026-10-09 (um pregão específico)

Rodar de vez em quando (ex.: uma vez por mês); o site só lê o CSV, não consulta a B3 a cada visita.

Fontes (públicas):
- B3: o cadastro de instrumentos ("InstrumentsEquities") e os negócios do pregão
  ("ConsolidatedTradesEquities") do site de dados da B3. Entram ações, units, fundos, ETFs e BDRs
  NEGOCIADOS no pregão (os sem negócio deixariam a lista pesada e cheia de ativos mortos);
- EUA: as empresas do S&P 500 do projeto "datasets" (licença ODC-PDDL, domínio público);
- índices, criptomoedas e câmbio: lista fixa abaixo, com o código do Yahoo Finance.
"""

import io
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from base.arquivo.agente import AGENTE

URL_DA_B3 = "https://arquivos.b3.com.br/bdi/table/export/csv?lang=en-us"
URL_DO_SP500 = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
DESTINO = Path(__file__).resolve().parent.parent / "conteudo" / "catalogo_de_ativos.csv"
CATEGORIAS_DA_B3 = {
    "SHARES": "Ação",
    "UNIT": "Unit",
    "FUNDS": "Fundo (FII e outros)",
    "ETF EQUITIES": "ETF",
    "ETF FOREIGN INDEX": "ETF",
    "BDR": "BDR",
}
# (código do Yahoo, código mostrado, nome, bolsa, tipo); na tela, índice sem o ^ do Yahoo
FIXOS = [
    ("^BVSP", "IBOV", "Ibovespa", "B3", "Índice"),
    ("^GSPC", "SPX", "S&P 500", "EUA", "Índice"),
    ("^IXIC", "IXIC", "Nasdaq Composite", "EUA", "Índice"),
    ("^DJI", "DJI", "Dow Jones", "EUA", "Índice"),
    ("^N225", "N225", "Nikkei 225", "Japão", "Índice"),
    ("^GDAXI", "DAX", "DAX", "Alemanha", "Índice"),
    ("^FTSE", "FTSE", "FTSE 100", "Reino Unido", "Índice"),
    ("BTC-USD", "BTC-USD", "Bitcoin em dólar", "Cripto", "Cripto"),
    ("ETH-USD", "ETH-USD", "Ethereum em dólar", "Cripto", "Cripto"),
    ("SOL-USD", "SOL-USD", "Solana em dólar", "Cripto", "Cripto"),
    ("BNB-USD", "BNB-USD", "BNB em dólar", "Cripto", "Cripto"),
    ("XRP-USD", "XRP-USD", "XRP em dólar", "Cripto", "Cripto"),
    ("BRL=X", "USD/BRL", "Dólar em reais", "Câmbio", "Câmbio"),
    ("EURBRL=X", "EUR/BRL", "Euro em reais", "Câmbio", "Câmbio"),
]


def _tabela_da_b3(nome: str, dia: date) -> pd.DataFrame:
    resposta = requests.post(
        URL_DA_B3,
        json={"Name": nome, "Date": dia.isoformat(), "FinalDate": dia.isoformat()},
        timeout=120,
        headers={"User-Agent": AGENTE},
    )
    resposta.raise_for_status()
    linhas = resposta.content.decode("utf-8-sig", errors="replace").splitlines()
    inicio = next(
        i for i, linha in enumerate(linhas) if linha.startswith("Ticker symbol")
    )
    return pd.read_csv(io.StringIO("\n".join(linhas[inicio:])), sep=";", dtype=str)


def _nome_bonito(texto: str) -> str:
    """ "PETROLEO BRASILEIRO S.A. PETROBRAS" → "Petroleo Brasileiro S.A. Petrobras"."""
    palavras = []
    for palavra in str(texto).split():
        siglas = (
            "S.A.",
            "S/A",
            "SA",
            "FII",
            "ETF",
            "BDR",
            "LTDA.",
            "LTDA",
            "FDO",
            "INV",
            "IMOB",
        )
        palavras.append(palavra if palavra.upper() in siglas else palavra.capitalize())
    return " ".join(palavras)


def _classe(descricao: str) -> str:
    """A classe da ação (ON, PN, PNA, UNT...) a partir da descrição curta da B3."""
    for parte in str(descricao).split():
        if parte in (
            "ON",
            "PN",
            "PNA",
            "PNB",
            "PNC",
            "UNT",
            "CI",
            "DR1",
            "DR2",
            "DR3",
            "DRN",
        ):
            return parte
    return ""


def ativos_da_b3(dia: date) -> pd.DataFrame:
    cadastro = _tabela_da_b3("InstrumentsEquities", dia)
    negociados = set(_tabela_da_b3("ConsolidatedTradesEquities", dia)["Ticker symbol"])
    a_vista = cadastro[
        (cadastro["Segment"] == "CASH")
        & cadastro["Category"].isin(CATEGORIAS_DA_B3)
        & cadastro["Ticker symbol"].str.fullmatch(r"[A-Z]{4}\d{1,2}")
        & cadastro["Ticker symbol"].isin(negociados)
    ]
    return pd.DataFrame(
        {
            "simbolo": a_vista["Ticker symbol"] + ".SA",
            "codigo": a_vista["Ticker symbol"],
            "nome": [
                f"{_nome_bonito(n)} {_classe(d)}".strip()
                for n, d in zip(
                    a_vista["Corporation name"],
                    a_vista["Asset description"],
                    strict=True,
                )
            ],
            "bolsa": "B3",
            "tipo": a_vista["Category"].map(CATEGORIAS_DA_B3),
        }
    )


def acoes_dos_eua() -> pd.DataFrame:
    tabela = pd.read_csv(URL_DO_SP500, dtype=str)
    codigos = tabela["Symbol"].str.replace(
        ".", "-", regex=False
    )  # BRK.B vira BRK-B no Yahoo
    return pd.DataFrame(
        {
            "simbolo": codigos,
            "codigo": codigos,
            "nome": tabela["Security"],
            "bolsa": "EUA",
            "tipo": "Ação",
        }
    )


def ultimo_pregao(hoje: date) -> date:
    dia = hoje - timedelta(days=1)
    while dia.weekday() >= 5:
        dia -= timedelta(days=1)
    return dia


def gerar(dia: date) -> pd.DataFrame:
    fixos = pd.DataFrame(FIXOS, columns=["simbolo", "codigo", "nome", "bolsa", "tipo"])
    catalogo = pd.concat([fixos, ativos_da_b3(dia), acoes_dos_eua()], ignore_index=True)
    return catalogo.drop_duplicates("simbolo").reset_index(drop=True)


def main() -> int:
    dia = (
        date.fromisoformat(sys.argv[1])
        if len(sys.argv) > 1
        else ultimo_pregao(datetime.now(ZoneInfo("America/Sao_Paulo")).date())
    )
    catalogo = gerar(dia)
    DESTINO.write_text(
        f"# catálogo de ativos da busca, gerado por scripts/gerar_catalogo.py (pregão {dia})\n"
        + catalogo.to_csv(index=False),
        encoding="utf-8",
    )
    print(f"{len(catalogo)} ativos em {DESTINO.name}:")
    print(catalogo.groupby(["bolsa", "tipo"]).size().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
