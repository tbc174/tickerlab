"""A rota `GET /companies/{cnpj}/public-procurement` (linha 980, onda 2, PR 6): as compras públicas da empresa.

Abre só o bloco `compras_publicas` do registro de tabelas ligadas pelo CNPJ (`tabelas_por_cnpj`): o cadastro de
fornecedores do SICAF e o Banco de Preços em Saúde (BPS), no conjunto `public_procurement`, desligado por padrão
(ADR 0122, Emenda 2: cada lote num conjunto próprio, ligado por linha do contrato da organização). A mecânica é a
de `blocos_avulsos.py`: o mesmo bloco, portão e varredura de pessoa da análise completa, um pedido por conjunto
aberto. A rota entra no roteador da API externa pela importação no fim de `rotas.py`.
"""

from datetime import date

from src.api_externa.blocos_avulsos import Avulsos, servir
from src.api_externa.rotas import Chave, _cnpj_pedido, _dia_pedido, router
from src.api_externa.tabelas_por_cnpj import COMPRAS_PUBLICAS

COMPRAS = Avulsos(
    blocos=(COMPRAS_PUBLICAS,),
    limites=(
        (
            "Só as compras públicas que a sua chave vê, como o Compras.gov.br e o Ministério da Saúde as "
            "publicaram, sem nota, soma nem ordenação nossa; bloco que não aparece não foi consultado."
        ),
        (
            "Uma lista que não aparece dentro do bloco não foi lida para a sua chave (a do BPS só sai quando a "
            "chave a vê): a falta dela não quer dizer que a empresa não tem compras ali."
        ),
        (
            "Bloco em `not_found` foi consultado e não achou a empresa: a ausência não quer dizer que ela não vende "
            "ao governo (o SICAF é o cadastro federal e o BPS cobre só compras de saúde que o Ministério recebe; a "
            "`coverage` de cada lista diz o que ela cobre)."
        ),
    ),
    rotulo="compras",
)


@router.get("/companies/{cnpj}/public-procurement")
def compras_da_empresa(
    cnpj: str, contexto: Chave, known_at: date | None = None
) -> object:
    """As compras públicas da empresa como eram em `known_at`, só com o conjunto `public_procurement` no contrato
    da organização: `public_procurement`, com o cadastro de fornecedor no SICAF e as compras de saúde do BPS em
    que ela é a fornecedora, quando a chave os vê. Cada lista traz a fonte e o dia em que cada valor ficou público;
    `not_found` diz que o bloco foi consultado e não achou a empresa, e a lista que não aparece não foi lida. Conta um pedido (`requests_used`). Não abre o resto da análise.
    MEI, empresário individual e o que não é empresa saem `not_available`."""
    return servir(COMPRAS, contexto, _cnpj_pedido(cnpj), _dia_pedido(known_at))
