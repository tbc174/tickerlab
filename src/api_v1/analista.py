"""As rotas da tela do analista (linha 798): a ficha de uma empresa e a busca de empresas, com login e plano.

`POST /v1/analista/ficha` devolve a ficha do CNPJ pedido (cadastro na Receita e, da companhia aberta, as
entregas à CVM), e `POST /v1/analista/ficha/planilha` a mesma ficha em Excel. As duas pedem a conta logada,
os termos aceitos e o plano da página `ficha_da_empresa` (`src/paginas.py`, recurso Dossiê da base).
`POST /v1/analista/empresas` busca empresas por setor, UF e idade mínima (página `encontrar_empresas`, o
mesmo recurso), e `POST /v1/analista/empresas/planilha` leva a busca para o Excel.
`POST /v1/analista/comparar` põe de dois a cinco CNPJs lado a lado (página `comparar_empresas`, o mesmo
recurso), e `POST /v1/analista/comparar/planilha` leva a comparação para o Excel.

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
from pydantic import BaseModel, Field

from base.porta import Porta
from src.analista import busca, comparacao, leitura, planilha
from src.api_externa import rotas as rotas_da_api_externa
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
PAGINA_DA_BUSCA = "encontrar_empresas"
NOME_DA_PLANILHA_DA_BUSCA = "empresas-tickerlab.xlsx"
TAMANHO_MAXIMO_DO_CURSOR = 64  # o cursor do leitor tem perto de vinte caracteres
BUSCA_INDISPONIVEL = "Busca não disponível: escolha um filtro e tente de novo."
FILTRO_INVALIDO = "Filtro fora do que a tela oferece."
TIPO_DA_PLANILHA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TAMANHO_MAXIMO_DO_CNPJ = 32  # com pontuação e espaços; o resto é erro de quem chama
CNPJ_INVALIDO = "CNPJ inválido: confira os 14 caracteres."
FICHA_INDISPONIVEL = "Ficha não disponível."
PAGINA_DA_COMPARACAO = "comparar_empresas"
NOME_DA_PLANILHA_DA_COMPARACAO = "comparacao-de-empresas-tickerlab.xlsx"
COMPARACAO_INVALIDA = "Escolha de 2 a 5 CNPJs diferentes, cada um com 14 caracteres."
COMPARACAO_INDISPONIVEL = "Comparação não disponível."
BASE_FORA_DO_AR = "A base não está disponível agora. Tente de novo em alguns minutos."

Conta = Annotated[Usuario, Depends(conta_com_acesso)]
router = APIRouter(prefix="/v1/analista", dependencies=[Depends(exigir_api_ligada)])


class PedidoDaFichaV1(BaseModel):
    cnpj: str  # sem limite aqui: o 422 do FastAPI repetiria o texto pedido (o limite fica na rota)


class PedidoDaBuscaV1(BaseModel):
    setores: list[str] = Field(default_factory=list, max_length=busca.SETORES_MAXIMOS)
    ufs: list[str] = Field(default_factory=list, max_length=len(busca.UFS))
    idade_minima: int | None = Field(None, ge=1, le=busca.IDADE_MAXIMA)
    cursor: str | None = Field(None, max_length=TAMANHO_MAXIMO_DO_CURSOR)

    def filtros(self) -> busca.Filtros:
        return busca.Filtros(
            setores=tuple(self.setores),
            ufs=tuple(self.ufs),
            idade_minima=self.idade_minima,
            cursor=self.cursor,
        )


class PedidoDaComparacaoV1(BaseModel):
    # sem limite aqui: o 422 do FastAPI repetiria o texto pedido (os limites ficam na rota)
    cnpjs: list[str]


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
            except KeyError as erro:
                # o portão libera uma tabela que a base deste servidor não tem (a porta diz qual e onde):
                # para quem usa, é a base fora do ar; o nome e o caminho ficam só no log do servidor
                log.warning("tela do analista: tabela fora desta base: %s", erro)
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
    return esquemas.de_ficha_do_analista(_ficha_do_pedido(pedido), leitura.LIMITES)


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


def _busca_do_pedido(
    pedido: PedidoDaBuscaV1, *, para_planilha: bool
) -> leitura.Resposta:
    filtros = pedido.filtros()
    # o formulário abre com este pedido: as opções saem sem abrir a base
    if filtros.vazio():
        return leitura.Resposta(busca.SEM_FILTRO)
    ler = busca.para_planilha if para_planilha else busca.buscar
    with _porta() as porta:
        try:
            resposta = ler(
                porta, filtros, hoje=hoje(), regras=rotas_da_api_externa.regras_da_api()
            )
        except busca.FiltroInvalido as erro:
            raise HTTPException(status_code=422, detail=FILTRO_INVALIDO) from erro
    log.info("busca do analista: %s", resposta.estado)  # só o estado, nunca o que achou
    return resposta


@router.post("/empresas")
def encontrar_empresas(
    _conta: Conta, pedido: PedidoDaBuscaV1
) -> esquemas.BuscaDeEmpresasV1:
    """Uma página de empresas (a matriz ativa) por setor, UF e idade mínima, cada campo com a fonte e o dia
    em que ficou público, e as opções do formulário. Sem filtro sai `sem_filtro`, sem ler a base; o que o
    portão ainda não libera sai `nao_liberada`."""
    return esquemas.de_busca_do_analista(_busca_do_pedido(pedido, para_planilha=False))


@router.post("/empresas/planilha", response_class=Response)
def encontrar_empresas_em_planilha(_conta: Conta, pedido: PedidoDaBuscaV1) -> Response:
    """A mesma busca em Excel (mesmo acesso, mesmo plano): até dez páginas, com os nomes ao lado dos códigos,
    a aba das fontes e o aviso."""
    resposta = _busca_do_pedido(pedido, para_planilha=True)
    if resposta.corpo is None:
        raise HTTPException(status_code=404, detail=BUSCA_INDISPONIVEL)
    corpo = resposta.corpo | {"fontes": resposta.fontes}
    return Response(
        content=planilha.xlsx(corpo),
        media_type=TIPO_DA_PLANILHA,
        headers={
            "Content-Disposition": f'attachment; filename="{NOME_DA_PLANILHA_DA_BUSCA}"',
            "Cache-Control": "no-store",
        },
    )


def _comparacao_do_pedido(pedido: PedidoDaComparacaoV1) -> leitura.Resposta:
    cnpjs = pedido.cnpjs
    if len(cnpjs) > comparacao.MAXIMO or any(
        len(cnpj) > TAMANHO_MAXIMO_DO_CNPJ for cnpj in cnpjs
    ):
        raise HTTPException(status_code=422, detail=COMPARACAO_INVALIDA)
    with _porta() as porta:
        try:
            resposta = comparacao.comparar(
                porta, cnpjs, hoje=hoje(), regras=rotas_da_api_externa.regras_da_api()
            )
        except (
            comparacao.PedidoInvalido
        ) as erro:  # só o pedido; erro da base não vira 422
            raise HTTPException(status_code=422, detail=COMPARACAO_INVALIDA) from erro
    log.info("comparação do analista: %s", resposta.estado)  # só o estado, nunca o CNPJ
    return resposta


@router.post("/comparar")
def comparar_empresas(
    _conta: Conta, pedido: PedidoDaComparacaoV1
) -> esquemas.ComparacaoDeEmpresasV1:
    """De dois a cinco CNPJs lado a lado: o cadastro na Receita, o porte, a abertura, a atividade, o lugar, o
    capital, os estabelecimentos e, da companhia aberta, a última entrega à CVM e os atrasos, cada campo com
    a fonte e o dia. Pessoa (MEI, empresário individual) e CNPJ que a base não conhece saem `nao_disponivel`,
    sem dizer o motivo; o que o portão ainda não libera sai `nao_liberada`."""
    return esquemas.de_comparacao_do_analista(
        _comparacao_do_pedido(pedido), comparacao.LIMITES
    )


@router.post("/comparar/planilha", response_class=Response)
def comparar_empresas_em_planilha(
    _conta: Conta, pedido: PedidoDaComparacaoV1
) -> Response:
    """A mesma comparação em Excel (mesmo acesso, mesmo plano), uma linha por empresa, com a aba das fontes
    e o aviso."""
    resposta = _comparacao_do_pedido(pedido)
    if resposta.corpo is None:
        raise HTTPException(status_code=404, detail=COMPARACAO_INDISPONIVEL)
    corpo = resposta.corpo | {"fontes": resposta.fontes}
    return Response(
        content=planilha.xlsx(corpo),
        media_type=TIPO_DA_PLANILHA,
        headers={
            "Content-Disposition": f'attachment; filename="{NOME_DA_PLANILHA_DA_COMPARACAO}"',
            "Cache-Control": "no-store",
        },
    )
