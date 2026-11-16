"""O quadro do estado sai dos PRs e das cópias, não de status escrito à mão (plano de 16/11/2026)."""

from datetime import datetime, timedelta, timezone

import pytest

from scripts import estado_da_empresa
from scripts.estado_da_empresa import (
    ALERTA_COPIA_DE_PR_MESCLADO,
    ALERTA_SEM_ATIVIDADE,
    ALERTA_VERDE_SEM_MERGE_AUTOMATICO,
    AVISO_DE_ARQUIVO_GERADO,
    classificar_testes,
    escrever_quadro,
    ler_copias,
    montar_estado,
    texto_do_quadro,
)

AGORA = datetime(2026, 11, 16, 9, 0, tzinfo=timezone(timedelta(hours=-3)))

PASSOU = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}
PULOU = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"}
FALHOU = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}
RODANDO = {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""}
CONTEXTO_VERDE = {"__typename": "StatusContext", "state": "SUCCESS"}
CONTEXTO_PENDENTE = {"__typename": "StatusContext", "state": "PENDING"}


def _pr(numero: int, ramo: str, parado: timedelta, **outros) -> dict:
    """Um PR como o `gh pr list --json` devolve, parado há `parado`."""
    mexido = (AGORA - parado).astimezone(timezone.utc)
    return {
        "number": numero,
        "title": f"feat: mudança {numero}",
        "headRefName": ramo,
        "updatedAt": mexido.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "isDraft": False,
        "autoMergeRequest": None,
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": [PASSOU, PULOU],
        **outros,
    }


def _alertas(estado: dict, tipo: str) -> list[dict]:
    return [alerta for alerta in estado["alertas"] if alerta["tipo"] == tipo]


@pytest.mark.parametrize(
    ("checks", "esperado"),
    [
        ([PASSOU, PULOU, CONTEXTO_VERDE], "verde"),
        ([PASSOU, FALHOU], "vermelho"),
        ([FALHOU, RODANDO], "vermelho"),  # já dá para saber que não passa
        ([PASSOU, RODANDO], "rodando"),
        ([PASSOU, CONTEXTO_PENDENTE], "rodando"),
        ([], "sem testes"),
    ],
)
def test_classifica_os_testes_de_um_pr(checks, esperado):
    assert classificar_testes(checks) == esperado


def test_pr_verde_de_dez_minutos_nao_gera_alerta():
    estado = montar_estado(
        [_pr(1, "feat/novo", timedelta(minutes=10))], [], set(), AGORA
    )

    assert estado["alertas"] == []
    assert estado["resumo"]["verdes"] == 1


def test_os_tres_alertas_saem_dos_prs_e_das_copias():
    prs = [
        _pr(1, "feat/novo", timedelta(minutes=10)),
        _pr(2, "feat/verde-parado", timedelta(hours=3)),
        _pr(3, "feat/esquecido", timedelta(days=8), statusCheckRollup=[FALHOU]),
    ]
    copias = [
        {"pasta": "C:/projetos/analise-acoes", "ramo": "main"},
        {"pasta": "C:/projetos/analise-acoes-novo", "ramo": "feat/novo"},
        {"pasta": "C:/projetos/analise-acoes-velha", "ramo": "feat/ja-entrou"},
    ]

    estado = montar_estado(prs, copias, {"feat/ja-entrou", "feat/outro"}, AGORA)

    assert [
        a["numero"] for a in _alertas(estado, ALERTA_VERDE_SEM_MERGE_AUTOMATICO)
    ] == [2]
    assert [a["numero"] for a in _alertas(estado, ALERTA_SEM_ATIVIDADE)] == [3]
    assert [a["pasta"] for a in _alertas(estado, ALERTA_COPIA_DE_PR_MESCLADO)] == [
        "C:/projetos/analise-acoes-velha"
    ]
    assert len(estado["alertas"]) == 3
    assert estado["resumo"] == {
        "abertos": 3,
        "verdes": 2,
        "vermelhos": 1,
        "rodando": 0,
        "sem_testes": 0,
        "do_agente": 0,
        "copias": 3,
    }


@pytest.mark.parametrize(
    "muda",
    [
        {"autoMergeRequest": {"mergeMethod": "SQUASH"}},  # já vai entrar sozinho
        {"isDraft": True},  # rascunho não é para mesclar
        {"statusCheckRollup": [PASSOU, RODANDO]},  # ainda não está verde
        {"statusCheckRollup": [FALHOU]},  # vermelho é outro problema
    ],
)
def test_verde_parado_so_vale_para_pr_pronto_e_sem_merge_automatico(muda):
    estado = montar_estado(
        [_pr(7, "feat/x", timedelta(hours=5), **muda)], [], set(), AGORA
    )

    assert _alertas(estado, ALERTA_VERDE_SEM_MERGE_AUTOMATICO) == []


def test_o_limite_de_duas_horas_e_de_sete_dias_e_estrito():
    prs = [
        _pr(1, "feat/a", timedelta(hours=2)),
        _pr(2, "feat/b", timedelta(days=7), statusCheckRollup=[FALHOU]),
    ]

    assert montar_estado(prs, [], set(), AGORA)["alertas"] == []


def test_copia_de_ramo_mesclado_que_voltou_a_ter_pr_aberto_nao_e_alerta():
    prs = [_pr(9, "feat/segunda-parte", timedelta(minutes=5))]
    copias = [{"pasta": "C:/projetos/analise-acoes-x", "ramo": "feat/segunda-parte"}]

    estado = montar_estado(prs, copias, {"feat/segunda-parte"}, AGORA)

    assert _alertas(estado, ALERTA_COPIA_DE_PR_MESCLADO) == []


def test_pr_do_agente_da_nuvem_vem_marcado():
    estado = montar_estado(
        [
            _pr(4, "claude/agente-relogio", timedelta(minutes=1)),
            _pr(5, "feat/de-conversa", timedelta(minutes=1)),
        ],
        [],
        set(),
        AGORA,
    )

    assert [pr["do_agente"] for pr in estado["prs"]] == [True, False]
    assert estado["resumo"]["do_agente"] == 1


def test_le_as_copias_da_saida_do_git():
    saida = (
        "worktree C:/projetos/analise-acoes\n"
        "HEAD 1111111111111111111111111111111111111111\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree C:/projetos/analise-acoes-estado\n"
        "HEAD 2222222222222222222222222222222222222222\n"
        "branch refs/heads/feat/estado-da-empresa\n"
        "\n"
        "worktree C:/projetos/analise-acoes-solta\n"
        "HEAD 3333333333333333333333333333333333333333\n"
        "detached\n"
    )

    assert ler_copias(saida) == [
        {"pasta": "C:/projetos/analise-acoes", "ramo": "main"},
        {"pasta": "C:/projetos/analise-acoes-estado", "ramo": "feat/estado-da-empresa"},
        {"pasta": "C:/projetos/analise-acoes-solta", "ramo": None},
    ]


def test_o_quadro_comeca_dizendo_que_e_gerado_e_a_hora():
    estado = montar_estado(
        [_pr(2, "feat/verde-parado", timedelta(hours=3))], [], set(), AGORA
    )

    texto = texto_do_quadro(estado)

    primeira_linha = texto.splitlines()[0]
    assert AVISO_DE_ARQUIVO_GERADO in primeira_linha
    assert "gerado, não editar" in primeira_linha
    assert "16/11/2026 09:00" in primeira_linha
    assert "#2" in texto
    assert "há 3 h" in texto


def test_quadro_sem_alerta_diz_que_nao_ha_nada_parado():
    estado = montar_estado(
        [_pr(1, "feat/novo", timedelta(minutes=10))], [], set(), AGORA
    )

    assert "Nenhum alerta" in texto_do_quadro(estado)


def test_escreve_o_quadro_no_destino(tmp_path):
    destino = tmp_path / "pasta-nova" / "estado.md"
    estado = montar_estado(
        [_pr(1, "feat/novo", timedelta(minutes=10))], [], set(), AGORA
    )

    escrever_quadro(estado, destino)

    assert destino.read_text(encoding="utf-8") == texto_do_quadro(estado)


def test_o_comando_le_monta_e_grava_sem_falar_com_o_github(tmp_path, monkeypatch):
    destino = tmp_path / "estado.md"
    monkeypatch.setattr(
        estado_da_empresa,
        "buscar_prs_abertos",
        lambda: [_pr(2, "feat/verde-parado", timedelta(days=30))],
    )
    monkeypatch.setattr(estado_da_empresa, "buscar_copias", list)
    monkeypatch.setattr(estado_da_empresa, "buscar_ramos_mesclados", set)

    assert estado_da_empresa.main(["--destino", str(destino)]) == 0

    texto = destino.read_text(encoding="utf-8")
    assert texto.startswith(AVISO_DE_ARQUIVO_GERADO)
    assert "## Alertas (2)" in texto
