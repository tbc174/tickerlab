"""Vigia das tarefas: estado de cada tarefa do servidor, pela agenda do crontab (painel das coletas).

    crontab -l | python -m scripts.vigia_das_tarefas --crontab - --marcas ~/estado-tarefas --saida estado.json

Roda de hora em hora nos dois servidores (pelo `vigia-das-coletas.sh`, na imagem, com as marcas
montadas só para leitura). Lê a agenda do próprio crontab (`src/agenda_das_tarefas.py`) e as marcas
`NOME.ok` e `NOME.falha` do `rodar-tarefa.sh`, e escreve um JSON com o estado de cada tarefa
(`src/estado_das_tarefas.py`), que o servidor manda ao Kuma.

Sai sempre com 0 quando consegue escrever o JSON: tarefa falhando é estado, não erro do vigia. O JSON
não leva o texto das marcas (a linha `FALHAS:` pode trazer trecho de página de fonte), só as horas.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from src.agenda_das_tarefas import ler_agenda
from src.estado_das_tarefas import Marca, estado_das_tarefas

SUFIXO_DO_SUCESSO = ".ok"
SUFIXO_DA_FALHA = ".falha"


def main(argv: list[str] | None = None) -> int:
    """Escreve o estado das tarefas em `--saida` e devolve 0."""
    argumentos = _argumentos().parse_args(argv)
    texto_do_crontab = (
        sys.stdin.read()
        if argumentos.crontab == "-"
        else Path(argumentos.crontab).read_text(encoding="utf-8")
    )
    agora = (
        datetime.fromisoformat(argumentos.agora)
        if argumentos.agora
        else datetime.now(UTC)
    )
    estados = estado_das_tarefas(
        ler_agenda(texto_do_crontab), ler_marcas(Path(argumentos.marcas)), agora
    )
    conteudo = {
        "gerado_em": agora.isoformat(),
        "tarefas": [estado.como_dicionario() for estado in estados],
    }
    _escrever(
        Path(argumentos.saida), json.dumps(conteudo, ensure_ascii=False, indent=1)
    )
    return 0


def ler_marcas(pasta: Path) -> dict[str, Marca]:
    """Devolve as marcas `.ok` e `.falha` da pasta do `rodar-tarefa.sh`, por nome de tarefa."""
    horas: dict[str, dict[str, datetime]] = {}
    for arquivo in pasta.iterdir():
        if arquivo.suffix in (SUFIXO_DO_SUCESSO, SUFIXO_DA_FALHA) and arquivo.is_file():
            horas.setdefault(arquivo.stem, {})[arquivo.suffix] = hora_da_marca(arquivo)
    return {
        nome: Marca(
            ok_em=marca.get(SUFIXO_DO_SUCESSO), falha_em=marca.get(SUFIXO_DA_FALHA)
        )
        for nome, marca in horas.items()
    }


def hora_da_marca(arquivo: Path) -> datetime:
    """Devolve a hora gravada na 1ª palavra da marca (`date -Is`) ou, sem ela, a hora do arquivo."""
    primeira_linha = arquivo.read_text(encoding="utf-8", errors="replace").split(
        "\n", 1
    )[0]
    palavras = primeira_linha.split()
    try:
        hora = datetime.fromisoformat(palavras[0]) if palavras else None
    except ValueError:
        hora = None
    if hora is None or hora.tzinfo is None:
        return datetime.fromtimestamp(arquivo.stat().st_mtime, tz=UTC)
    return hora


def _escrever(destino: Path, texto: str) -> None:
    # escreve ao lado e troca de uma vez: quem lê o JSON nunca pega um arquivo pela metade
    provisorio = destino.with_name(destino.name + ".novo")
    provisorio.write_text(texto + "\n", encoding="utf-8")
    provisorio.replace(destino)


def _argumentos() -> argparse.ArgumentParser:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "--crontab", required=True, help="texto do crontab -l ('-' = entrada)"
    )
    argumentos.add_argument("--marcas", required=True, help="pasta ~/estado-tarefas")
    argumentos.add_argument("--saida", required=True, help="arquivo JSON do estado")
    argumentos.add_argument("--agora", help=argparse.SUPPRESS)  # só para os testes
    return argumentos


if __name__ == "__main__":
    sys.exit(main())
