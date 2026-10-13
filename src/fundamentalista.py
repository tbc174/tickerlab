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
- **Histórico de até 10 anos** dos DFPs: a tabela, a análise vertical (resultado sobre a receita,
  balanço sobre o ativo), a horizontal (variação de um ano para o outro, só entre anos seguidos), o
  crescimento composto e a consistência. Ano que falta aparece como falta, nunca como zero.

Bancos e seguradoras: "não se aplica" onde o indicador não faz sentido, como na tela.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from src.banco.demonstracoes import DadosDaEmpresa
from src.demonstracoes import EXERCICIO, POSICAO, e_financeira
from src.fundamentos import (
    FRACAO,
    NAO_SE_APLICA_A_FINANCEIRAS,
    REAIS,
    VEZES,
    Indicador,
    anuais,
    balanco_mais_recente,
    doze_meses,
)

DIAS = "dias"
DIAS_NO_ANO = 365
ANOS_DO_HISTORICO = 10
SEM_RECEITA = "Sem receita no período."
SEM_CUSTO = "Sem custo das vendas informado (empresa de serviços ou holding)."
SEM_DESPESA_FINANCEIRA = "Sem despesa financeira no período: não se aplica."


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


def _um_ano_antes(d: date) -> date:
    return d.replace(year=d.year - 1, day=28 if (d.month, d.day) == (2, 29) else d.day)


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
                ("dupont_margem", "Margem líquida (DuPont)", FRACAO),
                ("dupont_giro", "Giro do ativo", VEZES),
                ("dupont_alavancagem", "Alavancagem (ativo / patrimônio)", VEZES),
                ("dupont_roe", "ROE pelo DuPont", FRACAO),
            )
        ]
    margem, giro, alavancagem = lucro / receita, receita / ativo, ativo / pl  # type: ignore[operator]
    return [
        _indicador("dupont_margem", "Margem líquida (DuPont)", margem, FRACAO, base),
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


def historico(contas: pd.DataFrame, anos: int = ANOS_DO_HISTORICO) -> Historico:
    """Os últimos `anos` exercícios (DFP), com vertical, horizontal, crescimento e consistência."""
    tabela = anuais(contas)
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
        _saldos_em(contas, _um_ano_antes(data_do_balanco)) if data_do_balanco else {}
    )
    base_balanco = f"balanço de {_data(data_do_balanco)}" if data_do_balanco else ""
    base = f"{base_12m}; {base_balanco}"
    base_media = (
        f"{base_12m}; saldo médio de {_data(_um_ano_antes(data_do_balanco))} e "
        f"{_data(data_do_balanco)}"
        if anterior and data_do_balanco
        else f"{base_12m}; saldo do fim, em {_data(data_do_balanco)}"
        if data_do_balanco
        else base_12m
    )
    grupos = [_dupont(ttm, saldo, base), _ciclo(ttm, saldo, anterior, base_media)]
    grupos += [_caixa_livre(ttm, base_12m), [_cobertura(ttm, base_12m)]]
    indicadores = [
        i for grupo in grupos for i in (_nao_se_aplica(grupo) if financeira else grupo)
    ]
    return Fundamentalista(
        indicadores={i.chave: i for i in indicadores}, historico=historico(contas)
    )
