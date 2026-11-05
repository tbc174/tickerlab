"""Funções puras de `src/edicao.py`: data da coleta e frase dos detentores."""

from datetime import UTC, date, datetime, timedelta, timezone

import pandas as pd

from src.edicao import _frase_do_detentor, quando_foi_coletado

PAR = (date(2026, 9, 1), date(2026, 8, 1))


def _linha(variacao: float, vendidos: int = 0) -> pd.Series:
    return pd.Series({"detentores": 12, "variacao": variacao, "vendidos": vendidos})


def test_sem_momento_diz_que_ainda_nao_foi_coletado():
    assert quando_foi_coletado(None) == "ainda não coletado"


def test_momento_sem_fuso_e_lido_como_utc():
    momento = datetime(2026, 11, 5, 15, 30)
    assert quando_foi_coletado(momento) == "coletado em 05/11/2026 às 12:30"


def test_momento_com_fuso_e_convertido_para_brasilia():
    momento = datetime(2026, 11, 5, 15, 30, tzinfo=timezone(timedelta(hours=-8)))
    assert quando_foi_coletado(momento) == "coletado em 05/11/2026 às 20:30"
    assert quando_foi_coletado(momento.astimezone(UTC)) == (
        "coletado em 05/11/2026 às 20:30"
    )


def test_frase_com_variacao_e_vendidos_da_cvm():
    frase = _frase_do_detentor("PETR4", _linha(3, 2), "fundos", PAR, True, 40)
    assert frase == (
        "PETR4: 12 fundos com a ação em 09/2026, de 40 que informaram "
        "(+3 desde 08/2026); 2 vendidos."
    )


def test_frase_sem_variacao_omite_o_parenteses():
    frase = _frase_do_detentor("PETR4", _linha(float("nan")), "fundos", PAR, True, 40)
    assert frase == "PETR4: 12 fundos com a ação em 09/2026, de 40 que informaram."


def test_frase_sem_vendidos_nao_cita_vendidos():
    frase = _frase_do_detentor("VALE3", _linha(-1, 0), "fundos", PAR, True, 40)
    assert "vendidos" not in frase
    assert "(-1 desde 08/2026)" in frase


def test_vendidos_so_aparecem_quando_a_fonte_e_a_da_cvm():
    frase = _frase_do_detentor("AAPL", _linha(1, 5), "gestores", PAR, False, 30)
    assert "vendidos" not in frase
    assert frase.startswith("AAPL: 12 gestores com a ação em 09/2026")
