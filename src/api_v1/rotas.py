"""As rotas da API de leitura (v1). Todas exigem a API ligada e uma conta logada (src/api_v1/acesso.py)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api_v1.acesso import conta_logada, exigir_api_ligada
from src.banco.usuarios import Usuario
from src.planos import limites_do

router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])

Conta = Annotated[Usuario, Depends(conta_logada)]


class LimitesV1(BaseModel):
    simulacoes: int | None  # null = sem limite
    favoritos: int
    ativos_na_carteira: int
    relatorios_por_dia: int | None
    recursos: list[str]


class EuV1(BaseModel):
    """Quem está logado: só o necessário para a tela (sem e-mail)."""

    nome: str | None
    plano: str
    administrador: bool
    limites: LimitesV1


@router.get("/eu")
def eu(conta: Conta) -> EuV1:
    limites = limites_do(conta.plano)
    return EuV1(
        nome=conta.nome,
        plano=conta.plano,
        administrador=conta.e_admin,
        limites=LimitesV1(
            simulacoes=limites.simulacoes,
            favoritos=limites.favoritos,
            ativos_na_carteira=limites.ativos_na_carteira,
            relatorios_por_dia=limites.relatorios_por_dia,
            recursos=sorted(limites.recursos),
        ),
    )
