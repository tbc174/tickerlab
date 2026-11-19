"""Monta `anvisa_por_empresa` (linha 860): os registros da Anvisa contados por raiz de CNPJ e por tipo, só pessoa jurídica.

    python -m scripts.montar_anvisa_por_empresa                      (lê e grava em <TICKERLAB_ACERVO>/base)
    python -m scripts.montar_anvisa_por_empresa --pasta /tmp/base    (outra pasta, de leitura e de saída)

Lê `anvisa_registros` **pela porta da base** (a mesma que serve a API; a pasta de medicamentos guardada por
versão não entra) e grava `<pasta>/anvisa_por_empresa/anvisa_por_empresa.parquet`, um retrato por dia de arquivo
da Anvisa (`base/anvisa_porte.py`: as regras, o que é "ativo" em cada tipo e a prova de zero pessoa). Não baixa
nada e não toca nas outras tabelas. Remontar sem retrato novo não regrava nada. O resumo no log diz as linhas
lidas, as raízes e os retratos de saída e quantas linhas ficaram sem situação classificada. Saída 0 tudo certo;
1 sem `anvisa_registros` na pasta ou nada para contar.

Roda: manual (python -m scripts.montar_anvisa_por_empresa), no servidor de casa, depois de cada retrato novo do
arquivista (`scripts/carga_licencas.py`); coberto por test_anvisa_porte.py; citado em dicionario.py.
"""

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from base import anvisa_porte as porte
from base import porta
from base.parquet import gravar_se_mudou
from src import acervo
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.montar_anvisa_por_empresa")

CARIMBOS = ("montado_em", "versao_do_codigo")


def _origens(pasta: Path) -> list[dict[str, str]]:
    """Os manifestos de `anvisa_registros` que a tabela leu: o SHA-256 de cada cadastro (a linhagem da saída)."""
    achados = []
    for manifesto in sorted((pasta / porte.CADASTRO_DA_TABELA).glob("*.json")):
        if ".v" in manifesto.stem:  # a versão guardada de uma tabela não é entrada
            continue
        sha = json.loads(manifesto.read_text(encoding="utf-8")).get("sha256_da_tabela")
        if sha:
            achados.append(
                {
                    "url": f"{porte.CADASTRO_DA_TABELA}/{manifesto.stem}",
                    "sha256": sha,
                }
            )
    return achados


def montar(pasta: Path, agora: datetime, versao_do_codigo: str) -> dict[str, object]:
    """Lê `anvisa_registros` da `pasta`, grava a tabela e devolve o resumo (vazio se não há o que contar)."""
    with porta.abrir(pasta) as p:
        registros = p.ler(
            porte.CADASTRO_DA_TABELA, colunas=list(porte.COLUNAS_DE_ENTRADA)
        )
    if registros.empty:
        return {}
    tabela = porte.com_carimbo(porte.contar(registros), agora, versao_do_codigo)
    if tabela.empty:
        return {}
    destino = pasta / porte.TABELA / porte.TABELA
    destino.parent.mkdir(parents=True, exist_ok=True)
    gravou = gravar_se_mudou(
        tabela,
        destino,
        _origens(pasta),
        ["cnpj_basico", porte.RETRATO],
        carimbos=CARIMBOS,
    )
    return {
        "linhas_lidas": len(registros),
        "linhas_na_tabela": len(tabela),
        "retratos": int(pd.Series(tabela[porte.RETRATO]).nunique()),
        "gravou": gravou,  # gravado, igual (nada mudou) ou acrescido
        "sem_classificar": porte.situacoes_sem_classificar(registros),
    }


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    versao = exigir_versao_do_codigo()
    log.info("Versão do código: %s", versao)
    if not (pasta / porte.CADASTRO_DA_TABELA).exists():
        log.warning("sem %s em %s", porte.CADASTRO_DA_TABELA, pasta)
        return 1
    resumo = montar(pasta, datetime.now(UTC), versao)
    if not resumo:
        log.warning("nada para contar em %s", porte.CADASTRO_DA_TABELA)
        return 1
    log.info("%s: %s", porte.TABELA, resumo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
