"""Pessoa física na tela da equipe (ADR 0128, Emenda 1; linha 808): os sócios da empresa da ficha.

`POST /v1/analista/ficha/pessoas` devolve, do cadastro público da Receita, os sócios pessoa física adultos do
CNPJ pedido: nome, qualificação e data de entrada. Sem CPF e sem menor de idade (o acervo já nasce assim).

Quem vê: a conta logada, com os termos aceitos e o plano da ficha, **e** membro de uma organização cujo
contrato tem a permissão `pessoa_na_tela` vigente (`src/banco/membros_da_organizacao.py`). A permissão nasce
desligada e é conferida aqui, no servidor, a cada pedido. Para qualquer outra conta a rota responde o mesmo
404 de um endereço que não existe, **antes** de ler o corpo, validar o CNPJ ou abrir o acervo: a resposta e o
tempo dela não dependem do que foi pedido, então não dizem se a empresa tem sócio pessoa física. Por isso o
corpo não é um parâmetro da rota (o FastAPI o leria antes da permissão): quem o lê é `pedido_de_quem_pode`,
que só roda depois de `organizacao_que_ve_pessoa`.

O acervo de pessoa fica fora da base e é lido só por `src/analista/pessoa.py`: nada daqui passa pela Porta,
pelo portão ou pela API por chave. Cada consulta atendida vai para a auditoria com a conta, a organização,
o tipo e quantas linhas saíram; nunca o CNPJ nem um nome. O log do app grava só o estado.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ValidationError

from src import auditoria
from src.analista import pessoa
from src.api_v1 import analista
from src.api_v1.acesso import conta_com_acesso, exigir_api_ligada
from src.banco import membros_da_organizacao as membros
from src.banco.conexao import obter_engine
from src.banco.usuarios import Usuario

log = logging.getLogger(__name__)

PRONTA = "pronta"
SEM_SOCIOS = "sem_socios"
TIPO_SOCIOS = "socios"

Conta = Annotated[Usuario, Depends(conta_com_acesso)]
router = APIRouter(prefix="/v1/analista", dependencies=[Depends(exigir_api_ligada)])


class SocioDaEmpresaV1(BaseModel):
    nome: str
    qualificacao: str
    entrou_em: str | None  # AAAA-MM-DD


class FonteDosSociosV1(BaseModel):
    fonte: str
    atribuicao: str
    mes_do_retrato: str | None  # AAAA-MM do retrato da Receita de onde a lista saiu


class SociosDaEmpresaV1(BaseModel):
    """Os sócios pessoa física da empresa: o estado, a lista, o total (a lista pode vir cortada), a fonte
    e os limites, sempre."""

    estado: (
        str  # "pronta" ou "sem_socios" (nenhum sócio pessoa física adulto no retrato)
    )
    socios: list[SocioDaEmpresaV1]
    total: int
    fonte: FonteDosSociosV1
    limites: list[str]


def organizacao_que_ve_pessoa(conta: Conta) -> uuid.UUID:
    """A organização pela qual a conta vê pessoa hoje; senão o 404 de um endereço que não existe."""
    with obter_engine().connect() as banco:
        organizacao = membros.organizacao_que_ve_pessoa(
            banco, conta.id, analista.hoje()
        )
    if organizacao is None:
        raise HTTPException(status_code=404)  # o mesmo corpo da rota inexistente
    return organizacao


Organizacao = Annotated[uuid.UUID, Depends(organizacao_que_ve_pessoa)]


async def pedido_de_quem_pode(
    _organizacao: Organizacao, request: Request
) -> analista.PedidoDaFichaV1:
    """O corpo do pedido, lido só depois da permissão; 422 sem repetir o que veio."""
    try:
        return analista.PedidoDaFichaV1.model_validate(await request.json())
    except (ValueError, ValidationError) as erro:
        raise HTTPException(status_code=422, detail=analista.CNPJ_INVALIDO) from erro


Pedido = Annotated[analista.PedidoDaFichaV1, Depends(pedido_de_quem_pode)]


def _registrar(conta: Usuario, organizacao: uuid.UUID, linhas: int) -> None:
    with obter_engine().begin() as banco:
        auditoria.registrar(
            banco,
            conta.id,
            auditoria.ACAO_PESSOA_VISTA,
            alvo_id=organizacao,
            detalhes={"tipo": TIPO_SOCIOS, "linhas": linhas},
        )


@router.post("/ficha/pessoas")
def socios_da_ficha(
    conta: Conta,
    organizacao: Organizacao,
    pedido: Pedido,
    resposta: Response,
) -> SociosDaEmpresaV1:
    """Os sócios pessoa física adultos do CNPJ, do quadro da Receita: nome, qualificação e data de entrada.
    Só para a organização com a permissão; para as outras contas a rota não existe (404)."""
    if len(pedido.cnpj) > analista.TAMANHO_MAXIMO_DO_CNPJ:
        raise HTTPException(status_code=422, detail=analista.CNPJ_INVALIDO)
    try:
        socios = pessoa.socios_da_empresa(pessoa.pasta_do_acervo(), pedido.cnpj)
    except pessoa.CnpjInvalidoError as erro:
        raise HTTPException(status_code=422, detail=analista.CNPJ_INVALIDO) from erro
    except pessoa.AcervoIndisponivelError as erro:
        raise HTTPException(status_code=503, detail=analista.BASE_FORA_DO_AR) from erro
    # a auditoria vem antes da resposta: se não gravar, nada sai
    _registrar(conta, organizacao, len(socios.socios))
    estado = PRONTA if socios.socios else SEM_SOCIOS
    log.info("sócios da ficha: %s", estado)  # só o estado, nunca o CNPJ nem um nome
    resposta.headers["Cache-Control"] = "no-store"
    return SociosDaEmpresaV1(
        estado=estado,
        socios=[SocioDaEmpresaV1.model_validate(socio) for socio in socios.socios],
        total=socios.total,
        fonte=FonteDosSociosV1(
            fonte=pessoa.FONTE,
            atribuicao=pessoa.ATRIBUICAO,
            mes_do_retrato=socios.mes_do_retrato,
        ),
        limites=list(pessoa.LIMITES),
    )
