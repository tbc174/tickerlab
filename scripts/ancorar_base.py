"""Ancora uma versão da base no Bitcoin pelo OpenTimestamps e confere o recibo (ADR 0078;
a raiz de Merkle vem de `base/ancoragem.py`).

    python -m scripts.ancorar_base montar ancoras/base-2026-10-15.json --rotulo 2026-10-15 --pasta <acervo>/base
    python -m scripts.ancorar_base montar ancoras/prereg-m3-v1.json --rotulo m3-v1 --arquivo docs/pre-registro.md
    python -m scripts.ancorar_base carimbar ancoras/base-2026-10-15.json      (grava o .ots ao lado)
    python -m scripts.ancorar_base atualizar ancoras/base-2026-10-15.json.ots (horas depois: pega o bloco)
    python -m scripts.ancorar_base conferir ancoras/base-2026-10-15.json --pasta <acervo>/base
    python -m scripts.ancorar_base provar ancoras/base-2026-10-15.json fca/emissores --saida prova.json
    python -m scripts.ancorar_base conferir-prova prova.json <acervo>/base/fca/emissores.json
    python -m scripts.ancorar_base noite --ancoras ancoras --pasta <acervo>/base --rotulos <acervo>/rotulos_ia/v1

`noite` é a rotina do cron (servidor de casa, 0h15): âncora da base se ela mudou (no máximo uma por
dia), uma por lote de rótulos gravado, `carimbar` do que está sem recibo, `atualizar` dos pendentes e
uma linha `FALHAS:` (saída 1) para recibo pendente há mais de 2 dias.

**O que sai da máquina:** no `carimbar`, só um hash de 32 bytes por calendário: o SHA-256 da âncora
com 16 bytes aleatórios no fim (o "sal"), passado de novo pelo SHA-256. Nem o hash da âncora sai. No
`atualizar`, o mesmo hash volta ao calendário que o recebeu (só os da lista oficial do OpenTimestamps).
No `conferir`, só a altura do bloco vai ao nó do Bitcoin de casa (`BITCOIN_COOKIE`, `BITCOIN_RPC_ENDERECO`);
se ele não está ligado ou não responde, vai a dois exploradores públicos, que precisam concordar. Quem
tiver um nó do Bitcoin também pode conferir com o `ots verify` oficial.

Usa a biblioteca `opentimestamps` (LGPL-3.0) e não o programa `ots`, que não abre no Windows (a
`python-bitcoinlib` procura o OpenSSL por `ctypes`); o recibo é o mesmo formato `.ots` de sempre.
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from opentimestamps.calendar import DEFAULT_CALENDAR_WHITELIST, RemoteCalendar
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
from opentimestamps.core.op import OpAppend, OpSHA256
from opentimestamps.core.serialize import (
    StreamDeserializationContext,
    StreamSerializationContext,
)
from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

from base import ancoragem as an
from base.cripto.no_bitcoin import ENDERECO_PADRAO, ClienteRPC, ErroDoNo
from base.parquet import gravar_atomico
from src import rede

log = logging.getLogger("tickerlab.ancorar_base")

# Os agregadores públicos que o `ots stamp` usa por padrão; cada um repassa a um calendário.
CALENDARIOS = [
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://a.pool.eternitywall.com",
    "https://ots.btc.catallaxy.com",
]
MINIMO_DE_CALENDARIOS = 2
EXPLORADORES = ["https://mempool.space/api", "https://blockstream.info/api"]
ESPERA = 15  # segundos por pedido
# O nó do Bitcoin do servidor de casa: o cookie do RPC (o mesmo da coleta de cripto) e o endereço
# vêm do ambiente (`.env`); sem o cookie, o nó fica de fora e valem só os exploradores.
VARIAVEL_DO_COOKIE = "BITCOIN_COOKIE"
VARIAVEL_DO_ENDERECO = "BITCOIN_RPC_ENDERECO"
ESPERA_DO_NO = 10  # segundos por pedido: nó parado não pode segurar a rotina da noite
BRASILIA = ZoneInfo("America/Sao_Paulo")

Enviar = Callable[[str, bytes], Timestamp]
Buscar = Callable[[str, bytes], Timestamp | None]
Bloco = Callable[[int], tuple[str, int] | None]


# --- montar a âncora ------------------------------------------------------------------------------
def _folhas(pasta: Path | None, arquivos: list[Path]) -> dict[str, bytes]:
    folhas = an.folhas_da_base(pasta) if pasta else {}
    for arquivo in arquivos:
        nome = f"arquivos/{arquivo.name}"
        if nome in folhas:
            raise ValueError(f"{nome} aparece duas vezes")
        folhas[nome] = an.hash_folha(an.folha_de_arquivo(nome, arquivo.read_bytes()))
    return folhas


def montar(
    destino: Path, rotulo: str, pasta: Path | None, arquivos: list[Path]
) -> Path:
    """Grava a âncora; nunca sobrescreve (uma âncora carimbada é para sempre)."""
    if destino.exists():
        raise FileExistsError(f"{destino} já existe: use outro rótulo")
    ancora = an.montar_ancora(_folhas(pasta, arquivos), rotulo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    gravar_atomico(
        destino, lambda caminho: Path(caminho).write_bytes(an.texto_da_ancora(ancora))
    )
    return destino


def diferencas_de_hoje(
    ancora: dict[str, Any], pasta: Path | None, arquivos: list[Path]
) -> list[str]:
    return an.diferencas(ancora, _folhas(pasta, arquivos))


# --- recibo .ots ----------------------------------------------------------------------------------
def _recibo_de(ancora: Path) -> Path:
    return ancora.with_name(ancora.name + ".ots")


def ler_recibo(recibo: Path) -> DetachedTimestampFile:
    with recibo.open("rb") as arquivo:
        return DetachedTimestampFile.deserialize(StreamDeserializationContext(arquivo))


def _gravar_recibo(recibo: Path, carimbo: DetachedTimestampFile) -> None:
    def gravar(caminho: Path) -> None:
        with open(caminho, "wb") as arquivo:
            carimbo.serialize(StreamSerializationContext(arquivo))

    gravar_atomico(recibo, gravar)


def _enviar(url: str, digest: bytes) -> Timestamp:
    return RemoteCalendar(url, user_agent="TickerLab").submit(digest, timeout=ESPERA)


def carimbar(ancora: Path, enviar: Enviar = _enviar) -> Path:
    """Manda o hash com sal aos calendários e grava `<âncora>.ots` (ainda pendente).

    Nunca sobrescreve: um recibo que já ganhou o bloco perderia a data confirmada.
    """
    if _recibo_de(ancora).exists():
        raise FileExistsError(f"{_recibo_de(ancora)} já existe: use `atualizar`")
    digest = hashlib.sha256(ancora.read_bytes()).digest()
    carimbo = DetachedTimestampFile(OpSHA256(), Timestamp(digest))
    # O sal: sem ele, quem tivesse a âncora acharia o pedido nos calendários (como o `ots stamp`).
    com_sal = carimbo.timestamp.ops.add(OpAppend(os.urandom(16)))
    compromisso = com_sal.ops.add(OpSHA256())
    aceitos = 0
    for url in CALENDARIOS:
        try:
            compromisso.merge(enviar(url, compromisso.msg))
            aceitos += 1
        except Exception as erro:  # noqa: BLE001 (um calendário fora do ar não para os outros)
            log.warning("%s não aceitou: %s", url, erro)
    if aceitos < MINIMO_DE_CALENDARIOS:
        raise RuntimeError(
            f"só {aceitos} calendários aceitaram (mínimo {MINIMO_DE_CALENDARIOS})"
        )
    recibo = _recibo_de(ancora)
    _gravar_recibo(recibo, carimbo)
    return recibo


def _pendentes(carimbo: Timestamp) -> Iterator[tuple[Timestamp, PendingAttestation]]:
    for atestado in carimbo.attestations:
        if isinstance(atestado, PendingAttestation):
            yield carimbo, atestado
    for seguinte in carimbo.ops.values():
        yield from _pendentes(seguinte)


def _buscar(uri: str, compromisso: bytes) -> Timestamp | None:
    try:
        return RemoteCalendar(uri, user_agent="TickerLab").get_timestamp(
            compromisso, timeout=ESPERA
        )
    except Exception as erro:  # noqa: BLE001 (sem bloco ainda, 404, ou fora do ar: tenta depois)
        log.info("%s ainda sem bloco: %s", uri, erro)
        return None


def _no_bitcoin(carimbo: Timestamp) -> list[tuple[bytes, int]]:
    return [
        (msg, atestado.height)
        for msg, atestado in carimbo.all_attestations()
        if isinstance(atestado, BitcoinBlockHeaderAttestation)
    ]


def atualizar(recibo: Path, buscar: Buscar = _buscar) -> bool:
    """Pede aos calendários o caminho até o bloco do Bitcoin; True se o recibo já tem um bloco."""
    carimbo = ler_recibo(recibo)
    for parte, atestado in list(_pendentes(carimbo.timestamp)):
        if atestado.uri not in DEFAULT_CALENDAR_WHITELIST:
            log.warning("calendário fora da lista oficial, ignorado: %s", atestado.uri)
            continue
        pronto = buscar(atestado.uri, parte.msg)
        if pronto is not None:
            parte.merge(pronto)
    _gravar_recibo(recibo, carimbo)
    return bool(_no_bitcoin(carimbo.timestamp))


# --- conferir -------------------------------------------------------------------------------------
def _buscar_texto(url: str) -> str:
    resposta = rede.obter(url, timeout=ESPERA)
    resposta.raise_for_status()
    return resposta.text


def _cliente_do_no() -> ClienteRPC | None:
    cookie = os.environ.get(VARIAVEL_DO_COOKIE)
    if not cookie:
        return None
    return ClienteRPC(
        Path(cookie),
        os.environ.get(VARIAVEL_DO_ENDERECO) or ENDERECO_PADRAO,
        tempo_limite=ESPERA_DO_NO,
    )


def raiz_do_bloco_no_no(altura: int, no: ClienteRPC) -> tuple[str, int]:
    """A raiz de Merkle e a hora do bloco, direto do nó do Bitcoin (cabeçalho, que o nó podado guarda)."""
    cabecalho = no.cabecalho(no.hash_na_altura(altura))
    return cabecalho["merkleroot"], int(cabecalho["time"])


def raiz_do_bloco(
    altura: int,
    buscar_texto: Callable[[str], str] = _buscar_texto,
    exploradores: list[str] = EXPLORADORES,
    no: ClienteRPC | None = None,
) -> tuple[str, int]:
    """A raiz de Merkle (como o Bitcoin Core e os exploradores mostram) e a hora do bloco.

    Pergunta primeiro ao nó do Bitcoin de casa (`no`, ou o do ambiente). Se ele não está configurado,
    não responde ou não conhece a altura, cai para os exploradores, que precisam concordar entre si.
    """
    no = no or _cliente_do_no()
    if no is not None:
        try:
            return raiz_do_bloco_no_no(altura, no)
        except (
            requests.RequestException,
            ErroDoNo,
            OSError,
            KeyError,
            ValueError,
        ) as erro:
            # o texto do erro não leva o cookie (o cliente o esconde); a mensagem vai ao log
            log.warning(
                "nó do Bitcoin sem resposta para o bloco %s (%s): usando os exploradores",
                altura,
                type(erro).__name__,
            )
    respostas = set()
    for explorador in exploradores:
        hash_do_bloco = buscar_texto(f"{explorador}/block-height/{altura}").strip()
        bloco = json.loads(buscar_texto(f"{explorador}/block/{hash_do_bloco}"))
        respostas.add((bloco["merkle_root"], int(bloco["timestamp"])))
    if len(respostas) != 1:
        raise RuntimeError(
            f"os exploradores não concordam sobre o bloco {altura}: {respostas}"
        )
    return respostas.pop()


@dataclass
class Resultado:
    diferencas: list[str]
    recibo_desta_ancora: bool
    pendente: bool = False
    altura: int | None = None
    confirmado_em: datetime | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            not self.diferencas
            and self.recibo_desta_ancora
            and self.confirmado_em is not None
        )


def conferir(
    ancora: Path,
    recibo: Path,
    pasta: Path | None,
    arquivos: list[Path],
    bloco: Bloco = raiz_do_bloco,
) -> Resultado:
    """A base de hoje é a da âncora? O recibo é desta âncora? Em que bloco do Bitcoin ela entrou?"""
    texto = ancora.read_bytes()
    carimbo = ler_recibo(recibo)
    resultado = Resultado(
        diferencas=diferencas_de_hoje(json.loads(texto), pasta, arquivos),
        recibo_desta_ancora=isinstance(carimbo.file_hash_op, OpSHA256)
        and carimbo.file_digest == hashlib.sha256(texto).digest(),
        pendente=any(True for _ in _pendentes(carimbo.timestamp)),
    )
    if not resultado.recibo_desta_ancora:
        return resultado
    for msg, altura in _no_bitcoin(carimbo.timestamp):
        try:
            no_bloco = bloco(altura)
        except (requests.RequestException, RuntimeError) as erro:
            resultado.avisos.append(f"bloco {altura} sem conferência: {erro}")
            continue
        # O Bitcoin guarda a raiz com os bytes ao contrário do que os exploradores mostram.
        if no_bloco is not None and len(msg) == 32 and msg[::-1].hex() == no_bloco[0]:
            data = datetime.fromtimestamp(no_bloco[1], tz=UTC)
            if resultado.confirmado_em is None or data < resultado.confirmado_em:
                resultado.altura, resultado.confirmado_em = altura, data
        else:
            resultado.avisos.append(f"o bloco {altura} não tem este compromisso")
    return resultado


# --- rotina noturna -------------------------------------------------------------------------------
PRAZO_DO_BLOCO = timedelta(days=2)  # recibo sem bloco depois disso vai para o Kuma
BASE_DO_DIA = re.compile(r"^base-\d{4}-\d{2}-\d{2}\.json$")
LISTADOS = 5  # quantos Parquets sem manifesto o aviso nomeia


@dataclass
class Noite:
    carimbadas: list[str] = field(default_factory=list)
    no_bitcoin: list[str] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)


def _nome_do_lote(lote_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", lote_id)


def _ancorar_base_do_dia(ancoras: Path, pasta: Path, dia: str, feito: Noite) -> None:
    """Uma âncora por dia, e só se a base mudou desde a última (ADR 0078, item 3)."""
    destino = ancoras / f"base-{dia}.json"
    if destino.exists():
        return
    anteriores = sorted(
        p for p in ancoras.glob("base-*.json") if BASE_DO_DIA.match(p.name)
    )
    try:
        if anteriores and not diferencas_de_hoje(_ler_json(anteriores[-1]), pasta, []):
            log.info("base igual à %s: sem âncora nova", anteriores[-1].name)
            return
        montar(destino, dia, pasta, [])
    except ValueError as erro:  # a regra da LGPD recusou uma tabela: para e avisa
        feito.problemas.append(f"base não ancorada: {erro}")


def _ancorar_lotes(ancoras: Path, rotulos: Path, feito: Noite) -> None:
    """Uma âncora para cada lote de rótulos já gravado (ADR 0078, item 1; ADR 0072), do rotulador
    (`manifesto.json`) e do segundo modelo (`manifesto.<modelo>.json`, Emenda 1)."""
    arquivos = [rotulos / "manifesto.json", rotulos / "rotulos.jsonl"]
    if not all(arquivo.exists() for arquivo in arquivos):
        feito.problemas.append(
            f"rótulos sem {', '.join(a.name for a in arquivos)} em {rotulos}"
        )
        return
    outros = sorted(rotulos.glob("manifesto.*.json"))
    for manifesto in [arquivos[0], *outros]:
        sufixo = manifesto.name.removeprefix("manifesto").removesuffix(".json")
        par = [manifesto, rotulos / f"rotulos{sufixo}.jsonl"]
        if not par[1].exists():
            feito.problemas.append(f"{manifesto.name} sem {par[1].name} em {rotulos}")
            continue
        for lote in _ler_json(manifesto).get("lotes", []):
            destino = ancoras / f"rotulos-{_nome_do_lote(lote['id'])}.json"
            if lote.get("estado") == "gravado" and not destino.exists():
                montar(destino, f"lote {lote['id']}", None, par)


def _completo(recibo: Path) -> bool:
    return bool(_no_bitcoin(ler_recibo(recibo).timestamp))


def noite(
    ancoras: Path,
    pasta: Path | None,
    rotulos: Path | None,
    agora: datetime,
    enviar: Enviar = _enviar,
    buscar: Buscar = _buscar,
) -> Noite:
    """A rotina do cron: monta as âncoras novas, carimba as que estão sem recibo, pede o bloco das
    pendentes e anota como problema o recibo pendente há mais de `PRAZO_DO_BLOCO`."""
    feito = Noite()
    ancoras.mkdir(parents=True, exist_ok=True)
    if pasta is not None:
        _ancorar_base_do_dia(
            ancoras, pasta, agora.astimezone(BRASILIA).date().isoformat(), feito
        )
        if soltos := an.parquets_sem_manifesto(pasta):
            feito.problemas.append(
                f"{len(soltos)} Parquet(s) sem manifesto, fora da âncora: "
                + ", ".join(soltos[:LISTADOS])
                + (" ..." if len(soltos) > LISTADOS else "")
            )
    if rotulos is not None:
        _ancorar_lotes(ancoras, rotulos, feito)

    for ancora in sorted(ancoras.glob("*.json")):
        if _recibo_de(ancora).exists():
            continue
        try:
            carimbar(ancora, enviar)
            feito.carimbadas.append(ancora.name)
        except (
            RuntimeError
        ) as erro:  # poucos calendários: tenta de novo na próxima noite
            feito.problemas.append(f"{ancora.name} sem recibo: {erro}")

    for recibo in sorted(ancoras.glob("*.json.ots")):
        if recibo.name.removesuffix(".ots") in feito.carimbadas or _completo(recibo):
            continue
        if atualizar(recibo, buscar):
            feito.no_bitcoin.append(recibo.name)
            continue
        montada_em = datetime.fromtimestamp(
            recibo.with_suffix("").stat().st_mtime, tz=BRASILIA
        )
        if agora - montada_em > PRAZO_DO_BLOCO:
            feito.problemas.append(
                f"{recibo.name} pendente há {(agora - montada_em).days} dias"
            )
    return feito


# --- linha de comando -----------------------------------------------------------------------------
def _ler_json(caminho: Path) -> Any:  # noqa: ANN401 (JSON lido do disco)
    return json.loads(caminho.read_text(encoding="utf-8"))


def _mostrar(resultado: Resultado) -> None:
    print(
        "base igual à âncora"
        if not resultado.diferencas
        else "base diferente da âncora:"
    )
    for linha in resultado.diferencas:
        print("  -", linha)
    print(
        "recibo é desta âncora"
        if resultado.recibo_desta_ancora
        else "recibo é de OUTRO arquivo"
    )
    if resultado.confirmado_em is not None:
        hora = resultado.confirmado_em.astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M")
        print(f"no Bitcoin desde o bloco {resultado.altura}: {hora} (Brasília)")
    elif resultado.pendente:
        print("ainda pendente: rode `atualizar` daqui a algumas horas")
    for aviso in resultado.avisos:
        print("aviso:", aviso)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    comandos = argumentos.add_subparsers(dest="comando", required=True)
    m = comandos.add_parser("montar", help="monta a âncora (raiz de Merkle)")
    m.add_argument("saida", type=Path)
    m.add_argument("--rotulo", required=True)
    m.add_argument(
        "--pasta",
        type=Path,
        help="pasta da base (manifestos .json ao lado dos .parquet)",
    )
    m.add_argument("--arquivo", type=Path, action="append", default=[])
    c = comandos.add_parser(
        "carimbar", help="manda o hash aos calendários e grava o .ots"
    )
    c.add_argument("ancora", type=Path)
    a = comandos.add_parser("atualizar", help="pega o caminho até o bloco do Bitcoin")
    a.add_argument("recibo", type=Path)
    v = comandos.add_parser("conferir", help="confere base, âncora, recibo e bloco")
    v.add_argument("ancora", type=Path)
    v.add_argument("--pasta", type=Path)
    v.add_argument("--arquivo", type=Path, action="append", default=[])
    p = comandos.add_parser(
        "provar", help="prova de inclusão de uma tabela, para o cliente"
    )
    p.add_argument("ancora", type=Path)
    p.add_argument("nome")
    p.add_argument("--saida", type=Path, required=True)
    cp = comandos.add_parser(
        "conferir-prova", help="o manifesto desta tabela está na raiz?"
    )
    cp.add_argument("prova", type=Path)
    cp.add_argument("manifesto", type=Path)
    n = comandos.add_parser(
        "noite", help="rotina do cron: âncoras novas, recibos e alarme dos pendentes"
    )
    n.add_argument("--ancoras", type=Path, required=True)
    n.add_argument("--pasta", type=Path, help="pasta da base")
    n.add_argument(
        "--rotulos", type=Path, help="pasta dos rótulos da IA (rotulos_ia/v1)"
    )
    args = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if args.comando == "montar":
        destino = montar(args.saida, args.rotulo, args.pasta, args.arquivo)
        print("raiz:", _ler_json(destino)["raiz"])
    elif args.comando == "carimbar":
        print("recibo:", carimbar(args.ancora))
    elif args.comando == "atualizar":
        print("no Bitcoin" if atualizar(args.recibo) else "ainda pendente")
    elif args.comando == "conferir":
        resultado = conferir(
            args.ancora, _recibo_de(args.ancora), args.pasta, args.arquivo
        )
        _mostrar(resultado)
        return 0 if resultado.ok else 1
    elif args.comando == "noite":
        feito = noite(
            args.ancoras,
            args.pasta,
            args.rotulos,
            datetime.now(BRASILIA),
            _enviar,
            _buscar,
        )
        for nome in feito.carimbadas:
            print("carimbada:", nome)
        for nome in feito.no_bitcoin:
            print("no Bitcoin:", nome)
        if feito.problemas:
            print("FALHAS: " + "; ".join(feito.problemas))
            return 1
        print("âncoras em dia")
    elif args.comando == "provar":
        prova = an.prova_da_tabela(_ler_json(args.ancora), args.nome)
        args.saida.write_text(
            json.dumps(prova, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print("prova:", args.saida)
    else:
        prova = _ler_json(args.prova)
        if not an.conferir_prova_da_tabela(prova, _ler_json(args.manifesto)):
            print(
                f"{prova['nome']}: este manifesto NÃO está na raiz {prova['raiz'][:16]}…"
            )
            return 1
        print(
            f"{prova['nome']}: está na raiz {prova['raiz'][:16]}… ({prova['rotulo']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
