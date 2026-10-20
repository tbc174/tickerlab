"""Novidades do TickerLab: o que entrou e o que foi corrigido em cada atualização.

Um lugar só para o texto público: a página `novidades.html` do site (via `web/conteudo/novidades.json`)
e a nota da versão no GitHub (`python -m scripts.nota_da_versao AAAA-MM-DD`). Texto para quem usa:
o que dá para fazer agora, sem números de uso, de clientes ou de retorno, e nada de recomendação.
A mais nova fica no topo.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Atualizacao:
    data: date
    titulo: str
    resumo: str
    novidades: tuple[str, ...]
    correcoes: tuple[str, ...] = ()


ATUALIZACOES: tuple[Atualizacao, ...] = (
    Atualizacao(
        data=date(2026, 10, 19),
        titulo="Busca por CNPJ, login que dura 30 dias e termos de uso atualizados",
        resumo=(
            "Uma página nova para começar a pesquisa pelo CNPJ da empresa, um login que não pede "
            "para entrar toda hora e os textos legais revistos."
        ),
        novidades=(
            (
                "Busca por CNPJ: digite o CNPJ de uma companhia aberta e veja de que grupo ela faz "
                "parte e os fatos públicos, com a data e a fonte de cada linha."
            ),
            "O login com o Google agora mantém a sua sessão por 30 dias.",
            (
                "Termos de uso e Política de privacidade atualizados para refletir o que o produto "
                "faz hoje."
            ),
        ),
    ),
    Atualizacao(
        data=date(2026, 10, 14),
        titulo="Relatório da empresa mais claro e números conferidos com o PDF da CVM",
        resumo=(
            "Conferimos à mão, com o PDF oficial das demonstrações, o relatório de cinco empresas "
            "de setores diferentes. As contas bateram; os ajustes abaixo vieram dessa conferência."
        ),
        novidades=(
            (
                "Metodologia pública das notas, dos padrões por setor e das fórmulas (DuPont, "
                "Piotroski, Altman Z'', Beneish, valuation) na página de metodologia."
            ),
            (
                '"Caixa operacional / lucro" agora tem nota por faixa fixa e pública (atenção, '
                "saudável ou conferir o lucro), sem comparar com o setor: um número alto costuma "
                "vir de lucro pequeno, não de caixa bom."
            ),
            (
                "Bancos: caixa, imobilizado e intangível passam a aparecer no histórico de contas."
            ),
        ),
        correcoes=(
            (
                "P/L e P/VP de empresas cuja primeira classe de ação não existe (como a Vale) saíam "
                "muito errados: o lucro por ação agora é o da classe que a empresa tem."
            ),
            (
                "A depreciação deixou de somar juros e custos de empréstimos que alguns balanços "
                "escrevem com a palavra amortização."
            ),
            (
                'As duas margens líquidas do relatório têm nomes diferentes ("lucro consolidado" e '
                '"dos acionistas"), porque usam lucros diferentes.'
            ),
            (
                "Quando as ações mudam depois de 2022 sem evento conhecido, o relatório avisa que "
                "pode ter sido bonificação e não mostra a diluição como certa."
            ),
        ),
    ),
    Atualizacao(
        data=date(2026, 10, 13),
        titulo="Relatório da empresa, novas telas de pesquisa e site novo",
        resumo=(
            "Um dia grande: o relatório completo de cada empresa da B3, o selo de qualidade dos "
            'dados, três telas novas no Research, a ficha "Foi sorte?" nos backtests, tema claro '
            "e escuro e o site reconstruído com a marca nova."
        ),
        novidades=(
            (
                "Relatório da empresa (Research, empresas da B3): resultado, retorno, dívida, caixa, "
                "notas clássicas (Piotroski, Altman Z'' e Beneish), comparação com as empresas do "
                "mesmo grupo de setores, valuation com as premissas que você escolhe, dividendos, o "
                "que mudou desde o balanço anterior e os limites de cada número, com a fonte e a data "
                "de cada um. Também em PDF nos planos Plus e Pro."
            ),
            (
                "Notas contra o setor: cada indicador mostra onde a empresa fica entre as do mesmo "
                "grupo de setores, por regras fixas e públicas. Dizem como o número está em relação "
                "aos pares, não o que vai acontecer."
            ),
            (
                "Selo de qualidade dos dados: números da CVM que não passam em regras fixas (balanço "
                "que não fecha, resultado refeito no documento seguinte, entre outras) aparecem "
                'marcados "em conferência" na tela Fundamentos, com o motivo.'
            ),
            (
                "Fundamentos mais completos: DuPont, ciclo de caixa, caixa livre, capex, cobertura de "
                "juros e histórico de até 10 anos."
            ),
            (
                "Juros e inflação: Selic, CDI, IPCA, juro real e o que o mercado espera, com a data e "
                "a fonte de cada número (Banco Central)."
            ),
            (
                "Linha do tempo: o preço do ativo e os documentos que a empresa publicou na CVM ou na "
                "SEC no mesmo eixo, com o link de cada documento."
            ),
            (
                "Carteira da B3 para todos os planos: concentração, a carteira no passado, Raio-X e "
                "Rebalanceamento a partir da planilha da Área do Investidor; agora também os "
                "proventos recebidos e o custo médio pela regra da Receita. A planilha é lida só na "
                "memória e não fica guardada."
            ),
            (
                'Ficha "Foi sorte?" nos backtests, na tela e no PDF: compara o resultado com o que o '
                "acaso faria e conta quantas tentativas foram feitas até chegar nele."
            ),
            'Retorno "ao ano" só aparece com pelo menos um ano de dados (padrão GIPS).',
            (
                "Tema claro, escuro ou automático (muda com o pôr do sol) no site e no app; no app, a "
                "escolha fica guardada na sua conta."
            ),
            (
                "Marca nova (manual de identidade v1) e site reconstruído, com as páginas Produto, "
                "Como funciona, Aprender, Sobre e esta página de Novidades."
            ),
        ),
        correcoes=(
            (
                "CDI nos backtests longos: a consulta ao Banco Central passou a ser feita em janelas "
                "menores e é repetida quando o servidor do BC devolve uma página de erro."
            ),
            "Carteira da B3: ações emprestadas (aluguel) não contam mais como venda no custo médio.",
            'Carteira da B3: números como "1.000" na planilha eram lidos como 1.',
            "A aba do app abre com o ícone do TickerLab.",
            "O site sempre carrega a versão mais nova do estilo, sem precisar limpar o cache.",
            "As atualizações chegam ao ar mesmo quando várias são publicadas em seguida.",
        ),
    ),
)


def como_lista() -> list[dict]:
    """As atualizações em tipos simples (para o JSON do site)."""
    return [
        {
            "data": a.data.isoformat(),
            "titulo": a.titulo,
            "resumo": a.resumo,
            "novidades": list(a.novidades),
            "correcoes": list(a.correcoes),
        }
        for a in ATUALIZACOES
    ]
