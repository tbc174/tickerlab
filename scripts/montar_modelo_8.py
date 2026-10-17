"""Montagem periódica das tabelas do modelo 8, com relatório de qualidade (ADR 0027, exigência 7;
critério de pronto do modelo 8, PR D).

Remonta, dos originais do acervo, `auditores`, `fca_geral`, `insolvencia` e `eventos` (base
histórica), as `trocas_de_auditor`, o `rotulos_atraso` e as `colunas_atraso`; as demonstrações "como era" são montadas antes, ano a ano,
pelo `scripts/montar_base_como_era.py` (o cron do servidor de casa roda os dois). Depois resume as
oito tabelas (linhas por ano, chaves duplicadas, escala dos valores em reais) e compara com a montagem
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
import sqlalchemy as sa

from base import auditores, historico
from base.cadastro import cadastro_do_acervo
from base.dicionario import TABELAS
from base.modelos.atraso import colunas, rotulo
from base.parquet import (
    LINHAGEM,
    VERSAO_GUARDADA,
    arquivos_atuais,
    gravar_se_mudou,
    origem_de_tabela,
)
from base.ponto_no_tempo import divulgacao_publica
from base.qualidade_da_montagem import Resumo, alertas
from src import acervo
from src.banco.coletas import exigir_licenca
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo, versao_do_codigo

log = logging.getLogger(__name__)

HISTORICAS = ("auditores", "fca_geral", "insolvencia", "eventos")
# tabela → (coluna que dá o ano de cada linha, colunas a mais na chave do dicionário, se tem escala)
RESUMOS: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "rotulos_atraso": ("referencia", (), False),
    "colunas_atraso": ("referencia", (), False),
    # a mesma conta aparece no trimestre e no acumulado, e em cada valor que valeu ao longo do tempo
    "demonstracoes_como_era": ("fim", ("inicio", "fim", "divulgado_em"), True),
    "auditores": ("ano_do_arquivo", (), False),
    "fca_geral": ("ano_do_arquivo", (), False),
    "trocas_de_auditor": ("conhecido_em", (), False),
    "insolvencia": ("ano_do_arquivo", (), False),
    "eventos": ("ano_do_arquivo", (), False),
}
# onde cada tabela fica dentro da base: os mesmos caminhos da porta (`base/porta/duckdb.py`, um teste
# confere), copiados porque a imagem do servidor de casa não leva o DuckDB
ARQUIVOS = {
    "rotulos_atraso": "rotulos_atraso/rotulos_atraso.parquet",
    "colunas_atraso": "colunas_atraso/colunas_atraso.parquet",
    "demonstracoes_como_era": "demonstracoes/*.parquet",
    "auditores": "auditores/*.parquet",
    "fca_geral": "fca_geral/*.parquet",
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


# --- as colunas do modelo (`base/modelos/atraso/colunas.py`): a leitura das fontes fica aqui, no
# montador, porque só montador lê a base sem a porta (tests/test_porta_unica.py) ------------
_VALORES_MOBILIARIOS = Path("fca") / "valores_mobiliarios.parquet"


def _datas(tabela: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    return tabela.assign(
        **{c: pd.to_datetime(tabela[c], errors="coerce") for c in colunas}
    )


def _ler(
    pasta: Path, nome: str, colunas: list[str], origens: list[dict[str, str]]
) -> pd.DataFrame:
    """Todos os anos de uma tabela da base, só com `colunas` (vazia se ainda não foi montada)."""
    arquivos = arquivos_atuais(pasta / nome)
    origens.extend(origem_de_tabela(a, pasta) for a in arquivos)
    if not arquivos:
        return pd.DataFrame(columns=colunas)
    return pd.concat(
        [pd.read_parquet(a, columns=colunas) for a in arquivos], ignore_index=True
    )


def _demonstracoes(pasta: Path, origens: list[dict[str, str]]) -> pd.DataFrame:
    """As contas do balanço de todos os anos da base "como era", um ano por vez (cabe na memória)."""
    colunas = [
        "cnpj", "grupo", "demonstracao", "conta", "descricao", "inicio", "fim", "valor",
        "divulgado_em", "ate",
    ]  # fmt: skip
    partes = []
    for arquivo in arquivos_atuais(pasta / "demonstracoes"):
        origens.append(origem_de_tabela(arquivo, pasta))
        ano = pd.read_parquet(
            arquivo,
            columns=colunas,
            filters=[("demonstracao", "in", ["BPA", "BPP", "DRE"])],
        )
        partes.append(colunas.contas_do_balanco(ano))
    if not partes:
        return pd.DataFrame(columns=[*colunas, "item"])
    return _datas(
        pd.concat(partes, ignore_index=True), ["inicio", "fim", "divulgado_em", "ate"]
    )


def fontes_das_colunas(
    conexao: sa.Connection, pasta: Path, origens: list[dict[str, str]]
) -> tuple[pd.DataFrame, colunas.Fontes] | None:
    """Os exemplos do rótulo e as fontes das colunas, lidos da base e do acervo (None sem o rótulo,
    sem o índice ou sem o cadastro). Cada tabela lida entra em `origens`."""
    arquivo_do_rotulo = pasta / rotulo.TABELA / f"{rotulo.TABELA}.parquet"
    achado = cadastro_do_acervo(conexao)
    indice, _, origens_do_indice = rotulo.ler_indices(conexao)
    if not arquivo_do_rotulo.exists() or achado is None or indice is None:
        return None
    cadastro, origem_do_cadastro = achado
    origens.extend([origem_de_tabela(arquivo_do_rotulo, pasta), *origens_do_indice])
    origens.append(origem_do_cadastro)
    exemplos = _datas(
        pd.read_parquet(arquivo_do_rotulo),
        ["referencia", "data_da_previsao", "prazo", "primeira_entrega"],
    )
    indice = indice.assign(
        publico_em=divulgacao_publica(
            indice["cnpj"], pd.to_datetime(indice["recebido_em"]), cadastro
        )
    )
    valores = pd.DataFrame(
        columns=[
            "cnpj", "referencia", "versao", "recebido_em", "valor_mobiliario", "mercado",
            "segmento", "fim_negociacao",
        ]
    )  # fmt: skip
    if (pasta / _VALORES_MOBILIARIOS).exists():
        origens.append(origem_de_tabela(pasta / _VALORES_MOBILIARIOS, pasta))
        valores = pd.read_parquet(
            pasta / _VALORES_MOBILIARIOS, columns=list(valores.columns)
        )
    valores = _datas(valores, ["referencia", "recebido_em", "fim_negociacao"])
    valores = valores.assign(
        publico_em=divulgacao_publica(valores["cnpj"], valores["recebido_em"], cadastro)
    )
    colunas_do_fca = [
        "cnpj", "referencia", "versao", "conhecido_em", "categoria", "setor",
        "controle_acionario", "mes_fim_do_exercicio",
    ]  # fmt: skip
    colunas_dos_mandatos = [
        "cnpj", "referencia", "versao", "conhecido_em", "auditor_id", "inicio", "fim",
    ]  # fmt: skip
    fontes = colunas.Fontes(
        entregas=exemplos,
        indice=indice,
        cadastro=cadastro,
        fca_geral=_datas(
            _ler(pasta, "fca_geral", colunas_do_fca, origens),
            ["referencia", "conhecido_em"],
        ),
        valores=valores,
        auditores=_datas(
            _ler(pasta, "auditores", colunas_dos_mandatos, origens),
            ["referencia", "conhecido_em", "inicio", "fim"],
        ),
        trocas=_datas(
            _ler(pasta, "trocas_de_auditor", ["cnpj", "conhecido_em"], origens),
            ["conhecido_em"],
        ),
        insolvencia=_datas(
            _ler(pasta, "insolvencia", ["cnpj", "rotulo", "conhecido_em"], origens),
            ["conhecido_em"],
        ),
        eventos=_datas(
            _ler(pasta, "eventos", ["cnpj", "publicado_em"], origens), ["publicado_em"]
        ),
        demonstracoes=_demonstracoes(pasta, origens),
    )
    return exemplos, fontes


def montar_colunas(conexao: sa.Connection, pasta: Path, agora: datetime) -> int:
    """`<pasta>/colunas_atraso/colunas_atraso.parquet`, uma linha por exemplo do rótulo; devolve as
    linhas (0 e nada gravado sem o rótulo, o índice ou o cadastro). Roda depois do rótulo e das
    tabelas históricas."""
    exigir_licenca("treinar", colunas.FONTES_DAS_COLUNAS, onde=colunas.TABELA)
    origens: list[dict[str, str]] = []
    lidas = fontes_das_colunas(conexao, pasta, origens)
    if lidas is None:
        return 0
    exemplos, fontes = lidas
    tabela = colunas.colunas_como_era_na_data(exemplos, fontes).assign(
        montado_em=agora.isoformat(), versao_do_codigo=versao_do_codigo()
    )
    gravar_se_mudou(
        tabela,
        pasta / colunas.TABELA / f"{colunas.TABELA}.parquet",
        origens,
        colunas.CHAVE,
        carimbos=LINHAGEM,
    )
    return len(tabela)


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
        # as colunas leem o rótulo e as históricas montadas acima
        elif not montar_colunas(conexao, pasta, agora):
            falhas.append(
                "colunas_atraso: nada montado (sem rótulo, índice ou cadastro)"
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
