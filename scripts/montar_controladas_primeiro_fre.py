"""Monta `controladas_primeiro_fre`: o primeiro FRE em que cada controlada aparece (linha 1045).

    python -m scripts.montar_base_historica controladas_primeiro_fre

Lê só `<acervo>/base/controladas/*.parquet` e grava só `<acervo>/base/controladas_primeiro_fre/` (Parquet com
manifesto e versões, sem regravar o que não mudou). A regra está em `base/controladas_primeiro_fre.py`.

Roda: manual no servidor de casa, pelo `scripts/montar_base_historica.py`, depois de `controladas` (a carga pede o
"pode" da Diretoria).
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from base.controladas_primeiro_fre import (
    CHAVE,
    LEITURA,
    TABELA,
    TABELA_DE_ORIGEM,
    primeiro_fre_de_cada_par,
)
from base.parquet import (
    LINHAGEM,
    arquivos_atuais,
    gravar_se_mudou,
    origem_de_tabela,
)
from src.versao_do_codigo import versao_do_codigo


def montar(pasta: Path, agora: datetime) -> int:
    """`<pasta>/controladas_primeiro_fre/controladas_primeiro_fre.parquet`, a partir de `<pasta>/controladas/*.parquet`.

    Devolve quantos pares gravou (0, e nada gravado, sem `controladas`). Não regrava o que não mudou.
    """
    anos = arquivos_atuais(pasta / TABELA_DE_ORIGEM)
    if not anos:
        return 0
    lidas = pd.concat(
        [pd.read_parquet(ano, columns=list(LEITURA)) for ano in anos],
        ignore_index=True,
    )
    resultado = primeiro_fre_de_cada_par(lidas)
    tabela = resultado.tabela.assign(
        montado_em=agora.isoformat(), versao_do_codigo=versao_do_codigo()
    )
    gravar_se_mudou(
        tabela,
        pasta / TABELA / f"{TABELA}.parquet",
        [origem_de_tabela(ano, pasta) for ano in anos],
        list(CHAVE),
        carimbos=LINHAGEM,
    )
    return len(tabela)
