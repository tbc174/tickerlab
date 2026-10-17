"""As tarefas do servidor no boletim: o que falhou e o que está atrasado.

Lê as marcas que o `rodar-tarefa.sh` grava em `~/estado-tarefas/` (montada só leitura no contêiner):
`NOME.ok` (deu certo, com a hora) e `NOME.falha` (1ª linha: hora e código de saída; 2ª, quando houver,
a linha `FALHAS: ...` da tarefa). É a mesma regra do `conferir-tarefas-casa.sh` (Kuma), contada aqui
para o e-mail: o Kuma diz que algo quebrou, o boletim diz o quê.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

HORAS_MAXIMAS = (
    26  # tarefa diária sem sucesso há mais que isto = atrasada (igual ao Kuma)
)


@dataclass(frozen=True)
class EstadoDaTarefa:
    nome: str
    situacao: str  # "falha", "atrasada" ou "sem_marca"
    quando: str = ""
    motivo: str = ""
    horas: int = 0


@dataclass(frozen=True)
class EstadoDasTarefas:
    disponivel: bool
    total: int = 0  # tarefas com alguma marca
    em_dia: int = 0  # diárias com sucesso recente
    falhas: list[EstadoDaTarefa] = field(default_factory=list)
    atrasadas: list[EstadoDaTarefa] = field(default_factory=list)
    sem_marca: list[EstadoDaTarefa] = field(default_factory=list)


def _falha(arquivo: Path) -> EstadoDaTarefa:
    linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines()
    quando = linhas[0].split(" ")[0] if linhas else ""
    motivo = next(
        (l[len("FALHAS: ") :] for l in linhas[1:] if l.startswith("FALHAS: ")), ""
    )
    return EstadoDaTarefa(arquivo.stem, "falha", quando=quando, motivo=motivo.strip())


def ler_estado(
    pasta: Path, agora: datetime, diarias: Iterable[str]
) -> EstadoDasTarefas:
    if not pasta.is_dir():
        return EstadoDasTarefas(disponivel=False)
    oks = {a.stem: a for a in pasta.glob("*.ok")}
    falhas = {a.stem: _falha(a) for a in sorted(pasta.glob("*.falha"))}
    atrasadas, sem_marca, em_dia = [], [], 0
    for nome in diarias:
        if nome in falhas:
            continue
        if nome not in oks:
            sem_marca.append(EstadoDaTarefa(nome, "sem_marca"))
            continue
        horas = int((agora.timestamp() - oks[nome].stat().st_mtime) // 3600)
        if horas >= HORAS_MAXIMAS:
            atrasadas.append(EstadoDaTarefa(nome, "atrasada", horas=horas))
        else:
            em_dia += 1
    return EstadoDasTarefas(
        disponivel=True,
        total=len(oks.keys() | falhas.keys()),
        em_dia=em_dia,
        falhas=list(falhas.values()),
        atrasadas=sorted(atrasadas, key=lambda e: -e.horas),
        sem_marca=sem_marca,
    )
