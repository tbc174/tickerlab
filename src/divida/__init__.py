"""Dívida de um emissor (protótipo B, DCM, do dossiê da plataforma modular; B-21).

`instrumentos`: a dívida que já existe, como `DebtInstrument`, lida pela porta da base e "como era"
no dia. `perfil`: o perfil de vencimentos por ano e indexador, cada número com o rastro. `nota_dfp`: o
cronograma de vencimentos da nota de endividamento da DFP (o grupo inteiro), lido por regra. Nada aqui
é opinião de risco nem recomendação; o que a fonte não diz fica "não observado".
"""

from src.divida.instrumentos import (
    NAO_OBSERVADO,
    DebtInstrument,
    instrumentos_das_ofertas,
    instrumentos_do_emissor,
)
from src.divida.nota_dfp import (
    CronogramaDaNota,
    FaixaDaNota,
    faixas_da_serie,
    ler_cronogramas,
    serie_do_total,
)
from src.divida.perfil import FaixaDoPerfil, PerfilDeVencimentos, perfil_de_vencimentos

__all__ = [
    "NAO_OBSERVADO",
    "CronogramaDaNota",
    "DebtInstrument",
    "FaixaDaNota",
    "FaixaDoPerfil",
    "PerfilDeVencimentos",
    "faixas_da_serie",
    "instrumentos_das_ofertas",
    "instrumentos_do_emissor",
    "ler_cronogramas",
    "perfil_de_vencimentos",
    "serie_do_total",
]
