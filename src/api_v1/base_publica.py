"""Destaques públicos de companhias abertas, sem sessão, preço ou dados de conta.

Router separado dos endpoints autenticados, como ferramentas e compartilhados.
Cache limitado por dia; o portão das fontes é reconferido mesmo quando a ficha está no cache.
"""

import re
from datetime import date, datetime
from functools import lru_cache
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from base import cnpj as cnpjs
from base import dossie as regras
from base import vitrine
from src import dossie
from src.api_v1.acesso import LimiteDePedidos, agora, exigir_api_ligada
from src.api_v1.compartilhados import ip_de_quem_pede
from src.banco.conexao import obter_engine
from src.banco.modelo import setores_cvm, tickers_dos_emissores

PEDIDOS_POR_MINUTO = 60
MAXIMO_NO_CACHE = 512
MAXIMO_DE_RESULTADOS = 20
ORIGEM_DO_SITE = "https://tickerlab.com.br"
FORA_DA_BASE = (
    "Esta empresa ainda não está na base aberta. A busca pública mostra apenas companhias "
    "abertas com ficha. Não aparecer aqui não quer dizer que a empresa não exista."
)
LIMITE_POR_IP = LimiteDePedidos(PEDIDOS_POR_MINUTO)


def hoje() -> date:
    """Dia da consulta no fuso do produto."""
    return datetime.now(dossie.FUSO).date()


def _cabecalhos(request: Request) -> dict[str, str]:
    cabecalhos = {"Vary": "Origin"}
    if request.headers.get("origin") == ORIGEM_DO_SITE:
        cabecalhos["Access-Control-Allow-Origin"] = ORIGEM_DO_SITE
    return cabecalhos


def _recusar(request: Request, status: int, detalhe: object) -> HTTPException:
    return HTTPException(status, detalhe, headers=_cabecalhos(request))


def conferir_pedido(request: Request) -> None:
    """Conta também pedidos inválidos e respostas que já estão no cache."""
    if not LIMITE_POR_IP.permitir(ip_de_quem_pede(request), agora()):
        raise _recusar(request, 429, "Muitos pedidos: espere um minuto.")


router = APIRouter(
    prefix="/v1/base",
    dependencies=[Depends(exigir_api_ligada), Depends(conferir_pedido)],
)


def _consulta(texto: str) -> tuple[str, bool]:
    consulta = " ".join(texto.strip().upper().split())
    compacto = cnpjs.completo(consulta)
    parece_documento = (
        bool(re.fullmatch(r"[0-9./\- ]+", consulta)) or compacto is not None
    )
    if parece_documento:
        if compacto is None or not cnpjs.dv_confere(compacto):
            raise ValueError(
                "CNPJ inválido: confira os 14 caracteres e os dígitos verificadores."
            )
        return compacto, True
    if len(consulta) < 2:
        raise ValueError(
            "Digite um CNPJ, nome ou ticker com pelo menos dois caracteres."
        )
    return consulta, False


@lru_cache(maxsize=MAXIMO_NO_CACHE)
def _companhias(
    consulta: str, por_cnpj: bool, dia: date
) -> tuple[tuple[str, str], ...]:
    # Cadastro e tickers são públicos e comuns a todas as contas. Nenhuma tabela de usuário é lida.
    del dia
    tabela = tickers_dos_emissores
    if por_cnpj:
        # Companhia registrada na CVM pode ter ficha mesmo sem ação negociada na bolsa.
        pedido = sa.select(setores_cvm.c.cnpj, sa.literal("").label("empresa")).where(
            setores_cvm.c.cnpj.in_((consulta, cnpjs.formatar(consulta)))
        )
    else:
        pedido = (
            sa.select(tabela.c.cnpj, tabela.c.empresa)
            .join(setores_cvm, setores_cvm.c.cnpj == tabela.c.cnpj)
            .where(
                sa.or_(
                    sa.func.upper(tabela.c.codigo) == consulta.removesuffix(".SA"),
                    sa.func.upper(tabela.c.empresa).contains(consulta, autoescape=True),
                )
            )
        )
    # O nome "cnpj" também existe na tabela associada; ordene as colunas selecionadas.
    # PostgreSQL exige que toda ordenação do DISTINCT apareça na seleção.
    pedido = (
        pedido.distinct()
        .order_by(pedido.selected_columns.empresa, pedido.selected_columns.cnpj)
        .limit(MAXIMO_DE_RESULTADOS)
    )
    with obter_engine().connect() as conexao:
        return tuple((str(l.cnpj), str(l.empresa)) for l in conexao.execute(pedido))


@lru_cache(maxsize=MAXIMO_NO_CACHE)
def _ficha(cnpj: str, pasta: str, dia: date) -> dossie.Ficha | None:
    del (
        pasta,
        dia,
    )  # fazem parte da chave: outra base ou outro dia não reutiliza a ficha
    return dossie.ficha_do(cnpj)


def limpar_cache() -> None:
    """Limpa estado dos testes e permite invalidar as fichas após uma atualização manual."""
    LIMITE_POR_IP.zerar()
    _companhias.cache_clear()
    _ficha.cache_clear()


def _resposta(cnpj: str, dia: date) -> dict[str, object] | None:
    if not cnpjs.dv_confere(cnpj):
        return None
    ficha = _ficha(cnpj, str(dossie.pasta_das_fichas()), dia)
    if ficha is None or cnpjs.normalizar_cnpj(ficha.cnpj) != cnpj:
        return None
    destaques = vitrine.destaques_publicos(ficha)
    if not destaques:
        return None
    resultado: dict[str, object] = {
        "cnpj": cnpj,
        "empresa": ficha.empresa,
        "medido_em": dossie.dia_da_ficha(ficha).isoformat(),
        "fonte": sorted({d.fonte for d in destaques}),
        "destaques": [
            {
                "chave": d.chave,
                "titulo": d.titulo,
                "texto": d.texto,
                "fonte": d.fonte,
                "data": d.data,
            }
            for d in destaques
        ],
        "aviso": "Até três destaques da ficha da noite indicada. Nada aqui é recomendação de investimento.",
    }
    regras.conferir_sem_pessoas(resultado, set())
    return resultado


@router.get("/destaques")
def buscar(
    request: Request, q: Annotated[str, Query(min_length=1, max_length=120)]
) -> JSONResponse:
    """Busca por CNPJ, nome ou ticker; devolve apenas os agregados liberados para a vitrine."""
    try:
        consulta, por_cnpj = _consulta(q)
    except ValueError as erro:
        raise _recusar(request, 422, str(erro)) from None
    try:
        candidatas = _companhias(consulta, por_cnpj, hoje())
        for documento, _ in candidatas:
            cnpj = cnpjs.normalizar_cnpj(documento)
            if cnpj and (resultado := _resposta(cnpj, hoje())):
                return JSONResponse(
                    resultado,
                    headers={
                        **_cabecalhos(request),
                        "Cache-Control": "public, max-age=86400",
                    },
                )
    except (SQLAlchemyError, OSError, regras.PessoaNaFichaError):
        raise _recusar(
            request, 503, "A busca está indisponível agora. Tente novamente mais tarde."
        ) from None
    raise _recusar(
        request,
        404,
        {"mensagem": FORA_DA_BASE, "sugestoes": vitrine.empresas_da_base()},
    )
