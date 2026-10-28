"""O pregão do dia (linha 444 da fila; plano `2026-10-28-raio-x-todo-dia`): os números do relatório curto
que o site mostra todo dia útil, a partir do fechamento oficial da B3.

Entradas (montadas pelo gerador, que lê o acervo; aqui só se faz conta):

- o COTAHIST da véspera e do dia, como `base.intradiario_b3.ler_cotahist` devolve (código → `fechamento`
  e `volume`, em reais);
- `papeis`: código, CNPJ, nome curto da empresa e setor (FCA da CVM, só o que era público na véspera);
- a série do Ibovespa (estatísticas do índice da B3) e os contratos do boletim PR da B3 (DI1 e dólar
  futuro, com o ajuste do dia e o da véspera).

A saída de `resumo_do_pregao` é um `dict` de tipos simples (vai para JSON e para a API), em que cada
bloco leva a fonte e a data. Variações são frações (−0,10 é queda de 10%). Nada aqui diz por que o
mercado se mexeu: só o que ele fez.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

import pandas as pd

# O mesmo corte do Raio-X de 26/10: papel com menos que isto negociado na véspera não entra nas contas.
LIQUIDEZ_MINIMA = 20_000_000
# Mediana de um ou dois papéis não descreve um setor.
EMPRESAS_POR_SETOR_MINIMO = 3
MAIORES_POR_LISTA = 5
# Juros: o DI1 de janeiro mais perto deste prazo (o mesmo vértice do Raio-X, juros de 2 anos).
PRAZO_DOS_JUROS_EM_DIAS = 730
PONTOS_BASE_POR_PONTO_PERCENTUAL = 100
# O dólar futuro da B3 é cotado em reais por mil dólares.
DOLARES_POR_CONTRATO = 1000
# Letra do mês de vencimento dos futuros da B3 (janeiro = F ... dezembro = Z).
LETRAS_DOS_MESES = "FGHJKMNQUVXZ"

FONTE_DAS_ACOES = "B3, série histórica de cotações (COTAHIST), fechamento oficial"
FONTE_DO_INDICE = "B3, estatísticas do índice Ibovespa"
FONTE_DOS_JUROS = (
    "B3, boletim de preços de referência (BVBG.086), taxa de ajuste do DI1"
)
FONTE_DO_DOLAR = (
    "B3, boletim de preços de referência (BVBG.086), ajuste do dólar futuro"
)
FONTE_DOS_SETORES = FONTE_DAS_ACOES + "; setor do Formulário Cadastral (FCA) da CVM"


class FaltaNoBoletimError(ValueError):
    """Um número de que o relatório precisa não está nos arquivos do dia."""


@dataclass(frozen=True)
class EntradasDoPregao:
    """Tudo o que o resumo de um pregão usa, já lido do acervo."""

    dia: date
    vespera: date
    empresas: pd.DataFrame  # saída de `variacoes_das_empresas`
    ibovespa: pd.Series  # data → pontos; precisa do dia e de pelo menos um pregão antes
    contratos: pd.DataFrame  # código → `ajuste` e `ajuste_vespera` (boletim PR)


# --- as ações ------------------------------------------------------------------------------------


def variacoes_das_empresas(
    vespera: pd.DataFrame,
    dia: pd.DataFrame,
    papeis: pd.DataFrame,
    com_evento_no_dia: Collection[str] = (),
) -> pd.DataFrame:
    """Uma linha por empresa: o papel mais negociado na véspera, com o fechamento dos dois dias, a
    variação (fração), os volumes (reais) e se a variação está "a conferir".

    `com_evento_no_dia`: os códigos com desdobramento ou grupamento "ex" no dia (cadastro de eventos
    da B3). O COTAHIST não ajusta o preço, então a variação desses papéis não é comparável: ficam "a
    conferir" e fora das contas. O tamanho da variação não basta para isso: no circuit breaker de
    26/10/2026, MGLU3 caiu 58% de verdade.
    """
    precos = papeis.merge(
        vespera[["fechamento", "volume"]].add_suffix("_vespera"),
        left_on="simbolo",
        right_index=True,
    ).merge(dia[["fechamento", "volume"]], left_on="simbolo", right_index=True)
    precos = precos[(precos["fechamento_vespera"] > 0) & (precos["fechamento"] > 0)]
    um_por_empresa = precos.sort_values(
        "volume_vespera", ascending=False
    ).drop_duplicates("cnpj")
    tabela = um_por_empresa.assign(
        variacao=um_por_empresa["fechamento"] / um_por_empresa["fechamento_vespera"] - 1
    )
    tabela["a_conferir"] = tabela["simbolo"].isin(list(com_evento_no_dia))
    return tabela.reset_index(drop=True)


def liquidas(tabela: pd.DataFrame) -> pd.DataFrame:
    """As empresas que entram nas contas: liquidez mínima na véspera e variação fora do "a conferir"."""
    return tabela[(tabela["volume_vespera"] >= LIQUIDEZ_MINIMA) & ~tabela["a_conferir"]]


def amplitude(tabela: pd.DataFrame) -> dict[str, int]:
    """Quantas empresas líquidas subiram, caíram e ficaram no mesmo preço."""
    variacao = liquidas(tabela)["variacao"]
    return {
        "subiram": int((variacao > 0).sum()),
        "cairam": int((variacao < 0).sum()),
        "estaveis": int((variacao == 0).sum()),
    }


def _linha_da_lista(linha: pd.Series) -> dict[str, object]:
    return {
        "simbolo": str(linha["simbolo"]),
        "empresa": str(linha["empresa"]),
        "setor": str(linha["setor"]),
        "variacao": float(linha["variacao"]),
        "fechamento": float(linha["fechamento"]),
    }


def maiores_altas_e_quedas(
    tabela: pd.DataFrame, quantas: int = MAIORES_POR_LISTA
) -> dict[str, list[dict[str, object]]]:
    """As maiores altas e quedas entre as líquidas; no empate, a mais negociada na véspera primeiro."""
    contas = liquidas(tabela)
    altas = contas[contas["variacao"] > 0].sort_values(
        ["variacao", "volume_vespera"], ascending=[False, False]
    )
    quedas = contas[contas["variacao"] < 0].sort_values(
        ["variacao", "volume_vespera"], ascending=[True, False]
    )
    return {
        "altas": [
            _linha_da_lista(linha) for _, linha in altas.head(quantas).iterrows()
        ],
        "quedas": [
            _linha_da_lista(linha) for _, linha in quedas.head(quantas).iterrows()
        ],
    }


def setores_contra_o_indice(
    tabela: pd.DataFrame, variacao_do_indice: float
) -> list[dict[str, object]]:
    """A mediana de cada setor e a diferença para o índice (fração), do melhor setor ao pior. Setor
    com menos de `EMPRESAS_POR_SETOR_MINIMO` empresas líquidas fica de fora."""
    por_setor = liquidas(tabela).groupby("setor")["variacao"].agg(["median", "size"])
    por_setor = por_setor[por_setor["size"] >= EMPRESAS_POR_SETOR_MINIMO]
    por_setor = por_setor.sort_values("median", ascending=False)
    return [
        {
            "setor": str(setor),
            "empresas": int(linha["size"]),
            "mediana": float(linha["median"]),
            "contra_o_indice": float(linha["median"] - variacao_do_indice),
        }
        for setor, linha in por_setor.iterrows()
    ]


# --- juros e dólar (boletim PR) ------------------------------------------------------------------


def _codigo_do_vencimento(prefixo: str, ano: int, mes: int) -> str:
    return f"{prefixo}{LETRAS_DOS_MESES[mes - 1]}{ano % 100:02d}"


def _contrato(contratos: pd.DataFrame, simbolo: str) -> pd.Series:
    if simbolo not in contratos.index:
        raise FaltaNoBoletimError(f"{simbolo} não está no boletim PR do dia.")
    return contratos.loc[simbolo]


def taxa_do_di(contratos: pd.DataFrame, dia: date) -> dict[str, object]:
    """A taxa de ajuste (% ao ano) do DI1 de janeiro mais perto de dois anos e a mudança desde a véspera,
    em pontos-base."""
    alvo = pd.Timestamp(dia) + pd.Timedelta(days=PRAZO_DOS_JUROS_EM_DIAS)
    ano = min(
        (alvo.year, alvo.year + 1),
        key=lambda candidato: abs(pd.Timestamp(candidato, 1, 1) - alvo),
    )
    simbolo = _codigo_do_vencimento("DI1", ano, 1)
    contrato = _contrato(contratos, simbolo)
    return {
        "simbolo": simbolo,
        "taxa": float(contrato["ajuste"]),
        "taxa_vespera": float(contrato["ajuste_vespera"]),
        "variacao_em_pontos_base": float(
            (contrato["ajuste"] - contrato["ajuste_vespera"])
            * PONTOS_BASE_POR_PONTO_PERCENTUAL
        ),
    }


def dolar_futuro(contratos: pd.DataFrame, dia: date) -> dict[str, object]:
    """O dólar futuro do 1º vencimento (o mês seguinte: o contrato vence no 1º dia útil do mês), em
    reais por dólar, e a variação desde a véspera (fração)."""
    mes_seguinte = pd.Timestamp(dia.year, dia.month, 1) + pd.DateOffset(months=1)
    simbolo = _codigo_do_vencimento("DOL", mes_seguinte.year, mes_seguinte.month)
    contrato = _contrato(contratos, simbolo)
    return {
        "simbolo": simbolo,
        "reais_por_dolar": float(contrato["ajuste"] / DOLARES_POR_CONTRATO),
        "variacao": float(contrato["ajuste"] / contrato["ajuste_vespera"] - 1),
    }


# --- o dia na história ---------------------------------------------------------------------------


def lugar_na_historia(ibovespa: pd.Series, dia: date) -> dict[str, object]:
    """Onde a variação do Ibovespa no dia fica entre todas as anteriores: quantos pregões variaram
    tanto quanto ou mais, no mesmo sentido, e quando foi a última vez. Só usa a série até o dia."""
    serie = ibovespa.sort_index()
    serie = serie[serie.index <= pd.Timestamp(dia)]
    if serie.empty or serie.index[-1] != pd.Timestamp(dia) or len(serie) < 2:
        raise FaltaNoBoletimError(
            f"O Ibovespa de {dia:%d/%m/%Y} ou da véspera não está na série."
        )
    variacoes = serie.pct_change().dropna()
    variacao_do_dia = float(variacoes.iloc[-1])
    antes = variacoes.iloc[:-1]
    tao_extremos = (
        antes[antes <= variacao_do_dia]
        if variacao_do_dia < 0
        else antes[antes >= variacao_do_dia]
    )
    return {
        "variacao": variacao_do_dia,
        "pregoes_comparados": len(antes),
        "pregoes_tao_extremos": len(tao_extremos),
        "ultima_vez": tao_extremos.index[-1].date().isoformat()
        if len(tao_extremos)
        else None,
        "desde": antes.index[0].date().isoformat() if len(antes) else None,
    }


# --- o resumo ------------------------------------------------------------------------------------


def resumo_do_pregao(entradas: EntradasDoPregao) -> dict[str, object]:
    """Os números do relatório do dia, um bloco por assunto, cada bloco com a fonte e a data."""
    data = entradas.dia.isoformat()
    historia = lugar_na_historia(entradas.ibovespa, entradas.dia)
    tabela = entradas.empresas
    # só as líquidas: papel sem liquidez não entra no relatório, nem como "a conferir"
    a_conferir = tabela[
        tabela["a_conferir"] & (tabela["volume_vespera"] >= LIQUIDEZ_MINIMA)
    ].sort_values("simbolo")
    return {
        "pregao": data,
        "vespera": entradas.vespera.isoformat(),
        "ibovespa": {
            "pontos": float(entradas.ibovespa[pd.Timestamp(entradas.dia)]),
            **historia,
            "fonte": FONTE_DO_INDICE,
            "data": data,
        },
        "amplitude": {
            **amplitude(tabela),
            "liquidez_minima": LIQUIDEZ_MINIMA,
            "fonte": FONTE_DAS_ACOES,
            "data": data,
        },
        "setores": {
            "lista": setores_contra_o_indice(tabela, historia["variacao"]),
            "fonte": FONTE_DOS_SETORES,
            "data": data,
        },
        "maiores": {
            **maiores_altas_e_quedas(tabela),
            "fonte": FONTE_DAS_ACOES,
            "data": data,
        },
        "juros": {
            **taxa_do_di(entradas.contratos, entradas.dia),
            "fonte": FONTE_DOS_JUROS,
            "data": data,
        },
        "dolar": {
            **dolar_futuro(entradas.contratos, entradas.dia),
            "fonte": FONTE_DO_DOLAR,
            "data": data,
        },
        "a_conferir": [_linha_da_lista(linha) for _, linha in a_conferir.iterrows()],
    }
