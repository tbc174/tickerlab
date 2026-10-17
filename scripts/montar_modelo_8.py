"""Montagem periódica das tabelas do modelo 8, com relatório de qualidade (ADR 0027, exigência 7;
critério de pronto do modelo 8, PR D).

Remonta, dos originais do acervo, `auditores`, `insolvencia` e `eventos` (base histórica), as
`trocas_de_auditor` e o `rotulos_atraso`; as demonstrações "como era" são montadas antes, ano a ano,
pelo `scripts/montar_base_como_era.py` (o cron do servidor de casa roda os dois). Depois resume as
seis tabelas (linhas por ano, chaves duplicadas, escala dos valores em reais) e compara com a montagem
anterior (`base/qualidade_da_montagem.py`). O relatório fica em `<pasta>/qualidade/modelo_8/<dia>.json`.

Qualquer alerta ou montagem que falhou: sai com 1 e imprime uma linha `FALHAS: ...`, que o
`rodar-tarefa.sh` do servidor leva ao Uptime Kuma. Uso:

    python -m scripts.montar_modelo_8 [--pasta <acervo>/base] [--sem-montar] [--dia AAAA-MM-DD]
"""

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from base import auditores, historico
from base.dicionario import TABELAS
from base.modelos.atraso import rotulo
from base.parquet import VERSAO_GUARDADA
from base.qualidade_da_montagem import Resumo, alertas
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo, versao_do_codigo

log = logging.getLogger(__name__)

HISTORICAS = ("auditores", "insolvencia", "eventos")
# tabela → (coluna que dá o ano de cada linha, colunas a mais na chave do dicionário, se tem escala)
RESUMOS: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "rotulos_atraso": ("referencia", (), False),
    # a mesma conta aparece no trimestre e no acumulado, e em cada valor que valeu ao longo do tempo
    "demonstracoes_como_era": ("fim", ("inicio", "fim", "divulgado_em"), True),
    "auditores": ("ano_do_arquivo", (), False),
    "trocas_de_auditor": ("conhecido_em", (), False),
    "insolvencia": ("ano_do_arquivo", (), False),
    "eventos": ("ano_do_arquivo", (), False),
}
# onde cada tabela fica dentro da base: os mesmos caminhos da porta (`base/porta/duckdb.py`, um teste
# confere), copiados porque a imagem do servidor de casa não leva o DuckDB
ARQUIVOS = {
    "rotulos_atraso": "rotulos_atraso/rotulos_atraso.parquet",
    "demonstracoes_como_era": "demonstracoes/*.parquet",
    "auditores": "auditores/*.parquet",
    "trocas_de_auditor": "trocas_de_auditor/trocas.parquet",
    "insolvencia": "insolvencia/*.parquet",
    "eventos": "eventos/*.parquet",
}
CONTA_DA_ESCALA = (
    "1"  # ativo total: a mediana por ano mostra reais que viraram milhares
)
PASTA_DOS_RELATORIOS = Path("qualidade") / "modelo_8"


def dia_de(agora: datetime) -> str:
    """O dia da montagem no horário de Brasília (nome do relatório)."""
    return pd.Timestamp(agora).tz_convert("America/Sao_Paulo").date().isoformat()


def arquivos_da_tabela(pasta: Path, tabela: str) -> list[Path]:
    """Os Parquets vigentes da tabela, sem as versões guardadas (`2024.v1.parquet`)."""
    return sorted(
        a
        for a in pasta.glob(ARQUIVOS[tabela])
        if a.is_file() and not VERSAO_GUARDADA.search(a.with_suffix("").name)
    )


def _ano(coluna: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(coluna):
        return coluna.astype("Int64")
    return pd.to_datetime(coluna, errors="coerce").dt.year.astype("Int64")


def resumir(pasta: Path, tabela: str) -> Resumo | None:
    """O resumo da tabela gravada em `pasta` (None se ela não tem arquivo), um arquivo por vez: as
    chaves não se repetem entre arquivos (cada um é um ano, ou a tabela inteira)."""
    arquivos = arquivos_da_tabela(pasta, tabela)
    if not arquivos:
        return None
    coluna_do_ano, extras, com_escala = RESUMOS[tabela]
    chave = list(dict.fromkeys((*TABELAS[tabela].chaves, *extras)))
    colunas = list(
        dict.fromkeys(
            [coluna_do_ano, *chave, *(["conta", "valor"] if com_escala else [])]
        )
    )
    linhas: dict[int, int] = {}
    duplicadas = 0
    valores: dict[int, list[pd.Series]] = {}
    for arquivo in arquivos:
        dados = pd.read_parquet(arquivo, columns=colunas)
        ano = _ano(dados[coluna_do_ano])
        for a, n in ano.value_counts().items():
            linhas[int(a)] = linhas.get(int(a), 0) + int(n)
        duplicadas += int(dados.duplicated(chave, keep="first").sum())
        if com_escala:
            ativo = dados["conta"] == CONTA_DA_ESCALA
            for a, v in dados.loc[ativo, "valor"].abs().groupby(ano[ativo]):
                valores.setdefault(int(a), []).append(v)
    escala = {
        a: float(pd.concat(partes).median())
        for a, partes in valores.items()
        if pd.notna(pd.concat(partes).median())
    }
    return Resumo(tabela, linhas, duplicadas, escala)


def _anterior(pasta_dos_relatorios: Path, dia: str) -> dict[str, Resumo]:
    """Os resumos do relatório mais recente de antes de `dia` (vazio na primeira montagem)."""
    anteriores = sorted(r for r in pasta_dos_relatorios.glob("*.json") if r.stem < dia)
    if not anteriores:
        return {}
    dados = json.loads(anteriores[-1].read_text(encoding="utf-8"))
    return {nome: Resumo.do_json(r) for nome, r in dados["tabelas"].items()}


def montar(pasta: Path, agora: datetime) -> list[str]:
    """Remonta as tabelas do modelo 8; devolve o que falhou."""
    falhas = []
    with obter_engine().connect() as conexao:
        for nome in HISTORICAS:
            try:
                anos = historico.montar(nome, conexao, pasta, agora)
                log.info("%s: %d anos", nome, len(anos))
            except historico.ArquivoIlegivel as erro:
                falhas.append(str(erro))
        log.info("trocas_de_auditor: %d", auditores.montar_trocas(pasta, agora))
        if not rotulo.montar(conexao, pasta, agora):
            falhas.append(
                "rotulos_atraso: nada montado (sem índice da DFP/ITR ou sem cadastro)"
            )
    return falhas


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument(
        "--sem-montar", action="store_true", help="só o relatório de qualidade"
    )
    argumentos.add_argument("--dia", help="dia do relatório (padrão: hoje em Brasília)")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    agora = datetime.now(UTC)
    dia = opcoes.dia or dia_de(agora)

    falhas = [] if opcoes.sem_montar else montar(pasta, agora)
    relatorios = pasta / PASTA_DOS_RELATORIOS
    anteriores = _anterior(relatorios, dia)
    resumos: dict[str, Resumo] = {}
    for tabela in RESUMOS:
        resumo = resumir(pasta, tabela)
        if resumo is None:
            falhas.append(f"{tabela}: sem arquivo na base")
            continue
        resumos[tabela] = resumo
        falhas.extend(alertas(resumo, anteriores.get(tabela)))

    relatorios.mkdir(parents=True, exist_ok=True)
    relatorio = {
        "dia": dia,
        "montado_em": agora.isoformat(),
        "versao_do_codigo": versao_do_codigo(),
        "tabelas": {nome: r.para_json() for nome, r in resumos.items()},
        "alertas": falhas,
    }
    (relatorios / f"{dia}.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    for tabela, resumo in resumos.items():
        log.info(
            "%s: %d linhas em %d anos",
            tabela,
            sum(resumo.linhas_por_ano.values()),
            len(resumo.linhas_por_ano),
        )
    if falhas:
        for falha in falhas:
            log.error("%s", falha)
        print("FALHAS: " + "; ".join(falhas)[:900])
        return 1
    log.info("nenhum alerta (%s)", relatorios / f"{dia}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
