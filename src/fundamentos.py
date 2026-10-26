"""Indicadores fundamentalistas a partir das demonstrações da CVM (Research, etapa 3b).

Tudo sai das contas guardadas por `src/demonstracoes.py` e das fórmulas abaixo, escritas aqui para
qualquer um conferir. Regras (PRD v2, seções 4.3 e 5):

- **Últimos 12 meses:** anual do último DFP + acumulado do ano no último ITR − acumulado do mesmo
  período do ano anterior (que o próprio ITR traz). Sem ITR mais novo que o DFP, vale o ano do DFP.
- **Balanço:** o saldo mais recente (do ITR, se for mais novo que o DFP).
- **"Não se aplica" com motivo**, nunca zero: bancos e seguradoras (outro plano de contas, sem
  margem bruta, EBIT nem dívida comparáveis), prejuízo (P/L sem sentido), patrimônio negativo,
  base negativa no crescimento, falta de preço ou de quantidade de ações.
- **Hipóteses explícitas:** ROIC com alíquota de 34% de IR/CS; P/L e P/VP usam o preço do ticker
  escolhido para **todas** as classes de ação (aproximação quando ON e PN valem diferente).
- **Quantidade de ações conferida:** algumas companhias a informam em milhares (o arquivo da CVM
  não diz). Ela é comparada com lucro ÷ lucro por ação declarado na DRE: perto de 1, vale; perto
  de 1.000, é multiplicada por mil; fora disso, os indicadores por ação ficam indisponíveis.

Os filtros (ROIC mínimo, P/L máximo) vêm da página Parâmetros e são **educacionais**: dizem se o
número passa do limite que a pessoa escolheu, não se a ação é boa ou ruim.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from src.banco.demonstracoes import DadosDaEmpresa
from src.demonstracoes import (
    ACUMULADO,
    ACUMULADO_ANTERIOR,
    CONTAS_DA_CVM,
    EXERCICIO,
    POSICAO,
    e_financeira,
)
from src.rastro import Entrada

VERSAO_DOS_FUNDAMENTOS = "3"  # sobe quando uma fórmula abaixo mudar
ALIQUOTA_DE_IR_CS = 0.34  # hipótese do ROIC (alíquota nominal de IR + CSLL no Brasil)
ALIQUOTA_DOS_EUA = (
    0.21  # imposto federal sobre o lucro das empresas nos EUA (sem os estaduais)
)
FAIXA_DE_ACOES_CONFERIDAS = (
    0.8,
    1.25,
)  # razão aceitável entre ações implícitas e informadas
MIL = 1_000
DIAS_DE_UM_ANO = 371  # 53 semanas: o maior exercício possível
NAO_SE_APLICA_A_FINANCEIRAS = (
    "Não se aplica a bancos e seguradoras: o balanço deles é organizado de outro jeito "
    "(não há margem bruta, EBIT nem dívida comparáveis)."
)
REAIS, FRACAO, VEZES, REAIS_POR_ACAO = "reais", "fração", "vezes", "reais por ação"
SEM_RECEITA = "Sem receita positiva no período."
SEM_DIVIDENDOS_NO_CAIXA = (
    "O fluxo de caixa não traz linha de dividendos ou JCP pagos: não dá para saber se a "
    "empresa não pagou ou se a linha tem outro nome."
)
# os de mercado que não servem a bancos (sem dívida nem receita comparáveis às das outras)
DA_FIRMA = (
    ("valor_da_firma", "Valor da firma (valor de mercado + dívida líquida)", REAIS),
    ("ev_ebitda", "Valor da firma / EBITDA (12 meses)", VEZES),
    ("ev_ebit", "Valor da firma / EBIT (12 meses)", VEZES),
    ("p_receita", "Preço / receita (12 meses)", VEZES),
    ("p_ebitda", "Preço / EBITDA (12 meses)", VEZES),
    ("p_ebit", "Preço / EBIT (12 meses)", VEZES),
    ("p_fcf", "Preço / caixa livre (12 meses)", VEZES),
)
# os que pedem o preço do ativo, além de P/L e P/VP (D3 mudada em 20/10/2026)
DE_MERCADO = (
    "valor_de_mercado",
    "dividend_yield",
    "dividend_yield_medio",
    "p_ativo",
    *(chave for chave, _, _ in DA_FIRMA),
)
ANOS_DO_CRESCIMENTO = 5  # o horizonte padrão do crescimento composto
# a conta de cada indicador abaixo, para o rastro do número (`src/rastro.py`): mudou uma conta aqui,
# suba `VERSAO_DOS_FUNDAMENTOS` (o gabarito de `tests/test_rastro.py` cobra)
_12M = "(12 meses: último DFP + acumulado do ano no último ITR − o mesmo período do ano anterior)"
_LUCRO = "lucro dos controladores (sem a divisão, o lucro consolidado)"
_PL = "(patrimônio líquido − participação dos minoritários)"
_ACOES = (
    "ações em circulação (total − tesouraria, conferidas com o lucro por ação da DRE)"
)
FORMULAS = {
    "receita": f"receita líquida {_12M}",
    "lucro": f"{_LUCRO} {_12M}",
    "margem_bruta": "resultado bruto ÷ receita (12 meses)",
    "margem_ebit": "EBIT ÷ receita (12 meses)",
    "margem_liquida": "lucro líquido consolidado ÷ receita (12 meses)",
    "roe": f"{_LUCRO} (12 meses) ÷ {_PL} no balanço mais recente",
    "roic": (
        "EBIT (12 meses) × (1 − alíquota de IR e CSLL: 34% no Brasil, 21% nos EUA) ÷ (patrimônio "
        "líquido + dívida bruta − caixa e aplicações) no balanço mais recente"
    ),
    "divida_bruta": "empréstimos e financiamentos de curto prazo + de longo prazo (balanço mais recente)",
    "caixa": "caixa e equivalentes + aplicações financeiras (balanço mais recente)",
    "divida_liquida": "dívida bruta − caixa e aplicações (balanço mais recente)",
    "divida_sobre_pl": f"dívida líquida ÷ {_PL}",
    "conversao_de_caixa": "caixa operacional (12 meses) ÷ lucro líquido consolidado (12 meses)",
    "crescimento_receita": (
        f"(receita do último DFP ÷ receita do DFP de {ANOS_DO_CRESCIMENTO} anos antes) ^ "
        f"(1 ÷ {ANOS_DO_CRESCIMENTO}) − 1"
    ),
    "crescimento_lucro": (
        f"({_LUCRO} do último DFP ÷ o do DFP de {ANOS_DO_CRESCIMENTO} anos antes) ^ "
        f"(1 ÷ {ANOS_DO_CRESCIMENTO}) − 1"
    ),
    "lpa": f"{_LUCRO} (12 meses) ÷ {_ACOES}",
    "vpa": f"{_PL} ÷ {_ACOES}",
    "p_l": "preço da ação ÷ lucro por ação (o mesmo preço para todas as classes de ação)",
    "p_vp": "preço da ação ÷ patrimônio por ação (o mesmo preço para todas as classes de ação)",
    "valor_de_mercado": f"preço da ação × {_ACOES}",
    "dividend_yield": (
        "dividendos e JCP pagos em caixa (12 meses, fluxo de caixa) ÷ valor de mercado"
    ),
    "valor_da_firma": "valor de mercado + dívida líquida",
    "ev_ebitda": "valor da firma ÷ (EBIT + depreciação e amortização) (12 meses)",
    "ev_ebit": "valor da firma ÷ EBIT (12 meses)",
    "p_receita": "valor de mercado ÷ receita (12 meses)",
    "p_ebitda": "valor de mercado ÷ (EBIT + depreciação e amortização) (12 meses)",
    "p_ebit": "valor de mercado ÷ EBIT (12 meses)",
    "p_fcf": "valor de mercado ÷ (caixa operacional − capex) (12 meses, fluxo de caixa)",
    "p_ativo": "valor de mercado ÷ ativo total (balanço mais recente)",
    "dividend_yield_medio": (
        f"média dos dividendos e JCP pagos em caixa nos {ANOS_DO_CRESCIMENTO} últimos exercícios "
        "(DFP, fluxo de caixa) ÷ valor de mercado de hoje"
    ),
}

# As contas que entram em cada indicador, e de onde: os 12 meses, o balanço mais recente, a conferência
# da quantidade de ações (o último exercício da DFP), o primeiro e o último ano do crescimento ou os
# exercícios da média; no `fundamentalista`, também o balanço de um ano antes (o saldo médio), todos os
# exercícios (a diluição) e o último com o de N anos antes (o crescimento do dividendo); nas
# `notas_classicas`, o último exercício e o anterior. É o que `entradas` cita no rastro; mudou uma
# conta acima, mude aqui (o teste de `tests/test_rastro.py` refaz cada número só com as entradas).
DOZE_MESES, BALANCO, CONFERENCIA, CRESCIMENTO, MEDIA_DOS_ANOS, UM_ANO_ANTES = (
    "doze_meses", "balanco", "conferencia", "crescimento", "media_dos_anos", "um_ano_antes",
)  # fmt: skip
TODOS_OS_ANOS, COMECO_E_FIM, ANO_ANTERIOR = (
    "todos_os_anos",
    "comeco_e_fim",
    "ano_anterior",
)
LUCRO = "lucro"  # o dos controladores; sem a divisão, o consolidado (como em `_lucro`)


def _em(onde: str, *contas: str) -> tuple[tuple[str, str], ...]:
    return tuple((onde, conta) for conta in contas)


_DIVIDA_E_CAIXA = ("divida_cp", "divida_lp", "caixa", "aplicacoes")
_PL_SEM_MINORITARIOS = ("patrimonio_liquido", "minoritarios")
DAS_ACOES = _em(BALANCO, "acoes_total", "acoes_tesouraria") + _em(
    CONFERENCIA, LUCRO, "lpa_basico", "acoes_total"
)
_DA_FIRMA = _em(BALANCO, *_DIVIDA_E_CAIXA) + DAS_ACOES
_EBITDA = _em(DOZE_MESES, "ebit", "depreciacao")
CONTAS_DOS_INDICADORES: dict[str, tuple[tuple[str, str], ...]] = {
    "receita": _em(DOZE_MESES, "receita"),
    "lucro": _em(DOZE_MESES, LUCRO),
    "margem_bruta": _em(DOZE_MESES, "resultado_bruto", "receita"),
    "margem_ebit": _em(DOZE_MESES, "ebit", "receita"),
    "margem_liquida": _em(DOZE_MESES, "lucro_liquido", "receita"),
    "roe": _em(DOZE_MESES, LUCRO) + _em(BALANCO, *_PL_SEM_MINORITARIOS),
    "roic": _em(DOZE_MESES, "ebit")
    + _em(BALANCO, "patrimonio_liquido", *_DIVIDA_E_CAIXA),
    "divida_bruta": _em(BALANCO, "divida_cp", "divida_lp"),
    "caixa": _em(BALANCO, "caixa", "aplicacoes"),
    "divida_liquida": _em(BALANCO, *_DIVIDA_E_CAIXA),
    "divida_sobre_pl": _em(BALANCO, *_DIVIDA_E_CAIXA, *_PL_SEM_MINORITARIOS),
    "conversao_de_caixa": _em(DOZE_MESES, "fco", "lucro_liquido"),
    "crescimento_receita": _em(CRESCIMENTO, "receita"),
    "crescimento_lucro": _em(CRESCIMENTO, LUCRO),
    "lpa": _em(DOZE_MESES, LUCRO) + DAS_ACOES,
    "vpa": _em(BALANCO, *_PL_SEM_MINORITARIOS) + DAS_ACOES,
    "p_l": _em(DOZE_MESES, LUCRO) + DAS_ACOES,
    "p_vp": _em(BALANCO, *_PL_SEM_MINORITARIOS) + DAS_ACOES,
    "valor_de_mercado": DAS_ACOES,
    "dividend_yield": _em(DOZE_MESES, "dividendos_pagos") + DAS_ACOES,
    "valor_da_firma": _DA_FIRMA,
    "ev_ebitda": _EBITDA + _DA_FIRMA,
    "ev_ebit": _em(DOZE_MESES, "ebit") + _DA_FIRMA,
    "p_receita": _em(DOZE_MESES, "receita") + DAS_ACOES,
    "p_ebitda": _EBITDA + DAS_ACOES,
    "p_ebit": _em(DOZE_MESES, "ebit") + DAS_ACOES,
    "p_fcf": _em(DOZE_MESES, "fco", "capex") + DAS_ACOES,
    "p_ativo": _em(BALANCO, "ativo_total") + DAS_ACOES,
    "dividend_yield_medio": _em(MEDIA_DOS_ANOS, "dividendos_pagos") + DAS_ACOES,
}


@dataclass(frozen=True)
class Indicador:
    chave: str
    nome: str
    valor: float | None
    unidade: str
    base: (
        str  # de quando é o número ("12 meses até 30/06/2026", "balanço de 30/06/2026")
    )
    motivo: str = ""  # por que está indisponível

    @property
    def disponivel(self) -> bool:
        return self.valor is not None


@dataclass(frozen=True)
class Fundamentos:
    empresa: str
    setor: str
    financeira: bool
    indicadores: dict[str, Indicador]
    anual: (
        pd.DataFrame
    )  # um ano por linha: receita, lucro, margem líquida, patrimônio, dívida
    documentos: pd.DataFrame  # documento, referencia, recebido_em, link (os usados)
    notas: list[str] = field(
        default_factory=list
    )  # avisos sobre os dados (ex.: ações em milhares)
    filtros: list[str] = field(default_factory=list)
    versao: str = VERSAO_DOS_FUNDAMENTOS

    def __getitem__(self, chave: str) -> Indicador:
        return self.indicadores[chave]


def _data(d: date) -> str:
    return f"{d:%d/%m/%Y}"


def um_ano_antes(d: date) -> date:
    """O mesmo dia um ano antes (29/02 vira 28/02)."""
    return d.replace(year=d.year - 1, day=28 if (d.month, d.day) == (2, 29) else d.day)


def _contas_em(
    contas: pd.DataFrame, documento: str | None, referencia: date, periodo: str
) -> dict:
    filtro = (contas["referencia"] == referencia) & (contas["periodo"] == periodo)
    if documento:
        filtro &= contas["documento"] == documento
    return dict(
        zip(contas.loc[filtro, "conta"], contas.loc[filtro, "valor"], strict=True)
    )


def _lucro(valores: dict) -> float | None:
    """Lucro dos controladores (o que é do acionista da empresa); sem a divisão, o consolidado."""
    return valores.get("lucro_controladores", valores.get("lucro_liquido"))


def _positivo(valor: float | None) -> bool:
    return valor is not None and valor > 0


# --- de onde vêm os números -----------------------------------------------------------------
def anuais(contas: pd.DataFrame) -> pd.DataFrame:
    """As contas de cada exercício (DFP, fluxos e saldos), um ano por linha, do mais antigo."""
    dfp = contas[contas["documento"] == "DFP"]
    exercicios = dfp[dfp["periodo"].isin([EXERCICIO, POSICAO])]
    if exercicios.empty or not (exercicios["periodo"] == EXERCICIO).any():
        return pd.DataFrame()
    tabela = exercicios.pivot_table(
        index="referencia", columns="conta", values="valor", aggfunc="first"
    ).sort_index()
    tabela.index = pd.Index([d.year for d in tabela.index], name="ano")
    return tabela[~tabela.index.duplicated(keep="last")]


Parte = tuple[
    str, date, str
]  # (documento, referência, período): um pedaço da tabela de contas


def janela_dos_doze_meses(contas: pd.DataFrame) -> tuple[tuple[Parte, ...], str]:
    """(as partes que fazem os últimos 12 meses, descrição da base): a DFP sozinha, ou a DFP mais
    o acumulado do ITR menos o acumulado do mesmo período do ano anterior."""
    dfp = contas[(contas["documento"] == "DFP") & (contas["periodo"] == EXERCICIO)]
    if dfp.empty:
        return (), ""
    ultimo_dfp = max(dfp["referencia"])
    so_o_dfp = (
        (("DFP", ultimo_dfp, EXERCICIO),),
        f"exercício encerrado em {_data(ultimo_dfp)}",
    )
    itr = contas[(contas["documento"] == "ITR") & (contas["periodo"] == ACUMULADO)]
    mais_novo = max(itr["referencia"]) if not itr.empty else None
    if mais_novo is None or mais_novo <= ultimo_dfp:
        return so_o_dfp
    # o último anual antes do trimestre, a no máximo um ano dele: funciona com ano fiscal fora
    # do calendário (Apple termina em setembro; Walmart, em janeiro)
    base = [
        r
        for r in dfp["referencia"].unique()
        if r < mais_novo and (mais_novo - r).days <= DIAS_DE_UM_ANO
    ]
    if not base:
        return so_o_dfp
    partes = (
        ("DFP", max(base), EXERCICIO),
        ("ITR", mais_novo, ACUMULADO),
        ("ITR", mais_novo, ACUMULADO_ANTERIOR),
    )
    return partes, f"12 meses até {_data(mais_novo)}"


def doze_meses(contas: pd.DataFrame) -> tuple[dict, str, list[tuple[str, date]]]:
    """(contas dos últimos 12 meses, descrição da base, documentos usados)."""
    partes, base = janela_dos_doze_meses(contas)
    usados = list(
        dict.fromkeys((documento, referencia) for documento, referencia, _ in partes)
    )
    valores = [_contas_em(contas, *parte) for parte in partes]
    if len(valores) <= 1:
        return (valores[0] if valores else {}), base, usados
    anual, acumulado, anterior = valores
    ttm = {
        conta: anual[conta] + acumulado[conta] - anterior[conta]
        for conta in anual
        if conta in acumulado and conta in anterior and conta != "lpa_basico"
    }
    return ttm, base, usados


def balanco_mais_recente(contas: pd.DataFrame) -> tuple[dict, date | None, str]:
    """(saldos, data, documento) do balanço mais recente (o ITR vence o DFP na mesma data)."""
    saldos = contas[contas["periodo"] == POSICAO]
    if saldos.empty:
        return {}, None, ""
    referencia = max(saldos["referencia"])
    documentos = set(saldos.loc[saldos["referencia"] == referencia, "documento"])
    documento = "ITR" if "ITR" in documentos else "DFP"
    return _contas_em(contas, documento, referencia, POSICAO), referencia, documento


def acoes_em_circulacao(
    saldo: dict, contas: pd.DataFrame
) -> tuple[float | None, str, str]:
    """(ações, nota, motivo de indisponibilidade), conferindo com o lucro por ação declarado."""
    if "acoes_total" not in saldo:
        return None, "", "Sem a quantidade de ações no documento."
    acoes = saldo["acoes_total"] - saldo.get("acoes_tesouraria", 0.0)
    if acoes <= 0:  # visto em documentos reais: dividir por zero derrubava a página
        return None, "", "Quantidade de ações zerada ou negativa no documento."
    tabela = anuais(contas)
    if tabela.empty or "lpa_basico" not in tabela or "acoes_total" not in tabela:
        return (
            acoes,
            "Quantidade de ações não conferida (sem lucro por ação declarado).",
            "",
        )
    ano = tabela.iloc[-1]
    lucro, lpa, informadas = (
        _lucro(ano.dropna().to_dict()),
        ano.get("lpa_basico"),
        ano.get("acoes_total"),
    )
    if not (_positivo(lucro) and _positivo(lpa) and _positivo(informadas)):
        return (
            acoes,
            "Quantidade de ações não conferida (sem lucro por ação declarado).",
            "",
        )
    razao = (lucro / lpa) / informadas
    minimo, maximo = FAIXA_DE_ACOES_CONFERIDAS
    if minimo <= razao <= maximo:
        return acoes, "", ""
    if minimo * MIL <= razao <= maximo * MIL:
        nota = (
            "A quantidade de ações veio em milhares na CVM; corrigida pelo lucro por ação "
            "declarado na DRE."
        )
        return acoes * MIL, nota, ""
    return (
        None,
        "",
        "A quantidade de ações informada não bate com o lucro por ação declarado.",
    )


def divida_e_caixa(saldo: dict) -> tuple[float | None, float | None]:
    """(dívida bruta, caixa e aplicações) de um balanço; sem nenhuma das contas, `None`."""
    divida = (
        saldo.get("divida_cp", 0.0) + saldo.get("divida_lp", 0.0)
        if "divida_cp" in saldo or "divida_lp" in saldo
        else None
    )
    caixa = (
        saldo.get("caixa", 0.0) + saldo.get("aplicacoes", 0.0)
        if "caixa" in saldo or "aplicacoes" in saldo
        else None
    )
    return divida, caixa


# --- as entradas do rastro -----------------------------------------------------------------------
_Linha = tuple[str, date, str, str]  # (documento, referência, período, conta)


@dataclass(frozen=True)
class _Lugares:
    """Onde cada indicador lê as contas: as mesmas escolhas de `calcular`."""

    guardadas: dict[
        _Linha, tuple[float, int]
    ]  # a linha da tabela de contas → (valor, versão)
    doze_meses: tuple[Parte, ...]
    balanco: Parte | None
    tabela: pd.DataFrame  # a de `anuais`
    referencia_do_ano: dict[int, date]  # a data da DFP de cada linha de `tabela`
    # (dia, conta) → a linha do saldo naquele dia; com dois documentos no mesmo dia, o último da
    # tabela, como no `_saldos_em` do `fundamentalista`
    saldos: dict[tuple[date, str], _Linha]


def _lugares(contas: pd.DataFrame) -> _Lugares:
    colunas = ("documento", "referencia", "periodo", "conta", "valor", "versao")
    guardadas, saldos = {}, {}
    for documento, referencia, periodo, conta, valor, versao in zip(
        *(contas[c] for c in colunas), strict=True
    ):
        guardadas[(documento, referencia, periodo, conta)] = (float(valor), int(versao))
        if periodo == POSICAO:
            saldos[(referencia, conta)] = (documento, referencia, periodo, conta)
    _, referencia, documento = balanco_mais_recente(contas)
    dfp = contas[
        (contas["documento"] == "DFP") & contas["periodo"].isin([EXERCICIO, POSICAO])
    ]
    return _Lugares(
        guardadas,
        janela_dos_doze_meses(contas)[0],
        (documento, referencia, POSICAO) if referencia else None,
        anuais(contas),
        {
            r.year: r for r in sorted(dfp["referencia"].unique())
        },  # como `anuais`: a última do ano
        saldos,
    )


def _nos_doze_meses(lugares: _Lugares, conta: str, anos: int) -> list[_Linha]:
    """A conta em cada parte dos 12 meses; se falta numa delas, a soma não a tem (nem o número)."""
    partes = lugares.doze_meses

    def em_todas(nome: str) -> bool:
        return bool(partes) and all((*p, nome) in lugares.guardadas for p in partes)

    if conta == LUCRO:
        conta = (
            "lucro_controladores"
            if em_todas("lucro_controladores")
            else "lucro_liquido"
        )
    return [(*p, conta) for p in partes] if em_todas(conta) else []


def _no_balanco(lugares: _Lugares, conta: str, anos: int) -> list[_Linha]:
    linha = None if lugares.balanco is None else (*lugares.balanco, conta)
    return [linha] if linha in lugares.guardadas else []


def _no_ano_antes(lugares: _Lugares, conta: str, anos: int) -> list[_Linha]:
    """O saldo de um ano antes do balanço mais recente, que o saldo médio usa quando existe."""
    if lugares.balanco is None or not _no_balanco(lugares, conta, anos):
        return []
    linha = lugares.saldos.get((um_ano_antes(lugares.balanco[1]), conta))
    return [] if linha is None else [linha]


def _da_dfp(lugares: _Lugares, ano: int, conta: str) -> list[_Linha]:
    referencia = lugares.referencia_do_ano[int(ano)]
    linhas = [("DFP", referencia, periodo, conta) for periodo in (EXERCICIO, POSICAO)]
    return [linha for linha in linhas if linha in lugares.guardadas][:1]


def _no_exercicio(lugares: _Lugares, ano: int, conta: str) -> list[_Linha]:
    """A conta no exercício `ano`; o lucro, o dos controladores se aquele ano o tem (`_lucro`)."""
    if conta == LUCRO:
        tem = pd.notna(lugares.tabela.loc[ano].get("lucro_controladores"))
        conta = "lucro_controladores" if tem else "lucro_liquido"
    return _da_dfp(lugares, ano, conta)


def _na_conferencia(lugares: _Lugares, conta: str, anos: int) -> list[_Linha]:
    """O lucro, o lucro por ação e as ações do último exercício (`acoes_em_circulacao`); é também o
    ano que as notas clássicas leem."""
    if lugares.tabela.empty:
        return []
    return _no_exercicio(lugares, lugares.tabela.index[-1], conta)


def _no_ano_anterior(lugares: _Lugares, conta: str, anos: int) -> list[_Linha]:
    """O exercício antes do último, com que as notas clássicas comparam; sem ele, nenhuma linha."""
    indice = lugares.tabela.index
    if indice.empty or (indice.max() - 1) not in indice:
        return []
    return _no_exercicio(lugares, indice.max() - 1, conta)


def _no_crescimento(lugares: _Lugares, conta: str, anos: int) -> list[_Linha]:
    """O primeiro e o último ano do crescimento composto (`_cagr`)."""
    tabela = lugares.tabela
    if conta == LUCRO:
        conta = (
            "lucro_controladores"
            if "lucro_controladores" in tabela
            else "lucro_liquido"
        )
    serie = tabela[conta].dropna() if conta in tabela else pd.Series(dtype=float)
    if len(serie) < anos + 1:
        return []
    return [
        *_da_dfp(lugares, serie.index[-(anos + 1)], conta),
        *_da_dfp(lugares, serie.index[-1], conta),
    ]


def _na_media(lugares: _Lugares, conta: str, anos: int) -> list[_Linha]:
    """Os exercícios da média (`_pagos_em_media`); com um ano sem a conta, não há média."""
    tabela = lugares.tabela
    if (
        conta not in tabela
        or len(tabela) < anos
        or tabela[conta].iloc[-anos:].isna().any()
    ):
        return []
    return [
        linha for ano in tabela.index[-anos:] for linha in _da_dfp(lugares, ano, conta)
    ]


def _em_todos_os_anos(lugares: _Lugares, conta: str, anos: int) -> list[_Linha]:
    """A conta em cada exercício da DFP: a diluição e os fatores das ações leem a série inteira."""
    return [
        linha for ano in lugares.tabela.index for linha in _da_dfp(lugares, ano, conta)
    ]


def _no_comeco_e_no_fim(lugares: _Lugares, conta: str, anos: int) -> list[_Linha]:
    """O último exercício e o de `anos` antes, sem tirar os vazios (`_crescimento_do_dividendo`)."""
    indice = lugares.tabela.index
    if indice.empty or (indice.max() - anos) not in indice:
        return []
    ultimo = indice.max()
    return [
        *_da_dfp(lugares, ultimo - anos, conta),
        *_da_dfp(lugares, ultimo, conta),
    ]


_ONDE = {
    DOZE_MESES: _nos_doze_meses,
    BALANCO: _no_balanco,
    CONFERENCIA: _na_conferencia,
    CRESCIMENTO: _no_crescimento,
    MEDIA_DOS_ANOS: _na_media,
    UM_ANO_ANTES: _no_ano_antes,
    TODOS_OS_ANOS: _em_todos_os_anos,
    COMECO_E_FIM: _no_comeco_e_no_fim,
    ANO_ANTERIOR: _no_ano_anterior,
}


def _publicados_em(
    documentos: pd.DataFrame,
) -> dict[tuple[str, date, int], date | None]:
    """(documento, referência, versão) → o dia em que a CVM recebeu o documento."""
    if documentos.empty:
        return {}
    colunas = ("documento", "referencia", "versao", "recebido_em")
    return {
        (documento, referencia, int(versao)): None
        if pd.isna(dia)
        else pd.Timestamp(dia).date()
        for documento, referencia, versao, dia in zip(
            *(documentos[c] for c in colunas), strict=True
        )
    }


def _entrada(linha: _Linha, guardada: tuple[float, int], publicados: dict) -> Entrada:
    documento, referencia, periodo, conta = linha
    (codigo, nome), (valor, versao) = CONTAS_DA_CVM[conta], guardada
    publicado_em = publicados.get((documento, referencia, versao))
    return Entrada(
        conta, codigo, nome, valor, periodo, documento, referencia, versao, publicado_em
    )


def todas_as_entradas(
    dados: DadosDaEmpresa,
    anos: int = ANOS_DO_CRESCIMENTO,
    contas_dos_indicadores: dict[
        str, tuple[tuple[str, str], ...]
    ] = CONTAS_DOS_INDICADORES,
) -> dict[str, tuple[Entrada, ...]]:
    """As entradas de cada indicador de `FORMULAS` (ou de outro módulo, pelas contas dele): as contas
    guardadas que entram nele, com o valor, o código e o nome na CVM e o documento de onde vieram.
    Só com elas, `calcular` refaz o número; a conta que o documento não traz fica de fora (e o
    número sai indisponível)."""
    if dados.contas.empty:
        return {chave: () for chave in contas_dos_indicadores}
    lugares, publicados = _lugares(dados.contas), _publicados_em(dados.documentos)
    saida = {}
    for chave, contas in contas_dos_indicadores.items():
        linhas = [
            linha
            for onde, conta in contas
            for linha in _ONDE[onde](lugares, conta, anos)
        ]
        saida[chave] = tuple(
            _entrada(linha, lugares.guardadas[linha], publicados)
            for linha in dict.fromkeys(linhas)
        )
    return saida


def entradas(
    chave: str, dados: DadosDaEmpresa, anos: int = ANOS_DO_CRESCIMENTO
) -> tuple[Entrada, ...]:
    """As entradas de um indicador (ver `todas_as_entradas`)."""
    return todas_as_entradas(dados, anos)[chave]


# --- indicadores ---------------------------------------------------------------------------------
class _Lista:
    """Junta os indicadores, transformando ausência de dado em "indisponível com motivo"."""

    def __init__(self) -> None:
        self.itens: dict[str, Indicador] = {}

    def add(
        self,
        chave: str,
        nome: str,
        valor: float | None,
        unidade: str,
        base: str,
        motivo: str = "",
    ) -> None:
        if motivo:
            valor = None
        elif valor is not None and (pd.isna(valor) or abs(valor) == float("inf")):
            valor, motivo = None, "Não há dados suficientes para calcular."
        elif valor is None:
            motivo = "A conta não aparece nas demonstrações guardadas."
        self.itens[chave] = Indicador(chave, nome, valor, unidade, base, motivo)


def _resultado(lista: _Lista, ttm: dict, base: str, financeira: bool) -> None:
    receita, lucro_total = ttm.get("receita"), ttm.get("lucro_liquido")
    lista.add("receita", "Receita (12 meses)", receita, REAIS, base)
    lista.add("lucro", "Lucro dos acionistas (12 meses)", _lucro(ttm), REAIS, base)
    sem_receita = "" if _positivo(receita) else SEM_RECEITA
    for chave, nome, conta in (
        ("margem_bruta", "Margem bruta", "resultado_bruto"),
        ("margem_ebit", "Margem EBIT", "ebit"),
    ):
        motivo = NAO_SE_APLICA_A_FINANCEIRAS if financeira else sem_receita
        valor = ttm.get(conta)
        lista.add(
            chave,
            nome,
            None if valor is None or motivo else valor / receita,
            FRACAO,
            base,
            motivo,
        )
    lista.add(
        "margem_liquida", "Margem líquida (lucro consolidado)",
        None if lucro_total is None or sem_receita else lucro_total / receita, FRACAO, base, sem_receita,
    )  # fmt: skip


def _retornos_e_divida(
    lista: _Lista,
    ttm: dict,
    saldo: dict,
    base_12m: str,
    base_balanco: str,
    financeira: bool,
    aliquota: float = ALIQUOTA_DE_IR_CS,
) -> None:
    pl_total = saldo.get("patrimonio_liquido")
    pl = None if pl_total is None else pl_total - saldo.get("minoritarios", 0.0)
    pl_ruim = "" if _positivo(pl) else "Patrimônio líquido negativo ou zero."
    lucro = _lucro(ttm)
    lista.add(
        "roe", "ROE (retorno sobre o patrimônio)",
        None if lucro is None or pl_ruim else lucro / pl, FRACAO, f"{base_12m}; {base_balanco}", pl_ruim,
    )  # fmt: skip
    nomes = (
        ("roic", "ROIC (retorno sobre o capital investido)", FRACAO),
        ("divida_bruta", "Dívida bruta", REAIS),
        ("caixa", "Caixa e aplicações", REAIS),
        ("divida_liquida", "Dívida líquida", REAIS),
        ("divida_sobre_pl", "Dívida líquida / patrimônio", VEZES),
        ("conversao_de_caixa", "Caixa operacional / lucro", VEZES),
    )
    if financeira:
        for chave, nome, unidade in nomes:
            lista.add(
                chave, nome, None, unidade, base_balanco, NAO_SE_APLICA_A_FINANCEIRAS
            )
        return
    divida, caixa = divida_e_caixa(saldo)
    investido = (
        None
        if pl_total is None or divida is None or caixa is None
        else pl_total + divida - caixa
    )
    sem_capital = "" if _positivo(investido) else "Capital investido negativo ou zero."
    ebit = ttm.get("ebit")
    lista.add(
        "roic", nomes[0][1], None if ebit is None or sem_capital else ebit * (1 - aliquota) / investido,
        FRACAO, f"{base_12m}; {base_balanco}", sem_capital,
    )  # fmt: skip
    liquida = None if divida is None or caixa is None else divida - caixa
    lista.add("divida_bruta", "Dívida bruta", divida, REAIS, base_balanco)
    lista.add("caixa", "Caixa e aplicações", caixa, REAIS, base_balanco)
    lista.add("divida_liquida", "Dívida líquida", liquida, REAIS, base_balanco)
    lista.add(
        "divida_sobre_pl", "Dívida líquida / patrimônio",
        None if liquida is None or pl_ruim else liquida / pl, VEZES, base_balanco, pl_ruim,
    )  # fmt: skip
    lucro_total, fco = ttm.get("lucro_liquido"), ttm.get("fco")
    sem_lucro = "" if _positivo(lucro_total) else "Sem lucro positivo no período."
    lista.add(
        "conversao_de_caixa", "Caixa operacional / lucro",
        None if fco is None or sem_lucro else fco / lucro_total, VEZES, base_12m, sem_lucro,
    )  # fmt: skip


def _cagr(serie: pd.Series | None, anos: int) -> tuple[float | None, str]:
    serie = pd.Series(dtype=float) if serie is None else serie.dropna()
    if len(serie) < anos + 1:
        return (
            None,
            f"Só há {len(serie)} anos de demonstrações guardados; o horizonte pede {anos + 1}.",
        )
    inicio, fim = float(serie.iloc[-(anos + 1)]), float(serie.iloc[-1])
    if inicio <= 0 or fim <= 0:
        return None, "Base negativa ou zero: crescimento composto não tem sentido."
    return (fim / inicio) ** (1 / anos) - 1, ""


def _crescimento(lista: _Lista, tabela: pd.DataFrame, anos: int) -> None:
    lucro = (
        None
        if tabela.empty
        else tabela.get("lucro_controladores", tabela.get("lucro_liquido"))
    )
    for chave, serie, nome in (
        (
            "crescimento_receita",
            None if tabela.empty else tabela.get("receita"),
            "da receita",
        ),
        ("crescimento_lucro", lucro, "do lucro"),
    ):
        base = (
            ""
            if tabela.empty
            else f"DFP de {tabela.index[-1] - anos} a {tabela.index[-1]}"
        )
        valor, motivo = _cagr(serie, anos)
        lista.add(
            chave,
            f"Crescimento {nome} ({anos} anos, ao ano)",
            valor,
            FRACAO,
            base,
            motivo,
        )


def _por_acao(
    lista: _Lista,
    ttm: dict,
    saldo: dict,
    acoes: tuple,
    preco: float | None,
    bases: tuple[str, str],
) -> None:
    quantidade, _, sem_acoes = acoes
    base_12m, base_balanco = bases
    lucro = _lucro(ttm)
    pl = (
        None
        if "patrimonio_liquido" not in saldo
        else saldo["patrimonio_liquido"] - saldo.get("minoritarios", 0.0)
    )
    lpa = None if sem_acoes or lucro is None else lucro / quantidade
    vpa = None if sem_acoes or pl is None else pl / quantidade
    lista.add(
        "lpa", "Lucro por ação (12 meses)", lpa, REAIS_POR_ACAO, base_12m, sem_acoes
    )
    lista.add(
        "vpa", "Patrimônio por ação", vpa, REAIS_POR_ACAO, base_balanco, sem_acoes
    )
    sem_preco = "" if _positivo(preco) else "Sem o preço do ativo."
    motivo_pl = (
        sem_preco
        or sem_acoes
        or (
            ""
            if _positivo(lpa)
            else "Prejuízo nos últimos 12 meses: o P/L não tem sentido."
        )
    )
    motivo_pvp = (
        sem_preco
        or sem_acoes
        or ("" if _positivo(vpa) else "Patrimônio líquido negativo ou zero.")
    )
    lista.add(
        "p_l",
        "P/L (preço / lucro por ação)",
        None if motivo_pl else preco / lpa,
        VEZES,
        base_12m,
        motivo_pl,
    )
    lista.add(
        "p_vp",
        "P/VP (preço / patrimônio por ação)",
        None if motivo_pvp else preco / vpa,
        VEZES,
        base_balanco,
        motivo_pvp,
    )


def _razao_positiva(
    numerador: float | None, denominador: float | None, sem_denominador: str
) -> tuple[float | None, str]:
    """(numerador ÷ denominador, motivo): denominador ausente, zero ou negativo vira o motivo."""
    if numerador is None or denominador is None:
        return None, ""
    if denominador <= 0:
        return None, sem_denominador
    return numerador / denominador, ""


def _de_mercado(
    lista: _Lista,
    ttm: dict,
    acoes: tuple,
    preco: float | None,
    bases: tuple[str, str],
    financeira: bool,
) -> None:
    """Valor de mercado, valor da firma, dividend yield e múltiplos da firma (D3 mudada em
    20/10/2026). O mesmo preço vale para todas as classes de ação; o DY usa o caixa pago em
    dividendos e JCP nos 12 meses (DFC), que pode incluir o pago aos minoritários."""
    quantidade, _, sem_acoes = acoes
    base_12m, base_balanco = bases
    sem_preco = "" if _positivo(preco) else "Sem o preço do ativo."
    motivo = sem_preco or sem_acoes
    mercado = None if motivo or preco is None else preco * quantidade
    lista.add(
        "valor_de_mercado", "Valor de mercado", mercado, REAIS, base_balanco, motivo
    )
    pagos = ttm.get("dividendos_pagos")
    lista.add(
        "dividend_yield", "Dividend yield (12 meses)",
        None if mercado is None or pagos is None else abs(pagos) / mercado, FRACAO, base_12m,
        motivo or ("" if pagos is not None else SEM_DIVIDENDOS_NO_CAIXA),
    )  # fmt: skip
    if financeira:
        for chave, nome, unidade in DA_FIRMA:
            lista.add(chave, nome, None, unidade, base_12m, NAO_SE_APLICA_A_FINANCEIRAS)
        return
    liquida = lista.itens["divida_liquida"].valor
    firma = None if mercado is None or liquida is None else mercado + liquida
    ebit, depreciacao = ttm.get("ebit"), ttm.get("depreciacao")
    ebitda = None if ebit is None or depreciacao is None else ebit + depreciacao
    fco, capex = ttm.get("fco"), ttm.get("capex")
    livre = None if fco is None or capex is None else fco - abs(capex)
    contas = (
        ("valor_da_firma", firma, ""),
        ("ev_ebitda", *_razao_positiva(firma, ebitda, "EBITDA negativo ou zero.")),
        ("ev_ebit", *_razao_positiva(firma, ebit, "EBIT negativo ou zero.")),
        ("p_receita", *_razao_positiva(mercado, ttm.get("receita"), SEM_RECEITA)),
        ("p_ebitda", *_razao_positiva(mercado, ebitda, "EBITDA negativo ou zero.")),
        ("p_ebit", *_razao_positiva(mercado, ebit, "EBIT negativo ou zero.")),
        ("p_fcf", *_razao_positiva(mercado, livre, "Caixa livre negativo ou zero.")),
    )
    for (chave, nome, unidade), (_, valor, sem_conta) in zip(
        DA_FIRMA, contas, strict=True
    ):
        base = (
            base_balanco if chave == "valor_da_firma" else f"{base_12m}; {base_balanco}"
        )
        lista.add(chave, nome, valor, unidade, base, motivo or sem_conta)


def _pagos_em_media(tabela: pd.DataFrame, anos: int) -> tuple[float | None, str, str]:
    """(média dos dividendos e JCP pagos nos `anos` últimos exercícios, base, motivo). Só a DFP:
    um exercício entra depois de publicado, então cortar o futuro não muda a média do passado."""
    if tabela.empty or "dividendos_pagos" not in tabela:
        return None, "", SEM_DIVIDENDOS_NO_CAIXA
    if len(tabela) < anos:
        return None, "", (
            f"Só há {len(tabela)} exercícios de demonstrações guardados; a média pede {anos}."
        )  # fmt: skip
    ultimos = tabela["dividendos_pagos"].iloc[-anos:]
    primeiro, ultimo = ultimos.index[0], ultimos.index[-1]
    base = f"DFP de {primeiro}" if anos == 1 else f"DFP de {primeiro} a {ultimo}"
    faltam = [str(ano) for ano, valor in ultimos.items() if pd.isna(valor)]
    if faltam:
        return None, base, (
            f"O fluxo de caixa de {', '.join(faltam)} não traz a linha de dividendos ou JCP pagos."
        )  # fmt: skip
    return float(ultimos.abs().mean()), base, ""


def _sobre_o_mercado(
    lista: _Lista, saldo: dict, tabela: pd.DataFrame, anos: int, base_balanco: str
) -> None:
    """P/Ativo e dividend yield médio: o valor de mercado de hoje sobre o ativo do balanço e
    sobre a média dos pagos nos exercícios (sem série de preço: o DY de cada ano pediria o preço
    da época, e o do Yahoo vem ajustado pelos proventos)."""
    mercado = lista.itens["valor_de_mercado"]
    sem_mercado = mercado.motivo if mercado.valor is None else ""
    ativo, sem_ativo = _razao_positiva(
        mercado.valor, saldo.get("ativo_total"), "Sem o ativo total no balanço."
    )
    lista.add(
        "p_ativo", "Preço / ativo total", ativo, VEZES, base_balanco,
        sem_mercado or sem_ativo,
    )  # fmt: skip
    media, base, sem_media = _pagos_em_media(tabela, anos)
    lista.add(
        "dividend_yield_medio", f"Dividend yield médio ({anos} anos)",
        None if mercado.valor is None or media is None else media / mercado.valor,
        FRACAO, base, sem_mercado or sem_media,
    )  # fmt: skip


def _tabela_anual(tabela: pd.DataFrame) -> pd.DataFrame:
    """Receita, lucro, margem líquida, patrimônio e dívida líquida de cada ano (vazio = NaN)."""
    if tabela.empty:
        return tabela
    vazio = pd.Series(float("nan"), index=tabela.index)

    def coluna(nome: str) -> pd.Series:
        return tabela.get(nome, vazio)

    lucro = coluna("lucro_controladores").fillna(coluna("lucro_liquido"))
    saida = pd.DataFrame(index=tabela.index)
    saida["receita"] = coluna("receita")
    saida["lucro"] = lucro
    saida["margem_liquida"] = coluna("lucro_liquido") / coluna("receita")
    saida["patrimonio"] = coluna("patrimonio_liquido")
    if "divida_cp" in tabela or "divida_lp" in tabela:
        divida = coluna("divida_cp").fillna(0) + coluna("divida_lp").fillna(0)
        caixa = coluna("caixa").fillna(0) + coluna("aplicacoes").fillna(0)
        saida["divida_liquida"] = divida - caixa
    return saida


def _filtros(
    itens: dict[str, Indicador], roic_minimo: float | None, pl_maximo: float | None
) -> list[str]:
    """Frases neutras: o número passa ou não do limite escolhido na página Parâmetros."""
    frases = []
    roic, pl = itens["roic"], itens["p_l"]
    if (
        roic_minimo is not None and roic.valor is not None
    ):  # o mesmo que roic.disponivel
        lado = "acima" if roic.valor * 100 >= roic_minimo else "abaixo"
        valor = f"{roic.valor:.1%}".replace(".", ",")
        frases.append(
            f"ROIC de {valor}: {lado} do seu filtro de {roic_minimo:g}%.".replace(
                ".0%", "%"
            )
        )
    if pl_maximo is not None and pl.valor is not None:
        lado = "dentro" if pl.valor <= pl_maximo else "fora"
        frases.append(
            f"P/L de {pl.valor:.1f}".replace(".", ",")
            + f": {lado} do seu filtro de até {pl_maximo:g}."
        )
    return frases


def calcular(
    dados: DadosDaEmpresa,
    preco: float | None,
    anos: int = ANOS_DO_CRESCIMENTO,
    roic_minimo: float | None = None,
    pl_maximo: float | None = None,
    aliquota: float = ALIQUOTA_DE_IR_CS,
) -> Fundamentos:
    """Os indicadores da companhia. `preco`: último fechamento do ticker, na moeda do balanço;
    `aliquota`: o imposto usado no ROIC (34% no Brasil, `ALIQUOTA_DOS_EUA` nos EUA)."""
    contas = dados.contas
    financeira = e_financeira(
        dados.setor, contas["conta"].unique() if not contas.empty else ()
    )
    ttm, base_12m, usados = doze_meses(contas)
    saldo, data_do_balanco, documento_do_balanco = balanco_mais_recente(contas)
    base_balanco = f"balanço de {_data(data_do_balanco)}" if data_do_balanco else ""
    if data_do_balanco:
        usados.append((documento_do_balanco, data_do_balanco))
    acoes = acoes_em_circulacao(saldo, contas)
    tabela = anuais(contas)
    lista = _Lista()
    _resultado(lista, ttm, base_12m, financeira)
    _retornos_e_divida(lista, ttm, saldo, base_12m, base_balanco, financeira, aliquota)
    _crescimento(lista, tabela, anos)
    _por_acao(lista, ttm, saldo, acoes, preco, (base_12m, base_balanco))
    _de_mercado(lista, ttm, acoes, preco, (base_12m, base_balanco), financeira)
    _sobre_o_mercado(lista, saldo, tabela, anos, base_balanco)
    docs = dados.documentos
    if not docs.empty:
        usados_set = set(usados)
        docs = docs[
            [
                (d, r) in usados_set
                for d, r in zip(docs["documento"], docs["referencia"], strict=True)
            ]
        ]
    empresa = (
        dados.documentos.sort_values("referencia")["empresa"].iloc[-1]
        if not dados.documentos.empty
        else ""
    )
    notas = [acoes[1]] if acoes[1] else []
    return Fundamentos(
        empresa=empresa,
        setor=dados.setor,
        financeira=financeira,
        indicadores=lista.itens,
        anual=_tabela_anual(tabela),
        documentos=docs.sort_values("referencia") if not docs.empty else docs,
        notas=notas,
        filtros=_filtros(lista.itens, roic_minimo, pl_maximo),
    )
