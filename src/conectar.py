"""O texto da página "Conectar" (linha 832): ligar o TickerLab ao Claude ou ao ChatGPT e usar a CLI.

Um lugar só para o que a página mostra: o endereço do conector, os passos, os comandos da CLI e as perguntas
prontas. Tipos simples (a página lê pela API, `GET /v1/conectar`). A chave é sempre o exemplo `tld_...`: a
página nunca recebe nem mostra uma chave de verdade. O texto longo, com todos os cuidados, é o de
`docs/guia-do-analista-conector.md` e `docs/cli.md`.
"""

ENDERECO_DO_CONECTOR = "https://mcp.tickerlab.com.br/mcp"  # igual a conector_remoto.configuracao (há teste)
CHAVE_DE_EXEMPLO = "tld_..."
CNPJ_DE_EXEMPLO = "00.000.000/0001-00"

PASSOS_NO_CLAUDE = (
    "Em Configurações → Conectores, escolha Adicionar conector personalizado.",
    f"Cole o endereço {ENDERECO_DO_CONECTOR} e confirme.",
    'Clique em Conectar. Abre uma página do TickerLab com o título "Ligar o Claude ao TickerLab".',
    "Cole a sua chave pessoal e clique em Ligar. Você volta ao Claude com o conector ligado.",
)
PASSOS_NO_CHATGPT = (
    "Em Configurações → Apps e conectores, crie um conector novo com o mesmo endereço e a autenticação OAuth.",
    'Ao conectar, abre a página do TickerLab com o título "Ligar o ChatGPT ao TickerLab".',
    "Cole a sua chave pessoal e clique em Ligar.",
)
CUIDADO_COM_A_CHAVE = (
    "A chave é pessoal e começa com tld_. Só cole a chave numa página que abriu porque você clicou em "
    "Conectar agora; se alguém mandou o link, não cole."
)

COMANDO_DE_INSTALAR = (
    "py -m pip install --user pipx\n"
    "py -m pipx ensurepath\n"
    'pipx install "https://github.com/tbc174/tickerlab/archive/refs/heads/main.zip#subdirectory=cli"'
)
COMANDOS_DA_CLI = (
    ("Instalar (Windows, com o Python 3.11 ou mais novo)", COMANDO_DE_INSTALAR),
    ("Entrar com a chave (ela é pedida sem aparecer na tela)", "tickerlab login"),
    ("Ficha de uma empresa", f"tickerlab empresa {CNPJ_DE_EXEMPLO}"),
    ("Empresas parecidas", f"tickerlab comparaveis {CNPJ_DE_EXEMPLO}"),
    (
        "Buscar empresas por atividade e estado",
        "tickerlab prospectar --cnae 2222600 --uf SC",
    ),
)

PERGUNTAS_PRONTAS = (
    f"Faça a triagem do CNPJ {CNPJ_DE_EXEMPLO} para uma reunião amanhã, com a fonte e a data de cada ponto.",
    "Liste empresas ativas de embalagens plásticas em Santa Catarina com mais de 15 anos, com a fonte de cada campo.",
    "Quem são as empresas parecidas com esta? Monte uma tabela e separe o que a base diz do que você deduz.",
)

LIMITES = (
    "Nada aqui é recomendação de investimento: o TickerLab organiza dados públicos.",
    "Confira a fonte indicada antes de levar um número para um material.",
    "O conector só lê; o que a sua chave não libera, a IA não vê.",
)


def como_dicionario() -> dict[str, object]:
    """O conteúdo da página em tipos simples."""
    return {
        "endereco_do_conector": ENDERECO_DO_CONECTOR,
        "chave_de_exemplo": CHAVE_DE_EXEMPLO,
        "passos_no_claude": list(PASSOS_NO_CLAUDE),
        "passos_no_chatgpt": list(PASSOS_NO_CHATGPT),
        "cuidado_com_a_chave": CUIDADO_COM_A_CHAVE,
        "comandos_da_cli": [{"titulo": t, "comando": c} for t, c in COMANDOS_DA_CLI],
        "perguntas_prontas": list(PERGUNTAS_PRONTAS),
        "limites": list(LIMITES),
    }
