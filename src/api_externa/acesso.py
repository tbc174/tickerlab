"""Quem pode chamar a API externa: a organização cliente, pela chave dela (N7; plano D3 a D10).

A rota (B-32) recebe o `ContextoDaChave` de `exigir_chave` e, para cada campo que for servir, pergunta a
`autorizar`, que junta as duas travas do D8: o contrato da organização (`direitos_da_organizacao`) e o
portão da N3 (o direito do TickerLab de revender o campo). Depois de servir, a rota soma o pedido com
`registrar_consumo` (`src/banco/chaves_da_api.py`).

A chave entra só pelo cabeçalho (`Authorization: Bearer` ou `X-API-Key`). Pela URL ela iria para o log de
acesso do servidor e da Cloudflare: o pedido é recusado (400) sem ecoar nada. Toda recusa da chave é o
mesmo 401, com o mesmo corpo e os mesmos cabeçalhos; o motivo fica no log (`conferir_chave`). Os códigos
das respostas são em inglês, como os nomes externos do portão (ADR 0108, D7).
"""

from datetime import UTC, date, datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import Header, HTTPException, Request

from src.api_v1.acesso import LimiteDePedidos
from src.banco.chaves_da_api import (
    conferir_chave,
    consumo_do_mes,
    contrato_permite,
    e_organizacao_do_piloto,
)
from src.banco.conexao import obter_engine
from src.chaves_da_api import INICIO, ContextoDaChave
from src.planos import limites_da_api
from src.portao_externo import Decisao, Motivo, Pedido, Regras, decidir

CODIGO_DA_CHAVE_RECUSADA = "invalid_api_key"
CODIGO_DA_CHAVE_NA_URL = "api_key_in_url"
CODIGO_DO_LIMITE_DO_MINUTO = "rate_limited"
CODIGO_DA_QUOTA_DO_MES = "monthly_quota_exceeded"
# nomes de parâmetro que só serviriam para mandar a chave pela URL
PARAMETROS_DE_CHAVE = frozenset(
    {"api_key", "apikey", "api-key", "key", "token", "access_token", "chave"}
)
JANELA_DO_MINUTO = 60  # segundos


def agora() -> datetime:
    """A hora do pedido, em UTC (os testes trocam esta função)."""
    return datetime.now(UTC)


def _por_minuto(plano_da_api: str) -> int:
    return limites_da_api(plano_da_api).pedidos_por_minuto


# um limite por plano (cada um com o seu número), contado por organização: as chaves dela dividem a cota
_LIMITES_DO_MINUTO: dict[str, LimiteDePedidos] = {}


def _limite_do_minuto(plano_da_api: str) -> LimiteDePedidos:
    if plano_da_api not in _LIMITES_DO_MINUTO:
        _LIMITES_DO_MINUTO[plano_da_api] = LimiteDePedidos(
            por_minuto=_por_minuto(plano_da_api), janela=JANELA_DO_MINUTO
        )
    return _LIMITES_DO_MINUTO[plano_da_api]


def zerar_limites() -> None:
    """Esquece a contagem do minuto (para os testes)."""
    _LIMITES_DO_MINUTO.clear()


def _chave_recusada() -> HTTPException:
    # a mesma resposta para todo motivo (D3): status, corpo e cabeçalhos
    return HTTPException(
        status_code=401,
        detail=CODIGO_DA_CHAVE_RECUSADA,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _recusar_chave_na_url(request: Request) -> None:
    for nome, valor in request.query_params.multi_items():
        if nome.lower() in PARAMETROS_DE_CHAVE or f"{INICIO}_" in valor:
            raise HTTPException(status_code=400, detail=CODIGO_DA_CHAVE_NA_URL)


def _chave_do_cabecalho(authorization: str | None, x_api_key: str | None) -> str:
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    tipo, _, valor = (authorization or "").partition(" ")
    if tipo.lower() != "bearer" or not valor.strip():
        raise _chave_recusada()
    return valor.strip()


def _segundos_ate_o_mes_seguinte(momento: datetime) -> int:
    ano, mes = (
        (momento.year + 1, 1)
        if momento.month == 12
        else (momento.year, momento.month + 1)
    )
    virada = datetime(ano, mes, 1, tzinfo=UTC)
    return max(1, int((virada - momento).total_seconds()))


def _conferir_minuto(contexto: ContextoDaChave, momento: datetime) -> None:
    limite = _limite_do_minuto(contexto.plano_da_api)
    if not limite.permitir(str(contexto.organizacao_id), momento.timestamp()):
        raise HTTPException(
            status_code=429,
            detail=CODIGO_DO_LIMITE_DO_MINUTO,
            headers={"Retry-After": str(JANELA_DO_MINUTO)},
        )


def exigir_quota(
    conexao: sa.Connection,
    contexto: ContextoDaChave,
    pedidos: int,
    momento: datetime,
) -> None:
    """429 se `pedidos` a mais passam da quota do mês. O lote de N chama com N antes de servir.

    Dois lotes da mesma organização ao mesmo tempo podem passar juntos da quota em até um lote: a
    conferência e a soma não ficam na mesma trava. O plano aceita esse estouro (B-32a, risco 4).
    """
    if pedidos < 1:
        raise ValueError("Um pedido conta pelo menos 1 na quota.")
    por_mes = limites_da_api(contexto.plano_da_api).pedidos_por_mes
    ja_usados = consumo_do_mes(conexao, contexto.organizacao_id, momento.date()).pedidos
    if ja_usados + pedidos > por_mes:
        raise HTTPException(
            status_code=429,
            detail=CODIGO_DA_QUOTA_DO_MES,
            headers={"Retry-After": str(_segundos_ate_o_mes_seguinte(momento))},
        )


def _contexto_da_chave(
    request: Request,
    authorization: str | None,
    x_api_key: str | None,
    *,
    com_quota_do_mes: bool,
) -> ContextoDaChave:
    _recusar_chave_na_url(request)
    chave = _chave_do_cabecalho(authorization, x_api_key)
    momento = agora()
    with obter_engine().begin() as conexao:  # begin: grava o último uso da chave
        resultado = conferir_chave(conexao, chave, agora=momento)
        if not isinstance(resultado, ContextoDaChave):
            raise _chave_recusada()
        _conferir_minuto(resultado, momento)
        if com_quota_do_mes:
            exigir_quota(conexao, resultado, 1, momento)
    return resultado


def exigir_chave(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> ContextoDaChave:
    """Dependência do FastAPI: o contexto da organização dona da chave, ou 400, 401 ou 429."""
    return _contexto_da_chave(request, authorization, x_api_key, com_quota_do_mes=True)


def exigir_chave_sem_quota_do_mes(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> ContextoDaChave:
    """A mesma porta, sem a quota do mês: para o catálogo e o consumo, que não servem dado.

    Quem gastou a quota precisa conseguir ver que gastou. O limite do minuto continua valendo.
    """
    return _contexto_da_chave(request, authorization, x_api_key, com_quota_do_mes=False)


def linhas_por_resposta(contexto: ContextoDaChave) -> int:
    """Quantas linhas uma resposta pode ter no plano da organização (a rota corta ou pagina)."""
    return limites_da_api(contexto.plano_da_api).linhas_por_resposta


def autorizar(
    conexao: sa.Connection,
    contexto: ContextoDaChave,
    *,
    fonte: str,
    conjunto: str,
    campo: str,
    finalidade: str,
    hoje: date,
    derivado: bool = False,
    regras: Regras | None = None,
) -> Decisao:
    """Libera o campo só se o contrato da organização **e** o portão da N3 deixarem (D8).

    Sem linha de contrato vigente, nega antes de perguntar ao portão. O canal é sempre o do contexto
    (a API externa): não há como pedir pelo canal do app com uma chave. Para fora, toda negação é o
    mesmo `codigo_publico` do portão.
    """
    if not contrato_permite(
        conexao,
        contexto.organizacao_id,
        conjunto=conjunto,
        finalidade=finalidade,
        dia=hoje,
    ):
        return Decisao(False, Motivo.SEM_CONTRATO_DA_ORGANIZACAO)
    pedido = Pedido(
        fonte=fonte,
        conjunto=conjunto,
        campo=campo,
        canal=contexto.canal,
        finalidade=finalidade,
        derivado=derivado,
        # D11: a marca de piloto se confere aqui, no servidor, a cada pedido (desligada por padrão)
        piloto=e_organizacao_do_piloto(
            conexao, contexto.organizacao_id, finalidade=finalidade, dia=hoje
        ),
    )
    return decidir(pedido, hoje, regras)
