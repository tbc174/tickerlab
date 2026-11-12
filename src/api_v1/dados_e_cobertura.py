"""A rota da página "Dados e cobertura" (linha 832): o que a base serve de verdade, por tabela.

Livre para toda conta logada. Só repete o catálogo público (`GET /v1/base/tabelas`, sem as colunas):
tabela, o que traz, fonte, licença, histórico e frequência. Nada de cobertura escrita à mão: o que a
base não declara, a tela não mostra.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api_v1.acesso import conta_com_acesso, exigir_api_ligada
from src.api_v1.base_tabelas import tabelas_abertas
from src.api_v1.esquemas import DadosECoberturaV1
from src.banco.usuarios import Usuario

Conta = Annotated[Usuario, Depends(conta_com_acesso)]
router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])


@router.get("/dados-e-cobertura")
def dados_e_cobertura(_conta: Conta) -> DadosECoberturaV1:
    """As tabelas consultáveis da base, na ordem do catálogo, com a fonte e a licença de cada uma."""
    return DadosECoberturaV1.model_validate(
        {
            "tabelas": [
                {**entrada, "n_colunas": len(entrada["colunas"])}  # type: ignore[arg-type]
                for entrada in tabelas_abertas()
            ]
        }
    )
