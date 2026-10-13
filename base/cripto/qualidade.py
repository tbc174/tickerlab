"""Regras fixas de qualidade da base de cripto (série 1, PR 5; exigência 7 do critério de pronto).

Como as regras da CVM (`base/regras.py`), cada regra só **aponta**: nunca corrige nem apaga. Cada
achado diz a regra, a tabela, a chave (dia, altura ou semana), o valor, o que se esperava, o porquê
em português e desde quando o achado existe (`valido_desde`, sem olhar o futuro).

- **C1:** dia faltando numa série diária (preços ou rede).
- **C2:** preço impossível: zero ou negativo, ou máxima abaixo da mínima, ou fechamento fora delas.
- **C3:** salto de mais de 30% de um dia para o outro (aponta; pode ser verdade em cripto).
- **C4:** volume mais de 10 vezes a mediana dos 90 dias **anteriores**.
- **C5:** Mercado Bitcoin e Kraken (convertida pela PTAX) diferentes em mais de 2% no fechamento.
  Folga larga por causa do ágio do Bitcoin no Brasil; a PTAX usada é a última publicada até o dia.
- **C6:** bloco sem alguma métrica.
- **C7:** soma do histograma de moedas não gastas diferente do total que o nó informa.
- **C8:** semana sem relatório da CFTC (mais de 8 dias entre dois relatórios do mesmo contrato).

As comparações de limite são feitas como `|novo - velho| > limite × velho`, e não pela variação
em %, porque 1 - 140/200 dá 0,30000000000000004 em ponto flutuante e dispararia no limite exato.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import pairwise

import pandas as pd

log = logging.getLogger(__name__)

VERSAO_DAS_REGRAS = "1"
SALTO_MAXIMO = 0.30
VEZES_A_MEDIANA_DO_VOLUME = 10
DIAS_DA_MEDIANA_DO_VOLUME = 90
DIFERENCA_MAXIMA_ENTRE_CORRETORAS = 0.02
DIAS_MAXIMOS_ENTRE_RELATORIOS = 8
METRICAS_DO_BLOCO = [
    "n_transacoes",
    "taxas_total",
    "valor_movimentado",
    "dias_moeda_destruidos",
    "emissao",
    "dificuldade",
]


@dataclass(frozen=True)
class AchadoCripto:
    """Um ponto que chamou a atenção numa tabela da base de cripto."""

    regra: str
    tabela: str
    chave: str  # o dia (AAAA-MM-DD), a altura do bloco ou "contrato AAAA-MM-DD"
    valor: float | None
    valor_esperado: float | None
    porque: str
    valido_desde: pd.Timestamp | None = None


@dataclass
class Rodada:
    """O resultado de rodar as regras: os achados e as regras que quebraram (com o erro)."""

    achados: list[AchadoCripto] = field(default_factory=list)
    falhas: dict[str, str] = field(default_factory=dict)


def c1_dias_faltando(tabela: pd.DataFrame, nome: str) -> list[AchadoCripto]:
    """Cada dia entre o primeiro e o último que não está na tabela."""
    if tabela.empty:
        return []
    presentes = set(tabela["dia"])
    todos = pd.date_range(min(presentes), max(presentes), freq="D").date
    return [
        AchadoCripto(
            "C1", nome, dia.isoformat(), None, None, f"Falta o dia {dia:%d/%m/%Y}."
        )
        for dia in todos
        if dia not in presentes
    ]


def c2_preco_impossivel(tabela: pd.DataFrame, nome: str) -> list[AchadoCripto]:
    """Preço zero ou negativo, máxima abaixo da mínima ou fechamento fora da faixa do dia."""
    precos = tabela[["abertura", "maxima", "minima", "fechamento"]]
    impossivel = (
        (precos <= 0).any(axis=1)
        | (tabela["maxima"] < tabela["minima"])
        | (tabela["fechamento"] > tabela["maxima"])
        | (tabela["fechamento"] < tabela["minima"])
    )
    return [
        _achado(
            "C2", nome, linha, linha["fechamento"], None, "Preço impossível no dia."
        )
        for _, linha in tabela[impossivel].iterrows()
    ]


def c3_salto(tabela: pd.DataFrame, nome: str) -> list[AchadoCripto]:
    """Fechamento que mudou mais de 30% em relação ao dia anterior."""
    ordenada = tabela.sort_values("dia").reset_index(drop=True)
    anterior = ordenada["fechamento"].shift(1)
    salto = (ordenada["fechamento"] - anterior).abs() > SALTO_MAXIMO * anterior
    return [
        _achado(
            "C3",
            nome,
            linha,
            linha["fechamento"],
            anterior[i],
            "Salto de mais de 30% num dia.",
        )
        for i, linha in ordenada[salto].iterrows()
    ]


def c4_volume_fora_do_padrao(tabela: pd.DataFrame, nome: str) -> list[AchadoCripto]:
    """Volume mais de 10 vezes a mediana dos 90 dias anteriores (só o passado)."""
    ordenada = tabela.sort_values("dia").reset_index(drop=True)
    mediana = (
        ordenada["volume"]
        .shift(1)
        .rolling(DIAS_DA_MEDIANA_DO_VOLUME, min_periods=DIAS_DA_MEDIANA_DO_VOLUME)
        .median()
    )
    fora = ordenada["volume"] > VEZES_A_MEDIANA_DO_VOLUME * mediana
    porque = "Volume mais de 10 vezes a mediana dos 90 dias anteriores."
    return [
        _achado("C4", nome, linha, linha["volume"], mediana[i], porque)
        for i, linha in ordenada[fora].iterrows()
    ]


def c5_corretoras_divergem(
    kraken: pd.DataFrame, mercado_bitcoin: pd.DataFrame, ptax: pd.DataFrame
) -> list[AchadoCripto]:
    """Fechamento do Mercado Bitcoin (R$) contra o da Kraken (US$) vezes a última PTAX até o dia."""
    juntas = kraken[["dia", "fechamento"]].merge(
        mercado_bitcoin[["dia", "fechamento", "divulgado_em"]],
        on="dia",
        suffixes=("_usd", "_brl"),
    )
    juntas = pd.merge_asof(
        juntas.assign(momento=pd.to_datetime(juntas["dia"])).sort_values("momento"),
        ptax.assign(momento=pd.to_datetime(ptax["dia"]))[
            ["momento", "ptax"]
        ].sort_values("momento"),
        on="momento",
    ).dropna(subset=["ptax"])
    em_reais = juntas["fechamento_usd"] * juntas["ptax"]
    diverge = (
        juntas["fechamento_brl"] - em_reais
    ).abs() > DIFERENCA_MAXIMA_ENTRE_CORRETORAS * em_reais
    diferenca = juntas["fechamento_brl"] / em_reais - 1
    porque = "Mercado Bitcoin e Kraken (pela PTAX) diferem mais de 2% no fechamento."
    return [
        _achado("C5", "kraken x mb", linha, diferenca[i], 0.0, porque)
        for i, linha in juntas[diverge].iterrows()
    ]


def c6_bloco_sem_metrica(blocos: pd.DataFrame) -> list[AchadoCripto]:
    """Bloco com alguma métrica vazia."""
    colunas = [coluna for coluna in METRICAS_DO_BLOCO if coluna in blocos]
    vazios = blocos[blocos[colunas].isna().any(axis=1)]
    return [
        AchadoCripto(
            "C6", "blocos", str(altura), None, None, "Bloco com métrica vazia."
        )
        for altura in vazios["altura"]
    ]


def c7_oferta_nao_bate(diferenca: int, altura: int) -> list[AchadoCripto]:
    """A diferença (satoshis) entre a soma do histograma e o total não gasto do nó."""
    if diferenca == 0:
        return []
    porque = "A soma das moedas não gastas da base não bate com o total do nó."
    return [AchadoCripto("C7", "blocos", str(altura), float(diferenca), 0.0, porque)]


def c8_semana_sem_cot(cot: pd.DataFrame) -> list[AchadoCripto]:
    """Relatório da CFTC que veio mais de 8 dias depois do anterior, por contrato."""
    achados = []
    for contrato, relatorios in cot.groupby("contrato"):
        datas = sorted(relatorios["relatorio"])
        for anterior, atual in pairwise(datas):
            if atual - anterior > timedelta(days=DIAS_MAXIMOS_ENTRE_RELATORIOS):
                porque = f"Faltou relatório da CFTC entre {anterior:%d/%m/%Y} e {atual:%d/%m/%Y}."
                achados.append(
                    AchadoCripto(
                        "C8",
                        "cftc",
                        f"{contrato} {atual.isoformat()}",
                        None,
                        None,
                        porque,
                    )
                )
    return achados


def rodar(
    precos: dict[str, pd.DataFrame] | None = None,
    ptax: pd.DataFrame | None = None,
    blocos: pd.DataFrame | None = None,
    cot: pd.DataFrame | None = None,
    oferta: tuple[int, int] | None = None,
) -> Rodada:
    """Roda as regras que os dados permitem; uma regra que quebra fica de fora e é avisada."""
    rodada = Rodada()
    for regra, chamar in _regras(precos or {}, ptax, blocos, cot, oferta):
        try:
            rodada.achados.extend(chamar())
        except (KeyError, ValueError, TypeError) as erro:
            log.warning("Regra %s de cripto quebrou: %r", regra, erro)
            rodada.falhas[regra] = repr(erro)
    return rodada


def _regras(
    precos: dict[str, pd.DataFrame],
    ptax: pd.DataFrame | None,
    blocos: pd.DataFrame | None,
    cot: pd.DataFrame | None,
    oferta: tuple[int, int] | None,
) -> list[tuple[str, Callable[[], list[AchadoCripto]]]]:
    # as regras são lidas do módulo na hora de rodar (um teste pode trocar uma delas)
    regras: list[tuple[str, Callable[[], list[AchadoCripto]]]] = []
    for nome, tabela in precos.items():
        regras += [
            ("C1", lambda t=tabela, n=nome: c1_dias_faltando(t, n)),
            ("C2", lambda t=tabela, n=nome: c2_preco_impossivel(t, n)),
            ("C3", lambda t=tabela, n=nome: c3_salto(t, n)),
            ("C4", lambda t=tabela, n=nome: c4_volume_fora_do_padrao(t, n)),
        ]
    if ptax is not None and {"kraken", "mb"} <= precos.keys():
        regras.append(
            ("C5", lambda: c5_corretoras_divergem(precos["kraken"], precos["mb"], ptax))
        )
    if blocos is not None:
        regras.append(("C6", lambda: c6_bloco_sem_metrica(blocos)))
    if oferta is not None:
        regras.append(("C7", lambda: c7_oferta_nao_bate(*oferta)))
    if cot is not None:
        regras.append(("C8", lambda: c8_semana_sem_cot(cot)))
    return regras


def _achado(
    regra: str,
    tabela: str,
    linha: pd.Series,
    valor: float | None,
    esperado: float | None,
    porque: str,
) -> AchadoCripto:
    dia: date = linha["dia"]
    return AchadoCripto(
        regra=regra,
        tabela=tabela,
        chave=dia.isoformat(),
        valor=None if pd.isna(valor) else float(valor),
        valor_esperado=None
        if esperado is None or pd.isna(esperado)
        else float(esperado),
        porque=porque,
        valido_desde=linha.get("divulgado_em"),
    )
