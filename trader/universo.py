"""A lista de ativos da pesquisa de ML (fase M1).

Duas fontes, guardadas separadas (os feriados e os fusos são diferentes; o alinhamento das datas
fica para a M2):

- `mt5`: forex e metais, direto da conta demo (preços do corretor);
- `yfinance`: B3, commodities, cripto, índices e macro (preços ajustados por dividendos e desdobramentos).

`papel` diz para que a série serve: `operar` entra como candidata a estratégia; `atributo` só entra
como informação para o modelo (VIX, juros, dólar), nunca é operada.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ativo:
    simbolo: str  # como a fonte chama (EURUSD, KC=F, PETR4.SA)
    fonte: str  # "mt5" ou "yfinance"
    classe: str
    papel: str = "operar"
    aviso: str = ""  # defeito conhecido e real da série (não é erro de download)
    proxy_de: str = (
        ""  # futuro da B3 que esta série representa na pesquisa (histórico longo)
    )

    @property
    def arquivo(self) -> str:
        """Nome seguro para o arquivo (sem ^, = nem outros caracteres de ticker)."""
        trocas = {"^": "IDX_", "=": "_", "-": "_"}
        nome = self.simbolo
        for velho, novo in trocas.items():
            nome = nome.replace(velho, novo)
        return nome


AVISOS = {
    "CL=F": "fechou a -37,63 em 20/04/2020 (preço negativo real do WTI): retornos percentuais quebram nesse dia",
}


# Futuros contínuos do Yahoo (`=F`) são SÓ ATRIBUTO (decisão do Tiago, 11/10/2026): a série emenda
# contratos sem ajuste e a troca de contrato vira um salto falso de preço (no gás natural, os maiores
# "retornos" diários, de +20% a +46%, caem todos na semana do vencimento). Voltam a ser operáveis
# quando houver dado por contrato (boletim da B3 acumulado ou corretora).
#
# Enquanto o histórico dos futuros da B3 não existe (a B3 só guarda ~3 semanas, ver `b3.py`),
# estas séries longas fazem o papel deles na pesquisa. Nenhuma é igual ao contrato real.
PROXIES = {
    "^BVSP": "WIN e IND (mini índice e índice cheio): o Ibovespa à vista, sem base nem rolagem",
    "BRL=X": "WDO e DOL (mini dólar e dólar cheio): o dólar à vista, sem base nem rolagem",
    "KC=F": "ICF (café arábica da B3): mesmo grão, mas em ¢/lb na ICE, não em US$/saca",
    "LE=F": "BGI (boi gordo da B3): gado vivo da CME em US$/cwt; aproximação FRACA",
}


def _mt5(classe: str, *simbolos: str) -> list[Ativo]:
    return [Ativo(s, "mt5", classe) for s in simbolos]


def _yf(classe: str, *simbolos: str, papel: str = "operar") -> list[Ativo]:
    return [
        Ativo(s, "yfinance", classe, papel, AVISOS.get(s, ""), PROXIES.get(s, ""))
        for s in simbolos
    ]


UNIVERSO: list[Ativo] = [
    *_mt5(
        "forex",
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "USDCHF",
        "AUDUSD",
        "USDCAD",
        "NZDUSD",
        "EURJPY",
        "GBPJPY",
        "EURGBP",
        "AUDJPY",
        "USDMXN",
        "USDZAR",
    ),
    *_mt5("metais", "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"),
    *_yf(
        "energia", "CL=F", "BZ=F", "NG=F", papel="atributo"
    ),  # petróleo WTI, Brent, gás natural
    *_yf("metais", "HG=F", papel="atributo"),  # cobre
    *_yf(
        "agro",
        "KC=F",  # café arábica
        "SB=F",  # açúcar
        "CT=F",  # algodão
        "CC=F",  # cacau
        "LE=F",  # boi vivo (CME; aproxima o boi gordo da B3)
        "GF=F",  # boi magro
        "ZS=F",  # soja
        "ZC=F",  # milho
        "ZW=F",  # trigo
        "OJ=F",  # suco de laranja
        papel="atributo",
    ),
    *_yf("cripto", "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"),
    *_yf(
        "acoes_b3",
        "PETR4.SA",
        "PETR3.SA",
        "VALE3.SA",
        "ITUB4.SA",
        "BBDC4.SA",
        "BBAS3.SA",
        "ABEV3.SA",
        "WEGE3.SA",
        "SUZB3.SA",
        "JBSS32.SA",
        "RENT3.SA",
        "PRIO3.SA",
        "BBSE3.SA",
        "SANB11.SA",
        "AXIA3.SA",
        "EQTL3.SA",
        "LREN3.SA",
        "MGLU3.SA",
        "RADL3.SA",
        "RAIL3.SA",
        "CSNA3.SA",
        "GGBR4.SA",
        "SLCE3.SA",
        "SMTO3.SA",
        "BOVA11.SA",
    ),
    *_yf("indices", "^BVSP", "^GSPC", "^IXIC", "^DJI", "^N225", "^GDAXI"),
    *_yf("etfs", "TLT", "GLD"),
    *_yf("macro", "^VIX", "^TNX", "DX-Y.NYB", papel="atributo"),
    *_yf(
        "cambio", "BRL=X"
    ),  # dólar em reais: opera-se pelo WDO/DOL, vale como proxy deles
]


def por_fonte(fonte: str) -> list[Ativo]:
    return [a for a in UNIVERSO if a.fonte == fonte]
