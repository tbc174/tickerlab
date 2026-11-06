"""Os eventos de PJ do informe mensal de FIDC (CVM): o primeiro caso dos três estados.

- **mudou:** os eventos de monitoramento da B-15 (`src/securitizacao/monitoramento.py`), cada um
  como evento de PJ (`EventoDeMonitoramento.como_evento_de_pj`).
- **não observado:** o fundo que entregou o mês anterior e não entregou o mês até o prazo (a
  competência mais `base.fidc.DIAS_ATE_FICAR_PUBLICO` dias). A entrega atrasada não apaga o atraso:
  o evento é do dia do prazo, com o que era público naquele dia.
- **fonte falhou:** o mês sem nenhuma leitura boa do arquivo até o prazo (`Tentativa`, do registro
  de coletas por `registro.tentativas_da_url`); vale para cada fundo que se esperava, e nenhum
  deles conta como ausente.

As linhas são as de `monitoramento.leituras_dos_informes` (uma por fundo-mês, com `disponivel_em`).
"""

from collections.abc import Iterable
from datetime import date, timedelta

import pandas as pd

from base.fidc import DIAS_ATE_FICAR_PUBLICO
from src.eventos_de_pj.evento import (
    DescricaoDaFonte,
    EventoDePJ,
    Leitura,
    Tentativa,
    cnpj_do_objeto,
    em_ordem,
    eventos_das_leituras,
    leitura_ok,
)
from src.securitizacao import monitoramento

DESCRICAO = DescricaoDaFonte(
    fonte=monitoramento.FONTE_DO_INFORME,
    objeto_tipo="fundo",
    documento="informe mensal de FIDC (CVM)",
    versao_do_calculo="eventos_fidc 1",
    formula="fundo esperado = entregou o mês anterior; prazo = competência + 45 dias",
)


def prazo(competencia: date) -> date:
    """O dia em que se confere quem entregou o mês: o piso da regra do prazo da CVM."""
    return competencia + timedelta(days=DIAS_ATE_FICAR_PUBLICO)


def _competencias(
    leituras: pd.DataFrame, tentativas: Iterable[Tentativa]
) -> list[date]:
    dos_informes = {pd.Timestamp(c).date() for c in leituras["competencia"]}
    return sorted(dos_informes | {t.periodo for t in tentativas})


def _leitura_do_mes(
    leituras: pd.DataFrame, competencia: date, tentativas: list[Tentativa]
) -> Leitura:
    """O que se via do mês no dia do prazo: os fundos com informe público até lá."""
    dia = prazo(competencia)
    do_mes = leituras[
        (leituras["competencia"] == pd.Timestamp(competencia))
        & (pd.to_datetime(leituras["disponivel_em"]) <= pd.Timestamp(dia))
    ]
    return Leitura(
        periodo=competencia,
        publico_em=dia,
        ok=leitura_ok(tentativas, competencia, dia),
        objetos={str(cnpj): {} for cnpj in do_mes["cnpj_fundo"]},
    )


def eventos_do_fidc(
    leituras: pd.DataFrame,
    tentativas: Iterable[Tentativa],
    *,
    como_em: date | None = None,
    cnpjs: Iterable[str] | None = None,
) -> list[EventoDePJ]:
    """Os eventos dos fundos nos três estados, só com o que era público em `como_em` (padrão: tudo).

    `cnpjs` limita aos fundos pedidos (com ou sem pontuação); eles passam a ser os esperados.
    """
    tentativas = [t for t in tentativas if como_em is None or t.dia <= como_em]
    visiveis = (
        leituras if como_em is None else monitoramento.como_era_em(leituras, como_em)
    )
    pedidos = None if cnpjs is None else {cnpj_do_objeto(c) for c in cnpjs}
    if pedidos is not None:
        visiveis = visiveis[visiveis["cnpj_fundo"].map(cnpj_do_objeto).isin(pedidos)]
    competencias = _competencias(visiveis, tentativas)
    meses = [
        _leitura_do_mes(visiveis, c, tentativas)
        for c in competencias
        if como_em is None or prazo(c) <= como_em
    ]
    mudou = [
        evento.como_evento_de_pj()
        for competencia in competencias
        for evento in monitoramento.eventos_do_mes(
            visiveis, competencia, como_em=como_em
        )
    ]
    return em_ordem(
        [*eventos_das_leituras(meses, DESCRICAO, esperados=pedidos), *mudou]
    )
