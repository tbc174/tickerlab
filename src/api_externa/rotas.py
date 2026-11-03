"""As rotas da API externa do TickerLab Data, em `/data/v1` (B-32a; ADR 0108).

Só entram no app com `TICKERLAB_API_EXTERNA=1` (`src/api.py`). Cada rota recebe a organização pela
chave (`acesso`), faz a conta em `src/` e traduz as chaves para o inglês na saída, num lugar só
(`nomes.traduzir_chaves`). O catálogo e o consumo não servem dado: não gastam a quota do mês nem entram
no consumo, mas contam no limite do minuto.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api_externa import acesso
from src.api_externa.catalogo import catalogo_da_organizacao, consumo_da_organizacao
from src.api_externa.nomes import traduzir_chaves
from src.banco.conexao import obter_engine
from src.chaves_da_api import ContextoDaChave
from src.portao_externo import Regras

router = APIRouter(prefix="/data/v1")

ChaveSemQuota = Annotated[
    ContextoDaChave, Depends(acesso.exigir_chave_sem_quota_do_mes)
]


def regras_da_api() -> Regras | None:
    """As regras do portão: None vale as vigentes (os testes trocam esta função)."""
    return None


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
