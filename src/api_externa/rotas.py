"""As rotas da API externa do TickerLab Data, em `/data/v1` (B-32a; ADR 0108).

Só entram no app com `TICKERLAB_API_EXTERNA=1` (`src/api.py`). Cada rota recebe a organização pela
chave (`acesso`), faz a conta em `src/` e traduz as chaves para o inglês na saída, num lugar só
(`nomes.traduzir_chaves`). O catálogo e o consumo não servem dado: não gastam a quota do mês nem entram
no consumo, mas contam no limite do minuto.

As rotas de dado contam na quota do mês (o lote conta um por CNPJ válido) e passam cada campo pelo
contrato da organização e pelo portão (`acesso.autorizar`). Toda recusa sai como `not_available`, o
mesmo de um CNPJ que não existe, para não dizer qual foi o motivo.
"""

import math
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from functools import cache
from typing import Annotated

import duckdb
import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from base import porta as porta_da_base
from base.porta import Porta
from src.api_externa import acesso, deck, lote, piloto
from src.api_externa.catalogo import catalogo_da_organizacao, consumo_da_organizacao
from src.api_externa.conjuntos import (
    Permitido,
    Servido,
    ativos,
    comparaveis,
    compradores,
    credito,
    demonstracoes,
    empresas,
    eventos,
    ficha,
    fundos,
    novidades,
    prospeccao,
    setores,
    vinculos,
)
from src.api_externa.envelope import fontes_da_resposta
from src.api_externa.nomes import traduzir_chaves
from src.apresentacao import Apresentacao
from src.banco.chaves_da_api import registrar_consumo
from src.banco.conexao import obter_engine
from src.chaves_da_api import ContextoDaChave
from src.portao_externo import Finalidade, Regras

router = APIRouter(prefix="/data/v1")

ChaveSemQuota = Annotated[
    ContextoDaChave, Depends(acesso.exigir_chave_sem_quota_do_mes)
]
Chave = Annotated[ContextoDaChave, Depends(acesso.exigir_chave)]

FINALIDADE = Finalidade.ANALISE.value  # a dos conjuntos do beta; `credit` é de crédito
FINALIDADE_DE_CREDITO = Finalidade.CREDITO.value
NAO_DISPONIVEL = "not_available"
# 100% ao ano: acima disso a conta de exemplo deixa de ser plausível
RETORNO_SUPOSTO_MAXIMO = 1.0


def regras_da_api() -> Regras | None:
    """As regras do portão: None vale as vigentes (os testes trocam esta função)."""
    return None


def abrir_porta(banco: sa.Connection) -> Porta:
    """A porta da base, com o registro de coletas para a linhagem (os testes trocam esta função)."""
    return porta_da_base.abrir(banco=banco)


def _fora_do_ar() -> HTTPException:
    return HTTPException(status_code=503, detail="service_unavailable")


@contextmanager
def _porta(banco: sa.Connection) -> Iterator[Porta]:
    """A porta aberta; 503 sem dizer onde nem por quê se a base não está neste servidor ou falha na
    leitura (a transação volta e o pedido não conta no consumo)."""
    try:
        porta = abrir_porta(banco)
    except (ImportError, OSError, ValueError) as erro:
        raise _fora_do_ar() from erro
    with porta:
        try:
            yield porta
        except (duckdb.Error, OSError) as erro:
            raise _fora_do_ar() from erro


def _recusa(codigo: str) -> HTTPException:
    return HTTPException(status_code=400, detail=codigo)


def _dia_pedido(known_at: date | None) -> date:
    """O `known_at` do pedido (sem ele, hoje); 400 se está no futuro."""
    hoje = acesso.agora().date()
    if known_at is None:
        return hoje
    if known_at > hoje:
        raise _recusa("invalid_known_at")
    return known_at


def _retorno_pedido(assumed_return: float | None) -> float | None:
    """O retorno suposto do cliente; 400 se não é um número ou está fora do plausível."""
    if assumed_return is None:
        return None
    if not math.isfinite(assumed_return) or not (
        -1 < assumed_return <= RETORNO_SUPOSTO_MAXIMO
    ):
        raise _recusa("invalid_assumed_return")
    return assumed_return


def _portao(
    conexao: sa.Connection,
    contexto: ContextoDaChave,
    conjunto: str,
    finalidade: str = FINALIDADE,
) -> Permitido:
    """O contrato da organização e o portão, uma pergunta por fonte e campo dentro do pedido."""
    hoje = acesso.agora().date()
    regras = regras_da_api()

    @cache
    def permitido(fonte: str, campo: str, derivado: bool) -> bool:
        decisao = acesso.autorizar(
            conexao, contexto, fonte=fonte, conjunto=conjunto, campo=campo,
            finalidade=finalidade, hoje=hoje, derivado=derivado, regras=regras,
        )  # fmt: skip
        # D11: o campo de piloto só sai com o registro do pedido aberto, para o bloco levar o aviso
        return piloto.registrar(fonte, campo, decisao)

    return permitido


def _leitor(
    conexao: sa.Connection, porta: Porta, contexto: ContextoDaChave
) -> fundos.LeitorDeFundos:
    return fundos.LeitorDeFundos(
        porta,
        _portao(conexao, contexto, fundos.CONJUNTO),
        acesso.linhas_por_resposta(contexto),
    )


@router.get("/catalog")
def catalogo(contexto: ChaveSemQuota) -> object:
    """O que esta chave pode pedir hoje: conjuntos, campos, licença e atribuição de cada fonte."""
    with obter_engine().connect() as conexao:
        corpo = catalogo_da_organizacao(
            conexao, contexto, acesso.agora().date(), regras_da_api()
        )
    return traduzir_chaves(corpo)


@router.get("/usage")
def consumo(contexto: ChaveSemQuota) -> object:
    """O consumo do mês da própria organização, os limites do plano e o que falta da quota."""
    with obter_engine().connect() as conexao:
        corpo = consumo_da_organizacao(conexao, contexto, acesso.agora().date())
    return traduzir_chaves(corpo)


class LoteDeFundos(BaseModel):
    """O corpo do lote: até 100 CNPJs, um `known_at` e um `assumed_return` para todos."""

    cnpjs: list[object]
    known_at: date | None = None
    assumed_return: float | None = None


# lê um CNPJ já validado: None se nada sai dele
LerUm = Callable[[str], Servido | None]


def _lote(
    contexto: ContextoDaChave,
    conjunto: str,
    cnpjs: list[object],
    dia: date,
    leitor: Callable[[sa.Connection, Porta], LerUm],
    finalidade: str = FINALIDADE,
) -> object:
    """Um lote de dado: cada CNPJ como na rota de um, com a situação de cada item; conta um pedido por
    CNPJ válido e distinto. O lote inteiro cabe na quota ou volta 429 antes de ler qualquer CNPJ."""
    try:
        lido = lote.ler_lote(cnpjs)
    except lote.LoteInvalidoError as erro:
        raise _recusa("invalid_batch") from erro
    itens: list[dict] = []
    fontes: set[str] = set()
    linhas = 0
    with obter_engine().begin() as conexao, piloto.anotar() as liberados:
        acesso.exigir_quota(conexao, contexto, lido.pedidos, acesso.agora())
        with _porta(conexao) as porta:
            ler = leitor(conexao, porta)
            for cnpj in lido.validos:
                servido = ler(cnpj)
                if servido is None:
                    itens.append({"cnpj": cnpj, "situacao_do_item": NAO_DISPONIVEL})
                    continue
                itens.append({"situacao_do_item": "ok"} | servido.corpo)
                fontes |= servido.fontes
                linhas += servido.linhas
        registrar_consumo(
            conexao, contexto, conjunto=conjunto, finalidade=finalidade,
            linhas=linhas, pedidos=lido.pedidos, agora=acesso.agora(),
        )  # fmt: skip
    itens += [
        {"cnpj": invalido, "situacao_do_item": "invalid_cnpj"}
        for invalido in lido.invalidos
    ]
    corpo = piloto.marcar({"como_era_em": dia.isoformat(), "itens": itens}, liberados)
    return traduzir_chaves(corpo | {"fontes": fontes_da_resposta(fontes)})


# o lote vem antes de `/funds/{cnpj}` só por clareza: um é POST, o outro GET
@router.post("/funds/batch")
def lote_de_fundos(pedido: LoteDeFundos, contexto: Chave) -> object:
    """O mesmo de `/funds/{cnpj}` para cada CNPJ; conta um pedido por CNPJ válido e distinto."""
    dia = _dia_pedido(pedido.known_at)
    retorno = _retorno_pedido(pedido.assumed_return)

    def leitor(conexao: sa.Connection, porta: Porta) -> LerUm:
        fundos_ = _leitor(conexao, porta, contexto)
        return lambda cnpj: fundos_.fundo(cnpj, dia, retorno)

    return _lote(contexto, fundos.CONJUNTO, pedido.cnpjs, dia, leitor)


def _um_pedido(
    contexto: ContextoDaChave,
    conjunto: str,
    ler: Callable[[sa.Connection, Porta], Servido | None],
    finalidade: str = FINALIDADE,
) -> object:
    """Um pedido de dado: lê, conta no consumo (a recusa conta como negada) e responde 404 se nada sai."""

    return _pedido_contado(contexto, conjunto, _pela_porta(ler), finalidade)


def _pela_porta(
    ler: Callable[[sa.Connection, Porta], Servido | None],
) -> Callable[[sa.Connection], Servido | None]:
    """A leitura com a porta da base aberta só durante ela."""

    def pela_porta(conexao: sa.Connection) -> Servido | None:
        with _porta(conexao) as porta:
            return ler(conexao, porta)

    return pela_porta


def _pedido_contado(
    contexto: ContextoDaChave,
    conjunto: str,
    ler: Callable[[sa.Connection], Servido | None],
    finalidade: str = FINALIDADE,
) -> object:
    """Lê, conta no consumo (a recusa conta como negada) e responde 404 se nada sai."""
    with piloto.anotar() as liberados:
        servido = _servido_contado(contexto, conjunto, ler, finalidade)
    corpo = piloto.marcar(servido.corpo, liberados)
    return traduzir_chaves(corpo | {"fontes": fontes_da_resposta(servido.fontes)})


def _servido_contado(
    contexto: ContextoDaChave,
    conjunto: str,
    ler: Callable[[sa.Connection], Servido | None],
    finalidade: str = FINALIDADE,
) -> Servido:
    """O que a leitura serviu, já contado no consumo (a recusa conta como negada); 404 se nada sai. O JSON
    e o deck passam por aqui: o mesmo portão, a mesma quota e a mesma conta de linhas. O registro do piloto é
    de quem chama (D11): o JSON o abre e marca o corpo; o deck o abre e põe a frase em todo slide. Quem não o
    abre não recebe campo de piloto."""
    with obter_engine().begin() as conexao:
        servido = ler(conexao)
        # o 404 sai depois do `with` para o consumo não voltar atrás
        registrar_consumo(
            conexao, contexto, conjunto=conjunto, finalidade=finalidade,
            linhas=0 if servido is None else servido.linhas, negado=servido is None,
            agora=acesso.agora(),
        )  # fmt: skip
    if servido is None:
        raise HTTPException(status_code=404, detail=NAO_DISPONIVEL)
    return servido


def _deck_contado(
    contexto: ContextoDaChave,
    conjunto: str,
    ler: Callable[[sa.Connection], Servido | None],
) -> tuple[Servido, piloto.Liberados]:
    """O que a leitura serviu para o deck, com o registro do piloto aberto (o mesmo dado do JSON)."""
    with piloto.anotar() as liberados:
        servido = _servido_contado(contexto, conjunto, ler)
    return servido, liberados


def _arquivo_do_deck(
    servido: Servido,
    liberados: piloto.Liberados,
    montar: Callable[[dict, list[dict], datetime], Apresentacao],
    nome: str,
) -> Response:
    """O deck do corpo servido como arquivo para baixar; `nome` só com o que a rota já validou. Com dado de
    piloto na resposta, todo slide leva a frase (D11.3)."""
    agora = acesso.agora().astimezone(deck.FUSO)
    apresentacao = montar(servido.corpo, fontes_da_resposta(servido.fontes), agora)
    if liberados.piloto:
        apresentacao = deck.com_aviso_de_piloto(apresentacao)
    return Response(
        content=deck.em_arquivo(apresentacao, agora),
        media_type=deck.TIPO_DO_ARQUIVO,
        headers={
            "Content-Disposition": f'attachment; filename="{nome}.pptx"',
            "Cache-Control": "no-store",
        },
    )


def _cnpj_pedido(cnpj: str) -> str:
    """O CNPJ do endereço, só com os números; 400 se não é um CNPJ."""
    lido = lote.ler_lote([cnpj])
    if not lido.validos:
        raise _recusa("invalid_cnpj")
    return lido.validos[0]


@router.get("/funds/{cnpj}")
def fundo(
    cnpj: str,
    contexto: Chave,
    known_at: date | None = None,
    assumed_return: float | None = None,
) -> object:
    """Taxas, custo da taxa e carteira do fundo como eram em `known_at`; o custo só com `assumed_return`."""
    numeros = _cnpj_pedido(cnpj)
    dia, retorno = _dia_pedido(known_at), _retorno_pedido(assumed_return)
    return _um_pedido(
        contexto,
        fundos.CONJUNTO,
        lambda conexao, porta: _leitor(conexao, porta, contexto).fundo(
            numeros, dia, retorno
        ),
    )


@router.get("/companies/{cnpj}/financials")
def demonstracoes_da_empresa(
    cnpj: str,
    contexto: Chave,
    known_at: date | None = None,
    period_end: date | None = None,
) -> object:
    """As DFP e os ITR da companhia como eram em `known_at`: um valor por conta e período, com o documento,
    a versão e a origem; `period_end` traz só o período que termina nesse dia."""
    numeros = _cnpj_pedido(cnpj)
    dia = _dia_pedido(known_at)

    def ler(conexao: sa.Connection, porta: Porta) -> Servido | None:
        leitor = demonstracoes.LeitorDeDemonstracoes(
            porta,
            _portao(conexao, contexto, demonstracoes.CONJUNTO),
            acesso.linhas_por_resposta(contexto),
        )
        return leitor.demonstracoes(numeros, dia, period_end)

    return _um_pedido(contexto, demonstracoes.CONJUNTO, ler)


class LoteDeEmpresas(BaseModel):
    """O corpo do lote: até 100 CNPJs e um `known_at` para todos."""

    cnpjs: list[object]
    known_at: date | None = None


def _leitor_de_empresas(
    conexao: sa.Connection, porta: Porta, contexto: ContextoDaChave
) -> empresas.LeitorDeEmpresas:
    return empresas.LeitorDeEmpresas(
        porta, _portao(conexao, contexto, empresas.CONJUNTO)
    )


@router.get("/companies")
def busca_de_empresas(
    contexto: Chave,
    cnae: Annotated[list[str], Query()] = [],  # noqa: B006 - o FastAPI copia o padrão
    state: Annotated[list[str], Query()] = [],  # noqa: B006
    municipality: Annotated[list[str], Query()] = [],  # noqa: B006
    size: Annotated[list[str], Query()] = [],  # noqa: B006
    legal_nature: Annotated[list[str], Query()] = [],  # noqa: B006
    registration_status: Annotated[list[str], Query()] = [],  # noqa: B006
    opened_before: date | None = None,
    opened_after: date | None = None,
    head_office: bool | None = None,
    capital_min: float | None = None,
    capital_max: float | None = None,
    branches_min: int | None = None,
    sort: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    known_at: date | None = None,
) -> object:
    """Busca de empresas (só pessoa jurídica: sem MEI nem empresário individual) por atividade (CNAE),
    UF, município, porte, natureza jurídica, situação, abertura, matriz, capital social (`capital_min`,
    `capital_max`) e número mínimo de estabelecimentos ativos (`branches_min`), no retrato da Receita que
    valia em `known_at`. `sort` ordena por `capital` ou `branches` (`-` na frente é decrescente); sem ele,
    por CNPJ. Capital e estabelecimentos são sinais aproximados de porte, não faturamento. Pelo menos um
    filtro; 50 por página (máximo 100); `next_cursor` traz a seguinte."""
    dia = _dia_pedido(known_at)
    try:
        busca = prospeccao.busca_dos_pedidos(
            cnae=cnae, state=state, municipality=municipality, size=size,
            legal_nature=legal_nature, registration_status=registration_status,
            opened_before=opened_before, opened_after=opened_after, head_office=head_office,
            cursor=cursor, limit=limit, capital_min=capital_min, capital_max=capital_max,
            branches_min=branches_min, sort=sort,
        )  # fmt: skip
    except prospeccao.FiltroInvalido as erro:
        raise _recusa(erro.codigo) from erro
    return _um_pedido(
        contexto,
        prospeccao.CONJUNTO,
        lambda conexao, porta: prospeccao.LeitorDeProspeccao(
            porta,
            _portao(conexao, contexto, prospeccao.CONJUNTO),
            acesso.linhas_por_resposta(contexto),
        ).buscar(busca, dia),
    )


@router.get("/buyers")
def compradores_do_setor(
    contexto: Chave,
    cnae: str,
    state: str | None = None,
    years: int | None = None,
    limit: int | None = None,
    known_at: date | None = None,
) -> object:
    """Quem já se mexeu num setor (só pessoa jurídica): as empresas que entraram como sócias de uma empresa
    com estabelecimento ativo do CNAE (`cnae`, classe de 5 ou subclasse de 7 dígitos; na UF `state`, se
    dada) nos últimos `years` anos (padrão 3, até 10), os FIPs sócios dessas empresas e as companhias abertas
    com controlada no setor, como era em `known_at`. Cada comprador traz os sinais e até 5 exemplos por
    sinal, com fonte e data; `limit` (padrão 20, até 50). Movimento passado, não intenção de compra."""
    dia = _dia_pedido(known_at)
    try:
        pedido = compradores.pedido_dos_parametros(cnae, state, years, limit)
    except compradores.PedidoInvalido as erro:
        raise _recusa(erro.codigo) from erro
    return _um_pedido(
        contexto,
        compradores.CONJUNTO,
        lambda conexao, porta: compradores.LeitorDeCompradores(
            porta,
            _portao(conexao, contexto, compradores.CONJUNTO),
            acesso.linhas_por_resposta(contexto),
        ).compradores(pedido, dia),
    )


def _novidades_do_contrato(
    contexto: ContextoDaChave, conexao: sa.Connection, dias: int
) -> novidades.NovidadesServidas | None:
    """As novidades, só se o contrato da organização tem o conjunto `research` (D8); senão 404 e negado."""
    hoje = acesso.agora().date()
    if not acesso.contrato_permite(
        conexao,
        contexto.organizacao_id,
        conjunto=novidades.CONJUNTO,
        finalidade=FINALIDADE,
        dia=hoje,
    ):
        return None
    return novidades.novidades(dias, acesso.linhas_por_resposta(contexto), hoje)


@router.get("/research/news")
def novidades_da_pesquisa(contexto: Chave, days: int | None = None) -> object:
    """As fontes que a pesquisa provou nos últimos `days` dias (padrão 7, até 30): cada uma com o órgão
    público, a data, o trecho literal e o sha256 do original. Só o que tem prova gravada; sem nada novo, a
    lista vem vazia."""
    try:
        dias = novidades.dias_do_pedido(days)
    except novidades.PedidoInvalido as erro:
        raise _recusa(erro.codigo) from erro
    return _pedido_contado(
        contexto,
        novidades.CONJUNTO,
        lambda conexao: _novidades_do_contrato(contexto, conexao, dias),
    )


# antes de `/companies/{cnpj}` só por clareza: um é POST, o outro GET
@router.post("/companies/batch")
def lote_de_empresas(pedido: LoteDeEmpresas, contexto: Chave) -> object:
    """O mesmo de `/companies/{cnpj}` para cada CNPJ; conta um pedido por CNPJ válido e distinto."""
    dia = _dia_pedido(pedido.known_at)

    def leitor(conexao: sa.Connection, porta: Porta) -> LerUm:
        empresas_ = _leitor_de_empresas(conexao, porta, contexto)
        return lambda cnpj: empresas_.empresa(cnpj, dia)

    return _lote(contexto, empresas.CONJUNTO, pedido.cnpjs, dia, leitor)


@router.get("/companies/{cnpj}")
def empresa(cnpj: str, contexto: Chave, known_at: date | None = None) -> object:
    """A situação cadastral do estabelecimento na Receita como era em `known_at` (o retrato mensal mais
    novo já público); MEI, empresário individual e o que não é empresa saem `not_available`."""
    numeros = _cnpj_pedido(cnpj)
    dia = _dia_pedido(known_at)
    return _um_pedido(
        contexto,
        empresas.CONJUNTO,
        lambda conexao, porta: _leitor_de_empresas(conexao, porta, contexto).empresa(
            numeros, dia
        ),
    )


@router.get("/companies/{cnpj}/profile")
def perfil_da_empresa(
    cnpj: str, contexto: Chave, known_at: date | None = None
) -> object:
    """O perfil da empresa como era em `known_at`: o cadastro na Receita (o mesmo de `/companies/{cnpj}`)
    e, da companhia aberta, cada DFP e ITR que ela devia até o dia, com o prazo da CVM, a entrega e a
    situação da entrega. MEI, empresário individual e o que não é empresa saem `not_available`."""
    numeros = _cnpj_pedido(cnpj)
    dia = _dia_pedido(known_at)
    return _um_pedido(
        contexto,
        ficha.CONJUNTO,
        lambda conexao, porta: ficha.LeitorDeFicha(
            porta, _portao(conexao, contexto, ficha.CONJUNTO)
        ).ficha(numeros, dia),
    )


DO_DECK = {
    200: {"content": {deck.TIPO_DO_ARQUIVO: {}}, "description": "o deck (.pptx)"}
}


@router.get("/companies/{cnpj}/deck", response_class=Response, responses=DO_DECK)
def deck_da_empresa(
    cnpj: str, contexto: Chave, known_at: date | None = None
) -> Response:
    """O perfil da empresa (o mesmo de `/companies/{cnpj}/profile`, com o mesmo contrato `profiles`) como
    deck `.pptx`: o cadastro e as entregas à CVM, com a fonte e o dia de cada tabela, as fontes e os
    limites. Conta na quota como o JSON."""
    numeros = _cnpj_pedido(cnpj)
    dia = _dia_pedido(known_at)
    servido, liberados = _deck_contado(
        contexto,
        ficha.CONJUNTO,
        _pela_porta(
            lambda conexao, porta: ficha.LeitorDeFicha(
                porta, _portao(conexao, contexto, ficha.CONJUNTO)
            ).ficha(numeros, dia)
        ),
    )
    return _arquivo_do_deck(
        servido, liberados, deck.da_empresa, f"tickerlab-empresa-{numeros}"
    )


@router.get("/sectors/{key}/deck", response_class=Response, responses=DO_DECK)
def deck_do_setor(key: str, contexto: Chave, known_at: date | None = None) -> Response:
    """O setor (o mesmo de `/sectors/{key}`, com o mesmo contrato `sectors` e o mesmo corte do plano) como
    deck `.pptx`: a concentração, a parte de cada companhia e quem são, com a fonte e o dia de cada
    tabela, as fontes e os limites. Conta na quota como o JSON."""
    dia = _dia_pedido(known_at)
    servido, liberados = _deck_contado(
        contexto, setores.CONJUNTO, _leitura_do_setor(contexto, key, dia)
    )
    # o nome do arquivo sai da chave que o leitor achou na lista do relatório, nunca do endereço cru
    return _arquivo_do_deck(
        servido,
        liberados,
        deck.do_setor,
        f"tickerlab-setor-{servido.corpo['setor']}",
    )


@router.get("/companies/{cnpj}/events")
def eventos_da_empresa(
    cnpj: str,
    contexto: Chave,
    known_at: date | None = None,
    types: Annotated[list[str], Query()] = [],  # noqa: B006 - o FastAPI copia o padrão
    cursor: str | None = None,
    limit: int | None = None,
) -> object:
    """Os eventos da empresa como eram em `known_at`, do mais novo ao mais velho: cada documento entregue à
    CVM pelo IPE (`ipe_filing`: fato relevante, comunicado, assembleia...) e cada troca de auditor
    (`auditor_change`). `types` filtra; a página vai até `limit` linhas (sem ele, até o limite do plano; o
    plano é o teto) e `next_cursor` traz a seguinte. Um tipo pedido que não está disponível para a organização
    vem em `unavailable_event_types` (não foi consultado: a lista não diz nada sobre ele); se nenhum tipo pedido
    está, a resposta é `not_available`, como para MEI, empresário individual e o que não é empresa."""
    numeros = _cnpj_pedido(cnpj)
    dia = _dia_pedido(known_at)
    try:
        tipos = eventos.tipos_do_pedido(types)
        if cursor is not None:
            eventos.chave_do_cursor(cursor)
        if limit is not None and limit < 1:
            raise eventos.PedidoInvalido("invalid_limit")
    except eventos.PedidoInvalido as erro:
        raise _recusa(erro.codigo) from erro
    do_plano = acesso.linhas_por_resposta(contexto)
    return _um_pedido(
        contexto,
        eventos.CONJUNTO,
        lambda conexao, porta: eventos.LeitorDeEventos(
            porta,
            _portao(conexao, contexto, eventos.CONJUNTO),
            do_plano if limit is None else min(limit, do_plano),
        ).eventos(numeros, dia, tipos, cursor),
    )


@router.get("/companies/{cnpj}/assets")
def ativos_da_empresa(
    cnpj: str, contexto: Chave, known_at: date | None = None
) -> object:
    """Os ativos físicos da empresa como eram em `known_at`, um bloco por base aberta de agência. Hoje sai um
    bloco: os contratos de exploração e produção de petróleo e gás da ANP (`oil_gas_contracts`), com a parte
    da empresa em cada um. Mineração (barragens e royalties da ANM) ainda não sai, e `not_covered` diz isso.
    O bloco diz se achou a empresa, a fonte e o dia do dado mais novo; `not_covered` diz o que a rota não
    traz. A lista vai até o limite de linhas do plano (`truncated`). MEI, empresário individual e o que não é
    empresa saem `not_available`."""
    numeros = _cnpj_pedido(cnpj)
    dia = _dia_pedido(known_at)
    return _um_pedido(
        contexto,
        ativos.CONJUNTO,
        lambda conexao, porta: ativos.LeitorDeAtivos(
            porta,
            _portao(conexao, contexto, ativos.CONJUNTO),
            acesso.linhas_por_resposta(contexto),
        ).ativos(numeros, dia),
    )


@router.get("/companies/{cnpj}/links")
def vinculos_da_empresa(
    cnpj: str,
    contexto: Chave,
    known_at: date | None = None,
    depth: int = 1,
    types: Annotated[list[str], Query()] = [],  # noqa: B006 - o FastAPI copia o padrão
) -> object:
    """Os vínculos da empresa como eram em `known_at`, de 1 a 3 saltos (`depth`): de quem ela era controlada,
    coligada ou participada e quem ela controlava (`subsidiary_of`, `affiliate_of`, `investee_of`, pelo FRE) e
    a firma que a auditava (`audits`, pelo FCA). `types` filtra; a lista vai até o limite de linhas do plano
    (`truncated`). O tipo pedido que não está disponível para a organização não foi consultado e vem em
    `unavailable_link_types` (os `limits` não falam da fonte dele); se nenhum tipo pedido está disponível, a
    resposta é `not_available`. MEI, empresário individual e o que não é empresa saem `not_available`."""
    numeros = _cnpj_pedido(cnpj)
    dia = _dia_pedido(known_at)
    try:
        profundidade = vinculos.profundidade_do_pedido(depth)
        tipos = vinculos.tipos_do_pedido(types)
    except vinculos.PedidoInvalido as erro:
        raise _recusa(erro.codigo) from erro
    return _um_pedido(
        contexto,
        vinculos.CONJUNTO,
        lambda conexao, porta: vinculos.LeitorDeVinculos(
            porta,
            _portao(conexao, contexto, vinculos.CONJUNTO),
            acesso.linhas_por_resposta(contexto),
        ).vinculos(numeros, dia, profundidade, tipos),
    )


@router.get("/companies/{cnpj}/comparables")
def comparaveis_da_empresa(
    cnpj: str, contexto: Chave, known_at: date | None = None
) -> object:
    """Os comparáveis da companhia aberta como eram em `known_at`: as companhias do mesmo grupo de setores
    (pelo setor do FCA), cada uma com os números do último DFP já entregue (receita, EBITDA, lucro, dívida
    líquida e as razões), e a mediana de cada razão entre os pares. Empresa sem FCA no dia, MEI,
    empresário individual e o que não é empresa saem `not_available`."""
    numeros = _cnpj_pedido(cnpj)
    dia = _dia_pedido(known_at)
    return _um_pedido(
        contexto,
        comparaveis.CONJUNTO,
        lambda conexao, porta: comparaveis.LeitorDeComparaveis(
            porta,
            _portao(conexao, contexto, comparaveis.CONJUNTO),
            acesso.linhas_por_resposta(contexto),
        ).comparaveis(numeros, dia),
    )


def _leitor_de_credito(
    conexao: sa.Connection, porta: Porta, contexto: ContextoDaChave
) -> credito.LeitorDeCredito:
    return credito.LeitorDeCredito(
        porta,
        _portao(conexao, contexto, credito.CONJUNTO, FINALIDADE_DE_CREDITO),
    )


# antes de `/credit/{cnpj}` só por clareza: um é POST, o outro GET
@router.post("/credit/batch")
def lote_de_credito(pedido: LoteDeEmpresas, contexto: Chave) -> object:
    """O mesmo de `/credit/{cnpj}` para cada CNPJ (os sacados de uma carteira, por exemplo); conta um
    pedido por CNPJ válido e distinto."""
    dia = _dia_pedido(pedido.known_at)

    def leitor(conexao: sa.Connection, porta: Porta) -> LerUm:
        credito_ = _leitor_de_credito(conexao, porta, contexto)
        return lambda cnpj: credito_.ficha(cnpj, dia)

    return _lote(
        contexto, credito.CONJUNTO, pedido.cnpjs, dia, leitor, FINALIDADE_DE_CREDITO
    )


@router.get("/credit/{cnpj}")
def ficha_de_credito(
    cnpj: str, contexto: Chave, known_at: date | None = None
) -> object:
    """Os fatos da ficha de crédito da empresa (cedente ou sacado) como eram em `known_at`, cada um com a
    fonte e o dia em que ficou público; fatos, sem regra, nota nem opinião. MEI, empresário individual e
    o que não é empresa saem `not_available`."""
    numeros = _cnpj_pedido(cnpj)
    dia = _dia_pedido(known_at)
    return _um_pedido(
        contexto,
        credito.CONJUNTO,
        lambda conexao, porta: _leitor_de_credito(conexao, porta, contexto).ficha(
            numeros, dia
        ),
        FINALIDADE_DE_CREDITO,
    )


@router.get("/sectors")
def lista_de_setores(contexto: ChaveSemQuota) -> object:
    """Os setores que a última noite gravou, com o dia dela; não serve dado (não gasta a quota do mês)."""
    return traduzir_chaves({"setores": setores.disponiveis()})


@router.get("/sectors/{key}")
def setor(key: str, contexto: Chave, known_at: date | None = None) -> object:
    """O mercado do setor (tamanho, CR4 e HHI por ano), a participação de cada companhia aberta e quem
    são, como a última noite os deixou; `known_at` antes da noite sai `not_available`."""
    dia = _dia_pedido(known_at)
    return _pedido_contado(
        contexto, setores.CONJUNTO, _leitura_do_setor(contexto, key, dia)
    )


def _leitura_do_setor(
    contexto: ContextoDaChave, chave: str, dia: date
) -> Callable[[sa.Connection], Servido | None]:
    """A leitura do setor para um pedido (a mesma no JSON e no deck), com o corte de linhas do plano."""

    def ler(conexao: sa.Connection) -> Servido | None:
        leitor = setores.LeitorDeSetores(
            _portao(conexao, contexto, setores.CONJUNTO),
            acesso.linhas_por_resposta(contexto),
        )
        return leitor.setor(chave, dia)

    return ler
