"""Os press-releases de resultado no índice do IPE da CVM (vitrine, ideia 2; plano de 17/10/2026).

O IPE lista tudo o que as companhias entregam à CVM. Um press-release de resultado é a linha da
categoria "Dados Econômico-Financeiros" com tipo "Press-release". A regra de classificação é a de
`src.eventos.classificar`; aqui só se separa o press-release das demonstrações completas que caem
no mesmo tema. Nada é lido do documento: este módulo só acha o release e o liga ao trimestre.
"""

import pandas as pd

from src import eventos
from src.eventos import identificador

COLUNAS = (
    "cnpj", "codigo_cvm", "periodo", "referencia", "data_entrega", "protocolo", "versao", "link",
)  # fmt: skip
MESES_POR_TRIMESTRE = 3
TIPO_DO_RELEASE = "press-release"


def periodo_do_trimestre(referencia: object) -> str:
    """O trimestre da data de referência: 2025-09-30 → "3T25" (o 4T é também o fim do ano)."""
    dia = pd.Timestamp(referencia)  # type: ignore[arg-type]
    trimestre = (dia.month - 1) // MESES_POR_TRIMESTRE + 1
    return f"{trimestre}T{dia.year % 100:02d}"


def _e_press_release(categoria: str, tipo: str) -> bool:
    classe = eventos.classificar(categoria, tipo)
    return (
        classe is not None
        and classe.tema == "resultados"
        and TIPO_DO_RELEASE in eventos._sem_acento(tipo)
    )


def releases_de_resultado(ipe: pd.DataFrame, ate: object = None) -> pd.DataFrame:
    """Os press-releases de resultado de um IPE bruto (colunas da CVM), um por entrega.

    Fica a versão mais nova de cada entrega que já tinha sido entregue em `ate` (um release
    reapresentado depois não existia na data; `None` = sem corte). Sem link ou sem data de
    entrega, a linha não entra: não há o que conferir depois.
    """
    vazio = pd.DataFrame(columns=list(COLUNAS))
    if ipe.empty:
        return vazio
    e_release = [
        _e_press_release(c, t)
        for c, t in zip(ipe["Categoria"], ipe["Tipo"], strict=True)
    ]
    linhas = ipe[e_release]
    entregas = pd.to_datetime(linhas["Data_Entrega"], errors="coerce")
    referencias = pd.to_datetime(linhas["Data_Referencia"], errors="coerce")
    validas = entregas.notna() & referencias.notna() & linhas["Link_Download"].ne("")
    if ate is not None:
        validas &= entregas <= pd.Timestamp(ate)  # type: ignore[arg-type]
    linhas, entregas, referencias = (
        linhas[validas],
        entregas[validas],
        referencias[validas],
    )
    registros = []
    for linha, entrega, referencia in zip(
        linhas.itertuples(index=False), entregas, referencias, strict=True
    ):
        chave = identificador(
            linha.Protocolo_Entrega, linha.Versao, linha.Link_Download
        )
        if chave is None:
            continue
        registros.append(
            (linha.CNPJ_Companhia.strip(), linha.Codigo_CVM, periodo_do_trimestre(referencia),
             referencia, entrega, chave[0], chave[1], linha.Link_Download.strip())
        )  # fmt: skip
    if not registros:
        return vazio
    tabela = pd.DataFrame(registros, columns=list(COLUNAS))
    tabela = tabela.sort_values(["protocolo", "versao"]).drop_duplicates(
        "protocolo", keep="last"
    )
    return tabela.sort_values("data_entrega", ascending=False).reset_index(drop=True)
