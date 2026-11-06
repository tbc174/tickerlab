"""Os checklists da sala por tipo de operação (B-20, PR 4, D10).

Cada tipo (`ma`, `divida`, `credito`, `fidc`) tem de 8 a 15 itens: o que um analista costuma pedir
antes de fechar a operação. O texto é uma lista de conferência, não um parecer: o item "recebido"
só diz que há um documento ligado a ele; "revisado" é sempre a pessoa que marca.

O `codigo` é a chave gravada no banco (`checklist_da_sala.codigo`): mudar o texto de um item é
livre, mudar o código perde o estado que a pessoa marcou.
"""

from dataclasses import dataclass

from src.banco.modelo import TIPOS_DE_OPERACAO

MINIMO_DE_ITENS = 8
MAXIMO_DE_ITENS = 15


@dataclass(frozen=True)
class ItemDoChecklist:
    codigo: str
    titulo: str
    ajuda: str  # o que procurar no documento


CHECKLISTS: dict[str, tuple[ItemDoChecklist, ...]] = {
    "ma": (
        ItemDoChecklist(
            "ma_estatuto",
            "Estatuto ou contrato social em vigor",
            "Versão consolidada, com todas as alterações registradas.",
        ),
        ItemDoChecklist(
            "ma_quadro_societario",
            "Quadro societário e atas recentes",
            "Quem são os sócios, quanto cada um tem e o que as últimas assembleias decidiram.",
        ),
        ItemDoChecklist(
            "ma_dfs",
            "Demonstrações financeiras dos últimos três exercícios",
            "Com o parecer do auditor, quando houver.",
        ),
        ItemDoChecklist(
            "ma_balancete",
            "Balancete mais recente",
            "Para ver o que mudou desde a última demonstração anual.",
        ),
        ItemDoChecklist(
            "ma_endividamento",
            "Endividamento e garantias concedidas",
            "Credores, saldos, vencimentos, garantias reais e avais.",
        ),
        ItemDoChecklist(
            "ma_contratos_relevantes",
            "Contratos relevantes e cláusulas de mudança de controle",
            "Clientes, fornecedores e financiamentos que mudam de condição se o controle mudar.",
        ),
        ItemDoChecklist(
            "ma_contingencias",
            "Contingências fiscais, trabalhistas e cíveis",
            "Posição atualizada dos advogados, com valor, chance de perda e depósitos.",
        ),
        ItemDoChecklist(
            "ma_certidoes",
            "Certidões negativas",
            "Federal, estadual, municipal, FGTS e trabalhista.",
        ),
        ItemDoChecklist(
            "ma_licencas",
            "Licenças, alvarás e autorizações",
            "O que a atividade exige e a data de validade de cada uma.",
        ),
        ItemDoChecklist(
            "ma_propriedade_intelectual",
            "Marcas, patentes e domínios",
            "Registros em nome da empresa e contratos de licença.",
        ),
        ItemDoChecklist(
            "ma_partes_relacionadas",
            "Operações com partes relacionadas",
            "Contratos e saldos com sócios, administradores e empresas do grupo.",
        ),
        ItemDoChecklist(
            "ma_projecoes",
            "Plano de negócios e projeções",
            "As premissas por trás dos números projetados.",
        ),
    ),
    "divida": (
        ItemDoChecklist(
            "divida_instrumento",
            "Instrumento da dívida",
            "Escritura, contrato ou cédula, com todos os aditamentos.",
        ),
        ItemDoChecklist(
            "divida_garantias",
            "Garantias",
            "Contratos de garantia, registros e avaliações dos bens dados em garantia.",
        ),
        ItemDoChecklist(
            "divida_covenants",
            "Cláusulas de manutenção (covenants)",
            "Os índices exigidos, como são medidos e a última apuração.",
        ),
        ItemDoChecklist(
            "divida_vencimento_antecipado",
            "Eventos de vencimento antecipado",
            "O que permite ao credor cobrar tudo de uma vez e se algum já ocorreu.",
        ),
        ItemDoChecklist(
            "divida_cronograma",
            "Cronograma de pagamentos",
            "Datas, valores de principal e juros, e carência.",
        ),
        ItemDoChecklist(
            "divida_dfs",
            "Demonstrações financeiras do devedor",
            "Últimos exercícios e o balancete mais recente.",
        ),
        ItemDoChecklist(
            "divida_outros_credores",
            "Outras dívidas do devedor",
            "Relação de credores, saldos e prioridade de cada um.",
        ),
        ItemDoChecklist(
            "divida_poderes",
            "Poderes de quem assinou",
            "Estatuto, atas e procurações que dão a quem assinou o poder de endividar a empresa.",
        ),
        ItemDoChecklist(
            "divida_rating",
            "Rating da emissão ou do emissor",
            "Relatório da agência, quando houver.",
        ),
        ItemDoChecklist(
            "divida_certidoes",
            "Certidões do devedor",
            "Negativas fiscais, de protesto e de distribuição de ações.",
        ),
    ),
    "credito": (
        ItemDoChecklist(
            "credito_cadastro",
            "Cadastro e documentos de constituição",
            "Contrato ou estatuto social, CNPJ e quem são os administradores.",
        ),
        ItemDoChecklist(
            "credito_poderes",
            "Poderes de quem assina",
            "Procuração ou ata que autoriza a assinar o crédito.",
        ),
        ItemDoChecklist(
            "credito_dfs",
            "Demonstrações financeiras",
            "Últimos exercícios e o balancete mais recente.",
        ),
        ItemDoChecklist(
            "credito_faturamento",
            "Faturamento dos últimos 12 meses",
            "Mês a mês, para comparar com as demonstrações e os extratos.",
        ),
        ItemDoChecklist(
            "credito_extratos",
            "Extratos bancários",
            "Os últimos meses das contas principais.",
        ),
        ItemDoChecklist(
            "credito_endividamento",
            "Posição de endividamento no sistema financeiro",
            "Relatório do SCR (Banco Central) ou quadro enviado pelo cliente, com saldos e vencimentos.",
        ),
        ItemDoChecklist(
            "credito_garantias",
            "Garantias oferecidas",
            "Descrição, valor e documentos de propriedade e registro.",
        ),
        ItemDoChecklist(
            "credito_certidoes",
            "Certidões negativas",
            "Fiscais, trabalhistas, de protesto e de distribuição de ações.",
        ),
        ItemDoChecklist(
            "credito_finalidade",
            "Finalidade do crédito",
            "Para que o dinheiro será usado e a fonte de pagamento.",
        ),
        ItemDoChecklist(
            "credito_avalistas",
            "Avalistas e garantidores",
            "Documentos e declaração de bens, quando houver aval.",
        ),
    ),
    "fidc": (
        ItemDoChecklist(
            "fidc_regulamento",
            "Regulamento do fundo",
            "Política de investimento, critérios de elegibilidade e limites de concentração.",
        ),
        ItemDoChecklist(
            "fidc_contrato_cessao",
            "Contrato de cessão",
            "Condições da compra dos direitos creditórios e coobrigação do cedente, se houver.",
        ),
        ItemDoChecklist(
            "fidc_carteira",
            "Posição da carteira",
            "Saldo por devedor, vencimento e valor, na data-base mais recente.",
        ),
        ItemDoChecklist(
            "fidc_inadimplencia",
            "Atrasos e perdas por faixa",
            "Inadimplência por faixa de atraso, ao longo do tempo.",
        ),
        ItemDoChecklist(
            "fidc_concentracao",
            "Concentração por cedente e por sacado",
            "Os maiores devedores e cedentes em relação ao patrimônio do fundo.",
        ),
        ItemDoChecklist(
            "fidc_lastro",
            "Amostra de documentos do lastro",
            "Duplicatas, contratos ou notas fiscais de uma amostra dos direitos creditórios.",
        ),
        ItemDoChecklist(
            "fidc_custodia",
            "Contrato e relatório do custodiante",
            "Quem guarda os documentos e o que ele confere.",
        ),
        ItemDoChecklist(
            "fidc_prestadores",
            "Contratos de administrador, gestor e agente de cobrança",
            "Responsabilidades e remuneração de cada um.",
        ),
        ItemDoChecklist(
            "fidc_subordinacao",
            "Índice de subordinação",
            "Cotas sêniores, mezanino e subordinadas e o índice exigido.",
        ),
        ItemDoChecklist(
            "fidc_demonstracoes",
            "Demonstrações financeiras do fundo",
            "Com o parecer do auditor.",
        ),
        ItemDoChecklist(
            "fidc_rating",
            "Rating das cotas",
            "Relatório da agência, quando houver.",
        ),
        ItemDoChecklist(
            "fidc_cobranca",
            "Política de cobrança e recompra",
            "Como se cobra o atrasado e quando o cedente recompra.",
        ),
    ),
}

assert set(CHECKLISTS) == set(TIPOS_DE_OPERACAO)


def itens_do_tipo(tipo: str) -> tuple[ItemDoChecklist, ...]:
    """Os itens do checklist do tipo de operação (`ValueError` se o tipo não existe)."""
    if tipo not in CHECKLISTS:
        raise ValueError(f"Tipo de operação desconhecido: {tipo}.")
    return CHECKLISTS[tipo]


def item_do_tipo(tipo: str, codigo: str) -> ItemDoChecklist | None:
    return next((i for i in itens_do_tipo(tipo) if i.codigo == codigo), None)
