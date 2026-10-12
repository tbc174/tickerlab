"""Entregas de DFP e ITR fora do prazo da CVM: um sinal de alerta calculado dos dados abertos.

Prazos (Resolução CVM 80, arts. 28 e 29): o **DFP** vence 3 meses depois do fim do exercício e o
**ITR**, 45 dias depois do fim do trimestre. Prazo que cai em fim de semana vai para a segunda;
feriados não são considerados, então um atraso de 1 ou 2 dias pode ser só um feriado (a tela diz
isso). Conta a **primeira** entrega de cada documento: uma reapresentação depois do prazo não é
atraso.

O atraso costuma acompanhar dificuldades: nos DFP de 2025, boa parte das 52 entregas atrasadas veio
de empresas em recuperação judicial. É um fato a conferir, não uma conclusão.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

FONTE_PRAZO = "cvm_prazo"
MESES_DO_DFP = 3
DIAS_DO_ITR = 45
ATRASO_GRAVE = 30  # dias: acima disso o alerta pesa mais
NOMES = {"DFP": "DFP (anual)", "ITR": "ITR (trimestral)"}
COLUNAS = [
    "protocolo", "versao", "cnpj", "empresa", "categoria", "tipo", "assunto", "rotulo", "tema",
    "materialidade", "referencia", "publicado_em", "link",
]  # fmt: skip


def prazo(documento: str, referencia: date) -> date:
    """O último dia para entregar o documento, já passado para dia útil (sem feriados)."""
    if documento == "DFP":
        limite = (pd.Timestamp(referencia) + pd.DateOffset(months=MESES_DO_DFP)).date()
    else:
        limite = referencia + timedelta(days=DIAS_DO_ITR)
    return np.busday_offset(limite, 0, roll="forward").astype(object)


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
