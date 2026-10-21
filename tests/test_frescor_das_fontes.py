"""Frescor das fontes: a última coleta "ok" de cada fonte está dentro do prazo? (painel das coletas, PR 3)

O vigia das tarefas diz se a tarefa rodou; este diz se chegou dado novo. Uma tarefa pode sair com 0 e
não baixar nada (a fonte mudou o endereço e o coletor só registrou "nao_encontrado").
"""

import json
import re
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from scripts import frescor_das_fontes as script
from src.banco.coletas import registrar
from src.banco.modelo import metadata
from src.frescor_das_fontes import FREQUENCIAS_DAS_FONTES, frescor_das_fontes

AGORA = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
DIARIA = timedelta(days=1)


def _registrar(motor, fonte: str, situacao: str, ha: timedelta) -> None:
    with motor.begin() as conexao:
        registrar(
            conexao,
            fonte,
            f"https://dados.exemplo.gov.br/{fonte}",
            b"x" if situacao == "ok" else None,
            situacao,
            agora=AGORA - ha,
        )


def _por_fonte(motor, frequencias: dict[str, timedelta]) -> dict[str, object]:
    with motor.connect() as conexao:
        return {f.fonte: f for f in frescor_das_fontes(conexao, frequencias, AGORA)}


def test_coleta_ok_de_duas_horas_atras_com_frequencia_diaria_e_fresca(banco):
    _registrar(banco, "cvm-ipe", "ok", timedelta(hours=2))

    frescor = _por_fonte(banco, {"cvm-ipe": DIARIA})["cvm-ipe"]

    assert frescor.situacao == "fresca"
    assert frescor.ultima_ok == AGORA - timedelta(hours=2)
    assert frescor.vence_em == AGORA - timedelta(hours=2) + timedelta(hours=26)


def test_coleta_ok_de_tres_dias_atras_com_frequencia_diaria_e_velha(banco):
    _registrar(banco, "cvm-ipe", "ok", timedelta(days=3))

    assert _por_fonte(banco, {"cvm-ipe": DIARIA})["cvm-ipe"].situacao == "velha"


def test_tentativas_que_falharam_depois_nao_renovam_o_frescor(banco):
    _registrar(banco, "cvm-ipe", "ok", timedelta(days=3))
    _registrar(banco, "cvm-ipe", "nao_encontrado", timedelta(hours=1))

    frescor = _por_fonte(banco, {"cvm-ipe": DIARIA})["cvm-ipe"]

    assert frescor.situacao == "velha"
    assert frescor.ultima_tentativa == AGORA - timedelta(hours=1)


def test_fonte_so_com_falhas_nunca_trouxe_dado(banco):
    _registrar(banco, "sec-13f", "falhou", timedelta(hours=5))

    frescor = _por_fonte(banco, {"sec-13f": DIARIA})["sec-13f"]

    assert frescor.situacao == "nunca"
    assert frescor.ultima_ok is None
    assert frescor.vence_em is None


def test_fonte_sem_frequencia_aparece_sem_prazo(banco):
    _registrar(banco, "anac-estatistico", "ok", timedelta(days=40))

    frescor = _por_fonte(banco, {})["anac-estatistico"]

    assert frescor.situacao == "sem_prazo"
    assert frescor.prazo is None


def test_fonte_com_frequencia_e_nenhuma_coleta_aparece_como_nunca(banco):
    assert _por_fonte(banco, {"cvm-eventos": DIARIA})["cvm-eventos"].situacao == "nunca"


def test_lista_sai_em_ordem_de_fonte(banco):
    for fonte in ("sec-13f", "cvm-cda", "bcb-ifdata"):
        _registrar(banco, fonte, "ok", timedelta(hours=1))

    with banco.connect() as conexao:
        fontes = [f.fonte for f in frescor_das_fontes(conexao, {}, AGORA)]

    assert fontes == ["bcb-ifdata", "cvm-cda", "sec-13f"]


def test_a_consulta_le_so_a_tabela_de_coletas(banco):
    _registrar(banco, "cvm-ipe", "ok", timedelta(hours=2))
    comandos: list[str] = []

    def guardar(_conexao, _cursor, comando, *_):
        comandos.append(comando.lower())

    sa.event.listen(banco, "before_cursor_execute", guardar)
    try:
        _por_fonte(banco, {"cvm-ipe": DIARIA})
    finally:
        sa.event.remove(banco, "before_cursor_execute", guardar)

    assert comandos
    outras = [nome for nome in metadata.tables if nome != "coletas"]
    for comando in comandos:
        assert "coletas" in comando
        for nome in outras:
            assert not re.search(rf"\b{nome}\b", comando), nome


def test_frequencias_das_fontes_diarias_da_vps():
    for fonte in (
        "cvm-eventos",
        "sec-eventos",
        "cvm-vlmo",
        "cvm-dfp-itr",
        "cvm-cda",
        "sec-13f",
    ):
        assert FREQUENCIAS_DAS_FONTES[fonte] == DIARIA


def test_dicionario_vai_para_json(banco):
    _registrar(banco, "cvm-ipe", "ok", timedelta(hours=2))

    with banco.connect() as conexao:
        (frescor,) = frescor_das_fontes(conexao, {"cvm-ipe": DIARIA}, AGORA)

    assert frescor.como_dicionario() == {
        "fonte": "cvm-ipe",
        "situacao": "fresca",
        "ultima_ok": "2026-10-21T10:00:00+00:00",
        "ultima_tentativa": "2026-10-21T10:00:00+00:00",
        "vence_em": "2026-10-22T12:00:00+00:00",
        "prazo_em_horas": 26.0,
    }


def test_script_escreve_o_json_e_sai_com_zero(banco, tmp_path):
    _registrar(banco, "cvm-eventos", "ok", timedelta(days=5))
    saida = tmp_path / "frescor.json"

    codigo = script.main(["--saida", str(saida), "--agora", AGORA.isoformat()])

    assert codigo == 0
    conteudo = json.loads(saida.read_text(encoding="utf-8"))
    assert conteudo["gerado_em"] == AGORA.isoformat()
    situacoes = {f["fonte"]: f["situacao"] for f in conteudo["fontes"]}
    assert situacoes["cvm-eventos"] == "velha"
    assert situacoes["sec-13f"] == "nunca"
