"""O tutorial por objetivo (blueprint, seção 4): três portas de entrada e passos curtos.

A pessoa escolhe o que quer fazer, não o "nível": analisar uma ação, entender a carteira ou
gerar um relatório. Cada passo acontece numa tela de verdade, com dados de verdade, e só libera
o "Continuar" quando a ação foi feita (ou quando o passo é só leitura). Sempre dá para voltar,
pular ou recomeçar. Não conhece o Streamlit: a tela lê o estado e mostra.

Também há a lista de três tarefas da página inicial (analisar um ativo, salvar um favorito, ver
a prévia de um PDF), que some quando tudo foi feito.
"""

from dataclasses import dataclass

ANALISAR = "analisar"
CARTEIRA = "carteira"
RELATORIO = "relatorio"


@dataclass(frozen=True)
class Objetivo:
    chave: str
    titulo: str  # o botão da porta de entrada
    descricao: str
    icone: str
    nome_do_roteiro: str


@dataclass(frozen=True)
class Passo:
    chave: str
    titulo: str
    texto: str
    pagina: str  # onde o passo acontece (chave de `src.paginas`)
    condicao: str | None = (
        None  # o que precisa ter acontecido (None: só ler e continuar)
    )
    pendente: str = ""  # o que falta, quando a condição ainda não foi cumprida


OBJETIVOS = {
    ANALISAR: Objetivo(
        ANALISAR,
        "Quero analisar uma ação",
        "Busque um ativo, escolha o período e entenda dois números em 2 minutos.",
        ":material/query_stats:",
        "Minha primeira análise",
    ),
    CARTEIRA: Objetivo(
        CARTEIRA,
        "Quero entender minha carteira",
        "Com a planilha da B3 ou uma carteira fictícia de exemplo.",
        ":material/account_balance_wallet:",
        "Minha carteira",
    ),
    RELATORIO: Objetivo(
        RELATORIO,
        "Quero gerar um relatório",
        "Escolha um modelo, veja a prévia do PDF de verdade e troque o estilo.",
        ":material/picture_as_pdf:",
        "Meu primeiro relatório",
    ),
}

ROTEIROS: dict[str, tuple[Passo, ...]] = {
    ANALISAR: (
        Passo(
            "busque",
            "Busque um ativo",
            "Digite um código (PETR4) ou o nome de uma empresa (Petrobras) e escolha na "
            "lista. A lista mostra a bolsa e o tipo de cada ativo.",
            "inicio",
            condicao="escolheu_ativo",
            pendente="Escolha um ativo na busca ou num dos atalhos.",
        ),
        Passo(
            "periodo",
            "Escolha o período",
            "No topo da página, o período define a janela de dias analisada: o mesmo ativo "
            "pode parecer ótimo em 1 ano e ruim em 5. Troque e veja os números mudarem.",
            "visao_geral",
        ),
        Passo(
            "explore",
            "Leia dois números",
            "O retorno total diz quanto o preço variou no período. A maior queda diz o pior "
            "tombo a partir de um topo: é o susto que quem investiu passou. Clique em "
            '"Mostrar como ler" para ver os dois com os números deste ativo.',
            "visao_geral",
            condicao="leu_os_numeros",
            pendente='Clique em "Mostrar como ler".',
        ),
        Passo(
            "gere",
            "Guarde a sua pesquisa",
            "O estúdio de relatórios abre no modelo Executivo. A prévia ao lado é o PDF de "
            "verdade e não conta no seu limite; gerar o arquivo é opcional.",
            "relatorio",
            condicao="viu_a_previa",
            pendente="Abra o estúdio para ver a prévia do PDF.",
        ),
        Passo(
            "pronto",
            "Sua primeira análise está pronta",
            "Salve o ativo nos favoritos para voltar a ele, ou analise outro. O tutorial "
            "pode ser reaberto na página inicial.",
            "visao_geral",
        ),
    ),
    CARTEIRA: (
        Passo(
            "planilha",
            "Envie a planilha ou use o exemplo",
            "Baixe a posição em Excel na Área do Investidor da B3 e envie no estúdio. Sem "
            'a planilha à mão? Ligue "Usar a carteira de exemplo": ela é fictícia e o PDF '
            "sai marcado como demonstração.",
            "relatorio",
            condicao="carregou_a_carteira",
            pendente="Envie a planilha ou ligue a carteira de exemplo.",
        ),
        Passo(
            "previa",
            "Veja a concentração na prévia",
            "A prévia mostra a maior posição, as três maiores juntas e o número efetivo de "
            "ativos: quantos ativos de mesmo peso dariam a mesma concentração.",
            "relatorio",
            condicao="viu_a_previa",
            pendente="Espere a prévia aparecer ao lado.",
        ),
        Passo(
            "pronto",
            "Pronto",
            "A planilha é lida só na memória e não fica guardada. A análise usa os pesos de "
            "hoje no passado: mostra risco e concentração, não o seu resultado real.",
            "relatorio",
        ),
    ),
    RELATORIO: (
        Passo(
            "modelo",
            "Escolha o modelo",
            "Executivo traz o essencial em 2 a 4 páginas; Pesquisa completa traz tudo. Em "
            '"Seções e ordem" você monta o seu.',
            "relatorio",
            condicao="viu_a_previa",
            pendente="Espere a prévia aparecer ao lado.",
        ),
        Passo(
            "estilo",
            "Troque o estilo",
            "Research para imprimir, Terminal para ler na tela, Institucional para enviar. "
            "Só as cores mudam: os números são os mesmos.",
            "relatorio",
            condicao="trocou_o_estilo",
            pendente="Escolha outro estilo e veja a prévia mudar.",
        ),
        Passo(
            "pronto",
            "Pronto para gerar",
            '"Gerar relatório" cria o arquivo e o guarda em Meus relatórios (quem entra '
            "com a conta). O seu plano mostra quantos ainda cabem hoje.",
            "relatorio",
        ),
    ),
}


def passos(objetivo: str) -> tuple[Passo, ...]:
    return ROTEIROS[objetivo]


def passo_atual(objetivo: str, indice: int) -> Passo:
    roteiro = ROTEIROS[objetivo]
    return roteiro[max(0, min(indice, len(roteiro) - 1))]


def pode_continuar(passo: Passo, feitos: set[str]) -> bool:
    """O passo está cumprido? (os de leitura sempre estão)."""
    return passo.condicao is None or passo.condicao in feitos


@dataclass(frozen=True)
class Tarefa:
    chave: str
    rotulo: str
    pagina: str


TAREFAS = (
    Tarefa("escolheu_ativo", "Analisar o primeiro ativo", "visao_geral"),
    Tarefa("salvou_favorito", "Salvar um favorito", "momentum"),
    Tarefa("viu_a_previa", "Ver a prévia de um relatório em PDF", "relatorio"),
)


def tarefas_pendentes(feitos: set[str]) -> list[Tarefa]:
    return [t for t in TAREFAS if t.chave not in feitos]
