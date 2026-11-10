"""As rotas da tela do analista (linha 798): a ficha de uma empresa no app, com login e plano.

`POST /v1/analista/ficha` devolve a ficha do CNPJ pedido (cadastro na Receita e, da companhia aberta, as
entregas à CVM), e `POST /v1/analista/ficha/planilha` a mesma ficha em Excel. As duas pedem a conta logada,
os termos aceitos e o plano da página `ficha_da_empresa` (`src/paginas.py`, recurso Dossiê da base).

Nada aqui lê a base por outro caminho: a porta e as regras do portão são as da API externa
(`src/api_externa/rotas.py`, `abrir_porta` e `regras_da_api`), e a leitura é a do leitor da API
(`src/analista/leitura.py`). Assim a tela mostra só o que a API mostraria.

É POST porque o CNPJ vai no corpo, não no endereço (não vai para o log de acesso); o log do app grava só o
estado da resposta, e o nome do arquivo da planilha não leva o CNPJ.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime
from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from base.porta import Porta
from src.analista import leitura, planilha
from src.api_externa import rotas as rotas_da_api_externa
from src.api_externa.conjuntos.ficha import LIMITES
from src.api_v1 import esquemas
from src.api_v1.acesso import conta_com_acesso, exigir_api_ligada
from src.banco.conexao import obter_engine
from src.banco.usuarios import Usuario
from src.bcb import FUSO

log = logging.getLogger(__name__)

PAGINA = "ficha_da_empresa"
NOME_DA_PLANILHA = (
    "ficha-da-empresa-tickerlab.xlsx"  # sem o CNPJ: o nome não vai para o disco alheio
)
TIPO_DA_PLANILHA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TAMANHO_MAXIMO_DO_CNPJ = 32  # com pontuação e espaços; o resto é erro de quem chama
CNPJ_INVALIDO = "CNPJ inválido: confira os 14 caracteres."
FICHA_INDISPONIVEL = "Ficha não disponível."
BASE_FORA_DO_AR = "A base não está disponível agora. Tente de novo em alguns minutos."

Conta = Annotated[Usuario, Depends(conta_com_acesso)]
router = APIRouter(prefix="/v1/analista", dependencies=[Depends(exigir_api_ligada)])


class PedidoDaFichaV1(BaseModel):
    cnpj: str  # sem limite aqui: o 422 do FastAPI repetiria o texto pedido (o limite fica na rota)


def hoje() -> date:
    """O dia de hoje no Brasil (os testes trocam esta função)."""
    return datetime.now(FUSO).date()


@contextmanager
def _porta() -> Generator[Porta]:
    """A porta da API externa; 503 sem dizer onde nem por quê se a base não está neste servidor."""
    with obter_engine().connect() as banco:
        try:
            porta = rotas_da_api_externa.abrir_porta(banco)
        except (ImportError, OSError, ValueError) as erro:
            raise HTTPException(status_code=503, detail=BASE_FORA_DO_AR) from erro
        with porta:
            try:
                yield porta
            except (duckdb.Error, OSError) as erro:
                raise HTTPException(status_code=503, detail=BASE_FORA_DO_AR) from erro


def _ficha_do_pedido(pedido: PedidoDaFichaV1) -> leitura.Resposta:
    if len(pedido.cnpj) > TAMANHO_MAXIMO_DO_CNPJ:
        raise HTTPException(status_code=422, detail=CNPJ_INVALIDO)
    with _porta() as porta:
        try:
            resposta = leitura.ficha(
                porta,
                pedido.cnpj,
                hoje=hoje(),
                regras=rotas_da_api_externa.regras_da_api(),
            )
        except ValueError as erro:
            raise HTTPException(status_code=422, detail=CNPJ_INVALIDO) from erro
    log.info("ficha do analista: %s", resposta.estado)  # só o estado, nunca o CNPJ
    return resposta


@router.post("/ficha")
def ficha_da_empresa(
    _conta: Conta, pedido: PedidoDaFichaV1
) -> esquemas.FichaDaEmpresaV1:
    """A ficha do CNPJ: o cadastro na Receita e, da companhia aberta, as entregas à CVM, cada campo com a
    fonte e o dia em que ficou público. Pessoa (MEI, empresário individual) e CNPJ que a base não conhece
    saem `nao_disponivel`, sem dizer o motivo; o que o portão ainda não libera sai `nao_liberada`."""
    return esquemas.de_ficha_do_analista(_ficha_do_pedido(pedido), LIMITES)


@router.post("/ficha/planilha", response_class=Response)
def ficha_da_empresa_em_planilha(_conta: Conta, pedido: PedidoDaFichaV1) -> Response:
    """A mesma ficha em Excel (mesmo acesso, mesmo plano), com a aba das fontes e o aviso."""
    resposta = _ficha_do_pedido(pedido)
    if resposta.corpo is None:
        raise HTTPException(status_code=404, detail=FICHA_INDISPONIVEL)
    corpo = resposta.corpo | {"fontes": resposta.fontes}
    return Response(
        content=planilha.xlsx(corpo),
        media_type=TIPO_DA_PLANILHA,
        headers={
            "Content-Disposition": f'attachment; filename="{NOME_DA_PLANILHA}"',
            "Cache-Control": "no-store",
        },
    )
