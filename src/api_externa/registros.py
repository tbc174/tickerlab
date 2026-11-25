"""A rota `GET /companies/{cnpj}/registrations` (linha 980, onda 2, PR 5): os registros da empresa nas agências.

Abre só os blocos do registro de tabelas ligadas pelo CNPJ (`tabelas_por_cnpj`) que dizem o que a empresa tem nas
agências reguladoras: `regulados` (ANEEL e ANS, no conjunto `profiles`) e `registros_adicionais` (Anatel, ANM, ANP
e o PAT do MTE, no `extended_sources`), pela mecânica comum de `blocos_avulsos.py` (o mesmo bloco, portão e
varredura de pessoa da análise completa, um pedido por conjunto aberto). A rota entra no roteador da API externa
pela importação no fim de `rotas.py`.
"""

from datetime import date

from src.api_externa.blocos_avulsos import Avulsos, servir
from src.api_externa.rotas import Chave, _cnpj_pedido, _dia_pedido, router
from src.api_externa.tabelas_por_cnpj import REGISTROS_ADICIONAIS, REGULADOS

REGISTROS = Avulsos(
    blocos=(REGULADOS, REGISTROS_ADICIONAIS),
    limites=(
        (
            "Só os registros da empresa nas agências que a sua chave vê, como a fonte os publicou, sem nota nem "
            "ordenação; bloco que não aparece não foi consultado, e isso não diz nada sobre a empresa."
        ),
        (
            "Bloco em `not_found` foi consultado e não achou a empresa: a ausência não quer dizer que ela não tem "
            "registro na agência (a base pode não cobrir o período ou o tipo de registro; a `coverage` de cada "
            "lista diz o que ela cobre)."
        ),
    ),
    rotulo="registros",
)


@router.get("/companies/{cnpj}/registrations")
def registros_da_empresa(
    cnpj: str, contexto: Chave, known_at: date | None = None
) -> object:
    """Os registros da empresa nas agências reguladoras como eram em `known_at`, um bloco por conjunto que a
    organização pode ver: `regulated_activities` (ANEEL e ANS, no `profiles`) e, com o conjunto `extended_sources`,
    `additional_records` (Anatel, ANM, ANP e PAT). Cada lista traz a fonte e o dia em que cada valor ficou
    público; `not_found` diz o bloco consultado que não achou a empresa; bloco que não aparece não foi consultado.
    Cada conjunto aberto conta um pedido (`requests_used`). Não abre o resto da análise. MEI, empresário
    individual e o que não é empresa saem `not_available`."""
    return servir(REGISTROS, contexto, _cnpj_pedido(cnpj), _dia_pedido(known_at))
