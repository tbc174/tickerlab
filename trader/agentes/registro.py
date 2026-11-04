"""O registro dos agentes analistas: uma cadeia de hashes, uma linha por rodada, sem edição.

Cada linha é um JSON com o conteúdo da rodada, a data e a hora do relógio (Brasília), o hash da linha
anterior e o próprio hash (SHA-256 do JSON canônico sem o campo `hash`). Editar, apagar ou trocar a
ordem de qualquer linha quebra a cadeia, e `verificar` aponta onde. Os dossiês ficam numa pasta ao
lado, cada um com o nome igual ao SHA-256 do texto.

A data nunca vem do conteúdo: vem do relógio no momento do registro. O registro recusa uma segunda
rodada no mesmo mês e um relógio anterior ao da última linha. A prova de fora do PC é o hash da ponta,
anotado no dia na nota privada e na Central (critérios, seção 6).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from trader.registro import RAIZ, especificacao_canonica, pasta_da_pesquisa_quant

__all__ = ["RAIZ"]

PASTA_PADRAO = pasta_da_pesquisa_quant() / "agentes"  # fora do Git e das cópias, como o resto da pesquisa
BRASILIA = ZoneInfo("America/Sao_Paulo")
GENESE = "0" * 64  # o "hash anterior" da primeira linha
CAMPOS_DO_REGISTRO = ("data", "registrado_em", "hash_anterior", "hash")


class RegistroAlteradoError(RuntimeError):
    """A cadeia não confere: alguma linha ou algum dossiê mudou depois de registrado."""


class RodadaRecusadaError(ValueError):
    """A rodada não pode entrar (mês repetido, relógio para trás, campo reservado)."""


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def hash_da_linha(linha: dict) -> str:
    return _sha256(
        especificacao_canonica({k: v for k, v in linha.items() if k != "hash"})
    )


class RegistroDeAgentes:
    def __init__(self, pasta: Path = PASTA_PADRAO) -> None:
        self.pasta = pasta
        self.arquivo = pasta / "registro.jsonl"
        self.pasta_dos_dossies = pasta / "dossies"

    # --- dossiês ---

    def guardar_dossie(self, texto: str) -> str:
        codigo = _sha256(texto)
        caminho = self.pasta_dos_dossies / f"{codigo}.md"
        if not caminho.exists():
            self.pasta_dos_dossies.mkdir(parents=True, exist_ok=True)
            caminho.write_bytes(texto.encode("utf-8"))
        return codigo

    def ler_dossie(self, codigo: str) -> str:
        return (self.pasta_dos_dossies / f"{codigo}.md").read_bytes().decode("utf-8")

    # --- a cadeia ---

    def linhas(self) -> list[dict]:
        if not self.arquivo.exists():
            return []
        texto = self.arquivo.read_text(encoding="utf-8")
        return [json.loads(linha) for linha in texto.splitlines() if linha.strip()]

    def ponta(self) -> str:
        linhas = self.linhas()
        return linhas[-1]["hash"] if linhas else GENESE

    def acrescentar(self, conteudo: dict, agora: datetime | None = None) -> dict:
        """Grava a rodada com a data do relógio e devolve a linha gravada."""
        reservados = sorted(set(conteudo) & set(CAMPOS_DO_REGISTRO))
        if reservados:
            raise RodadaRecusadaError(
                f"o registro é quem põe {', '.join(reservados)} (a data vem do relógio)"
            )
        agora = datetime.now(BRASILIA) if agora is None else agora
        if agora.tzinfo is None:
            raise ValueError("o relógio do registro precisa de fuso horário")
        agora = agora.astimezone(BRASILIA)
        self.verificar()
        anteriores = self.linhas()
        if anteriores:
            ultima = anteriores[-1]
            if agora <= datetime.fromisoformat(ultima["registrado_em"]):
                raise RodadaRecusadaError(
                    f"relógio ({agora.isoformat()}) anterior à última rodada ({ultima['registrado_em']})"
                )
            if ultima["data"][:7] == agora.date().isoformat()[:7]:
                raise RodadaRecusadaError(
                    f"já há rodada neste mês ({ultima['data']}): uma por mês"
                )
        linha = {
            **conteudo,
            "data": agora.date().isoformat(),
            "registrado_em": agora.isoformat(),
            "hash_anterior": anteriores[-1]["hash"] if anteriores else GENESE,
        }
        linha["hash"] = hash_da_linha(linha)
        self.pasta.mkdir(parents=True, exist_ok=True)
        with self.arquivo.open("a", encoding="utf-8", newline="\n") as saida:
            saida.write(json.dumps(linha, ensure_ascii=False, sort_keys=True) + "\n")
        return linha

    def verificar(self) -> None:
        """Recalcula a cadeia inteira e cada dossiê citado; falha dizendo onde não confere."""
        anterior = GENESE
        for numero, linha in enumerate(self.linhas(), start=1):
            if linha.get("hash_anterior") != anterior:
                raise RegistroAlteradoError(
                    f"a cadeia quebra na linha {numero}: falta ou sobra uma rodada antes dela"
                )
            if hash_da_linha(linha) != linha.get("hash"):
                raise RegistroAlteradoError(
                    f"a linha {numero} ({linha.get('data')}) mudou depois de registrada"
                )
            for avaliacao in linha.get("avaliacoes", []):
                self._conferir_dossie(numero, avaliacao.get("hash_do_dossie"))
            anterior = linha["hash"]

    def _conferir_dossie(self, numero: int, codigo: str | None) -> None:
        if codigo is None:
            return
        caminho = self.pasta_dos_dossies / f"{codigo}.md"
        if not caminho.exists() or _sha256(self.ler_dossie(codigo)) != codigo:
            raise RegistroAlteradoError(
                f"o dossiê {codigo[:12]} da linha {numero} sumiu ou mudou"
            )
