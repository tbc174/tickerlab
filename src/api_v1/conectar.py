"""A rota da página "Conectar" (linha 832): como ligar o TickerLab ao Claude, ao ChatGPT e à CLI.

Livre para toda conta logada. Só repete o texto de `src/conectar.py`: nada do banco e nenhuma chave (a
chave que aparece é o exemplo `tld_...`).
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src import conectar
from src.api_v1.acesso import conta_com_acesso, exigir_api_ligada
from src.api_v1.esquemas import ConectarV1
from src.banco.usuarios import Usuario

Conta = Annotated[Usuario, Depends(conta_com_acesso)]
router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])


@router.get("/conectar")
def como_conectar(_conta: Conta) -> ConectarV1:
    """O endereço do conector, os passos, os comandos da CLI e as perguntas prontas."""
    return ConectarV1.model_validate(conectar.como_dicionario())
