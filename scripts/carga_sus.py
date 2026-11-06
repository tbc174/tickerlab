"""Carga dos totais do SUS por estabelecimento e mês para a base: SIH RD e SIA PA (linha 698).

    python -m scripts.carga_sus --sistema sih --competencia 202607          (grava no acervo)
    python -m scripts.carga_sus --sistema sia --competencia 202607 --uf AC --pasta /tmp/base
    python -m scripts.carga_sus --sistema sih                               (as competências recentes)

Lê o FTP do DATASUS por `base/sus.py`, que baixa cada DBC para a memória, soma por estabelecimento,
suprime as células pequenas e descarta o arquivo. Grava, com manifesto e versões
(`base/parquet.py::gravar_com_versoes`), um arquivo por competência:
- `sus_internacoes/<AAAAMM>.parquet` (SIH) ou `sus_ambulatorial/<AAAAMM>.parquet` (SIA): um estabelecimento
  por linha; competência ainda não publicada não grava nada aqui;
- `sus_competencias/<sistema>-<AAAAMM>.parquet`: uma linha por UF, com os arquivos lidos, o sha256 de cada
  um, quantos registros foram somados e quantos estabelecimentos saíram suprimidos ou por pessoa física.
A linha do paciente nunca chega ao disco (ADR 0088 Emenda 1). As origens do manifesto são os arquivos do FTP
com o sha256 de cada um.

`disponivel_em` é o dia em que a competência foi vista pela primeira vez: olhar de novo sem mudança não a
empurra para frente; o reprocesso do DATASUS que muda um número vira versão nova com a data nova.

Ritmo mensal no servidor de casa; o app não depende dela. Licença: ADR 0122 (vendável com atribuição,
`FRASE_DO_DATASUS`), treino barrado. Recusa rodar sem a versão do código (exigência 13 da ADR 0055).
Saída 0 tudo certo; 1 se alguma competência falhou.

Roda: manual no servidor de casa, uma vez por mês (python -m scripts.carga_sus --sistema sih e --sistema sia;
cron ainda não registrado em 05/11/2026); coberto por tests/test_carga_sus.py.
"""

import argparse
import hashlib
import json
import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from base import sus
from base.parquet import IGUAL, como_no_disco, gravar_com_versoes, ler_tabela
from scripts.carga_cnes import competencias_recentes
from src import acervo
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_sus")
SEM_DADOS = "sem_dados"
PASTA_DA_TABELA = {sus.SIH.nome: "sus_internacoes", sus.SIA.nome: "sus_ambulatorial"}
PASTA_DA_SITUACAO = "sus_competencias"
ORDEM_DA_SITUACAO = ["competencia", "uf"]


def _origens(
    sistema: sus.Sistema, competencia: int, situacao: pd.DataFrame
) -> list[dict[str, str]]:
    """Cada arquivo lido com o sha256 do conteúdo; sem arquivo, o pedido da competência."""
    origens = [
        {
            "url": f"ftp://{sus.SERVIDOR_FTP}{sistema.pasta_no_ftp}/{nome}",
            "sha256": resumo,
        }
        for nomes, resumos in zip(situacao["arquivos"], situacao["sha256"], strict=True)
        if nomes
        for nome, resumo in zip(nomes.split(","), resumos.split(","), strict=True)
    ]
    if origens:
        return origens
    pedido = f"ftp://{sus.SERVIDOR_FTP}{sistema.pasta_no_ftp}/{sistema.prefixo}*{competencia % 10000:04d}*.dbc"
    return [{"url": pedido, "sha256": hashlib.sha256(pedido.encode()).hexdigest()}]


def carregar_competencia(
    sistema: sus.Sistema,
    competencia: int,
    saida: Path,
    coletado_em: date,
    listar: sus.Listador = sus.listar_no_ftp,
    baixar: sus.Baixador = sus.baixar_do_ftp,
    forcar: bool = False,
    ufs: tuple[str, ...] = sus.UFS,
) -> tuple[str, str]:
    """Coleta e grava uma competência; devolve o que aconteceu com a tabela e com a situação."""
    tabela, situacao = sus.coletar_competencia(
        sistema, competencia, coletado_em, listar=listar, baixar=baixar, ufs=ufs
    )
    log.info(
        "SUS %s %s: %d estabelecimentos, %d registros somados",
        sistema.nome, competencia, len(tabela), int(situacao["registros"].sum()),
    )  # fmt: skip
    origens = _origens(sistema, competencia, situacao)
    resultado_da_tabela = SEM_DADOS
    if len(tabela):
        resultado_da_tabela = _gravar(
            tabela, saida / PASTA_DA_TABELA[sistema.nome] / str(competencia),
            list(sus.CHAVE), ("disponivel_em",), origens, forcar,
        )  # fmt: skip
    resultado_da_situacao = _gravar(
        situacao, saida / PASTA_DA_SITUACAO / f"{sistema.nome}-{competencia}",
        ORDEM_DA_SITUACAO, ("coletado_em",), origens, forcar,
    )  # fmt: skip
    return resultado_da_tabela, resultado_da_situacao


def _gravar(
    tabela: pd.DataFrame,
    destino: Path,
    ordem: list[str],
    carimbos: tuple[str, ...],
    origens: list[dict[str, str]],
    forcar: bool,
) -> str:
    """Grava só se o conteúdo mudou, sem contar a data da coleta (como `scripts/carga_cnes.py`)."""
    arquivo = destino.with_suffix(".parquet")
    if arquivo.exists() and not forcar:
        anterior = ler_tabela(arquivo).drop(columns=list(carimbos))
        # pelo Parquet dos dois lados: o decimal volta do disco como `object`, não como ArrowDtype
        novo = como_no_disco(tabela).drop(columns=list(carimbos))
        if anterior.reset_index(drop=True).equals(novo.reset_index(drop=True)):
            return IGUAL
    return gravar_com_versoes(lambda: tabela, destino, origens, ordem, forcar=True)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--sistema", choices=sorted(sus.SISTEMAS), required=True)
    argumentos.add_argument("--competencia", type=int, action="append", default=None)
    argumentos.add_argument("--uf", action="append", default=None, choices=sus.UFS)
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--forcar", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    sistema = sus.SISTEMAS[opcoes.sistema]
    competencias = opcoes.competencia or competencias_recentes(hoje)
    ufs = tuple(opcoes.uf) if opcoes.uf else sus.UFS
    saida = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    falhas = 0
    for competencia in competencias:
        try:
            resultado = carregar_competencia(
                sistema, competencia, saida, hoje, forcar=opcoes.forcar, ufs=ufs
            )
        except (TypeError, ValueError, OSError) as erro:
            log.error("SUS %s %s falhou: %s", sistema.nome, competencia, erro)
            falhas += 1
            continue
        log.info("SUS %s %s: %s", sistema.nome, competencia, json.dumps(resultado))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
