"""Os módulos do TickerLab e o que cada um faz: o que já está no app e o que vem por aí.

É a fonte da página "Produto" do site (e de qualquer outro lugar que liste funcionalidades). O
manual de identidade manda descrever como disponível só o que já existe: cada funcionalidade diz
se está no app (com a página dele), no site (as ferramentas grátis) ou se ainda está em construção ("Em breve", sem link). As ideias
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
    # página do site público (as ferramentas grátis, sem cadastro): "calculadora-de-....html"
    pagina_do_site: str | None = None

    @property
    def disponivel(self) -> bool:
        return self.pagina_do_app is not None or self.pagina_do_site is not None


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
                "Relatório da empresa",
                "Resultado, dívida, caixa, notas clássicas e valuation de uma empresa da B3, com a fonte de cada número.",
                "relatorio-empresa",
            ),
            Funcionalidade(
                "Donos e fundos",
                "Quais fundos e grandes gestores têm a ação, quem entrou e quem saiu.",
                "donos",
            ),
            Funcionalidade(
                "Busca por CNPJ",
                "Digite o CNPJ de uma companhia aberta e veja de que grupo ela faz parte e os fatos públicos, com data e fonte.",
                "busca-por-cnpj",
            ),
            Funcionalidade(
                "Pulse",
                "O resumo do que mudou nos seus ativos desde a última visita.",
                "pulse",
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
                "diario-de-teses",
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
                CARTEIRA_B3,
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
            Funcionalidade(
                "Newsletter", "Os acontecimentos da sua lista por e-mail.", "newsletter"
            ),
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
                "Juros simples e compostos",
                "Quanto um valor rende ao longo do tempo.",
                pagina_do_site="calculadora-de-juros-compostos.html",
            ),
            Funcionalidade(
                "Aportes e metas",
                "Quanto guardar por mês para chegar a um objetivo.",
                pagina_do_site="calculadora-de-aportes-e-metas.html",
            ),
            Funcionalidade(
                "Conversor de moedas",
                "Dólar, euro, libra e mais 7 moedas pela PTAX do Banco Central.",
                pagina_do_site="conversor-de-moedas.html",
            ),
            Funcionalidade(
                "Renda fixa com IR",
                "CDB, LCI/LCA, Tesouro Selic e poupança pelo mesmo prazo, sem o imposto.",
                pagina_do_site="calculadora-de-renda-fixa.html",
            ),
            Funcionalidade(
                "Juro real e taxas",
                "Quanto rende acima da inflação, e taxa ao mês ou ao ano.",
                pagina_do_site="calculadora-de-juro-real.html",
            ),
            Funcionalidade(
                "Correção pela inflação",
                "Quanto um valor do passado vale hoje, pelo IPCA.",
                pagina_do_site="calculadora-de-correcao-pela-inflacao.html",
            ),
            Funcionalidade(
                "Custo das taxas e da queda",
                "Quanto 1% ao ano leva em 20 anos, e quanto subir depois de cair.",
                pagina_do_site="custo-das-taxas-e-da-queda.html",
            ),
            Funcionalidade(
                "Viver de renda",
                "Quanto juntar para tirar um valor por mês, em dinheiro de hoje.",
                pagina_do_site="calculadora-viver-de-renda.html",
            ),
            Funcionalidade(
                "Sorte em série",
                "Cem estratégias de cara ou coroa: a melhor parece genial por acaso.",
                pagina_do_site="sorte-em-serie.html",
            ),
            Funcionalidade(
                "Imposto sobre ações (DARF)",
                "O imposto do mês, a isenção de R$ 20 mil e o prejuízo a compensar.",
                pagina_do_site="calculadora-de-darf.html",
            ),
            Funcionalidade(
                "Preço médio",
                "O preço médio de ações e FIIs, com as mesmas regras do app.",
                pagina_do_site="calculadora-de-preco-medio.html",
            ),
            Funcionalidade(
                "Fundo ou CDB",
                "Um fundo DI, com taxas e come-cotas, contra um CDB no mesmo prazo.",
                pagina_do_site="fundo-ou-cdb.html",
            ),
            Funcionalidade(
                "Financiamento SAC ou Price",
                "As parcelas dos dois sistemas lado a lado, com amortização extra.",
                pagina_do_site="simulador-de-financiamento.html",
            ),
            Funcionalidade(
                "Quanto daria? Foi sorte?",
                "Quanto um valor aplicado num mês teria virado, e se a data foi sorte.",
                pagina_do_site="quanto-daria.html",
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
