"""Registro de tentativas da M2: toda configuração testada entra aqui, sem exceção.

Existe para cumprir a seção 7 do critério aprovado (`docs/pre-registro-m2-v0.4.md`): o Sharpe
deflacionado só é honesto se contar **todas** as variações que foram experimentadas, e não só a
que deu certo. Cada tentativa é um dicionário com a especificação completa (modelo, rótulo,
atributos, parâmetros, custos...). O hash dessa especificação é a identidade: rodar de novo a mesma
configuração **não** é uma tentativa nova; mudar qualquer valor é.

O banco fica em `pesquisa_m2/registro.db` (fora do Git). Se ele for perdido, a contagem se perde e o
DSR fica otimista: faça cópia de segurança.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DA_PESQUISA = RAIZ / "pesquisa_m2"
CAMINHO_PADRAO = PASTA_DA_PESQUISA / "registro.db"
ORCAMENTO_DE_TENTATIVAS = 300  # critério, seção 7
TENTATIVAS_POR_AJUSTE = 25  # mudar o critério depois de aprovado soma isto
# baselines, linear, árvores, meta-rotulagem, deep learning e séries temporais clássicas (v0.2)
FAMILIAS = ("H0", "H1", "H2", "H3", "H4", "H5")
FASES = ("desenvolvimento", "holdout")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS tentativas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash TEXT NOT NULL,
    familia TEXT NOT NULL,
    nome TEXT NOT NULL,
    fase TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    commit_do_codigo TEXT NOT NULL,
    criada_em TEXT NOT NULL,
    execucoes INTEGER NOT NULL DEFAULT 1,
    resultado_json TEXT,
    UNIQUE (hash, fase)
);
CREATE TABLE IF NOT EXISTS ajustes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    versao TEXT NOT NULL,
    motivo TEXT NOT NULL,
    tentativas_extras INTEGER NOT NULL,
    registrado_em TEXT NOT NULL
);
"""
# Quem escreveu cada hipótese (ideia "proveniência" do Vibe-Trading, 20/10/2026). Fica numa tabela à
# parte, de propósito: a identidade da tentativa é o hash da especificação, e anotar o autor não pode
# fazer a mesma configuração contar de novo. Bancos antigos ganham a tabela vazia ao abrir.
ESQUEMA_DA_PROVENIENCIA = """
CREATE TABLE IF NOT EXISTS proveniencia (
    tentativa_id INTEGER PRIMARY KEY REFERENCES tentativas (id),
    autor TEXT NOT NULL,
    modelo TEXT,
    commit_do_codigo TEXT NOT NULL,
    registrada_em TEXT NOT NULL
);
"""


def especificacao_canonica(spec: dict) -> str:
    """JSON estável (chaves ordenadas, sem espaços). Valores que não são JSON dão erro de propósito."""
    return json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_da_especificacao(spec: dict) -> str:
    return hashlib.sha256(especificacao_canonica(spec).encode("utf-8")).hexdigest()


def commit_atual() -> str:
    """Commit do código que está rodando, com `+alterado` se há mudanças ainda não commitadas."""
    try:
        base = ["git", "-C", str(RAIZ)]
        curto = subprocess.run(
            [*base, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        ).stdout.strip()
        sujo = subprocess.run(
            [*base, "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "desconhecido"
    return f"{curto}+alterado" if sujo else curto


class OrcamentoEstouradoError(RuntimeError):
    """Mais tentativas do que o orçamento aprovado (não bloqueia: só avisa e penaliza o DSR)."""


class Registro:
    """Uso: `r = Registro(); r.registrar("H2", "lightgbm_v1", {...})`."""

    def __init__(
        self,
        caminho: Path = CAMINHO_PADRAO,
        commit_fn: Callable[[], str] = commit_atual,
        agora_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
        familias: tuple[str, ...] = FAMILIAS,
        orcamento: int = ORCAMENTO_DE_TENTATIVAS,
    ) -> None:
        self.caminho = Path(caminho)
        self.familias = familias
        self.orcamento = orcamento
        self._commit_fn = commit_fn
        self._agora_fn = agora_fn
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._conectar() as c:
            c.executescript(ESQUEMA)
            c.executescript(ESQUEMA_DA_PROVENIENCIA)

    def _conectar(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.caminho)
        c.row_factory = sqlite3.Row
        return c

    # --- escrever ----------------------------------------------------------------------------
    def registrar(
        self, familia: str, nome: str, spec: dict, fase: str = "desenvolvimento"
    ) -> int:
        """Anota a tentativa e devolve o id. A mesma especificação na mesma fase não conta de novo."""
        if familia not in self.familias:
            raise ValueError(
                f"Família desconhecida: {familia}. Use uma de {self.familias}."
            )
        if fase not in FASES:
            raise ValueError(f"Fase desconhecida: {fase}. Use uma de {FASES}.")
        if not nome.strip():
            raise ValueError("A tentativa precisa de um nome.")
        texto = especificacao_canonica(spec)
        hash_ = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        with self._conectar() as c:
            existente = c.execute(
                "SELECT id FROM tentativas WHERE hash = ? AND fase = ?", (hash_, fase)
            ).fetchone()
            if existente:
                c.execute(
                    "UPDATE tentativas SET execucoes = execucoes + 1 WHERE id = ?",
                    (existente["id"],),
                )
                return int(existente["id"])
            cursor = c.execute(
                "INSERT INTO tentativas (hash, familia, nome, fase, spec_json,"
                " commit_do_codigo, criada_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    hash_,
                    familia,
                    nome,
                    fase,
                    texto,
                    self._commit_fn(),
                    self._agora_fn().isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def salvar_resultado(self, tentativa_id: int, resultado: dict) -> None:
        with self._conectar() as c:
            alteradas = c.execute(
                "UPDATE tentativas SET resultado_json = ? WHERE id = ?",
                (especificacao_canonica(resultado), tentativa_id),
            ).rowcount
        if not alteradas:
            raise KeyError(f"Não existe a tentativa {tentativa_id}.")

    def registrar_proveniencia(
        self, tentativa_id: int, autor: str, modelo: str | None = None
    ) -> None:
        """Anota quem escreveu a hipótese: a pessoa (`autor`) e, se veio de um LLM, o `modelo`.

        É um fato do passado: repetir a mesma anotação não faz nada, e uma anotação diferente
        para a mesma tentativa é recusada (não se reescreve quem escreveu).
        """
        if not autor.strip():
            raise ValueError("A proveniência precisa de um autor.")
        modelo = modelo.strip() if modelo and modelo.strip() else None
        self.obter(tentativa_id)  # KeyError se a tentativa não existe
        anterior = self.obter_proveniencia(tentativa_id)
        if anterior is not None:
            if (anterior["autor"], anterior["modelo"]) != (autor.strip(), modelo):
                raise ValueError(
                    f"A tentativa {tentativa_id} já tem autor ({anterior['autor']}); "
                    "a proveniência não se reescreve."
                )
            return
        with self._conectar() as c:
            c.execute(
                "INSERT INTO proveniencia (tentativa_id, autor, modelo, commit_do_codigo,"
                " registrada_em) VALUES (?, ?, ?, ?, ?)",
                (
                    tentativa_id,
                    autor.strip(),
                    modelo,
                    self._commit_fn(),
                    self._agora_fn().isoformat(),
                ),
            )

    def registrar_ajuste_do_criterio(self, versao: str, motivo: str) -> None:
        """Mudar o critério depois de aprovado é permitido, mas custa tentativas (seção 7)."""
        with self._conectar() as c:
            c.execute(
                "INSERT INTO ajustes (versao, motivo, tentativas_extras, registrado_em)"
                " VALUES (?, ?, ?, ?)",
                (versao, motivo, TENTATIVAS_POR_AJUSTE, self._agora_fn().isoformat()),
            )

    # --- ler ---------------------------------------------------------------------------------
    def obter(self, tentativa_id: int) -> dict:
        with self._conectar() as c:
            linha = c.execute(
                "SELECT * FROM tentativas WHERE id = ?", (tentativa_id,)
            ).fetchone()
        if linha is None:
            raise KeyError(f"Não existe a tentativa {tentativa_id}.")
        dados = dict(linha)
        dados["spec"] = json.loads(dados.pop("spec_json"))
        bruto = dados.pop("resultado_json")
        dados["resultado"] = json.loads(bruto) if bruto else None
        return dados

    def obter_proveniencia(self, tentativa_id: int) -> dict | None:
        """Quem escreveu a tentativa, ou `None` se ninguém anotou (nunca se adivinha)."""
        with self._conectar() as c:
            linha = c.execute(
                "SELECT autor, modelo, commit_do_codigo, registrada_em FROM proveniencia"
                " WHERE tentativa_id = ?",
                (tentativa_id,),
            ).fetchone()
        return dict(linha) if linha else None

    def contar(self, fase: str = "desenvolvimento") -> int:
        """Configurações distintas testadas na fase (sem os ajustes do critério)."""
        with self._conectar() as c:
            return int(
                c.execute(
                    "SELECT COUNT(*) FROM tentativas WHERE fase = ?", (fase,)
                ).fetchone()[0]
            )

    def tentativas_extras(self) -> int:
        with self._conectar() as c:
            return int(
                c.execute(
                    "SELECT COALESCE(SUM(tentativas_extras), 0) FROM ajustes"
                ).fetchone()[0]
            )

    def total_para_o_dsr(self) -> int:
        """O número de tentativas que o Sharpe deflacionado deve usar: desenvolvimento + ajustes."""
        return self.contar("desenvolvimento") + self.tentativas_extras()

    def orcamento_restante(self) -> int:
        """Negativo quando o orçamento (300 na M2) foi ultrapassado."""
        return self.orcamento - self.total_para_o_dsr()

    def exigir_orcamento(self) -> None:
        """Para quem quiser parar de verdade ao estourar; o padrão é só avisar e penalizar."""
        if self.orcamento_restante() < 0:
            raise OrcamentoEstouradoError(
                f"{self.total_para_o_dsr()} tentativas, orçamento de {self.orcamento}."
            )

    def listar(self, fase: str | None = None) -> list[dict]:
        consulta = "SELECT id, hash, familia, nome, fase, commit_do_codigo, criada_em, execucoes FROM tentativas"
        parametros: tuple = ()
        if fase:
            consulta += " WHERE fase = ?"
            parametros = (fase,)
        with self._conectar() as c:
            return [dict(l) for l in c.execute(consulta + " ORDER BY id", parametros)]
