"""O placar da semana sai do GitHub: sempre os mesmos dez números (plano de 16/11/2026)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from scripts import placar_da_semana
from scripts.estado_da_empresa import AVISO_DE_ARQUIVO_GERADO
from scripts.placar_da_semana import (
    QUANTOS_NUMEROS,
    escrever_placar,
    ler_semana,
    montar_placar,
    semana_anterior,
    texto_do_placar,
)

BRASILIA = timezone(timedelta(hours=-3))
SEGUNDA = date(2026, 11, 9)  # semana 46: de 09/11 a 15/11/2026
AGORA = datetime(2026, 11, 16, 9, 0, tzinfo=BRASILIA)

PASSOU = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}
FALHOU = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}


def _hora(dia: int, hora: int = 12, minuto: int = 0) -> str:
    """Uma hora de novembro de 2026, de Brasília, escrita como o GitHub escreve (UTC)."""
    local = datetime(2026, 11, dia, hora, minuto, tzinfo=BRASILIA)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mesclado(
    numero: int, entrou: str, minutos: int, titulo: str = "feat: algo"
) -> dict:
    """Um PR que entrou em `entrou`, aberto `minutos` antes."""
    aberto = datetime.fromisoformat(entrou.replace("Z", "+00:00")) - timedelta(
        minutes=minutos
    )
    return {
        "number": numero,
        "title": titulo,
        "createdAt": aberto.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mergedAt": entrou,
    }


def _execucao(criada: str, conclusao: str, status: str = "completed") -> dict:
    return {"createdAt": criada, "conclusion": conclusao, "status": status}


def _aberto(numero: int, parado: timedelta, **outros) -> dict:
    mexido = (AGORA - parado).astimezone(timezone.utc)
    return {
        "number": numero,
        "title": f"feat: mudança {numero}",
        "headRefName": f"feat/ramo-{numero}",
        "updatedAt": mexido.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "isDraft": False,
        "autoMergeRequest": None,
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": [PASSOU],
        **outros,
    }


def _numero(placar: dict, qual: int) -> dict:
    return next(linha for linha in placar["numeros"] if linha["numero"] == qual)


def _placar(mesclados=(), execucoes=(), abertos=()) -> dict:
    return montar_placar(
        list(mesclados), list(execucoes), list(abertos), SEGUNDA, AGORA
    )


def test_conta_so_os_prs_que_entraram_dentro_da_semana():
    placar = _placar(
        mesclados=[
            _mesclado(1, _hora(8, 23, 59), 10),  # domingo anterior, 23h59: fora
            _mesclado(2, _hora(9, 0, 0), 10),  # segunda, 0h00: dentro
            _mesclado(3, _hora(15, 23, 59), 10),  # domingo, 23h59: dentro
            _mesclado(4, _hora(16, 0, 0), 10),  # segunda seguinte, 0h00: fora
        ]
    )

    assert _numero(placar, 1)["valor"] == 2
    assert placar["semana"] == {
        "rotulo": "2026-W46",
        "inicio": "2026-11-09",
        "fim": "2026-11-15",
    }


def test_tempo_mediano_entre_abrir_e_entrar_em_minutos():
    placar = _placar(
        mesclados=[
            _mesclado(1, _hora(10), 5),
            _mesclado(2, _hora(11), 9),
            _mesclado(3, _hora(12), 600),  # um PR demorado não puxa a mediana
            _mesclado(4, _hora(2), 1),  # fora da semana: não entra na conta
        ]
    )

    assert _numero(placar, 2)["valor"] == 9
    assert "9 min" in _numero(placar, 2)["texto"]


def test_falha_na_versao_principal_ignora_cancelada_e_o_que_ainda_roda():
    placar = _placar(
        execucoes=[
            _execucao(_hora(10), "success"),
            _execucao(_hora(10), "success"),
            _execucao(_hora(11), "success"),
            _execucao(_hora(12), "failure"),
            _execucao(_hora(12), "cancelled"),  # trocada por um push mais novo
            _execucao(_hora(13), "", status="in_progress"),
            _execucao(_hora(3), "failure"),  # fora da semana
        ]
    )

    assert _numero(placar, 3)["valor"] == 25.0
    assert "1 de 4" in _numero(placar, 3)["texto"]


def test_verdes_parados_ha_mais_de_um_dia_sao_os_prontos_sem_merge_automatico():
    placar = _placar(
        abertos=[
            _aberto(1, timedelta(hours=25)),
            _aberto(2, timedelta(hours=24)),  # o limite é estrito
            _aberto(3, timedelta(days=3), isDraft=True),
            _aberto(4, timedelta(days=3), autoMergeRequest={"mergeMethod": "SQUASH"}),
            _aberto(5, timedelta(days=3), statusCheckRollup=[FALHOU]),
            _aberto(6, timedelta(days=9)),
        ]
    )

    assert _numero(placar, 4)["valor"] == 2
    assert "#1" in _numero(placar, 4)["texto"]
    assert "#6" in _numero(placar, 4)["texto"]


def test_reversoes_sao_os_prs_da_semana_com_titulo_de_reversao():
    placar = _placar(
        mesclados=[
            _mesclado(1, _hora(10), 5, titulo='Revert "feat: algo"'),
            _mesclado(2, _hora(11), 5, titulo="revert: desfaz a coleta"),
            _mesclado(3, _hora(12), 5, titulo="fix: reverte o sinal do saldo"),
        ]
    )

    assert _numero(placar, 9)["valor"] == 2


def test_semana_vazia_nao_inventa_numero():
    placar = _placar()

    assert _numero(placar, 1)["valor"] == 0
    assert _numero(placar, 2)["valor"] is None
    assert _numero(placar, 3)["valor"] is None
    assert _numero(placar, 4)["valor"] == 0


def test_o_placar_tem_sempre_os_mesmos_dez_numeros_e_diz_o_que_nao_mede():
    placar = _placar()

    assert [linha["numero"] for linha in placar["numeros"]] == list(
        range(1, QUANTOS_NUMEROS + 1)
    )
    assert QUANTOS_NUMEROS == 10
    assert [linha["numero"] for linha in placar["numeros"] if linha["medido"]] == [
        1,
        2,
        3,
        4,
        9,
    ]
    for linha in placar["numeros"]:
        if not linha["medido"]:
            assert linha["valor"] is None
            assert linha["texto"].startswith("não medido por este programa")


@pytest.mark.parametrize(
    ("escrito", "segunda"),
    [("2026-W46", date(2026, 11, 9)), ("2027-W01", date(2027, 1, 4))],
)
def test_le_a_semana_escrita_como_ano_e_numero(escrito, segunda):
    assert ler_semana(escrito) == segunda


@pytest.mark.parametrize("escrito", ["2026-46", "semana passada", "2026-W60"])
def test_semana_mal_escrita_e_recusada(escrito):
    with pytest.raises(ValueError, match="AAAA-Www"):
        ler_semana(escrito)


@pytest.mark.parametrize(
    ("hoje", "segunda"),
    [
        (
            date(2026, 11, 16),
            date(2026, 11, 9),
        ),  # numa segunda: a semana que fechou ontem
        (
            date(2026, 11, 22),
            date(2026, 11, 9),
        ),  # num domingo: a semana em curso não conta
    ],
)
def test_sem_semana_pedida_vale_a_ultima_semana_fechada(hoje, segunda):
    assert semana_anterior(hoje) == segunda


def test_o_texto_comeca_dizendo_que_e_gerado_e_traz_os_dez_numeros():
    texto = texto_do_placar(_placar(mesclados=[_mesclado(1, _hora(10), 5)]))

    primeira_linha = texto.splitlines()[0]
    assert primeira_linha.startswith(AVISO_DE_ARQUIVO_GERADO)
    assert "16/11/2026 09:00" in primeira_linha
    assert "2026-W46" in texto
    assert "09/11 a 15/11/2026" in texto
    assert sum(linha.startswith("| ") for linha in texto.splitlines()) == 11


def test_escreve_o_placar_no_destino(tmp_path):
    destino = tmp_path / "placares" / "2026-W46.md"
    placar = _placar()

    escrever_placar(placar, destino)

    assert destino.read_text(encoding="utf-8") == texto_do_placar(placar)


def test_o_comando_pede_ao_github_uma_janela_que_cobre_a_semana(tmp_path, monkeypatch):
    pedidos = {}

    def mesclados_falsos(de: date, ate: date) -> list[dict]:
        pedidos["mesclados"] = (de, ate)
        return [_mesclado(1, _hora(10), 5)]

    def execucoes_falsas(de: date, ate: date) -> list[dict]:
        pedidos["execucoes"] = (de, ate)
        return [_execucao(_hora(10), "success")]

    monkeypatch.setattr(placar_da_semana, "buscar_prs_mesclados", mesclados_falsos)
    monkeypatch.setattr(placar_da_semana, "buscar_execucoes_da_main", execucoes_falsas)
    monkeypatch.setattr(placar_da_semana, "buscar_prs_abertos", list)
    destino = tmp_path / "placar.md"

    assert (
        placar_da_semana.main(["--semana", "2026-W46", "--destino", str(destino)]) == 0
    )

    # um dia de folga de cada lado: as datas da busca do GitHub são em UTC
    assert pedidos["mesclados"] == (date(2026, 11, 8), date(2026, 11, 17))
    assert pedidos["execucoes"] == (date(2026, 11, 8), date(2026, 11, 17))
    assert "| 1 | PRs que entraram na semana | 1 |" in destino.read_text(
        encoding="utf-8"
    )
