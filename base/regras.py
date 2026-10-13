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
- **R3:** escala suspeita: o mesmo período ou o período seguinte vale cerca de mil vezes mais (ou
  menos) que no documento anterior, sinal de reais e milhares trocados (5 casos na prova do ENET).
- **R4:** valor impossível: ativo total, ativo circulante ou caixa negativos.
- **R6:** número refeito pela própria empresa no balanço seguinte (a coluna "penúltimo" do documento
  seguinte diferente do "último" deste), só nas contas principais (ativo total, receita, lucro e
  patrimônio líquido): 3,9% de todas as contas mudam de um ano para o outro, quase tudo
  reclassificação pequena. O achado vale a partir da entrega do documento seguinte.
- **R9:** linhas repetidas idênticas no arquivo da CVM (contadas por `base/contas_cvm.py`).
- **R10:** lucro do período em branco (zero) numa empresa com receita; a linha do lucro é achada
  pela descrição (7 casos na DFP 2022 e 4 na de 2023).
- **R11:** conta mãe em branco (zero) com as filhas preenchidas: quem lê a mãe vê zero onde há
  valor.

Medido na DFP 2022 inteira (13/10/2026, 729 empresas): R1 não disparou (o sistema da CVM já confere
na entrega); a 1ª versão da R2 dava 2.287 alarmes em 411 empresas, quase todos **filhas zeradas
com a mãe preenchida**, hábito comum de preenchimento e não número errado, que por isso não
dispara; sobraram 29 casos de R2 (10 empresas) e 34 de R11 (9 empresas).

`VERSAO_DAS_REGRAS` vai junto de cada achado gravado: mudou a regra, os achados podem ser refeitos.
"""

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from base.contas_cvm import LeituraDeContas
from src.negociacoes import formatar_valor

VERSAO_DAS_REGRAS = "1"
TOLERANCIA_EM_REAIS = 1000.0  # um "mil" da escala MIL: arredondamento da própria CVM
TOLERANCIA_R1 = 0.001  # 0,1% do maior dos dois
TOLERANCIA_R2 = 0.005  # 0,5% da conta mãe (as filhas arredondam uma a uma)
DEMONSTRACOES_DO_BALANCO = ("BPA", "BPP")
CONTAS_DA_ESCALA = ("1", "3.01")  # ativo total e receita: sempre preenchidas e grandes
FAIXA_DE_MIL_VEZES = (
    700.0,
    1400.0,
)  # razão entre os dois valores que indica escala trocada
NAO_PODEM_SER_NEGATIVAS = {
    "1": "ativo total",
    "1.01": "ativo circulante",
    "1.01.01": "caixa",
}
RECEITA = "3.01"
PATRIMONIO_LIQUIDO = re.compile(r"^patrim[oô]nio l[ií]quido", re.IGNORECASE)
# a linha do lucro do período, achada pela descrição: em parte das empresas a 3.11 é a reversão dos
# juros sobre capital próprio e o lucro fica na 3.13 (medido na DFP 2022)
LINHA_DO_LUCRO = re.compile(
    r"^lucro\s*(/|ou)\s*preju[ií]zo( l[ií]quido)?( consolidado)? do per[ií]odo$",
    re.IGNORECASE,
)
CHAVE = ["cnpj", "documento", "referencia", "versao", "grupo"]
# uma linha de `DataFrame.itertuples()`: tupla com nome, com as colunas da tabela como atributos
Linha = Any


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
    valido_desde: pd.Timestamp | None = (
        None  # quando o achado passou a existir (sem olhar o futuro)
    )


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


def _achado_r1(linha: Linha) -> Achado:
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


def _achado_r2(linha: Linha) -> Achado:
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


def _achado_r11(linha: Linha) -> Achado:
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


def _mil_vezes(valor: float, outro: float) -> bool:
    if not (_preenchido(valor) and _preenchido(outro)):
        return False
    razao = abs(valor / outro)
    menor, maior = FAIXA_DE_MIL_VEZES
    return menor <= razao <= maior or 1 / maior <= razao <= 1 / menor


def _da_escala(contas: pd.DataFrame, ordem: str) -> pd.DataFrame:
    return contas[(contas["ordem"] == ordem) & contas["conta"].isin(CONTAS_DA_ESCALA)]


def r3_escala(contas: pd.DataFrame, anteriores: pd.DataFrame) -> list[Achado]:
    """Salto de ~1000 vezes contra o documento anterior (mesmo período ou período seguinte).

    `anteriores` são as contas do documento anterior das mesmas empresas (a DFP do ano passado, ou o
    ITR anterior); sem ele, a regra não tem com o que comparar e não diz nada.
    """
    if anteriores.empty:
        return []
    anterior = _da_escala(anteriores, "ultimo")
    chave = ["cnpj", "grupo", "demonstracao", "conta"]
    mesmo_periodo = _da_escala(contas, "penultimo").merge(
        anterior, on=[*chave, "inicio", "fim"], suffixes=("", "_anterior")
    )
    # período seguinte: só o saldo do balanço (a DRE do ITR tem trimestre e acumulado juntos)
    seguinte = _da_escala(contas, "ultimo")
    seguinte = seguinte[seguinte["demonstracao"] == "BPA"].merge(
        anterior, on=chave, suffixes=("", "_anterior")
    )
    achados: dict[tuple, Achado] = {}
    for linha in pd.concat([mesmo_periodo, seguinte]).itertuples(index=False):
        chave_do_achado = (linha.cnpj, linha.grupo, linha.conta)
        if chave_do_achado not in achados and _mil_vezes(
            linha.valor, linha.valor_anterior
        ):
            achados[chave_do_achado] = _achado_r3(linha)
    return list(achados.values())


def _achado_r3(linha: Linha) -> Achado:
    sentido = "maior" if abs(linha.valor) > abs(linha.valor_anterior) else "menor"
    return Achado(
        regra="R3",
        cnpj=linha.cnpj,
        documento=linha.documento,
        referencia=linha.referencia,
        grupo=linha.grupo,
        conta=linha.conta,
        valor=float(linha.valor),
        valor_esperado=float(linha.valor_anterior),
        porque=(
            f"A conta {linha.conta} ({linha.descricao}) está cerca de mil vezes {sentido} que no "
            f"documento anterior ({_reais(linha.valor)} contra {_reais(linha.valor_anterior)}): "
            "sinal de reais e milhares trocados."
        ),
    )


def r4_impossivel(contas: pd.DataFrame) -> list[Achado]:
    """Ativo total, ativo circulante ou caixa negativos."""
    proprias = _do_documento(contas)
    negativas = proprias[
        (proprias["demonstracao"] == "BPA")
        & proprias["conta"].isin(NAO_PODEM_SER_NEGATIVAS)
        & (proprias["valor"] < -TOLERANCIA_EM_REAIS)
    ]
    return [
        Achado(
            regra="R4",
            cnpj=linha.cnpj,
            documento=linha.documento,
            referencia=linha.referencia,
            grupo=linha.grupo,
            conta=linha.conta,
            valor=float(linha.valor),
            valor_esperado=None,
            porque=(
                f"O {NAO_PODEM_SER_NEGATIVAS[linha.conta]} veio negativo ({_reais(linha.valor)}), "
                "o que não existe num balanço."
            ),
        )
        for linha in negativas.itertuples(index=False)
    ]


def r9_repetidas(leitura: LeituraDeContas) -> list[Achado]:
    """Um achado por demonstração com linhas repetidas idênticas no arquivo da CVM."""
    documento = str(leitura.contas["documento"].iloc[0]) if len(leitura.contas) else ""
    return [
        Achado(
            regra="R9",
            cnpj=linha.cnpj,
            documento=documento,
            referencia=linha.referencia,
            grupo=linha.grupo,
            conta="",
            valor=float(linha.linhas),
            valor_esperado=0.0,
            porque=(
                f"O arquivo da CVM trouxe {linha.linhas} linhas repetidas nesta demonstração "
                f"({linha.demonstracao}); o TickerLab contou cada uma só uma vez."
            ),
        )
        for linha in leitura.repetidas.itertuples(index=False)
    ]


def r10_lucro_em_branco(contas: pd.DataFrame) -> list[Achado]:
    """Lucro do período zerado numa empresa com receita no mesmo período.

    A linha do lucro é achada pela descrição (`LINHA_DO_LUCRO`), entre as contas de 1º nível da DRE.
    """
    dre = _do_documento(contas)
    dre = dre[(dre["demonstracao"] == "DRE") & _primeiro_nivel(dre)]
    chave = [*CHAVE, "inicio", "fim"]
    receita = dre[dre["conta"] == RECEITA]
    lucro = dre[dre["descricao"].str.strip().str.match(LINHA_DO_LUCRO)]
    juntos = lucro.merge(
        receita[[*chave, "valor"]], on=chave, suffixes=("", "_receita")
    )
    return [
        Achado(
            regra="R10",
            cnpj=linha.cnpj,
            documento=linha.documento,
            referencia=linha.referencia,
            grupo=linha.grupo,
            conta=linha.conta,
            valor=float(linha.valor),
            valor_esperado=None,
            porque=(
                f"O lucro do período veio em branco, mas a receita foi de "
                f"{_reais(linha.valor_receita)}."
            ),
        )
        for linha in juntos.itertuples(index=False)
        if not _preenchido(linha.valor) and _preenchido(linha.valor_receita)
    ]


def _primeiro_nivel(contas: pd.DataFrame) -> pd.Series:
    return contas["conta"].str.count(r"\.") == 1


def _contas_principais(contas: pd.DataFrame) -> pd.DataFrame:
    """Ativo total, receita, lucro do período e patrimônio líquido (os dois últimos pela descrição)."""
    demonstracao, conta = contas["demonstracao"], contas["conta"]
    descricao = contas["descricao"].str.strip()
    principal = (
        ((demonstracao == "BPA") & (conta == "1"))
        | ((demonstracao == "DRE") & (conta == RECEITA))
        | (
            (demonstracao == "DRE")
            & _primeiro_nivel(contas)
            & descricao.str.match(LINHA_DO_LUCRO)
        )
        | (
            (demonstracao == "BPP")
            & _primeiro_nivel(contas)
            & descricao.str.match(PATRIMONIO_LIQUIDO)
        )
    )
    return contas[principal]


def r6_refeito_no_seguinte(
    contas: pd.DataFrame,
    seguintes: pd.DataFrame,
    recebido_em_seguinte: dict[str, pd.Timestamp],
) -> list[Achado]:
    """Conta principal que a empresa refez no documento seguinte.

    `contas` é o documento com o número original; `seguintes`, o documento do período seguinte das
    mesmas empresas; `recebido_em_seguinte`, a data de entrega dele por CNPJ (o achado só passa a
    existir nessa data).
    """
    original = _contas_principais(contas[contas["ordem"] == "ultimo"])
    refeito = _contas_principais(seguintes[seguintes["ordem"] == "penultimo"])
    chave = ["cnpj", "grupo", "demonstracao", "conta", "inicio", "fim"]
    juntos = original.merge(
        refeito[[*chave, "valor"]], on=chave, suffixes=("", "_refeito")
    )
    return [
        _achado_r6(linha, recebido_em_seguinte.get(linha.cnpj))
        for linha in juntos.itertuples(index=False)
        if _diferente(linha.valor, linha.valor_refeito, TOLERANCIA_R1)
    ]


def _troca_de_sinal(linha: Linha) -> str:
    if not LINHA_DO_LUCRO.match(str(linha.descricao).strip()):
        return ""
    if linha.valor > 0 > linha.valor_refeito:
        return " (de lucro para prejuízo)"
    if linha.valor < 0 < linha.valor_refeito:
        return " (de prejuízo para lucro)"
    return ""


def _achado_r6(linha: Linha, valido_desde: pd.Timestamp | None) -> Achado:
    quando = (
        f", no documento entregue em {valido_desde:%d/%m/%Y}" if valido_desde else ""
    )
    return Achado(
        regra="R6",
        cnpj=linha.cnpj,
        documento=linha.documento,
        referencia=linha.referencia,
        grupo=linha.grupo,
        conta=linha.conta,
        valor=float(linha.valor),
        valor_esperado=float(linha.valor_refeito),
        porque=(
            f"A empresa refez este número no balanço seguinte{quando}: {linha.descricao} era "
            f"{_reais(linha.valor)} e passou a {_reais(linha.valor_refeito)}"
            f"{_troca_de_sinal(linha)}."
        ),
        valido_desde=valido_desde,
    )
