"""Vigia das tarefas: lê o crontab e as marcas do servidor e escreve o estado em JSON (painel das coletas)."""

import io
import json
import os
from datetime import UTC, datetime

from scripts import vigia_das_tarefas as vigia

CRONTAB = """\
0 7 * * * /home/usuario/rodar-tarefa.sh eventos-cvm /home/usuario/eventos-cvm.log 'x'
*/10 * * * * /home/usuario/rodar-tarefa.sh cripto-no /home/usuario/logs/cripto-no.log "y"
0 9 12 * * /home/usuario/rodar-tarefa.sh carga-fca /home/usuario/logs/carga-fca.log "z"
"""
AGORA = "2026-10-21T12:00:00-03:00"


def _preparar(tmp_path):
    crontab = tmp_path / "crontab.txt"
    crontab.write_text(CRONTAB, encoding="utf-8")
    marcas = tmp_path / "estado-tarefas"
    marcas.mkdir()
    (marcas / "eventos-cvm.ok").write_text(
        "2026-10-21T07:00:03-03:00\n", encoding="utf-8"
    )
    (marcas / "cripto-no.ok").write_text(
        "2026-10-17T09:10:02-03:00\n", encoding="utf-8"
    )
    (marcas / "cripto-no.falha").write_text(
        "2026-10-21T11:50:01-03:00 saída 1\nFALHAS: C7: a soma não bate\n",
        encoding="utf-8",
    )
    (marcas / "memoria.ok").write_text("2026-10-21T11:55:00-03:00\n", encoding="utf-8")
    return crontab, marcas


def _rodar(tmp_path, *extras: str) -> tuple[int, dict]:
    crontab, marcas = _preparar(tmp_path)
    saida = tmp_path / "estado.json"
    argumentos = [
        "--crontab",
        str(crontab),
        "--marcas",
        str(marcas),
        "--saida",
        str(saida),
    ]
    codigo = vigia.main([*argumentos, "--agora", AGORA, *extras])
    return codigo, json.loads(saida.read_text(encoding="utf-8"))


def test_escreve_uma_entrada_por_tarefa_e_sai_com_zero_mesmo_com_falha(tmp_path):
    codigo, estado = _rodar(tmp_path)

    assert codigo == 0
    situacoes = {t["nome"]: t["situacao"] for t in estado["tarefas"]}
    assert situacoes == {
        "eventos-cvm": "ok",
        "cripto-no": "falhou",
        "carga-fca": "nunca_rodou",
        "memoria": "fora_da_agenda",
    }
    assert estado["gerado_em"] == "2026-10-21T12:00:00-03:00"


def test_o_json_nao_leva_o_texto_da_marca_de_falha(tmp_path):
    _, estado = _rodar(tmp_path)

    assert "C7" not in json.dumps(estado, ensure_ascii=False)


def test_hora_da_marca_vem_do_conteudo(tmp_path):
    _, estado = _rodar(tmp_path)

    cripto = next(t for t in estado["tarefas"] if t["nome"] == "cripto-no")
    assert cripto["ultima_falha"] == "2026-10-21T11:50:01-03:00"
    assert cripto["ultimo_ok"] == "2026-10-17T09:10:02-03:00"


def test_marca_sem_data_legivel_usa_a_hora_do_arquivo(tmp_path):
    marca = tmp_path / "x.ok"
    marca.write_text("lixo\n", encoding="utf-8")
    momento = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
    os.utime(marca, (momento.timestamp(), momento.timestamp()))

    assert vigia.hora_da_marca(marca) == momento


def test_crontab_pela_entrada_padrao(tmp_path, monkeypatch):
    _, marcas = _preparar(tmp_path)
    saida = tmp_path / "estado.json"
    monkeypatch.setattr("sys.stdin", io.StringIO(CRONTAB))

    codigo = vigia.main(
        [
            "--crontab",
            "-",
            "--marcas",
            str(marcas),
            "--saida",
            str(saida),
            "--agora",
            AGORA,
        ]
    )

    assert codigo == 0
    assert len(json.loads(saida.read_text(encoding="utf-8"))["tarefas"]) == 4
