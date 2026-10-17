"""Arquivista: guarda o retrato de cada fonte como veio, para existir o "como era na data".

Várias fontes oficiais só mostram o dia de hoje (CNPJ, sanções da CGU, dívida ativa, cadastros da
CVM) ou reescrevem o passado em silêncio (FIAGRO, FIDC). Se ninguém guardar, o histórico some. Aqui
nada é lido nem tratado: cada arquivo é **baixado, conferido, guardado no acervo** (`src/acervo.py`,
nome = SHA-256) e **registrado** (`src/banco/coletas.py`), com uma linha a mais no manifesto do dia
(`<acervo>/manifesto/AAAA-MM-DD.jsonl`), que é a cópia do registro fora do banco.

Regras (testes em `tests/test_base_arquivo.py`):
- arquivos grandes vão para o disco em partes, nunca inteiros na memória;
- fonte **leve**: sempre baixa e compara pelo SHA-256 (a CVM sobrescreve sem mudar os cabeçalhos);
  fonte **pesada** (GBs): se `ETag`, `Last-Modified` e tamanho são os da última coleta, nem baixa;
- **freio de disco** antes das pesadas: menos de 50 GB livres ou mais de 70% usado (ADR 0031);
- descoberta sem nenhum arquivo, ou HTML no lugar do arquivo, é **falha**, nunca "nada novo";
- a fonte que diz que o arquivo não existe (ainda ou mais; a B3 responde 404 ou "200 com 0 bytes")
  levanta `SemArquivo`: fica registrada como "nao_encontrado", nunca "ok" nem falha;
- fonte sem ETag nem Last-Modified (a B3) decide pela última coleta "ok" (`guardado_vale`) se nem
  precisa baixar de novo;
- fonte **vigia** (termos de uso, catálogos): avisa quando o texto visível muda.
"""

import hashlib
import json
import logging
import re
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

import certifi
import sqlalchemy as sa

from src import acervo
from src.banco.coletas import registrar_arquivo, ultima_coleta_ok
from src.banco.conexao import obter_engine

log = logging.getLogger(__name__)

esperar = time.sleep  # só este módulo espera por aqui: os testes trocam este nome, não o `time.sleep` do processo
VERSAO_DO_ARQUIVISTA = "1"
LIVRE_MINIMO_EM_BYTES = 50 * 1024**3
USO_MAXIMO_DO_DISCO = 0.70
PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS = 1.0
TAMANHO_DA_PARTE = 1024 * 1024
CABECALHOS_GUARDADOS = ("Last-Modified", "ETag", "Content-Length", "Content-Type")
SEPARADOR_DO_DETALHE = " | "
IGUAL_A_ANTERIOR = "igual à coleta anterior"
ASSINATURAS = {"pdf": (b"%PDF",), "json": (b"{", b"["), "zip": (b"PK",)}
# a página de bloqueio do BC começa com "<?xml ...>" antes do "<!DOCTYPE html"
COMECO_DE_HTML = re.compile(
    rb"^\s*(<\?xml[^>]*>\s*)?(<!doctype html|<html)", re.IGNORECASE
)
SCRIPTS_E_ESTILOS = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
ETIQUETAS = re.compile(r"<[^>]+>")
ESPACOS = re.compile(r"\s+")


# intermediários que alguns servidores do governo esquecem de mandar (o MDIC, 14/10/2026: só a
# folha; o Windows completa sozinho, o Python não). São públicos e fecham em raízes do `certifi`
CERTIFICADOS_EXTRAS = Path(__file__).resolve().parent / "certificados"


def pacote_de_certificados(pasta: Path = CERTIFICADOS_EXTRAS) -> str:
    """As raízes do `certifi` mais os intermediários de `pasta`, num arquivo temporário."""
    extras = sorted(pasta.glob("*.pem")) if pasta.is_dir() else []
    if not extras:
        return certifi.where()
    texto = Path(certifi.where()).read_text(encoding="ascii")
    texto += "".join("\n" + p.read_text(encoding="ascii") for p in extras)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".pem", delete=False, encoding="ascii"
    ) as pacote:
        pacote.write(texto)
    return pacote.name


@dataclass(frozen=True)
class Resposta:
    url: str  # o endereço final, depois dos redirecionamentos
    conteudo: bytes
    cabecalhos: Mapping[str, str]


class Cliente(Protocol):
    """Quem fala com as fontes (no script, `requests`; nos testes, um dublê)."""

    def ler(
        self,
        url: str,
        *,
        metodo: str = "GET",
        cabecalhos: Mapping[str, str] | None = None,
    ) -> Resposta:
        """Uma página ou um JSON pequeno (descoberta)."""
        ...

    def cabecalhos(self, url: str) -> Mapping[str, str]:
        """Só os cabeçalhos (HEAD), para as pesadas decidirem se baixam."""
        ...

    def baixar(self, url: str, destino: Path) -> Mapping[str, str]:
        """Grava o arquivo em `destino`, em partes, e devolve os cabeçalhos da resposta."""
        ...

    def ler_trecho(self, url: str, inicio: int, fim: int) -> bytes:
        """Os bytes de `inicio` a `fim` (inclusive), por pedido de trecho (HTTP Range); falha se o
        servidor ignorar o trecho (nunca baixa o arquivo inteiro sem querer)."""
        ...


# quando baixar inteiro não serve (ZIP de GBs, coluna com CPF): grava em `destino` e devolve os
# cabeçalhos da origem (`base/arquivo/obter.py`)
Obter = Callable[[Cliente, Path], Mapping[str, str]]


@dataclass(frozen=True)
class Alvo:
    url: str
    extensao: str | None = None  # quando o endereço não diz (".zip" da CGU)
    obter: Obter | None = field(
        default=None, compare=False
    )  # None: `cliente.baixar(url)`


Descobrir = Callable[[Cliente, datetime], list[Alvo]]


@dataclass(frozen=True)
class Fonte:
    id: str  # nome no registro de coletas, "família-detalhe" (`licenca_da_fonte`)
    grupo: str  # "diaria", "semanal" ou "mensal" (a hora em que roda)
    descobrir: Descobrir
    tipo: str = "arquivo"  # "arquivo" (qualquer coisa que não seja HTML), "pdf", "json", "zip" ou "html"
    pesada: bool = False
    vigia: bool = False
    # pela última coleta "ok" do endereço, o que já está guardado basta (não baixa de novo)? Para
    # fonte sem ETag nem Last-Modified (a B3); None: a regra dos cabeçalhos (pesadas) ou do SHA-256
    guardado_vale: Callable[[sa.Row], bool] | None = None
    # espera mínima entre dois pedidos (site pequeno de terceiros, ADR 0082); vale quando há pausa
    pausa_minima: float = 0.0


@dataclass
class Resultado:
    fonte: str
    novos: int = 0
    iguais: int = 0
    pulados: int = 0
    sem_arquivo: int = 0
    falhas: list[str] = field(default_factory=list)
    mudaram: list[str] = field(default_factory=list)


class ErroDeDescoberta(Exception):
    """A fonte não mostrou nenhum arquivo, ou mudou de formato: tratar como falha."""


class SemArquivo(Exception):
    """A fonte disse que o arquivo não existe (ainda ou mais): nem "ok" nem falha."""


class FreioDeDisco(Exception):
    """Pouco espaço para uma fonte pesada."""


def espaco_do_disco(pasta: Path) -> tuple[int, int]:
    """(total, livre) em bytes do disco onde fica `pasta` (ou do primeiro pai que existe)."""
    while not pasta.exists() and pasta != pasta.parent:
        pasta = pasta.parent
    uso = shutil.disk_usage(pasta)
    return uso.total, uso.free


def conferir_freio(total: int, livre: int) -> None:
    if livre < LIVRE_MINIMO_EM_BYTES or (total - livre) / total > USO_MAXIMO_DO_DISCO:
        raise FreioDeDisco(
            f"livre {livre / 1024**3:.0f} GB de {total / 1024**3:.0f} GB"
        )


def texto_visivel(html: bytes) -> str:
    """O texto que uma pessoa lê na página (sem scripts, estilos e etiquetas), para a vigia:
    uma página que só troca um código de sessão não conta como "termo mudou"."""
    texto = SCRIPTS_E_ESTILOS.sub(" ", html.decode("utf-8", errors="replace"))
    return ESPACOS.sub(" ", ETIQUETAS.sub(" ", texto)).strip()


def conferir_tipo(tipo: str, comeco: bytes) -> str | None:
    """O motivo da recusa, ou None se o começo do arquivo combina com o tipo esperado."""
    if tipo != "html" and COMECO_DE_HTML.match(comeco):
        return f"veio HTML no lugar de {tipo}"
    assinaturas = ASSINATURAS.get(tipo)
    if assinaturas and not comeco.lstrip().startswith(assinaturas):
        return f"não parece {tipo}"
    return None


def assinatura(cabecalhos: Mapping[str, str]) -> str:
    """Os cabeçalhos que dizem a versão do arquivo na fonte, numa linha (vai para o detalhe)."""
    minusculos = {k.lower(): v for k, v in cabecalhos.items()}
    partes = [
        f"{nome}={minusculos.get(nome.lower(), '')}"
        for nome in CABECALHOS_GUARDADOS[:3]
    ]
    return "; ".join(partes)


def _sha256_do_arquivo(caminho: Path) -> tuple[str, int, bytes]:
    soma, tamanho, comeco = hashlib.sha256(), 0, b""
    with caminho.open("rb") as arquivo:
        while parte := arquivo.read(TAMANHO_DA_PARTE):
            if not comeco:
                comeco = parte[:512]
            soma.update(parte)
            tamanho += len(parte)
    return soma.hexdigest(), tamanho, comeco


def _escrever_manifesto(agora: datetime, linha: dict[str, object]) -> None:
    pasta = acervo.pasta_do_acervo()
    if pasta is None:
        return
    destino = pasta / "manifesto" / f"{agora:%Y-%m-%d}.jsonl"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")


def _registrar(
    fonte: str,
    url: str,
    sha256: str | None,
    tamanho: int | None,
    situacao: str,
    detalhe: str,
    agora: datetime,
    caminho: str | None = None,
) -> None:
    with obter_engine().begin() as conexao:
        registrar_arquivo(
            conexao, fonte, url, sha256, tamanho, situacao, detalhe, agora, caminho
        )


def _ultima(url: str):  # noqa: ANN202 (linha do banco ou None)
    with obter_engine().connect() as conexao:
        return ultima_coleta_ok(conexao, url)


def _assinatura_registrada(detalhe: str | None) -> str:
    return (detalhe or "").split(SEPARADOR_DO_DETALHE)[0]


def _ja_guardado(fonte: Fonte, alvo: Alvo, cliente: Cliente, anterior: sa.Row) -> bool:
    """O que a última coleta "ok" guardou ainda vale (não precisa baixar de novo)?"""
    if fonte.guardado_vale is not None:
        return fonte.guardado_vale(anterior)
    if not fonte.pesada:
        return False
    cab = assinatura(cliente.cabecalhos(alvo.url))
    return cab != assinatura({}) and cab == _assinatura_registrada(anterior.detalhe)


def _arquivar_um(
    fonte: Fonte,
    alvo: Alvo,
    cliente: Cliente,
    agora: datetime,
    temporario: Path,
    resultado: Resultado,
) -> None:
    anterior = _ultima(alvo.url)
    if anterior is not None and _ja_guardado(fonte, alvo, cliente, anterior):
        resultado.pulados += 1
        log.info("%s: %s já guardado e sem mudança; não baixa", fonte.id, alvo.url)
        return
    if alvo.obter is not None:
        cabecalhos = alvo.obter(cliente, temporario)
    else:
        cabecalhos = cliente.baixar(alvo.url, temporario)
    sha256, tamanho, comeco = _sha256_do_arquivo(temporario)
    detalhe = assinatura(cabecalhos)
    motivo = conferir_tipo(fonte.tipo, comeco)
    if motivo:
        temporario.unlink(missing_ok=True)
        raise ValueError(motivo)
    if fonte.vigia:
        texto = hashlib.sha256(
            texto_visivel(temporario.read_bytes()).encode()
        ).hexdigest()[:16]
        detalhe += f"; texto={texto}"
        if anterior is not None and f"texto={texto}" not in (anterior.detalhe or ""):
            resultado.mudaram.append(alvo.url)
    igual = anterior is not None and anterior.sha256 == sha256
    if igual:
        detalhe += SEPARADOR_DO_DETALHE + IGUAL_A_ANTERIOR
    caminho = acervo.guardar_arquivo(
        fonte.id, alvo.url, temporario, sha256, agora, alvo.extensao
    )
    _registrar(fonte.id, alvo.url, sha256, tamanho, "ok", detalhe, agora, caminho)
    _escrever_manifesto(
        agora,
        {
            "fonte": fonte.id,
            "url": alvo.url,
            "sha256": sha256,
            "bytes": tamanho,
            "caminho": caminho,
            "igual_a_anterior": igual,
            "cabecalhos": {
                k: v for k, v in cabecalhos.items() if k in CABECALHOS_GUARDADOS
            },
            "hora": agora.isoformat(),
            "versao_do_arquivista": VERSAO_DO_ARQUIVISTA,
        },
    )
    if igual:
        resultado.iguais += 1
    else:
        resultado.novos += 1


def arquivar(
    fonte: Fonte,
    cliente: Cliente,
    agora: datetime,
    pasta_temporaria: Path,
    *,
    pausa: float = PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS,
    espaco: Callable[[Path], tuple[int, int]] = espaco_do_disco,
) -> Resultado:
    """Baixa, confere, guarda e registra cada arquivo da fonte, um pedido por vez.

    Levanta `ErroDeDescoberta` (a fonte não mostrou arquivo) e `FreioDeDisco`; falha num arquivo
    fica registrada como "falhou" e não impede os outros.
    """
    if fonte.pesada:
        conferir_freio(*espaco(acervo.pasta_do_acervo() or pasta_temporaria))
    alvos = fonte.descobrir(cliente, agora)
    if not alvos:
        raise ErroDeDescoberta(f"{fonte.id}: nenhum arquivo encontrado")
    pasta_temporaria.mkdir(parents=True, exist_ok=True)
    resultado = Resultado(fonte.id)
    espera = max(pausa, fonte.pausa_minima) if pausa else 0.0  # pausa 0: testes
    for numero, alvo in enumerate(alvos):
        if numero and espera:
            esperar(espera)
        temporario = pasta_temporaria / f"{fonte.id}-{numero}.parcial"
        try:
            _arquivar_um(fonte, alvo, cliente, agora, temporario, resultado)
        except SemArquivo as motivo:
            temporario.unlink(missing_ok=True)
            log.info("%s: sem arquivo em %s (%s)", fonte.id, alvo.url, motivo)
            resultado.sem_arquivo += 1
            _registrar(
                fonte.id, alvo.url, None, None, "nao_encontrado", str(motivo), agora
            )
        except Exception as erro:  # noqa: BLE001 (cada arquivo falha sozinho, com registro)
            temporario.unlink(missing_ok=True)
            log.warning("%s: falhou %s (%s)", fonte.id, alvo.url, erro)
            resultado.falhas.append(alvo.url)
            detalhe = f"{type(erro).__name__}: {erro}"
            _registrar(fonte.id, alvo.url, None, None, "falhou", detalhe, agora)
    return resultado


def guardar_copia(
    fonte: str,
    url: str,
    arquivo: Path,
    sha256: str,
    agora: datetime,
    *,
    origem: str,
    extensao: str | None = None,
) -> str | None:
    """Guarda no acervo um arquivo que outra máquina baixou (a cópia da B3 no VPS, ADR 0073) e o
    registra como coleta "ok", com a origem no detalhe e no manifesto. `arquivo` some (é movido).

    `extensao`, como no `Alvo`: quando o endereço não diz (".zip" da B3)."""
    tamanho = arquivo.stat().st_size
    caminho = acervo.guardar_arquivo(fonte, url, arquivo, sha256, agora, extensao)
    _registrar(fonte, url, sha256, tamanho, "ok", f"cópia do {origem}", agora, caminho)
    _escrever_manifesto(
        agora,
        {
            "fonte": fonte,
            "url": url,
            "sha256": sha256,
            "bytes": tamanho,
            "caminho": caminho,
            "origem": origem,
            "hora": agora.isoformat(),
            "versao_do_arquivista": VERSAO_DO_ARQUIVISTA,
        },
    )
    return caminho
