"""Cruza as raízes das tabelas sem marca de pessoa com a `cnpj_empresas_pj` (linha 789).

    python -m scripts.conferir_sem_pessoa

Para cada tabela de `base.sem_pessoa_por_raiz.SEM_PESSOA_PELA_RAIZ` imprime quantas raízes distintas tem e
quantas não estão na `cnpj_empresas_pj`; sai com 1 se alguma tem raiz de fora (pode ser pessoa). Imprime só
contagens, nunca a raiz.

Roda: manual, a cada coleta das tabelas listadas e antes de dar prontidão de piloto a elas.
"""

import sys

from base import porta
from base.sem_pessoa_por_raiz import cruzar_todas


def main() -> int:
    with porta.abrir() as p:
        resultados = cruzar_todas(p)
    for c in resultados:
        estado = "sem pessoa" if c.sem_pessoa else "RAIZ DE FORA"
        print(
            f"{c.tabela}: {c.raizes} raízes, {c.fora_da_pj} fora da cnpj_empresas_pj: {estado}"
        )
    return 0 if all(c.sem_pessoa for c in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
