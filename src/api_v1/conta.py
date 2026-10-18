"""A conta nova pelo app novo (ADR 0062, tela 2): o primeiro login sem passar pelo Streamlit.

`POST /v1/conta` recebe o mesmo token do Google das outras rotas e chama a mesma função do Streamlit
(`src/autenticacao.registrar_login`): cria a conta na primeira vez ou só registra o acesso, dá o papel
de administrador só ao e-mail da lista que o Google confirmou e guarda a origem do cadastro (cookie
`tl_origem`) só no primeiro login.

Depois do login, `POST /v1/conta` abre a sessão de 30 dias e põe o cookie (src/api_v1/sessao.py);
`POST /v1/sair` encerra a sessão e apaga o cookie.

`POST /v1/aceite-dos-termos` grava o aceite dos termos atuais (a mesma `registrar_aceite` do
Streamlit), conferindo que a tela mostrou a versão atual.

Fora do `rotas.py` de propósito: as rotas de lá exigem uma conta que já existe e os termos aceitos;
estas são justamente as que criam a conta e registram o aceite. Sem o aceite, nenhuma página abre.
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from src.api_v1.acesso import (
    LIMITE,
    agora,
    conta_sem_o_aceite,
    exigir_api_ligada,
    identidade_logada,
    recusar_pedido_de_fora,
)
from src.api_v1.rotas import EuV1, eu_da_conta
from src.api_v1.sessao import por_o_cookie, tirar_o_cookie, token_do_cookie
from src.autenticacao import (
    IdentidadeDoGoogle,
    LoginInvalidoError,
    emails_de_admin,
    registrar_login,
)
from src.banco import sessoes
from src.banco.conexao import obter_engine
from src.banco.usuarios import Usuario, buscar_por_id
from src.conformidade import VERSAO_DOS_TERMOS, aceitar_os_termos
from src.envio_novidades import VERSAO_DO_CONSENTIMENTO as VERSAO_DAS_NOVIDADES
from src.origem import NOME_DO_COOKIE, ler_origem

router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])


class ContaV1(EuV1):
    primeira_vez: bool  # True: a conta acabou de ser criada


class AceiteV1(BaseModel):
    """A versão dos termos que a tela mostrou (uma aba velha não aceita os termos novos)."""

    versao: str = Field(max_length=40)
    # a caixa opcional das Novidades por e-mail (desmarcada por padrão) e a versão do texto dela
    novidades: bool = False
    versao_das_novidades: str | None = Field(None, max_length=40)


@router.post("/conta")
def entrar(
    request: Request,
    response: Response,
    identidade: Annotated[IdentidadeDoGoogle, Depends(identidade_logada)],
    tl_origem: Annotated[str | None, Cookie(alias=NOME_DO_COOKIE)] = None,
) -> ContaV1:
    """Cria a conta de quem o token prova ser (ou só registra o acesso) e abre a sessão."""
    # a conta ainda pode não existir: o limite fica pelo identificador do Google
    if not LIMITE.permitir(f"google:{identidade.sub}", agora()):
        raise HTTPException(status_code=429, detail="Muitos pedidos: espere um minuto.")
    try:
        usuario, primeira_vez = _registrar(identidade, tl_origem)
    except LoginInvalidoError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    _abrir_a_sessao(request, response, usuario)
    return ContaV1(**eu_da_conta(usuario).model_dump(), primeira_vez=primeira_vez)


def _registrar(
    identidade: IdentidadeDoGoogle, cookie: str | None
) -> tuple[Usuario, bool]:
    """`registrar_login`; se outra aba criou a mesma conta no mesmo instante, a chave única do
    banco recusa a segunda gravação, e a segunda tentativa só entra na conta que já existe."""
    admins, origem = emails_de_admin(), ler_origem(cookie)
    try:
        return registrar_login(identidade, admins=admins, origem=origem)
    except IntegrityError:
        return registrar_login(identidade, admins=admins, origem=origem)


def _abrir_a_sessao(request: Request, response: Response, usuario: Usuario) -> None:
    """Abre a sessão nova e põe o cookie; a sessão que o navegador ainda tinha é encerrada."""
    antiga = token_do_cookie(request)
    with obter_engine().begin() as conexao:
        if antiga:
            sessoes.encerrar(conexao, antiga)
        token = sessoes.abrir(conexao, usuario.id, "google")
    por_o_cookie(response, token)


@router.post("/sair", status_code=204)
def sair(request: Request, response: Response) -> None:
    """Encerra a sessão do cookie (neste aparelho) e apaga o cookie. Sem sessão, não é erro."""
    recusar_pedido_de_fora(request)
    token = token_do_cookie(request)
    if token:
        with obter_engine().begin() as conexao:
            sessoes.encerrar(conexao, token)
    tirar_o_cookie(response)


@router.post("/aceite-dos-termos")
def registrar_o_aceite(
    conta: Annotated[Usuario, Depends(conta_sem_o_aceite)], aceite: AceiteV1
) -> EuV1:
    """Grava o aceite dos termos atuais para a conta do token (como o botão do Streamlit)."""
    if aceite.versao != VERSAO_DOS_TERMOS:
        raise HTTPException(
            status_code=409,
            detail="Os termos mudaram enquanto a página estava aberta. "
            "Recarregue a página e leia a versão nova.",
        )
    if aceite.novidades and aceite.versao_das_novidades != VERSAO_DAS_NOVIDADES:
        raise HTTPException(
            status_code=409,
            detail="O texto das Novidades mudou enquanto a página estava aberta. "
            "Recarregue a página e confirme de novo.",
        )
    with obter_engine().begin() as conexao:
        aceitar_os_termos(conexao, conta.id, aceite.novidades)
        atualizada = buscar_por_id(conexao, conta.id)
    return eu_da_conta(atualizada or conta)
