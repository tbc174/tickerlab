"""O próximo passo no fim da resposta das ferramentas de lista.

Quem usa o conector não conhece as ferramentas pelo nome: depois de uma lista de empresas, não sabe que existe
a ficha, o comparador ou a lista de compradores. A resposta de cada ferramenta de lista traz, no campo
`next_step`, uma frase curta dizendo o que chamar a seguir; quando a lista vem vazia, a frase diz o que ficou
de fora do pedido e como alargá-lo, sem estimar nada.

Os textos são fixos (nada vem da API) e falam só de ferramentas e de parâmetros do próprio conector; um teste
confere que cada nome citado existe e que nenhum texto tem preço, promessa, recomendação, nome de pessoa nem o
nome de quem usa.
"""

# a ferramenta de lista → a chave da lista no corpo da resposta
LISTA_DA_FERRAMENTA: dict[str, str] = {
    "buscar_empresas": "companies",
    "compradores_do_setor": "buyers",
    "comparaveis": "peers",
    "eventos": "events",
    "vinculos": "links",
    "setores": "sectors",
}
CHAVE_DO_PROXIMO_PASSO = "next_step"

SE_NAO_APARECE = " Ferramenta que não está na sua lista não foi liberada para a chave: diga isso ao analista."
SEM_ESTIMAR = " Vazio quer dizer que a base não tem; não estime."

PROXIMO_PASSO: dict[str, str] = {
    "buscar_empresas": (
        "Próximo passo: para ver uma empresa da lista, chame `ficha_da_empresa` com o CNPJ dela; para pôr de 2 "
        "a 5 lado a lado, `comparar_empresas`; para ver quem já se mexeu no setor, `compradores_do_setor`."
        + SE_NAO_APARECE
    ),
    "compradores_do_setor": (
        "Próximo passo: para conhecer um comprador da lista, chame `ficha_da_empresa` com o CNPJ dele; para "
        "ver as participações dele, `vinculos`; para pôr de 2 a 5 lado a lado, `comparar_empresas`."
        + SE_NAO_APARECE
    ),
    "comparaveis": (
        "Próximo passo: para ver os números de um dos pares, chame `demonstracoes` com o CNPJ dele; para o "
        "cadastro, `ficha_da_empresa`." + SE_NAO_APARECE
    ),
    "eventos": (
        "Próximo passo: para ver o cadastro da empresa, chame `ficha_da_empresa`; para saber o que mudou "
        "nela desde um dia, `o_que_mudou`." + SE_NAO_APARECE
    ),
    "vinculos": (
        "Próximo passo: para ver uma empresa do grupo, chame `ficha_da_empresa` com o CNPJ dela; para os "
        "fatos dela, `eventos`." + SE_NAO_APARECE
    ),
    "setores": (
        "Próximo passo: para ver a concentração de um setor da lista, chame `setor` com a `chave` dele; para "
        "listar empresas, `buscar_empresas` com o `cnae`." + SE_NAO_APARECE
    ),
}

QUANDO_VAZIA: dict[str, str] = {
    "buscar_empresas": (
        "Nenhuma empresa na base para esses filtros."
        + SEM_ESTIMAR
        + " Para alargar: tire `porte` ou "
        "`natureza_juridica`, use menos dígitos no `cnae` ('62' traz a divisão inteira) ou tire `municipio`."
    ),
    "compradores_do_setor": (
        "Nenhum comprador na base para esse setor e período."
        + SEM_ESTIMAR
        + " Para alargar: aumente "
        "`anos` ou tire `uf`."
    ),
    "comparaveis": (
        "Nenhum par na base para essa empresa."
        + SEM_ESTIMAR
        + " Para ver o cadastro e o setor dela, "
        "chame `ficha_da_empresa`."
    ),
    "eventos": (
        "Nenhum evento na base para esse pedido."
        + SEM_ESTIMAR
        + " Para alargar: tire o filtro de `tipos`."
    ),
    "vinculos": (
        "Nenhum vínculo na base para esse pedido."
        + SEM_ESTIMAR
        + " Para alargar: aumente `profundidade` "
        "ou tire o filtro de `tipos`."
    ),
    "setores": (
        "Nenhum setor na lista."
        + SEM_ESTIMAR
        + " Para ver o que a chave enxerga, chame `o_que_posso_ver`."
    ),
}


def com_proximo_passo(ferramenta: str, corpo: object) -> object:
    """O mesmo corpo com `next_step`, se a ferramenta é de lista e o corpo é um objeto que ainda não o tem.

    Lista com itens traz o próximo passo; lista vazia traz o que ficou de fora do pedido. O que não é de lista,
    ou não é objeto, passa como veio."""
    chave_da_lista = LISTA_DA_FERRAMENTA.get(ferramenta)
    if chave_da_lista is None or not isinstance(corpo, dict):
        return corpo
    if CHAVE_DO_PROXIMO_PASSO in corpo:
        return corpo
    lista = corpo.get(chave_da_lista)
    if not isinstance(lista, list):
        return corpo  # corpo de outra forma que a esperada: melhor sem rodapé do que um rodapé errado
    texto = PROXIMO_PASSO[ferramenta] if lista else QUANDO_VAZIA[ferramenta]
    return corpo | {CHAVE_DO_PROXIMO_PASSO: texto}
