"""O pregão do dia na API, sem conta e só leitura (plano `2026-10-28-raio-x-todo-dia`, PR 5).

O servidor de casa monta o resumo de cada pregão (`scripts/gerar_pregao_do_dia.py`) e o manda ao VPS;
estas rotas leem essa pasta e devolvem o texto pelo molde aprovado, no mesmo formato da página do
site (`texto_do_pregao.para_o_site`). A data do pedido só vira nome de arquivo depois de lida como
data; o resto da pasta (e a `origem` de cada resumo, com caminhos do acervo) nunca sai.
"""

import json
import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from src import texto_do_pregao as tp
from src.api_v1.acesso import LimiteDePedidos, agora, exigir_api_ligada
from src.api_v1.base_publica import ORIGEM_DO_SITE
from src.api_v1.compartilhados import ip_de_quem_pede
from src.configuracao import PASTA_RAIZ

VARIAVEL_DA_PASTA = "TICKERLAB_PREGAO"
PASTA_PADRAO = PASTA_RAIZ / "dados_locais" / "pregao"
PEDIDOS_POR_MINUTO = 60
MAXIMO_NO_CACHE = 64
# O último pregão muda uma vez por dia (e quando a B3 corrige um dia); um pregão antigo, quase nunca.
SEGUNDOS_NO_CACHE_DO_ULTIMO = 300
SEGUNDOS_NO_CACHE_DO_DIA = 3600
_NOME_DO_ARQUIVO = re.compile(r"\d{4}-\d{2}-\d{2}\.json")
SEM_PREGAO = "Nenhum pregão guardado para essa data."
INDISPONIVEL = "O pregão do dia está indisponível agora. Tente novamente mais tarde."
LIMITE_POR_IP = LimiteDePedidos(PEDIDOS_POR_MINUTO)


def pasta_dos_pregoes() -> Path:
    """A pasta que o servidor de casa manda ao VPS (`dados_locais/pregao`, se não disserem outra)."""
    return Path(os.environ.get(VARIAVEL_DA_PASTA) or PASTA_PADRAO)


def _cabecalhos(request: Request) -> dict[str, str]:
    cabecalhos = {"Vary": "Origin"}
    if request.headers.get("origin") == ORIGEM_DO_SITE:
        cabecalhos["Access-Control-Allow-Origin"] = ORIGEM_DO_SITE
    return cabecalhos


def _recusar(request: Request, status: int, detalhe: str) -> HTTPException:
    return HTTPException(status, detalhe, headers=_cabecalhos(request))


def conferir_pedido(request: Request) -> None:
    """Conta também os pedidos recusados e os que saem do cache."""
    if not LIMITE_POR_IP.permitir(ip_de_quem_pede(request), agora()):
        raise _recusar(request, 429, "Muitos pedidos: espere um minuto.")


router = APIRouter(
    prefix="/v1/estudos/pregao",
    dependencies=[Depends(exigir_api_ligada), Depends(conferir_pedido)],
)


@lru_cache(maxsize=MAXIMO_NO_CACHE)
def _texto(caminho: Path, modificado_em: int) -> dict[str, Any]:
    # a hora do arquivo faz parte da chave: o pregão que a B3 corrigiu e o servidor refez sai novo
    del modificado_em
    resumo = json.loads(caminho.read_text(encoding="utf-8"))
    return {
        "molde_aprovado": tp.IMPRESSAO_DO_MOLDE_APROVADO,
        "pregao": tp.texto_do_pregao(resumo, tp.ler_molde()),
    }


def limpar_cache() -> None:
    """Zera o limite e o cache (testes e troca manual dos arquivos)."""
    LIMITE_POR_IP.zerar()
    _texto.cache_clear()


def _ultimo_arquivo(pasta: Path) -> Path | None:
    nomes = sorted(
        a.name for a in pasta.glob("*.json") if _NOME_DO_ARQUIVO.fullmatch(a.name)
    )
    return pasta / nomes[-1] if nomes else None


def _arquivo_do_dia(texto: str) -> Path | None:
    """O arquivo do pregão pedido, ou None. Só uma data de verdade vira nome de arquivo."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        return None
    try:
        dia = date.fromisoformat(texto)
    except ValueError:
        return None
    return pasta_dos_pregoes() / f"{dia.isoformat()}.json"


def _responder(request: Request, arquivo: Path | None, segundos: int) -> JSONResponse:
    if arquivo is None or not arquivo.is_file():
        raise _recusar(request, 404, SEM_PREGAO)
    try:
        corpo = _texto(arquivo, arquivo.stat().st_mtime_ns)
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        # resumo estragado ou de outro formato: nada do erro (caminho, conteúdo) vai na resposta
        raise _recusar(request, 503, INDISPONIVEL) from None
    if corpo["pregao"]["impressao_digital"] != tp.IMPRESSAO_DO_MOLDE_APROVADO:
        # molde trocado sem o "pode": a página também recusaria, mas o texto nem sai daqui
        raise _recusar(request, 503, INDISPONIVEL)
    return JSONResponse(
        corpo,
        headers={
            **_cabecalhos(request),
            "Cache-Control": f"public, max-age={segundos}",
        },
    )


@router.get("/ultimo")
def ultimo(request: Request) -> JSONResponse:
    """O texto do pregão mais recente que o servidor mandou."""
    try:
        arquivo = _ultimo_arquivo(pasta_dos_pregoes())
    except OSError:
        raise _recusar(request, 503, INDISPONIVEL) from None
    return _responder(request, arquivo, SEGUNDOS_NO_CACHE_DO_ULTIMO)


@router.get("/{data}")
def do_dia(request: Request, data: str) -> JSONResponse:
    """O texto do pregão de `data` (AAAA-MM-DD)."""
    return _responder(request, _arquivo_do_dia(data), SEGUNDOS_NO_CACHE_DO_DIA)
