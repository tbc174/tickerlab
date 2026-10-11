"""TickerLab Trade: o que a página mostra sobre a pesquisa de trading quantitativo.

A pesquisa roda no PC do Tiago (pasta `trader/`, MetaTrader 5 em conta de demonstração) e fica
fora do site. Esta página só explica o projeto e mostra em que fase ele está; quando terminar,
ela vira a página de download do relatório e do painel. Para atualizar a página, mude só aqui
(a fase atual e, no fim, os downloads).

Regra da marca: nada de promessa de rentabilidade. Resultado negativo também é publicado.
"""

from dataclasses import dataclass

FEITA = "feita"
AGORA = "agora"
DEPOIS = "depois"


@dataclass(frozen=True)
class Fase:
    codigo: str
    nome: str
    estado: str  # FEITA, AGORA ou DEPOIS
    explicacao: str


FASES = (
    Fase("M0", "Ambiente", FEITA, "MetaTrader 5 em conta de demonstração, só leitura."),
    Fase(
        "M1",
        "Dados",
        FEITA,
        "Histórico diário de mais de 80 ativos, com checagem de qualidade.",
    ),
    Fase(
        "M2",
        "Pesquisa com ML",
        AGORA,
        "Modelos testados com regras de aprovação escritas antes de ver os resultados.",
    ),
    Fase(
        "M3", "Teste em conta demo", DEPOIS, "Só se um modelo passar no critério da M2."
    ),
    Fase(
        "M4",
        "Controles de risco",
        DEPOIS,
        "Limites de perda e de exposição antes de tudo.",
    ),
    Fase("M5", "Painel", DEPOIS, "Programa para acompanhar a pesquisa e o teste."),
)


@dataclass(frozen=True)
class Download:
    titulo: str
    descricao: str
    disponivel: bool = False  # True quando o arquivo existir (no fim do projeto)


DOWNLOADS = (
    Download(
        "Relatório da pesquisa",
        "O que foi testado, o que passou e o que não passou, com os números.",
    ),
    Download(
        "Painel do trader",
        "Programa para Windows, só leitura, que acompanha a pesquisa com o MetaTrader 5.",
    ),
)


def fase_atual() -> Fase:
    return next(f for f in FASES if f.estado == AGORA)
