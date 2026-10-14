"""Calendário de pregões da NYSE (bolsa de Nova York): quais dias úteis não têm pregão.

Os feriados saem das regras da própria bolsa, então valem para qualquer ano sem baixar nada:

- **Datas fixas** (Ano-Novo, Juneteenth, Independence Day, Natal): se caem no sábado, a folga é na
  sexta; no domingo, na segunda. **Exceção:** Ano-Novo no sábado não dá folga na sexta (a NYSE não
  fecha no último dia do ano; em 31/12/2021 houve pregão).
- **Datas móveis:** 3ª segunda de janeiro (Martin Luther King Jr.) e de fevereiro (Washington's
  Birthday), Sexta-feira Santa, última segunda de maio (Memorial Day), 1ª segunda de setembro
  (Labor Day) e 4ª quinta de novembro (Thanksgiving).
- **Juneteenth** (19/06) só a partir de 2022.
- **Fechamentos extras** (luto nacional, furacão) não seguem regra: ficam em `FECHAMENTOS_EXTRAS`.
  Um fechamento novo aparece como falha do coletor da IEX (404 num dia que seria de pregão); aí
  é só acrescentar a data aqui.

Dias de pregão mais curto (véspera de Natal, dia seguinte ao Thanksgiving) contam como pregão.
"""

from datetime import date, timedelta
from functools import cache

FECHAMENTOS_EXTRAS = {
    date(2018, 12, 5): "Luto nacional (George H. W. Bush)",
    date(2025, 1, 9): "Luto nacional (Jimmy Carter)",
}


def _pascoa(ano: int) -> date:
    """Domingo de Páscoa no calendário gregoriano (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mes, dia = divmod(h + m - 7 * n + 114, 31)
    return date(ano, mes, dia + 1)


def _enesimo_dia_da_semana(ano: int, mes: int, dia_da_semana: int, n: int) -> date:
    """O `n`-ésimo `dia_da_semana` (0 = segunda) do mês; `n = -1` é o último."""
    if n > 0:
        primeiro = date(ano, mes, 1)
        return primeiro + timedelta(
            days=(dia_da_semana - primeiro.weekday()) % 7 + 7 * (n - 1)
        )
    ultimo = date(ano + mes // 12, mes % 12 + 1, 1) - timedelta(days=1)
    return ultimo - timedelta(days=(ultimo.weekday() - dia_da_semana) % 7)


def _folga(dia: date) -> date:
    """Data fixa no fim de semana: sábado folga na sexta, domingo na segunda."""
    if dia.weekday() == 5:
        return dia - timedelta(days=1)
    if dia.weekday() == 6:
        return dia + timedelta(days=1)
    return dia


@cache
def feriados(ano: int) -> dict[date, str]:
    """Os dias úteis de `ano` sem pregão por feriado, com o nome de cada um."""
    lista = {
        _enesimo_dia_da_semana(ano, 1, 0, 3): "Martin Luther King Jr. Day",
        _enesimo_dia_da_semana(ano, 2, 0, 3): "Washington's Birthday",
        _pascoa(ano) - timedelta(days=2): "Sexta-feira Santa",
        _enesimo_dia_da_semana(ano, 5, 0, -1): "Memorial Day",
        _folga(date(ano, 7, 4)): "Independence Day",
        _enesimo_dia_da_semana(ano, 9, 0, 1): "Labor Day",
        _enesimo_dia_da_semana(ano, 11, 3, 4): "Thanksgiving",
        _folga(date(ano, 12, 25)): "Natal",
    }
    if (
        date(ano, 1, 1).weekday() != 5
    ):  # no sábado não há folga (seria em 31/12 do ano anterior)
        lista[_folga(date(ano, 1, 1))] = "Ano-Novo"
    if ano >= 2022:
        lista[_folga(date(ano, 6, 19))] = "Juneteenth"
    lista.update({d: nome for d, nome in FECHAMENTOS_EXTRAS.items() if d.year == ano})
    return dict(sorted(lista.items()))


def eh_pregao(dia: date) -> bool:
    """True se a NYSE abre em `dia` (de segunda a sexta e fora dos feriados)."""
    return dia.weekday() < 5 and dia not in feriados(dia.year)
