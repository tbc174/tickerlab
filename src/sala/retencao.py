"""Prazos de guarda da sala de dados (decisão D14 do plano do B-20).

Toda operação tem uma data em que some sozinha (`retencao_ate`): a pessoa escolhe 90, 180 ou 365
dias ao criar, pode prorrogar até 365 dias por vez, e encerrar a operação deixa 30 dias para baixar
a sala antes do expurgo. As datas são as de Brasília, como a pessoa as vê no app.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

PRAZOS_DE_GUARDA_EM_DIAS = (90, 180, 365)
PRAZO_PADRAO_EM_DIAS = 180
DIAS_PARA_BAIXAR_DEPOIS_DE_ENCERRAR = 30
PRORROGACAO_MAXIMA_EM_DIAS = 365

FUSO_DE_BRASILIA = ZoneInfo("America/Sao_Paulo")


def hoje_em_brasilia() -> date:
    """A data de hoje em Brasília."""
    return datetime.now(FUSO_DE_BRASILIA).date()


def prazo_inicial(hoje: date, dias: int = PRAZO_PADRAO_EM_DIAS) -> date:
    """A data em que uma operação criada hoje some; `dias` precisa ser 90, 180 ou 365."""
    if dias not in PRAZOS_DE_GUARDA_EM_DIAS:
        raise ValueError(f"O prazo de guarda é de {PRAZOS_DE_GUARDA_EM_DIAS} dias.")
    return hoje + timedelta(days=dias)


def prazo_ao_encerrar(hoje: date) -> date:
    """A data em que uma operação encerrada hoje some (o tempo de baixar a sala)."""
    return hoje + timedelta(days=DIAS_PARA_BAIXAR_DEPOIS_DE_ENCERRAR)


def prazo_prorrogado(atual: date, hoje: date, dias: int) -> date:
    """O prazo depois de prorrogar `dias` a partir de hoje; prorrogar nunca encurta o prazo."""
    if not 1 <= dias <= PRORROGACAO_MAXIMA_EM_DIAS:
        raise ValueError(f"Prorrogue de 1 a {PRORROGACAO_MAXIMA_EM_DIAS} dias por vez.")
    return max(atual, hoje + timedelta(days=dias))
