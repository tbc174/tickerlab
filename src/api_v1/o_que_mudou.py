"""A rota da página "O que mudou" (linha 804): o que entrou no app a cada dia, com a página para abrir.

Livre para toda conta logada (a página `o_que_mudou` não tem recurso de plano). Só lê o registro de
`src/o_que_mudou.py`: nada do banco, nada da base.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src import o_que_mudou
from src.api_v1.acesso import conta_com_acesso, exigir_api_ligada
from src.api_v1.esquemas import OQueMudouV1
from src.banco.usuarios import Usuario

Conta = Annotated[Usuario, Depends(conta_com_acesso)]
router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])


@router.get("/o-que-mudou")
def o_que_mudou_no_app(_conta: Conta) -> OQueMudouV1:
    """As entregas visíveis do app, a mais nova primeiro."""
    return OQueMudouV1.model_validate({"entregas": o_que_mudou.como_lista()})
