"""As séries que o código calcula para os gráficos (emenda 1 do plano de 23/10/2026).

O histórico da ficha traz as contas cruas, ano a ano, em reais; o modelo não faz conta. Aqui saem as
séries prontas (margens, retorno, crescimento, dívida, caixa, prazos, dividendos), cada uma uma
tabela `series.<chave>` com o ano no eixo e as células escritas como no resto da ficha ("13,8%",
"R$ 4,2 bi", "1,60×", "36 dias"). Cada linha cita em `de` as linhas do histórico de onde saiu, e a
porta 1 confere o achado do gráfico contra esses mesmos números.

A conta que não tem de onde sair (conta ausente, divisão por zero, margem sobre prejuízo) fica em
branco; a tabela sem nenhum valor sai. O ano só usa ele mesmo e o anterior: cortar o futuro não muda
nenhuma linha do passado.

As séries entram só no caminho dos gráficos (`ampliar`): o texto da análise continua conferido
contra a entrada original, e o hash dela não muda.
"""

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src import fundamentos
from src.fundamentalista import DIAS, DIAS_NO_ANO
from src.relatorio_empresa import divida_liquida, escrever

SECAO = "series"
NOME_DA_SECAO = "Séries calculadas pelo código"
EIXO = "Ano"
_HISTORICO = "historico.contas."

Contas = dict[str, Any]
# a conta de um ano: as contas do ano e as do ano anterior (None no primeiro ano ou com buraco)
Calculo = Callable[[Contas, Contas | None], float | None]


@dataclass(frozen=True)
class _Serie:
    coluna: str
    calcular: Calculo


@dataclass(frozen=True)
class _Tabela:
    chave: str
    nome: str
    unidade: str  # uma unidade por tabela: o gráfico não mistura reais com percentuais
    series: tuple[_Serie, ...]
    usa_o_anterior: bool = False  # a linha cita também o ano anterior


def _conta(contas: Contas | None, nome: str) -> float | None:
    if contas is None:
        return None
    valor = contas.get(nome)
    if (
        not isinstance(valor, int | float)
        or isinstance(valor, bool)
        or math.isnan(valor)
    ):
        return None
    return float(valor)


def _razao(cima: float | None, baixo: float | None) -> float | None:
    """`cima / baixo` só com a base positiva: margem sobre receita zero ou prejuízo não se lê."""
    if cima is None or baixo is None or baixo <= 0:
        return None
    return cima / baixo


def _sobre(nome: str, base: str, absoluto: bool = False) -> Calculo:
    def calcular(ano: Contas, _: Contas | None) -> float | None:
        valor = _conta(ano, nome)
        if absoluto and valor is not None:
            valor = abs(valor)
        return _razao(valor, _conta(ano, base))

    return calcular


def _absoluto(nome: str) -> Calculo:
    def calcular(ano: Contas, _: Contas | None) -> float | None:
        valor = _conta(ano, nome)
        return None if valor is None else abs(valor)

    return calcular


def _propria(nome: str) -> Calculo:
    return lambda ano, _: _conta(ano, nome)


def _crescimento(nome: str) -> Calculo:
    def calcular(ano: Contas, anterior: Contas | None) -> float | None:
        razao = _razao(_conta(ano, nome), _conta(anterior, nome))
        return None if razao is None else razao - 1

    return calcular


def _ebitda(ano: Contas) -> float | None:
    ebit, depreciacao = _conta(ano, "ebit"), _conta(ano, "depreciacao")
    return None if ebit is None or depreciacao is None else ebit + depreciacao


def _divida(ano: Contas, _: Contas | None) -> float | None:
    return divida_liquida(ano)


def _divida_sobre_ebitda(ano: Contas, _: Contas | None) -> float | None:
    return _razao(divida_liquida(ano), _ebitda(ano))


def _roe(ano: Contas, _: Contas | None) -> float | None:
    """Lucro dos controladores sobre o patrimônio deles (sem a parte dos minoritários)."""
    patrimonio = _conta(ano, "patrimonio_liquido")
    if patrimonio is None:
        return None
    return _razao(
        _conta(ano, "lucro_controladores"),
        patrimonio - (_conta(ano, "minoritarios") or 0.0),
    )


def _caixa_livre(ano: Contas, _: Contas | None) -> float | None:
    fco, capex = _conta(ano, "fco"), _conta(ano, "capex")
    return None if fco is None or capex is None else fco - abs(capex)


def _prazo(nome: str, base: str) -> Calculo:
    """Dias de receita (ou de custo) parados na conta: saldo sobre o fluxo do ano × 365."""
    fracao = _sobre(nome, base)

    def calcular(ano: Contas, anterior: Contas | None) -> float | None:
        custo = _conta(ano, base)
        com_base_positiva = {**ano, base: abs(custo)} if custo is not None else ano
        valor = fracao(com_base_positiva, anterior)
        return None if valor is None else valor * DIAS_NO_ANO

    return calcular


def _payout(ano: Contas, _: Contas | None) -> float | None:
    dividendos = _conta(ano, "dividendos_pagos")
    if dividendos is None:
        return None
    return _razao(abs(dividendos), _conta(ano, "lucro_controladores"))


def _conversao(ano: Contas, _: Contas | None) -> float | None:
    return _razao(_conta(ano, "fco"), _conta(ano, "lucro_liquido"))


R, F, X = fundamentos.REAIS, fundamentos.FRACAO, fundamentos.VEZES

# a ordem é a do relatório: resultado, retorno, crescimento, dívida, caixa, giro, dividendos
CATALOGO: tuple[_Tabela, ...] = (
    _Tabela("margens", "Margens ano a ano", F, (
        _Serie("Margem bruta", _sobre("resultado_bruto", "receita")),
        _Serie("Margem EBIT", _sobre("ebit", "receita")),
        _Serie("Margem líquida", _sobre("lucro_liquido", "receita")),
    )),
    _Tabela("receita_e_lucro", "Receita, EBITDA e lucro ano a ano", R, (
        _Serie("Receita", _propria("receita")),
        _Serie("EBITDA", lambda ano, _: _ebitda(ano)),
        _Serie("Lucro líquido", _propria("lucro_liquido")),
    )),
    _Tabela("retorno", "Retorno ano a ano (sobre o balanço do fim do ano)", F, (
        _Serie("ROE", _roe),
        _Serie("ROA", _sobre("lucro_liquido", "ativo_total")),
    )),
    _Tabela("crescimento", "Crescimento sobre o ano anterior", F, (
        _Serie("Crescimento da receita", _crescimento("receita")),
        _Serie("Crescimento do lucro", _crescimento("lucro_liquido")),
    ), usa_o_anterior=True),
    _Tabela("despesas", "Despesas sobre a receita", F, (
        _Serie("Despesas com vendas", _sobre("despesas_com_vendas", "receita", absoluto=True)),
        _Serie("Despesas administrativas", _sobre("despesas_administrativas", "receita", absoluto=True)),
        _Serie("Despesas financeiras", _sobre("despesas_financeiras", "receita", absoluto=True)),
    )),
    _Tabela("divida", "Dívida líquida no fim de cada ano", R, (
        _Serie("Dívida líquida", _divida),
    )),
    _Tabela("alavancagem", "Dívida líquida sobre o EBITDA", X, (
        _Serie("Dívida líquida / EBITDA", _divida_sobre_ebitda),
    )),
    _Tabela("estrutura", "Patrimônio sobre o ativo", F, (
        _Serie("Patrimônio sobre o ativo", _sobre("patrimonio_liquido", "ativo_total")),
    )),
    _Tabela("liquidez", "Liquidez corrente", X, (
        _Serie("Liquidez corrente", _sobre("ativo_circulante", "passivo_circulante")),
    )),
    _Tabela("caixa", "Caixa operacional, investimento e caixa livre", R, (
        _Serie("Caixa operacional", _propria("fco")),
        _Serie("Investimento (capex)", _absoluto("capex")),
        _Serie("Caixa livre", _caixa_livre),
    )),
    _Tabela("conversao", "Caixa operacional sobre o lucro", X, (
        _Serie("Caixa operacional / lucro", _conversao),
    )),
    _Tabela("investimento", "Capex sobre a depreciação", X, (
        _Serie("Capex / depreciação", _sobre("capex", "depreciacao", absoluto=True)),
    )),
    _Tabela("prazos", "Prazos do capital de giro", DIAS, (
        _Serie("Prazo de recebimento", _prazo("contas_a_receber", "receita")),
        _Serie("Prazo de estoque", _prazo("estoques", "custo")),
        _Serie("Prazo de fornecedores", _prazo("fornecedores", "custo")),
    )),
    _Tabela("giro", "Giro do ativo", X, (
        _Serie("Giro do ativo", _sobre("receita", "ativo_total")),
    )),
    _Tabela("dividendos", "Dividendos pagos ano a ano", R, (
        _Serie("Dividendos pagos", _absoluto("dividendos_pagos")),
    )),
    _Tabela("payout", "Payout (dividendos pagos sobre o lucro)", F, (
        _Serie("Payout", _payout),
    )),
    _Tabela("lpa", "Lucro por ação ano a ano", fundamentos.REAIS_POR_ACAO, (
        _Serie("LPA", _propria("lpa_basico")),
    )),
)  # fmt: skip


@dataclass(frozen=True)
class _Ano:
    id: str
    ano: int
    contas: Contas
    so_pro: bool


def _anos_do_historico(entrada: dict[str, Any]) -> list[_Ano]:
    anos = [
        _Ano(li["id"], int(li["celulas"]["ano"]), li["celulas"], bool(li.get("so_pro")))
        for li in entrada["linhas"]
        if li["id"].startswith(_HISTORICO) and li.get("tipo") == "linha"
    ]
    return sorted(anos, key=lambda a: a.ano)


def _linhas_da_tabela(tabela: _Tabela, anos: list[_Ano]) -> list[dict[str, Any]]:
    linhas: list[dict[str, Any]] = []
    for i, atual in enumerate(anos):
        anterior = anos[i - 1] if i and anos[i - 1].ano == atual.ano - 1 else None
        celulas: dict[str, Any] = {EIXO: atual.ano}
        for serie in tabela.series:
            valor = serie.calcular(atual.contas, anterior.contas if anterior else None)
            if valor is not None:
                celulas[serie.coluna] = escrever(valor, tabela.unidade)
        if len(celulas) == 1:
            continue
        fontes = [anterior, atual] if tabela.usa_o_anterior and anterior else [atual]
        linhas.append(
            {
                "secao": SECAO,
                "id": f"{SECAO}.{tabela.chave}.{len(linhas)}",
                "tipo": "linha",
                "tabela": tabela.nome,
                "celulas": celulas,
                "de": [a.id for a in fontes],
                "so_pro": any(a.so_pro for a in fontes),
            }
        )
    return linhas


def linhas_das_series(entrada: dict[str, Any]) -> list[dict[str, Any]]:
    """As linhas de todas as séries que o histórico desta entrada sustenta, na ordem do catálogo."""
    anos = _anos_do_historico(entrada)
    return [linha for tabela in CATALOGO for linha in _linhas_da_tabela(tabela, anos)]


def ampliar(entrada: dict[str, Any]) -> dict[str, Any]:
    """A entrada dos gráficos: a mesma, mais a seção das séries (a original fica como estava)."""
    ampliada = copy.deepcopy(entrada)
    novas = linhas_das_series(entrada)
    if novas:
        ampliada["secoes"] = {**ampliada["secoes"], SECAO: NOME_DA_SECAO}
        ampliada["linhas"] = [*ampliada["linhas"], *novas]
    return ampliada
