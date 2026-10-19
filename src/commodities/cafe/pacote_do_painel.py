"""O pacote do Painel do café: as tabelas da base que o painel usa, num JSON só.

Como o pacote do mapa (`pacote_do_mapa.py`): a base (DuckDB) mora no servidor de casa e o painel roda
no servidor do app, que não tem a base. O pacote é montado lá (`montar_pacote`, com as tabelas lidas
pela porta; `scripts/montar_pacotes_do_cafe.py`) e chega aqui como um arquivo JSON (`ler_pacote`),
que `painel.tabelas_pela_porta` usa quando a porta da base não abre. As contas continuam no painel,
com as mesmas funções: o pacote só carrega as linhas.

**Sem olhar o futuro:** o pacote do dia D leva só as linhas já públicas em D, com todas as versões
(o termômetro da CONAB usa o 1º levantamento de cada safra, e o corte "como estava em" de cada tabela
continua valendo). Do Comex vão só os últimos meses que o painel mostra: a tabela é grande e o resto
não aparece. Um arquivo que não abre ou de versão desconhecida vira `None` (o painel diz "sem a base").
"""

import functools
import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from src.configuracao import PASTA_RAIZ

log = logging.getLogger(__name__)

VERSAO_DO_PACOTE = 1  # muda quando o app precisa ler o pacote de outro jeito
VARIAVEL_DO_ARQUIVO = "TICKERLAB_PAINEL_DO_CAFE"
ARQUIVO_PADRAO = PASTA_RAIZ / "dados_locais" / "commodities" / "painel_do_cafe.json"
COMEX = "comex"
# a coluna que diz quando cada linha ficou pública, por tabela do painel (`painel.TABELAS_DA_BASE`)
COLUNA_DA_DIVULGACAO = {
    "cftc": "disponivel_em",
    COMEX: "divulgado_em",
    "usda": "divulgado_em",
    "conab": "divulgado_em",
    "clima": "disponivel_em",
}


@dataclass(frozen=True)
class PacoteDoPainel:
    """As tabelas como estavam em `gerado_em` e, para cada uma que faltou na base, o motivo."""

    gerado_em: date
    tabelas: Mapping[str, pd.DataFrame] = field(default_factory=dict)
    motivos: Mapping[str, str] = field(default_factory=dict)


# --- montar (no servidor de casa) ------------------------------------------------------------------
def _publicas_em(nome: str, tabela: pd.DataFrame, dia: date) -> pd.DataFrame:
    """As linhas já públicas em `dia`, com todas as versões (o painel faz o corte de cada tabela)."""
    coluna = COLUNA_DA_DIVULGACAO[nome]
    divulgacao = pd.to_datetime(tabela[coluna])
    return tabela[divulgacao <= pd.Timestamp(dia)].reset_index(drop=True)


def _ultimos_meses(tabela: pd.DataFrame, meses: int) -> pd.DataFrame:
    """As linhas das últimas `meses` competências (todas as versões de cada uma)."""
    competencias = pd.to_datetime(tabela["competencia"])
    ultimas = sorted(competencias.unique())[-meses:]
    return tabela[competencias.isin(ultimas)].reset_index(drop=True)


def montar_pacote(
    tabelas: Mapping[str, pd.DataFrame],
    motivos: Mapping[str, str],
    dia: date,
    meses_do_comex: int,
) -> PacoteDoPainel:
    """O pacote de `dia`: cada tabela só com o que era público nesse dia; o Comex, só os últimos
    `meses_do_comex` meses (os que o painel soma)."""
    desconhecidas = set(tabelas) - set(COLUNA_DA_DIVULGACAO)
    if desconhecidas:
        raise ValueError(f"tabelas fora do painel: {sorted(desconhecidas)}")
    recortadas: dict[str, pd.DataFrame] = {}
    for nome, tabela in tabelas.items():
        publicas = _publicas_em(nome, tabela, dia)
        recortadas[nome] = (
            _ultimos_meses(publicas, meses_do_comex) if nome == COMEX else publicas
        )
    return PacoteDoPainel(dia, recortadas, dict(motivos))


# --- o JSON ----------------------------------------------------------------------------------------
def _colunas_de_data(tabela: pd.DataFrame) -> list[str]:
    """As colunas de data: o JSON as leva como texto e a leitura as devolve como data."""
    return [
        str(coluna)
        for coluna in tabela.columns
        if pd.api.types.is_datetime64_any_dtype(tabela[coluna])
    ]


def _tabela_em_dicionario(tabela: pd.DataFrame) -> dict[str, object]:
    dividida = json.loads(
        tabela.to_json(orient="split", index=False, date_format="iso", date_unit="s")
    )
    return {
        "colunas": dividida["columns"],
        "datas": _colunas_de_data(tabela),
        "linhas": dividida["data"],
    }


def _tabela_do_dicionario(dado: Mapping[str, object]) -> pd.DataFrame:
    colunas = list(dado["colunas"])  # type: ignore[call-overload]
    tabela = pd.DataFrame(dado["linhas"], columns=colunas)  # type: ignore[arg-type]
    for coluna in dado["datas"]:  # type: ignore[attr-defined]
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    return tabela


def em_dicionario(pacote: PacoteDoPainel) -> dict[str, object]:
    return {
        "versao": VERSAO_DO_PACOTE,
        "gerado_em": pacote.gerado_em.isoformat(),
        "tabelas": {
            nome: _tabela_em_dicionario(tabela)
            for nome, tabela in pacote.tabelas.items()
        },
        "motivos": dict(pacote.motivos),
    }


def do_dicionario(dado: Mapping[str, object]) -> PacoteDoPainel:
    if dado.get("versao") != VERSAO_DO_PACOTE:
        raise ValueError(
            f"versão do pacote do painel desconhecida: {dado.get('versao')!r}"
        )
    tabelas = dado["tabelas"]
    motivos = dado["motivos"]
    if not isinstance(tabelas, Mapping) or not isinstance(motivos, Mapping):
        raise TypeError("pacote do painel sem as tabelas ou sem os motivos")
    return PacoteDoPainel(
        date.fromisoformat(str(dado["gerado_em"])),
        {str(nome): _tabela_do_dicionario(t) for nome, t in tabelas.items()},
        {str(nome): str(motivo) for nome, motivo in motivos.items()},
    )


def gravar_pacote(pacote: PacoteDoPainel, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(em_dicionario(pacote), ensure_ascii=False, separators=(",", ":"))
    caminho.write_text(texto, encoding="utf-8")


def arquivo_do_pacote() -> Path:
    return Path(os.environ.get(VARIAVEL_DO_ARQUIVO) or ARQUIVO_PADRAO)


@functools.lru_cache(maxsize=2)
def _ler(caminho: str, _versao_do_arquivo: tuple[int, int]) -> PacoteDoPainel | None:
    """Lê uma vez por versão do arquivo (data e tamanho): o painel é aberto a cada visita."""
    try:
        return do_dicionario(json.loads(Path(caminho).read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        log.exception("Pacote do painel do café inválido: %s", Path(caminho).name)
        return None


def ler_pacote(caminho: Path | None = None) -> PacoteDoPainel | None:
    """O pacote gravado, ou `None` se ainda não há arquivo ou se ele não abre (o erro vai ao log)."""
    caminho = caminho or arquivo_do_pacote()
    try:
        estado = caminho.stat()
    except OSError:
        return None
    return _ler(str(caminho), (estado.st_mtime_ns, estado.st_size))
