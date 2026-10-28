"""O mapa do site: quais páginas existem, em que grupo ficam e para que servem.

A tela monta o menu a partir desta lista, e a página inicial também. Para renomear uma página,
mudar o texto de ajuda ou trocar de grupo, é só mexer aqui.
"""

from dataclasses import dataclass

from src.planos import APRENDIZADO_DE_MAQUINA, PARES, motivo_sem_acesso

# Páginas sem grupo: aparecem direto na barra do menu (o Streamlit as põe no começo)
GRUPO_TOPO = ""
GRUPO_ANALISAR = "Analisar"
GRUPO_ESTRATEGIAS = "Estratégias"
GRUPO_AVANCADO = "Avançado (Pro)"
GRUPO_RESEARCH = "Research"
GRUPO_APRENDER = "Aprender"
GRUPO_CONTA = "Minha conta"
GRUPO_MAIS = "Mais"  # experimental e menos usado (blueprint: TickerLab Trade fica aqui como Beta)
GRUPO_ADMIN = "Administração"
GRUPOS = (
    GRUPO_TOPO,
    GRUPO_ANALISAR,
    GRUPO_ESTRATEGIAS,
    GRUPO_AVANCADO,
    GRUPO_RESEARCH,
    GRUPO_APRENDER,
    GRUPO_CONTA,
    GRUPO_MAIS,
    GRUPO_ADMIN,
)

FRASE_DE_CADA_GRUPO = {
    GRUPO_TOPO: "O começo e os relatórios do TickerLab.",
    GRUPO_MAIS: "Linhas experimentais, ainda em pesquisa.",
    GRUPO_APRENDER: "Como os números são calculados, os limites do app e cada termo explicado.",
    GRUPO_ANALISAR: "Entenda um ativo: preço, risco e comportamento ao longo do tempo.",
    GRUPO_ESTRATEGIAS: "Teste regras de compra e venda no passado, com custos.",
    GRUPO_AVANCADO: "Ferramentas mais técnicas, do plano Pro.",
    GRUPO_RESEARCH: "Pesquisa sob medida: você escolhe como analisar, e cada número diz de onde veio.",
    GRUPO_CONTA: "O que é seu: simulações guardadas, favoritos, plano e privacidade.",
    GRUPO_ADMIN: "Só para administradores: usuários, planos e assinaturas.",
}


# --- Áreas do app novo (ADR 0096) -----------------------------------------------------------
# O app em React organiza o menu por área, não pelo grupo do Streamlit (que não muda). O mapa vem da
# pesquisa de organização do app (§5); trocar uma página de área é mexer só no `area=` dela.


@dataclass(frozen=True)
class Area:
    rotulo: str  # o nome no menu e nas abas do celular
    icone: str  # o nome do ícone em web/src/app/areas.ts (SVG desenhado lá, sem biblioteca)
    frase: str  # uma frase: o que a pessoa encontra nesta área
    ordem: int


AREA_INICIO = "inicio"
AREA_ATIVO = "ativo"
AREA_ESTRATEGIAS = "estrategias"
AREA_ACOMPANHAR = "acompanhar"
AREA_CONTA = "conta"  # no menu da pessoa, no topo
AREA_AJUDA = "ajuda"  # no rodapé, fora do menu principal
AREAS = {
    AREA_INICIO: Area(
        "Início", "inicio", "O que mudou nos seus ativos e por onde começar.", 1
    ),
    AREA_ATIVO: Area(
        "Ativo",
        "ativo",
        "Entenda um ativo: preço, risco, a empresa e quem tem a ação.",
        2,
    ),
    AREA_ESTRATEGIAS: Area(
        "Estratégias",
        "estrategias",
        "Teste regras de compra e venda no passado, com custos.",
        3,
    ),
    AREA_ACOMPANHAR: Area(
        "Acompanhar",
        "acompanhar",
        "O que você acompanha: acontecimentos, teses, carteira, alertas, juros e inflação.",
        4,
    ),
    AREA_CONTA: Area(
        "Conta", "conta", "O que é seu: simulações guardadas, plano e privacidade.", 5
    ),
    AREA_AJUDA: Area(
        "Ajuda",
        "ajuda",
        "Como os números são calculados, as regras de uso e a pesquisa em curso.",
        6,
    ),
}
# ficam por último na área, nesta ordem: são ações sobre o ativo da tela ("Comparar com…" e o
# relatório em PDF), não análises; a ordem é a das abas da página do ativo (PR 3 da ADR 0096)
NO_FIM_DA_AREA = ("comparar", "relatorio")


# --- Contrato de cada página (preparação 3 da ADR 0044; ADR 0048) ---------------------------
# O que a tela recebe (entradas) e qual rota da API devolve o que ela mostra (resposta). Uma tela nova
# (React) é montada a partir daqui; há teste que confere cada contrato contra a API de verdade.

PERIODOS = ("6mo", "1y", "2y", "5y")  # os mesmos de src/dados.py (há teste)


@dataclass(frozen=True)
class Entrada:
    """Um campo que a pessoa preenche (ou que tem padrão) e vai para a rota."""

    nome: str  # nome do parâmetro na rota
    tipo: str  # "texto", "inteiro", "numero", "opcao", "lista de textos", "objeto" ou
    # "parametros da estrategia" (nomes de parâmetros numéricos da estratégia escolhida)
    descricao: str
    obrigatoria: bool = False
    padrao: int | float | str | None = None
    minimo: int | float | None = None
    maximo: int | float | None = None
    opcoes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Contrato:
    metodo: str  # "GET" ou "POST"
    rota: str  # na API, sem o prefixo /api: "/v1/visao-geral"
    entradas: tuple[Entrada, ...]
    resposta: str  # o esquema da resposta em src/api_v1/esquemas.py


ATIVO = Entrada("ticker", "texto", "O ativo: PETR4, AAPL, ^BVSP...", obrigatoria=True)
PERIODO = Entrada(
    "periodo", "opcao", "Quanto do passado olhar.", padrao="2y", opcoes=PERIODOS
)
TAXA = Entrada(
    "taxa",
    "numero",
    "Taxa livre de risco ao ano; vazia = o CDI do período.",
    minimo=0,
    maximo=1,
)


@dataclass(frozen=True)
class Pagina:
    chave: str
    titulo: str
    grupo: str
    icone: str  # ícone do Material (o Streamlit mostra no menu)
    descricao: str  # uma frase: para que serve esta página
    area: str  # a área no menu do app novo (uma de AREAS)
    recurso: str | None = None  # recurso do plano que a página exige (None = livre)
    precisa_do_ativo: bool = True  # mostra os campos de ativo e período no topo
    somente_admin: bool = False  # só aparece no menu (e só abre) para administradores
    no_menu: bool = (
        True  # False: fora do menu, mas com endereço (Termos e Privacidade, no rodapé)
    )
    contrato: Contrato | None = None  # páginas que já têm rota na API de leitura
    # True: a tela existe só no app em React; o Streamlit (/classico) não a mostra nem lhe dá endereço.
    # Toda tela nova nasce assim (ADR 0062, Emenda 2); o `grupo` fica só porque o campo é obrigatório.
    so_no_app_novo: bool = False

    def __post_init__(self) -> None:
        if self.so_no_app_novo and self.contrato is None:
            raise ValueError(
                f"{self.chave}: página só do app novo precisa de contrato (é a rota que o React pede)"
            )

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
        GRUPO_TOPO,
        ":material/home:",
        "Comece por aqui: o que é o TickerLab e o caminho mais curto para usá-lo.",
        area=AREA_INICIO,
        precisa_do_ativo=False,
    ),
    Pagina(
        "relatorio",
        "Gerar relatório",
        GRUPO_TOPO,
        ":material/picture_as_pdf:",
        "Leve a análise com você: um PDF com os números, os gráficos e cada termo explicado.",
        area=AREA_ATIVO,
    ),
    Pagina(
        "guia",
        "Guia e glossário",
        GRUPO_APRENDER,
        ":material/menu_book:",
        "Como os números são calculados, os limites do app e cada termo explicado em português.",
        area=AREA_AJUDA,
        precisa_do_ativo=False,
    ),
    Pagina(
        "termos",
        "Termos de uso",
        GRUPO_APRENDER,
        ":material/gavel:",
        "As regras de uso do TickerLab e o que ele não é: não há recomendação de investimento.",
        area=AREA_AJUDA,
        precisa_do_ativo=False,
        no_menu=False,
    ),
    Pagina(
        "privacidade",
        "Política de privacidade",
        GRUPO_APRENDER,
        ":material/lock_person:",
        "Quais dados pessoais o TickerLab guarda, para quê, por quanto tempo e quais são os seus direitos.",
        area=AREA_AJUDA,
        precisa_do_ativo=False,
        no_menu=False,
    ),
    Pagina(
        "trade",
        "TickerLab Trade · Beta",
        GRUPO_MAIS,
        ":material/memory:",
        "A pesquisa de trading quantitativo do TickerLab: o que está sendo testado e em que fase está.",
        area=AREA_AJUDA,
        precisa_do_ativo=False,
    ),
    Pagina(
        "visao_geral",
        "Visão geral",
        GRUPO_ANALISAR,
        ":material/dashboard:",
        "O preço do ativo e os números-chave: retorno, risco e os dias mais extremos.",
        area=AREA_ATIVO,
        contrato=Contrato(
            "GET",
            "/v1/visao-geral",
            (
                ATIVO,
                PERIODO,
                TAXA,
                Entrada(
                    "confianca_do_var",
                    "inteiro",
                    "Confiança da perda de um dia ruim (VaR), em %.",
                    padrao=95,
                    minimo=90,
                    maximo=99,
                ),
            ),
            "VisaoGeralV1",
        ),
    ),
    Pagina(
        "risco",
        "Risco",
        GRUPO_ANALISAR,
        ":material/shield:",
        "Quanto o ativo já caiu e o quanto o preço oscila ao longo do tempo.",
        area=AREA_ATIVO,
        contrato=Contrato(
            "GET",
            "/v1/risco",
            (
                ATIVO,
                PERIODO,
                TAXA,
                Entrada(
                    "janela",
                    "inteiro",
                    "Dias da volatilidade móvel.",
                    padrao=20,
                    minimo=5,
                    maximo=252,
                ),
            ),
            "RiscoDoAtivoV1",
        ),
    ),
    Pagina(
        "retorno_mensal",
        "Retorno mensal",
        GRUPO_ANALISAR,
        ":material/calendar_month:",
        "Como o ativo foi em cada mês e ano, e se existem meses melhores que outros.",
        area=AREA_ATIVO,
        contrato=Contrato(
            "GET",
            "/v1/retorno-mensal",
            (ATIVO, PERIODO, TAXA),
            "RetornoMensalDoAtivoV1",
        ),
    ),
    Pagina(
        "comparar",
        "Comparar ativos",
        GRUPO_ANALISAR,
        ":material/compare_arrows:",
        "Coloque dois ou mais ativos lado a lado, com o Ibovespa e o S&P 500 de referência.",
        area=AREA_ATIVO,
        contrato=Contrato(
            "GET",
            "/v1/comparacao",
            (
                ATIVO,
                Entrada(
                    "com",
                    "lista de textos",
                    "Os outros ativos (até 4); o principal entra sempre.",
                    obrigatoria=True,
                ),
                PERIODO,
                TAXA,
            ),
            "ComparacaoDoAtivoV1",
        ),
    ),
    Pagina(
        "correlacao",
        "Correlação e beta",
        GRUPO_ANALISAR,
        ":material/hub:",
        "Quanto o ativo anda junto com outros e com o mercado (o beta mede essa sensibilidade).",
        area=AREA_ATIVO,
    ),
    Pagina(
        "backtest",
        "Backtest",
        GRUPO_ESTRATEGIAS,
        ":material/history:",
        "Teste no passado: e se eu tivesse seguido esta regra de compra e venda?",
        area=AREA_ESTRATEGIAS,
        contrato=Contrato(
            "POST",
            "/v1/backtest",
            (
                ATIVO,
                PERIODO,
                Entrada(
                    "estrategia",
                    "texto",
                    "O nome de uma estratégia de src/estrategias.py.",
                    obrigatoria=True,
                ),
                Entrada(
                    "parametros",
                    "objeto",
                    "Os ajustes da estratégia; os que faltarem ficam no padrão.",
                ),
                Entrada(
                    "custo_por_operacao",
                    "numero",
                    "Custo de cada compra ou venda (0,0005 = 0,05%).",
                    padrao=0.0005,  # CUSTO_PADRAO_POR_OPERACAO de src/backtest.py (há teste)
                    minimo=0,
                    maximo=0.05,
                ),
                TAXA,
                # a ficha "Foi sorte?" embaixo do resultado (os limites de src/ficha.py; há teste)
                Entrada(
                    "capital_inicial",
                    "numero",
                    "Capital do começo, em R$ (só o imposto da ficha depende dele).",
                    padrao=10_000.0,
                    minimo=100,
                    maximo=1e12,
                ),
                Entrada(
                    "tolerancia_de_queda",
                    "numero",
                    "A maior queda que você aguentaria (0,30 = 30%); vazia = a guardada na conta.",
                    minimo=0.05,
                    maximo=0.9,
                ),
                Entrada(
                    "livres",
                    "parametros da estrategia",
                    "Até 2 parâmetros numéricos que variam na ficha; vazio = os dois primeiros.",
                ),
            ),
            "BacktestDoAtivoV1",
        ),
    ),
    Pagina(
        "ranking",
        "Ranking de estratégias",
        GRUPO_ESTRATEGIAS,
        ":material/leaderboard:",
        "Todas as estratégias no mesmo ativo, da melhor à pior, e quanto do resultado pode ser sorte.",
        area=AREA_ESTRATEGIAS,
    ),
    Pagina(
        "carteira",
        "Carteira",
        GRUPO_ESTRATEGIAS,
        ":material/pie_chart:",
        "Várias ações ao mesmo tempo, com regras para dividir o dinheiro entre elas.",
        area=AREA_ESTRATEGIAS,
    ),
    Pagina(
        "experimentos",
        "Experimentos",
        GRUPO_ESTRATEGIAS,
        ":material/science:",
        "Perguntas clássicas respondidas com dados: aportar de uma vez ou aos poucos, rebalancear, virada do mês.",
        area=AREA_ESTRATEGIAS,
    ),
    Pagina(
        "regimes",
        "Fases do mercado",
        GRUPO_ESTRATEGIAS,
        ":material/waves:",
        "Como uma estratégia se comporta em fases calmas e agitadas, e proteções contra quedas fortes.",
        area=AREA_ESTRATEGIAS,
    ),
    Pagina(
        "aprendizado",
        "Aprendizado de máquina",
        GRUPO_AVANCADO,
        ":material/psychology:",
        "Modelos que tentam prever o mercado, com validação honesta do que realmente funciona.",
        area=AREA_ESTRATEGIAS,
        recurso=APRENDIZADO_DE_MAQUINA,
    ),
    Pagina(
        "pares",
        "Pairs trading",
        GRUPO_AVANCADO,
        ":material/swap_horiz:",
        "Apostar que dois ativos ligados voltam a andar juntos depois de se afastarem.",
        area=AREA_ESTRATEGIAS,
        recurso=PARES,
    ),
    Pagina(
        "research",
        "Acontecimentos",
        GRUPO_RESEARCH,
        ":material/travel_explore:",
        "O que as empresas que você acompanha publicaram na CVM e na SEC, por relevância, "
        "com o documento original de cada item.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
    ),
    Pagina(
        "pulse",
        "Pulse",
        GRUPO_RESEARCH,
        ":material/monitor_heart:",
        "O que mudou nos seus ativos desde a sua última visita: os acontecimentos novos na CVM "
        "e na SEC, a variação do preço e o veredito das suas estratégias salvas.",
        area=AREA_INICIO,
        precisa_do_ativo=False,
        contrato=Contrato(
            "GET",
            "/v1/pulse",
            (
                Entrada(
                    "desde",
                    "texto",
                    "O início da janela que a aba já mostrava (data e hora com fuso), para o "
                    "F5 não encolher a janela; vale até 30 dias atrás.",
                ),
            ),
            "PulseV1",
        ),
    ),
    Pagina(
        "diario_de_teses",
        "Diário de Teses",
        GRUPO_RESEARCH,
        ":material/edit_note:",
        "O que você pensa de cada ativo, com a data em que escreveu, ligado aos backtests que "
        "você salvou.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
    ),
    Pagina(
        "carteira_b3",
        "Carteira da B3",
        GRUPO_RESEARCH,
        ":material/donut_large:",
        "A sua posição e a sua movimentação da B3 lidas só na memória: concentração, a "
        "carteira no passado, Raio-X por tipo, setor e moeda, Rebalanceamento para os pesos "
        "que você escolher, proventos recebidos e custo médio.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
    ),
    Pagina(
        "juros_e_inflacao",
        "Juros e inflação",
        GRUPO_RESEARCH,
        ":material/percent:",
        "Selic, CDI, IPCA, juro real e o que o mercado espera, com a data e a fonte de cada "
        "número (Banco Central).",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
        contrato=Contrato("GET", "/v1/juros-e-inflacao", (), "JurosEInflacaoV1"),
    ),
    Pagina(
        "precos_de_referencia",
        "Preços de referência",
        GRUPO_RESEARCH,
        ":material/grain:",
        "Café (arábica e robusta), algodão e fertilizantes: o preço mensal do Banco Mundial e do "
        "FMI, com a fonte e a data de cada número.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
        contrato=Contrato(
            "GET", "/v1/precos-de-referencia", (), "PrecosDeReferenciaV1"
        ),
    ),
    Pagina(
        "linha_do_tempo",
        "Linha do tempo",
        GRUPO_RESEARCH,
        ":material/timeline:",
        "O preço do ativo do topo e os documentos que a empresa publicou na CVM ou na SEC, no "
        "mesmo eixo, com o link de cada documento.",
        area=AREA_ATIVO,
        contrato=Contrato(
            "GET",
            "/v1/linha-do-tempo",
            (
                ATIVO,
                PERIODO,
                Entrada(
                    "materialidade_minima",
                    "inteiro",
                    "Quais acontecimentos mostrar: 70 = os mais relevantes, 50 = relevantes, "
                    "0 = todos.",
                    padrao=50,  # MATERIALIDADE_PADRAO de src/linha_do_tempo.py (há teste)
                    minimo=0,
                    maximo=100,
                ),
            ),
            "LinhaDoTempoDoAtivoV1",
        ),
    ),
    Pagina(
        "fundamentos",
        "Fundamentos",
        GRUPO_RESEARCH,
        ":material/account_balance:",
        "Receita, lucro, margens, retorno, dívida e múltiplos do ativo do topo, a partir das "
        "demonstrações entregues à CVM ou à SEC, com o documento de cada número.",
        area=AREA_ATIVO,
    ),
    Pagina(
        "relatorio_empresa",
        "Relatório da empresa",
        GRUPO_RESEARCH,
        ":material/summarize:",
        "O relatório completo da empresa do topo (B3): resultado, retorno, dívida, caixa, notas "
        "clássicas, comparação com o setor, valuation, dividendos e limites, com a fonte de cada "
        "número.",
        area=AREA_ATIVO,
        contrato=Contrato(
            "GET", "/v1/relatorio-empresa", (ATIVO,), "RelatorioDaEmpresaV1"
        ),
    ),
    Pagina(
        "busca_por_cnpj",
        "Busca por CNPJ",
        GRUPO_RESEARCH,
        ":material/manage_search:",
        "Digite o CNPJ de uma empresa e veja quem é: da companhia aberta, o grupo, a rede de empresas "
        "e os fatos públicos; das outras, o cadastro da Receita, o Simples e o MEI, os sócios e o que "
        "mudou em 12 meses. Com a data e a fonte de cada linha.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
        contrato=Contrato(
            "POST",
            "/v1/busca-por-cnpj",
            (
                Entrada(
                    "cnpj",
                    "texto",
                    "O CNPJ da empresa, com ou sem pontuação (aceita as letras do CNPJ novo).",
                    obrigatoria=True,
                ),
            ),
            "BuscaPorCnpjV1",
        ),
        so_no_app_novo=True,
    ),
    Pagina(
        "relatorio_do_setor",
        "Relatório do setor",
        GRUPO_RESEARCH,
        ":material/domain:",
        "Escolha um setor e veja quem está nele, o tamanho do mercado, a concentração (CR4 e HHI "
        "com a faixa do CADE), as empresas lado a lado e o que ainda não temos, com a fonte de "
        "cada número.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
        contrato=Contrato(
            "GET",
            "/v1/relatorio-setor",
            (
                Entrada(
                    "setor",
                    "texto",
                    "A chave do setor do lançamento; a lista, com os nomes, vem de /v1/setores.",
                    obrigatoria=True,
                ),
            ),
            "RelatorioDoSetorV1",
        ),
        so_no_app_novo=True,
    ),
    Pagina(
        "por_dentro",
        "Pessoas de dentro",
        GRUPO_RESEARCH,
        ":material/badge:",
        "Quem conhece a empresa por dentro (diretoria, conselho, controlador) comprou ou vendeu "
        "ações? Dados oficiais da CVM e da SEC, com o documento de cada negociação.",
        area=AREA_ATIVO,
    ),
    Pagina(
        "donos",
        "Donos e fundos",
        GRUPO_RESEARCH,
        ":material/groups:",
        "Quais fundos (B3) e grandes gestores (EUA) têm a ação, quem entrou e quem saiu, e quanto "
        "está vendido. Carteiras oficiais entregues à CVM e à SEC.",
        area=AREA_ATIVO,
    ),
    Pagina(
        "newsletter",
        "Newsletter",
        GRUPO_RESEARCH,
        ":material/newspaper:",
        "A edição da sua lista: destaques, alertas, pessoas de dentro, resultados e fundos, com o "
        "documento de cada item. Na tela ou em PDF.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
    ),
    Pagina(
        "carteira_research",
        "Minha carteira",
        GRUPO_RESEARCH,
        ":material/donut_large:",
        "Guarde a fotografia da sua carteira da B3 (só os pesos em %, com o seu consentimento) "
        "para o Research e a Newsletter darem mais destaque às maiores posições.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,  # guardar é do Pro: a própria página explica (sem cadeado)
    ),
    Pagina(
        "alertas",
        "Alertas",
        GRUPO_RESEARCH,
        ":material/notifications:",
        "Monte regras com várias condições (diário e semanal) e veja em quais ativos da sua lista "
        "elas valem hoje, com o fechamento usado e o motivo de cada resultado.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
    ),
    Pagina(
        "parametros",
        "Parâmetros",
        GRUPO_RESEARCH,
        ":material/tune:",
        "Escolha como analisar: janelas, médias, RSI, pesos e temas, para todos os ativos ou só "
        "para um, e veja o efeito antes de salvar.",
        area=AREA_ACOMPANHAR,
    ),
    Pagina(
        "simulacoes",
        "Minhas simulações",
        GRUPO_CONTA,
        ":material/bookmarks:",
        "As simulações que você guardou: reabra para recalcular com os dados de hoje ou apague.",
        area=AREA_CONTA,
        precisa_do_ativo=False,
        contrato=Contrato("GET", "/v1/simulacoes", (), "MinhasSimulacoesV1"),
    ),
    Pagina(
        "momentum",
        "Favoritos e momentum",
        GRUPO_CONTA,
        ":material/star:",
        "Seus ativos favoritos ordenados pela força da tendência recente (momentum).",
        area=AREA_ACOMPANHAR,
    ),
    Pagina(
        "meus_dados",
        "Meus dados e privacidade",
        GRUPO_CONTA,
        ":material/shield_person:",
        "Baixe uma cópia dos seus dados ou apague a sua conta e tudo o que está nela.",
        area=AREA_CONTA,
        precisa_do_ativo=False,
        contrato=Contrato("GET", "/v1/links-compartilhados", (), "MeusLinksV1"),
    ),
    Pagina(
        "planos",
        "Planos e assinatura",
        GRUPO_CONTA,
        ":material/workspace_premium:",
        "Seu plano, o que ele inclui, quanto você já usou e como assinar o Pro.",
        area=AREA_CONTA,
        precisa_do_ativo=False,
        contrato=Contrato("GET", "/v1/meu-plano", (), "MeuPlanoV1"),
    ),
    Pagina(
        "admin",
        "Administração",
        GRUPO_ADMIN,
        ":material/admin_panel_settings:",
        "Usuários, planos, assinaturas e o registro de ações de administrador.",
        area=AREA_CONTA,
        precisa_do_ativo=False,
        somente_admin=True,
    ),
    Pagina(
        "sala_de_dados",
        "Sala de dados",
        GRUPO_CONTA,
        ":material/lock:",
        "Os documentos de cada operação num lugar cifrado, com a origem de cada número, as "
        "contradições entre documentos e o checklist do que falta.",
        area=AREA_CONTA,
        precisa_do_ativo=False,
        contrato=Contrato("GET", "/v1/sala", (), "SalaV1"),
        so_no_app_novo=True,
    ),
    Pagina(
        "boas_vindas_beta",
        "Boas-vindas ao beta",
        GRUPO_CONTA,
        ":material/waving_hand:",
        "O roteiro dos 10 minutos para conhecer o TickerLab: o relatório do setor, o de uma empresa e a "
        "busca por CNPJ, com a fonte de cada número.",
        area=AREA_CONTA,
        precisa_do_ativo=False,
        contrato=Contrato("GET", "/v1/beta/boas-vindas", (), "BoasVindasDoBetaV1"),
        so_no_app_novo=True,
    ),
    Pagina(
        "mapa_do_cafe",
        "Mapa do café",
        GRUPO_RESEARCH,
        ":material/map:",
        "Onde se produz café arábica e conilon, município a município (IBGE), e a chuva e a geada "
        "de cada região contra a normal, com a fonte e a data de cada número.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
        contrato=Contrato(
            "GET",
            "/v1/commodities/cafe/mapa",
            (
                Entrada(
                    "tipo",
                    "opcao",
                    "O café do mapa: arábica ou conilon (robusta).",
                    padrao="arabica",
                    opcoes=("arabica", "conilon"),
                ),
            ),
            "MapaDoCafeV1",
        ),
        so_no_app_novo=True,
    ),
    Pagina(
        "painel_do_cafe",
        "Painel do café",
        GRUPO_RESEARCH,
        ":material/coffee:",
        "Café arábica ou conilon: preço de referência, câmbio, fundos, exportações, safra da CONAB, "
        "clima e calendário, cada número com a data e a fonte.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
        contrato=Contrato(
            "GET",
            "/v1/painel-do-cafe",
            (
                Entrada(
                    "tipo",
                    "opcao",
                    "Arábica ou conilon (robusta).",
                    padrao="arabica",
                    opcoes=("arabica", "conilon"),
                ),
                Entrada(
                    "regiao",
                    "texto",
                    "A região do clima e do calendário; vazia, a de maior área do tipo.",
                ),
            ),
            "PainelDoCafeV1",
        ),
        so_no_app_novo=True,
    ),
)

PAGINAS += (
    Pagina(
        "radar_imobiliario",
        "Radar imobiliário",
        GRUPO_RESEARCH,
        ":material/apartment:",
        "Atividade imobiliária em São Paulo e no Rio: ITBI, valores declarados e cobertura territorial, com fonte e data.",
        area=AREA_ACOMPANHAR,
        precisa_do_ativo=False,
        contrato=Contrato(
            "GET",
            "/v1/radar-imobiliario",
            (
                Entrada(
                    "cidade", "opcao", "Município.", padrao="SP", opcoes=("SP", "RIO")
                ),
                Entrada(
                    "recorte",
                    "opcao",
                    "Uso do imóvel.",
                    padrao="todos",
                    opcoes=("todos", "residencial"),
                ),
            ),
            "RadarImobiliarioV1",
        ),
        so_no_app_novo=True,
    ),
)

POR_CHAVE = {p.chave: p for p in PAGINAS}
PAGINA_INICIAL = "inicio"

# As rotas que a página "Sala de dados" usa (a de leitura é o contrato dela; as outras mudam a sala).
# Fora do `openapi_v1` de propósito (a sala não vai para o contrato público da v1; o contrato da
# página dela é o `/v1/sala`, conferido em `test_api_v1_sala_painel`); o teste da sala confere que toda rota dos três roteadores está aqui, e só elas.
ROTAS_DA_SALA = frozenset(
    {
        ("GET", "/v1/sala"),
        ("GET", "/v1/operacoes"),
        ("POST", "/v1/operacoes"),
        ("GET", "/v1/operacoes/{operacao_id}"),
        ("GET", "/v1/operacoes/{operacao_id}/painel"),
        ("POST", "/v1/operacoes/{operacao_id}/encerrar"),
        ("POST", "/v1/operacoes/{operacao_id}/prorrogar"),
        ("DELETE", "/v1/operacoes/{operacao_id}"),
        ("GET", "/v1/operacoes/{operacao_id}/documentos"),
        ("POST", "/v1/operacoes/{operacao_id}/documentos"),
        ("GET", "/v1/operacoes/{operacao_id}/documentos/{documento_id}/arquivo"),
        ("DELETE", "/v1/operacoes/{operacao_id}/documentos/{documento_id}"),
        ("GET", "/v1/operacoes/{operacao_id}/sala"),
        ("POST", "/v1/operacoes/{operacao_id}/evidencias"),
        ("GET", "/v1/operacoes/{operacao_id}/evidencias"),
        ("PATCH", "/v1/operacoes/{operacao_id}/evidencias/{evidencia_id}"),
        ("DELETE", "/v1/operacoes/{operacao_id}/evidencias/{evidencia_id}"),
        ("GET", "/v1/operacoes/{operacao_id}/contradicoes"),
        ("PATCH", "/v1/operacoes/{operacao_id}/contradicoes/{contradicao_id}"),
        ("GET", "/v1/operacoes/{operacao_id}/checklist"),
        ("PATCH", "/v1/operacoes/{operacao_id}/checklist/{codigo}"),
        ("GET", "/v1/operacoes/{operacao_id}/garantias"),
        ("GET", "/v1/operacoes/{operacao_id}/exposicoes"),
    }
)


def paginas_do_classico() -> list[Pagina]:
    """As páginas que o Streamlit mostra: todas menos as que só existem no app em React."""
    return [p for p in PAGINAS if not p.so_no_app_novo]


def paginas_do_grupo(grupo: str) -> list[Pagina]:
    """As páginas do grupo no menu do Streamlit (os grupos só existem lá)."""
    return [p for p in paginas_do_classico() if p.grupo == grupo]


def paginas_da_area(area: str) -> list[Pagina]:
    """As páginas da área na ordem do menu: a de PAGINAS, com as de NO_FIM_DA_AREA por último."""
    if area not in AREAS:
        raise KeyError(f"área desconhecida: {area}")

    def posicao(p: Pagina) -> int:
        return NO_FIM_DA_AREA.index(p.chave) + 1 if p.chave in NO_FIM_DA_AREA else 0

    return sorted((p for p in PAGINAS if p.area == area), key=posicao)


def pagina(chave: str) -> Pagina:
    return POR_CHAVE[chave]


def motivo_da_pagina(plano: str | None, chave: str) -> str | None:
    """Por que o plano não abre a página (o Streamlit e a API mostram este texto), ou None se abre."""
    recurso = POR_CHAVE[chave].recurso
    return None if recurso is None else motivo_sem_acesso(plano, recurso)


# a API acha a página de cada rota pelo contrato (src/api_v1/acesso.py confere o plano por aqui)
POR_ROTA = {p.contrato.rota: p for p in PAGINAS if p.contrato is not None}
PREFIXO_DA_API = "/api"  # a API v1 responde em /v1/... e em /api/v1/... (src/api.py)


def pagina_da_rota(rota: str) -> Pagina | None:
    """A página cujo contrato usa esta rota da API (com ou sem o /api na frente), ou None."""
    if rota.startswith(PREFIXO_DA_API + "/"):
        rota = rota[len(PREFIXO_DA_API) :]
    return POR_ROTA.get(rota)
