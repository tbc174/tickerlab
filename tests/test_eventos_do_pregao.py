"""Dia de evento do pregão (plano `2026-10-28-raio-x-todo-dia`, PR 4c).

Data marcada pela fonte oficial (o efeito no mesmo pregão ou no seguinte) ou Ibovespa andando 3% ou
mais fazem do pregão um dia de evento; o resto é dia comum.
"""

from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pytest

from src import eventos_do_pregao as ev
from src.calendario_b3 import eh_pregao

COPOM = ev.EventoMarcado(
    date(2026, 11, 4), "Decisão do Copom", ev.DEPOIS_DO_FECHAMENTO, "https://bcb"
)
IPCA = ev.EventoMarcado(
    date(2026, 11, 12), "IPCA", ev.ANTES_DO_FECHAMENTO, "https://ibge"
)
CALENDARIO = [COPOM, IPCA]
# fontes oficiais de cada evento do calendário
DOMINIOS_OFICIAIS = {
    "www.bcb.gov.br",
    "www.federalreserve.gov",
    "www.ibge.gov.br",
    "www.bls.gov",
}


def test_copom_e_evento_no_pregao_seguinte() -> None:
    """O comunicado sai depois do fechamento: o pregão da decisão ainda não o viu."""
    assert (
        ev.motivo_do_evento(date(2026, 11, 4), date(2026, 11, 3), 0.001, CALENDARIO)
        is None
    )
    motivo = ev.motivo_do_evento(
        date(2026, 11, 5), date(2026, 11, 4), 0.001, CALENDARIO
    )
    assert motivo is not None
    assert motivo["calendario"] == [
        {"evento": "Decisão do Copom", "data": "2026-11-04", "fonte": "https://bcb"}
    ]
    assert motivo["variacao_forte_do_ibovespa"] is False


def test_ipca_e_evento_no_mesmo_pregao() -> None:
    motivo = ev.motivo_do_evento(
        date(2026, 11, 12), date(2026, 11, 11), 0.0, CALENDARIO
    )
    assert motivo is not None
    assert [m["evento"] for m in motivo["calendario"]] == ["IPCA"]
    assert (
        ev.motivo_do_evento(date(2026, 11, 13), date(2026, 11, 12), 0.0, CALENDARIO)
        is None
    )


def test_evento_depois_do_fechamento_antes_de_feriado_cai_no_pregao_seguinte() -> None:
    """Sexta 20/11 é feriado: o que sai na quinta à noite vale para a segunda."""
    quinta = ev.EventoMarcado(
        date(2026, 11, 19), "Decisão", ev.DEPOIS_DO_FECHAMENTO, "https://x"
    )
    motivo = ev.motivo_do_evento(date(2026, 11, 23), date(2026, 11, 19), 0.0, [quinta])
    assert motivo is not None


@pytest.mark.parametrize("variacao", [-0.03, 0.035, -0.139])
def test_queda_ou_alta_de_3_por_cento_e_evento(variacao: float) -> None:
    motivo = ev.motivo_do_evento(date(2026, 10, 26), date(2026, 10, 23), variacao, [])
    assert motivo is not None
    assert motivo["calendario"] == []
    assert motivo["variacao_forte_do_ibovespa"] is True
    assert motivo["variacao_minima"] == ev.VARIACAO_FORTE_DO_IBOVESPA


def test_dia_comum_nao_e_evento() -> None:
    assert (
        ev.motivo_do_evento(date(2026, 11, 10), date(2026, 11, 9), -0.029, CALENDARIO)
        is None
    )


def test_momento_desconhecido_e_recusado(tmp_path: Path) -> None:
    caminho = tmp_path / "calendario.csv"
    caminho.write_text(
        "data,evento,momento,fonte\n2026-11-04,Copom,de_noite,https://bcb\n", "utf-8"
    )
    with pytest.raises(ValueError, match="de_noite"):
        ev.ler_calendario(caminho)


def test_o_calendario_do_repositorio_abre_e_cita_a_fonte_oficial() -> None:
    calendario = ev.ler_calendario()
    assert calendario
    assert [e.data for e in calendario] == sorted(e.data for e in calendario)
    assert len({(e.data, e.evento) for e in calendario}) == len(calendario)
    for evento in calendario:
        assert urlparse(evento.fonte).scheme == "https"
        assert urlparse(evento.fonte).hostname in DOMINIOS_OFICIAIS


def test_evento_do_mesmo_dia_cai_em_dia_de_pregao() -> None:
    """Um evento de efeito no mesmo dia marcado num dia sem pregão nunca seria visto."""
    for evento in ev.ler_calendario():
        if evento.momento == ev.ANTES_DO_FECHAMENTO:
            assert eh_pregao(evento.data), evento
