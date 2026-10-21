"""Vigia das tarefas: estado de cada tarefa do servidor, pela agenda do crontab (painel das coletas).

    crontab -l | python -m scripts.vigia_das_tarefas --crontab - --marcas ~/estado-tarefas --saida estado.json
        [--servidor casa --resumos ~/resumos-das-falhas]

Roda de hora em hora nos dois servidores (pelo `vigia-das-coletas.sh`, na imagem, com as marcas
montadas só para leitura). Lê a agenda do próprio crontab (`src/agenda_das_tarefas.py`) e as marcas
`NOME.ok` e `NOME.falha` do `rodar-tarefa.sh`, e escreve um JSON com o estado de cada tarefa
(`src/estado_das_tarefas.py`), que o servidor manda ao Kuma.

Sai sempre com 0 quando consegue escrever o JSON: tarefa falhando é estado, não erro do vigia. O JSON
não leva o texto das marcas (a linha `FALHAS:` pode trazer trecho de página de fonte), só as horas.

Com `--resumos`, escreve também `<tarefa>.json` para cada tarefa falhando ou atrasada: o resumo da
falha de `src/classificar_falha.py` (tipo de uma lista fechada, sem texto do log), que vai para o
repositório de estado lido pela equipe de conserto. O log de cada tarefa é o que o crontab passa ao
`rodar-tarefa.sh`; no contêiner, a pasta pessoal é montada no mesmo caminho, só para leitura.
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from src.agenda_das_tarefas import TarefaAgendada, ler_agenda
from src.classificar_falha import Classificacao, ResumoDaFalha, classificar
from src.estado_das_tarefas import EstadoDaTarefa, Marca, estado_das_tarefas

SUFIXO_DO_SUCESSO = ".ok"
SUFIXO_DA_FALHA = ".falha"
SITUACOES_COM_RESUMO = ("falhou", "atrasada")
# a cauda do log que o classificador lê: o bastante para o traceback da última rodada
BYTES_DA_CAUDA_DO_LOG = 64 * 1024
BYTES_DA_MARCA = 2 * 1024
CODIGO_NA_MARCA = re.compile(r"saída (\d{1,3})\b")


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
    agenda = ler_agenda(texto_do_crontab)
    estados = estado_das_tarefas(agenda, ler_marcas(Path(argumentos.marcas)), agora)
    conteudo = {
        "gerado_em": agora.isoformat(),
        "tarefas": [estado.como_dicionario() for estado in estados],
    }
    _escrever(
        Path(argumentos.saida), json.dumps(conteudo, ensure_ascii=False, indent=1)
    )
    if argumentos.resumos:
        escrever_resumos(
            estados,
            {tarefa.nome: tarefa for tarefa in agenda},
            Path(argumentos.marcas),
            argumentos.servidor,
            Path(argumentos.resumos),
        )
    return 0


def escrever_resumos(
    estados: list[EstadoDaTarefa],
    agenda: dict[str, TarefaAgendada],
    marcas: Path,
    servidor: str,
    pasta: Path,
) -> None:
    """Escreve `<tarefa>.json` com o resumo de cada tarefa falhando ou atrasada; apaga o das que voltaram.

    O resumo é conferido (`src/classificar_falha.validar`) antes de ir para o disco: o que não passa
    não é escrito.
    """
    for estado in estados:
        destino = pasta / f"{estado.nome}.json"
        if estado.situacao == "ok":
            destino.unlink(missing_ok=True)
        if estado.situacao not in SITUACOES_COM_RESUMO:
            continue
        resumo = _resumo(estado, agenda.get(estado.nome), marcas, servidor)
        if resumo:
            _escrever(destino, json.dumps(resumo.como_dicionario(), ensure_ascii=False))


def _resumo(
    estado: EstadoDaTarefa, tarefa: TarefaAgendada | None, marcas: Path, servidor: str
) -> ResumoDaFalha | None:
    if estado.situacao == "atrasada" and estado.vence_em:
        hora, codigo = estado.vence_em, None
        classificacao = Classificacao("atrasada", None, None)
    elif estado.ultima_falha:
        texto_da_marca = _ler_o_fim(
            marcas / f"{estado.nome}{SUFIXO_DA_FALHA}", BYTES_DA_MARCA
        )
        achado = CODIGO_NA_MARCA.search(texto_da_marca)
        codigo = int(achado.group(1)) if achado else None
        cauda = (
            _ler_o_fim(Path(tarefa.log), BYTES_DA_CAUDA_DO_LOG)
            if tarefa and tarefa.log
            else ""
        )
        # a marca vem por último: a linha "FALHAS:" e o "saída trava" são o fim da rodada
        classificacao = classificar(f"{cauda}\n{texto_da_marca}", codigo or 0)
        hora = estado.ultima_falha
    else:
        return None
    try:
        return ResumoDaFalha.montar(
            servidor, estado.nome, hora.isoformat(), codigo, classificacao
        )
    except ValueError:
        print(f"{estado.nome}: resumo fora do padrão, não escrito", file=sys.stderr)
        return None


def _ler_o_fim(arquivo: Path, maximo_de_bytes: int) -> str:
    """Devolve os últimos bytes de um arquivo como texto, ou "" se ele não existe ou não abre."""
    try:
        with arquivo.open("rb") as aberto:
            aberto.seek(max(0, arquivo.stat().st_size - maximo_de_bytes))
            return aberto.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


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
    argumentos.add_argument(
        "--servidor", default="servidor", help="nome curto: vps ou casa"
    )
    argumentos.add_argument(
        "--resumos", help="pasta dos resumos das falhas (um JSON por tarefa)"
    )
    argumentos.add_argument("--agora", help=argparse.SUPPRESS)  # só para os testes
    return argumentos


if __name__ == "__main__":
    sys.exit(main())
