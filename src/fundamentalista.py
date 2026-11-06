"""Cálculos fundamentalistas do relatório completo de empresa (série 2 da base de ML, PR 2; ADR 0032).

Tudo sai das demonstrações da CVM já guardadas (`DadosDaEmpresa`), com as mesmas bases da tela
Fundamentos (`src/fundamentos.py`: 12 meses e balanço mais recente), e cada número diz de quando é e,
quando falta, por quê:

- **DuPont:** margem líquida × giro do ativo × alavancagem = ROE (fecha com o ROE da tela: lucro e
  patrimônio dos controladores, balanço do fim).
- **Ciclo de caixa (dias):** prazo médio de receber (contas a receber ÷ receita), de estocar e de
  pagar (estoques e fornecedores ÷ custo), × 365; com o saldo médio entre hoje e um ano antes,
  quando houver, senão o saldo do fim (e o texto diz qual).
- **Caixa livre:** caixa operacional − capex; **capex ÷ depreciação** (acima de 1, a empresa investe
  mais do que desgasta).
- **Cobertura de juros:** EBIT ÷ despesas financeiras.
- **Sem preço (linha 54 da fila):** margem EBITDA (EBIT + depreciação, como a série T1 da base),
  dívida líquida sobre o EBITDA e sobre o EBIT, passivos e patrimônio sobre o ativo, ROA, liquidez
  corrente, dividendo por ação, payout e crescimento do dividendo, e as ações por espécie (ON e PN).
- **Histórico de até 10 anos** dos DFPs: a tabela, a análise vertical (resultado sobre a receita,
  balanço sobre o ativo), a horizontal (variação de um ano para o outro, só entre anos seguidos), o
  crescimento composto e a consistência. Ano que falta aparece como falta, nunca como zero.

Bancos e seguradoras: "não se aplica" onde o indicador não faz sentido, como na tela.
"""

from dataclasses import dataclass, field
from datetime import date
from itertools import pairwise

import pandas as pd

from base.fre import ULTIMO_ANO_COM_AS_TABELAS
from src.banco.demonstracoes import DadosDaEmpresa
from src.demonstracoes import EXERCICIO, POSICAO, e_financeira
from src.formatos import formatar_decimal, formatar_pct
from src.fundamentos import (
    BALANCO,
    COMECO_E_FIM,
    CONFERENCIA,
    DAS_ACOES,
    DOZE_MESES,
    FRACAO,
    LUCRO,
    NAO_SE_APLICA_A_FINANCEIRAS,
    REAIS,
    REAIS_POR_ACAO,
    TODOS_OS_ANOS,
    UM_ANO_ANTES,
    VEZES,
    Indicador,
    acoes_em_circulacao,
    anuais,
    balanco_mais_recente,
    divida_e_caixa,
    doze_meses,
    um_ano_antes,
)
from src.fundamentos import todas_as_entradas as _entradas_das_contas
from src.rastro import Entrada

DIAS = "dias"
ACOES = "ações"
ANOS_DO_CRESCIMENTO_DO_DIVIDENDO = 5
DIAS_NO_ANO = 365
ANOS_DO_HISTORICO = 10
SEM_RECEITA = "Sem receita no período."
SEM_CUSTO = "Sem custo das vendas informado (empresa de serviços ou holding)."
SEM_DESPESA_FINANCEIRA = "Sem despesa financeira no período: não se aplica."
VERSAO_DO_FUNDAMENTALISTA = "1"  # sobe quando uma fórmula de `FORMULAS` mudar
# a conta de cada indicador, para o rastro do número (`src/rastro.py`)
_SALDO_MEDIO = (
    "saldo médio entre o balanço mais recente e o de um ano antes (sem ele, o do fim)"
)
_PL = "(patrimônio líquido − participação dos minoritários)"
DOS_DIVIDENDOS = (
    "anos_pagando",
    "diluicao",
    "dividendo_por_acao",
    "payout",
    "crescimento_do_dividendo",
)  # de `dividendos_e_diluicao`, não de `calcular`
DA_COMPOSICAO_DO_CAPITAL = ("acoes_em_circulacao",)  # de `acoes_por_especie`
_EBITDA = "(EBIT + depreciação e amortização)"
_PAGOS = "dividendos e JCP pagos no fluxo de caixa da DFP"
FORMULAS = {
    "dupont_margem": "lucro dos controladores ÷ receita (12 meses)",
    "dupont_giro": "receita (12 meses) ÷ ativo total (balanço mais recente)",
    "dupont_alavancagem": f"ativo total ÷ {_PL} (balanço mais recente)",
    "dupont_roe": "margem líquida dos acionistas × giro do ativo × alavancagem",
    "pmr": f"contas a receber ({_SALDO_MEDIO}) ÷ receita (12 meses) × {DIAS_NO_ANO}",
    "pme": f"estoques ({_SALDO_MEDIO}) ÷ custo das vendas (12 meses) × {DIAS_NO_ANO}",
    "pmp": f"fornecedores ({_SALDO_MEDIO}) ÷ custo das vendas (12 meses) × {DIAS_NO_ANO}",
    "ciclo_de_caixa": "prazo médio de recebimento + de estocagem − de pagamento",
    "caixa_livre": "caixa operacional − capex (12 meses, fluxo de caixa)",
    "capex": "capex do fluxo de caixa (12 meses), em valor absoluto",
    "capex_sobre_depreciacao": "capex ÷ depreciação e amortização (12 meses)",
    "cobertura_de_juros": "EBIT ÷ despesas financeiras (12 meses)",
    "margem_ebitda": f"{_EBITDA} ÷ receita (12 meses)",
    "divida_liquida_sobre_ebitda": f"dívida líquida (balanço mais recente) ÷ {_EBITDA} (12 meses)",
    "divida_liquida_sobre_ebit": "dívida líquida (balanço mais recente) ÷ EBIT (12 meses)",
    "passivos_sobre_ativos": (
        "(ativo total − patrimônio líquido com os minoritários) ÷ ativo total (balanço mais recente)"
    ),
    "pl_sobre_ativos": "patrimônio líquido com os minoritários ÷ ativo total (balanço mais recente)",
    "roa": "lucro líquido consolidado (12 meses) ÷ ativo total (balanço mais recente)",
    "liquidez_corrente": "ativo circulante ÷ passivo circulante (balanço mais recente)",
    "anos_pagando": "anos com dividendos ou JCP pagos no fluxo de caixa da DFP (acima de zero)",
    "diluicao": (
        "(ações em circulação do último ano ÷ as do primeiro) ^ (1 ÷ anos) − 1, ajustadas por "
        "desdobramentos, grupamentos e bonificações do FRE"
    ),
    "dividendo_por_acao": (
        f"{_PAGOS} do último exercício ÷ ações em circulação do fim dele (ajustadas por "
        "desdobramentos, grupamentos e bonificações)"
    ),
    "payout": f"{_PAGOS} do último exercício ÷ lucro dos controladores dele",
    "crescimento_do_dividendo": (
        f"(dividendo por ação do último exercício ÷ o de {ANOS_DO_CRESCIMENTO_DO_DIVIDENDO} anos "
        f"antes) ^ (1 ÷ {ANOS_DO_CRESCIMENTO_DO_DIVIDENDO}) − 1"
    ),
    "acoes_em_circulacao": (
        "ações do capital integralizado − em tesouraria, por espécie (ON e PN), no balanço mais "
        "recente; conferidas com o lucro por ação da DRE"
    ),
}


# As contas que entram em cada indicador, e de onde (os lugares de `src/fundamentos.py`): é o que o
# rastro cita como entradas. Cada uma leva todas as contas que `calcular` lê para dar o número, também
# as que só decidem se ele sai (o DuPont pede receita, ativo, patrimônio e lucro para as quatro partes).
# Os fatores do FRE (desdobramentos, grupamentos e bonificações) não são contas da DFP e ficam fora:
# sem eles, as entradas refazem os dividendos com o ajuste só pelos saltos redondos.
def _medio(conta: str) -> tuple[tuple[str, str], ...]:
    """O saldo médio: o do balanço mais recente e, quando há, o de um ano antes."""
    return ((BALANCO, conta), (UM_ANO_ANTES, conta))


_DO_DUPONT = (
    (DOZE_MESES, LUCRO),
    (DOZE_MESES, "receita"),
    (BALANCO, "ativo_total"),
    (BALANCO, "patrimonio_liquido"),
    (BALANCO, "minoritarios"),
)
_RECEBER = ((DOZE_MESES, "receita"), *_medio("contas_a_receber"))
_ESTOCAR = ((DOZE_MESES, "custo"), *_medio("estoques"))
_PAGAR = ((DOZE_MESES, "custo"), *_medio("fornecedores"))
_DIVIDA_LIQUIDA = tuple(
    (BALANCO, conta) for conta in ("divida_cp", "divida_lp", "caixa", "aplicacoes")
)
_DA_ESTRUTURA = ((BALANCO, "ativo_total"), (BALANCO, "patrimonio_liquido"))
# as ações de todos os anos: os saltos sem evento e os fatores que ajustam cada ano leem a série inteira
_ACOES_DE_TODOS_OS_ANOS = (
    (TODOS_OS_ANOS, "acoes_total"),
    (TODOS_OS_ANOS, "acoes_tesouraria"),
)
_PAGOS_NO_ULTIMO = (CONFERENCIA, "dividendos_pagos")
_POR_ESPECIE = tuple(
    (BALANCO, conta)
    for conta in (
        "acoes_ordinarias",
        "acoes_ordinarias_tesouraria",
        "acoes_preferenciais",
        "acoes_preferenciais_tesouraria",
    )
)
CONTAS_DOS_INDICADORES: dict[str, tuple[tuple[str, str], ...]] = {
    "dupont_margem": _DO_DUPONT,
    "dupont_giro": _DO_DUPONT,
    "dupont_alavancagem": _DO_DUPONT,
    "dupont_roe": _DO_DUPONT,
    "pmr": _RECEBER,
    "pme": _ESTOCAR,
    "pmp": _PAGAR,
    "ciclo_de_caixa": _RECEBER + _ESTOCAR + _PAGAR,
    "caixa_livre": ((DOZE_MESES, "fco"), (DOZE_MESES, "capex")),
    "capex": ((DOZE_MESES, "capex"),),
    "capex_sobre_depreciacao": ((DOZE_MESES, "capex"), (DOZE_MESES, "depreciacao")),
    "cobertura_de_juros": ((DOZE_MESES, "ebit"), (DOZE_MESES, "despesas_financeiras")),
    "margem_ebitda": (
        (DOZE_MESES, "ebit"),
        (DOZE_MESES, "depreciacao"),
        (DOZE_MESES, "receita"),
    ),
    "divida_liquida_sobre_ebitda": (
        *_DIVIDA_LIQUIDA,
        (DOZE_MESES, "ebit"),
        (DOZE_MESES, "depreciacao"),
    ),
    "divida_liquida_sobre_ebit": (*_DIVIDA_LIQUIDA, (DOZE_MESES, "ebit")),
    "passivos_sobre_ativos": _DA_ESTRUTURA,
    "pl_sobre_ativos": _DA_ESTRUTURA,
    "roa": ((DOZE_MESES, "lucro_liquido"), (BALANCO, "ativo_total")),
    "liquidez_corrente": (
        (BALANCO, "ativo_circulante"),
        (BALANCO, "passivo_circulante"),
    ),
    "anos_pagando": ((TODOS_OS_ANOS, "dividendos_pagos"),),
    "diluicao": _ACOES_DE_TODOS_OS_ANOS,
    # o último ano não tem salto depois dele: só as ações do fim dele entram no "por ação"
    "dividendo_por_acao": (
        _PAGOS_NO_ULTIMO,
        (CONFERENCIA, "acoes_total"),
        (CONFERENCIA, "acoes_tesouraria"),
    ),
    "payout": (_PAGOS_NO_ULTIMO, (CONFERENCIA, LUCRO)),
    "crescimento_do_dividendo": (
        (COMECO_E_FIM, "dividendos_pagos"),
        *_ACOES_DE_TODOS_OS_ANOS,
    ),
    "acoes_em_circulacao": DAS_ACOES + _POR_ESPECIE,
}


def todas_as_entradas(dados: DadosDaEmpresa) -> dict[str, tuple[Entrada, ...]]:
    """As entradas de cada indicador de `CONTAS_DOS_INDICADORES` (ver `fundamentos.todas_as_entradas`)."""
    return _entradas_das_contas(
        dados,
        anos=ANOS_DO_CRESCIMENTO_DO_DIVIDENDO,
        contas_dos_indicadores=CONTAS_DOS_INDICADORES,
    )


@dataclass(frozen=True)
class Historico:
    contas: pd.DataFrame  # um ano por linha (o índice), uma conta por coluna
    vertical: pd.DataFrame  # resultado sobre a receita; balanço sobre o ativo total
    horizontal: (
        pd.DataFrame
    )  # variação de um ano para o outro (vazio se faltar o ano anterior)
    crescimento: dict[str, float | None] = field(
        default_factory=dict
    )  # composto, ao ano
    consistencia: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Fundamentalista:
    indicadores: dict[str, Indicador]
    historico: Historico

    def __getitem__(self, chave: str) -> Indicador:
        return self.indicadores[chave]


def _data(d: date) -> str:
    return f"{d:%d/%m/%Y}"


def _saldos_em(contas: pd.DataFrame, referencia: date) -> dict:
    linhas = contas[
        (contas["periodo"] == POSICAO) & (contas["referencia"] == referencia)
    ]
    return dict(zip(linhas["conta"], linhas["valor"], strict=True))


def _indicador(
    chave: str,
    nome: str,
    valor: float | None,
    unidade: str,
    base: str,
    motivo: str = "",
) -> Indicador:
    return Indicador(chave, nome, None if motivo else valor, unidade, base, motivo)


def _dupont(ttm: dict, saldo: dict, base: str) -> list[Indicador]:
    lucro = ttm.get("lucro_controladores", ttm.get("lucro_liquido"))
    receita, ativo = ttm.get("receita"), saldo.get("ativo_total")
    pl_total = saldo.get("patrimonio_liquido")
    pl = None if pl_total is None else pl_total - saldo.get("minoritarios", 0.0)
    motivo = (
        SEM_RECEITA
        if not receita or receita <= 0
        else "Ativo total indisponível." if not ativo or ativo <= 0
        else "Patrimônio líquido negativo ou zero." if pl is None or pl <= 0
        else "Lucro indisponível." if lucro is None
        else ""
    )  # fmt: skip
    if motivo:
        return [
            _indicador(c, n, None, u, base, motivo)
            for c, n, u in (
                ("dupont_margem", "Margem líquida dos acionistas (DuPont)", FRACAO),
                ("dupont_giro", "Giro do ativo", VEZES),
                ("dupont_alavancagem", "Alavancagem (ativo / patrimônio)", VEZES),
                ("dupont_roe", "ROE pelo DuPont", FRACAO),
            )
        ]
    margem, giro, alavancagem = lucro / receita, receita / ativo, ativo / pl  # type: ignore[operator]
    return [
        _indicador(
            "dupont_margem",
            "Margem líquida dos acionistas (DuPont)",
            margem,
            FRACAO,
            base,
        ),
        _indicador("dupont_giro", "Giro do ativo", giro, VEZES, base),
        _indicador(
            "dupont_alavancagem",
            "Alavancagem (ativo / patrimônio)",
            alavancagem,
            VEZES,
            base,
        ),
        _indicador(
            "dupont_roe", "ROE pelo DuPont", margem * giro * alavancagem, FRACAO, base
        ),
    ]


def _saldo_medio(conta: str, saldo: dict, anterior: dict) -> float | None:
    if conta not in saldo:
        return None
    return (saldo[conta] + anterior[conta]) / 2 if conta in anterior else saldo[conta]


def _ciclo(ttm: dict, saldo: dict, anterior: dict, base: str) -> list[Indicador]:
    receita, custo = ttm.get("receita"), abs(ttm.get("custo") or 0.0)
    receber = _saldo_medio("contas_a_receber", saldo, anterior)
    estoques = _saldo_medio("estoques", saldo, anterior)
    fornecedores = _saldo_medio("fornecedores", saldo, anterior)

    def prazo(
        chave: str,
        nome: str,
        saldo_medio: float | None,
        divisor: float | None,
        falta: str,
    ) -> Indicador:
        if not divisor or divisor <= 0:
            return _indicador(chave, nome, None, DIAS, base, falta)
        if saldo_medio is None:
            return _indicador(chave, nome, None, DIAS, base, "Saldo não informado.")
        return _indicador(chave, nome, saldo_medio / divisor * DIAS_NO_ANO, DIAS, base)

    pmr = prazo("pmr", "Prazo médio de recebimento", receber, receita, SEM_RECEITA)
    pme = prazo("pme", "Prazo médio de estocagem", estoques, custo, SEM_CUSTO)
    pmp = prazo("pmp", "Prazo médio de pagamento", fornecedores, custo, SEM_CUSTO)
    partes = (pmr, pme, pmp)
    falta = next((p.motivo for p in partes if not p.disponivel), "")
    ciclo = (
        None if falta else pmr.valor + pme.valor - pmp.valor  # type: ignore[operator]
    )
    return [
        *partes,
        _indicador("ciclo_de_caixa", "Ciclo de caixa", ciclo, DIAS, base, falta),
    ]


def _caixa_livre(ttm: dict, base: str) -> list[Indicador]:
    fco, capex, depreciacao = ttm.get("fco"), ttm.get("capex"), ttm.get("depreciacao")
    sem_capex = "Capex não informado no fluxo de caixa." if capex is None else ""
    livre = None if fco is None or sem_capex else fco - abs(capex)  # type: ignore[arg-type]
    sem_depreciacao = (
        "Depreciação não informada." if not depreciacao or depreciacao <= 0 else ""
    )
    return [
        _indicador(
            "caixa_livre", "Caixa livre (operacional − capex)", livre, REAIS, base,
            sem_capex or ("Caixa operacional não informado." if fco is None else ""),
        ),
        _indicador("capex", "Capex", None if capex is None else abs(capex), REAIS, base, sem_capex),
        _indicador(
            "capex_sobre_depreciacao", "Capex / depreciação",
            None if sem_capex or sem_depreciacao else abs(capex) / depreciacao,  # type: ignore[arg-type,operator]
            VEZES, base, sem_capex or sem_depreciacao,
        ),
    ]  # fmt: skip


def _cobertura(ttm: dict, base: str) -> Indicador:
    ebit, despesas = ttm.get("ebit"), ttm.get("despesas_financeiras")
    motivo = (
        SEM_DESPESA_FINANCEIRA if not despesas
        else "EBIT indisponível." if ebit is None
        else ""
    )  # fmt: skip
    valor = None if motivo else ebit / abs(despesas)  # type: ignore[operator,arg-type]
    return _indicador(
        "cobertura_de_juros",
        "Cobertura de juros (EBIT / despesas financeiras)",
        valor,
        VEZES,
        base,
        motivo,
    )


def _margem_ebitda(ttm: dict, base: str) -> Indicador:
    ebit, depreciacao, receita = (
        ttm.get("ebit"),
        ttm.get("depreciacao"),
        ttm.get("receita"),
    )
    motivo = (
        SEM_RECEITA if not receita or receita <= 0
        else "EBIT indisponível." if ebit is None
        else "Depreciação não informada." if depreciacao is None
        else ""
    )  # fmt: skip
    valor = None if motivo else (ebit + depreciacao) / receita  # type: ignore[operator]
    return _indicador("margem_ebitda", "Margem EBITDA", valor, FRACAO, base, motivo)


def _sobre_o_resultado(
    chave: str,
    nome: str,
    liquida: float | None,
    resultado: float | None,
    falta: str,
    base: str,
) -> Indicador:
    """Dívida líquida ÷ um resultado positivo; caixa maior que a dívida dá a razão negativa."""
    motivo = (
        "Dívida ou caixa não informados no balanço." if liquida is None
        else f"{falta} indisponível." if resultado is None
        else f"{falta} negativo ou zero: a razão não tem sentido." if resultado <= 0
        else ""
    )  # fmt: skip
    valor = None if motivo else liquida / resultado  # type: ignore[operator]
    return _indicador(chave, nome, valor, VEZES, base, motivo)


def _alavancagem(ttm: dict, saldo: dict, base: str) -> list[Indicador]:
    divida, caixa = divida_e_caixa(saldo)
    liquida = None if divida is None or caixa is None else divida - caixa
    ebit, depreciacao = ttm.get("ebit"), ttm.get("depreciacao")
    ebitda = None if ebit is None or depreciacao is None else ebit + depreciacao
    return [
        _sobre_o_resultado("divida_liquida_sobre_ebitda", "Dívida líquida / EBITDA", liquida,
                           ebitda, "EBITDA", base),
        _sobre_o_resultado("divida_liquida_sobre_ebit", "Dívida líquida / EBIT", liquida, ebit,
                           "EBIT", base),
    ]  # fmt: skip


def _liquidez(saldo: dict, base: str) -> Indicador:
    circulante, passivo = saldo.get("ativo_circulante"), saldo.get("passivo_circulante")
    motivo = (
        "Ativo circulante não informado." if circulante is None
        else "Passivo circulante não informado ou zero." if not passivo or passivo <= 0
        else ""
    )  # fmt: skip
    valor = None if motivo else circulante / passivo  # type: ignore[operator]
    return _indicador(
        "liquidez_corrente", "Liquidez corrente", valor, VEZES, base, motivo
    )


def _estrutura(ttm: dict, saldo: dict, base_balanco: str, base: str) -> list[Indicador]:
    """ROA e o quanto do ativo é dos sócios e de terceiros: valem também para bancos e seguradoras."""
    ativo, pl = saldo.get("ativo_total"), saldo.get("patrimonio_liquido")
    lucro = ttm.get("lucro_liquido")
    sem_ativo = "Ativo total indisponível." if not ativo or ativo <= 0 else ""
    sem_pl = sem_ativo or ("Patrimônio líquido não informado." if pl is None else "")
    sem_lucro = sem_ativo or ("Lucro indisponível." if lucro is None else "")
    return [
        _indicador("roa", "ROA (retorno sobre o ativo)",
                   None if sem_lucro else lucro / ativo, FRACAO, base, sem_lucro),  # type: ignore[operator]
        _indicador("passivos_sobre_ativos", "Passivos / ativos",
                   None if sem_pl else (ativo - pl) / ativo, FRACAO, base_balanco, sem_pl),  # type: ignore[operator]
        _indicador("pl_sobre_ativos", "Patrimônio / ativos",
                   None if sem_pl else pl / ativo, FRACAO, base_balanco, sem_pl),  # type: ignore[operator]
    ]  # fmt: skip


def _nao_se_aplica(indicadores: list[Indicador]) -> list[Indicador]:
    return [
        Indicador(i.chave, i.nome, None, i.unidade, i.base, NAO_SE_APLICA_A_FINANCEIRAS)
        for i in indicadores
    ]


def _cagr(serie: pd.Series) -> float | None:
    validos = serie.dropna()
    if len(validos) < 2 or validos.iloc[0] <= 0 or validos.iloc[-1] <= 0:
        return None
    anos = validos.index[-1] - validos.index[0]
    return float((validos.iloc[-1] / validos.iloc[0]) ** (1 / anos) - 1)


# as ações por espécie vão para a ficha técnica (`acoes_por_especie`), não para o histórico
CONTAS_SO_DA_FICHA = (
    "acoes_ordinarias",
    "acoes_preferenciais",
    "acoes_ordinarias_tesouraria",
    "acoes_preferenciais_tesouraria",
)


def historico(contas: pd.DataFrame, anos: int = ANOS_DO_HISTORICO) -> Historico:
    """Os últimos `anos` exercícios (DFP), com vertical, horizontal, crescimento e consistência."""
    tabela = anuais(contas).drop(columns=list(CONTAS_SO_DA_FICHA), errors="ignore")
    if tabela.empty:
        vazio = pd.DataFrame()
        return Historico(vazio, vazio, vazio)
    ultimo = int(tabela.index.max())
    primeiro = max(int(tabela.index.min()), ultimo - anos + 1)
    tabela = tabela.reindex(pd.Index(range(primeiro, ultimo + 1), name="ano"))
    dfp = contas[contas["documento"] == "DFP"]
    fluxos = set(dfp.loc[dfp["periodo"] == EXERCICIO, "conta"]) & set(tabela.columns)
    saldos = set(dfp.loc[dfp["periodo"] == POSICAO, "conta"]) & set(tabela.columns)
    vertical = pd.DataFrame(index=tabela.index)
    if "receita" in tabela:
        for conta in sorted(fluxos):
            vertical[conta] = tabela[conta] / tabela["receita"]
    if "ativo_total" in tabela:
        for conta in sorted(saldos):
            vertical[conta] = tabela[conta] / tabela["ativo_total"]
    horizontal = tabela.pct_change(fill_method=None)
    lucro = tabela.get("lucro_controladores", tabela.get("lucro_liquido"))
    com_dado = tabela.notna().any(axis=1)
    return Historico(
        contas=tabela,
        vertical=vertical,
        horizontal=horizontal,
        crescimento={
            "receita": _cagr(tabela["receita"]) if "receita" in tabela else None,
            "lucro": _cagr(lucro) if lucro is not None else None,
        },
        consistencia={
            "anos_com_dado": int(com_dado.sum()),
            "anos_com_lucro": int((lucro > 0).sum()) if lucro is not None else 0,
            "anos_com_receita_crescendo": int((horizontal["receita"] > 0).sum())
            if "receita" in horizontal
            else 0,
        },
    )


def calcular(dados: DadosDaEmpresa) -> Fundamentalista:
    """Os indicadores fundamentalistas novos e o histórico de uma empresa."""
    contas = dados.contas
    financeira = e_financeira(
        dados.setor, contas["conta"].unique() if not contas.empty else ()
    )
    ttm, base_12m, _ = doze_meses(contas)
    saldo, data_do_balanco, _ = balanco_mais_recente(contas)
    anterior = (
        _saldos_em(contas, um_ano_antes(data_do_balanco)) if data_do_balanco else {}
    )
    base_balanco = f"balanço de {_data(data_do_balanco)}" if data_do_balanco else ""
    base = f"{base_12m}; {base_balanco}"
    base_media = (
        f"{base_12m}; saldo médio de {_data(um_ano_antes(data_do_balanco))} e "
        f"{_data(data_do_balanco)}"
        if anterior and data_do_balanco
        else f"{base_12m}; saldo do fim, em {_data(data_do_balanco)}"
        if data_do_balanco
        else base_12m
    )
    grupos = [_dupont(ttm, saldo, base), _ciclo(ttm, saldo, anterior, base_media)]
    grupos += [_caixa_livre(ttm, base_12m), [_cobertura(ttm, base_12m)]]
    grupos += [[_margem_ebitda(ttm, base_12m)], _alavancagem(ttm, saldo, base)]
    grupos += [[_liquidez(saldo, base_balanco)]]
    indicadores = [
        i for grupo in grupos for i in (_nao_se_aplica(grupo) if financeira else grupo)
    ]
    indicadores += _estrutura(ttm, saldo, base_balanco, base)
    return Fundamentalista(
        indicadores={i.chave: i for i in indicadores}, historico=historico(contas)
    )


# --- dividendos e diluição (série 2, PR 6) -------------------------------------------------------
FATORES_DE_CAPITAL = ("desdobramento", "grupamento", "bonificação")
SALTO_MINIMO = (
    1.9  # razão entre as ações de dois anos que já pode ser desdobramento (2 para 1)
)
TOLERANCIA_DO_SALTO = 0.02  # a razão precisa estar a 2% de um número inteiro
# salto de exatamente mil vezes: a quantidade veio em milhares num ano e em unidades no outro
# (Petrobras, 2020 → 2021), não um desdobramento de 1.000 para 1
TROCA_DE_UNIDADE = 1_000.0
# depois do último FRE com eventos, mudança nas ações a partir disto, sem evento, pode ser bonificação
# (que não dilui) ou emissão: sem como saber, a diluição fica sem número (fim da série 2: Itaú, +13%)
SALTO_SEM_EVENTO = 0.05


@dataclass(frozen=True)
class DividendosEDiluicao:
    historico: (
        pd.DataFrame
    )  # por ano: ações, ajustadas, dividendos pagos, lucro, payouts
    diluicao_anual: (
        float | None
    )  # crescimento composto das ações ajustadas (0,1 = 10% ao ano)
    anos_pagando: int
    avisos: list[str] = field(default_factory=list)
    # as ações mudaram depois de 2022 sem evento conhecido: o "por ação" de antes pode estar errado
    acoes_sem_evento: bool = False


def _salto_redondo(razao: float) -> float | None:
    """2, 3, 10... (desdobramento) ou 1/2, 1/10... (grupamento), se a razão estiver perto."""
    if (
        razao >= SALTO_MINIMO
        and abs(razao - round(razao)) <= TOLERANCIA_DO_SALTO * razao
    ):
        return float(round(razao))
    inversa = 1 / razao if razao > 0 else 0
    if (
        inversa >= SALTO_MINIMO
        and abs(inversa - round(inversa)) <= TOLERANCIA_DO_SALTO * inversa
    ):
        return 1 / round(inversa)
    return None


def _fatores_por_ano(
    acoes: pd.Series, eventos: pd.DataFrame | None
) -> tuple[dict[int, float], list[str]]:
    """Ano → fator do evento entre aquele balanço e o seguinte (FRE ou salto redondo, avisado)."""
    conhecidos: dict[int, float] = {}
    if eventos is not None and not eventos.empty:
        de_capital = eventos[
            eventos["tipo"].isin(FATORES_DE_CAPITAL) & eventos["fator"].notna()
        ]
        for evento in de_capital.itertuples(index=False):
            ano_anterior = (
                pd.Timestamp(evento.data).year - 1
            )  # balanço de 31/12 antes do evento
            conhecidos[ano_anterior] = conhecidos.get(ano_anterior, 1.0) * float(
                evento.fator
            )
    avisos = []
    anos = list(acoes.dropna().index)
    for ano, seguinte in pairwise(anos):
        if ano in conhecidos or seguinte != ano + 1 or acoes[ano] <= 0:
            continue
        fator = _salto_redondo(acoes[seguinte] / acoes[ano])
        if fator:
            conhecidos[ano] = fator
            avisos.append(
                _aviso_do_salto(ano, seguinte, acoes[seguinte] / acoes[ano], fator)
            )
    return conhecidos, avisos


def _aviso_do_salto(ano: int, seguinte: int, razao: float, fator: float) -> str:
    if fator == TROCA_DE_UNIDADE:  # a CVM passou a receber a quantidade em unidades
        return (
            f"Entre {ano} e {seguinte} a quantidade de ações passou de milhares para unidades na "
            "CVM (mil vezes maior, sem evento no FRE): tratado como troca de unidade, não como "
            "diluição."
        )
    tipo = "desdobramento" if fator > 1 else "grupamento"
    return (
        f"Entre {ano} e {seguinte} as ações mudaram {formatar_decimal(razao)} vezes sem evento no "
        f"FRE: tratado como provável {tipo}, não como diluição."
    )


def _saltos_sem_evento(acoes: pd.Series, conhecidos: dict[int, float]) -> list[str]:
    """Avisos dos saltos nas ações depois do último FRE com eventos, sem evento que os explique."""
    avisos = []
    serie = acoes.dropna()
    for ano, seguinte in pairwise(serie.index):
        if (
            seguinte <= ULTIMO_ANO_COM_AS_TABELAS
            or ano in conhecidos
            or serie[ano] <= 0
        ):
            continue
        mudanca = serie[seguinte] / serie[ano] - 1
        if abs(mudanca) >= SALTO_SEM_EVENTO:
            avisos.append(
                f"Entre {ano} e {seguinte} as ações mudaram {formatar_pct(mudanca)} "
                f"sem evento conhecido: o FRE aberto não traz eventos de capital depois de "
                f"{ULTIMO_ANO_COM_AS_TABELAS}, e pode ter sido bonificação (que não dilui) ou emissão. "
                "A diluição fica sem número até a conferência nos fatos relevantes."
            )
    return avisos


def _ajustadas(acoes: pd.Series, fatores: dict[int, float]) -> pd.Series:
    """As ações de cada ano na unidade de hoje: multiplicadas pelos eventos que vieram depois."""
    ajustadas = acoes.copy()
    for ano in acoes.index:
        multiplicador = 1.0
        for ano_do_evento, fator in fatores.items():
            if ano_do_evento >= ano:
                multiplicador *= fator
        ajustadas[ano] = acoes[ano] * multiplicador
    return ajustadas


def _coluna_anual(tabela: pd.DataFrame, nome: str) -> pd.Series:
    if nome not in tabela:
        return pd.Series(float("nan"), index=tabela.index)
    return tabela[nome].astype(float)


def _proventos_por_ano(proventos: pd.DataFrame) -> pd.DataFrame:
    """Uma linha do FRE por ano: a do exercício mais tarde no ano e, nele, a versão mais recente.

    O FRE de algumas empresas (o Banco do Brasil, por exemplo) traz um exercício parcial
    (31/03/2010) ao lado do cheio (31/12/2010); dois no mesmo ano quebravam o `reindex` por ano.
    """
    exercicio = pd.to_datetime(proventos["exercicio"])
    ordem = ["ano", "exercicio_"] + (["versao"] if "versao" in proventos else [])
    return (
        proventos.assign(ano=exercicio.dt.year, exercicio_=exercicio)
        .sort_values(ordem)
        .drop_duplicates("ano", keep="last")
        .set_index("ano")
    )


def dividendos_e_diluicao(
    dados: DadosDaEmpresa,
    proventos: pd.DataFrame | None = None,
    eventos: pd.DataFrame | None = None,
) -> DividendosEDiluicao:
    """Payout pelos dividendos pagos (fluxo de caixa), proventos do FRE (até 2022) e diluição.

    A diluição é o crescimento composto das ações em circulação ajustadas por desdobramentos,
    grupamentos e bonificações (do FRE; depois de 2022, um salto redondo é tratado como provável
    desdobramento, com aviso), para que trocar 1 ação por 10 não pareça emissão.
    """
    tabela = anuais(dados.contas)
    if tabela.empty:
        return DividendosEDiluicao(pd.DataFrame(), None, 0)
    lucro = _coluna_anual(tabela, "lucro_controladores")
    if lucro.isna().all():
        lucro = _coluna_anual(tabela, "lucro_liquido")
    pagos = _coluna_anual(tabela, "dividendos_pagos").abs()
    acoes = _coluna_anual(tabela, "acoes_total") - _coluna_anual(
        tabela, "acoes_tesouraria"
    ).fillna(0)
    fatores, avisos = _fatores_por_ano(acoes, eventos)
    sem_evento = _saltos_sem_evento(acoes, fatores)
    historico = pd.DataFrame(
        {
            "acoes": acoes,
            "acoes_ajustadas": _ajustadas(acoes, fatores),
            "dividendos_pagos": pagos,
            "lucro": lucro,
            "payout_caixa": pagos / lucro.where(lucro > 0),
        }
    )
    por_acao = historico["acoes_ajustadas"].where(historico["acoes_ajustadas"] > 0)
    historico["dividendo_por_acao"] = pagos / por_acao
    if proventos is not None and not proventos.empty:
        do_fre = _proventos_por_ano(proventos)
        historico["dividendo_fre"] = do_fre["dividendo_total"].reindex(historico.index)
        historico["payout_fre"] = do_fre["payout"].reindex(historico.index)
        for coluna in (
            "dividendos",
            "jcp",
        ):  # o que foi dividendo e o que foi JCP (até 2022)
            if coluna in do_fre:
                fre = do_fre[coluna].reindex(historico.index)
                historico[f"{coluna}_fre_por_acao"] = fre / por_acao
    ajustadas = historico["acoes_ajustadas"].dropna()
    ajustadas = ajustadas[ajustadas > 0]
    diluicao = (
        float(
            (ajustadas.iloc[-1] / ajustadas.iloc[0])
            ** (1 / (ajustadas.index[-1] - ajustadas.index[0]))
            - 1
        )
        if len(ajustadas) >= 2 and not sem_evento
        else None
    )
    return DividendosEDiluicao(
        historico,
        diluicao,
        int((pagos > 0).sum()),
        [*avisos, *sem_evento],
        bool(sem_evento),
    )


def _crescimento_do_dividendo(d: DividendosEDiluicao) -> Indicador:
    anos = ANOS_DO_CRESCIMENTO_DO_DIVIDENDO
    chave, nome = "crescimento_do_dividendo", "Crescimento do dividendo por ação"
    dpa = d.historico.get("dividendo_por_acao")
    ultimo = int(d.historico.index.max()) if dpa is not None else 0
    if dpa is None or (ultimo - anos) not in dpa.index:
        falta = (
            f"O crescimento de {anos} anos pede {anos + 1} exercícios seguidos com DFP."
        )
        return _indicador(chave, nome, None, FRACAO, "", falta)
    inicio, fim = dpa[ultimo - anos], dpa[ultimo]
    motivo = (
        "As ações mudaram sem evento conhecido: o dividendo por ação de antes pode estar errado."
        if d.acoes_sem_evento
        else "Sem dividendo pago no começo ou no fim: crescimento composto não tem sentido."
        if pd.isna(inicio) or pd.isna(fim) or inicio <= 0 or fim <= 0
        else ""
    )
    valor = None if motivo else float((fim / inicio) ** (1 / anos) - 1)
    base = f"DFP de {ultimo - anos} e de {ultimo}"
    return _indicador(chave, nome, valor, FRACAO, base, motivo)


def indicadores_dos_dividendos(d: DividendosEDiluicao) -> dict[str, Indicador]:
    """Dividendo por ação e payout do último exercício e o crescimento do dividendo por ação."""
    dpa, payout, base = float("nan"), float("nan"), ""
    if not d.historico.empty:
        ultimo = int(d.historico.index.max())
        linha, base = d.historico.loc[ultimo], f"DFP de {ultimo}"
        dpa, payout = linha["dividendo_por_acao"], linha["payout_caixa"]
    sem_dfp = "" if base else "Sem DFP guardada."
    sem_dpa = sem_dfp or (
        "Sem dividendos pagos ou sem ações no exercício." if pd.isna(dpa) else ""
    )
    sem_payout = sem_dfp or (
        "Sem lucro positivo no exercício." if pd.isna(payout) else ""
    )
    lista = [
        _indicador("dividendo_por_acao", "Dividendo por ação", None if sem_dpa else float(dpa),
                   REAIS_POR_ACAO, base, sem_dpa),
        _indicador("payout", "Payout (pago sobre o lucro)",
                   None if sem_payout else float(payout), FRACAO, base, sem_payout),
        _crescimento_do_dividendo(d),
    ]  # fmt: skip
    return {i.chave: i for i in lista}


# --- ações por espécie (ON e PN), para a ficha técnica ---------------------------------------------
@dataclass(frozen=True)
class AcoesPorEspecie:
    total: Indicador  # em circulação (total − tesouraria), com a correção de milhares da tela
    ordinarias: float | None = None
    preferenciais: float | None = None
    nota: str = ""  # quando a quantidade veio em milhares e foi corrigida


def acoes_por_especie(dados: DadosDaEmpresa) -> AcoesPorEspecie:
    """As ações em circulação do balanço mais recente, e as ON e as PN quando o documento as traz."""
    saldo, data, _ = balanco_mais_recente(dados.contas)
    base = f"balanço de {_data(data)}" if data else ""
    acoes, nota, motivo = acoes_em_circulacao(saldo, dados.contas)
    total = _indicador(
        "acoes_em_circulacao", "Ações em circulação", acoes, ACOES, base, motivo
    )
    if acoes is None:
        return AcoesPorEspecie(total, nota=nota)
    # o mesmo fator da tela: 1, ou mil quando a CVM recebeu a quantidade em milhares
    fator = acoes / (saldo["acoes_total"] - saldo.get("acoes_tesouraria", 0.0))

    def especie(conta: str) -> float | None:
        if conta not in saldo:
            return None
        return (saldo[conta] - saldo.get(f"{conta}_tesouraria", 0.0)) * fator

    return AcoesPorEspecie(
        total, especie("acoes_ordinarias"), especie("acoes_preferenciais"), nota
    )
