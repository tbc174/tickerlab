"""Comparar empresas na tela do analista (linha 798, PR 2): de dois a cinco CNPJs lado a lado.

Nada aqui é leitura nova: cada CNPJ passa pela ficha (`leitura.ficha`, o mesmo leitor e o mesmo portão da API
externa), e o porte, a abertura, a atividade, a UF, o município, o capital social e o número de
estabelecimentos ativos vêm do leitor da busca (`LeitorDeProspeccao`), o mesmo de "Encontrar empresas". A busca
é lida só para os CNPJs que a ficha serviu: quem a ficha não serve (pessoa, MEI, empresário individual, CNPJ que
a base não conhece) sai `nao_disponivel`, igual a um CNPJ que não existe, e nada mais é lido dele.

Cada empresa sai numa linha só (os campos soltos, cada um no envelope com a fonte e o dia), para a tela pôr as
empresas em colunas e a planilha numa aba. Das entregas à CVM saem a última entrega e duas contas nossas: quantas
entregas a base conhecia no dia e quantas atrasaram.

Estados: `nao_liberada` se o portão não deixa sair o cadastro (decidido sem ler CNPJ nenhum, como na ficha);
senão `pronta`, com o estado de cada empresa. `PedidoInvalido` (um `ValueError`) se o pedido foge da regra:
menos de dois ou mais de cinco CNPJs, um inválido ou o mesmo duas vezes (a rota responde 422).
"""

from collections.abc import Mapping, Sequence
from datetime import date

from base import cnpj as cnpj_
from base.porta import Porta
from src.analista import busca, leitura
from src.api_externa.conjuntos import ficha as ficha_
from src.api_externa.conjuntos import prospeccao
from src.api_externa.envelope import fontes_da_resposta
from src.portao_externo import Regras

MINIMO = 2
MAXIMO = 5
# os campos que a ficha não tem e a busca tem; o que as duas têm (razão social, natureza, situação, matriz)
# sai da ficha, que é o cadastro "como era" no dia
CAMPOS_DA_BUSCA = (
    "porte", "data_inicio_atividade", "cnae_principal", "uf", "municipio", "capital_social",
    "n_estabelecimentos",
)  # fmt: skip
TODAS_AS_SITUACOES = tuple(
    prospeccao.SITUACOES.values()
)  # uma empresa baixada também se compara
# a zona cinzenta (atraso curto que um feriado local pode explicar) não conta como atraso
SITUACOES_COM_ATRASO = frozenset(
    {ficha_.ATRASOU, ficha_.ATRASO_GRAVE, ficha_.NAO_ENTREGUE}
)
ULTIMA_ENTREGA = {
    "documento": "ultima_entrega_documento",
    "referencia": "ultima_entrega_referencia",
    "situacao_da_entrega": "ultima_entrega_situacao",
}
LIMITES = (
    *leitura.LIMITES,
    (
        "Capital social e número de estabelecimentos ativos são só uma aproximação do tamanho: o capital é o "
        "declarado na Receita, não o patrimônio, e nenhum dos dois mede faturamento."
    ),
    (
        "Entregas com atraso são uma conta nossa sobre as entregas à CVM que a base conhecia no dia: contam "
        "as que atrasaram, as com atraso grave e as não feitas; a zona cinzenta (atraso curto que um "
        "feriado local pode explicar) não conta."
    ),
)


class PedidoInvalido(ValueError):
    """O pedido foge da regra: menos de dois ou mais de cinco CNPJs, um inválido ou repetido."""


def cnpjs_do_pedido(cnpjs: Sequence[str]) -> tuple[str, ...]:
    """Os CNPJs pedidos, sem pontuação e na ordem do pedido. `PedidoInvalido` fora da regra."""
    if not MINIMO <= len(cnpjs) <= MAXIMO:
        raise PedidoInvalido
    normais = tuple(cnpj_.normalizar_cnpj(cnpj) for cnpj in cnpjs)
    if not all(normais) or len(set(normais)) != len(normais):
        raise PedidoInvalido
    return normais


def comparar(
    porta: Porta, cnpjs: Sequence[str], *, hoje: date, regras: Regras | None = None
) -> leitura.Resposta:
    """As empresas pedidas lado a lado, como a base as conhecia hoje (veja a docstring do módulo)."""
    normais = cnpjs_do_pedido(cnpjs)
    fonte, campo = leitura.ANCORA
    if not leitura.permitido_na_tela(ficha_.CONJUNTO, hoje, regras)(
        fonte, campo, False
    ):
        return leitura.Resposta(leitura.NAO_LIBERADA)
    fichas = {
        cnpj: leitura.ficha(porta, cnpj, hoje=hoje, regras=regras) for cnpj in normais
    }
    servidas = tuple(cnpj for cnpj, ficha in fichas.items() if ficha.corpo is not None)
    da_busca = _da_busca(porta, servidas, hoje, regras)
    empresas = [_linha(cnpj, fichas[cnpj], da_busca.corpo_de(cnpj)) for cnpj in normais]
    nomes_das_fontes = {
        f["fonte"]
        for resposta in (*fichas.values(), da_busca.resposta)
        for f in resposta.fontes
    }
    corpo = {
        "como_era_em": hoje.isoformat(),
        "empresas": empresas,
        "limites": list(LIMITES),
    }
    linhas = sum(r.linhas for r in fichas.values()) + da_busca.resposta.linhas
    return leitura.Resposta(
        leitura.PRONTA, corpo, fontes_da_resposta(nomes_das_fontes), linhas
    )


class _DaBusca:
    """O que o leitor da busca serviu, por CNPJ (vazio se nada foi lido ou o portão não deixa)."""

    def __init__(self, resposta: leitura.Resposta) -> None:
        self.resposta = resposta
        empresas = (resposta.corpo or {}).get("empresas", [])
        self._por_cnpj = {empresa["cnpj"]: empresa for empresa in empresas}

    def corpo_de(self, cnpj: str) -> Mapping:
        return self._por_cnpj.get(cnpj, {})


def _da_busca(
    porta: Porta, cnpjs: tuple[str, ...], hoje: date, regras: Regras | None
) -> _DaBusca:
    """Os campos da busca dos CNPJs que a ficha serviu, no retrato público hoje; sem CNPJ, nada é lido."""
    if not cnpjs:
        return _DaBusca(leitura.Resposta(leitura.NAO_DISPONIVEL))
    permitido = leitura.permitido_na_tela(prospeccao.CONJUNTO, hoje, regras)
    pedido = prospeccao.Busca(cnpjs=cnpjs, situacoes=TODAS_AS_SITUACOES, limite=MAXIMO)
    servida = prospeccao.LeitorDeProspeccao(porta, permitido, MAXIMO).buscar(
        pedido, hoje
    )
    if servida is None:
        return _DaBusca(leitura.Resposta(leitura.NAO_LIBERADA))
    corpo = {
        **servida.corpo,
        "empresas": [busca.legivel(e) for e in servida.corpo["empresas"]],
    }
    return _DaBusca(
        leitura.Resposta(
            leitura.PRONTA, corpo, fontes_da_resposta(servida.fontes), servida.linhas
        )
    )


def _linha(cnpj: str, ficha: leitura.Resposta, da_busca: Mapping) -> dict:
    """Uma empresa numa linha: o cadastro da ficha, os campos da busca e o resumo das entregas."""
    if ficha.corpo is None:
        return {"cnpj": cnpj, "estado": leitura.NAO_DISPONIVEL}
    # da busca, os campos que a ficha não tem e o nome ao lado de cada código (sem repetir o CNPJ nem o que
    # a ficha já trouxe "como era")
    repetidos = {"cnpj", *(set(prospeccao.CAMPOS) - set(CAMPOS_DA_BUSCA))}
    return {
        "cnpj": cnpj,
        "estado": leitura.PRONTA,
        **ficha.corpo["cadastro_na_receita"],
        **{nome: valor for nome, valor in da_busca.items() if nome not in repetidos},
        **_resumo_das_entregas(ficha.corpo.get("entregas")),
    }


def _resumo_das_entregas(entregas: list[dict] | None) -> dict:
    """A última entrega (a ficha vem da mais nova à mais velha) e as duas contas; vazio se o bloco não saiu."""
    if not entregas:
        return {}
    resumo = {
        nome: entregas[0][campo]
        for campo, nome in ULTIMA_ENTREGA.items()
        if campo in entregas[0]
    }
    situacoes = [
        e["situacao_da_entrega"] for e in entregas if "situacao_da_entrega" in e
    ]
    # sem a situação de alguma entrega (o portão a negou) não há conta honesta
    if len(situacoes) == len(entregas):
        resumo["entregas_conhecidas"] = len(entregas)
        resumo["entregas_com_atraso"] = sum(
            s["valor"] in SITUACOES_COM_ATRASO for s in situacoes
        )
    return resumo
