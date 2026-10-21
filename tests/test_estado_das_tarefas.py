"""Estado de cada tarefa: as marcas do rodar-tarefa.sh contra a agenda do crontab (painel das coletas)."""

from datetime import UTC, datetime, timedelta

from src.agenda_das_tarefas import TarefaAgendada
from src.estado_das_tarefas import Marca, estado_das_tarefas

AGORA = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
DIARIA = TarefaAgendada(
    "eventos-cvm", timedelta(days=1), timedelta(hours=26), ("0 7 * * *",)
)


def _estado(marcas: dict[str, Marca], agenda: list[TarefaAgendada] | None = None):
    return {e.nome: e for e in estado_das_tarefas(agenda or [DIARIA], marcas, AGORA)}


def test_sucesso_dentro_do_prazo_fica_ok():
    ok_em = AGORA - timedelta(hours=5)

    estado = _estado({"eventos-cvm": Marca(ok_em=ok_em)})["eventos-cvm"]

    assert estado.situacao == "ok"
    assert estado.ultimo_ok == ok_em
    assert estado.vence_em == ok_em + timedelta(hours=26)


def test_sucesso_vencido_fica_atrasada():
    estado = _estado({"eventos-cvm": Marca(ok_em=AGORA - timedelta(hours=27))})

    assert estado["eventos-cvm"].situacao == "atrasada"


def test_sucesso_no_limite_do_prazo_ainda_e_ok():
    estado = _estado({"eventos-cvm": Marca(ok_em=AGORA - timedelta(hours=26))})

    assert estado["eventos-cvm"].situacao == "ok"


def test_falha_mais_nova_que_o_sucesso_fica_falhou_com_o_ultimo_sucesso():
    ok_em = AGORA - timedelta(days=4)
    falha_em = AGORA - timedelta(hours=5)

    estado = _estado({"eventos-cvm": Marca(ok_em=ok_em, falha_em=falha_em)})[
        "eventos-cvm"
    ]

    assert estado.situacao == "falhou"
    assert estado.ultimo_ok == ok_em
    assert estado.ultima_falha == falha_em


def test_falha_sem_nenhum_sucesso_fica_falhou():
    estado = _estado({"eventos-cvm": Marca(falha_em=AGORA - timedelta(hours=1))})

    assert estado["eventos-cvm"].situacao == "falhou"
    assert estado["eventos-cvm"].vence_em is None


def test_falha_velha_com_sucesso_depois_fica_ok():
    # o rodar-tarefa.sh apaga o .falha no sucesso; se sobrou um, vale a marca mais nova
    marca = Marca(ok_em=AGORA - timedelta(hours=1), falha_em=AGORA - timedelta(hours=3))

    assert _estado({"eventos-cvm": marca})["eventos-cvm"].situacao == "ok"


def test_tarefa_sem_marca_fica_nunca_rodou():
    assert _estado({})["eventos-cvm"].situacao == "nunca_rodou"


def test_marca_sem_linha_no_cron_fica_fora_da_agenda_depois_das_agendadas():
    marcas = {
        "removida": Marca(ok_em=AGORA - timedelta(days=30)),
        "eventos-cvm": Marca(ok_em=AGORA),
    }

    estados = estado_das_tarefas([DIARIA], marcas, AGORA)

    assert [(e.nome, e.situacao) for e in estados] == [
        ("eventos-cvm", "ok"),
        ("removida", "fora_da_agenda"),
    ]


def test_estado_vira_dicionario_de_tipos_simples():
    ok_em = AGORA - timedelta(hours=5)

    (estado,) = estado_das_tarefas([DIARIA], {"eventos-cvm": Marca(ok_em=ok_em)}, AGORA)

    assert estado.como_dicionario() == {
        "nome": "eventos-cvm",
        "situacao": "ok",
        "ultimo_ok": "2026-10-21T07:00:00+00:00",
        "ultima_falha": None,
        "vence_em": "2026-10-22T09:00:00+00:00",
        "prazo_em_horas": 26.0,
    }
