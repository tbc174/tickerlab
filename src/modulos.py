"""Os módulos do TickerLab e o que cada um faz: o que já está no app e o que vem por aí.

É a fonte da página "Produto" do site (e de qualquer outro lugar que liste funcionalidades). O
manual de identidade manda descrever como disponível só o que já existe: cada funcionalidade diz
se está no app (com a página dele) ou se ainda está em construção ("Em breve", sem link). As ideias
futuras vêm do catálogo do Documento Mestre v3, seção 09.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Funcionalidade:
    nome: str
    descricao: str
    pagina_do_app: str | None = (
        None  # URL da página no app (src/paginas.py); None = em breve
    )
    ticker: str | None = None  # abre a página já com um ativo de exemplo

    @property
    def disponivel(self) -> bool:
        return self.pagina_do_app is not None


@dataclass(frozen=True)
class Modulo:
    chave: str  # âncora na página Produto
    nome: str
    objetivo: str  # o que a pessoa quer fazer (o "olho" acima do nome)
    frase: str
    funcionalidades: tuple[Funcionalidade, ...]

    @property
    def disponiveis(self) -> int:
        return sum(f.disponivel for f in self.funcionalidades)

    @property
    def em_breve(self) -> int:
        return len(self.funcionalidades) - self.disponiveis


EXEMPLO = "PETR4.SA"
# A planilha da B3 (aberta a todos); "carteira" é a Carteira de Estratégias (backtest)
CARTEIRA_B3 = "carteira-b3"

MODULOS = (
    Modulo(
        "research",
        "Research",
        "Entender um ativo",
        "Preço, risco e os documentos oficiais de uma empresa, explicados em português.",
        (
            Funcionalidade(
                "Visão geral do ativo",
                "Retorno, risco e os dias mais extremos de ações, ETFs, índices e cripto.",
                "visao-geral",
                EXEMPLO,
            ),
            Funcionalidade(
                "Risco e retorno mês a mês",
                "Volatilidade, maiores quedas, meses bons e ruins.",
                "risco",
                EXEMPLO,
            ),
            Funcionalidade(
                "Comparar ativos", "Lado a lado, com correlação e beta.", "comparar"
            ),
            Funcionalidade(
                "Fundamentos",
                "Receita, lucro e indicadores calculados dos documentos da CVM e da SEC.",
                "fundamentos",
            ),
            Funcionalidade(
                "Acontecimentos",
                "Fatos relevantes e comunicados, com o link para o documento original.",
                "research",
            ),
            Funcionalidade(
                "Pessoas de dentro e donos",
                "Compras e vendas de administradores e quem são os grandes acionistas.",
                "por-dentro",
            ),
            Funcionalidade(
                "Pulse", "O resumo do que mudou nos seus ativos desde a última visita."
            ),
            Funcionalidade(
                "Calendário", "Resultados, assembleias e proventos que vêm pela frente."
            ),
            Funcionalidade(
                "Linha do tempo",
                "Preço e acontecimentos da empresa num só eixo.",
                "linha-do-tempo",
                EXEMPLO,
            ),
            Funcionalidade(
                "Diário de Teses",
                "Escreva por que acompanha um ativo e revisite a ideia depois.",
            ),
        ),
    ),
    Modulo(
        "carteira",
        "Carteira",
        "Cuidar da carteira",
        "Sua posição da B3 lida só na memória, com concentração e risco.",
        (
            Funcionalidade(
                "Importar a planilha da B3",
                "A posição da Área do Investidor, sem guardar o arquivo.",
                CARTEIRA_B3,
            ),
            Funcionalidade(
                "Concentração e número efetivo",
                "Quanto da carteira depende de poucos ativos.",
                CARTEIRA_B3,
            ),
            Funcionalidade(
                "A carteira no passado",
                "Como a carteira de hoje teria se comportado, comparada ao Ibovespa.",
                CARTEIRA_B3,
            ),
            Funcionalidade(
                "Alertas",
                "Avisos quando uma condição combinada acontece com os seus ativos.",
                "alertas",
            ),
            Funcionalidade(
                "Raio-X", "Exposição por setor, moeda e tipo de ativo.", CARTEIRA_B3
            ),
            Funcionalidade(
                "Rebalanceamento",
                "Quanto comprar ou vender para voltar ao peso que você escolheu.",
                CARTEIRA_B3,
            ),
            Funcionalidade(
                "Dividendos e custo médio",
                "Proventos recebidos e preço médio por ativo.",
            ),
        ),
    ),
    Modulo(
        "estrategias",
        "Estratégias",
        "Testar uma ideia",
        "Regras de compra e venda testadas no passado, com custos e sem olhar o futuro.",
        (
            Funcionalidade(
                "Backtest",
                "12 estratégias, com custos de corretagem, impostos e o CDI no caixa.",
                "backtest",
                EXEMPLO,
            ),
            Funcionalidade(
                "Ranking de estratégias",
                "Todas as estratégias no mesmo ativo, lado a lado.",
                "ranking",
            ),
            Funcionalidade(
                "Validação honesta",
                "Fora da amostra e teste contra o acaso: mostra quando a estratégia não funciona.",
                "experimentos",
            ),
            Funcionalidade(
                "Fases do mercado",
                "Como a estratégia se sai em alta, queda e lateralidade.",
                "regimes",
            ),
            Funcionalidade(
                "Aprendizado de máquina e pairs trading",
                "Modelos e pares de ativos, no plano Pro.",
                "aprendizado",
            ),
            Funcionalidade(
                "Replay", "Rever o passado dia a dia, como se estivesse acontecendo."
            ),
            Funcionalidade(
                "Testes de robustez",
                "A mesma estratégia com parâmetros e períodos diferentes.",
            ),
        ),
    ),
    Modulo(
        "relatorios",
        "Relatórios",
        "Guardar e compartilhar",
        "Seu estudo em PDF, com a prévia de verdade antes de baixar.",
        (
            Funcionalidade(
                "Report Studio",
                "Modelo, seções e estilo, com a prévia do PDF real.",
                "relatorio",
            ),
            Funcionalidade(
                "Três estilos",
                "Research claro, Terminal escuro e Institucional, os mesmos números.",
                "relatorio",
            ),
            Funcionalidade(
                "PDFs originais guardados",
                "O arquivo exato que você gerou, para baixar de novo.",
                "relatorio",
            ),
            Funcionalidade("Newsletter", "Os acontecimentos da sua lista por e-mail."),
            Funcionalidade(
                "Compartilhamento seguro",
                'Um link privado, com prazo e revogável, para a ficha "Foi sorte?" ou um PDF.',
                "relatorio",
            ),
            Funcionalidade(
                "Comparações em PDF",
                "Dois ou mais ativos no mesmo relatório.",
                "relatorio",
            ),
        ),
    ),
    Modulo(
        "mercado",
        "Mercado",
        "Acompanhar o mercado",
        "Juros, inflação, câmbio e as principais cotações, com a fonte e a hora de cada dado.",
        (
            Funcionalidade(
                "Juros e inflação",
                "CDI, Selic e IPCA com as séries oficiais do Banco Central.",
                "juros-e-inflacao",
            ),
            Funcionalidade(
                "Cotações", "B3, EUA, câmbio e cripto, com o atraso de cada fonte."
            ),
            Funcionalidade(
                "Qualidade dos dados",
                "De onde veio cada número, quando foi conferido e o que está faltando.",
                "fundamentos",  # o selo "em conferência" dos documentos da CVM
                EXEMPLO,
            ),
        ),
    ),
    Modulo(
        "ferramentas",
        "Ferramentas",
        "Fazer as contas",
        "Calculadoras simples, abertas para todos, sem cadastro.",
        (
            Funcionalidade(
                "Juros simples e compostos", "Quanto um valor rende ao longo do tempo."
            ),
            Funcionalidade(
                "Aportes e metas",
                "Quanto guardar por mês para chegar a um objetivo.",
            ),
            Funcionalidade(
                "Conversores",
                "Taxa anual em mensal, percentual do CDI em taxa e outros.",
            ),
        ),
    ),
    Modulo(
        "aprender",
        "Aprender",
        "Aprender fazendo",
        "Cada conceito ligado a uma ação no produto.",
        (
            Funcionalidade(
                "Tutorial de 2 minutos",
                "A primeira análise guiada, com dados de verdade.",
                "visao-geral",
                EXEMPLO,
            ),
            Funcionalidade(
                "Guia e glossário", "Os termos do app explicados em português.", "guia"
            ),
            Funcionalidade(
                "Trilhas", "Sequências curtas, do primeiro ativo ao primeiro relatório."
            ),
        ),
    ),
)
POR_CHAVE = {m.chave: m for m in MODULOS}
