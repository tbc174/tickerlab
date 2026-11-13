"""As rotas da tela do analista (linha 798): a ficha de uma empresa e a busca de empresas, com login e plano.

`POST /v1/analista/ficha` devolve a ficha do CNPJ pedido (cadastro na Receita e, da companhia aberta, as
entregas à CVM), e `POST /v1/analista/ficha/planilha` a mesma ficha em Excel. As duas pedem a conta logada,
os termos aceitos e o plano da página `ficha_da_empresa` (`src/paginas.py`, recurso Dossiê da base).
`POST /v1/analista/empresas` busca empresas por setor, UF, idade mínima, capital social e estabelecimentos
ativos, com a ordem por um deles (página `encontrar_empresas`, o mesmo recurso), e `POST /v1/analista/empresas/planilha` leva a busca para o Excel.
`POST /v1/analista/comparar` põe de dois a cinco CNPJs lado a lado (página `comparar_empresas`, o mesmo
recurso), e `POST /v1/analista/comparar/planilha` leva a comparação para o Excel.

Nada aqui lê a base por outro caminho: a porta e as regras do portão são as da API externa
(`src/api_externa/rotas.py`, `abrir_porta` e `regras_da_api`), e a leitura é a do leitor da API
(`src/analista/leitura.py`). Assim a tela mostra só o que a API mostraria.

A busca de empresas vale também pela prontidão de piloto (D11): para a conta que é membro de uma organização
com a marca de piloto vigente (`membros.e_do_piloto`, conferido aqui, no servidor, a cada pedido), e a
resposta e a planilha levam o aviso de piloto. Para as outras contas nada muda: `nao_liberada`.

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
from src.analista import busca, comparacao, eventos, leitura, planilha, setor, vinculos
from src.api_externa import rotas as rotas_da_api_externa
from src.api_v1 import esquemas
from src.api_v1.acesso import conta_com_acesso, exigir_api_ligada
from src.banco import membros_da_organizacao as membros
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
# o cursor ordenado (coluna, valor e CNPJ em JSON) passa de 70 caracteres
TAMANHO_MAXIMO_DO_CURSOR = 256
TAMANHO_MAXIMO_DA_ORDEM = (
    32  # a ordem fora da lista o leitor recusa (422) sem repetir o texto
)
BUSCA_INDISPONIVEL = "Busca não disponível: escolha um filtro e tente de novo."
FILTRO_INVALIDO = "Filtro fora do que a tela oferece."
TIPO_DA_PLANILHA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TAMANHO_MAXIMO_DO_CNPJ = 32  # com pontuação e espaços; o resto é erro de quem chama
CNPJ_INVALIDO = "CNPJ inválido: confira os 14 caracteres."
FICHA_INDISPONIVEL = "Ficha não disponível."
CURSOR_INVALIDO = "Cursor inválido: peça a primeira página de novo."
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
    capital_minimo: float | None = Field(None, ge=0, le=busca.CAPITAL_MAXIMO)
    capital_maximo: float | None = Field(None, ge=0, le=busca.CAPITAL_MAXIMO)
    estabelecimentos_minimo: int | None = Field(
        None, ge=1, le=busca.ESTABELECIMENTOS_MAXIMOS
    )
    ordem: str | None = Field(None, max_length=TAMANHO_MAXIMO_DA_ORDEM)
    cursor: str | None = Field(None, max_length=TAMANHO_MAXIMO_DO_CURSOR)

    def filtros(self) -> busca.Filtros:
        return busca.Filtros(
            setores=tuple(self.setores),
            ufs=tuple(self.ufs),
            idade_minima=self.idade_minima,
            capital_minimo=self.capital_minimo,
            capital_maximo=self.capital_maximo,
            estabelecimentos_minimo=self.estabelecimentos_minimo,
            ordem=self.ordem,
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


class PedidoDosEventosV1(BaseModel):
    cnpj: str  # sem limite aqui: o 422 do FastAPI repetiria o texto pedido (os limites ficam na rota)
    cursor: str | None = None


@router.post("/ficha/eventos")
def eventos_da_empresa(
    _conta: Conta, pedido: PedidoDosEventosV1
) -> esquemas.EventosDaEmpresaV1:
    """Os documentos à CVM e as trocas de auditor da empresa, do mais novo ao mais velho, por página. Mesmo
    acesso, mesmo plano e mesmos estados da ficha; `proximo_cursor` abre a página seguinte."""
    if len(pedido.cnpj) > TAMANHO_MAXIMO_DO_CNPJ:
        raise HTTPException(status_code=422, detail=CNPJ_INVALIDO)
    if (
        pedido.cursor is not None
        and len(pedido.cursor) > eventos.TAMANHO_MAXIMO_DO_CURSOR
    ):
        raise HTTPException(status_code=422, detail=CURSOR_INVALIDO)
    with _porta() as porta:
        try:
            resposta = eventos.eventos(
                porta,
                pedido.cnpj,
                hoje=hoje(),
                cursor=pedido.cursor,
                regras=rotas_da_api_externa.regras_da_api(),
            )
        except ValueError as erro:  # inclui eventos.PedidoInvalido
            detalhe = (
                CURSOR_INVALIDO
                if isinstance(erro, eventos.PedidoInvalido)
                else CNPJ_INVALIDO
            )
            raise HTTPException(status_code=422, detail=detalhe) from erro
    log.info("eventos do analista: %s", resposta.estado)  # só o estado, nunca o CNPJ
    return esquemas.de_eventos_do_analista(resposta, eventos.LIMITES)


@router.post("/ficha/vinculos")
def vinculos_da_empresa(
    _conta: Conta, pedido: PedidoDaFichaV1
) -> esquemas.VinculosDaEmpresaV1:
    """Controle, coligação, participação e auditoria da empresa, a um salto, cada campo com fonte e dia. Mesmo
    acesso, mesmo plano e mesmos estados da ficha; pessoa natural nunca sai."""
    if len(pedido.cnpj) > TAMANHO_MAXIMO_DO_CNPJ:
        raise HTTPException(status_code=422, detail=CNPJ_INVALIDO)
    with _porta() as porta:
        try:
            resposta = vinculos.vinculos(
                porta,
                pedido.cnpj,
                hoje=hoje(),
                regras=rotas_da_api_externa.regras_da_api(),
            )
        except ValueError as erro:
            raise HTTPException(status_code=422, detail=CNPJ_INVALIDO) from erro
    log.info("vínculos do analista: %s", resposta.estado)  # só o estado, nunca o CNPJ
    return esquemas.de_vinculos_do_analista(resposta, vinculos.LIMITES)


def _e_do_piloto(conta: Usuario, dia: date) -> bool:
    """A conta é membro de uma organização com a marca de piloto no dia? Conferido no servidor, a cada pedido."""
    with obter_engine().connect() as banco:
        return membros.e_do_piloto(banco, conta.id, dia)


def _busca_do_pedido(
    conta: Usuario, pedido: PedidoDaBuscaV1, *, para_planilha: bool
) -> leitura.Resposta:
    filtros = pedido.filtros()
    # o formulário abre com este pedido: as opções saem sem abrir a base
    if filtros.vazio():
        return leitura.Resposta(busca.SEM_FILTRO)
    ler = busca.para_planilha if para_planilha else busca.buscar
    dia = hoje()
    piloto = _e_do_piloto(conta, dia)
    with _porta() as porta:
        try:
            resposta = ler(
                porta,
                filtros,
                hoje=dia,
                regras=rotas_da_api_externa.regras_da_api(),
                piloto=piloto,
            )
        except busca.FiltroInvalido as erro:
            raise HTTPException(status_code=422, detail=FILTRO_INVALIDO) from erro
    log.info("busca do analista: %s", resposta.estado)  # só o estado, nunca o que achou
    return resposta


@router.post("/empresas")
def encontrar_empresas(
    conta: Conta, pedido: PedidoDaBuscaV1
) -> esquemas.BuscaDeEmpresasV1:
    """Uma página de empresas (a matriz ativa) pelos filtros da tela, cada campo com a fonte e o dia
    em que ficou público, e as opções do formulário. Sem filtro sai `sem_filtro`, sem ler a base; o que o
    portão ainda não libera sai `nao_liberada`. O que sai pela prontidão de piloto, só para a conta de
    organização com a marca, vem com `aviso_de_piloto`."""
    return esquemas.de_busca_do_analista(
        _busca_do_pedido(conta, pedido, para_planilha=False)
    )


@router.post("/empresas/planilha", response_class=Response)
def encontrar_empresas_em_planilha(conta: Conta, pedido: PedidoDaBuscaV1) -> Response:
    """A mesma busca em Excel (mesmo acesso, mesmo plano): até dez páginas, com os nomes ao lado dos códigos,
    a aba das fontes e o aviso; dado de piloto leva o aviso de piloto em cada linha e nas fontes."""
    resposta = _busca_do_pedido(conta, pedido, para_planilha=True)
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


SETOR_INVALIDO = (
    "Setor inválido: use o CNAE com 5 ou 7 dígitos, a UF com 2 letras e de 1 a 10 anos."
)
TAMANHO_MAXIMO_DO_CNAE = 16  # com pontuação e espaços; o resto é erro de quem chama


class PedidoDoSetorV1(BaseModel):
    # sem limite aqui: o 422 do FastAPI repetiria o texto pedido (os limites ficam na rota)
    cnae: str
    uf: str | None = None
    anos: int | None = None


@router.post("/setor/compradores")
def compradores_do_setor(
    _conta: Conta, pedido: PedidoDoSetorV1
) -> esquemas.CompradoresDoSetorV1:
    """Quem já se mexeu num setor (só pessoa jurídica): as empresas que entraram como sócias de uma empresa
    ativa do CNAE, os FIPs sócios e as companhias abertas com controlada no setor, cada campo com fonte e dia.
    Mesmo leitor e mesmo portão da API externa, sem o contrato da organização; movimento passado, não intenção
    de compra. O sinal que o portão não libera vem em `sinais_nao_disponiveis`."""
    if len(pedido.cnae) > TAMANHO_MAXIMO_DO_CNAE or len(pedido.uf or "") > 2:
        raise HTTPException(status_code=422, detail=SETOR_INVALIDO)
    with _porta() as porta:
        try:
            resposta = setor.compradores(
                porta,
                pedido.cnae,
                pedido.uf,
                pedido.anos,
                hoje=hoje(),
                regras=rotas_da_api_externa.regras_da_api(),
            )
        except ValueError as erro:  # PedidoInvalido é um ValueError
            raise HTTPException(status_code=422, detail=SETOR_INVALIDO) from erro
    log.info(
        "setor do analista: %s", resposta.estado
    )  # só o estado, nunca o setor pedido
    return esquemas.de_compradores_do_analista(resposta, ())
