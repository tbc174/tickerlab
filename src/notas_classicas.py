"""Notas clássicas da análise fundamentalista (série 2 da base de ML, PR 3; ADR 0032, item 1).

Três notas conhecidas da literatura, calculadas com as demonstrações anuais (DFP) da CVM e com as
parcelas à vista, para quem lê conferir de onde sai o número:

- **Piotroski F (2000):** 9 critérios de saúde financeira, comparando o ano com o anterior (um
  ponto por critério cumprido). Critério sem dado fica "sem dado", nunca vira zero, e o texto diz
  quantos foram avaliados. Diferença do artigo: o ROA usa o ativo do fim de cada ano.
- **Altman Z'' (2005, empresas não industriais e mercados emergentes):** usa o patrimônio contábil,
  não o preço. Faixas do artigo: acima de 2,60 "segura", de 1,10 a 2,60 "cinzenta", abaixo de 1,10
  "de aflição".
- **Beneish M (1999), 8 índices:** acima de −1,78 o artigo associou a maior chance de manipulação
  dos números; abaixo, não.

Nenhuma nota diz "vai quebrar" ou "manipula": dizem o que o número é e em que faixa do artigo cai.
Bancos e seguradoras: não se aplica.
"""

from dataclasses import dataclass, field

import pandas as pd

from src.banco.demonstracoes import DadosDaEmpresa
from src.demonstracoes import e_financeira
from src.fundamentos import (
    ANO_ANTERIOR,
    CONFERENCIA,
    LUCRO,
    NAO_SE_APLICA_A_FINANCEIRAS,
    anuais,
)
from src.fundamentos import todas_as_entradas as _entradas_das_contas
from src.notas import Regua
from src.rastro import Entrada

VERSAO_DAS_NOTAS_CLASSICAS = "1"  # sobe quando uma fórmula ou um peso abaixo mudar
ALTMAN_SEGURA, ALTMAN_AFLICAO = 2.60, 1.10
BENEISH_LIMITE = -1.78
AFLICAO, CINZENTA, SEGURA = "de aflição", "cinzenta", "segura"
ABAIXO_DO_LIMITE, ACIMA_DO_LIMITE = (
    "abaixo do limite do artigo",
    "acima do limite do artigo",
)
# as faixas do artigo em ordem de valor: o Altman é "segura" só acima de 2,60 e "de aflição" só
# abaixo de 1,10; o Beneish passa do limite só acima de −1,78 (`Regua`, para "o que mudaria")
REGUAS = {
    "altman": Regua(
        (AFLICAO, CINZENTA, SEGURA), (ALTMAN_AFLICAO, ALTMAN_SEGURA), (True, False)
    ),
    "beneish": Regua((ABAIXO_DO_LIMITE, ACIMA_DO_LIMITE), (BENEISH_LIMITE,), (False,)),
}
PIOTROSKI_ALTO, PIOTROSKI_BAIXO = 8, 1  # os grupos das pontas no artigo: 8 e 9; 0 e 1
PESOS_DO_ALTMAN = (6.56, 3.26, 6.72, 1.05)
BENEISH_CONSTANTE = -4.84
PESOS_DO_BENEISH = {
    "DSRI": 0.920,
    "GMI": 0.528,
    "AQI": 0.404,
    "SGI": 0.892,
    "DEPI": 0.115,
    "SGAI": -0.172,
    "TATA": 4.679,
    "LVGI": -0.327,
}


@dataclass(frozen=True)
class Parcela:
    nome: str
    valor: float | None
    passou: bool | None = None  # no Piotroski: cumpriu o critério? None = sem dado


@dataclass(frozen=True)
class NotaClassica:
    chave: str
    nome: str
    valor: float | None
    base: str  # de quando é ("DFP de 2025 contra 2024")
    formula: str
    referencia: str  # o artigo
    parcelas: list[Parcela] = field(default_factory=list)
    faixa: str = ""
    motivo: str = ""  # por que não saiu


def _div(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None or b == 0 else a / b


def _valor(linha: pd.Series, conta: str) -> float | None:
    valor = linha.get(conta)
    return None if valor is None or pd.isna(valor) else float(valor)


def _lucro(ano: pd.Series) -> float | None:
    """Lucro dos controladores; sem a divisão, o consolidado (como a tela Fundamentos)."""
    controladores = _valor(ano, "lucro_controladores")
    return controladores if controladores is not None else _valor(ano, "lucro_liquido")


def _lucros_retidos(ano: pd.Series) -> float | None:
    reservas = _valor(ano, "reservas_de_lucro")
    return (
        None
        if reservas is None
        else reservas + (_valor(ano, "lucros_acumulados") or 0.0)
    )


# --- Altman Z'' ---------------------------------------------------------------------------------
ALTMAN_FORMULA = "Z'' = 6,56·X1 + 3,26·X2 + 6,72·X3 + 1,05·X4"
ALTMAN_REFERENCIA = (
    "Altman (2005), Z'' para empresas não industriais e mercados emergentes"
)


def _altman(ano: pd.Series, base: str) -> NotaClassica:
    ativo, pl = _valor(ano, "ativo_total"), _valor(ano, "patrimonio_liquido")
    giro = (
        None
        if _valor(ano, "ativo_circulante") is None
        or _valor(ano, "passivo_circulante") is None
        else _valor(ano, "ativo_circulante") - _valor(ano, "passivo_circulante")  # type: ignore[operator]
    )
    passivo = None if ativo is None or pl is None else ativo - pl
    parcelas = [
        Parcela("Capital de giro / ativo", _div(giro, ativo)),
        Parcela("Lucros retidos / ativo", _div(_lucros_retidos(ano), ativo)),
        Parcela("EBIT / ativo", _div(_valor(ano, "ebit"), ativo)),
        Parcela("Patrimônio / passivo", _div(pl, passivo)),
    ]
    falta = [p.nome for p in parcelas if p.valor is None]
    if falta:
        return NotaClassica(
            "altman", "Altman Z''", None, base, ALTMAN_FORMULA, ALTMAN_REFERENCIA, parcelas,
            motivo=f"Sem dado para: {', '.join(falta)}.",
        )  # fmt: skip
    z = sum(peso * p.valor for peso, p in zip(PESOS_DO_ALTMAN, parcelas, strict=True))  # type: ignore[operator]
    faixa = SEGURA if z > ALTMAN_SEGURA else AFLICAO if z < ALTMAN_AFLICAO else CINZENTA
    return NotaClassica(
        "altman",
        "Altman Z''",
        z,
        base,
        ALTMAN_FORMULA,
        ALTMAN_REFERENCIA,
        parcelas,
        faixa,
    )


# --- Beneish M ----------------------------------------------------------------------------------
BENEISH_FORMULA = (
    "M = −4,84 + 0,920·DSRI + 0,528·GMI + 0,404·AQI + 0,892·SGI + 0,115·DEPI − 0,172·SGAI "
    "+ 4,679·TATA − 0,327·LVGI"
)
BENEISH_REFERENCIA = (
    "Beneish (1999), The Detection of Earnings Manipulation (8 índices)"
)


def _sga(ano: pd.Series) -> float | None:
    vendas, administrativas = (
        _valor(ano, "despesas_com_vendas"),
        _valor(ano, "despesas_administrativas"),
    )
    if vendas is None and administrativas is None:
        return None
    return abs(vendas or 0.0) + abs(administrativas or 0.0)


def _indices_do_beneish(t: pd.Series, a: pd.Series) -> dict[str, float | None]:
    """Os 8 índices (t = ano, a = ano anterior), com as contas da CVM."""

    def margem_bruta(ano: pd.Series) -> float | None:
        return _div(_valor(ano, "resultado_bruto"), _valor(ano, "receita"))

    def qualidade_do_ativo(ano: pd.Series) -> float | None:
        ativo, circulante, imobilizado = (
            _valor(ano, c) for c in ("ativo_total", "ativo_circulante", "imobilizado")
        )
        soma = (
            None
            if circulante is None or imobilizado is None
            else circulante + imobilizado
        )
        razao = _div(soma, ativo)
        return None if razao is None else 1 - razao

    def depreciacao(ano: pd.Series) -> float | None:
        dep, imobilizado = _valor(ano, "depreciacao"), _valor(ano, "imobilizado")
        return (
            None if dep is None or imobilizado is None else _div(dep, dep + imobilizado)
        )

    def alavancagem(ano: pd.Series) -> float | None:
        circulante, longo = _valor(ano, "passivo_circulante"), _valor(ano, "divida_lp")
        soma = None if circulante is None else circulante + (longo or 0.0)
        return _div(soma, _valor(ano, "ativo_total"))

    def receber(ano: pd.Series) -> float | None:
        return _div(_valor(ano, "contas_a_receber"), _valor(ano, "receita"))

    def despesas(ano: pd.Series) -> float | None:
        return _div(_sga(ano), _valor(ano, "receita"))

    lucro, fco = _valor(t, "lucro_liquido"), _valor(t, "fco")
    return {
        "DSRI": _div(receber(t), receber(a)),
        "GMI": _div(margem_bruta(a), margem_bruta(t)),
        "AQI": _div(qualidade_do_ativo(t), qualidade_do_ativo(a)),
        "SGI": _div(_valor(t, "receita"), _valor(a, "receita")),
        "DEPI": _div(depreciacao(a), depreciacao(t)),
        "SGAI": _div(despesas(t), despesas(a)),
        "TATA": None
        if lucro is None or fco is None
        else _div(lucro - fco, _valor(t, "ativo_total")),
        "LVGI": _div(alavancagem(t), alavancagem(a)),
    }


def _beneish(t: pd.Series, a: pd.Series | None, base: str) -> NotaClassica:
    if a is None:
        return NotaClassica(
            "beneish", "Beneish M", None, base, BENEISH_FORMULA, BENEISH_REFERENCIA,
            motivo="Precisa do ano anterior para comparar.",
        )  # fmt: skip
    indices = _indices_do_beneish(t, a)
    parcelas = [Parcela(nome, valor) for nome, valor in indices.items()]
    falta = [nome for nome, valor in indices.items() if valor is None]
    if falta:
        return NotaClassica(
            "beneish", "Beneish M", None, base, BENEISH_FORMULA, BENEISH_REFERENCIA, parcelas,
            motivo=f"Sem dado para: {', '.join(falta)}.",
        )  # fmt: skip
    m = BENEISH_CONSTANTE + sum(PESOS_DO_BENEISH[n] * v for n, v in indices.items())  # type: ignore[operator]
    faixa = ACIMA_DO_LIMITE if m > BENEISH_LIMITE else ABAIXO_DO_LIMITE
    return NotaClassica(
        "beneish",
        "Beneish M",
        m,
        base,
        BENEISH_FORMULA,
        BENEISH_REFERENCIA,
        parcelas,
        faixa,
    )


# --- Piotroski F --------------------------------------------------------------------------------
PIOTROSKI_FORMULA = "um ponto por critério cumprido, de 0 a 9"
PIOTROSKI_REFERENCIA = "Piotroski (2000), Value Investing: The Use of Historical Financial Statement Information"


def _comparar(
    atual: float | None, anterior: float | None, maior_e_melhor: bool = True
) -> bool | None:
    if atual is None or anterior is None:
        return None
    return atual > anterior if maior_e_melhor else atual < anterior


def _criterios_do_piotroski(t: pd.Series, a: pd.Series) -> list[Parcela]:
    lucro, lucro_a = _lucro(t), _lucro(a)
    roa, roa_a = (
        _div(lucro, _valor(t, "ativo_total")),
        _div(lucro_a, _valor(a, "ativo_total")),
    )
    fco = _valor(t, "fco")
    alav = _div(_valor(t, "divida_lp") or 0.0, _valor(t, "ativo_total"))
    alav_a = _div(_valor(a, "divida_lp") or 0.0, _valor(a, "ativo_total"))
    liquidez = _div(_valor(t, "ativo_circulante"), _valor(t, "passivo_circulante"))
    liquidez_a = _div(_valor(a, "ativo_circulante"), _valor(a, "passivo_circulante"))
    acoes, acoes_a = _valor(t, "acoes_total"), _valor(a, "acoes_total")
    margem = _div(_valor(t, "resultado_bruto"), _valor(t, "receita"))
    margem_a = _div(_valor(a, "resultado_bruto"), _valor(a, "receita"))
    giro = _div(_valor(t, "receita"), _valor(t, "ativo_total"))
    giro_a = _div(_valor(a, "receita"), _valor(a, "ativo_total"))
    sem_divida = alav == 0 and alav_a == 0
    return [
        Parcela("ROA positivo", roa, None if roa is None else roa > 0),
        Parcela("Caixa operacional positivo", fco, None if fco is None else fco > 0),
        Parcela("ROA subiu", roa, _comparar(roa, roa_a)),
        Parcela(
            "Caixa operacional maior que o lucro",
            fco,
            None if fco is None or lucro is None else fco > lucro,
        ),
        Parcela(
            "Alavancagem caiu",
            alav,
            True if sem_divida else _comparar(alav, alav_a, maior_e_melhor=False),
        ),
        Parcela("Liquidez corrente subiu", liquidez, _comparar(liquidez, liquidez_a)),
        Parcela(
            "Não emitiu ações",
            acoes,
            None if acoes is None or acoes_a is None else acoes <= acoes_a,
        ),
        Parcela("Margem bruta subiu", margem, _comparar(margem, margem_a)),
        Parcela("Giro do ativo subiu", giro, _comparar(giro, giro_a)),
    ]


def _piotroski(t: pd.Series, a: pd.Series | None, base: str) -> NotaClassica:
    if a is None:
        return NotaClassica(
            "piotroski", "Piotroski F", None, base, PIOTROSKI_FORMULA, PIOTROSKI_REFERENCIA,
            motivo="Precisa do ano anterior para comparar.",
        )  # fmt: skip
    parcelas = _criterios_do_piotroski(t, a)
    avaliados = [p for p in parcelas if p.passou is not None]
    pontos = sum(1 for p in avaliados if p.passou)
    return NotaClassica(
        "piotroski", "Piotroski F", float(pontos),
        f"{base}; {len(avaliados)} de {len(parcelas)} critérios avaliados",
        PIOTROSKI_FORMULA, PIOTROSKI_REFERENCIA, parcelas,
    )  # fmt: skip


def calcular(dados: DadosDaEmpresa) -> dict[str, NotaClassica]:
    """As três notas pela DFP mais recente (e a anterior, quando a nota compara os dois anos)."""
    contas = dados.contas
    tabela = anuais(contas)
    financeira = e_financeira(
        dados.setor, contas["conta"].unique() if not contas.empty else ()
    )
    if tabela.empty or financeira:
        motivo = (
            NAO_SE_APLICA_A_FINANCEIRAS if financeira else "Sem demonstrações anuais."
        )
        return {
            chave: NotaClassica(
                chave, nome, None, "", formula, referencia, motivo=motivo
            )
            for chave, nome, formula, referencia in (
                ("piotroski", "Piotroski F", PIOTROSKI_FORMULA, PIOTROSKI_REFERENCIA),
                ("altman", "Altman Z''", ALTMAN_FORMULA, ALTMAN_REFERENCIA),
                ("beneish", "Beneish M", BENEISH_FORMULA, BENEISH_REFERENCIA),
            )
        }
    ano = int(tabela.index.max())
    atual = tabela.loc[ano]
    anterior = tabela.loc[ano - 1] if ano - 1 in tabela.index else None
    base = f"DFP de {ano} contra {ano - 1}" if anterior is not None else f"DFP de {ano}"
    return {
        "piotroski": _piotroski(atual, anterior, base),
        "altman": _altman(atual, f"DFP de {ano}"),
        "beneish": _beneish(atual, anterior, base),
    }


# --- as entradas do rastro -----------------------------------------------------------------------
_DO_BENEISH = (
    "receita",
    "resultado_bruto",
    "ativo_total",
    "ativo_circulante",
    "imobilizado",
    "depreciacao",
    "passivo_circulante",
    "divida_lp",
    "contas_a_receber",
    "despesas_com_vendas",
    "despesas_administrativas",
)
_DO_PIOTROSKI = (
    LUCRO,
    "ativo_total",
    "divida_lp",
    "ativo_circulante",
    "passivo_circulante",
    "acoes_total",
    "resultado_bruto",
    "receita",
)


def _nos_dois_anos(*contas: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (onde, conta) for onde in (ANO_ANTERIOR, CONFERENCIA) for conta in contas
    )


# As contas de cada nota (as que `_altman`, `_indices_do_beneish` e `_criterios_do_piotroski` leem):
# a conferência é o último exercício; o ano anterior, o de antes. O caixa operacional (no Piotroski
# e no TATA do Beneish) e o lucro do TATA são só do último ano. Mudou uma conta acima, mude aqui (o
# teste de `tests/test_rastro.py` refaz cada nota só com as entradas).
CONTAS_DAS_NOTAS: dict[str, tuple[tuple[str, str], ...]] = {
    "piotroski": (*_nos_dois_anos(*_DO_PIOTROSKI), (CONFERENCIA, "fco")),
    "altman": tuple(
        (CONFERENCIA, conta)
        for conta in (
            "ativo_total",
            "patrimonio_liquido",
            "ativo_circulante",
            "passivo_circulante",
            "reservas_de_lucro",
            "lucros_acumulados",
            "ebit",
        )
    ),
    "beneish": (
        *_nos_dois_anos(*_DO_BENEISH),
        (CONFERENCIA, "lucro_liquido"),
        (CONFERENCIA, "fco"),
    ),
}


def todas_as_entradas(dados: DadosDaEmpresa) -> dict[str, tuple[Entrada, ...]]:
    """As entradas de cada nota de `CONTAS_DAS_NOTAS` (ver `fundamentos.todas_as_entradas`)."""
    return _entradas_das_contas(dados, contas_dos_indicadores=CONTAS_DAS_NOTAS)
