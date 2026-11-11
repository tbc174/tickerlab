"""O que mudou no app, dia a dia (linha 804): uma linha por entrega visível, com a página para abrir.

Pedido do Tiago (10/11/2026): "quero ver uma evolução real todo dia, algo que eu realmente consiga acessar
no site e ir vendo o que está melhorando". Cada PR que põe no ar algo que dá para abrir no app novo
acrescenta uma linha aqui, no topo, com o dia em que entrou em produção.

Não é o mesmo que `src/novidades.py`: aquele é o texto público, juntado por atualização, que vai para o
site e para a nota da versão. Este é o registro diário, dentro do app, e cada linha leva a uma página
(chave de `src/paginas.py`; há teste que confere que o app novo a abre). Texto para quem usa: o que dá
para fazer agora, sem número de uso, sem promessa e sem recomendação.
"""

from dataclasses import dataclass
from datetime import date

from src import paginas

TAMANHO_MAXIMO = (
    240  # uma frase curta: a linha cabe na tela do celular em poucas linhas
)


@dataclass(frozen=True)
class Entrega:
    data: date  # o dia em que entrou em produção
    o_que: str  # uma frase: o que dá para fazer agora
    pagina: str  # a chave da página em src/paginas.py


ENTREGAS: tuple[Entrega, ...] = (
    Entrega(
        data=date(2026, 11, 11),
        o_que=(
            "Comparar empresas: ponha de duas a cinco empresas lado a lado pelo CNPJ, cada campo com a fonte "
            "e a data. Leve a empresa da ficha para a comparação e baixe tudo em Excel."
        ),
        pagina="comparar_empresas",
    ),
    Entrega(
        data=date(2026, 11, 11),
        o_que=(
            "Encontrar empresas: agora também por capital social e número de estabelecimentos ativos, "
            "com a lista em ordem de um deles. É só uma aproximação do tamanho: nenhum dos dois mede "
            "faturamento."
        ),
        pagina="encontrar_empresas",
    ),
    Entrega(
        data=date(2026, 11, 10),
        o_que=(
            "Encontrar empresas: escolha o setor, o estado e a idade mínima e veja as empresas ativas, "
            "com a fonte e a data de cada campo. Abra a ficha de cada uma e baixe a lista em Excel."
        ),
        pagina="encontrar_empresas",
    ),
    Entrega(
        data=date(2026, 11, 10),
        o_que=(
            "O que mudou: esta página, com o que entrou no app a cada dia e o link para abrir. A ficha "
            "da empresa passa a mostrar o que vai trazer enquanto o dado não é liberado."
        ),
        pagina="o_que_mudou",
    ),
    Entrega(
        data=date(2026, 11, 10),
        o_que=(
            "Ficha da empresa: digite o CNPJ e veja o cadastro na Receita e, da companhia aberta, as "
            "entregas de balanço à CVM, com a fonte e a data de cada campo. Baixe tudo em Excel."
        ),
        pagina="ficha_da_empresa",
    ),
)


def como_lista(entregas: tuple[Entrega, ...] = ENTREGAS) -> list[dict[str, str]]:
    """As entregas em tipos simples, com o título e o endereço da página (a mais nova primeiro).

    `ValueError` se uma linha aponta para página que não existe."""
    por_chave = {p.chave: p for p in paginas.PAGINAS}
    lista = []
    for entrega in entregas:
        pagina = por_chave.get(entrega.pagina)
        if pagina is None:
            raise ValueError(f"página desconhecida: {entrega.pagina}")
        lista.append(
            {
                "data": entrega.data.isoformat(),
                "o_que": entrega.o_que,
                "titulo": pagina.titulo,
                "url": pagina.url,
            }
        )
    return lista
