"""Carga do CNES por competência para a base: estabelecimentos de saúde e a situação de cada competência (linha 654).

    python -m scripts.carga_cnes --competencia 202607                 (grava no acervo)
    python -m scripts.carga_cnes --competencia 202607 --competencia 202608 --pasta /tmp/base --forcar
    python -m scripts.carga_cnes                                      (as competências dos últimos meses)

Lê o FTP do DATASUS em DBC (padrão, `--fonte ftp`: 27 UFs, layout conferido no STAC2608.dbc real) ou a API de dados
abertos (`--fonte api`) por `base/cnes.py` e grava, com manifesto e versões
(`base/parquet.py::gravar_com_versoes`), um arquivo por competência:
- `cnes_estabelecimentos/<AAAAMM>.parquet`: um estabelecimento por linha, com o CNPJ dele e o da mantenedora
  em colunas separadas; competência vazia não grava estabelecimentos;
- `cnes_competencias/<AAAAMM>.parquet`: uma linha dizendo que a competência foi olhada e se veio `vazia` ou
  `com_dados`. Vazia nunca significa "sem estabelecimentos": a fonte ainda não publicou.
Endereço, telefone e e-mail da fonte nunca entram; estabelecimento sem nenhum CNPJ fica sem nome.

Ritmo mensal: o app não depende dela; o servidor de casa roda uma vez por mês. Licença a confirmar, só uso
interno (ADR 0102, Emenda 2); nada é perguntado à fonte. Recusa rodar sem a versão do código (exigência 13 da
ADR 0055). Saída 0 tudo certo; 1 se alguma competência falhou.
"""

import argparse
import hashlib
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from base import cnes
from base.parquet import IGUAL, gravar_com_versoes, ler_tabela
from src import acervo, rede
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_cnes")
TEMPO_LIMITE = 120
COMPETENCIAS_PADRAO = (
    3  # a mais recente com dado costuma ficar 1 a 3 meses atrás da data
)
FONTE_API = "api"
FONTE_FTP = "ftp"
ORDEM_DOS_ESTABELECIMENTOS = list(cnes.CHAVE)
ORDEM_DA_SITUACAO = ["competencia"]


def buscar_na_api(competencia: int, offset: int, limit: int) -> dict[str, Any]:
    """Uma página da API do DATASUS (o `Buscador` de `base/cnes.py`)."""
    resposta = rede.get_com_agente(
        cnes.URL_DA_API,
        params={"nu_comp": competencia, "offset": offset, "limit": limit},
        timeout=TEMPO_LIMITE,
    )
    resposta.raise_for_status()
    return resposta.json()


def competencias_recentes(hoje: date, quantas: int = COMPETENCIAS_PADRAO) -> list[int]:
    """As `quantas` competências (AAAAMM) mais recentes até o mês de `hoje`, da mais antiga à mais nova."""
    meses = [hoje.year * 12 + hoje.month - 1 - passo for passo in range(quantas)]
    return sorted((m // 12) * 100 + m % 12 + 1 for m in reversed(meses))


def _origem(competencia: int, fonte: str = FONTE_API) -> dict[str, str]:
    """A origem de uma competência. Nem a API nem o FTP (27 arquivos) dão um conteúdo bruto único: o resumo é
    do pedido, e a tabela (que muda quando o dado muda) é comparada pelo conteúdo em `_gravar`."""
    if fonte == FONTE_FTP:
        pedido = f"ftp://{cnes.SERVIDOR_FTP}{cnes.PASTA_NO_FTP}/ST*{competencia % 10000:04d}.dbc"
    else:
        pedido = f"{cnes.URL_DA_API}?nu_comp={competencia}"
    return {"url": pedido, "sha256": hashlib.sha256(pedido.encode()).hexdigest()}


def carregar_competencia(
    competencia: int,
    saida: Path,
    coletado_em: date,
    buscar: cnes.Buscador = buscar_na_api,
    forcar: bool = False,
    fonte: str = FONTE_API,
    baixar: cnes.BaixadorDeDbc = cnes.baixar_dbc_se_publicado,
) -> tuple[str, str]:
    """Coleta e grava uma competência; devolve o que aconteceu com os estabelecimentos e com a situação."""
    if fonte == FONTE_FTP:
        tabela, situacao = cnes.coletar_competencia_ftp(
            competencia, coletado_em, baixar
        )
    else:
        tabela, situacao = cnes.coletar_competencia(buscar, competencia, coletado_em)
    log.info(
        "CNES %s: %s (%d estabelecimentos)",
        competencia,
        situacao["situacao"],
        len(tabela),
    )
    registro = pd.DataFrame([situacao], columns=list(cnes.COLUNAS_DA_SITUACAO))
    estabelecimentos = _gravar(
        tabela, saida / "cnes_estabelecimentos" / str(competencia), competencia,
        ORDEM_DOS_ESTABELECIMENTOS, ("disponivel_em",), forcar, fonte,
    )  # fmt: skip
    situacao_gravada = _gravar(
        registro, saida / "cnes_competencias" / str(competencia), competencia,
        ORDEM_DA_SITUACAO, ("coletado_em",), forcar, fonte,
    )  # fmt: skip
    return estabelecimentos, situacao_gravada


def _gravar(
    tabela: pd.DataFrame,
    destino: Path,
    competencia: int,
    ordem: list[str],
    carimbos: tuple[str, ...],
    forcar: bool,
    fonte: str = FONTE_API,
) -> str:
    """Grava a competência só se o conteúdo mudou, sem contar a data da coleta.

    A data da coleta (`disponivel_em`, `coletado_em`) é o dia em que o dado foi visto pela primeira vez:
    olhar de novo a mesma competência não pode empurrá-la para frente (sem olhar o futuro). Competência que
    estava `vazia` e agora tem dados muda o conteúdo, e aí a coleta nova vale.
    """
    arquivo = destino.with_suffix(".parquet")
    if arquivo.exists() and not forcar:
        anterior = ler_tabela(arquivo).drop(columns=list(carimbos))
        igual = anterior.reset_index(drop=True).equals(
            tabela.drop(columns=list(carimbos)).reset_index(drop=True)
        )
        if igual:
            return IGUAL
    return gravar_com_versoes(
        lambda: tabela, destino, [_origem(competencia, fonte)], ordem, forcar=True
    )


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--competencia", type=int, action="append", default=None)
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--forcar", action="store_true")
    argumentos.add_argument(
        "--fonte",
        choices=(FONTE_FTP, FONTE_API),
        default=FONTE_FTP,
        help="ftp (DBC por UF, ~2 competências à frente, sem nomes) ou api (JSON, com nomes)",
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    competencias = opcoes.competencia or competencias_recentes(hoje)
    saida = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    falhas = 0
    for competencia in competencias:
        try:
            resultado = carregar_competencia(
                competencia, saida, hoje, forcar=opcoes.forcar, fonte=opcoes.fonte
            )
        except (TypeError, ValueError, OSError) as erro:
            log.error("CNES %s falhou: %s", competencia, erro)
            falhas += 1
            continue
        log.info("CNES %s: %s", competencia, json.dumps(resultado))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
