"""Registro de tentativas do modelo C-1 (pré-registro v2, seção 9; ADR 0006).

**Cada execução de treino e avaliação conta**, inclusive repetida e inclusive a que dá erro depois
de olhar o alvo: é o que torna honesta a correção de Holm pelo número de tentativas. O orçamento é
de 20; mudar o critério depois de aprovado soma 5 (a v2 já começou com 5 usadas). O hash da
especificação fica guardado para rastrear, mas não perdoa repetição.

Irmão do `trader/registro.py` da pesquisa de trading (que é outra área, com regras próprias). O
banco é um SQLite fora do Git: perder o arquivo perde a contagem, então ele tem cópia de segurança
junto com o acervo.
"""

import hashlib
import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ORCAMENTO = 20
FASES = ("desenvolvimento", "lacrado")
ESQUEMA = """
CREATE TABLE IF NOT EXISTS tentativas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash TEXT NOT NULL,
    fase TEXT NOT NULL,
    especificacao TEXT NOT NULL,
    commit_do_codigo TEXT NOT NULL,
    criada_em TEXT NOT NULL,
    p_valor REAL,
    ganho REAL,
    aprovada INTEGER
);
CREATE TABLE IF NOT EXISTS ajustes (
    versao TEXT PRIMARY KEY,
    motivo TEXT NOT NULL,
    tentativas INTEGER NOT NULL,
    criado_em TEXT NOT NULL
);
"""


class OrcamentoEstouradoError(RuntimeError):
    """As 20 tentativas acabaram: não há mais execução honesta possível nesta versão."""


def hash_da_especificacao(especificacao: dict) -> str:
    """SHA-256 da especificação em forma canônica (chaves em ordem)."""
    canonica = json.dumps(
        especificacao, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonica.encode("utf-8")).hexdigest()


def commit_atual() -> str:
    """O commit do código que está rodando (ou "desconhecido" fora de um repositório Git)."""
    try:
        saida = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "desconhecido"
    return saida.stdout.strip()


class Registro:
    """O registro de tentativas num arquivo SQLite."""

    def __init__(self, caminho: Path, commit: str | None = None) -> None:
        self.caminho = caminho
        self.commit = commit or commit_atual()
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._conexao() as conexao:
            conexao.executescript(ESQUEMA)

    def registrar_ajuste(self, versao: str, motivo: str, tentativas: int) -> None:
        """Soma as tentativas de uma versão nova do critério (uma vez por versão)."""
        with self._conexao() as conexao:
            conexao.execute(
                "INSERT OR IGNORE INTO ajustes VALUES (?, ?, ?, ?)",
                (versao, motivo, tentativas, _agora()),
            )

    def usadas(self) -> int:
        """Execuções registradas mais as tentativas somadas pelos ajustes."""
        with self._conexao() as conexao:
            execucoes = conexao.execute("SELECT COUNT(*) FROM tentativas").fetchone()[0]
            ajustes = conexao.execute(
                "SELECT COALESCE(SUM(tentativas), 0) FROM ajustes"
            ).fetchone()[0]
        return int(execucoes + ajustes)

    def nova_tentativa(self, especificacao: dict, fase: str) -> int:
        """Registra uma execução **antes** de ela olhar o alvo; devolve o número dela."""
        if fase not in FASES:
            raise ValueError(f"A fase tem de ser uma de {FASES}, não {fase!r}.")
        if self.usadas() >= ORCAMENTO:
            raise OrcamentoEstouradoError(
                f"As {ORCAMENTO} tentativas do pré-registro acabaram."
            )
        with self._conexao() as conexao:
            cursor = conexao.execute(
                "INSERT INTO tentativas (hash, fase, especificacao, commit_do_codigo, criada_em)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    hash_da_especificacao(especificacao),
                    fase,
                    json.dumps(
                        especificacao, sort_keys=True, ensure_ascii=False, default=str
                    ),
                    self.commit,
                    _agora(),
                ),
            )
            return int(cursor.lastrowid or 0)

    def anotar_resultado(
        self, tentativa: int, p_valor: float, ganho: float, aprovada: bool
    ) -> None:
        """Guarda o resultado de uma execução (o p entra na correção de Holm das seguintes)."""
        with self._conexao() as conexao:
            conexao.execute(
                "UPDATE tentativas SET p_valor = ?, ganho = ?, aprovada = ? WHERE id = ?",
                (p_valor, ganho, int(aprovada), tentativa),
            )

    def p_das_outras(self, tentativa: int) -> list[float]:
        """Os p das outras execuções com resultado, para a correção de Holm desta."""
        with self._conexao() as conexao:
            linhas = conexao.execute(
                "SELECT p_valor FROM tentativas WHERE id != ? AND p_valor IS NOT NULL ORDER BY id",
                (tentativa,),
            ).fetchall()
        return [float(linha[0]) for linha in linhas]

    def aprovada(self, tentativa: int) -> bool:
        """Se a execução passou no desenvolvimento (só ela pode abrir o lacrado)."""
        with self._conexao() as conexao:
            linha = conexao.execute(
                "SELECT aprovada FROM tentativas WHERE id = ?", (tentativa,)
            ).fetchone()
        return bool(linha and linha[0])

    def hash_da(self, tentativa: int) -> str:
        """O hash da especificação de uma execução."""
        with self._conexao() as conexao:
            return conexao.execute(
                "SELECT hash FROM tentativas WHERE id = ?", (tentativa,)
            ).fetchone()[0]

    def _conexao(self) -> sqlite3.Connection:
        return sqlite3.connect(self.caminho)


def _agora() -> str:
    return datetime.now(UTC).isoformat()
