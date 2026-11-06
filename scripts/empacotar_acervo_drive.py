#!/usr/bin/env python3
"""Backup do acervo no Drive em pacotes .tar cifrados (ADR 0123, Emenda 1; linha 251 da fila).

Por que pacotes: o `client_id` compartilhado do rclone deixa o Google limitar a ~14 arquivos pequenos por minuto,
e o acervo tem 60 mil arquivos. Em pacotes, o que o Drive vê são centenas de objetos grandes.

Como funciona (só biblioteca padrão, roda na VM do servidor de casa):

- `subir`: lê a origem (nunca escreve nela), junta os arquivos novos ou mudados em pacotes .tar por fonte e período
  (`bruto/<fonte>/<ano>`; no ano corrente, por mês) e manda cada um para o Drive com `rclone rcat` (sem arquivo
  temporário), pelo remoto `crypt` (nomes e conteúdo cifrados). Cada pacote traz um **índice** (`indices/...jsonl`,
  cifrado igual): caminho, bytes, sha256 e posição de cada arquivo dentro do tar.
- **Pacote é imutável:** o nome leva a data e a hora da subida. Período fechado sobe uma vez só; o que chega depois
  (ou muda) vai num pacote novo só com esses arquivos (por dia, na prática). Nada é regravado, movido ou apagado no
  Drive: este arquivo não tem `sync`, `delete`, `move` nem `purge`.
- O estado do que já subiu fica num arquivo local (`pacotes-estado.jsonl`) e pode ser refeito dos índices do Drive
  (`reconstruir-estado`).
- Fontes com nome de pessoa ou só de uso interno, `restrito/` e a sala de dados **nunca entram**, em qualquer
  profundidade (há teste que compara a lista com `acervo.FONTES_COM_PESSOA` e `coletas.FONTES_SO_INTERNAS`).
- `conferir`: contagem e bytes origem × índices do Drive, tamanho de cada pacote no Drive; com `--completo`, relê
  todos os pacotes do Drive e confere o sha256 de cada arquivo contra o índice e contra a origem.
- `amostra`: restaura pacotes inteiros e arquivos avulsos (pela posição no índice, sem baixar o pacote) e confere o sha256.

Variáveis (todas têm padrão): ACERVO, PASTA_DE_BACKUPS, RCLONE, RCLONE_CONFIG, REMOTO, ESTADO, LOG, BWLIMIT,
PARALELO, MIN_IDADE, LIMITE_PACOTE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shlex
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, BinaryIO

NOMES_PROIBIDOS = ("restrito", "tickerlab-sala")
# Fontes cujo original traz nome de pessoa ou é só de uso interno: `acervo.FONTES_COM_PESSOA` e
# `coletas.FONTES_SO_INTERNAS`. Enquanto o `mover_acervo_restrito` não rodou ainda há cópia delas em `bruto/`.
# O que sobe ao Drive nunca mais sai (LGPD): elas não sobem de jeito nenhum.
FONTES_SO_NO_RESTRITO = (
    "rfb-cnpj",
    "pgfn-divida",
    "mte-lista-suja",
    "ibama-autos",
    "ibama-embargos",
    "cvm-enet-notas",
    "antt-autos-de-transito",
    "djen-partes",
    "djen-processos",
    "datajud",
)
PROIBIDOS = frozenset(NOMES_PROIBIDOS + FONTES_SO_NO_RESTRITO)

UM_GIB = 2**30
LIMITE_PACOTE_PADRAO = 20 * UM_GIB
SEGUNDOS_MIN_IDADE_SUBIDA = 5 * 60
SEGUNDOS_MIN_IDADE_CONFERENCIA = 7 * 3600
BLOCO_DE_LEITURA = 1024 * 1024
TAMANHO_MAXIMO_DA_AMOSTRA = 300 * 1024 * 1024
ARQUIVOS_AVULSOS_NA_AMOSTRA = 8
# Opções do envio de um pacote: lote grande (poucas requisições), para no limite diário do Drive, sem esperar à toa.
OPCOES_DO_ENVIO = (
    "--drive-chunk-size",
    "128M",
    "--drive-stop-on-upload-limit",
    "--low-level-retries",
    "10",
    "--timeout",
    "2m",
    "--contimeout",
    "30s",
)


@dataclass(frozen=True)
class Parte:
    """Uma pasta da origem que vira pacotes."""

    nome: str  # nome no estado e no relatório
    raiz: Path  # pasta onde ela mora
    sub: str  # caminho dentro da raiz (vira o prefixo dos arquivos no tar)
    modo: str  # "fonte-ano" | "subpasta" | "unico"
    destino: str  # pasta no Drive, dentro de pacotes/ e de indices/


@dataclass
class Configuracao:
    acervo: Path = Path("/mnt/dados/tickerlab-acervo")
    pasta_de_backups: Path = Path("/mnt/dados/backups")
    rclone: list[str] = field(
        default_factory=lambda: [str(Path.home() / "bin" / "rclone")]
    )
    remoto: str = "cripto"
    estado: Path = Path.home() / ".config/tickerlab/backup-drive/pacotes-estado.jsonl"
    log: Path | None = None
    bwlimit: str = "07:00,2M 23:00,off"
    paralelo: int = 2
    min_idade: float = SEGUNDOS_MIN_IDADE_SUBIDA
    limite_pacote: int = LIMITE_PACOTE_PADRAO
    partes: list[Parte] | None = None

    def lista_de_partes(self) -> list[Parte]:
        """Primeiro o que é pequeno e insubstituível (backups); o `bruto`, que é o grosso, por último."""
        if self.partes is not None:
            return self.partes
        return [
            Parte(
                "backups-tickerlab-pc",
                self.pasta_de_backups,
                "tickerlab-pc",
                "subpasta",
                "backups/tickerlab-pc",
            ),
            Parte(
                "backups-tickerlab-acervo",
                self.pasta_de_backups,
                "tickerlab-acervo",
                "subpasta",
                "backups/tickerlab-acervo",
            ),
            Parte(
                "acervo-manifesto",
                self.acervo,
                "manifesto",
                "unico",
                "acervo/manifesto",
            ),
            Parte("acervo-ancoras", self.acervo, "ancoras", "unico", "acervo/ancoras"),
            Parte("acervo-bruto", self.acervo, "bruto", "fonte-ano", "acervo/bruto"),
        ]


def configuracao_do_ambiente() -> Configuracao:
    """Lê as variáveis de ambiente; o que não vier fica no padrão."""
    cfg = Configuracao()
    env = os.environ
    if env.get("ACERVO"):
        cfg.acervo = Path(env["ACERVO"])
    if env.get("PASTA_DE_BACKUPS"):
        cfg.pasta_de_backups = Path(env["PASTA_DE_BACKUPS"])
    if env.get("RCLONE"):
        cfg.rclone = shlex.split(env["RCLONE"])
    cfg.remoto = env.get("REMOTO", cfg.remoto)
    if env.get("ESTADO"):
        cfg.estado = Path(env["ESTADO"])
    cfg.log = (
        Path(env["LOG"])
        if env.get("LOG")
        else Path.home() / "logs" / "backup-acervo-drive.log"
    )
    cfg.bwlimit = env.get("BWLIMIT", cfg.bwlimit)
    cfg.paralelo = int(env.get("PARALELO", cfg.paralelo))
    if env.get("MIN_IDADE"):
        cfg.min_idade = float(env["MIN_IDADE"])
    if env.get("LIMITE_PACOTE"):
        cfg.limite_pacote = int(env["LIMITE_PACOTE"])
    return cfg


# ---------- origem: o que pode subir ----------


def origem_permitida(caminho: Path | str) -> bool:
    """Recusa origem que tenha um nome proibido (ou `.`/`..`) em qualquer pedaço do caminho."""
    pedacos = str(caminho).replace("\\", "/").split("/")
    return not any(p in PROIBIDOS or p in (".", "..") for p in pedacos if p)


def listar(
    parte: Parte, min_idade: float, agora: float | None = None
) -> Iterator[tuple[tuple[str, ...], int, int]]:
    """Arquivos comuns da parte, `(caminho relativo, bytes, mtime_ns)`, sem seguir link e sem pastas proibidas.

    Só entram arquivos com mais de `min_idade` segundos (o que ainda está sendo gravado fica para a próxima).
    """
    base = parte.raiz / parte.sub
    if not origem_permitida(base):
        raise ValueError(f"origem recusada: {base} tem nome proibido")
    if not base.is_dir():
        raise FileNotFoundError(f"falta a origem de {parte.nome}")
    agora = time.time() if agora is None else agora
    for pasta, subpastas, nomes in os.walk(base):
        subpastas[:] = sorted(d for d in subpastas if d not in PROIBIDOS)
        for nome in sorted(nomes):
            caminho = os.path.join(pasta, nome)
            info = os.lstat(caminho)
            if not stat.S_ISREG(info.st_mode) or agora - info.st_mtime < min_idade:
                continue
            yield Path(caminho).relative_to(base).parts, info.st_size, info.st_mtime_ns


def chave_do_grupo(
    parte: Parte, rel: tuple[str, ...], mtime_ns: int, ano_atual: int
) -> str:
    """Pasta do pacote no Drive: fonte e ano; no ano corrente, também o mês (pacotes menores, o período ainda corre)."""
    if parte.modo == "fonte-ano":
        if len(rel) < 3:
            return f"{rel[0]}/_raiz" if len(rel) == 2 else "_raiz"
        fonte, ano = rel[0], rel[1]
        if ano == str(ano_atual):
            return f"{fonte}/{ano}-{datetime.fromtimestamp(mtime_ns / 1e9, tz=UTC):%m}"
        return f"{fonte}/{ano}"
    if parte.modo == "subpasta":
        return rel[0] if len(rel) > 1 else "_raiz"
    return "_tudo"


Arquivo = tuple[tuple[str, ...], int, int]
Estado = dict[tuple[str, str], tuple[int, int]]


@dataclass
class Pacote:
    parte: Parte
    chave: str
    arquivos: list[Arquivo]
    sufixo: str = ""

    @property
    def bytes(self) -> int:
        return sum(a[1] for a in self.arquivos)


def planejar(
    parte: Parte, estado: Estado, min_idade: float, limite: int, ano_atual: int
) -> list[Pacote]:
    """Agrupa o que ainda não subiu (ou mudou) em pacotes de no máximo `limite` bytes."""
    pendentes: dict[str, list[Arquivo]] = defaultdict(list)
    for rel, tamanho, mtime in listar(parte, min_idade):
        if estado.get((parte.nome, "/".join(rel))) == (tamanho, mtime):
            continue
        pendentes[chave_do_grupo(parte, rel, mtime, ano_atual)].append(
            (rel, tamanho, mtime)
        )
    pacotes = []
    for chave in sorted(pendentes):
        lotes: list[list[Arquivo]] = [[]]
        total = 0
        for arq in pendentes[chave]:
            if lotes[-1] and total + arq[1] > limite:
                lotes.append([])
                total = 0
            lotes[-1].append(arq)
            total += arq[1]
        for n, lote in enumerate(lotes, start=1):
            pacotes.append(
                Pacote(parte, chave, lote, "" if len(lotes) == 1 else f"-p{n}")
            )
    return pacotes


# ---------- estado ----------


def carregar_estado(caminho: Path) -> Estado:
    estado: Estado = {}
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                d = json.loads(linha)
                estado[(d["parte"], d["rel"])] = (d["b"], d["m"])
    return estado


def gravar_estado(
    caminho: Path, parte: Parte, entradas: list[dict[str, Any]], pacote: str
) -> None:
    """Anota no estado o que acabou de subir (só depois de pacote e índice conferidos no Drive)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    corte = (
        len(parte.sub) + 1
    )  # o membro do tar leva o prefixo `sub/`; o estado guarda o relativo à parte
    with open(caminho, "a", encoding="utf-8") as saida:
        saida.writelines(
            json.dumps(
                {
                    "parte": parte.nome,
                    "rel": e["p"][corte:],
                    "b": e["b"],
                    "m": e["m"],
                    "pacote": pacote,
                },
                ensure_ascii=False,
            )
            + "\n"
            for e in entradas
        )
    os.chmod(caminho, 0o600)


# ---------- rclone ----------


def registrar(cfg: Configuracao, texto: str) -> None:
    linha = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {texto}"
    print(linha, flush=True)
    if cfg.log:
        cfg.log.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg.log, "a", encoding="utf-8") as saida:
            saida.write(linha + "\n")


def comando(cfg: Configuracao, *args: str) -> list[str]:
    extras = ["--log-file", str(cfg.log), "--log-level", "NOTICE"] if cfg.log else []
    return [*cfg.rclone, *args, *extras]


def listar_drive(cfg: Configuracao, pasta: str) -> list[dict[str, Any]]:
    """Arquivos de uma pasta do Drive (decifrados pelo crypt: o tamanho é o do conteúdo original)."""
    try:
        saida = subprocess.run(
            [*cfg.rclone, "lsjson", "-R", "--files-only", f"{cfg.remoto}:{pasta}"],
            capture_output=True,
            check=True,
        ).stdout
        return list(json.loads(saida or b"[]"))
    except subprocess.CalledProcessError:
        return []


class Contador:
    """Escreve no destino e conta os bytes."""

    def __init__(self, destino: BinaryIO) -> None:
        self.destino = destino
        self.n = 0

    def write(self, dados: bytes) -> int:
        self.destino.write(dados)
        self.n += len(dados)
        return len(dados)

    def flush(self) -> None:
        self.destino.flush()


class LeitorComHash:
    """Lê o arquivo e calcula o sha256 do que passou."""

    def __init__(self, arquivo: BinaryIO) -> None:
        self.arquivo = arquivo
        self.hash = hashlib.sha256()
        self.n = 0

    def read(self, tamanho: int = -1) -> bytes:
        dados = self.arquivo.read(tamanho)
        self.hash.update(dados)
        self.n += len(dados)
        return dados


def montar_pacote(
    pacote: Pacote, destino: BinaryIO
) -> tuple[list[dict[str, Any]], int]:
    """Escreve o tar do pacote em `destino`; devolve o índice e o total de bytes do tar."""
    entradas: list[dict[str, Any]] = []
    contador = Contador(destino)
    base = pacote.parte.raiz / pacote.parte.sub
    with tarfile.open(fileobj=contador, mode="w|") as tar:  # type: ignore[call-overload]
        for rel, _tamanho, _mtime in pacote.arquivos:
            membro = "/".join((pacote.parte.sub, *rel))
            with open(base.joinpath(*rel), "rb") as arquivo:
                info = os.fstat(arquivo.fileno())
                ti = tarfile.TarInfo(membro)
                ti.size, ti.mtime, ti.mode = info.st_size, int(info.st_mtime), 0o644
                cabecalho = len(ti.tobuf(tar.format, tar.encoding, tar.errors))
                inicio_dos_dados = tar.offset + cabecalho
                leitor = LeitorComHash(arquivo)
                tar.addfile(ti, leitor)  # type: ignore[arg-type]
            entradas.append(
                {
                    "p": membro,
                    "b": info.st_size,
                    "m": info.st_mtime_ns,
                    "sha256": leitor.hash.hexdigest(),
                    "o": inicio_dos_dados,
                }
            )
    return entradas, contador.n


def nome_no_drive(pacote: Pacote, carimbo: str) -> str:
    return f"{pacote.parte.destino}/{pacote.chave}/{carimbo}{pacote.sufixo}"


TENTATIVAS_DA_CONFERENCIA = 4
ESPERA_DA_CONFERENCIA = 5.0


def conferir_tamanho(cfg: Configuracao, pasta: str, nome: str, esperado: int) -> None:
    """Confere o tamanho no Drive; a listagem do Drive pode atrasar um pouco, então tenta algumas vezes."""
    for tentativa in range(TENTATIVAS_DA_CONFERENCIA):
        for item in listar_drive(cfg, pasta):
            if item["Path"] == nome or item["Name"] == nome:
                if item["Size"] != esperado:
                    raise RuntimeError(
                        f"{pasta}/{nome}: {item['Size']} bytes no Drive, esperado {esperado}"
                    )
                return
        if tentativa < TENTATIVAS_DA_CONFERENCIA - 1:
            time.sleep(ESPERA_DA_CONFERENCIA)
    raise RuntimeError(f"{pasta}/{nome} não apareceu no Drive")


def criar_pastas(cfg: Configuracao, pacotes: list[Pacote]) -> None:
    """Cria, uma de cada vez, as pastas-mãe dos pacotes e dos índices antes de subir em paralelo.

    O Drive aceita duas pastas com o mesmo nome: dois envios paralelos que criam `pacotes/` ao mesmo tempo
    deixam duas e o rclone só enxerga uma (06/11: o pacote do manifesto "sumiu" assim). Aqui nascem as
    pastas compartilhadas; a pasta de cada grupo (fonte) é criada pelo único envio que a usa (ver `grupos`).
    """
    maes: set[str] = set()
    for raiz in ("pacotes", "indices"):
        for p in pacotes:
            partes = f"{raiz}/{p.parte.destino}".split("/")
            maes.update("/".join(partes[:n]) for n in range(1, len(partes) + 1))
    for pasta in sorted(maes, key=lambda m: (m.count("/"), m)):
        resultado = subprocess.run(
            comando(cfg, "mkdir", f"{cfg.remoto}:{pasta}"),
            capture_output=True,
            check=False,
        )
        if resultado.returncode != 0:
            raise RuntimeError(f"rclone mkdir falhou em {pasta}")


def grupos(pacotes: list[Pacote]) -> list[list[Pacote]]:
    """Pacotes que dividem a mesma pasta no Drive (a mesma fonte); cada grupo sobe em sequência, por um só envio."""
    por_grupo: dict[str, list[Pacote]] = defaultdict(list)
    for p in pacotes:
        por_grupo[f"{p.parte.destino}/{p.chave.split('/')[0]}"].append(p)
    return list(por_grupo.values())


def subir_pacote(
    cfg: Configuracao, pacote: Pacote, carimbo: str
) -> list[dict[str, Any]]:
    """Manda um pacote e o índice dele; só devolve quando os dois estão no Drive com o tamanho certo."""
    nome = nome_no_drive(pacote, carimbo)
    alvo_tar, alvo_indice = f"pacotes/{nome}.tar", f"indices/{nome}.jsonl"
    envio = subprocess.Popen(
        comando(
            cfg,
            "rcat",
            f"{cfg.remoto}:{alvo_tar}",
            "--bwlimit",
            cfg.bwlimit,
            *OPCOES_DO_ENVIO,
        ),
        stdin=subprocess.PIPE,
    )
    assert envio.stdin is not None
    try:
        entradas, total = montar_pacote(pacote, envio.stdin)
    except BaseException:
        envio.kill()  # corta o fluxo sem fechar: um envio pela metade nunca vira objeto completo no Drive
        envio.wait()
        raise
    envio.stdin.close()
    if envio.wait() != 0:
        raise RuntimeError(
            f"rclone rcat falhou em {alvo_tar} (código {envio.returncode})"
        )
    cabecalho = {
        "pacote": f"pacotes/{nome}.tar",
        "tar_bytes": total,
        "arquivos": len(entradas),
        "criado": carimbo,
        "parte": pacote.parte.nome,
    }
    indice = (
        "\n".join(json.dumps(x, ensure_ascii=False) for x in [cabecalho, *entradas])
        + "\n"
    )
    resultado = subprocess.run(
        comando(cfg, "rcat", f"{cfg.remoto}:{alvo_indice}", *OPCOES_DO_ENVIO),
        input=indice.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"rclone rcat falhou no índice {alvo_indice}")
    pasta, _, arquivo = alvo_tar.rpartition("/")
    conferir_tamanho(cfg, pasta, arquivo, total)
    pasta_i, _, arquivo_i = alvo_indice.rpartition("/")
    conferir_tamanho(cfg, pasta_i, arquivo_i, len(indice.encode("utf-8")))
    return entradas


# ---------- subir ----------


def subir(
    cfg: Configuracao, agora: datetime | None = None, simular: bool = False
) -> int:
    agora = agora or datetime.now().astimezone()
    carimbo = agora.strftime("%Y-%m-%d_%H%M%S")
    estado = carregar_estado(cfg.estado)
    falhas: list[str] = []
    pacotes: list[Pacote] = []
    for parte in cfg.lista_de_partes():
        try:
            novos = planejar(
                parte, estado, cfg.min_idade, cfg.limite_pacote, agora.year
            )
        except (FileNotFoundError, ValueError) as erro:
            registrar(cfg, f"FALTA ou RECUSADO ({parte.nome}): {erro}")
            falhas.append(f"pacotes-{parte.nome}")
            continue
        if not novos and not any(k[0] == parte.nome for k in estado):
            registrar(
                cfg, f"parte vazia: {parte.nome} não tem nenhum arquivo para subir"
            )
            falhas.append(f"pacotes-{parte.nome}-vazia")
        pacotes.extend(novos)
    total_bytes = sum(p.bytes for p in pacotes)
    registrar(
        cfg,
        f"pacotes a subir: {len(pacotes)} ({sum(len(p.arquivos) for p in pacotes)} arquivos, "
        f"{total_bytes} bytes)",
    )
    if simular:
        for p in pacotes:
            print(
                f"{nome_no_drive(p, carimbo)}.tar {len(p.arquivos)} arquivos {p.bytes} bytes"
            )
        return 1 if falhas else 0
    if pacotes:
        try:
            criar_pastas(cfg, pacotes)
        except RuntimeError as erro:
            registrar(cfg, f"FALHOU: {erro}")
            print("FALHAS: pacotes-pastas")
            return 1
    trava = threading.Lock()
    enviados = 0

    def trabalhar(pacote: Pacote) -> None:
        nonlocal enviados
        entradas = subir_pacote(cfg, pacote, carimbo)
        with trava:
            gravar_estado(
                cfg.estado, pacote.parte, entradas, nome_no_drive(pacote, carimbo)
            )
            enviados += 1
        registrar(
            cfg,
            f"fim: {nome_no_drive(pacote, carimbo)} ({len(entradas)} arquivos, {pacote.bytes} bytes)",
        )

    def trabalhar_grupo(grupo: list[Pacote]) -> None:
        for pacote in (
            grupo
        ):  # em sequência: uma pasta nova do Drive nunca é criada por dois envios
            try:
                trabalhar(pacote)
            except Exception as erro:  # noqa: BLE001 - um pacote que falha não derruba os outros
                registrar(cfg, f"FALHOU: {nome_no_drive(pacote, carimbo)}: {erro}")
                with trava:
                    falhas.append(f"pacotes-{pacote.parte.nome}")

    with ThreadPoolExecutor(max_workers=max(1, cfg.paralelo)) as piscina:
        list(piscina.map(trabalhar_grupo, grupos(pacotes)))
    registrar(cfg, f"pacotes enviados: {enviados} de {len(pacotes)}")
    if falhas:
        print("FALHAS: " + " ".join(sorted(set(falhas))))
        return 1
    registrar(cfg, "pacotes do acervo no Drive: tudo certo")
    return 0


# ---------- índices no Drive ----------


def ler_indices(
    cfg: Configuracao, parte: Parte
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Todos os índices de uma parte, direto do Drive: `(cabeçalho, entradas)` de cada pacote."""
    pasta = f"indices/{parte.destino}"
    caminhos = [
        f["Path"] for f in listar_drive(cfg, pasta) if f["Path"].endswith(".jsonl")
    ]

    def ler(caminho: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        bruto = subprocess.run(
            [*cfg.rclone, "cat", f"{cfg.remoto}:{pasta}/{caminho}"],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
        linhas = [json.loads(x) for x in bruto.splitlines() if x.strip()]
        return linhas[0], linhas[1:]

    with ThreadPoolExecutor(max_workers=4) as piscina:
        return list(piscina.map(ler, caminhos))


def reconstruir_estado(cfg: Configuracao) -> int:
    """Refaz o arquivo de estado a partir dos índices do Drive (se o do servidor se perder)."""
    destino = cfg.estado.with_suffix(".reconstruido")
    destino.unlink(missing_ok=True)
    for parte in cfg.lista_de_partes():
        for cabecalho, entradas in ler_indices(cfg, parte):
            gravar_estado(destino, parte, entradas, cabecalho["pacote"])
    print(
        f"estado refeito em {destino}; confira e troque pelo {cfg.estado} se estiver certo"
    )
    return 0


def ultimas_versoes(
    indices: list[tuple[dict[str, Any], list[dict[str, Any]]]],
) -> dict[str, dict[str, Any]]:
    """Por caminho, a entrada do pacote mais novo (o carimbo no nome ordena no tempo)."""
    mais_novas: dict[str, dict[str, Any]] = {}
    for cabecalho, entradas in sorted(
        indices, key=lambda x: x[0]["pacote"].rsplit("/", 1)[-1]
    ):
        for e in entradas:
            mais_novas[e["p"]] = {**e, "pacote": cabecalho["pacote"]}
    return mais_novas


# ---------- conferir ----------


def sha256_do_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(BLOCO_DE_LEITURA), b""):
            h.update(bloco)
    return h.hexdigest()


def reler_pacote(
    cfg: Configuracao,
    parte: Parte,
    cabecalho: dict[str, Any],
    entradas: list[dict[str, Any]],
) -> list[str]:
    """Baixa o pacote inteiro do Drive e confere cada arquivo (índice e origem). Devolve os problemas."""
    problemas: list[str] = []
    esperado = {e["p"]: e for e in entradas}
    visto: set[str] = set()
    leitor = subprocess.Popen(
        [*cfg.rclone, "cat", f"{cfg.remoto}:{cabecalho['pacote']}"],
        stdout=subprocess.PIPE,
    )
    assert leitor.stdout is not None
    try:
        with tarfile.open(fileobj=leitor.stdout, mode="r|") as tar:  # type: ignore[call-overload]
            for membro in tar:
                if not membro.isfile():
                    continue
                e = esperado.get(membro.name)
                dados = tar.extractfile(membro)
                if e is None or dados is None:
                    problemas.append(f"{membro.name}: no pacote mas fora do índice")
                    continue
                visto.add(membro.name)
                h = hashlib.sha256()
                for bloco in iter(partial(dados.read, BLOCO_DE_LEITURA), b""):
                    h.update(bloco)
                if h.hexdigest() != e["sha256"] or membro.size != e["b"]:
                    problemas.append(f"{membro.name}: o Drive não bate com o índice")
                    continue
                origem = parte.raiz / e["p"]
                if origem.exists():
                    info = origem.stat()
                    if (
                        info.st_size == e["b"]
                        and info.st_mtime_ns == e["m"]
                        and sha256_do_arquivo(origem) != e["sha256"]
                    ):
                        problemas.append(
                            f"{membro.name}: a origem não bate com o índice"
                        )
    finally:
        leitor.stdout.close()
        if leitor.wait() != 0:
            problemas.append(
                f"{cabecalho['pacote']}: rclone cat saiu com {leitor.returncode}"
            )
    problemas.extend(
        f"{faltou}: está no índice mas não veio no pacote"
        for faltou in sorted(set(esperado) - visto)
    )
    return problemas


def conferir(cfg: Configuracao, completo: bool = False) -> int:
    """Origem × Drive por parte. Passa quando toda a origem (com mais de `min_idade`) está nos índices do Drive."""
    falhas: list[str] = []
    total_origem = [0, 0]
    total_drive = [0, 0]
    todos: list[tuple[Parte, dict[str, Any], list[dict[str, Any]]]] = []
    for parte in cfg.lista_de_partes():
        try:
            origem = list(listar(parte, cfg.min_idade))
        except (FileNotFoundError, ValueError) as erro:
            print(f"{parte.nome}: {erro}")
            falhas.append(parte.nome)
            continue
        indices = ler_indices(cfg, parte)
        versoes = ultimas_versoes(indices)
        ausentes = diferentes = 0
        for rel, tamanho, mtime in origem:
            e = versoes.get("/".join((parte.sub, *rel)))
            if e is None:
                ausentes += 1
            elif (e["b"], e["m"]) != (tamanho, mtime):
                diferentes += 1
        no_drive = [v for v in versoes.values()]
        bytes_origem = sum(a[1] for a in origem)
        bytes_drive = sum(v["b"] for v in no_drive)
        drive = {
            f["Path"]: f["Size"] for f in listar_drive(cfg, f"pacotes/{parte.destino}")
        }
        tamanho_errado = sum(
            1
            for c, _ in indices
            if drive.get(c["pacote"].split(f"pacotes/{parte.destino}/", 1)[-1])
            != c["tar_bytes"]
        )
        print(
            f"{parte.nome}: origem {len(origem)} arquivos / {bytes_origem} bytes; "
            f"Drive {len(no_drive)} arquivos / {bytes_drive} bytes em {len(indices)} pacotes; "
            f"ausentes no Drive: {ausentes}; mudaram depois do envio: {diferentes}; "
            f"pacotes com tamanho errado ou ausentes: {tamanho_errado}"
        )
        total_origem[0] += len(origem)
        total_origem[1] += bytes_origem
        total_drive[0] += len(no_drive)
        total_drive[1] += bytes_drive
        if ausentes or diferentes or tamanho_errado:
            falhas.append(parte.nome)
        todos.extend((parte, c, e) for c, e in indices)
    if total_origem[0] == 0:
        falhas.append("origem-vazia")
    print(
        f"TOTAL origem {total_origem[0]} arquivos / {total_origem[1]} bytes; "
        f"Drive {total_drive[0]} arquivos / {total_drive[1]} bytes"
    )
    if completo and not falhas:
        falhas.extend(conferir_completo(cfg, todos))
    if falhas:
        print("FALHAS: " + " ".join(falhas))
        return 1
    print("conferência do backup no Drive: tudo certo")
    return 0


def conferir_completo(
    cfg: Configuracao, todos: list[tuple[Parte, dict[str, Any], list[dict[str, Any]]]]
) -> list[str]:
    """Relê do Drive todos os pacotes: o sha256 de cada arquivo contra o índice e contra a origem."""
    arquivos = sum(len(e) for _, _, e in todos)
    problemas: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, cfg.paralelo)) as piscina:
        futuros = {piscina.submit(reler_pacote, cfg, p, c, e): c for p, c, e in todos}
        for futuro in as_completed(futuros):
            problemas.extend(futuro.result())
    for linha in problemas[:20]:
        print(linha)
    print(
        f"leitura completa: {arquivos} arquivos relidos do Drive, decifrados e conferidos por sha256 "
        f"(índice e origem); {len(problemas)} com problema"
    )
    return ["leitura-completa"] if problemas else []


# ---------- amostra de restauração ----------


def baixar_trecho(cfg: Configuracao, pacote: str, inicio: int, tamanho: int) -> bytes:
    """Um arquivo avulso, pela posição do índice, sem baixar o pacote inteiro."""
    return subprocess.run(
        [
            *cfg.rclone,
            "cat",
            "--offset",
            str(inicio),
            "--count",
            str(tamanho),
            f"{cfg.remoto}:{pacote}",
        ],
        capture_output=True,
        check=True,
    ).stdout


def amostra(
    cfg: Configuracao, pacotes_na_amostra: int = 4, sorteio: random.Random | None = None
) -> int:
    """Restaura pacotes inteiros e arquivos avulsos e confere o sha256 contra o índice."""
    sorteio = sorteio or random.Random()
    candidatos: list[tuple[Parte, dict[str, Any], list[dict[str, Any]]]] = []
    for parte in cfg.lista_de_partes():
        candidatos.extend(
            (parte, c, e)
            for c, e in ler_indices(cfg, parte)
            if 0 < c["tar_bytes"] <= TAMANHO_MAXIMO_DA_AMOSTRA
        )
    sorteio.shuffle(candidatos)
    escolhidos = candidatos[:pacotes_na_amostra]
    problemas: list[str] = []
    arquivos = 0
    for parte, cabecalho, entradas in escolhidos:
        problemas.extend(reler_pacote(cfg, parte, cabecalho, entradas))
        arquivos += len(entradas)
    avulsos = [(c, e) for _, c, es in escolhidos for e in es]
    sorteio.shuffle(avulsos)
    for cabecalho, e in avulsos[:ARQUIVOS_AVULSOS_NA_AMOSTRA]:
        dados = baixar_trecho(cfg, cabecalho["pacote"], e["o"], e["b"])
        arquivos += 1
        if hashlib.sha256(dados).hexdigest() != e["sha256"]:
            problemas.append(
                f"{e['p']}: arquivo avulso pela posição do índice não bate"
            )
    for linha in problemas[:20]:
        print(linha)
    if not escolhidos:
        print("restauração: nenhum pacote pequeno para testar")
        return 1
    print(
        f"restauração: {arquivos} arquivos baixados, decifrados e conferidos por sha256; "
        f"{len(problemas)} com problema"
    )
    return 1 if problemas else 0


def principal(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = ap.add_subparsers(dest="acao", required=True)
    s = sub.add_parser("subir", help="empacota e sobe o que é novo")
    s.add_argument("--simular", action="store_true", help="só mostra o plano")
    c = sub.add_parser("conferir", help="origem × Drive")
    c.add_argument(
        "--completo", action="store_true", help="relê todos os pacotes do Drive"
    )
    a = sub.add_parser("amostra", help="restaura pacotes e arquivos de amostra")
    a.add_argument("--pacotes", type=int, default=4)
    sub.add_parser(
        "reconstruir-estado", help="refaz o estado a partir dos índices do Drive"
    )
    args = ap.parse_args(argv)
    cfg = configuracao_do_ambiente()
    os.environ.setdefault(
        "RCLONE_CONFIG", str(Path.home() / ".config/tickerlab/backup-drive/rclone.conf")
    )
    tempfile.tempdir = os.environ.get("TMPDIR") or tempfile.gettempdir()
    if args.acao == "subir":
        return subir(cfg, simular=args.simular)
    if args.acao == "conferir":
        cfg.min_idade = float(
            os.environ.get("MIN_IDADE", SEGUNDOS_MIN_IDADE_CONFERENCIA)
        )
        return conferir(cfg, completo=args.completo)
    if args.acao == "amostra":
        return amostra(cfg, args.pacotes)
    return reconstruir_estado(cfg)


if __name__ == "__main__":
    sys.exit(principal())
