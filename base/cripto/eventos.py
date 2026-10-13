"""Calendário de eventos da rede do Bitcoin (série 1; exigência 5 do critério de pronto da base de
cripto).

Eventos que mudam a regra do jogo: os halvings (a emissão por bloco cai pela metade), a divisão que
criou o Bitcoin Cash e as duas grandes mudanças de regra (SegWit e Taproot). Cada um com a altura do
bloco, o dia em UTC e a fonte. Servem para:

- conferir os dados do nó: o bloco da altura do evento tem de cair no dia do evento;
- procurar **saltos falsos**: uma métrica que muda de patamar exatamente na data de um evento pode
  ser efeito da mudança de regra (ex.: o SegWit mudou o tamanho das transações), não do mercado. A
  tabela vai para revisão humana; nenhum número é corrigido.
"""

from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd

DIAS_ANTES_PARA_COMPARAR = 7
METRICAS_PARA_SALTOS = [
    "n_transacoes",
    "taxas_total",
    "valor_movimentado",
    "dias_moeda_destruidos",
]


@dataclass(frozen=True)
class Evento:
    """Um evento da rede, com o bloco onde ele valeu e a fonte."""

    dia: date  # UTC
    altura: int
    nome: str
    tipo: str  # halving, divisao ou regra
    fonte: str


_WIKI = "https://en.bitcoin.it/wiki/"
_BIPS = "https://github.com/bitcoin/bips/blob/master/"
EVENTOS = (
    Evento(
        date(2012, 11, 28),
        210_000,
        "1º halving: de 50 para 25 BTC por bloco",
        "halving",
        _WIKI + "Controlled_supply",
    ),
    Evento(
        date(2016, 7, 9),
        420_000,
        "2º halving: de 25 para 12,5 BTC",
        "halving",
        _WIKI + "Controlled_supply",
    ),
    Evento(
        date(2017, 8, 1),
        478_559,
        "Bitcoin Cash se separa (primeiro bloco só do BCH)",
        "divisao",
        _WIKI + "Bitcoin_Cash",
    ),
    Evento(
        date(2017, 8, 24),
        481_824,
        "SegWit passa a valer (BIP 141)",
        "regra",
        _BIPS + "bip-0141.mediawiki",
    ),
    Evento(
        date(2020, 5, 11),
        630_000,
        "3º halving: de 12,5 para 6,25 BTC",
        "halving",
        _WIKI + "Controlled_supply",
    ),
    Evento(
        date(2021, 11, 14),
        709_632,
        "Taproot passa a valer (BIPs 340 a 342)",
        "regra",
        _BIPS + "bip-0341.mediawiki",
    ),
    Evento(
        date(2024, 4, 20),
        840_000,
        "4º halving: de 6,25 para 3,125 BTC",
        "halving",
        _WIKI + "Controlled_supply",
    ),
)


def tabela_de_eventos() -> pd.DataFrame:
    """O calendário como tabela, para o acervo e o dicionário."""
    return pd.DataFrame([asdict(evento) for evento in EVENTOS])


def dias_que_nao_batem(blocos: pd.DataFrame) -> list[str]:
    """Eventos cuja altura está nos blocos lidos mas caiu noutro dia UTC (deve ser vazio)."""
    por_altura = blocos.set_index("altura")["hora"]
    problemas = []
    for evento in EVENTOS:
        if evento.altura in por_altura.index:
            dia_no_no = por_altura.loc[evento.altura].date()
            if dia_no_no != evento.dia:
                problemas.append(
                    f"{evento.nome}: o nó diz {dia_no_no}, o calendário diz {evento.dia}"
                )
    return problemas


def saltos_nos_eventos(rede_diaria: pd.DataFrame) -> pd.DataFrame:
    """Para cada evento e métrica: o valor no dia, a mediana dos 7 dias antes e a razão entre eles.

    Razões muito longe de 1 pedem uma olhada: podem ser o mercado ou o efeito da mudança de regra.
    """
    por_dia = rede_diaria.set_index("dia")
    linhas = []
    for evento in EVENTOS:
        if evento.dia not in por_dia.index:
            continue
        antes = por_dia[(por_dia.index < evento.dia)].tail(DIAS_ANTES_PARA_COMPARAR)
        for metrica in METRICAS_PARA_SALTOS:
            mediana = antes[metrica].median()
            valor = por_dia.loc[evento.dia, metrica]
            linhas.append(
                {
                    "evento": evento.nome,
                    "metrica": metrica,
                    "valor_no_dia": valor,
                    "mediana_antes": mediana,
                    "razao": valor / mediana if mediana else None,
                }
            )
    return pd.DataFrame(linhas)
