"""Segunda cópia dos negócios do pregão da B3 (no VPS) e a reconciliação com a de casa (ADR 0073).

A cópia principal fica no servidor de casa, no acervo, pelo arquivista (fonte `b3-negocios`). A do
VPS existe para quando faltar luz ou internet em casa e fica **fora do banco do app** (dado da B3 é
só pesquisa): uma pasta própria com um arquivo por versão, `<pasta>/brutos/AAAA-MM-DD/<sha256>.zip`,
e uma linha por download em `<pasta>/manifesto.jsonl`. Retenção de 90 dias (a casa guarda tudo).
Mesmas regras do arquivista: 404 e "200 com 0 bytes" não são arquivo, zip quebrado é falha, dia
pequeno demais (veio incompleto) é baixado de novo a cada rodada.

Todo dia o servidor de casa compara as duas cópias (`scripts/reconciliar_b3_vps.py`): traz para o
acervo a versão que só o VPS tem e acusa, dentro da janela, dia que falta numa das máquinas ou cuja
última versão é diferente. Dia que não está em nenhuma das duas (feriado ou perdido) fica com o
alarme da janela (PR 3 do plano dos intradiários).
"""

import hashlib
import json
import logging
import os
import re
import shutil
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import cast

from base.arquivo import fontes
from base.arquivo.coleta import (
    PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS,
    Alvo,
    Cliente,
    SemArquivo,
    conferir_freio,
    espaco_do_disco,
    guardar_copia,
)

log = logging.getLogger(__name__)

FONTE = "b3-negocios"
RETENCAO_EM_DIAS = 90
SHA_CURTO = 12  # o começo do SHA-256 nas mensagens (cabe no aviso do Kuma)
NOME_DE_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NOME_DE_SHA = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Versao:
    dia: date
    sha256: str
    quando: float  # segundos desde 1970: a mais recente é a que vale
    caminho: str = ""  # relativo ao acervo (só a de casa)


@dataclass
class Rodada:
    novos: int = 0
    iguais: int = 0
    pulados: int = 0
    sem_arquivo: int = 0
    falhas: list[str] = field(default_factory=list)


def _sha256(caminho: Path) -> str:
    with caminho.open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest()


def dia_do_endereco(url: str) -> date:
    return date.fromisoformat(url.rstrip("/").rsplit("/", 1)[-1])


def dias_da_janela(agora: datetime) -> list[date]:
    """Os dias que o arquivista olha (dias úteis dos últimos 30, no fuso de São Paulo). A
    descoberta da B3 só monta os endereços: não fala com a rede e não usa o cliente."""
    sem_rede = cast(Cliente, None)
    return [
        dia_do_endereco(a.url) for a in fontes.descobrir_negocios_b3(sem_rede, agora)
    ]


# --- a cópia no VPS -------------------------------------------------------------------------------


def _mais_recente(pasta_do_dia: Path) -> Path | None:
    versoes = list(pasta_do_dia.glob("*.zip"))
    return max(versoes, key=lambda p: p.stat().st_mtime) if versoes else None


def _copiar_um(
    alvo: Alvo, cliente: Cliente, pasta: Path, agora: datetime, rodada: Rodada
) -> None:
    dia = dia_do_endereco(alvo.url)
    pasta_do_dia = pasta / "brutos" / dia.isoformat()
    ultima = _mais_recente(pasta_do_dia)
    # lido aqui (e não importado) para o teste poder trocar o limite
    if (
        ultima is not None
        and ultima.stat().st_size >= fontes.TAMANHO_MINIMO_DE_UM_DIA_BOM
    ):
        rodada.pulados += 1
        return
    temporario = pasta / ".temporario" / f"{dia.isoformat()}.parcial"
    try:
        if alvo.obter is not None:
            alvo.obter(cliente, temporario)
        else:
            cliente.baixar(alvo.url, temporario)
        sha256 = _sha256(temporario)
        tamanho = temporario.stat().st_size
        destino = pasta_do_dia / f"{sha256}.zip"
        if destino.exists():
            os.utime(destino)  # visto de novo agora: volta a ser a versão mais recente
            rodada.iguais += 1
        else:
            pasta_do_dia.mkdir(parents=True, exist_ok=True)
            temporario.replace(destino)  # mesmo disco: o arquivo só aparece inteiro
            rodada.novos += 1
    finally:
        temporario.unlink(missing_ok=True)
    linha = {
        "dia": dia.isoformat(),
        "sha256": sha256,
        "bytes": tamanho,
        "url": alvo.url,
        "hora": agora.isoformat(),
    }
    with (pasta / "manifesto.jsonl").open("a", encoding="utf-8") as manifesto:
        manifesto.write(json.dumps(linha) + "\n")


def copiar_janela(
    cliente: Cliente,
    pasta: Path,
    agora: datetime,
    *,
    pausa: float = PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS,
    espaco: Callable[[Path], tuple[int, int]] = espaco_do_disco,
) -> Rodada:
    """Baixa os dias da janela que ainda não estão guardados inteiros, um pedido por vez.

    Levanta `FreioDeDisco` antes de baixar (o VPS é o da produção); falha num dia não para os outros.
    Não usa banco nenhum.
    """
    conferir_freio(*espaco(pasta))
    (pasta / ".temporario").mkdir(parents=True, exist_ok=True)
    rodada = Rodada()
    for numero, alvo in enumerate(fontes.descobrir_negocios_b3(cliente, agora)):
        if numero and pausa:
            time.sleep(pausa)
        try:
            _copiar_um(alvo, cliente, pasta, agora, rodada)
        except SemArquivo as motivo:
            log.info("%s: sem arquivo (%s)", alvo.url, motivo)
            rodada.sem_arquivo += 1
        except Exception as erro:  # noqa: BLE001 (cada dia falha sozinho)
            log.warning("%s: falhou (%s)", alvo.url, erro)
            rodada.falhas.append(
                f"{dia_do_endereco(alvo.url)} ({type(erro).__name__}: {erro})"
            )
    return rodada


def apagar_antigos(pasta: Path, hoje: date, dias: int = RETENCAO_EM_DIAS) -> list[date]:
    """Apaga as pastas de pregão com mais de `dias` dias; devolve os dias apagados."""
    apagados = []
    brutos = pasta / "brutos"
    for pasta_do_dia in sorted(brutos.iterdir()) if brutos.is_dir() else []:
        if not NOME_DE_DIA.match(pasta_do_dia.name):
            continue
        dia = date.fromisoformat(pasta_do_dia.name)
        if (hoje - dia).days > dias:
            shutil.rmtree(pasta_do_dia)
            apagados.append(dia)
    return apagados


# --- a reconciliação, no servidor de casa ---------------------------------------------------------


def _mais_recentes(versoes: Iterable[Versao]) -> dict[date, Versao]:
    ultimas: dict[date, Versao] = {}
    for versao in versoes:
        atual = ultimas.get(versao.dia)
        if atual is None or versao.quando >= atual.quando:
            ultimas[versao.dia] = versao
    return ultimas


def ler_lista_do_vps(texto: str) -> tuple[dict[date, Versao], list[str]]:
    """A lista que o VPS manda (`dia nome sha_calculado mtime bytes` por linha, do
    `servir-b3.sh`): a versão mais recente de cada dia e os problemas (arquivo estragado no VPS)."""
    versoes, problemas = [], []
    for linha in texto.splitlines():
        if not linha.strip():
            continue
        partes = linha.split()
        if (
            len(partes) != 5
            or not NOME_DE_DIA.match(partes[0])
            or not all(NOME_DE_SHA.match(p) for p in partes[1:3])
        ):
            problemas.append(f"linha estranha na lista do VPS: {linha!r}")
            continue
        dia, nome, calculado, mtime, _ = partes
        if nome != calculado:
            problemas.append(f"{dia}: arquivo {nome[:SHA_CURTO]} estragado no VPS")
            continue
        versoes.append(Versao(date.fromisoformat(dia), nome, float(mtime)))
    return _mais_recentes(versoes), problemas


def ultimas_da_casa(acervo: Path, dias: Iterable[date]) -> dict[date, Versao]:
    """A versão mais recente de cada dia da janela no acervo de casa, pelos manifestos do
    arquivista (uma linha por download, com a hora). Só lê os manifestos desde o dia mais antigo."""
    dias = set(dias)
    if not dias:
        return {}
    desde = min(dias).isoformat()
    versoes = []
    for manifesto in sorted((acervo / "manifesto").glob("*.jsonl")):
        if manifesto.stem < desde:
            continue
        for linha in manifesto.read_text(encoding="utf-8").splitlines():
            registro = json.loads(linha)
            if registro.get("fonte") != FONTE or not registro.get("caminho"):
                continue
            dia = dia_do_endereco(registro["url"])
            if dia in dias:
                quando = datetime.fromisoformat(registro["hora"]).timestamp()
                versoes.append(
                    Versao(dia, registro["sha256"], quando, registro["caminho"])
                )
    return _mais_recentes(versoes)


def conferir_casa(acervo: Path, ultimas: Mapping[date, Versao]) -> list[str]:
    """O arquivo de casa ainda é o que o manifesto diz (SHA-256 calculado de novo)?"""
    problemas = []
    for dia, versao in sorted(ultimas.items()):
        caminho = acervo / versao.caminho
        if not caminho.is_file():
            problemas.append(f"{dia}: arquivo de casa sumiu do acervo")
        elif _sha256(caminho) != versao.sha256:
            problemas.append(f"{dia}: arquivo de casa não bate com o manifesto")
    return problemas


def comparar(
    casa: Mapping[date, Versao], vps: Mapping[date, Versao], dias: Iterable[date]
) -> list[str]:
    """Dia da janela que falta numa máquina ou cuja última versão é diferente nas duas."""
    problemas = []
    for dia in sorted(dias):
        de_casa, do_vps = casa.get(dia), vps.get(dia)
        if de_casa is None and do_vps is None:
            continue
        if do_vps is None:
            problemas.append(f"{dia}: falta no VPS")
        elif de_casa is None:
            problemas.append(f"{dia}: faltava em casa")
        elif de_casa.sha256 != do_vps.sha256:
            problemas.append(
                f"{dia}: diferente (casa {de_casa.sha256[:SHA_CURTO]}, "
                f"VPS {do_vps.sha256[:SHA_CURTO]})"
            )
    return problemas


def guardar_recebidos(recebidos: Path, agora: datetime) -> tuple[int, list[str]]:
    """Põe no acervo (com registro e manifesto) as versões que vieram do VPS
    (`<recebidos>/AAAA-MM-DD/<sha256>.zip`), conferindo o SHA-256 de cada uma."""
    trazidos, problemas = 0, []
    for arquivo in sorted(recebidos.glob("*/*.zip")):
        dia = date.fromisoformat(arquivo.parent.name)
        if _sha256(arquivo) != arquivo.stem:
            problemas.append(
                f"{dia}: chegou estragado do VPS ({arquivo.stem[:SHA_CURTO]})"
            )
            arquivo.unlink()
            continue
        url = fontes.NEGOCIOS_DA_B3.format(dia=dia.isoformat())
        guardar_copia(
            FONTE, url, arquivo, arquivo.stem, agora, origem="VPS", extensao=".zip"
        )
        trazidos += 1
    return trazidos, problemas
