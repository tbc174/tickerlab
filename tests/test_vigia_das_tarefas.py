"""Vigia das tarefas: lê o crontab e as marcas do servidor e escreve o estado em JSON (painel das coletas)."""

import io
import json
import os
from datetime import UTC, datetime

from scripts import vigia_das_tarefas as vigia
from src.classificar_falha import validar

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


def _preparar_com_logs(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "series-macro.log").write_text(
        "rodada antiga\nHTTPError: 403 Client Error: Forbidden\n"
        "rodada nova\njson.decoder.JSONDecodeError: Expecting value\n"
        "src.bcb.BcbIndisponivelError: https://api.bcb.gov.br/dados não respondeu JSON\n",
        encoding="utf-8",
    )
    crontab = tmp_path / "crontab.txt"
    crontab.write_text(
        f"30 6 * * * /home/usuario/rodar-tarefa.sh series-macro {logs / 'series-macro.log'} 'x'\n"
        f"*/10 * * * * /home/usuario/rodar-tarefa.sh cripto-no {logs / 'nao-existe.log'} 'y'\n"
        f"0 7 * * * /home/usuario/rodar-tarefa.sh eventos-cvm {logs / 'eventos.log'} 'z'\n"
        f"0 2 * * * /home/usuario/rodar-tarefa.sh arquivo-diaria {logs / 'arquivo.log'} 'w'\n",
        encoding="utf-8",
    )
    marcas = tmp_path / "estado-tarefas"
    marcas.mkdir()
    (marcas / "series-macro.falha").write_text(
        "2026-10-21T06:30:09-03:00 saída 1\n", "utf-8"
    )
    (marcas / "cripto-no.falha").write_text(
        "2026-10-21T11:50:01-03:00 saída 1\nFALHAS: C7: a soma não bate\n", "utf-8"
    )
    (marcas / "eventos-cvm.ok").write_text("2026-10-21T07:00:03-03:00\n", "utf-8")
    (marcas / "arquivo-diaria.ok").write_text("2026-10-18T02:10:00-03:00\n", "utf-8")
    resumos = tmp_path / "resumos"
    resumos.mkdir()
    (resumos / "eventos-cvm.json").write_text("{}", "utf-8")  # sobra de quando falhou
    return crontab, marcas, resumos


def _rodar_com_resumos(tmp_path) -> dict[str, dict]:
    crontab, marcas, resumos = _preparar_com_logs(tmp_path)
    argumentos = ["--crontab", str(crontab), "--marcas", str(marcas)]
    argumentos += ["--saida", str(tmp_path / "estado.json"), "--agora", AGORA]
    assert (
        vigia.main([*argumentos, "--servidor", "casa", "--resumos", str(resumos)]) == 0
    )
    return {
        arquivo.stem: json.loads(arquivo.read_text(encoding="utf-8"))
        for arquivo in resumos.glob("*.json")
    }


def test_escreve_um_resumo_valido_por_falha_ou_atraso_e_apaga_o_das_que_voltaram(
    tmp_path,
):
    resumos = _rodar_com_resumos(tmp_path)

    assert set(resumos) == {"series-macro", "cripto-no", "arquivo-diaria"}
    for resumo in resumos.values():
        validar(resumo)


def test_resumo_usa_o_erro_mais_recente_do_log_e_o_codigo_da_marca(tmp_path):
    resumo = _rodar_com_resumos(tmp_path)["series-macro"]

    assert resumo == {
        "servidor": "casa",
        "tarefa": "series-macro",
        "hora": "2026-10-21T06:30:09-03:00",
        "codigo": 1,
        "tipo": "resposta_nao_json",
        "excecao": "BcbIndisponivelError",
        "host": "api.bcb.gov.br",
    }


def test_resumo_le_a_linha_falhas_da_marca_quando_o_log_nao_existe(tmp_path):
    resumo = _rodar_com_resumos(tmp_path)["cripto-no"]

    assert resumo["tipo"] == "conferencia_falhou"
    assert "C7" not in json.dumps(resumo)


def test_tarefa_atrasada_vira_resumo_do_tipo_atrasada(tmp_path):
    resumo = _rodar_com_resumos(tmp_path)["arquivo-diaria"]

    assert resumo["tipo"] == "atrasada"
    assert resumo["codigo"] is None
    assert (
        resumo["hora"] == "2026-10-19T04:10:00-03:00"
    )  # quando o último sucesso venceu
