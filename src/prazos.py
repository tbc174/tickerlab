"""Entregas de DFP e ITR fora do prazo da CVM: um sinal de alerta calculado dos dados abertos.

Prazos (Resolução CVM 80, art. 30, II, e art. 31, II; arts. 28 e 29 da Instrução CVM 480 até 2022): a
**DFP** vence 3 meses depois do fim do exercício (4 meses para emissor estrangeiro) e o **ITR**, 45
dias depois do fim do trimestre. A norma diz também "ou na data de envio das demonstrações
financeiras, o que ocorrer primeiro"; essa data não está nos dados abertos, então vale o prazo mais
longo. Prazo que acaba em sábado, domingo ou feriado nacional vai para o primeiro dia útil seguinte
(Res. 80, art. 66-A; feriados de `base/dias_uteis.py`). Feriados estaduais e municipais não contam,
então um atraso de 1 ou 2 dias ainda pode ser só um feriado local (a tela diz isso).

Prorrogações excepcionais da CVM, cada uma lida no texto oficial em 14/10/2026 (`_prorrogado`):
pandemia (Deliberações 849, 852 e 862, de 2020) e enchentes no Rio Grande do Sul (Resolução 202,
de 2024). Conta a **primeira** entrega de cada documento: uma reapresentação depois do prazo não é
atraso.

O atraso costuma acompanhar dificuldades: nos DFP de 2025, boa parte das 52 entregas atrasadas veio
de empresas em recuperação judicial. É um fato a conferir, não uma conclusão.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from base.dias_uteis import feriados_nacionais

FONTE_PRAZO = "cvm_prazo"
MESES_DO_DFP = 3
MESES_DO_DFP_ESTRANGEIRO = 4
DIAS_DO_ITR = 45
ATRASO_GRAVE = 30  # dias: acima disso o alerta pesa mais
NOMES = {"DFP": "DFP (anual)", "ITR": "ITR (trimestral)"}
COLUNAS = [
    "protocolo", "versao", "cnpj", "empresa", "categoria", "tipo", "assunto", "rotulo", "tema",
    "materialidade", "referencia", "publicado_em", "link",
]  # fmt: skip


def _mais_meses(dia: date, meses: int) -> date:
    return (pd.Timestamp(dia) + pd.DateOffset(months=meses)).date()


def trimestre_do_exercicio(referencia: date, mes_fim_do_exercicio: int = 12) -> int:
    """1 a 4: a posição do trimestre que acaba em `referencia` no exercício da empresa."""
    return (referencia.month - mes_fim_do_exercicio - 1) % 12 // 3 + 1


def _prorrogado(
    documento: str,
    referencia: date,
    limite: date,
    mes_fim_do_exercicio: int,
    uf: str | None,
    estrangeiro: bool,
) -> date:
    """O prazo normal (`limite`, antes de passar para dia útil) com as prorrogações da CVM."""
    if documento == "DFP":
        # Deliberação 849/2020, item III, "a", 4 (redação da 852/2020): +2 meses para o emissor
        # nacional com exercício encerrado entre 31/12/2019 e 31/03/2020
        if not estrangeiro and date(2019, 12, 31) <= referencia <= date(2020, 3, 31):
            return _mais_meses(referencia, MESES_DO_DFP + 2)
        return limite
    trimestre = trimestre_do_exercicio(referencia, mes_fim_do_exercicio)
    # Deliberação 849/2020, item IV (redação da 852/2020): +45 dias no 1º trimestre com prazo
    # entre 15/05 e 14/08/2020 e no 3º trimestre com prazo entre 14/04 e 14/06/2020
    if (trimestre == 1 and date(2020, 5, 15) <= limite <= date(2020, 8, 14)) or (
        trimestre == 3 and date(2020, 4, 14) <= limite <= date(2020, 6, 14)
    ):
        return limite + timedelta(days=45)
    # Deliberação 862/2020: +15 dias no ITR de 30/06/2020, só exercício encerrado em dezembro
    if referencia == date(2020, 6, 30) and mes_fim_do_exercicio == 12:
        return limite + timedelta(days=15)
    # Resolução 202/2024 (enchentes): ITR com entrega prevista em maio ou junho de 2024, só para
    # emissor com sede no Rio Grande do Sul, vai para 30/06/2024
    sede_no_rs = (uf or "").strip().upper() == "RS"
    if sede_no_rs and date(2024, 5, 1) <= limite <= date(2024, 6, 30):
        return date(2024, 6, 30)
    return limite


def prazo(
    documento: str,
    referencia: date,
    *,
    mes_fim_do_exercicio: int = 12,
    uf: str | None = None,
    estrangeiro: bool = False,
) -> date:
    """O último dia para entregar o documento, com as prorrogações e já passado para dia útil.

    `mes_fim_do_exercicio` diz qual trimestre do exercício é o ITR (as prorrogações de 2020
    dependem disso); `uf` é o estado da sede (a de 2024 só vale para o RS).
    """
    if documento == "DFP":
        meses = MESES_DO_DFP_ESTRANGEIRO if estrangeiro else MESES_DO_DFP
        limite = _mais_meses(referencia, meses)
    else:
        limite = referencia + timedelta(days=DIAS_DO_ITR)
    limite = _prorrogado(
        documento, referencia, limite, mes_fim_do_exercicio, uf, estrangeiro
    )
    feriados = feriados_nacionais(limite.year) + feriados_nacionais(limite.year + 1)
    return np.busday_offset(limite, 0, roll="forward", holidays=feriados).astype(object)


def _data_br(dia: date) -> str:
    return f"{dia:%d/%m/%Y}"


def eventos_de_atraso(entregas: pd.DataFrame) -> pd.DataFrame:
    """Os documentos entregues depois do prazo, no formato da tabela de eventos.

    `entregas`: cnpj, empresa, documento, referencia, primeira_entrega, link (a primeira versão).
    """
    linhas = []
    for e in entregas.itertuples(index=False):
        if pd.isna(e.primeira_entrega):
            continue
        limite = prazo(e.documento, e.referencia)
        dias = (e.primeira_entrega - limite).days
        if dias <= 0:
            continue
        linhas.append(
            {
                "protocolo": f"prazo-{e.documento}-{e.cnpj}-{e.referencia:%Y-%m-%d}",
                "versao": 1,
                "cnpj": e.cnpj,
                "empresa": e.empresa,
                "categoria": "Entrega fora do prazo",
                "tipo": e.documento,
                "assunto": (
                    f"{NOMES[e.documento]} com data-base {_data_br(e.referencia)} entregue em "
                    f"{_data_br(e.primeira_entrega)}, {dias} dia{'s' if dias > 1 else ''} "
                    f"depois do prazo ({_data_br(limite)})."
                ),
                "rotulo": f"{e.documento} entregue fora do prazo",
                "tema": "risco",
                "materialidade": 80 if dias > ATRASO_GRAVE else 50,
                "referencia": e.referencia,
                "publicado_em": e.primeira_entrega,
                "link": e.link,
            }
        )
    tabela = pd.DataFrame(linhas, columns=COLUNAS)
    return tabela.sort_values("publicado_em", ascending=False).reset_index(drop=True)
