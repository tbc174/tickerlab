"""Baixa os originais documentais e confere cada um contra o manifesto (plano de 05/11/2026, ADR 0124).

Uso, numa pasta nova e vazia fora do repositório:

    python -I -m scripts.baixar_originais_documentais <pasta>

Cada original do manifesto (`base/conferidas/fatos_documentais_originais.json`) só vale como "conferido"
se veio com a assinatura de PDF, os bytes e o SHA-256 esperados: HTTP 200 não basta. O que não confere vira
pendência em `<acervo>/pendencias/fatos_documentais.jsonl`, nunca fato novo:

- coleta vazia (zero byte) não é sucesso;
- HTML ou outro tipo no lugar do PDF é recusado e apagado;
- PDF com outro SHA-256 ou outro tamanho fica guardado à parte (`divergentes/`), e a pendência leva as duas
  evidências (a esperada e a observada) para uma pessoa decidir.

O conteúdo dos PDFs é dado, nunca instrução: este script não abre nem interpreta o que baixa.
"""

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from base.arquivo.cliente_http import ClienteHttp
from base.arquivo.coleta import conferir_tipo
from base.arquivo.lote_documentais import originais_documentais
from src import acervo

CONFERIDO = "conferido"
PENDENCIA = "pendencia"  # PDF de verdade, mas outro SHA-256 ou outro tamanho
RECUSADO = "recusado"  # não é PDF (HTML de bloqueio, página de erro)
VAZIO = "vazio"  # zero byte: tentativa vazia nunca conta como coleta
FALHOU = "falhou"  # a rede ou o servidor falhou: nada foi guardado
EXTENSAO = ".pdf"
TIPO = "pdf"
TAMANHO_DA_PARTE = 1024 * 1024
TAMANHO_DO_COMECO = 512
ARQUIVO_DAS_PENDENCIAS = Path("pendencias") / "fatos_documentais.jsonl"


class Baixador(Protocol):
    """A parte do `Cliente` do arquivista que este script usa (no teste, um dublê)."""

    def baixar(self, url: str, destino: Path) -> Mapping[str, str]: ...


@dataclass(frozen=True)
class Conferencia:
    fonte: str
    url: str
    situacao: str
    motivo: str
    sha256_esperado: str
    bytes_esperados: int
    sha256_observado: str = ""
    bytes_observados: int = 0
    caminho: str = ""  # onde ficou o que veio (vazio quando nada ficou)


def originais_do_manifesto() -> list[dict[str, Any]]:
    """Os originais conferidos à mão, na ordem do manifesto."""
    return originais_documentais()


def caminho_das_pendencias() -> Path | None:
    """`<acervo>/pendencias/fatos_documentais.jsonl`, ou None com a guarda do acervo desligada."""
    pasta = acervo.pasta_do_acervo()
    return None if pasta is None else pasta / ARQUIVO_DAS_PENDENCIAS


def _medir(caminho: Path) -> tuple[str, int, bytes]:
    """SHA-256, tamanho e começo do arquivo."""
    soma, tamanho, comeco = hashlib.sha256(), 0, b""
    with caminho.open("rb") as arquivo:
        while parte := arquivo.read(TAMANHO_DA_PARTE):
            comeco = comeco or parte[:TAMANHO_DO_COMECO]
            soma.update(parte)
            tamanho += len(parte)
    return soma.hexdigest(), tamanho, comeco


def _mover(temporario: Path, pasta: Path, sha256: str) -> str:
    """Guarda o arquivo pelo SHA-256 (o nome não depende do que a fonte diz)."""
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{sha256}{EXTENSAO}"
    shutil.move(temporario, destino)
    return str(destino)


def _divergencia(original: Mapping[str, Any], sha256: str, tamanho: int) -> str:
    """O motivo da pendência, ou "" se o que veio é o original do manifesto."""
    motivos = []
    if tamanho != original["bytes"]:
        motivos.append(f"bytes: esperados {original['bytes']}, vieram {tamanho}")
    if sha256 != original["sha256"]:
        motivos.append("SHA-256 diferente do manifesto")
    return "; ".join(motivos)


def conferir_original(
    original: Mapping[str, Any], cliente: Baixador, pasta: Path, numero: int
) -> Conferencia:
    """Baixa um original para `pasta` e diz se ele confere com o manifesto."""
    base = {
        "fonte": original["fonte"],
        "url": original["url"],
        "sha256_esperado": original["sha256"],
        "bytes_esperados": original["bytes"],
    }
    temporario = pasta / f"baixando-{numero}.parcial"
    try:
        cliente.baixar(original["url"], temporario)
    except Exception as erro:  # noqa: BLE001 (cada original falha sozinho, com pendência)
        temporario.unlink(missing_ok=True)
        return Conferencia(
            **base, situacao=FALHOU, motivo=f"{type(erro).__name__}: {erro}"
        )
    sha256, tamanho, comeco = _medir(temporario)
    medida = {"sha256_observado": sha256, "bytes_observados": tamanho}
    if tamanho == 0:
        temporario.unlink()
        return Conferencia(
            **base, **medida, situacao=VAZIO, motivo="veio vazio (zero byte)"
        )
    if motivo := conferir_tipo(TIPO, comeco):
        temporario.unlink()
        return Conferencia(**base, **medida, situacao=RECUSADO, motivo=motivo)
    if motivo := _divergencia(original, sha256, tamanho):
        caminho = _mover(temporario, pasta / "divergentes", sha256)
        return Conferencia(
            **base, **medida, situacao=PENDENCIA, motivo=motivo, caminho=caminho
        )
    caminho = _mover(temporario, pasta / "originais", sha256)
    return Conferencia(**base, **medida, situacao=CONFERIDO, motivo="", caminho=caminho)


def _anotar_pendencias(
    conferencias: Sequence[Conferencia], destino: Path | None, agora: datetime
) -> None:
    """Acrescenta ao JSONL uma linha por original que não conferiu (nunca apaga linha antiga)."""
    abertas = [c for c in conferencias if c.situacao != CONFERIDO]
    if destino is None or not abertas:
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("a", encoding="utf-8") as arquivo:
        for conferencia in abertas:
            linha = {**asdict(conferencia), "registrado_em": agora.isoformat()}
            arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")


def baixar(
    cliente: Baixador,
    pasta: Path,
    agora: datetime,
    *,
    originais: Sequence[Mapping[str, Any]] | None = None,
    pendencias: Path | None = None,
) -> list[Conferencia]:
    """Baixa e confere cada original em `pasta` (nova ou vazia); anota as pendências.

    `pendencias` None: `<acervo>/pendencias/fatos_documentais.jsonl`.
    """
    if pasta.exists() and any(pasta.iterdir()):
        raise ValueError(f"a pasta precisa ser nova ou vazia: {pasta}")
    pasta.mkdir(parents=True, exist_ok=True)
    lista = originais_do_manifesto() if originais is None else originais
    conferencias = [
        conferir_original(original, cliente, pasta, numero)
        for numero, original in enumerate(lista)
    ]
    _anotar_pendencias(conferencias, pendencias or caminho_das_pendencias(), agora)
    return conferencias


def main(argumentos: Sequence[str] | None = None) -> int:
    """0 se todos os originais conferiram; 1 se ficou alguma pendência."""
    leitor = argparse.ArgumentParser(
        description="Baixa e confere os originais documentais."
    )
    leitor.add_argument(
        "pasta", type=Path, help="pasta nova e vazia, fora do repositório"
    )
    opcoes = leitor.parse_args(argumentos)
    conferencias = baixar(ClienteHttp(), opcoes.pasta, datetime.now(UTC))
    for conferencia in conferencias:
        print(f"{conferencia.situacao:10} {conferencia.fonte:18} {conferencia.url}")
        if conferencia.motivo:
            print(f"{'':10} {conferencia.motivo}")
    return 0 if all(c.situacao == CONFERIDO for c in conferencias) else 1


if __name__ == "__main__":
    sys.exit(main())
