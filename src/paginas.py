"""O mapa do site: quais páginas existem, em que grupo ficam e para que servem.

A tela monta o menu a partir desta lista, e a página inicial também. Para renomear uma página,
mudar o texto de ajuda ou trocar de grupo, é só mexer aqui.
"""

from dataclasses import dataclass

from src.planos import APRENDIZADO_DE_MAQUINA, PARES

GRUPO_COMECAR = "Começar"
GRUPO_ANALISAR = "Analisar"
GRUPO_ESTRATEGIAS = "Estratégias"
GRUPO_AVANCADO = "Avançado (Pro)"
GRUPO_CONTA = "Minha conta"
GRUPOS = (
    GRUPO_COMECAR,
    GRUPO_ANALISAR,
    GRUPO_ESTRATEGIAS,
    GRUPO_AVANCADO,
    GRUPO_CONTA,
)

FRASE_DE_CADA_GRUPO = {
    GRUPO_COMECAR: "O que é o TickerLab e como usar.",
    GRUPO_ANALISAR: "Entenda um ativo: preço, risco e comportamento ao longo do tempo.",
    GRUPO_ESTRATEGIAS: "Teste regras de compra e venda no passado, com custos.",
    GRUPO_AVANCADO: "Ferramentas mais técnicas, do plano Pro.",
    GRUPO_CONTA: "O que é seu: simulações guardadas, favoritos e plano.",
}


@dataclass(frozen=True)
class Pagina:
    chave: str
    titulo: str
    grupo: str
    icone: str  # ícone do Material (o Streamlit mostra no menu)
    descricao: str  # uma frase: para que serve esta página
    recurso: str | None = None  # recurso do plano que a página exige (None = livre)
    precisa_do_ativo: bool = True  # mostra os campos de ativo e período no topo

    @property
    def url(self) -> str:
        return self.chave.replace("_", "-")

    @property
    def e_pro(self) -> bool:
        return self.recurso is not None


PAGINAS = (
    Pagina(
        "inicio",
        "Início",
        GRUPO_COMECAR,
        ":material/home:",
        "Comece por aqui: o que é o TickerLab e o caminho mais curto para usá-lo.",
        precisa_do_ativo=False,
    ),
    Pagina(
        "guia",
        "Guia e glossário",
        GRUPO_COMECAR,
        ":material/menu_book:",
        "Como os números são calculados, os limites do app e cada termo explicado em português.",
        precisa_do_ativo=False,
    ),
    Pagina(
        "visao_geral",
        "Visão geral",
        GRUPO_ANALISAR,
        ":material/dashboard:",
        "O preço do ativo e os números-chave: retorno, risco e os dias mais extremos.",
    ),
    Pagina(
        "risco",
        "Risco",
        GRUPO_ANALISAR,
        ":material/shield:",
        "Quanto o ativo já caiu e o quanto o preço oscila ao longo do tempo.",
    ),
    Pagina(
        "retorno_mensal",
        "Retorno mensal",
        GRUPO_ANALISAR,
        ":material/calendar_month:",
        "Como o ativo foi em cada mês e ano, e se existem meses melhores que outros.",
    ),
    Pagina(
        "comparar",
        "Comparar ativos",
        GRUPO_ANALISAR,
        ":material/compare_arrows:",
        "Coloque dois ou mais ativos lado a lado, com o Ibovespa e o S&P 500 de referência.",
    ),
    Pagina(
        "correlacao",
        "Correlação e beta",
        GRUPO_ANALISAR,
        ":material/hub:",
        "Quanto o ativo anda junto com outros e com o mercado (o beta mede essa sensibilidade).",
    ),
    Pagina(
        "backtest",
        "Backtest",
        GRUPO_ESTRATEGIAS,
        ":material/history:",
        "Teste no passado: e se eu tivesse seguido esta regra de compra e venda?",
    ),
    Pagina(
        "ranking",
        "Ranking de estratégias",
        GRUPO_ESTRATEGIAS,
        ":material/leaderboard:",
        "Todas as estratégias no mesmo ativo, da melhor à pior, e quanto do resultado pode ser sorte.",
    ),
    Pagina(
        "carteira",
        "Carteira",
        GRUPO_ESTRATEGIAS,
        ":material/pie_chart:",
        "Várias ações ao mesmo tempo, com regras para dividir o dinheiro entre elas.",
    ),
    Pagina(
        "experimentos",
        "Experimentos",
        GRUPO_ESTRATEGIAS,
        ":material/science:",
        "Perguntas clássicas respondidas com dados: aportar de uma vez ou aos poucos, rebalancear, virada do mês.",
    ),
    Pagina(
        "regimes",
        "Fases do mercado",
        GRUPO_ESTRATEGIAS,
        ":material/waves:",
        "Como uma estratégia se comporta em fases calmas e agitadas, e proteções contra quedas fortes.",
    ),
    Pagina(
        "aprendizado",
        "Aprendizado de máquina",
        GRUPO_AVANCADO,
        ":material/psychology:",
        "Modelos que tentam prever o mercado, com validação honesta do que realmente funciona.",
        recurso=APRENDIZADO_DE_MAQUINA,
    ),
    Pagina(
        "pares",
        "Pairs trading",
        GRUPO_AVANCADO,
        ":material/swap_horiz:",
        "Apostar que dois ativos ligados voltam a andar juntos depois de se afastarem.",
        recurso=PARES,
    ),
    Pagina(
        "simulacoes",
        "Minhas simulações",
        GRUPO_CONTA,
        ":material/bookmarks:",
        "As simulações que você guardou: reabra para recalcular com os dados de hoje ou apague.",
        precisa_do_ativo=False,
    ),
    Pagina(
        "momentum",
        "Favoritos e momentum",
        GRUPO_CONTA,
        ":material/star:",
        "Seus ativos favoritos ordenados pela força da tendência recente (momentum).",
    ),
    Pagina(
        "planos",
        "Planos e assinatura",
        GRUPO_CONTA,
        ":material/workspace_premium:",
        "Seu plano, o que ele inclui, quanto você já usou e como assinar o Pro.",
        precisa_do_ativo=False,
    ),
)

POR_CHAVE = {p.chave: p for p in PAGINAS}
PAGINA_INICIAL = "inicio"


def paginas_do_grupo(grupo: str) -> list[Pagina]:
    return [p for p in PAGINAS if p.grupo == grupo]


def pagina(chave: str) -> Pagina:
    return POR_CHAVE[chave]
