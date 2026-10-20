"""Diário das operações simuladas: o porquê, o custo e a comparação de cada operação de um backtest.

`trader.backtest` já lista as operações (entrada, saída, lado, retorno). O diário acrescenta, para
quem revisa uma tentativa, o que a lista não diz:

- **decisão**: o fechamento em que a posição foi decidida (o dia anterior à entrada, pelo
  `shift(1)` do backtest); a operação nunca usa o preço do dia da decisão para render;
- **motivo**: o valor do sinal na decisão e o nome da regra; sinal ausente vira "REVISAR";
- **custo e swap** da operação, com as mesmas regras de divisão de `_extrair_operacoes`: na
  virada de lado, metade do custo do dia fica com cada operação; a saída para o caixa cai no
  primeiro dia sem posição e é da operação que acabou;
- **comprado no período**: quanto rendeu ficar comprado no mesmo ativo exatamente nos mesmos dias.

Nada aqui muda a conta do backtest: o diário só lê o `ResultadoBacktest`. Custo e swap são somas
simples em fração do capital; o `retorno` (líquido) é o mesmo, composto, de `resultado.operacoes`.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from trader.backtest import ResultadoBacktest

COLUNAS_DO_DIARIO = [
    "decisao",
    "entrada",
    "saida",
    "lado",
    "dias",
    "sinal_na_decisao",
    "motivo",
    "retorno_bruto",
    "custo",
    "swap",
    "retorno",
    "comprado_no_periodo",
    "aberta",
]
# Abaixo disto a taxa de acerto e o retorno médio mudam muito com uma operação a mais ou a menos:
# com 30 operações, o erro-padrão de uma taxa de acerto perto de 50% ainda é de 9 pontos.
MINIMO_DE_OPERACOES_PARA_JULGAR = 30
AVISO_DE_JANELA_CURTA = (
    "Só {n} operações fechadas: poucas operações para julgar a regra "
    f"(menos de {MINIMO_DE_OPERACOES_PARA_JULGAR}); a taxa de acerto e o retorno médio "
    "mudam muito com uma operação a mais ou a menos."
)
CUIDADOS_DO_DIARIO = (
    "Operações simuladas com dados do passado, não executadas; custos e swap são estimativas "
    "do modelo de custos da tentativa. Isto não é recomendação de investimento nem promessa "
    "de rentabilidade."
)
_TITULOS = {
    "decisao": "Decisão",
    "entrada": "Entrada",
    "saida": "Saída",
    "lado": "Lado",
    "dias": "Dias",
    "motivo": "Motivo",
    "retorno_bruto": "Bruto",
    "custo": "Custo",
    "swap": "Swap",
    "retorno": "Líquido",
    "comprado_no_periodo": "Comprado no período",
    "aberta": "Aberta",
}


def _motivo(regra: str, valor: float) -> str:
    if math.isnan(valor):
        return f"REVISAR: {regra} sem sinal na decisão"
    return f"{regra}: sinal {valor:+.2f} na decisão"


def _custo_da_operacao(
    resultado: ResultadoBacktest,
    entrada: pd.Timestamp,
    saida: pd.Timestamp,
    aberta: bool,
) -> float:
    """Custo do trecho, com metade do custo da virada de lado para cada operação."""
    indice = resultado.posicao.index
    lado = np.sign(resultado.posicao)
    custos = resultado.custos
    total = float(custos.loc[entrada:saida].sum())
    if lado.iloc[indice.get_loc(entrada) - 1] != 0:  # entrou virando de lado
        total -= custos.loc[entrada] / 2
    if not aberta:
        seguinte = indice[indice.get_loc(saida) + 1]
        virou = lado.loc[seguinte] != 0
        total += custos.loc[seguinte] / 2 if virou else custos.loc[seguinte]
    return total


def _composto(retornos: pd.Series) -> float:
    return float((1 + retornos).prod() - 1)


def diario_de_operacoes(
    resultado: ResultadoBacktest,
    retorno_do_ativo: pd.Series,
    sinal: pd.Series,
    regra: str,
) -> pd.DataFrame:
    """Uma linha por operação de `resultado.operacoes`, com as colunas de `COLUNAS_DO_DIARIO`.

    `retorno_do_ativo` é o mesmo usado no backtest (para a comparação); `sinal` é o valor que a
    regra olhou no fim de cada dia (a previsão do modelo, o momento etc.); `regra` é o nome que
    aparece no motivo.
    """
    indice = resultado.posicao.index
    if not retorno_do_ativo.index.equals(indice) or not sinal.index.equals(indice):
        raise ValueError(
            "Retorno do ativo e sinal precisam ter as mesmas datas do backtest."
        )
    linhas = []
    for operacao in resultado.operacoes.itertuples(index=False):
        entrada, saida, aberta = operacao.entrada, operacao.saida, bool(operacao.aberta)
        decisao = indice[
            indice.get_loc(entrada) - 1
        ]  # a posição de hoje foi decidida ontem
        valor = float(sinal.loc[decisao])
        linhas.append(
            {
                "decisao": decisao,
                "entrada": entrada,
                "saida": saida,
                "lado": int(operacao.lado),
                "dias": int(operacao.dias),
                "sinal_na_decisao": valor,
                "motivo": _motivo(regra, valor),
                "retorno_bruto": _composto(resultado.retorno_bruto.loc[entrada:saida]),
                "custo": _custo_da_operacao(resultado, entrada, saida, aberta),
                "swap": float(resultado.swap.loc[entrada:saida].sum()),
                "retorno": float(operacao.retorno),
                "comprado_no_periodo": _composto(
                    retorno_do_ativo.fillna(0.0).loc[entrada:saida]
                ),
                "aberta": aberta,
            }
        )
    return pd.DataFrame(linhas, columns=COLUNAS_DO_DIARIO)


def resumir_diario(diario: pd.DataFrame) -> dict[str, object]:
    """Contagem, taxa de acerto, custo total e o aviso quando há poucas operações fechadas."""
    fechadas = diario[~diario["aberta"].astype(bool)]
    n = len(fechadas)
    janela_curta = n < MINIMO_DE_OPERACOES_PARA_JULGAR
    return {
        "operacoes": len(diario),
        "fechadas": n,
        "abertas": len(diario) - n,
        "taxa_de_acerto": float((fechadas["retorno"] > 0).mean()) if n else math.nan,
        "retorno_medio": float(fechadas["retorno"].mean()) if n else math.nan,
        "custo_total": float(diario["custo"].sum()),
        "janela_curta": janela_curta,
        "aviso": AVISO_DE_JANELA_CURTA.format(n=n) if janela_curta else "",
    }


def _celula(coluna: str, valor: object) -> str:
    if isinstance(valor, pd.Timestamp):
        return valor.strftime("%Y-%m-%d")
    if coluna == "lado":
        return "comprado" if valor == 1 else "vendido"
    if coluna == "aberta":
        return "sim" if valor else "não"
    if isinstance(valor, float):
        return f"{valor:+.2%}"
    return str(valor)


def diario_em_markdown(diario: pd.DataFrame) -> str:
    """O diário em Markdown: a tabela, o resumo com o aviso e os cuidados."""
    colunas = list(_TITULOS)
    linhas = [
        "## Diário das operações simuladas",
        "",
        "| " + " | ".join(_TITULOS[c] for c in colunas) + " |",
        "|" + "---|" * len(colunas),
    ]
    linhas.extend(
        "| " + " | ".join(_celula(c, registro[c]) for c in colunas) + " |"
        for registro in diario.to_dict("records")
    )
    resumo = resumir_diario(diario)
    contagem = (
        f"Operações: {resumo['operacoes']} ({resumo['fechadas']} fechadas, "
        f"{resumo['abertas']} aberta(s))."
    )
    linhas += ["", contagem]
    if resumo["aviso"]:
        linhas += ["", f"**Atenção:** {resumo['aviso']}"]
    linhas += ["", "### Limites e cuidados", "", CUIDADOS_DO_DIARIO, ""]
    return "\n".join(linhas)
