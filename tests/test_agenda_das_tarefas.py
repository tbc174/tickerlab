"""A agenda das tarefas sai do próprio crontab: período e prazo de cada tarefa (painel das coletas)."""

from datetime import timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.agenda_das_tarefas import TarefaAgendada, ler_agenda, periodo_da_expressao

# linhas no formato dos crontabs reais dos dois servidores, com a pasta pessoal anonimizada
CRONTAB_DE_EXEMPLO = """\
# m h  dom mon dow   command
MAILTO=""
* * * * * bash /opt/stacks/tickerlab/scripts/deploy-automatico.sh >/dev/null 2>&1
0 7 * * * /home/usuario/rodar-tarefa.sh eventos-cvm /home/usuario/eventos-cvm.log 'cd /opt && python - < a.py'
*/10 * * * * /home/usuario/rodar-tarefa.sh cripto-no /home/usuario/logs/cripto-no.log "/home/usuario/bin/c.sh no"
30 * * * * /home/usuario/rodar-tarefa.sh ma-textos /home/usuario/logs/ma-textos.log /home/usuario/bin/m.sh
0 5 * * 1 /home/usuario/rodar-tarefa.sh modelo8-montagem /home/usuario/logs/m8.log "/home/usuario/bin/m8.sh"
0 9 12 * * /home/usuario/rodar-tarefa.sh carga-fca /home/usuario/logs/carga-fca.log "/home/usuario/bin/s3.sh fca"
5 * * * * /home/usuario/conferir-tarefas.sh >> /home/usuario/conferir-tarefas.log 2>&1
# 0 6 * * * /home/usuario/rodar-tarefa.sh desligada /home/usuario/x.log x
"""


def _por_nome(agenda: list[TarefaAgendada]) -> dict[str, TarefaAgendada]:
    return {tarefa.nome: tarefa for tarefa in agenda}


def test_le_so_as_linhas_do_rodar_tarefa():
    agenda = _por_nome(ler_agenda(CRONTAB_DE_EXEMPLO))

    assert set(agenda) == {
        "eventos-cvm",
        "cripto-no",
        "ma-textos",
        "modelo8-montagem",
        "carga-fca",
    }


@pytest.mark.parametrize(
    ("nome", "periodo", "prazo"),
    [
        ("eventos-cvm", timedelta(hours=24), timedelta(hours=26)),
        ("cripto-no", timedelta(minutes=10), timedelta(hours=2, minutes=10)),
        ("ma-textos", timedelta(hours=1), timedelta(hours=3)),
        ("modelo8-montagem", timedelta(days=7), timedelta(days=8)),
        # dia 12 de cada mês: o maior intervalo é o de um mês de 31 dias
        ("carga-fca", timedelta(days=31), timedelta(days=35)),
    ],
)
def test_periodo_e_prazo_de_cada_tarefa(nome, periodo, prazo):
    tarefa = _por_nome(ler_agenda(CRONTAB_DE_EXEMPLO))[nome]

    assert tarefa.periodo == periodo
    assert tarefa.prazo == prazo


def test_tarefa_com_duas_linhas_usa_o_maior_intervalo_entre_elas():
    crontab = (
        "10 9 * * * /home/usuario/rodar-tarefa.sh dados-ferramentas /l 'a'\n"
        "40 13 * * * /home/usuario/rodar-tarefa.sh dados-ferramentas /l 'b'\n"
    )

    (tarefa,) = ler_agenda(crontab)

    # das 13h40 às 9h10 do dia seguinte
    assert tarefa.periodo == timedelta(hours=19, minutes=30)
    assert tarefa.horarios == ("10 9 * * *", "40 13 * * *")


@pytest.mark.parametrize(
    ("expressao", "periodo"),
    [
        ("20 3,4,5 * * *", timedelta(hours=22)),
        ("40 7-23 * * *", timedelta(hours=8)),
        ("0 10 * * 6", timedelta(days=7)),
        ("0 3 * * 0", timedelta(days=7)),
        ("0 3 * * 7", timedelta(days=7)),  # 7 também é domingo
        ("30 10 28 * *", timedelta(days=31)),
        ("0 */6 * * *", timedelta(hours=6)),
        ("@hourly", timedelta(hours=1)),
        ("@daily", timedelta(days=1)),
        ("@weekly", timedelta(days=7)),
    ],
)
def test_periodo_da_expressao(expressao, periodo):
    assert periodo_da_expressao(expressao) == periodo


def test_dia_do_mes_e_da_semana_juntos_valem_um_ou_outro():
    # como no cron: dia 15 OU segunda-feira; se valessem os dois juntos, seriam meses entre rodadas
    assert periodo_da_expressao("0 0 15 * 1") == timedelta(days=7)


@pytest.mark.parametrize(
    "expressao", ["0 7 * *", "61 * * * *", "0 7 * * seg", "a b c d e"]
)
def test_expressao_invalida_e_recusada(expressao):
    with pytest.raises(ValueError, match="cron"):
        periodo_da_expressao(expressao)


def test_reboot_nao_entra_na_agenda():
    assert ler_agenda("@reboot /home/usuario/rodar-tarefa.sh subir /l 'x'\n") == []


def test_nome_de_tarefa_fora_do_padrao_e_recusado():
    with pytest.raises(ValueError, match="nome"):
        ler_agenda("0 7 * * * /home/usuario/rodar-tarefa.sh 'Nome Estranho' /l x\n")


_MINUTOS = st.sampled_from(["0", "15", "*/5", "*/10", "30", "0,30"])
_HORAS = st.sampled_from(["*", "3", "7-23", "*/6", "9,13", "0"])
_DIAS_DO_MES = st.sampled_from(["*", "1", "12", "28", "1,15"])
_DIAS_DA_SEMANA = st.sampled_from(["*", "0", "1", "6", "1-5"])


@given(_MINUTOS, _HORAS, _DIAS_DO_MES, _DIAS_DA_SEMANA)
def test_prazo_sempre_passa_do_periodo(minuto, hora, dia_do_mes, dia_da_semana):
    expressao = f"{minuto} {hora} {dia_do_mes} * {dia_da_semana}"
    crontab = f"{expressao} /home/usuario/rodar-tarefa.sh gerada /l x\n"

    (tarefa,) = ler_agenda(crontab)

    assert timedelta(0) < tarefa.periodo <= timedelta(days=31)
    assert tarefa.prazo > tarefa.periodo
