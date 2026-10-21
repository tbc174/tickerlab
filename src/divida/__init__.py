"""Dívida de um emissor (protótipo B, DCM, do dossiê da plataforma modular; B-21).

`instrumentos`: a dívida que já existe, como `DebtInstrument`, lida pela porta da base e "como era"
no dia. `perfil`: o perfil de vencimentos por ano e indexador, cada número com o rastro. `nota_dfp`: o
cronograma de vencimentos da nota de endividamento da DFP (o grupo inteiro), lido por regra.
`capacidade` (B-22): quanto mais de dívida cabe pelas regras que quem usa declara (alavancagem,
cobertura de juros, caixa mínimo), com a regra que amarra e a sensibilidade a choques. Nada aqui
é opinião de risco nem recomendação; o que a fonte não diz fica "não observado".
`simulador` (B-23): o fluxo de juros e amortização de um instrumento novo (pré, CDI ou IPCA; SAC,
Price ou bullet; carência), com a curva de juros `curva_do_dia` como era no dia, sem extrapolar.
"""

from src.divida.curva_do_dia import (
    CurvaDoDia,
    ForaDaCurva,
    curva_como_era,
)
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
from src.divida.simulador import Instrumento, Periodo, Simulacao, simular

__all__ = [
    "NAO_OBSERVADO",
    "CronogramaDaNota",
    "CurvaDoDia",
    "DebtInstrument",
    "FaixaDaNota",
    "FaixaDoPerfil",
    "ForaDaCurva",
    "Instrumento",
    "PerfilDeVencimentos",
    "Periodo",
    "Simulacao",
    "curva_como_era",
    "faixas_da_serie",
    "instrumentos_das_ofertas",
    "instrumentos_do_emissor",
    "ler_cronogramas",
    "perfil_de_vencimentos",
    "serie_do_total",
    "simular",
]
