"""Custos do Brasil para as estratégias quant (base comum das 8 P0; ADR 0118).

Tudo o que o relatório de 29/10 (seção 14) manda ter "desde o primeiro experimento", numa tabela
só, com versão: corretagem, emolumentos, imposto de renda por mês (com isenção e prejuízo a
compensar), aluguel com mínimo, lote padrão ou fracionário, IOF e spread de câmbio.

| Custo | Regra desta versão |
|---|---|
| Corretagem | R$ por ordem (muitas corretoras cobram zero) |
| Emolumentos à vista | 0,030% do valor (negociação 0,005% + liquidação 0,0224% + registro 0,0026%, faixa de até R$ 3 milhões por mês); no leilão de abertura ou de fechamento a negociação é 0,007% (total 0,032%); day trade 0,023% (negociação 0,005% + liquidação 0,018%, primeira faixa). Tabela da B3 lida em 03/11/2026 |
| Futuros | R$ por contrato, por lado: mini índice (WIN) R$ 1,97 × fator 0,2 = R$ 0,394 na primeira faixa (tabela da B3 lida em 03/11/2026). A tarifa do DI1 está em imagem na página da B3 e **fica a confirmar**: o DI1 usa o valor do WIN como aproximação |
| Cripto | 0,100% do valor por lado (tabela da Binance para usuário comum, lida em 03/11/2026) |
| IR | 15% no swing, 20% no day trade, 15% em cripto; isenção de R$ 20 mil de vendas no mês só em ações (não em ETF) e de R$ 35 mil em cripto (Lei 9.250/1995, art. 22, II; Perguntas e Respostas IRPF 2024, 627 e 653, lidos em 03/11/2026) |
| Prejuízo | compensa os lucros dos meses seguintes da mesma apuração (swing e day trade são apurações separadas) |
| Aluguel | % ao ano sobre o valor, dias corridos, mínimo de R$ 10 por contrato |
| Câmbio | IOF + spread sobre o valor convertido (cripto em reais) |

Hipótese assumida no imposto: o ganho de um mês isento não paga imposto nem consome o prejuízo
acumulado; o prejuízo de qualquer mês acumula. A versão de estresse (`em_estresse`) dobra o que
é custo de corretora ou de bolsa e não mexe no que é lei (alíquotas, isenções, IOF).

Nada aqui olha o futuro: o imposto do mês usa só as operações até aquele mês (há teste).

Versões: v0.1 (29/10/2026) foi a primeira tabela, com cinco itens "a confirmar"; v0.2 (03/11/2026)
leu na fonte a tarifa de day trade (0,030% → 0,023%), a tarifa do WIN (R$ 0,25 → R$ 0,394), a taxa
e a isenção de cripto (confirmadas) e acrescentou a tarifa do leilão (`emolumentos_no_leilao`).
Mudar um valor da tabela é versão nova dos custos, não do critério (pré-registro quant, seção 3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import pandas as pd

VERSAO = "v0.2"
CLASSES = ("acoes", "etf", "futuros", "cripto")
LOTE_PADRAO = 100
DIAS_DO_ANO = 365  # o aluguel conta dias corridos
COLUNAS_DO_IR = (
    "vendas",
    "resultado",
    "isento",
    "prejuizo_compensado",
    "base",
    "imposto",
    "prejuizo_acumulado",
)


@dataclass(frozen=True)
class CustosBR:
    """Tabela de custos; os campos em `a_confirmar` ainda não foram lidos na fonte oficial."""

    corretagem_por_ordem: float = 0.0
    emolumentos_a_vista: float = 0.0003
    emolumentos_no_leilao: float = (
        0.00032  # leilão de abertura ou de fechamento, não day trade
    )
    emolumentos_day_trade: float = 0.00023
    tarifa_futuro_por_contrato: float = (
        0.394  # WIN; o DI1 usa o mesmo valor (a confirmar)
    )
    taxa_cripto_por_lado: float = 0.001
    ir_swing: float = 0.15
    ir_day_trade: float = 0.20
    ir_cripto: float = 0.15
    isencao_acoes_no_mes: float = 20_000.0
    isencao_cripto_no_mes: float = 35_000.0
    aluguel_minimo: float = 10.0
    iof_cambio: float = 0.0038
    spread_cambio: float = 0.005
    fator_de_estresse: float = 1.0
    a_confirmar: tuple[str, ...] = (
        "tarifa_futuro_por_contrato",  # só o DI1: a tarifa do WIN foi lida na fonte
        "spread_cambio",
    )

    def em_estresse(self, fator: float = 2.0) -> CustosBR:
        """A mesma tabela com os custos de corretora e de bolsa multiplicados; lei não muda."""
        return replace(
            self,
            corretagem_por_ordem=self.corretagem_por_ordem * fator,
            emolumentos_a_vista=self.emolumentos_a_vista * fator,
            emolumentos_no_leilao=self.emolumentos_no_leilao * fator,
            emolumentos_day_trade=self.emolumentos_day_trade * fator,
            tarifa_futuro_por_contrato=self.tarifa_futuro_por_contrato * fator,
            taxa_cripto_por_lado=self.taxa_cripto_por_lado * fator,
            spread_cambio=self.spread_cambio * fator,
            fator_de_estresse=self.fator_de_estresse * fator,
        )

    def aliquota(self, classe: str, day_trade: bool) -> float:
        if day_trade:
            return self.ir_day_trade
        return self.ir_cripto if classe == "cripto" else self.ir_swing

    def isencao_no_mes(self, classe: str, day_trade: bool) -> float:
        """Até quanto de vendas no mês o ganho fica isento; zero quando não há isenção."""
        if day_trade:
            return 0.0
        if classe == "acoes":
            return self.isencao_acoes_no_mes
        if classe == "cripto":
            return self.isencao_cripto_no_mes
        return 0.0


PADRAO = CustosBR()


def _conferir_classe(classe: str) -> None:
    if classe not in CLASSES:
        raise ValueError(f"classe desconhecida: {classe!r}; use uma de {CLASSES}")


def custo_de_negociar(
    valor: float,
    classe: str,
    *,
    day_trade: bool = False,
    no_leilao: bool = False,
    contratos: float | None = None,
    custos: CustosBR = PADRAO,
) -> float:
    """Custo de uma ordem (um lado), em reais: corretagem mais a taxa da bolsa ou da corretora.

    `valor` é o valor financeiro negociado; em futuros ele não conta, o que conta é `contratos`
    (fração de contrato é aceita: a simulação declara quando usa). `no_leilao` é a ordem à vista
    executada no leilão de abertura ou de fechamento (tarifa maior), quando não é day trade.
    """
    _conferir_classe(classe)
    if valor < 0:
        raise ValueError("o valor negociado não pode ser negativo")
    if classe == "futuros":
        if contratos is None:
            raise ValueError("em futuros informe o número de contratos")
        return (
            custos.corretagem_por_ordem
            + abs(contratos) * custos.tarifa_futuro_por_contrato
        )
    if classe == "cripto":
        taxa = custos.taxa_cripto_por_lado
    elif day_trade:
        taxa = custos.emolumentos_day_trade
    elif no_leilao:
        taxa = custos.emolumentos_no_leilao
    else:
        taxa = custos.emolumentos_a_vista
    return custos.corretagem_por_ordem + valor * taxa


def arredondar_lote(
    quantidade: float, *, fracionario: bool = False, lote: int = LOTE_PADRAO
) -> int:
    """Quantidade que dá para negociar: múltiplo do lote (ou inteira, no fracionário), para o zero."""
    passo = 1 if fracionario else lote
    inteira = math.trunc(quantidade / passo) * passo
    return int(inteira)


def apurar_ir_mensal(
    vendas: pd.Series,
    resultado: pd.Series,
    classe: str,
    *,
    day_trade: bool = False,
    custos: CustosBR = PADRAO,
) -> pd.DataFrame:
    """Imposto de renda de cada mês de uma apuração (uma classe, swing ou day trade).

    `vendas` é o valor vendido em cada dia e `resultado` o lucro (positivo) ou prejuízo (negativo)
    realizado naquele dia, as duas com as mesmas datas. Devolve uma linha por mês, em ordem, com
    as colunas de `COLUNAS_DO_IR`. O prejuízo acumulado só vem de meses anteriores.
    """
    _conferir_classe(classe)
    if not vendas.index.equals(resultado.index):
        raise ValueError("vendas e resultado precisam ter as mesmas datas")
    if vendas.empty:
        return pd.DataFrame(columns=list(COLUNAS_DO_IR))
    por_mes = pd.DataFrame({"vendas": vendas, "resultado": resultado})
    por_mes = (
        por_mes.groupby(pd.DatetimeIndex(por_mes.index).to_period("M"))
        .sum()
        .sort_index()
    )
    isencao = custos.isencao_no_mes(classe, day_trade)
    aliquota = custos.aliquota(classe, day_trade)

    linhas = []
    prejuizo_acumulado = 0.0
    for mes, linha in por_mes.iterrows():
        vendas_do_mes, resultado_do_mes = (
            float(linha["vendas"]),
            float(linha["resultado"]),
        )
        isento = isencao > 0 and vendas_do_mes <= isencao
        compensado = base = imposto = 0.0
        if resultado_do_mes < 0:
            prejuizo_acumulado += -resultado_do_mes
        elif not isento:
            compensado = min(prejuizo_acumulado, resultado_do_mes)
            prejuizo_acumulado -= compensado
            base = resultado_do_mes - compensado
            imposto = base * aliquota
        linhas.append(
            {
                "mes": mes,
                "vendas": vendas_do_mes,
                "resultado": resultado_do_mes,
                "isento": isento,
                "prejuizo_compensado": compensado,
                "base": base,
                "imposto": imposto,
                "prejuizo_acumulado": prejuizo_acumulado,
            }
        )
    return pd.DataFrame(linhas).set_index("mes")[list(COLUNAS_DO_IR)]


def custo_do_aluguel(
    valor: float, *, dias: int, taxa_anual: float, custos: CustosBR = PADRAO
) -> float:
    """Aluguel de uma posição vendida: taxa ao ano sobre o valor, por dias corridos, com mínimo."""
    if dias <= 0:
        raise ValueError("dias precisa ser positivo")
    return max(valor * taxa_anual * dias / DIAS_DO_ANO, custos.aluguel_minimo)


def custo_do_cambio(valor: float, *, custos: CustosBR = PADRAO) -> float:
    """IOF mais spread sobre o valor convertido (a versão em reais das estratégias de cripto)."""
    return valor * (custos.iof_cambio + custos.spread_cambio)
