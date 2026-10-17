"""Cache persistente de preços em SQLite: o app consulta menos o Yahoo e sobrevive a uma queda dele.

Duas tabelas:
- `precos`: uma linha por ticker e dia (abertura, máxima, mínima, fechamento e volume);
- `consultas`: quando o Yahoo foi consultado pela última vez para cada ticker.

O arquivo do banco fica fora do Git (veja `.gitignore`) e pode ser apagado a qualquer momento: o
app recria tudo e baixa de novo.

Cuidado com os preços ajustados: quando uma empresa paga dividendo ou desdobra ações, o Yahoo
reajusta o passado inteiro. Por isso, ao pedir só os dias que faltam, o app compara os dias que
se repetem; se os preços mudaram, baixa o histórico inteiro de novo e só então troca o guardado
(`substituir_precos`, numa transação). Se o download falhar, o guardado fica como estava.
"""

import logging
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

PASTA_RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_PADRAO = PASTA_RAIZ / "dados_locais" / "precos.sqlite"
VARIAVEL_DO_CAMINHO = "TICKERLAB_BANCO"
COLUNAS = ["Open", "High", "Low", "Close", "Volume"]
HORAS_DE_VALIDADE = 4  # depois disso, o app pergunta ao Yahoo se há dias novos
DIAS_DE_SOBREPOSICAO = (
    7  # dias já guardados que o pedido incremental repete, para conferir
)
# diferença relativa que indica que o Yahoo reajustou o passado. Só o ruído de arredondamento
# fica abaixo dela: um dividendo de 0,05% já reajusta (achado 5c do Codex, 17/10/2026; era 0,1%)
TOLERANCIA_DO_AJUSTE = 1e-6

log = logging.getLogger(__name__)


def agora_utc() -> datetime:
    """O instante atual em UTC, sem fuso na data (é como os horários ficam no banco)."""
    return datetime.now(UTC).replace(tzinfo=None)


def caminho_do_banco() -> Path:
    """O arquivo do banco: o da variável de ambiente (usada nos testes) ou o padrão."""
    return Path(os.environ.get(VARIAVEL_DO_CAMINHO) or CAMINHO_PADRAO)


def _conectar(caminho: Path | None) -> sqlite3.Connection:
    caminho = Path(caminho) if caminho else caminho_do_banco()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS precos (
               ticker TEXT NOT NULL,
               data TEXT NOT NULL,
               open REAL, high REAL, low REAL, close REAL, volume REAL,
               PRIMARY KEY (ticker, data)
           )"""
    )
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS consultas (
               ticker TEXT PRIMARY KEY,
               consultado_em TEXT NOT NULL
           )"""
    )
    return conexao


INSERIR_PRECOS = (
    "INSERT OR REPLACE INTO precos "
    "(ticker, data, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)"
)
REGISTRAR_CONSULTA = (
    "INSERT OR REPLACE INTO consultas (ticker, consultado_em) VALUES (?, ?)"
)


def _instante(momento: datetime) -> str:
    return momento.isoformat(timespec="seconds")


def _linhas_do_banco(ticker: str, dados: pd.DataFrame) -> list[tuple]:
    return [
        (
            ticker,
            data.strftime("%Y-%m-%d"),
            *(None if pd.isna(linha[c]) else float(linha[c]) for c in COLUNAS),
        )
        for data, linha in dados.reindex(columns=COLUNAS).iterrows()
    ]


def salvar_precos(ticker: str, dados: pd.DataFrame, caminho: Path | None = None) -> int:
    """Grava (ou atualiza) os dias recebidos. Devolve quantas linhas foram gravadas."""
    if dados.empty:
        return 0
    linhas = _linhas_do_banco(ticker, dados)
    with closing(_conectar(caminho)) as conexao, conexao:
        conexao.executemany(INSERIR_PRECOS, linhas)
    return len(linhas)


def ler_precos(ticker: str, caminho: Path | None = None) -> pd.DataFrame:
    """Tudo o que está guardado do ticker, em ordem de data (vazio se não houver nada)."""
    with closing(_conectar(caminho)) as conexao:
        tabela = pd.read_sql(
            "SELECT data, open, high, low, close, volume FROM precos "
            "WHERE ticker = ? ORDER BY data",
            conexao,
            params=(ticker,),
            index_col="data",
            parse_dates=["data"],
        )
    tabela.columns = COLUNAS
    tabela.index.name = "Date"
    return tabela


def substituir_precos(
    ticker: str,
    dados: pd.DataFrame,
    agora: datetime | None = None,
    caminho: Path | None = None,
) -> int:
    """Troca o histórico inteiro do ticker pelo recebido, numa transação só.

    Ou o histórico novo fica inteiro no lugar do antigo, ou (se algo falhar no meio) o antigo
    continua lá: nunca sobra um ticker sem histórico nem um histórico misturado.
    """
    if dados.empty:
        raise ValueError("Histórico vazio: o guardado não pode ser trocado por nada.")
    linhas = _linhas_do_banco(ticker, dados)  # antes da transação: dado ruim falha aqui
    agora = agora or agora_utc()
    with closing(_conectar(caminho)) as conexao, conexao:
        conexao.execute("DELETE FROM precos WHERE ticker = ?", (ticker,))
        conexao.executemany(INSERIR_PRECOS, linhas)
        conexao.execute(REGISTRAR_CONSULTA, (ticker, _instante(agora)))
    return len(linhas)


def registrar_consulta(
    ticker: str, agora: datetime | None = None, caminho: Path | None = None
) -> None:
    agora = agora or agora_utc()
    with closing(_conectar(caminho)) as conexao, conexao:
        conexao.execute(REGISTRAR_CONSULTA, (ticker, _instante(agora)))


def consulta_recente(
    ticker: str,
    agora: datetime | None = None,
    horas: float = HORAS_DE_VALIDADE,
    caminho: Path | None = None,
) -> bool:
    """O Yahoo foi consultado para este ticker há menos de `horas` horas?"""
    agora = agora or agora_utc()
    with closing(_conectar(caminho)) as conexao:
        linha = conexao.execute(
            "SELECT consultado_em FROM consultas WHERE ticker = ?", (ticker,)
        ).fetchone()
    if linha is None:
        return False
    return agora - datetime.fromisoformat(linha[0]) < timedelta(hours=horas)


def precos_foram_reajustados(guardado: pd.DataFrame, novo: pd.DataFrame) -> bool:
    """Os dias que aparecem nos dois lados têm fechamentos diferentes (dividendo ou desdobramento)?

    O último dia guardado fica de fora quando há outros em comum: ele pode ter sido gravado com o
    pregão em andamento, e o fechamento do dia mudar não é reajuste. Um reajuste muda todos os
    dias antes da data-ex, então os outros dias em comum mostram.
    """
    comuns = guardado.index.intersection(novo.index)
    if len(comuns) > 1:
        comuns = comuns[comuns != guardado.index[-1]]
    if len(comuns) == 0:
        return False
    antes, depois = guardado.loc[comuns, "Close"], novo.loc[comuns, "Close"]
    diferenca = ((antes - depois).abs() / antes.abs()).max()
    return bool(diferenca > TOLERANCIA_DO_AJUSTE)
