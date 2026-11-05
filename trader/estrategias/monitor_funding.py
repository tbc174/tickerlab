"""Monitor da ficha P0-6: funding anualizado líquido e carry em reais, com os dois alertas.

Escopo da ficha: coleta e monitor; **nenhuma ordem, nenhum backtest de estratégia**; não passa pelo
critério da seção 5. As definições abaixo foram fixadas antes de qualquer número (03/11/2026):

- **Funding do dia:** a soma dos pagamentos de funding do perpétuo no dia de Brasília (quem está vendido
  no perpétuo recebe quando é positivo).
- **Funding anualizado bruto:** a média dos últimos 7 dias do funding do dia × 365 (só dias com 7 dias
  completos; um trecho novo começa do zero).
- **Funding anualizado líquido:** o bruto menos o custo da operação de carry (comprado à vista e vendido
  no perpétuo, montada e desfeita a cada 30 dias: 4 pernas × a taxa de cripto por lado de `custos_br`
  × 365/30) e, quando o resultado é positivo, menos o IR de cripto (15%).
- **Alerta 1:** funding anualizado líquido acima de 10% a.a.
- **Carry em reais:** funding líquido (em dólar) + CDI − cupom cambial de 30 dias, a fórmula da ficha. O
  CDI é a taxa anual efetiva do último dia útil antes do dia ((1 + CDI do dia)^252 − 1); o cupom é o da
  última curva da B3 publicada antes do dia. Como o CDI entra somando e é a régua do alerta, o alerta 2
  é o mesmo que funding líquido acima do cupom.
- **Alerta 2:** carry em reais acima do CDI.
- **Basis:** o índice de prêmio do dia (perpétuo contra o índice à vista); só mostrado, sem alerta.

Nada aqui é recomendação de investimento.
"""

from __future__ import annotations

import pandas as pd

from trader.custos_br import CustosBR
from trader.estrategias.dados_funding import FUSO_DE_BRASILIA

DIAS_DA_MEDIA = 7
DIAS_NO_ANO = 365
DIAS_UTEIS_NO_ANO = 252
PERNAS_DO_CARRY = 4  # compra e venda à vista, venda e recompra do perpétuo
DIAS_ENTRE_ROLAGENS = 30
LIMITE_DO_FUNDING = 0.10  # a.a.
PERCENTIS = (0.10, 0.50, 0.90)


def funding_por_dia(pagamentos: pd.Series) -> pd.Series:
    """Soma dos pagamentos (hora UTC sem fuso) por dia de Brasília.

    O primeiro e o último dia ficam de fora quando têm menos pagamentos que o dia típico: o arquivo
    mensal começa à meia-noite UTC, que ainda é a véspera em Brasília.
    """
    horas = (
        pd.DatetimeIndex(pagamentos.index)
        .tz_localize("UTC")
        .tz_convert(FUSO_DE_BRASILIA)
    )
    dias = pd.DatetimeIndex(horas.tz_localize(None).normalize())
    soma = pagamentos.groupby(dias).sum().sort_index()
    contagem = pagamentos.groupby(dias).size().sort_index()
    tipico = contagem.median()
    pontas = [d for d in contagem.index[[0, -1]].unique() if contagem[d] < tipico]
    return soma.drop(pontas)


def custo_anualizado(custos: CustosBR | None = None) -> float:
    custos = CustosBR() if custos is None else custos
    return (
        PERNAS_DO_CARRY
        * custos.taxa_cripto_por_lado
        * DIAS_NO_ANO
        / DIAS_ENTRE_ROLAGENS
    )


def funding_anualizado(diario: pd.Series) -> pd.Series:
    """Média de 7 dias corridos × 365; dia sem funding na janela deixa o valor vazio."""
    corridos = diario.asfreq("D")
    return (
        corridos.rolling(DIAS_DA_MEDIA, min_periods=DIAS_DA_MEDIA).mean() * DIAS_NO_ANO
    )


def funding_liquido(bruto: pd.Series, custos: CustosBR | None = None) -> pd.Series:
    custos = CustosBR() if custos is None else custos
    depois_do_custo = bruto - custo_anualizado(custos)
    return depois_do_custo.where(
        depois_do_custo <= 0, depois_do_custo * (1 - custos.ir_cripto)
    )


def taxa_conhecida_antes(serie: pd.Series, dias: pd.DatetimeIndex) -> pd.Series:
    """Em cada dia, o último valor de `serie` publicado num dia anterior (nunca o do próprio dia)."""
    anterior = serie.sort_index()
    anterior.index = pd.DatetimeIndex(anterior.index) + pd.Timedelta(days=1)
    anterior = anterior[~anterior.index.duplicated(keep="last")]
    return anterior.reindex(anterior.index.union(dias)).ffill().reindex(dias)


def cdi_anual(cdi_diario: pd.Series) -> pd.Series:
    return (1 + cdi_diario) ** DIAS_UTEIS_NO_ANO - 1


def monitorar(
    pagamentos: pd.Series,
    premio: pd.Series,
    cupom: pd.Series,
    cdi_diario: pd.Series,
    custos: CustosBR | None = None,
) -> pd.DataFrame:
    """A tabela diária de um trecho e de um par: as medidas e os dois alertas."""
    bruto = funding_anualizado(funding_por_dia(pagamentos))
    dias = pd.DatetimeIndex(bruto.index)
    liquido = funding_liquido(bruto, custos)
    cdi = taxa_conhecida_antes(cdi_anual(cdi_diario), dias)
    cupom_do_dia = taxa_conhecida_antes(cupom, dias)
    carry = liquido + cdi - cupom_do_dia
    tabela = pd.DataFrame(
        {
            "funding_bruto": bruto,
            "funding_liquido": liquido,
            "cdi": cdi,
            "cupom": cupom_do_dia,
            "carry_em_reais": carry,
            "basis": premio.reindex(dias),
        },
        index=dias,
    )
    tabela["alerta_funding"] = tabela["funding_liquido"] > LIMITE_DO_FUNDING
    tabela["alerta_carry"] = tabela["carry_em_reais"] > tabela["cdi"]
    return tabela.dropna(subset=["funding_bruto"])


def maior_sequencia(alertas: pd.Series) -> int:
    """O maior número de dias seguidos com o alerta ligado."""
    grupos = (~alertas).cumsum()
    return int(alertas.groupby(grupos).sum().max()) if alertas.any() else 0


def _percentis(serie: pd.Series) -> dict[str, float | None]:
    limpa = serie.dropna()
    return {
        f"p{int(p * 100)}": (float(limpa.quantile(p)) if len(limpa) else None)
        for p in PERCENTIS
    }


def resumir(tabela: pd.DataFrame) -> dict:
    """Quanto tempo cada alerta ficou ligado e como as medidas se distribuíram."""
    com_carry = tabela.dropna(subset=["carry_em_reais"])
    return {
        "inicio": tabela.index.min().date().isoformat(),
        "fim": tabela.index.max().date().isoformat(),
        "dias": len(tabela),
        "dias_com_carry": len(com_carry),
        "alerta_funding": float(tabela["alerta_funding"].mean()),
        "alerta_carry": float(com_carry["alerta_carry"].mean())
        if len(com_carry)
        else None,
        "maior_sequencia_funding": maior_sequencia(tabela["alerta_funding"]),
        "maior_sequencia_carry": maior_sequencia(com_carry["alerta_carry"]),
        "funding_bruto": _percentis(tabela["funding_bruto"]),
        "funding_liquido": _percentis(tabela["funding_liquido"]),
        "cupom": _percentis(tabela["cupom"]),
        "basis": _percentis(tabela["basis"]),
        "por_ano": {
            str(ano): {
                "dias": len(parte),
                "funding_liquido_mediano": float(parte["funding_liquido"].median()),
                "alerta_funding": float(parte["alerta_funding"].mean()),
                "alerta_carry": float(
                    parte.dropna(subset=["carry_em_reais"])["alerta_carry"].mean()
                )
                if parte["carry_em_reais"].notna().any()
                else None,
            }
            for ano, parte in tabela.groupby(tabela.index.year)
        },
    }


def ultimo_dia(tabela: pd.DataFrame) -> dict:
    """A leitura do último dia do trecho (o "hoje" do monitor)."""
    linha = tabela.iloc[-1]
    return {
        "dia": tabela.index[-1].date().isoformat(),
        **{
            coluna: (None if pd.isna(linha[coluna]) else float(linha[coluna]))
            for coluna in (
                "funding_bruto",
                "funding_liquido",
                "cdi",
                "cupom",
                "carry_em_reais",
                "basis",
            )
        },
        "alerta_funding": bool(linha["alerta_funding"]),
        "alerta_carry": bool(linha["alerta_carry"]),
    }
