"""A memória do bot, em SQLite próprio (fora do banco do TickerLab): o que já foi visto, o que
deu errado (negativo) e o veredito de cada fato conferido.

Serve para o bot não repetir o mesmo caminho morto a cada rodada das 8h, 14h e 20h. Negativo vale
por `VALIDADE_DO_NEGATIVO_DIAS`: depois disso a fonte pode ter se consertado e vale tentar de novo.
"""

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

VALIDADE_DO_NEGATIVO_DIAS = 7
TABELAS = ("visto", "negativo", "fato")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS visto (
    url TEXT PRIMARY KEY, url_final TEXT, sha256 TEXT NOT NULL, tipo TEXT NOT NULL,
    tamanho INTEGER NOT NULL, content_type TEXT, quando TEXT NOT NULL, rodada TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS negativo (
    url TEXT PRIMARY KEY, motivo TEXT NOT NULL, status_http INTEGER,
    quando TEXT NOT NULL, rodada TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fato (
    id INTEGER PRIMARY KEY AUTOINCREMENT, rodada TEXT NOT NULL, hipotese TEXT NOT NULL,
    fato TEXT NOT NULL, veredito TEXT NOT NULL, motivos TEXT NOT NULL, quando TEXT NOT NULL
);
"""


def agora() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Visto:
    url: str
    url_final: str | None
    sha256: str
    tipo: str
    tamanho: int
    content_type: str | None
    quando: str
    rodada: str


@dataclass(frozen=True)
class Negativo:
    url: str
    motivo: str
    status_http: int | None
    quando: str
    rodada: str


class Memoria:
    """Abre (e cria, se não existir) o SQLite em `caminho`."""

    def __init__(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho = caminho
        with self._conexao() as conexao:
            conexao.executescript(ESQUEMA)

    def _conexao(self) -> closing[sqlite3.Connection]:
        conexao = sqlite3.connect(self.caminho)
        conexao.row_factory = sqlite3.Row
        return closing(conexao)

    def lembrar(self, visto: Visto) -> None:
        """Guarda o que foi visto e apaga o negativo da mesma URL (agora ela abriu)."""
        with self._conexao() as conexao:
            conexao.execute(
                "INSERT OR REPLACE INTO visto VALUES (?,?,?,?,?,?,?,?)",
                (
                    visto.url,
                    visto.url_final,
                    visto.sha256,
                    visto.tipo,
                    visto.tamanho,
                    visto.content_type,
                    visto.quando,
                    visto.rodada,
                ),
            )
            conexao.execute("DELETE FROM negativo WHERE url = ?", (visto.url,))
            conexao.commit()

    def ja_visto(self, url: str) -> Visto | None:
        with self._conexao() as conexao:
            linha = conexao.execute(
                "SELECT * FROM visto WHERE url = ?", (url,)
            ).fetchone()
        return Visto(**dict(linha)) if linha else None

    def anotar_negativo(
        self, url: str, motivo: str, status_http: int | None, rodada: str
    ) -> None:
        with self._conexao() as conexao:
            conexao.execute(
                "INSERT OR REPLACE INTO negativo VALUES (?,?,?,?,?)",
                (url, motivo, status_http, agora().isoformat(), rodada),
            )
            conexao.commit()

    def negativo_valido(self, url: str) -> Negativo | None:
        """O negativo de `url`, se ainda está na validade; vencido, vale tentar de novo."""
        with self._conexao() as conexao:
            linha = conexao.execute(
                "SELECT * FROM negativo WHERE url = ?", (url,)
            ).fetchone()
        if linha is None:
            return None
        negativo = Negativo(**dict(linha))
        idade = agora() - datetime.fromisoformat(negativo.quando)
        if idade > timedelta(days=VALIDADE_DO_NEGATIVO_DIAS):
            return None
        return negativo

    def registrar_fato(
        self,
        rodada: str,
        hipotese: str,
        fato: dict[str, object],
        veredito: str,
        motivos: list[str],
    ) -> None:
        with self._conexao() as conexao:
            conexao.execute(
                "INSERT INTO fato (rodada, hipotese, fato, veredito, motivos, quando)"
                " VALUES (?,?,?,?,?,?)",
                (
                    rodada,
                    hipotese,
                    json.dumps(fato, ensure_ascii=False),
                    veredito,
                    json.dumps(motivos, ensure_ascii=False),
                    agora().isoformat(),
                ),
            )
            conexao.commit()

    def contagens(self) -> dict[str, int]:
        """Quantas linhas há em cada tabela (para o estado da rodada)."""
        with self._conexao() as conexao:
            return {
                tabela: conexao.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
                for tabela in TABELAS
            }
