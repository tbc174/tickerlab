"""Catálogo de fatores candidatos: fórmula, referência, dado de que precisa e se a base já tem esse dado.

Inspirado na biblioteca de fatores do Vibe-Trading (plano de 20/10/2026, ideia 1), reescrito do zero.
**Nenhum fator daqui foi medido.** Estar no catálogo não diz que funciona: medir um fator nos dados
(Sharpe, IC, qualquer número) é uma tentativa da pesquisa (`trader/CLAUDE.md`), com critério escrito
antes no próximo pré-registro e contada no registro de tentativas. Por isso todo fator nasce com
`medido=False`, e há teste que impede mudar isso sem o registro.

`direcao` diz o lado que a literatura compra: +1 = comprar os de valor maior, -1 = os de valor menor.
"""

from __future__ import annotations

from dataclasses import dataclass

# dado → módulo que já o serve (a chave é o que cada fator lista em `dados`)
FONTES: dict[str, str] = {
    "precos": "trader/dados.py",
    "mercado": "trader/dados.py",
    "demonstracoes": "base/ponto_no_tempo.py",
    "juros": "trader/juros.py",
    "acoes_em_circulacao": "src/demonstracoes.py",
}

SITUACOES_NA_BASE = ("sim", "parcial", "não")
COMPRA_OS_MAIORES = 1
COMPRA_OS_MENORES = -1


@dataclass(frozen=True)
class Fator:
    """Um fator candidato, com o que é preciso para medi-lo um dia."""

    nome: str
    familia: str
    formula: str
    dados: tuple[str, ...]
    na_base: str  # "sim", "parcial" (falta um dado ponto no tempo) ou "não"
    nota_da_base: str
    funcao: str | None  # caminho "modulo.funcao" de quem calcula; None se ainda não dá
    direcao: int
    referencia: str
    ano: int
    medido: bool = False


_SO_PRECO = "Só preço diário, que `trader/dados.py` serve (e `base_local.ler_serie` recusa se faltar)."
_DA_CVM = (
    "Contas da CVM na base 'como era na data', lidas na véspera (`trader/base_local.py`). "
    "Cobre só empresas com demonstração na CVM."
)
_FALTA_ACOES = (
    "A quantidade de ações só existe em `src/demonstracoes.py` (composição do capital), fora da base "
    "ponto no tempo: falta guardar quando cada número ficou público antes de medir."
)

FATORES: tuple[Fator, ...] = (
    Fator(
        nome="momento 12-1",
        familia="momento",
        formula="P(t-21) / P(t-252) - 1",
        dados=("precos",),
        na_base="sim",
        nota_da_base=_SO_PRECO,
        funcao="trader.fatores.preco.momento_12_1",
        direcao=COMPRA_OS_MAIORES,
        referencia="Jegadeesh e Titman (1993); Carhart (1997)",
        ano=1993,
    ),
    Fator(
        nome="reversão de 1 mês",
        familia="reversão",
        formula="P(t) / P(t-21) - 1",
        dados=("precos",),
        na_base="sim",
        nota_da_base=_SO_PRECO,
        funcao="trader.fatores.preco.retorno_de_1_mes",
        direcao=COMPRA_OS_MENORES,
        referencia="Jegadeesh (1990)",
        ano=1990,
    ),
    Fator(
        nome="baixa volatilidade",
        familia="risco",
        formula="desvio-padrão dos retornos diários de 252 pregões × √252",
        dados=("precos",),
        na_base="sim",
        nota_da_base=_SO_PRECO,
        funcao="trader.fatores.preco.volatilidade_de_12_meses",
        direcao=COMPRA_OS_MENORES,
        referencia="Ang, Hodrick, Xing e Zhang (2006); Blitz e van Vliet (2007)",
        ano=2006,
    ),
    Fator(
        nome="beta baixo (BAB)",
        familia="risco",
        formula="cov(r, m) / var(m) nos últimos 252 pregões",
        dados=("precos", "mercado"),
        na_base="sim",
        nota_da_base="Preço do ativo e de um índice de mercado, ambos por `trader/dados.py`.",
        funcao="trader.fatores.preco.beta_de_mercado",
        direcao=COMPRA_OS_MENORES,
        referencia="Frazzini e Pedersen (2014)",
        ano=2014,
    ),
    Fator(
        nome="perto da máxima de 52 semanas",
        familia="momento",
        formula="P(t) / max(P nos últimos 252 pregões) - 1",
        dados=("precos",),
        na_base="sim",
        nota_da_base=_SO_PRECO,
        funcao="trader.fatores.preco.distancia_da_maxima_de_52_semanas",
        direcao=COMPRA_OS_MAIORES,
        referencia="George e Hwang (2004)",
        ano=2004,
    ),
    Fator(
        nome="tendência (série temporal)",
        familia="momento",
        formula="sinal B1 da M2: média dos retornos de vários horizontes, normalizada",
        dados=("precos",),
        na_base="sim",
        nota_da_base=(
            "Já é a B1 da M2. A normalização acumulada depende de onde o histórico começa "
            "(fila, linha 70)."
        ),
        funcao="trader.baselines.previsao_b1",
        direcao=COMPRA_OS_MAIORES,
        referencia="Moskowitz, Ooi e Pedersen (2012)",
        ano=2012,
    ),
    Fator(
        nome="carry",
        familia="carry",
        formula="diferença anual de juros entre as moedas do par",
        dados=("precos", "juros"),
        na_base="sim",
        nota_da_base="Juros de cada moeda em `trader/juros.py` (só pares de moedas).",
        funcao="trader.juros.carry_anual",
        direcao=COMPRA_OS_MAIORES,
        referencia="Koijen, Moskowitz, Pedersen e Vrugt (2018)",
        ano=2018,
    ),
    Fator(
        nome="rentabilidade bruta",
        familia="qualidade",
        formula="resultado bruto do ano (3.03) / ativo total (1)",
        dados=("demonstracoes",),
        na_base="sim",
        nota_da_base=_DA_CVM,
        funcao="trader.fatores.balanco.rentabilidade_bruta",
        direcao=COMPRA_OS_MAIORES,
        referencia="Novy-Marx (2013)",
        ano=2013,
    ),
    Fator(
        nome="accruals",
        familia="qualidade",
        formula="(lucro do ano (3.11) - caixa operacional do ano (6.01)) / ativo total (1)",
        dados=("demonstracoes",),
        na_base="sim",
        nota_da_base=_DA_CVM,
        funcao="trader.fatores.balanco.accruals",
        direcao=COMPRA_OS_MENORES,
        referencia="Sloan (1996)",
        ano=1996,
    ),
    Fator(
        nome="crescimento do ativo",
        familia="investimento",
        formula="ativo total (1) / ativo total um ano antes - 1",
        dados=("demonstracoes",),
        na_base="sim",
        nota_da_base=_DA_CVM,
        funcao="trader.fatores.balanco.crescimento_do_ativo",
        direcao=COMPRA_OS_MENORES,
        referencia="Cooper, Gulen e Schill (2008)",
        ano=2008,
    ),
    Fator(
        nome="valor (patrimônio sobre preço)",
        familia="valor",
        formula="patrimônio líquido (2.03) / (preço × ações em circulação)",
        dados=("demonstracoes", "precos", "acoes_em_circulacao"),
        na_base="parcial",
        nota_da_base=_FALTA_ACOES,
        funcao=None,
        direcao=COMPRA_OS_MAIORES,
        referencia="Fama e French (1992)",
        ano=1992,
    ),
    Fator(
        nome="tamanho",
        familia="tamanho",
        formula="preço × ações em circulação (valor de mercado)",
        dados=("precos", "acoes_em_circulacao"),
        na_base="parcial",
        nota_da_base=_FALTA_ACOES,
        funcao=None,
        direcao=COMPRA_OS_MENORES,
        referencia="Banz (1981)",
        ano=1981,
    ),
)


def fator(nome: str) -> Fator:
    """O fator do catálogo com esse nome (ValueError se não houver)."""
    for candidato in FATORES:
        if candidato.nome == nome:
            return candidato
    raise ValueError(f"Fator {nome!r} não está no catálogo.")


def catalogo_em_markdown() -> str:
    """Tabela do catálogo para documentação, com o aviso de que nada foi medido."""
    linhas = [
        "| Fator | Família | Fórmula | Na base | Lado | Referência |",
        "|---|---|---|---|---|---|",
    ]
    for f in FATORES:
        lado = "maiores" if f.direcao == COMPRA_OS_MAIORES else "menores"
        linhas.append(
            f"| {f.nome} | {f.familia} | {f.formula} | {f.na_base} | {lado} | {f.referencia} |"
        )
    linhas.append("")
    linhas.append(
        "Nenhum fator foi medido. Medir é tentativa: só com critério escrito antes, no pré-registro."
    )
    return "\n".join(linhas)
