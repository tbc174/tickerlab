"""Estado das tarefas do servidor no boletim (`base/boletim/tarefas.py`): as marcas `.ok`/`.falha`
que o `rodar-tarefa.sh` grava."""

import os
from datetime import datetime, timedelta, timezone

from base.boletim import tarefas as ta

AGORA = datetime(2026, 10, 17, 9, 30, tzinfo=timezone(timedelta(hours=-3)))


def _marca(pasta, nome, texto, horas_atras=1.0):
    arquivo = pasta / nome
    arquivo.write_text(texto, encoding="utf-8")
    quando = (AGORA - timedelta(hours=horas_atras)).timestamp()
    os.utime(arquivo, (quando, quando))


def test_falha_traz_a_hora_e_o_motivo(tmp_path):
    _marca(
        tmp_path,
        "rede.falha",
        "2026-10-17T06:10:00-03:00 saída 1\nFALHAS: rede: sem memória\n",
    )
    _marca(tmp_path, "rede.ok", "2026-10-16T06:05:00-03:00\n", horas_atras=27)
    estado = ta.ler_estado(tmp_path, AGORA, diarias=["rede"])
    assert [(e.nome, e.situacao, e.motivo) for e in estado.falhas] == [
        ("rede", "falha", "rede: sem memória")
    ]
    assert estado.falhas[0].quando == "2026-10-17T06:10:00-03:00"
    assert estado.atrasadas == []  # a falha já diz; não repete como atraso


def test_diaria_sem_sucesso_ha_mais_de_26_horas_e_atrasada(tmp_path):
    _marca(
        tmp_path, "ratings-tabela.ok", "2026-10-16T05:00:00-03:00\n", horas_atras=28.5
    )
    _marca(tmp_path, "rede.ok", "2026-10-17T06:05:00-03:00\n", horas_atras=3.4)
    estado = ta.ler_estado(
        tmp_path, AGORA, diarias=["rede", "ratings-tabela", "nunca-rodou"]
    )
    assert [(e.nome, e.horas) for e in estado.atrasadas] == [("ratings-tabela", 28)]
    assert [e.nome for e in estado.sem_marca] == ["nunca-rodou"]
    assert estado.em_dia == 1
    assert estado.total == 2  # marcas encontradas


def test_tarefa_que_nao_e_diaria_nao_fica_atrasada(tmp_path):
    _marca(tmp_path, "carga-cda.ok", "2026-10-12T09:00:00-03:00\n", horas_atras=120)
    estado = ta.ler_estado(tmp_path, AGORA, diarias=[])
    assert estado.atrasadas == [] and estado.falhas == []


def test_pasta_que_nao_existe_e_estado_vazio(tmp_path):
    estado = ta.ler_estado(tmp_path / "nao-existe", AGORA, diarias=["rede"])
    assert estado.total == 0 and estado.disponivel is False
