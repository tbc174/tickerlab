"""Pool de recebíveis: concentração e vintages a partir de um tape (protótipo D, parte 2, B-11).

O `ReceivablePool` do `data_model.md` em tipos simples (`como_dict` dá JSON). Parte de um tape que o
validador (`tape.py`) já olhou. O pool **não conserta nada**: as linhas com achado de gravidade `erro`
ficam de fora da conta e aparecem em `validacao` e em `linhas_excluidas`; a linha só com aviso
(CNPJ de sacado inválido) entra. Dinheiro em centavos inteiros; razões como fração entre 0 e 1.

- **Concentração**: parte do **saldo em aberto** que está nos N maiores sacados (ou cedentes), N = 1, 5 e 10.
  Com menos de N contrapartes, a parte é 1. Saldo total zero: tudo 0.
- **Vintage**: a safra é o mês da emissão. Um recebível entra em inadimplência `ATRASO_DIAS` dias depois do
  vencimento, se ainda tem saldo na data de corte. A inadimplência acumulada da safra no mês M é a soma do
  saldo dos que já tinham entrado até o fim de M (no máximo a data de corte), dividida pela face da safra.
  Nunca cai de um mês para o seguinte e nunca olha depois do corte.

Limite honesto: o tape é uma foto na data de corte. Quem entrou em atraso e pagou depois some da conta (o
saldo hoje é zero), e quem pagou parte conta só o saldo que sobrou. A inadimplência aqui é piso, não o
histórico verdadeiro; o histórico mês a mês pede os tapes mensais (B-14 e B-15).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from src.rastro import DocumentoUsado, Rastro, datas_em_texto
from src.securitizacao.tape import (
    ERRO,
    achado_em_dicionario,
    hash_do_tape,
    validar_tape,
)

VERSAO_DO_CALCULO = "pool 1"
FONTE_DO_TAPE = "tape"
MOEDA = "BRL"
ATRASO_DIAS = 90
TAMANHOS_DO_TOPO = (1, 5, 10)
SUJEITOS = ("sacado", "cedente")
TAMANHO_DO_ID = 16  # caracteres do hash que viram o id do pool
CASAS_DA_RAZAO = 10


@dataclass(frozen=True)
class NumeroDoPool:
    """Uma razão do pool com o rastro de como saiu."""

    chave: str
    valor: float
    rastro: Rastro


@dataclass(frozen=True)
class Vintage:
    """Inadimplência acumulada de uma safra, mês a mês, a partir do mês da emissão."""

    safra: str  # "AAAA-MM"
    face: int  # centavos emitidos na safra
    meses: tuple[str, ...]  # "AAAA-MM", do mês da safra até o mês do corte
    inadimplencia_acumulada: tuple[float, ...]  # fração da face, um valor por mês
    rastro: Rastro


@dataclass(frozen=True)
class ReceivablePool:
    pool_id: str
    data_de_corte: date
    moeda: str
    n_recebiveis: int
    saldo: int
    linhas_excluidas: tuple[int, ...]
    validacao: tuple[dict[str, Any], ...]
    concentracao: dict[str, NumeroDoPool]
    vintages: tuple[Vintage, ...]
    hash_do_tape: str
    rastro: Rastro

    def como_dict(self) -> dict[str, Any]:
        """Para a API: tipos simples, datas em texto ISO."""
        return datas_em_texto(_em_dicionario(self))  # type: ignore[return-value]


def _em_dicionario(objeto: object) -> object:
    if hasattr(objeto, "__dataclass_fields__"):
        return {
            campo: _em_dicionario(getattr(objeto, campo))
            for campo in objeto.__dataclass_fields__  # type: ignore[attr-defined]
        }
    if isinstance(objeto, dict):
        return {k: _em_dicionario(v) for k, v in objeto.items()}
    if isinstance(objeto, (list, tuple)):
        return [_em_dicionario(v) for v in objeto]
    return objeto


def _razao(parte: int, total: int) -> float:
    return round(parte / total, CASAS_DA_RAZAO) if total else 0.0


def _rastro(tape: dict[str, Any], formula: str, corte: date) -> Rastro:
    documento = DocumentoUsado(
        f"tape de {len(tape['recebiveis'])} recebíveis, hash {hash_do_tape(tape)[:TAMANHO_DO_ID]}",
        corte,
    )
    return Rastro(formula, VERSAO_DO_CALCULO, FONTE_DO_TAPE, corte, (documento,))


def _linhas_com_erro(achados: list) -> set[int]:
    return {a.linha for a in achados if a.gravidade == ERRO and a.linha > 0}


def _recebiveis_aceitos(tape: dict[str, Any], excluidas: set[int]) -> list[dict]:
    return [
        r
        for linha, r in enumerate(tape["recebiveis"], start=1)
        if linha not in excluidas
    ]


# --- concentração ------------------------------------------------------------------------------


def _saldo_por_contraparte(recebiveis: list[dict], campo: str) -> list[int]:
    """Saldos por CNPJ ou id externo (sem diferença de maiúscula), do maior para o menor."""
    soma: dict[str, int] = defaultdict(int)
    for r in recebiveis:
        soma[r[campo].strip().upper()] += r["saldo"]
    return sorted(soma.values(), reverse=True)


def _concentracao(
    recebiveis: list[dict], saldo: int, tape: dict[str, Any], corte: date
) -> dict[str, NumeroDoPool]:
    numeros = {}
    for sujeito in SUJEITOS:
        saldos = _saldo_por_contraparte(recebiveis, f"{sujeito}_cnpj")
        for n in TAMANHOS_DO_TOPO:
            chave = f"{sujeito}_top{n}"
            formula = f"saldo em aberto dos {n} maiores {sujeito}s (por CNPJ ou id externo) / saldo em aberto do pool"
            numeros[chave] = NumeroDoPool(
                chave, _razao(sum(saldos[:n]), saldo), _rastro(tape, formula, corte)
            )
    return numeros


# --- vintages ----------------------------------------------------------------------------------


def _mes(dia: date) -> str:
    return f"{dia.year:04d}-{dia.month:02d}"


def _fim_do_mes(ano: int, mes: int) -> date:
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def _meses_ate(inicio: date, corte: date) -> list[date]:
    """O último dia de cada mês do mês de `inicio` ao do `corte`, com o último limitado ao corte."""
    fins = []
    ano, mes = inicio.year, inicio.month
    while (ano, mes) <= (corte.year, corte.month):
        fins.append(min(_fim_do_mes(ano, mes), corte))
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return fins


def _entrada_em_inadimplencia(r: dict) -> date:
    return date.fromisoformat(r["vencimento"]) + timedelta(days=ATRASO_DIAS)


def _vintage(
    safra: str, do_mes: list[dict], tape: dict[str, Any], corte: date
) -> Vintage:
    face = sum(r["valor_face"] for r in do_mes)
    inicio = date.fromisoformat(do_mes[0]["emissao"]).replace(day=1)
    fins = _meses_ate(inicio, corte)
    em_atraso = [
        (_entrada_em_inadimplencia(r), r["saldo"]) for r in do_mes if r["saldo"] > 0
    ]
    razoes = tuple(
        _razao(sum(s for entrada, s in em_atraso if entrada <= fim), face)
        for fim in fins
    )
    formula = (
        f"soma do saldo dos recebíveis da safra com vencimento + {ATRASO_DIAS} dias <= fim do mês "
        "(no máximo o corte) / face da safra"
    )
    return Vintage(
        safra, face, tuple(_mes(f) for f in fins), razoes, _rastro(tape, formula, corte)
    )


def _vintages(
    recebiveis: list[dict], tape: dict[str, Any], corte: date
) -> tuple[Vintage, ...]:
    por_safra: dict[str, list[dict]] = defaultdict(list)
    for r in recebiveis:
        por_safra[r["emissao"][:7]].append(r)
    return tuple(
        _vintage(safra, por_safra[safra], tape, corte) for safra in sorted(por_safra)
    )


# --- o pool ------------------------------------------------------------------------------------


def montar_pool(tape: dict[str, Any]) -> ReceivablePool:
    """O pool de um tape: validação, concentração e vintages. Mesmo tape, mesmo pool.

    Um tape cujo esquema inteiro está quebrado (sem data de corte ou sem lista) não vira pool:
    `ValueError` com os achados, porque não há o que contar.
    """
    achados = validar_tape(tape)
    if any(a.linha == 0 for a in achados):
        raise ValueError("tape sem estrutura: " + "; ".join(a.porque for a in achados))
    corte = date.fromisoformat(tape["data_de_corte"])
    excluidas = _linhas_com_erro(achados)
    aceitos = _recebiveis_aceitos(tape, excluidas)
    saldo = sum(r["saldo"] for r in aceitos)
    hash_tape = hash_do_tape(tape)
    return ReceivablePool(
        pool_id=hash_tape[:TAMANHO_DO_ID],
        data_de_corte=corte,
        moeda=MOEDA,
        n_recebiveis=len(aceitos),
        saldo=saldo,
        linhas_excluidas=tuple(sorted(excluidas)),
        validacao=tuple(achado_em_dicionario(a) for a in achados),
        concentracao=_concentracao(aceitos, saldo, tape, corte),
        vintages=_vintages(aceitos, tape, corte),
        hash_do_tape=hash_tape,
        rastro=_rastro(
            tape, "soma do saldo dos recebíveis sem erro de validação", corte
        ),
    )
