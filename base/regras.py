"""Regras fixas do selo "dado em conferência" (ADR 0028, item 2; série 1).

Cada regra recebe as contas lidas por `base/contas_cvm.py` e devolve **achados**: o número que
chamou a atenção, o que se esperava e o porquê, em português, para o selo mostrar ao lado do número.
As regras nunca corrigem nem apagam nada; só apontam. Todas são explicáveis e têm tolerância para
arredondamento (a CVM publica em milhares de reais).

Regras desta versão:
- **R1:** ativo total (BPA, conta 1) diferente do passivo total (BPP, conta 2, que inclui o
  patrimônio líquido), no período do próprio documento.
- **R2:** subtotal do balanço que não fecha: conta mãe e contas filhas preenchidas, e a soma das
  filhas diferente da mãe. Só BPA e BPP, onde a árvore de contas é sempre uma soma; na DRE e na
  DFC há contas que não somam (resultados intermediários), o que daria alarme falso.
- **R11:** conta mãe em branco (zero) com as filhas preenchidas: quem lê a mãe vê zero onde há
  valor.

Medido na DFP 2022 inteira (13/10/2026, 729 empresas): R1 não disparou (o sistema da CVM já confere
na entrega); a 1ª versão da R2 dava 2.287 alarmes em 411 empresas, quase todos **filhas zeradas
com a mãe preenchida**, hábito comum de preenchimento e não número errado, que por isso não
dispara; sobraram 29 casos de R2 (10 empresas) e 34 de R11 (9 empresas).

`VERSAO_DAS_REGRAS` vai junto de cada achado gravado: mudou a regra, os achados podem ser refeitos.
"""

from dataclasses import dataclass

import pandas as pd

from src.negociacoes import formatar_valor

VERSAO_DAS_REGRAS = "1"
TOLERANCIA_EM_REAIS = 1000.0  # um "mil" da escala MIL: arredondamento da própria CVM
TOLERANCIA_R1 = 0.001  # 0,1% do maior dos dois
TOLERANCIA_R2 = 0.005  # 0,5% da conta mãe (as filhas arredondam uma a uma)
DEMONSTRACOES_DO_BALANCO = ("BPA", "BPP")
CHAVE = ["cnpj", "documento", "referencia", "versao", "grupo"]


@dataclass(frozen=True)
class Achado:
    regra: str
    cnpj: str
    documento: str
    referencia: pd.Timestamp
    grupo: str  # "con" (consolidado) ou "ind" (individual)
    conta: str
    valor: float | None  # o número publicado
    valor_esperado: float | None  # o que a regra esperava encontrar
    porque: str  # frase para o selo


def _reais(valor: float) -> str:
    return formatar_valor(valor, "BRL")


def _diferente(valor: float, esperado: float, tolerancia_relativa: float) -> bool:
    diferenca = abs(valor - esperado)
    limite = max(
        TOLERANCIA_EM_REAIS, tolerancia_relativa * max(abs(valor), abs(esperado))
    )
    return diferenca > limite


def _do_documento(contas: pd.DataFrame) -> pd.DataFrame:
    """Só o período do próprio documento: o "penúltimo" é o do documento anterior."""
    return contas[contas["ordem"] == "ultimo"]


def r1_ativo_passivo(contas: pd.DataFrame) -> list[Achado]:
    """Ativo total diferente do passivo total (que inclui o patrimônio líquido)."""
    proprias = _do_documento(contas)
    ativo = proprias[(proprias["demonstracao"] == "BPA") & (proprias["conta"] == "1")]
    passivo = proprias[(proprias["demonstracao"] == "BPP") & (proprias["conta"] == "2")]
    juntos = ativo.merge(passivo, on=CHAVE, suffixes=("_ativo", "_passivo"))
    return [
        _achado_r1(linha)
        for linha in juntos.itertuples(index=False)
        if _diferente(linha.valor_ativo, linha.valor_passivo, TOLERANCIA_R1)
    ]


def _achado_r1(linha: tuple) -> Achado:
    return Achado(
        regra="R1",
        cnpj=linha.cnpj,
        documento=linha.documento,
        referencia=linha.referencia,
        grupo=linha.grupo,
        conta="1",
        valor=float(linha.valor_ativo),
        valor_esperado=float(linha.valor_passivo),
        porque=(
            f"O ativo total ({_reais(linha.valor_ativo)}) não bate com o passivo total mais o "
            f"patrimônio líquido ({_reais(linha.valor_passivo)}). Num balanço os dois lados são "
            "sempre iguais."
        ),
    )


def _mae(conta: str) -> str | None:
    return conta.rsplit(".", 1)[0] if "." in conta else None


def _somas_das_filhas(contas: pd.DataFrame) -> pd.DataFrame:
    """Cada conta do balanço com a soma e a quantidade das filhas diretas (pelo menos 2)."""
    balanco = _do_documento(contas)
    balanco = balanco[balanco["demonstracao"].isin(DEMONSTRACOES_DO_BALANCO)].copy()
    balanco["mae"] = balanco["conta"].map(_mae)
    filhas = balanco.dropna(subset=["mae"])
    somas = (
        filhas.groupby([*CHAVE, "demonstracao", "mae"])["valor"]
        .agg(soma="sum", quantas="size")
        .reset_index()
        .rename(columns={"mae": "conta"})
    )
    somas = somas[somas["quantas"] >= 2]
    return balanco.merge(somas, on=[*CHAVE, "demonstracao", "conta"])


def _preenchido(valor: float) -> bool:
    return abs(valor) > TOLERANCIA_EM_REAIS


def r2_subtotais(contas: pd.DataFrame) -> list[Achado]:
    """Mãe e filhas preenchidas, e a soma das filhas diretas não fecha com a mãe."""
    return [
        _achado_r2(linha)
        for linha in _somas_das_filhas(contas).itertuples(index=False)
        if _preenchido(linha.valor)
        and _preenchido(linha.soma)
        and _diferente(linha.valor, linha.soma, TOLERANCIA_R2)
    ]


def _achado_r2(linha: tuple) -> Achado:
    return Achado(
        regra="R2",
        cnpj=linha.cnpj,
        documento=linha.documento,
        referencia=linha.referencia,
        grupo=linha.grupo,
        conta=linha.conta,
        valor=float(linha.valor),
        valor_esperado=float(linha.soma),
        porque=(
            f"A conta {linha.conta} ({linha.descricao}) vale {_reais(linha.valor)}, mas as "
            f"{linha.quantas} contas abaixo dela somam {_reais(linha.soma)}."
        ),
    )


def r11_mae_em_branco(contas: pd.DataFrame) -> list[Achado]:
    """Conta mãe zerada com as filhas diretas preenchidas."""
    return [
        _achado_r11(linha)
        for linha in _somas_das_filhas(contas).itertuples(index=False)
        if not _preenchido(linha.valor) and _preenchido(linha.soma)
    ]


def _achado_r11(linha: tuple) -> Achado:
    return Achado(
        regra="R11",
        cnpj=linha.cnpj,
        documento=linha.documento,
        referencia=linha.referencia,
        grupo=linha.grupo,
        conta=linha.conta,
        valor=float(linha.valor),
        valor_esperado=float(linha.soma),
        porque=(
            f"A conta {linha.conta} ({linha.descricao}) veio em branco, mas as {linha.quantas} "
            f"contas abaixo dela somam {_reais(linha.soma)}."
        ),
    )
