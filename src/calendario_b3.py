"""Calendário de pregões da B3 (bolsa de São Paulo): quais dias úteis não têm pregão.

Os feriados saem das regras da bolsa, então valem para qualquer ano sem baixar nada. A B3 não passa
feriado de data fixa para a segunda-feira: se cai no fim de semana, não há folga em dia útil.

- **Datas fixas:** Ano-Novo (01/01), Tiradentes (21/04), Dia do Trabalho (01/05), Independência
  (07/09), Nossa Senhora Aparecida (12/10), Finados (02/11), Proclamação da República (15/11), Natal
  (25/12) e **também 24/12 e 31/12** (a B3 não abre nas vésperas de Natal e de Ano-Novo).
- **Datas móveis (a partir da Páscoa):** segunda e terça de Carnaval (48 e 47 dias antes),
  Sexta-feira Santa (2 dias antes) e Corpus Christi (60 dias depois).
- **Consciência Negra** (20/11) só a partir de 2024, quando virou feriado nacional (Lei 14.759).
- Vale de 2022 em diante. Antes disso a B3 também fechava em 25/01 (aniversário de São Paulo), que
  não está aqui.
- **Fechamentos extras** (luto, evento) não seguem regra: ficam em `FECHAMENTOS_EXTRAS`. Um fechamento
  novo aparece como falha da coleta do boletim (500 num dia sem pregão); aí é só acrescentar a data.
"""

from datetime import date, timedelta
from functools import cache

from src.calendario_nyse import _pascoa

FECHAMENTOS_EXTRAS: dict[date, str] = {}


@cache
def feriados(ano: int) -> dict[date, str]:
    """Os dias úteis de `ano` sem pregão, com o motivo de cada um."""
    pascoa = _pascoa(ano)
    lista = {
        date(ano, 1, 1): "Ano-Novo",
        pascoa - timedelta(days=48): "Carnaval (segunda)",
        pascoa - timedelta(days=47): "Carnaval (terça)",
        pascoa - timedelta(days=2): "Sexta-feira Santa",
        date(ano, 4, 21): "Tiradentes",
        date(ano, 5, 1): "Dia do Trabalho",
        pascoa + timedelta(days=60): "Corpus Christi",
        date(ano, 9, 7): "Independência",
        date(ano, 10, 12): "Nossa Senhora Aparecida",
        date(ano, 11, 2): "Finados",
        date(ano, 11, 15): "Proclamação da República",
        date(ano, 12, 24): "Véspera de Natal",
        date(ano, 12, 25): "Natal",
        date(ano, 12, 31): "Véspera de Ano-Novo",
    }
    if ano >= 2024:
        lista[date(ano, 11, 20)] = "Consciência Negra"
    lista.update({d: nome for d, nome in FECHAMENTOS_EXTRAS.items() if d.year == ano})
    return {d: nome for d, nome in sorted(lista.items()) if d.weekday() < 5}


def eh_pregao(dia: date) -> bool:
    """True se a B3 abre em `dia` (de segunda a sexta e fora dos feriados)."""
    return dia.weekday() < 5 and dia not in feriados(dia.year)
