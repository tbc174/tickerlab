"""ABS-EE da SEC (crédito auto) em tape: adaptador de entrada do validador (protótipo D, B-14).

O **ABS-EE** é o arquivo de ativos que o emissor de ABS dos EUA entrega à SEC todo mês (Reg AB, Item 1111):
um XML com uma linha por financiamento, público (fonte já licenciada, `licencas-por-fonte.md`). Este módulo
só **traduz** esse XML para o tape da B-10 (`tape.py`); o validador e o pool não mudam e não sabem de onde
o tape veio.

Como cada campo vira campo do tape (e o que se perde):

- `recebivel_id` = `assetNumber` (o emissor já o entrega em hash: o devedor não é identificável).
- `cedente_cnpj` = `originatorName` e `sacado_cnpj` = `assetNumber`: **o ABS-EE não tem CNPJ**, então o
  texto do originador e o hash do devedor ocupam o lugar, marcados como `externo` (`cedente_tipo_id` e
  `sacado_tipo_id`). O validador confere o id externo pela regra dele (texto, tamanho, sem quebra de linha) e
  nunca o trata como CNPJ; não se inventa CNPJ para calar o achado.
- `emissao` e `vencimento`: o XML traz só mês e ano (`10/2020`); entra o **último dia do mês**.
- `valor_face` = `originalLoanAmount` e `saldo` = `reportingPeriodActualEndBalanceAmount`, em centavos.
  `valor_pago` = face - saldo (o XML não traz o acumulado pago); então a regra T06 não pega nada aqui e
  um saldo maior que a face (juros capitalizados, renegociação) aparece como T01 de `valor_pago` negativo.
- `data_de_corte` = `reportingPeriodEndingDate` (MM-DD-AAAA). Atraso (`currentDelinquencyStatus`) e demais
  campos ficam de fora: o tape da B-10 não os tem.

Só lê o **esquema de crédito auto** (`.../absee/autoloan/assetdata`); outro esquema (CMBS, cartão, etc.)
levanta `ValueError`, porque campo trocado de lugar em silêncio seria tape errado.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import IO, Any
from xml.etree.ElementTree import Element  # só o tipo; a leitura é do defusedxml

from defusedxml import ElementTree

from src.securitizacao.tape import TIPO_EXTERNO

ESQUEMA_AUTO = "http://www.sec.gov/edgar/document/absee/autoloan/assetdata"
CENTAVOS = Decimal(100)

MESES_DO_XML = 12


def _dinheiro_em_centavos(texto: str | None) -> int | None:
    if texto is None or not texto.strip():
        return None
    try:
        return int((Decimal(texto.strip()) * CENTAVOS).to_integral_value(ROUND_HALF_UP))
    except ArithmeticError:
        return None


def _ultimo_dia_do_mes(texto: str | None) -> str | None:
    """`MM/AAAA` vira o último dia do mês em ISO; texto ilegível vira None (o validador acusa)."""
    try:
        mes, ano = (texto or "").strip().split("/")
        mes_n, ano_n = int(mes), int(ano)
        if not 1 <= mes_n <= MESES_DO_XML:
            return None
        return date(ano_n, mes_n, calendar.monthrange(ano_n, mes_n)[1]).isoformat()
    except ValueError:
        return None


def _data_do_periodo(texto: str | None) -> str | None:
    """`MM-DD-AAAA` vira ISO."""
    try:
        mes, dia, ano = (texto or "").strip().split("-")
        return date(int(ano), int(mes), int(dia)).isoformat()
    except ValueError:
        return None


def _campo(ativo: Element, nome: str) -> str | None:
    elemento = ativo.find(f"{{{ESQUEMA_AUTO}}}{nome}")
    return None if elemento is None else elemento.text


def _recebivel(ativo: Element) -> dict[str, Any]:
    face = _dinheiro_em_centavos(_campo(ativo, "originalLoanAmount"))
    saldo = _dinheiro_em_centavos(
        _campo(ativo, "reportingPeriodActualEndBalanceAmount")
    )
    return {
        "recebivel_id": _campo(ativo, "assetNumber"),
        "cedente_cnpj": _campo(ativo, "originatorName"),
        "sacado_cnpj": _campo(ativo, "assetNumber"),
        "cedente_tipo_id": TIPO_EXTERNO,
        "sacado_tipo_id": TIPO_EXTERNO,
        "emissao": _ultimo_dia_do_mes(_campo(ativo, "originationDate")),
        "vencimento": _ultimo_dia_do_mes(_campo(ativo, "loanMaturityDate")),
        "valor_face": face,
        "valor_pago": None if face is None or saldo is None else face - saldo,
        "saldo": saldo,
    }


def _ativos(arquivo: IO[bytes]) -> Iterator[Element]:
    """Os `<assets>` um a um, liberando a memória de cada (o arquivo do emissor chega a 100 MB)."""
    for _, elemento in ElementTree.iterparse(arquivo, events=("end",)):
        if elemento.tag == f"{{{ESQUEMA_AUTO}}}assets":
            yield elemento
            elemento.clear()
        elif elemento.tag.startswith("{") and not elemento.tag.startswith(
            f"{{{ESQUEMA_AUTO}}}"
        ):
            raise ValueError(f"esquema de ABS-EE não suportado: {elemento.tag}")


def tape_de_abs_ee(arquivo: IO[bytes], limite: int | None = None) -> dict[str, Any]:
    """O tape de um XML de ativos de ABS-EE (crédito auto). `limite` corta nos primeiros N ativos."""
    recebiveis: list[dict[str, Any]] = []
    cortes: set[str | None] = set()
    for ativo in _ativos(arquivo):
        if limite is not None and len(recebiveis) >= limite:
            break
        recebiveis.append(_recebivel(ativo))
        cortes.add(_data_do_periodo(_campo(ativo, "reportingPeriodEndingDate")))
    if not recebiveis:
        raise ValueError("nenhum ativo de crédito auto no arquivo")
    if len(cortes) != 1 or None in cortes:
        raise ValueError(f"data de corte ausente ou diferente entre ativos: {cortes}")
    return {"data_de_corte": cortes.pop(), "recebiveis": recebiveis}
