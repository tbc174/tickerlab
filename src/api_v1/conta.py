"""A conta nova pelo app novo (ADR 0062, tela 2): o primeiro login sem passar pelo Streamlit.

`POST /v1/conta` recebe o mesmo token do Google das outras rotas e chama a mesma função do Streamlit
(`src/autenticacao.registrar_login`): cria a conta na primeira vez ou só registra o acesso, dá o papel
de administrador só ao e-mail da lista que o Google confirmou e guarda a origem do cadastro (cookie
`tl_origem`) só no primeiro login.

Fora do `rotas.py` de propósito: as rotas de lá exigem uma conta que já existe (e os termos aceitos);
esta é justamente a que cria a conta. Os termos continuam valendo: a conta nova ainda precisa
aceitá-los antes de abrir qualquer página.
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from src.api_v1.acesso import LIMITE, agora, exigir_api_ligada, identidade_logada
from src.api_v1.rotas import EuV1, eu_da_conta
from src.autenticacao import (
    IdentidadeDoGoogle,
    LoginInvalidoError,
    emails_de_admin,
    registrar_login,
)
from src.banco.usuarios import Usuario
from src.origem import NOME_DO_COOKIE, ler_origem

router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])


class ContaV1(EuV1):
    primeira_vez: bool  # True: a conta acabou de ser criada


@router.post("/conta")
def entrar(
    identidade: Annotated[IdentidadeDoGoogle, Depends(identidade_logada)],
    tl_origem: Annotated[str | None, Cookie(alias=NOME_DO_COOKIE)] = None,
) -> ContaV1:
    """Cria a conta de quem o token prova ser (ou só registra o acesso, se ela já existe)."""
    # a conta ainda pode não existir: o limite fica pelo identificador do Google
    if not LIMITE.permitir(f"google:{identidade.sub}", agora()):
        raise HTTPException(status_code=429, detail="Muitos pedidos: espere um minuto.")
    try:
        usuario, primeira_vez = _registrar(identidade, tl_origem)
    except LoginInvalidoError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
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
