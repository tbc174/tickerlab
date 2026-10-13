"""O cálculo do nascer e do pôr do sol (static/tema/sol.js), que decide o tema Automático do site e do
app. Roda o JavaScript de verdade pelo Node (sem o Node, os testes são pulados)."""

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SOL = Path(__file__).resolve().parent.parent / "static" / "tema" / "sol.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node não instalado")


def _rodar(expressao: str):
    """Avalia `expressao` com o sol.js carregado (exportado como `sol`) e devolve o JSON."""
    programa = (
        f"const sol = require({json.dumps(str(SOL))});"
        f"process.stdout.write(JSON.stringify({expressao}));"
    )
    saida = subprocess.run(
        [NODE, "-e", programa], capture_output=True, text=True, check=True
    )
    return json.loads(saida.stdout)


def _horarios(data: str, fuso: str) -> tuple[datetime, datetime]:
    nascer, por = _rodar(
        f"(() => {{ const c = sol.CAPITAIS[{json.dumps(fuso)}];"
        f" const r = sol.nascerEPorDoSol(new Date({json.dumps(data)}), c[0], c[1]);"
        " return [r.nascer.toISOString(), r.por.toISOString()]; })()"
    )
    return datetime.fromisoformat(nascer), datetime.fromisoformat(por)


TOLERANCIA_EM_MINUTOS = 3  # fórmulas diferentes divergem 1 a 2 minutos


def _perto(horario: datetime, esperado: str, deslocamento_utc: int) -> bool:
    local = horario + timedelta(hours=deslocamento_utc)
    hora, minuto = (int(parte) for parte in esperado.split(":"))
    minutos = abs(local.hour * 60 + local.minute - (hora * 60 + minuto))
    return minutos <= TOLERANCIA_EM_MINUTOS


# esperado: as fórmulas da NOAA ("General Solar Position Calculations"), calculadas à parte
@pytest.mark.parametrize(
    ("fuso", "deslocamento", "nascer", "por"),
    [
        ("America/Sao_Paulo", -3, "05:35", "18:09"),
        ("America/Manaus", -4, "05:41", "17:51"),
        ("America/New_York", -4, "07:03", "18:20"),  # horário de verão em outubro
    ],
)
def test_nascer_e_por_do_sol_em_13_de_outubro(fuso, deslocamento, nascer, por):
    hora_nascer, hora_por = _horarios("2026-10-13T12:00:00Z", fuso)
    assert _perto(hora_nascer, nascer, deslocamento), hora_nascer
    assert _perto(hora_por, por, deslocamento), hora_por


@pytest.mark.parametrize(
    ("instante", "tema"),
    [
        ("2026-10-13T15:00:00Z", "claro"),  # 12h em São Paulo
        ("2026-10-14T02:00:00Z", "escuro"),  # 23h em São Paulo
        ("2026-10-13T08:00:00Z", "escuro"),  # 5h, antes do nascer
        ("2026-10-13T21:20:00Z", "escuro"),  # 18h20, depois do pôr
    ],
)
def test_tema_do_momento_em_sao_paulo(instante, tema):
    assert (
        _rodar(f'sol.temaDoMomento(new Date("{instante}"), "America/Sao_Paulo")')
        == tema
    )


def test_fuso_desconhecido_usa_6h_e_18h_do_relogio_do_aparelho():
    # sem capital conhecida, vale a hora local do aparelho (o Node do teste roda em UTC)
    meio_dia = datetime(2026, 10, 13, 12, tzinfo=timezone.utc).astimezone()
    noite = datetime(2026, 10, 13, 22, tzinfo=timezone.utc).astimezone()
    for instante, esperado in (
        (meio_dia, 6 <= meio_dia.hour < 18),
        (noite, 6 <= noite.hour < 18),
    ):
        tema = _rodar(
            f'sol.temaDoMomento(new Date("{instante.isoformat()}"), "Lugar/Inexistente")'
        )
        assert tema == ("claro" if esperado else "escuro")


def test_perto_dos_polos_sem_por_do_sol_nao_quebra():
    # inverno polar (sem nascer) e sol da meia-noite (sem pôr): o tema sai, sem erro
    noite_polar = _rodar(
        'sol.nascerEPorDoSol(new Date("2026-12-21T12:00:00Z"), 78.2, 15.6)'
    )
    dia_polar = _rodar(
        'sol.nascerEPorDoSol(new Date("2026-06-21T12:00:00Z"), 78.2, 15.6)'
    )
    assert noite_polar == {"nascer": None, "por": None, "sempre": "escuro"}
    assert dia_polar == {"nascer": None, "por": None, "sempre": "claro"}


def test_capitais_do_brasil_estao_todas():
    capitais = _rodar("Object.keys(sol.CAPITAIS)")
    for fuso in (
        "America/Sao_Paulo",
        "America/Manaus",
        "America/Belem",
        "America/Fortaleza",
        "America/Recife",
        "America/Bahia",
        "America/Cuiaba",
        "America/Campo_Grande",
        "America/Porto_Velho",
        "America/Boa_Vista",
        "America/Rio_Branco",
        "America/Noronha",
    ):
        assert fuso in capitais
