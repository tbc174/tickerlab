"""Contas da ficha que saem da DFC, da DVA e da DRE (série T1): EBITDA, capex, FCF e dividendos recebidos.

Uma linha por empresa, grupo (individual ou consolidado) e período da DFC (no ITR, do começo do ano
ao fim do trimestre). Cada número leva as contas de onde veio e o dia em que ficou público, para a
tela mostrar a fonte e para o backtest não usar o que ainda não existia.

- **EBIT:** DRE 3.05, só quando a conta é o "resultado antes do resultado financeiro" (466 de 474
  empresas nos DFP consolidados de 2023). Nos bancos e seguradoras a 3.05 é o resultado antes dos
  tributos: fica vazio, não errado.
- **Depreciação e amortização (D&A):** a da DVA (7.04.01 "depreciação, amortização e exaustão", 466
  de 474 em 2023); sem DVA, a soma das linhas de depreciação e amortização dos ajustes da DFC
  (6.01.01.*), fora as amortizações que são despesa financeira (custo de captação, juros).
- **EBITDA** = EBIT + D&A.
- **Caixa operacional:** DFC 6.01.
- **Capex:** as saídas para comprar imobilizado e intangível nas atividades de investimento
  (6.02.*), positivo; vendas, baixas e distratos ficam fora. Linha mãe e filhas não somam duas vezes.
- **FCF** (fluxo de caixa livre) = caixa operacional − capex.
- **Dividendos recebidos:** dividendos e juros sobre capital próprio recebidos, na operação ou no
  investimento (as empresas põem em um ou outro); "a receber" fica fora.

Sem a linha, o número fica vazio: nada é inventado. Nos DFP consolidados de 2023 (475 empresas com
DFC; medido em 19/10/2026): EBITDA em 95%, capex e FCF em 92%, D&A em 100% (toda pela DVA),
dividendos recebidos em 45% (quem não recebe não tem a linha). Em 6 empresas o capex sai negativo
porque a própria empresa informou a compra com sinal de entrada: fica como informado. `contas`: no formato de `base/contas_cvm.py`,
ou uma foto de `base/ponto_no_tempo.como_era_em` (aí cada número vale só o que era público no dia).
"""

import re
import unicodedata

import pandas as pd

DFC = ("DFC_MI", "DFC_MD")
DRE, DVA = "DRE", "DVA"
EBIT, CAIXA_OPERACIONAL = "3.05", "6.01"
PERIODO = ["cnpj", "grupo", "inicio", "fim"]
COLUNAS = (
    *PERIODO,
    "ebit",
    "depreciacao_amortizacao",
    "fonte_da_depreciacao",
    "ebitda",
    "caixa_operacional",
    "capex",
    "contas_do_capex",
    "fcf",
    "dividendos_recebidos",
    "contas_dos_dividendos",
    "divulgado_em",
)

E_EBIT = re.compile(r"antes do resultado financeiro")
DEPRECIACAO = re.compile(r"deprecia|amortiza|exaust")
NAO_E_DEPRECIACAO = re.compile(r"capta|juros|emprest|financ|debent")
IMOBILIZADO = re.compile(r"imobiliz|intang")
NAO_E_CAPEX = re.compile(r"venda|vend|aliena|receb|baixa|distrato|ressarc|reembols")
DIVIDENDOS = re.compile(r"dividend|juros sobre (?:o )?capital|jcp|jscp")
NAO_E_RECEBIDO = re.compile(r"a receber|imposto|retid|irrf|pag")


def _simples(descricoes: pd.Series) -> pd.Series:
    """Sem acento e em minúsculas (calculado uma vez por descrição distinta)."""

    def simples(texto: str) -> str:
        texto = unicodedata.normalize("NFD", str(texto))
        sem = "".join(c for c in texto if unicodedata.category(c) != "Mn")
        return sem.lower().strip()

    unicas = descricoes.drop_duplicates()
    return descricoes.map(dict(zip(unicas, unicas.map(simples), strict=True)))


def _so_as_mais_altas(linhas: pd.DataFrame) -> pd.DataFrame:
    """Tira a linha cuja mãe também foi escolhida (a mãe já soma as filhas)."""
    escolhidas = set(zip(*(linhas[c] for c in [*PERIODO, "conta"]), strict=True))

    def tem_mae(linha: tuple) -> bool:
        *periodo, conta = linha
        partes = conta.split(".")
        maes = (".".join(partes[:n]) for n in range(1, len(partes)))
        return any((*periodo, mae) in escolhidas for mae in maes)

    chaves = zip(*(linhas[c] for c in [*PERIODO, "conta"]), strict=True)
    return linhas[[not tem_mae(chave) for chave in chaves]]


def _somar(linhas: pd.DataFrame, nome: str, sinal: float = 1.0) -> pd.DataFrame:
    """Por período: a soma (com `sinal`), as contas usadas ("DFC_MI 6.02.01 + 6.02.02") e a data."""
    if linhas.empty:
        vazio = pd.MultiIndex.from_tuples([], names=PERIODO)
        return pd.DataFrame(
            {
                nome: pd.Series(dtype=float),
                f"contas_{nome}": pd.Series(dtype=object),
                f"divulgado_{nome}": pd.Series(dtype="datetime64[ns]"),
            }
        ).set_axis(vazio)
    linhas = _so_as_mais_altas(linhas).sort_values("conta")
    grupos = linhas.groupby(PERIODO, dropna=False)
    return pd.DataFrame(
        {
            nome: grupos["valor"].sum() * sinal,
            f"contas_{nome}": grupos.apply(_rotulo, include_groups=False),
            f"divulgado_{nome}": grupos["divulgado_em"].max(),
        }
    )


def _rotulo(linhas: pd.DataFrame) -> str:
    return f"{linhas['demonstracao'].iloc[0]} " + " + ".join(linhas["conta"])


def _preparar(contas: pd.DataFrame) -> pd.DataFrame:
    """Só as demonstrações usadas, uma linha por conta e período (a versão mais nova)."""
    linhas = contas[contas["demonstracao"].isin([*DFC, DRE, DVA])].copy()
    if "divulgado_em" not in linhas:
        linhas["divulgado_em"] = pd.NaT
    linhas["s"] = _simples(linhas["descricao"])
    ordem = [c for c in ("divulgado_em", "versao") if c in linhas]
    chave = [*PERIODO, "demonstracao", "conta"]
    return linhas.sort_values(ordem).drop_duplicates(chave, keep="last")


def _da_dfc(linhas: pd.DataFrame) -> pd.Series:
    return linhas["demonstracao"].isin(DFC)


def _ebit(linhas: pd.DataFrame) -> pd.DataFrame:
    ebit = linhas[
        (linhas["demonstracao"] == DRE)
        & (linhas["conta"] == EBIT)
        & linhas["s"].str.contains(E_EBIT)
    ]
    tabela = ebit.set_index(PERIODO)[["valor", "divulgado_em"]]
    return tabela.rename(columns={"valor": "ebit", "divulgado_em": "divulgado_ebit"})


def _caixa_operacional(linhas: pd.DataFrame) -> pd.DataFrame:
    caixa = linhas[_da_dfc(linhas) & (linhas["conta"] == CAIXA_OPERACIONAL)]
    tabela = caixa.set_index(PERIODO)[["valor", "divulgado_em"]]
    return tabela.rename(
        columns={"valor": "caixa_operacional", "divulgado_em": "divulgado_caixa"}
    )


def _depreciacao(linhas: pd.DataFrame) -> pd.DataFrame:
    """A D&A da DVA (positiva); sem DVA no período, a das linhas da DFC."""
    da_dva = linhas[
        (linhas["demonstracao"] == DVA)
        & (linhas["conta"].str.count(r"\.") == 2)
        & linhas["s"].str.startswith("deprecia")
    ]
    dva = _somar(da_dva, "da").assign(da=lambda t: t["da"].abs())
    da_dfc = linhas[
        _da_dfc(linhas)
        & linhas["conta"].str.startswith("6.01.01.")
        & linhas["s"].str.contains(DEPRECIACAO)
        & ~linhas["s"].str.contains(NAO_E_DEPRECIACAO)
    ]
    dfc = _somar(da_dfc, "da")
    tabela = pd.concat([dva, dfc[~dfc.index.isin(dva.index)]])
    return tabela.rename(
        columns={
            "da": "depreciacao_amortizacao",
            "contas_da": "fonte_da_depreciacao",
            "divulgado_da": "divulgado_depreciacao",
        }
    )


def _capex(linhas: pd.DataFrame) -> pd.DataFrame:
    capex = linhas[
        _da_dfc(linhas)
        & linhas["conta"].str.startswith("6.02.")
        & linhas["s"].str.contains(IMOBILIZADO)
        & ~linhas["s"].str.contains(NAO_E_CAPEX)
    ]
    tabela = _somar(capex, "capex", sinal=-1.0)
    return tabela.rename(columns={"contas_capex": "contas_do_capex"})


def _dividendos(linhas: pd.DataFrame) -> pd.DataFrame:
    dividendos = linhas[
        _da_dfc(linhas)
        & linhas["conta"].str.match(r"6\.0[123]\.")
        & linhas["s"].str.contains(DIVIDENDOS)
        & linhas["s"].str.contains("receb")
        & ~linhas["s"].str.contains(NAO_E_RECEBIDO)
    ]
    tabela = _somar(dividendos, "dividendos")
    return tabela.rename(
        columns={
            "dividendos": "dividendos_recebidos",
            "contas_dividendos": "contas_dos_dividendos",
        }
    )


def indicadores_de_caixa(contas: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por período com DFC: os números da ficha, as contas usadas e `divulgado_em`.

    `divulgado_em` é o dia mais novo entre as linhas que entraram nas contas (a partir dele, tudo o
    que a linha mostra era público).
    """
    linhas = _preparar(contas)
    periodos = linhas.loc[_da_dfc(linhas), PERIODO].drop_duplicates()
    if periodos.empty:
        return pd.DataFrame(columns=list(COLUNAS))
    partes = [
        _ebit(linhas),
        _depreciacao(linhas),
        _caixa_operacional(linhas),
        _capex(linhas),
        _dividendos(linhas),
    ]
    tabela = periodos.set_index(PERIODO).join(partes, how="left")
    tabela["ebitda"] = tabela["ebit"] + tabela["depreciacao_amortizacao"]
    tabela["fcf"] = tabela["caixa_operacional"] - tabela["capex"]
    datas = tabela.filter(like="divulgado_")
    tabela["divulgado_em"] = datas.max(axis=1) if datas.notna().any().any() else pd.NaT
    textos = ["fonte_da_depreciacao", "contas_do_capex", "contas_dos_dividendos"]
    tabela[textos] = tabela[textos].astype(object).where(tabela[textos].notna(), None)
    return tabela.reset_index()[list(COLUNAS)].reset_index(drop=True)
